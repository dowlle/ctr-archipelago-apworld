"""Archipelago Launcher component for the room page's "Connect via Game Client"
link (issue #334, implementation slice 5).

The WebHost room page links each slot as

    archipelago://<slot>:None@<host>:<port>?game=<game>&room=<room id>

(WebHostLib/templates/macros.html). With ``game_name`` and ``supports_uri``
set, the Launcher offers this component for Crash Team Racing slots and
passes that URI, untouched, as the first argument of ``launch_client``.

This component only translates. It validates the room link strictly, drops
the password field (the room page emits the literal sentinel ``None``, and a
password is never forwarded anywhere), builds the credential-free

    ctr-ap://connect?host=<host>&port=<port>&slot=<slot>&room=<room id>

request that ctr-native-ap's launch-request parser accepts, and hands it to
the operating system once through ``webbrowser.open``. The native client owns
everything after that: its registered ``ctr-ap`` link handler, the disc, the
connection config and any password prompt.

It stores nothing, picks no executable, reads no disc, edits no Steam data,
registers no handler, downloads nothing and starts no process of its own.

Diagnostics are fixed strings. No message ever contains the source URI, a
field value or a password.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import quote, unquote_to_bytes

GAME_NAME = "Crash Team Racing"
COMPONENT_NAME = "Crash Team Racing Client"

SOURCE_SCHEME = "archipelago://"
TARGET_PREFIX = "ctr-ap://connect?"

# Bounds of ctr-native-ap's parser (include/platform/native_launch_request.h).
# Field limits are UTF-8 byte counts after percent-decoding.
URI_MAX = 2048
HOST_MAX = 116
SLOT_MAX = 63
ROOM_MAX = 64
PORT_MIN = 1
PORT_MAX = 65535

# A room link is short; anything much longer is not one.
SOURCE_URI_MAX = 2048

_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DNS_CHARS = re.compile(r"[A-Za-z0-9_\-]+")
_IPV6_CHARS = re.compile(r"[0-9A-Fa-f:.]+")

SETUP_TITLE = "Crash Team Racing Client"
SETUP_TEXT = (
    "Crash Team Racing connects from the Archipelago room page.\n\n"
    "Open your room, click your slot name, and choose \"Crash Team Racing Client\". "
    "The CTR client (ctr-native-ap) then starts and connects to that slot.\n\n"
    "This needs the CTR client's ctr-ap link registration, which you turn on in the "
    "CTR client itself. See the Crash Team Racing setup guide for details.\n\n"
    "Nothing was opened."
)
ERROR_TITLE = "Crash Team Racing Client"
OPEN_FAILED_TEXT = (
    "The room link was valid, but the operating system could not open the CTR client. "
    "Check that the CTR client's ctr-ap link registration is turned on, then click the "
    "slot on the room page again."
)


class RoomLinkError(ValueError):
    """A rejected room link. ``reason`` is a fixed string that never contains
    the source URI or any value taken from it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _decode(raw: str, plus_is_space: bool) -> str:
    """Strict percent-decoding: malformed escapes, invalid UTF-8 and control
    characters are rejected rather than passed through or replaced."""
    if _BAD_ESCAPE.search(raw):
        raise RoomLinkError("malformed percent escape")
    if plus_is_space:
        # The Launcher picks the component with urllib's parse_qs, which reads
        # '+' as a space, so the game check must read it the same way.
        raw = raw.replace("+", " ")
    try:
        text = unquote_to_bytes(raw).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise RoomLinkError("invalid UTF-8") from None
    if any(unicodedata.category(ch) == "Cc" for ch in text):
        raise RoomLinkError("control character not allowed")
    return text


def _host_is_valid(host: str) -> bool:
    """Mirror of hostIsValid() in ctr-native-ap platform/native_launch_request.c:
    a DNS name ([A-Za-z0-9_-] labels, no empty label), an IPv4 literal when every
    character is a digit or dot, or a bracketed IPv6 literal (hex, ':' and '.')."""
    if not host:
        return False
    if host.startswith("["):
        inner = host[1:-1]
        return (len(host) >= 4 and host.endswith("]")
                and _IPV6_CHARS.fullmatch(inner) is not None and ":" in inner)
    labels = host.split(".")
    if any(not label or _DNS_CHARS.fullmatch(label) is None for label in labels):
        return False
    if all(ch.isdigit() or ch == "." for ch in host):
        if len(labels) != 4:
            return False
        return all(len(label) <= 3 and int(label) <= 255 for label in labels)
    return True


def _split_host_port(hostinfo: str) -> Tuple[str, int]:
    if hostinfo.startswith("["):
        end = hostinfo.find("]")
        if end < 0:
            raise RoomLinkError("invalid host")
        host, rest = hostinfo[:end + 1], hostinfo[end + 1:]
        if not rest.startswith(":"):
            raise RoomLinkError("missing port")
        port_text = rest[1:]
    else:
        host, sep, port_text = hostinfo.partition(":")
        if not sep:
            raise RoomLinkError("missing port")
    if "%" in host:
        raise RoomLinkError("invalid host")
    if not _host_is_valid(host) or len(host.encode("ascii")) > HOST_MAX:
        raise RoomLinkError("invalid host")
    if not (1 <= len(port_text) <= 5) or not all("0" <= ch <= "9" for ch in port_text):
        raise RoomLinkError("invalid port")
    port = int(port_text)
    if not (PORT_MIN <= port <= PORT_MAX):
        raise RoomLinkError("invalid port")
    return host.lower(), port


