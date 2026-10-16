"""Room titles for custom tracks: sanitizing and clash suffixes (#306).

A custom track's title is community text. Before it names a location in a room,
in Universal Tracker or in a frozen named block, it goes through the same two
steps everywhere:

1. `sanitize_title`: Unicode NFC, no control or format characters, square and
   curly brackets turned into round ones (Universal Tracker renders Kivy
   markup), whitespace collapsed, at most TITLE_MAX_CHARS characters and
   TITLE_MAX_BYTES UTF-8 bytes. The longest location name built from a room
   title still fits the content plan's 128-byte label limit.
2. `room_title`: the clash suffixes ruled on 2026-10-13. A title equal to a
   retail name (any registered CTR location stem, such as `Crash Cove`) gets
   `(Custom)`: `Crash Cove (Custom)`. A title equal to another custom track's
   name gets the author: `Crash Cove (Custom, Author)`. Names already taken
   keep their place; the later track gets the suffix.

Comparisons ignore case, so `crash cove` clashes with `Crash Cove` too.
"""
import re
import unicodedata
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple

TITLE_MAX_CHARS = 40
TITLE_MAX_BYTES = 60
AUTHOR_MAX_CHARS = 24
AUTHOR_MAX_BYTES = 30
#: A full room title, suffixes included. 105 bytes plus the longest suffix
#: ": Finish (Any Position)" (23 bytes) is the 128-byte label limit.
ROOM_TITLE_MAX_CHARS = 80
ROOM_TITLE_MAX_BYTES = 105

_GENERIC = re.compile(r"custom track \d+")
_BRACKETS = str.maketrans({"[": "(", "]": ")", "{": "(", "}": ")"})


def sanitize_title(raw, max_chars: int = TITLE_MAX_CHARS,
                   max_bytes: int = TITLE_MAX_BYTES) -> Optional[str]:
    """Clean community text into a safe title, or None when nothing is left."""
    if not isinstance(raw, str):
        return None
    text = unicodedata.normalize("NFC", raw).translate(_BRACKETS)
    kept = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch.isspace() or category.startswith("Z"):
            kept.append(" ")
        elif not category.startswith("C"):
            kept.append(ch)
    text = " ".join("".join(kept).split()).strip(" :")
    text = text[:max_chars]
    while len(text.encode("utf-8")) > max_bytes:
        text = text[:-1]
    text = text.rstrip(" :")
    return text or None


def is_sanitized(name: str) -> bool:
    return sanitize_title(name, ROOM_TITLE_MAX_CHARS, ROOM_TITLE_MAX_BYTES) == name


_RESERVED_CACHE: Optional[Set[str]] = None


def reserved_stems() -> Set[str]:
    """Casefolded name stems a custom title must not reuse: every registered
    CTR location stem (retail tracks, cups, garages, `Wumpa`, `Custom Track N`)
    except the named blocks', plus every destination name."""
    global _RESERVED_CACHE
    if _RESERVED_CACHE is None:
        from . import destinations
        from .Locations import CTR_LOCATION_IDS
        from .named_tracks import NAMED_TRACK_CLASS
        named = set(NAMED_TRACK_CLASS.names())
        stems = {name.split(": ", 1)[0].casefold()
                 for name in CTR_LOCATION_IDS if ": " in name and name not in named}
        stems |= {d.key.casefold() for d in destinations.BY_KEY.values()}
        stems |= {d.region_name.casefold() for d in destinations.BY_KEY.values()}
        _RESERVED_CACHE = stems
    return _RESERVED_CACHE


def named_stems() -> Set[str]:
    from .destinations import NAMED_TRACKS
    return {t.ap_name.casefold() for t in NAMED_TRACKS}