def _parse_query(query: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not query:
        raise RoomLinkError("missing query")
    for segment in query.split("&"):
        key_raw, sep, value_raw = segment.partition("=")
        if not sep or not key_raw:
            raise RoomLinkError("malformed query")
        key = _decode(key_raw, plus_is_space=True)
        if key in values:
            raise RoomLinkError("duplicate query key")
        values[key] = _decode(value_raw, plus_is_space=True)
    return values


def convert_room_link(source: str) -> str:
    """Validate a WebHost room link and return the matching credential-free
    ``ctr-ap://connect`` request. Raises RoomLinkError with a fixed reason."""
    if not isinstance(source, str) or not source:
        raise RoomLinkError("no room link")
    if len(source) > SOURCE_URI_MAX:
        raise RoomLinkError("room link too long")
    if any(unicodedata.category(ch) == "Cc" for ch in source):
        raise RoomLinkError("control character not allowed")
    if not source.startswith(SOURCE_SCHEME):
        raise RoomLinkError("not an archipelago:// room link")
    if "#" in source:
        raise RoomLinkError("fragment not allowed")

    rest = source[len(SOURCE_SCHEME):]
    head, sep, query = rest.partition("?")
    if not sep:
        raise RoomLinkError("missing query")
    netloc, slash, path = head.partition("/")
    if slash and path:
        raise RoomLinkError("unexpected path")

    # Same split as urllib and the core CommonClient: the last '@' ends the
    # user info and the first ':' inside it starts the password field.
    userinfo, at, hostinfo = netloc.rpartition("@")
    if not at:
        raise RoomLinkError("missing slot name")
    # Everything after that ':' is the password field. It is deliberately never
    # decoded, inspected or kept. The room page always writes the sentinel
    # "None"; a hand-made link carrying a real password is treated the same
    # way, and the native client asks for the password itself when needed.
    slot_raw = userinfo.partition(":")[0]

    host, port = _split_host_port(hostinfo)

    slot = _decode(slot_raw, plus_is_space=False)
    if not slot:
        raise RoomLinkError("missing slot name")
    if slot != slot.strip():
        raise RoomLinkError("slot name has edge whitespace")
    if len(slot.encode("utf-8")) > SLOT_MAX:
        raise RoomLinkError("slot name too long")

    query_values = _parse_query(query)
    if query_values.get("game") != GAME_NAME:
        raise RoomLinkError("room link is not for Crash Team Racing")
    room = query_values.get("room", "")
    if not room:
        raise RoomLinkError("missing room id")
    if len(room.encode("utf-8")) > ROOM_MAX:
        raise RoomLinkError("room id too long")
    if any(ch in room for ch in "/\\@"):
        raise RoomLinkError("invalid room id")

    target = (f"{TARGET_PREFIX}host={quote(host, safe='')}&port={port}"
              f"&slot={quote(slot, safe='')}&room={quote(room, safe='')}")
    if len(target) > URI_MAX:
        raise RoomLinkError("connect request too long")
    return target


def _show(title: str, text: str, error: bool) -> None:
    try:
        from Utils import messagebox
        messagebox(title, text, error=error)
    except Exception:  # headless or no dialog backend: the log line is enough
        (logging.error if error else logging.info)(f"{title}: {text}")


def launch_client(*args: str,
                  open_url: Optional[Callable[[str], bool]] = None,
                  show: Callable[[str, str, bool], None] = _show) -> bool:
    """Launcher entry point. Returns True only when a connect request was
    handed to the operating system."""
    if not args:
        show(SETUP_TITLE, SETUP_TEXT, False)
        return False
    if len(args) != 1:
        reason = "expected exactly one room link"
    else:
        try:
            target = convert_room_link(args[0])
        except RoomLinkError as error:
            reason = error.reason
        else:
            if open_url is None:
                import webbrowser
                open_url = webbrowser.open
            try:
                opened = open_url(target)
            except Exception:
                opened = False
            if not opened:
                logging.error("Crash Team Racing Client: could not open the ctr-ap connect request.")
                show(ERROR_TITLE, OPEN_FAILED_TEXT, True)
                return False
            logging.info("Crash Team Racing Client: connect request handed to the CTR client.")
            return True
    logging.error(f"Crash Team Racing Client: room link rejected ({reason}).")
    show(ERROR_TITLE, f"This room link could not be used: {reason}.\n\nNothing was opened.", True)
    return False


def register() -> None:
    """Append the component once. Called from the world package on import."""
    from worlds.LauncherComponents import Component, Type, components
    if any(getattr(c, "display_name", None) == COMPONENT_NAME for c in components):
        return
    components.append(Component(
        COMPONENT_NAME,
        func=launch_client,
        game_name=GAME_NAME,
        component_type=Type.CLIENT,
        supports_uri=True,
        description="Connect the CTR client from a room page slot link.",
    ))