def room_title(title, author=None, *, fallback_author: str = "",
               reserved: Optional[Set[str]] = None,
               taken: Iterable[str] = ()) -> Optional[str]:
    """The suffixed room title for one track, or None when the title is empty.

    `reserved` holds retail stems (default `reserved_stems()`); `taken` holds
    names other custom tracks already use. Both are compared casefolded.
    """
    base = sanitize_title(title)
    if base is None:
        return None
    reserved = reserved_stems() if reserved is None else reserved
    taken = {t.casefold() for t in taken}
    candidate = base
    if base.casefold() in reserved or _GENERIC.fullmatch(base.casefold()):
        candidate = f"{base} (Custom)"
    if candidate.casefold() in taken:
        who = (sanitize_title(author, AUTHOR_MAX_CHARS, AUTHOR_MAX_BYTES)
               or sanitize_title(fallback_author, AUTHOR_MAX_CHARS, AUTHOR_MAX_BYTES)
               or "Unknown")
        candidate = f"{base} (Custom, {who})"
        number = 2
        while candidate.casefold() in taken:
            candidate = f"{base} (Custom, {who} {number})"
            number += 1
    assert len(candidate.encode("utf-8")) <= ROOM_TITLE_MAX_BYTES
    return candidate


def seed_titles(entries: Sequence[Tuple[int, object, object, str]],
                taken: Iterable[str] = ()) -> Dict[int, str]:
    """{slot: room title} for one player's generic-slot tracks, in slot order.

    `entries` holds (slot, title, author, fallback author). Every named block's
    stem is taken from the start, so a generic track never shows a named
    track's name. A track with no usable title keeps its generic name.
    """
    used = set(named_stems()) | {t.casefold() for t in taken}
    out: Dict[int, str] = {}
    for slot, title, author, fallback_author in sorted(entries, key=lambda e: e[0]):
        resolved = room_title(title, author, fallback_author=fallback_author, taken=used)
        if resolved is not None:
            out[slot] = resolved
            used.add(resolved.casefold())
    return out


# -- legacy custom_tracks path: the schema-18 `custom_track_titles` block -------

TITLES_WIRE_VERSION = 1


def legacy_titles(tracks: Mapping[str, Mapping]) -> Dict[int, str]:
    """Room titles for the normalized legacy descriptor.

    A track on a named block (#133) is titled by the block's frozen `ap_name`,
    which is already the stem of its location names. A generic-slot track
    uses the descriptor's own `title` and `author` when present, else the
    compiled title table, with the clash suffixes above."""
    from .custom_tracks import TRACK_DISPLAY_NAMES
    named = {int(entry["slot"]): entry["ap_name"] for entry in tracks.values()
             if entry.get("named_block") is not None}
    out = seed_titles([(int(entry["slot"]),
                        entry.get("title", TRACK_DISPLAY_NAMES.get(track_id)),
                        entry.get("author"), track_id)
                       for track_id, entry in tracks.items()
                       if int(entry["slot"]) not in named])
    out.update(named)
    return dict(sorted(out.items()))


def titles_to_wire(titles: Mapping[int, str]) -> Dict[str, object]:
    return {"version": TITLES_WIRE_VERSION,
            "tracks": [{"slot": slot, "title": title} for slot, title in sorted(titles.items())]}


def titles_from_wire(block, slots: Iterable[int]) -> Optional[Dict[int, str]]:
    """Read the block back for Universal Tracker; None when absent or unusable.

    Every title must already be a sanitized room title and every slot must be
    one of the seed's custom slots, so a forged block cannot rename anything
    the seed does not own.
    """
    if not isinstance(block, Mapping) or type(block.get("version")) is not int or block["version"] != TITLES_WIRE_VERSION:
        return None
    rows = block.get("tracks")
    if not isinstance(rows, (list, tuple)):
        return None
    allowed, out = set(slots), {}
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        slot, title = row.get("slot"), row.get("title")
        if (type(slot) is not int or slot not in allowed or slot in out
                or not isinstance(title, str) or not is_sanitized(title)):
            return None
        out[slot] = title
    return out
