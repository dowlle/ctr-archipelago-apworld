#!/usr/bin/env python3
"""CTR solo runtime wrapper (#89).

The native client starts this script with the bundled interpreter to generate
solo seeds and to host a private MultiServer for one solo room. It talks JSON
lines on stdout; everything else (Archipelago logging, prints) goes to stderr
or a log file.

Layout inside a client folder (see RUNTIME.txt for the pinned parts):

    <client>/ctr.apworld            the release world, the only one loaded
    <client>/solo-runtime/          this script, presets, overlay, the core
    <client>/solo/                  rooms, YAMLs, inbox, tracks and ap-home (writable)

Commands:
    list                      rooms, saved YAMLs, inbox YAMLs and presets
    tracks                    installed custom tracks a new seed can include
    describe                  options of the loaded world plus the overlay
    validate  --yaml F        roll the settings and run the option checks
    generate  --yaml F        generate a room into solo/rooms/<room id>/
                              (--track ID adds an installed custom track,
                              --guarantee ID gives it an Adventure pad)
    import-yaml   F           validate and keep a copy in solo/yamls/
    import-room   F           accept a one-player CTR room as a solo room
    serve --room ID           host one room on 127.0.0.1 until told to stop

The wrapper never reads the player's global Archipelago install: it points
Archipelago's user folder at solo/ap-home before importing anything and
checks that only the Generic and CTR worlds were loaded. It never opens an
outbound connection and always binds 127.0.0.1.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import zipfile

# The runtime folder is read-only to the runtime: never write .pyc files.
sys.dont_write_bytecode = True

GAME = "Crash Team Racing"
PROTOCOL = 1
PORT_FIRST = 38301
PORT_LAST = 38320
HOST = "127.0.0.1"
ROOM_ID_HEX = 16
ALLOWED_GAMES = {"Archipelago", GAME}

# The protocol stream. Everything else printed by Archipelago goes to stderr.
_PROTOCOL_OUT = sys.stdout
_last_phase = None


def emit(event: str, **fields) -> None:
    global _last_phase
    if event == "progress":
        if fields.get("phase") == _last_phase:
            return
        _last_phase = fields.get("phase")
    fields = {"event": event, **fields}
    _PROTOCOL_OUT.write(json.dumps(fields, sort_keys=True) + "\n")
    _PROTOCOL_OUT.flush()


class SoloError(Exception):
    """A refusal the client shows to the player. kind is machine readable."""

    def __init__(self, kind: str, message: str, **detail):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail


# ---------------------------------------------------------------------------
# Paths and runtime identity


class Paths:
    def __init__(self, runtime: str, solo: str, apworld: str, core: str):
        self.runtime = os.path.abspath(runtime)
        self.solo = os.path.abspath(solo)
        self.apworld = os.path.abspath(apworld)
        self.core = os.path.abspath(core)
        self.ap_home = os.path.join(self.solo, "ap-home")
        self.rooms = os.path.join(self.solo, "rooms")
        self.yamls = os.path.join(self.solo, "yamls")
        self.inbox = os.path.join(self.solo, "inbox")
        self.tmp = os.path.join(self.solo, "tmp")
        self.tracks = os.path.join(self.solo, "tracks")
        self.presets = os.path.join(self.runtime, "presets")
        self.overlay = os.path.join(self.runtime, "options-overlay.json")

    def ensure(self) -> None:
        # Parents before children, each checked before anything is created
        # inside it, so a link can never receive a new folder. The solo
        # folder itself must be a real folder in the client folder.
        if os.path.islink(self.solo):
            raise SoloError("runtime", f"The solo folder is a link: {self.solo}")
        os.makedirs(self.solo, exist_ok=True)
        for path in (self.ap_home, os.path.join(self.ap_home, "worlds"), self.rooms, self.yamls, self.inbox,
                     self.tmp, self.tracks):
            self.check_one(path)
            os.makedirs(path, exist_ok=True)
        self.check_inside()

    def check_one(self, path: str) -> None:
        root = os.path.realpath(self.solo)
        if os.path.islink(path) or (os.path.exists(path) and
                                    os.path.commonpath([root, os.path.realpath(path)]) != root):
            raise SoloError("runtime", f"A solo folder leads outside the solo folder: {path}")

    def check_inside(self) -> None:
        """The wrapper deletes and writes in these folders. A link that leads
        elsewhere (for example to a global Archipelago worlds folder) is
        refused before anything is touched."""
        root = os.path.realpath(self.solo)
        for path in (self.ap_home, self.rooms, self.yamls, self.inbox, self.tmp, self.tracks,
                     os.path.join(self.ap_home, "worlds")):
            real = os.path.realpath(path)
            if os.path.islink(path) or os.path.commonpath([root, real]) != root:
                raise SoloError("runtime", f"A solo folder leads outside the solo folder: {path}")

    def room_dir(self, room_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{%d}" % ROOM_ID_HEX, room_id or ""):
            raise SoloError("bad_room", f"Not a room id: {room_id!r}")
        path = os.path.join(self.rooms, room_id)
        if os.path.islink(path):
            raise SoloError("bad_room", "That solo room is a link, not a folder.", room_id=room_id)
        return path


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_manifest(runtime: str) -> dict:
    """RUNTIME.txt lines are `key: value`. Missing file means a dev checkout."""
    result = {}
    path = os.path.join(runtime, "RUNTIME.txt")
    if not os.path.isfile(path):
        return result
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            key, sep, value = line.partition(":")
            if sep and not line.startswith("#"):
                result[key.strip()] = value.strip()
    return result


def check_apworld(paths: Paths, expected: str | None) -> str:
    if not os.path.isfile(paths.apworld):
        raise SoloError("runtime", f"ctr.apworld is missing: {paths.apworld}")
    actual = sha256_file(paths.apworld)
    if expected is None:
        expected = runtime_manifest(paths.runtime).get("ctr.apworld sha256")
    if expected and actual != expected.lower():
        raise SoloError("runtime", "ctr.apworld does not match the solo runtime",
                        expected=expected.lower(), actual=actual)
    return actual


def write_json_atomic(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Archipelago bootstrap


_archipelago_ready = False


def _redirect_stdout() -> None:
    # Archipelago and the world print freely. Keep stdout for the protocol.
    sys.stdout = sys.stderr


def bootstrap_core(paths: Paths, load_worlds: bool) -> None:
    """Import Archipelago from the bundled core with solo/ap-home as its user
    folder. load_worlds also loads the world registry and checks it."""
    global _archipelago_ready
    if not _archipelago_ready:
        os.environ["SKIP_REQUIREMENTS_UPDATE"] = "1"
        # The bundled dependencies, then the core, ahead of anything else.
        site = os.path.join(paths.runtime, "site-packages")
        for folder in (site, paths.core):
            if os.path.isdir(folder) and folder not in sys.path:
                sys.path.insert(0, folder)
        _redirect_stdout()
        # NetUtils compiles _speedups through pyximport when Cython is around,
        # into the user's home. The runtime never compiles: use the pure
        # Python fallback.
        sys.modules["pyximport"] = None
        import Utils  # noqa: E402  (bundled core)
        if os.path.normcase(os.path.dirname(os.path.abspath(Utils.__file__))) != os.path.normcase(paths.core):
            raise SoloError("runtime", f"Archipelago was imported from {Utils.__file__}, not the solo runtime")
        Utils.local_path.cached_path = paths.core
        Utils.user_path.cached_path = paths.ap_home
        Utils.home_path.cached_path = paths.ap_home
        Utils.cache_path.cached_path = os.path.join(paths.ap_home, "cache")
        # Archipelago reads options.yaml / host.yaml from the working folder
        # first, and its output stage uses the system temp folder. Keep both
        # inside solo/.
        os.chdir(paths.ap_home)
        tempfile.tempdir = paths.tmp
        _archipelago_ready = True
    if load_worlds and "worlds" not in sys.modules:
        _stage_world(paths)
        import worlds  # noqa: F401,E402
        from worlds.AutoWorld import AutoWorldRegister
        loaded = set(AutoWorldRegister.world_types)
        if GAME not in loaded:
            from worlds import failed_world_loads
            raise SoloError("runtime", "Crash Team Racing did not load", failed=sorted(failed_world_loads))
        extra = loaded - ALLOWED_GAMES
        if extra:
            raise SoloError("runtime", "The solo runtime loaded other worlds", worlds=sorted(extra))


def _stage_world(paths: Paths) -> None:
    """ap-home/worlds holds exactly one file: a copy of the client's ctr.apworld.
    Archipelago scans that folder and the core's own worlds folder only."""
    folder = os.path.join(paths.ap_home, "worlds")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, "ctr.apworld")
    for entry in os.listdir(folder):
        full = os.path.join(folder, entry)
        if entry == "ctr.apworld":
            continue
        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
    if not os.path.isfile(target) or sha256_file(target) != sha256_file(paths.apworld):
        shutil.copyfile(paths.apworld, target + ".tmp")
        os.replace(target + ".tmp", target)


def world_class():
    from worlds.AutoWorld import AutoWorldRegister
    return AutoWorldRegister.world_types[GAME]


def world_version() -> str:
    return world_class().world_version.as_simple_string()


def ap_version() -> str:
    import Utils
    return Utils.__version__


# ---------------------------------------------------------------------------
# describe


def _option_kind(option) -> str:
    import Options
    for cls, name in ((Options.NamedRange, "named_range"), (Options.Range, "range"),
                      (Options.Toggle, "toggle"), (Options.TextChoice, "text_choice"),
                      (Options.Choice, "choice"), (Options.OptionSet, "set"),
                      (Options.OptionList, "list"), (Options.OptionCounter, "counter"),
                      (Options.OptionDict, "dict"), (Options.FreeText, "text")):
        if issubclass(option, cls):
            return name
    return "other"


def _clean_doc(text: str | None) -> str:
    import inspect
    return inspect.cleandoc(text or "").strip()


def describe_option(name: str, option) -> dict:
    import Options
    kind = _option_kind(option)
    entry = {"name": name, "display_name": getattr(option, "display_name", name), "kind": kind,
             "doc": _clean_doc(option.__doc__)}
    default = option.default
    if issubclass(option, Options.Choice):
        names = {}
        for key, value in option.options.items():
            names.setdefault(value, key)  # first spelling wins, aliases later
        entry["choices"] = [{"name": names[v], "value": v} for v in sorted(names)]
        if isinstance(default, int) and default in names:
            entry["default"] = names[default]
        else:
            entry["default"] = default
    elif issubclass(option, Options.Range):
        entry["range_start"] = option.range_start
        entry["range_end"] = option.range_end
        entry["default"] = default
        if issubclass(option, Options.NamedRange):
            entry["special_range_names"] = dict(option.special_range_names)
    elif issubclass(option, Options.Toggle):
        entry["default"] = bool(default)
    else:
        if isinstance(default, (set, frozenset)):
            default = sorted(default)
        try:
            json.dumps(default)
        except TypeError:
            default = repr(default)
        entry["default"] = default
        keys = getattr(option, "valid_keys", None)
        if keys:
            entry["valid_keys"] = sorted(keys)
    return entry


def _canonical(option, raw):
    """The value the options screen shows: choice name, bool or int."""
    import Options
    value = option.from_any(raw)
    if isinstance(value, Options.Choice):
        return value.current_key
    if isinstance(value, Options.Toggle):
        return bool(value.value)
    if isinstance(value, Options.Range):
        return int(value.value)
    return None


def overlay_values(yaml_path: str | None, overlay: dict) -> dict:
    """Values of the overlay's options in a YAML (or the defaults). A weighted
    or random value cannot be shown on the screen and falls back to the default."""
    hints = world_class().options_dataclass.type_hints
    section = {}
    if yaml_path:
        doc = read_player_yaml(yaml_path)
        section = doc.get(GAME) or {}
        if not isinstance(section, dict):
            section = {}
    values = {}
    for group in overlay.get("groups", []):
        for name in group.get("options", []):
            option = hints.get(name)
            if option is None:
                continue
            raw = section.get(name, option.default)
            if isinstance(raw, dict) or (isinstance(raw, str) and raw.strip().lower().startswith("random")):
                raw = option.default
            try:
                values[name] = _canonical(option, raw)
            except Exception:
                values[name] = _canonical(option, option.default)
    return values


def describe(paths: Paths, yaml_path: str | None = None) -> dict:
    cls = world_class()
    options = [describe_option(name, option)
               for name, option in cls.options_dataclass.type_hints.items()]
    overlay = load_overlay(paths)
    return {"game": GAME, "world_version": world_version(), "ap_version": ap_version(),
            "options": options, "overlay": overlay, "presets": list_presets(paths),
            "values": overlay_values(yaml_path, overlay)}


def load_overlay(paths: Paths) -> dict:
    if not os.path.isfile(paths.overlay):
        return {}
    return read_json(paths.overlay)


# ---------------------------------------------------------------------------
# YAML handling


def _load_yaml_documents(path: str) -> list:
    from Utils import parse_yamls
    try:
        with open(path, "rb") as handle:
            text = handle.read().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        with open(path, "rb") as handle:
            line = handle.read()[:error.start].count(b"\n") + 1
        raise SoloError("yaml", "The YAML is not UTF-8 text.", file=os.path.basename(path), line=line)
    except OSError as error:
        raise SoloError("yaml", f"Could not read the YAML: {error}", file=os.path.basename(path))
    try:
        docs = list(parse_yamls(text))
    except Exception as error:  # yaml.MarkedYAMLError carries the line number
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise SoloError("yaml", f"The YAML could not be read: {error}",
                        file=os.path.basename(path), line=line)
    return docs


def _weight(value) -> int:
    """A weight as Archipelago reads it (int of the value); unreadable is 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_player_yaml(path: str) -> dict:
    """One document, one CTR player. Returns the document."""
    docs = _load_yaml_documents(path)
    if not docs or all(doc is None for doc in docs):
        raise SoloError("yaml", "The YAML is empty.", file=os.path.basename(path))
    if len(docs) > 1:
        raise SoloError("players", "Solo seeds have one player. This YAML has more than one document.",
                        file=os.path.basename(path), documents=len(docs))
    doc = docs[0]
    if not isinstance(doc, dict):
        raise SoloError("yaml", "The YAML is not a player settings file.", file=os.path.basename(path))
    game = doc.get("game")
    games = [k for k, v in game.items() if _weight(v) > 0] if isinstance(game, dict) else [game]
    if games != [GAME]:
        raise SoloError("game", f"This YAML is for {', '.join(map(str, games)) or 'no game'}, not {GAME}.",
                        file=os.path.basename(path))
    if not str(doc.get("name") or "").strip():
        raise SoloError("yaml", "The YAML has no player name.", file=os.path.basename(path))
    return doc


def apply_overrides(doc: dict, name: str | None, settings: list[str]) -> dict:
    import yaml
    doc = json.loads(json.dumps(doc))  # deep copy, plain types only
    if name:
        doc["name"] = name
    section = doc.setdefault(GAME, {})
    if not isinstance(section, dict):
        raise SoloError("yaml", f"The {GAME} section is not a mapping.")
    known = set(world_class().options_dataclass.type_hints)
    for item in settings:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep or key not in known:
            raise SoloError("option", f"Unknown option {key!r}.", option=key)
        section[key] = yaml.safe_load(raw)
    return doc


def stamp_requires(doc: dict) -> dict:
    """Only for YAMLs this client writes (presets). A YAML that already says
    what it requires keeps it, so Archipelago can refuse a mismatch."""
    if "requires" in doc:
        return doc
    doc = dict(doc)
    doc["requires"] = {"version": ap_version(), "game": {GAME: world_version()}}
    return doc


def dump_yaml(doc: dict, path: str) -> None:
    import yaml
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(doc, handle, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Generation


class _StopAfterOptions(Exception):
    pass


_PHASES = {
    "generate_early": "Checking options",
    "create_regions": "Building the world",
    "create_items": "Building the world",
    "set_rules": "Building the world",
    "connect_entrances": "Building the world",
    "generate_basic": "Placing items",
    "pre_fill": "Placing items",
    "post_fill": "Placing items",
    "generate_output": "Writing room",
}


def _option_error(error: Exception) -> SoloError:
    """Map a world or Archipelago exception to a refusal the client can show."""
    import Options
    text = str(error) or error.__class__.__name__
    hints = world_class().options_dataclass.type_hints
    found = []
    for name, option in hints.items():
        spots = [m.start() for pattern in (name, getattr(option, "display_name", name))
                 for m in [re.search(r"\b%s\b" % re.escape(pattern), text)] if m]
        if spots:
            found.append((min(spots), name))
    named = [name for _, name in sorted(found)]  # the option the message names first
    fill = error.__class__.__name__ in ("FillError",)
    if fill:
        return SoloError("fill", "This combination could not be generated. Try again or change options.",
                         detail=text)
    if isinstance(error, (Options.OptionError, ValueError, KeyError, TypeError)) or named:
        return SoloError("option", text, option=named[0] if named else None, options=named)
    return SoloError("generate", text, error=error.__class__.__name__)


def _run_generation(player_yaml: str, out_dir: str, seed: int | None, stop_after_options: bool,
                    spoiler: int, skip_output: bool = False) -> str | None:
    """Run Generate and Main in process. Returns the room zip path (None for
    skip_output: everything up to and including fill, no room file)."""
    import Generate
    import Main
    from worlds import AutoWorld

    players = os.path.join(out_dir, "players")
    os.makedirs(players, exist_ok=True)
    shutil.copyfile(player_yaml, os.path.join(players, "player.yaml"))
    argv = ["--player_files_path", players, "--outputpath", out_dir, "--spoiler", str(spoiler),
            "--multi", "1", "--weights_file_path", os.path.join(players, "_none.yaml"),
            "--meta_file_path", os.path.join(players, "_none_meta.yaml")]
    if seed is not None:
        argv += ["--seed", str(seed)]
    if skip_output:
        argv += ["--skip_output"]
    args = Generate.mystery_argparse(argv)
    emit("progress", phase="Checking options")
    try:
        erargs, seed_number = Generate.main(args)
    except SystemExit as error:
        raise SoloError("option", f"The settings were refused ({error}).")
    except Exception as error:
        cause = error.__cause__ or error
        raise _option_error(cause)

    original_call_all = AutoWorld.call_all
    seen = set()

    def call_all(multiworld, method_name, *args, **kwargs):
        phase = _PHASES.get(method_name)
        if phase and phase not in seen:
            seen.add(phase)
            emit("progress", phase=phase)
        result = original_call_all(multiworld, method_name, *args, **kwargs)
        if stop_after_options and method_name == "generate_early":
            raise _StopAfterOptions()
        if method_name == "post_fill":
            emit("progress", phase="Writing room")
        return result

    AutoWorld.call_all = call_all
    Main.AutoWorld.call_all = call_all
    try:
        Main.main(erargs, seed_number)
    except _StopAfterOptions:
        return None
    except SoloError:
        raise
    except Exception as error:
        raise _option_error(error)
    finally:
        AutoWorld.call_all = original_call_all
        Main.AutoWorld.call_all = original_call_all
    if skip_output:
        return None
    rooms = [name for name in os.listdir(out_dir) if name.startswith("AP_") and name.endswith(".zip")]
    if len(rooms) != 1:
        raise SoloError("generate", "Generation finished without exactly one room file.")
    return os.path.join(out_dir, rooms[0])


TMP_ABANDONED_SECONDS = 600  # well past the client's 120 s generation limit


def clear_tmp(paths: Paths) -> None:
    """A cancelled generation (the client ends the process) leaves its work
    folder behind. Remove work older than any live job can be."""
    now = time.time()
    for entry in os.listdir(paths.tmp):
        full = os.path.join(paths.tmp, entry)
        try:
            if now - os.path.getmtime(full) < TMP_ABANDONED_SECONDS:
                continue
        except OSError:
            continue
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        else:
            try:
                os.remove(full)
            except OSError:
                pass


def prepare_yaml(paths: Paths, source: str, name: str | None, settings: list[str],
                 stamp: bool, tracks: dict | None = None) -> tuple[dict, str]:
    """Read and override a YAML, add picked custom tracks, write the exact
    input to a temp file."""
    doc = read_player_yaml(source)
    doc = apply_overrides(doc, name, settings)
    if tracks:
        doc = apply_tracks(paths, doc, tracks["assets"], tracks["picked"], tracks["guaranteed"])
    presets = os.path.realpath(paths.presets)
    if stamp or os.path.commonpath([presets, os.path.realpath(source)]) == presets:
        doc = stamp_requires(doc)  # a bundled preset is always this client's own YAML
    fd, tmp = tempfile.mkstemp(prefix="player-", suffix=".yaml", dir=paths.tmp)
    os.close(fd)
    dump_yaml(doc, tmp)
    return doc, tmp


def validate(paths: Paths, source: str, name: str | None, settings: list[str], stamp: bool,
             tracks: dict | None = None) -> dict:
    _, tmp = prepare_yaml(paths, source, name, settings, stamp, tracks)
    work = tempfile.mkdtemp(prefix="validate-", dir=paths.tmp)
    try:
        # The whole generation except writing the room: the world raises some
        # option errors only at fill time (for example the warp pad check in
        # pre_fill), so stopping after generate_early would pass YAMLs that
        # cannot generate.
        _run_generation(tmp, work, None, stop_after_options=False, spoiler=0, skip_output=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        os.remove(tmp)
    return {"ok": True}


def read_multidata(room_path: str) -> dict:
    import MultiServer
    if room_path.lower().endswith(".zip"):
        with zipfile.ZipFile(room_path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".archipelago")]
            if len(names) != 1:
                raise SoloError("room", "The room file does not contain exactly one .archipelago file.")
            data = archive.read(names[0])
    else:
        with open(room_path, "rb") as handle:
            data = handle.read()
    try:
        return MultiServer.Context.decompress(data)
    except Exception as error:
        raise SoloError("room", f"The room file could not be read: {error}")


def room_facts(multidata: dict) -> dict:
    slots = multidata.get("slot_info", {})
    players = {sid: info for sid, info in slots.items() if getattr(info, "type", None) is None
               or int(getattr(info, "type")) == 1}
    if len(slots) != 1 or len(players) != 1:
        raise SoloError("players", "Solo rooms have one player. This room has more than one slot.",
                        slots=len(slots))
    slot_id, info = next(iter(players.items()))
    if info.game != GAME:
        raise SoloError("game", f"This room is for {info.game}, not {GAME}.")
    locations = multidata.get("locations", {}).get(slot_id, {})
    version = multidata.get("version")
    return {"seed_name": multidata.get("seed_name"), "slot": info.name, "slot_id": int(slot_id),
            "locations_total": len(locations),
            "ap_version": ".".join(map(str, version)) if version else None,
            "room_world_version": _room_world_version(multidata, slot_id)}


def _room_world_version(multidata: dict, slot_id) -> str | None:
    """The CTR world_version the room was generated with (slot_data key)."""
    data = multidata.get("slot_data", {}).get(slot_id)
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            value = item.get("world_version")
            if isinstance(value, str):
                return value
            stack.extend(v for v in item.values() if isinstance(v, dict))
    return None


def _custom_tracks(doc: dict | None) -> list:
    if not doc:
        return []
    section = doc.get(GAME) or {}
    pool = section.get("content_pool") if isinstance(section, dict) else None
    tracks = (pool or {}).get("tracks", {}) if isinstance(pool, dict) else {}
    custom = tracks.get("custom") if isinstance(tracks, dict) else None
    return custom if isinstance(custom, list) else []


def install_room(paths: Paths, room_file: str, origin: str, apworld_sha: str, player_yaml: str | None,
                 doc: dict | None, preset: str | None, spoiler: str | None) -> dict:
    multidata = read_multidata(room_file)
    facts = room_facts(multidata)
    digest = sha256_file(room_file)
    room_id = digest[:ROOM_ID_HEX]
    target = paths.room_dir(room_id)
    if os.path.isdir(target):
        raise SoloError("exists", "This room is already in your solo seeds.", room_id=room_id)
    staging = tempfile.mkdtemp(prefix="room-", dir=paths.tmp)
    room_name = os.path.basename(room_file)
    if not room_name.lower().endswith((".zip", ".archipelago")):
        room_name += ".archipelago"
    shutil.copyfile(room_file, os.path.join(staging, room_name))
    if player_yaml:
        shutil.copyfile(player_yaml, os.path.join(staging, "player.yaml"))
    if spoiler:
        shutil.copyfile(spoiler, os.path.join(staging, "spoiler.txt"))
    meta = {"protocol": PROTOCOL, "room_id": room_id, "room_file": room_name, "room_sha256": digest,
            "apworld_sha256": apworld_sha, "ap_core_version": ap_version(),
            "world_version": world_version(), "origin": origin, "preset": preset,
            "custom_tracks": _custom_tracks(doc), "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **facts}
    write_json_atomic(os.path.join(staging, "room.json"), meta)
    os.replace(staging, target)
    return meta


def generate(paths: Paths, source: str, name: str | None, settings: list[str], stamp: bool,
             seed: int | None, preset: str | None, apworld_sha: str, tracks: dict | None = None) -> dict:
    doc, tmp = prepare_yaml(paths, source, name, settings, stamp, tracks)
    work = tempfile.mkdtemp(prefix="generate-", dir=paths.tmp)
    try:
        room = _run_generation(tmp, work, seed, stop_after_options=False, spoiler=2)
        spoilers = [os.path.join(work, n) for n in os.listdir(work) if n.endswith("_Spoiler.txt")]
        if not spoilers:
            with zipfile.ZipFile(room) as archive:
                inner = [n for n in archive.namelist() if n.endswith("_Spoiler.txt")]
                if inner:
                    path = os.path.join(work, "spoiler.txt")
                    with open(path, "wb") as handle:
                        handle.write(archive.read(inner[0]))
                    spoilers = [path]
        return install_room(paths, room, "generated", apworld_sha, tmp, doc, preset,
                            spoilers[0] if spoilers else None)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if os.path.exists(tmp):
            os.remove(tmp)


def import_room(paths: Paths, source: str, apworld_sha: str) -> dict:
    if not os.path.isfile(source):
        raise SoloError("room", f"No such file: {source}")
    return install_room(paths, source, "imported", apworld_sha, None, None, None, None)


def import_yaml(paths: Paths, source: str) -> dict:
    doc = read_player_yaml(source)
    validate(paths, source, None, [], stamp=False)
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", os.path.splitext(os.path.basename(source))[0]).strip() or "player"
    target = os.path.join(paths.yamls, base + ".yaml")
    index = 2
    while os.path.exists(target):
        if sha256_file(target) == sha256_file(source):
            return {"file": os.path.basename(target), "name": doc.get("name"), "duplicate": True}
        target = os.path.join(paths.yamls, f"{base}-{index}.yaml")
        index += 1
    shutil.copyfile(source, target + ".tmp")
    os.replace(target + ".tmp", target)
    return {"file": os.path.basename(target), "name": doc.get("name"), "duplicate": False}


# ---------------------------------------------------------------------------
# list (no world import: fast)


def list_presets(paths: Paths) -> list:
    result = []
    if not os.path.isdir(paths.presets):
        return result
    order = []
    index = os.path.join(paths.presets, "presets.json")
    if os.path.isfile(index):
        order = read_json(index).get("presets", [])
    for entry in order:
        file = os.path.join(paths.presets, entry["file"])
        if os.path.isfile(file):
            result.append({**entry, "path": file})
    return result


def _yaml_entries(folder: str, source: str) -> list:
    result = []
    if not os.path.isdir(folder):
        return result
    for name in sorted(os.listdir(folder), key=str.lower):
        if not name.lower().endswith((".yaml", ".yml")):
            continue
        path = os.path.join(folder, name)
        entry = {"file": name, "path": path, "source": source}
        try:
            doc = read_player_yaml(path)
            entry["name"] = str(doc.get("name"))
        except SoloError as error:
            entry["error"] = error.message
        result.append(entry)
    return result


def checks_done(room: str, meta: dict) -> int | None:
    name = meta.get("room_file", "")
    if not isinstance(name, str) or os.path.basename(name) != name:
        return None
    save = os.path.join(room, os.path.splitext(name)[0] + ".apsave")
    if not os.path.isfile(save):
        return 0
    try:
        import zlib
        from Utils import restricted_loads
        with open(save, "rb") as handle:
            data = restricted_loads(zlib.decompress(handle.read()))
        checks = data.get("location_checks", {})
        return len(checks.get((0, meta.get("slot_id", 1)), ()))
    except Exception:
        return None


def list_all(paths: Paths) -> dict:
    rooms = []
    for room_id in sorted(os.listdir(paths.rooms)) if os.path.isdir(paths.rooms) else []:
        folder = os.path.join(paths.rooms, room_id)
        meta_path = os.path.join(folder, "room.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError):
            continue
        meta["checks_done"] = checks_done(folder, meta)
        meta["running"] = room_running(folder)
        rooms.append(meta)
    rooms.sort(key=lambda m: m.get("created", ""), reverse=True)
    return {"rooms": rooms, "yamls": _yaml_entries(paths.yamls, "saved"),
            "inbox": _yaml_entries(paths.inbox, "inbox"), "presets": list_presets(paths),
            "inbox_path": paths.inbox}


# ---------------------------------------------------------------------------
# custom tracks (decision 32): installed tracks a preset can include

#: Descriptor files: solo/tracks/<content_id>__<revision>.json. The client
#: writes one for every content-plan package it has verified on disk; a player
#: may drop one in too (for example a descriptor exported from AP-Pie).
DESCRIPTOR_MAX_BYTES = 64 * 1024
TRACK_FILE_SUFFIX = {"lev": ".lev", "vrm": ".vrm"}


def _world_module(name: str):
    """A module of the loaded CTR world (worlds.ctr.<name>)."""
    import importlib
    module = sys.modules[world_class().__module__]
    return importlib.import_module(f"{module.__package__ or module.__name__}.{name}")


def _descriptor_sources(paths: Paths) -> list:
    """(descriptor, source) pairs, unchecked: the world's own packages, the
    descriptor files in solo/tracks, and the tracks of the solo rooms."""
    found = [(d, "built-in") for d in _world_module("content_plan").PACKAGES]
    if os.path.isdir(paths.tracks):
        for name in sorted(os.listdir(paths.tracks)):
            full = os.path.join(paths.tracks, name)
            if not name.lower().endswith(".json") or not os.path.isfile(full) or os.path.islink(full):
                continue
            try:
                if os.path.getsize(full) > DESCRIPTOR_MAX_BYTES:
                    continue
                found.append((read_json(full), "file"))
            except (OSError, ValueError):
                continue
    if os.path.isdir(paths.rooms):
        for room_id in sorted(os.listdir(paths.rooms)):
            meta_path = os.path.join(paths.rooms, room_id, "room.json")
            try:
                meta = read_json(meta_path) if os.path.isfile(meta_path) else {}
            except (OSError, ValueError):
                continue
            for descriptor in meta.get("custom_tracks") or []:
                found.append((descriptor, "room"))
    return found


def _pinned_file(folders: list, pin: dict) -> str | None:
    """A file in one of the folders with the pin's suffix, size and SHA-256,
    whatever its name (the client's own rule, LocateContentFiles)."""
    suffix = TRACK_FILE_SUFFIX[pin["role"]]
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            full = os.path.join(folder, name)
            if (name.lower().endswith(suffix) and os.path.isfile(full)
                    and os.path.getsize(full) == pin["bytes"] and sha256_file(full) == pin["sha256"]):
                return full
    return None


def installed_tracks(paths: Paths, assets: str) -> list:
    """Admitted descriptors whose LEV and VRM are in assets/tracks/<track key>/original
    (or the folder the client keeps a built-in package in), one per package id."""
    admit = _world_module("custom_packages").admit
    supported = _world_module("content_plan").supported_modes
    tracks_root = os.path.join(assets, "tracks")
    seen, result = set(), []
    for raw, source in _descriptor_sources(paths):
        try:
            descriptor = admit(json.loads(json.dumps(raw)))
        except Exception:
            continue
        if descriptor["id"] in seen:
            continue
        key, revision = descriptor["content_id"], descriptor["revision"]
        folders = [os.path.join(tracks_root, key, "original"),
                   os.path.join(tracks_root, f"{key}-{revision}", "original")]
        if not all(_pinned_file(folders, pin) for pin in descriptor["files"]):
            continue
        seen.add(descriptor["id"])
        result.append({"id": descriptor["id"], "track_id": f"custom/{key}/{revision}", "content_id": key,
                       "revision": revision, "display_name": descriptor["display_name"],
                       "author": descriptor["author"], "laps": descriptor["laps"],
                       "modes": supported("custom", descriptor), "source": source, "descriptor": descriptor})
    result.sort(key=lambda t: (t["display_name"].lower(), t["revision"]))
    return result


def list_tracks(paths: Paths, assets: str) -> dict:
    tracks = installed_tracks(paths, assets)
    return {"tracks": [{k: v for k, v in t.items() if k != "descriptor"} for t in tracks],
            "tracks_path": paths.tracks}


def _merge_missing(target: dict, defaults: dict) -> None:
    for key, value in defaults.items():
        if key not in target:
            target[key] = json.loads(json.dumps(value))
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _merge_missing(target[key], value)


def apply_tracks(paths: Paths, doc: dict, assets: str, picked: list[str], guaranteed: list[str]) -> dict:
    """Put the picked installed tracks into content_pool.tracks.custom and the
    guaranteed ones into content_pool.required_entries. A YAML without a
    content plan gets the overlay's content profile where it sets nothing."""
    if not picked and not guaranteed:
        return doc
    if set(guaranteed) - set(picked):
        raise SoloError("track", "A guaranteed track must also be picked.")
    by_id = {t["id"]: t for t in installed_tracks(paths, assets)}
    missing = [p for p in picked if p not in by_id]
    if missing:
        raise SoloError("track", f"This track is no longer installed: {missing[0]}", track=missing[0])
    keys = [by_id[p]["content_id"] for p in picked]
    twice = next((p for p in picked if keys.count(by_id[p]["content_id"]) > 1), None)
    if twice:
        raise SoloError("track", f"Pick one version of {by_id[twice]['display_name']}.", track=twice)
    doc = json.loads(json.dumps(doc))
    section = doc.setdefault(GAME, {})
    for legacy in ("custom_tracks", "cortex_vortex_track"):
        if section.get(legacy):
            raise SoloError("option", f"This YAML uses {legacy}, which cannot be mixed with picked tracks.",
                            option=legacy)
    if not section.get("content_pool"):
        profile = load_overlay(paths).get("custom_tracks", {}).get("profile")
        if not isinstance(profile, dict) or not isinstance(profile.get("content_pool"), dict):
            raise SoloError("runtime", "The options overlay has no custom-track profile.")
        section["content_pool"] = {}
        _merge_missing(section, profile)
    pool = section["content_pool"]
    pool.setdefault("tracks", {})
    custom = pool["tracks"].setdefault("custom", [])
    have = {d.get("id") for d in custom if isinstance(d, dict)}
    for track_id in picked:
        if track_id not in have:
            custom.append(by_id[track_id]["descriptor"])
    required = pool.setdefault("required_entries", [])
    for track_id in guaranteed:
        entry = by_id[track_id]["track_id"]
        if entry not in required:
            required.append(entry)
    return doc


# ---------------------------------------------------------------------------
# serve


def pid_alive(pid: int) -> bool:
    """False only when the process is known to be gone. A process we may not
    query (access denied) counts as alive."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: exists, not ours to query
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class RoomLock:
    """One server per room: an OS file lock on rooms/<id>/serve.lock, held for
    the whole session and released by the OS when the process ends, so a
    crashed server never leaves a stale lock. session.lock beside it only
    tells the client which port the live server uses."""

    def __init__(self, room: str):
        self.path = os.path.join(room, "serve.lock")
        self.handle = None

    def try_acquire(self) -> bool:
        handle = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None


def room_running(room: str) -> bool:
    """True while a server holds the room lock (probe and let go at once)."""
    if not os.path.isfile(os.path.join(room, "serve.lock")):
        return False
    probe = RoomLock(room)
    if probe.try_acquire():
        probe.release()
        return False
    return True


def live_lock(room: str) -> dict | None:
    """The running server's session facts, or None when no server runs."""
    if not room_running(room):
        return None
    try:
        return read_json(os.path.join(room, "session.lock"))
    except (OSError, ValueError):
        return {"pid": None, "port": None}  # starting: not written yet


def _listen_socket(port: int):
    """The server's own listening socket. Windows: exclusive use, so no other
    program can bind the port while we hold it. POSIX: SO_REUSEADDR, so a
    port in TIME_WAIT from our last session is usable (a port with a live
    listener never is)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
        sock.listen(16)
        sock.setblocking(False)
        return sock
    except OSError:
        sock.close()
        return None


def port_answers(port: int) -> bool:
    """Something already answering on the port is never ours to reuse."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        return probe.connect_ex((HOST, port)) == 0
    finally:
        probe.close()


_SAVE_LOCK = threading.Lock()


def _atomic_save(ctx) -> bool:
    """Write the save to a unique temp file, fsync, then replace. Serialized:
    the saver thread and the check handler both call it. A failed save
    leaves the save dirty, so the saver thread retries until one succeeds;
    the client's check journal also resends checks on the next connect."""
    import pickle
    import zlib
    with _SAVE_LOCK:
        tmp = None
        try:
            encoded = zlib.compress(pickle.dumps(ctx.get_save()))
            folder = os.path.dirname(os.path.abspath(ctx.save_filename))
            fd, tmp = tempfile.mkstemp(prefix=".apsave-", suffix=".tmp", dir=folder)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, ctx.save_filename)
            tmp = None
        except Exception as error:
            ctx.logger.exception(error)
            ctx.save_dirty = True
            return False
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        ctx.save_dirty = False
        return True


SAVE_RETRY_SECONDS = 2.0


def _start_saver(ctx) -> None:
    """Replaces MultiServer's saver thread, which clears save_dirty even
    after a failed save. This one clears it only on success (_atomic_save)."""
    def loop():
        while not ctx.exit_event.is_set():
            time.sleep(SAVE_RETRY_SECONDS)
            if ctx.save_dirty:
                _atomic_save(ctx)
    threading.Thread(target=loop, daemon=True).start()


def _read_save(path: str):
    import zlib
    from Utils import restricted_loads
    with open(path, "rb") as handle:
        return restricted_loads(zlib.decompress(handle.read()))


def _save_matches_room(path: str, ctx) -> bool:
    """The save loads and passes the checks MultiServer's set_save makes
    (same players, not newer than the server), with the keys it reads."""
    try:
        data = _read_save(path)
    except Exception:
        return False
    needed = ("version", "connect_names", "received_items", "location_checks", "hints_used", "hints",
              "name_aliases", "client_game_state", "client_connection_timers", "client_activity_timers",
              "random_state")
    option_keys = ("hint_cost", "location_check_points", "server_password", "password", "release_mode",
                   "remaining_mode", "collect_mode", "item_cheat", "compatibility")
    if not (isinstance(data, dict) and all(key in data for key in needed)):
        return False
    options = data.get("game_options")
    if options is not None and not (isinstance(options, dict) and all(k in options for k in option_keys)):
        return False
    return data["connect_names"] == ctx.connect_names and data["version"] <= ctx.save_version


def prepare_save(save_file: str, ctx) -> str:
    """Before a start: keep a good save as .bak; restore a good .bak over a
    damaged or foreign save; refuse when there is no good one."""
    bak = save_file + ".bak"
    if not os.path.isfile(save_file):
        if os.path.isfile(bak) and _save_matches_room(bak, ctx):
            shutil.copyfile(bak, save_file)
            return "restored"
        return "new"
    if _save_matches_room(save_file, ctx):
        return "ok"  # .bak is refreshed once the save has been applied (load_save)
    damaged = save_file + ".damaged-" + time.strftime("%Y%m%d%H%M%S")
    os.replace(save_file, damaged)
    if os.path.isfile(bak) and _save_matches_room(bak, ctx):
        shutil.copyfile(bak, save_file)
        return "restored"
    raise SoloError("save", "The save of this solo seed is damaged and has no good backup.",
                    damaged=os.path.basename(damaged))


def load_save(ctx, save_file: str) -> None:
    """MultiServer's init_save logs a save it cannot apply and starts a new
    game, which the next check would then write over. Here a save that
    cannot be applied stops the start instead, and only a save that applied
    becomes the new .bak."""
    ctx.save_filename = save_file
    ctx.saving = True
    if os.path.isfile(save_file):
        try:
            ctx.set_save(_read_save(save_file))
        except Exception as error:
            raise SoloError("save", f"The save of this solo seed could not be loaded: {error}")
        bak = save_file + ".bak"
        shutil.copyfile(save_file, bak + ".tmp")
        os.replace(bak + ".tmp", bak)
    _start_saver(ctx)


def room_file_path(room: str, meta: dict) -> str:
    """room.json names the room file. It must be a plain file in the room
    folder with the recorded SHA-256, so an edited room.json cannot point the
    server (and its save) somewhere else."""
    name = meta.get("room_file")
    if not isinstance(name, str) or not name or os.path.basename(name) != name or name in (".", ".."):
        raise SoloError("room", "room.json does not name a room file in its folder.")
    path = os.path.join(room, name)
    if os.path.islink(path) or not os.path.isfile(path):
        raise SoloError("room", "The room file is missing.")
    if meta.get("room_sha256") and sha256_file(path) != meta["room_sha256"]:
        raise SoloError("room", "The room file does not match room.json.")
    return path


def check_ports(ports: tuple[int, int]) -> tuple[int, int]:
    """The solo range is 38301 to 38320. Tests may pick another range with
    CTR_SOLO_TEST_PORTS=1 (parallel test runs); the client never sets it."""
    first, last = ports
    if (first, last) != (PORT_FIRST, PORT_LAST) and os.environ.get("CTR_SOLO_TEST_PORTS") != "1":
        raise SoloError("ports", f"The solo port range is {PORT_FIRST} to {PORT_LAST}.")
    if not (1024 <= first <= last <= 65535):
        raise SoloError("ports", "Invalid port range.")
    return first, last


def serve(paths: Paths, room_id: str, game_pid: int | None, ports: tuple[int, int],
          password: str | None) -> int:
    ports = check_ports(ports)
    room = paths.room_dir(room_id)
    meta_path = os.path.join(room, "room.json")
    if not os.path.isfile(meta_path):
        raise SoloError("bad_room", "That solo room does not exist.", room_id=room_id)
    meta = read_json(meta_path)
    lock = RoomLock(room)
    if not lock.try_acquire():
        info = live_lock(room) or {}
        raise SoloError("running", "This room already has a running server.",
                        port=info.get("port"), pid=info.get("pid"))
    try:
        return _serve_locked(paths, room, room_id, meta, game_pid, ports, password)
    finally:
        try:
            os.remove(os.path.join(room, "session.lock"))
        except OSError:
            pass
        lock.release()


def _serve_locked(paths: Paths, room: str, room_id: str, meta: dict, game_pid: int | None,
                  ports: tuple[int, int], password: str | None) -> int:
    import asyncio
    import functools
    import logging
    import MultiServer
    import websockets

    room_file = room_file_path(room, meta)
    save_file = os.path.splitext(room_file)[0] + ".apsave"
    password = password or secrets.token_hex(12)

    log = logging.getLogger()
    log.setLevel(logging.INFO)
    handler = logging.FileHandler(os.path.join(room, "server.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)

    ctx = MultiServer.Context(HOST, 0, None, password, location_check_points=1, hint_cost=10,
                              item_cheat=False, release_mode="auto", collect_mode="auto",
                              countdown_mode="auto", remaining_mode="goal", auto_shutdown=0,
                              compatibility=2, log_network=False)
    ctx.load(room_file, True)
    ctx._save = lambda exit_save=False: _atomic_save(ctx)  # noqa: E731
    save_state = prepare_save(save_file, ctx)
    log.info("solo serve: room %s, save %s", room_id, save_state)
    load_save(ctx, save_file)
    # The room's embedded server options and a loaded save both set the
    # passwords. A solo server always uses this session's password and has
    # no admin password.
    ctx.password = password
    ctx.server_password = None
    # Save on every check batch, so a crash cannot lose a check.
    original_checks = MultiServer.register_location_checks

    def register_location_checks(c, team, slot, locations, *args, **kwargs):
        result = original_checks(c, team, slot, locations, *args, **kwargs)
        _atomic_save(c)
        return result

    MultiServer.register_location_checks = register_location_checks
    if ctx.seed_name != meta.get("seed_name"):
        raise SoloError("room", "The room file does not match room.json.")

    async def run() -> int:
        server = None
        port = None
        for candidate in range(ports[0], ports[1] + 1):
            if port_answers(candidate):
                continue
            sock = _listen_socket(candidate)
            if sock is None:
                continue
            try:
                server = await websockets.serve(functools.partial(MultiServer.server, ctx=ctx), sock=sock,
                                                extensions=[MultiServer.server_per_message_deflate_factory])
            except OSError:
                sock.close()
                continue
            port = candidate
            break
        if server is None:
            raise SoloError("ports", f"No free port between {ports[0]} and {ports[1]}.")
        ctx.port = port
        ctx.server = server
        write_json_atomic(os.path.join(room, "session.lock"),
                          {"pid": os.getpid(), "port": port, "seed_name": ctx.seed_name,
                           "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        emit("ready", port=port, password=password, seed_name=ctx.seed_name, slot=meta.get("slot"),
             room_id=room_id)
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue = asyncio.Queue()

        def read_stdin():
            for line in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, line.rstrip("\r\n"))
            loop.call_soon_threadsafe(lines.put_nowait, None)  # EOF: the client is gone

        threading.Thread(target=read_stdin, daemon=True).start()

        async def watchdog():
            while game_pid:
                await asyncio.sleep(1.0)
                if not pid_alive(game_pid):
                    lines.put_nowait(None)
                    return

        watch = asyncio.create_task(watchdog())
        reason = "exit"
        while not ctx.exit_event.is_set():
            try:
                line = await asyncio.wait_for(lines.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            if line is None:
                reason = "client_gone"
                break
            if line.strip() == "/save":
                emit("saved", ok=_atomic_save(ctx))
                continue
            if line.strip() == "/exit":
                break
            if line.strip():
                ctx.commandprocessor(line)
        watch.cancel()
        _atomic_save(ctx)
        ctx.exit_event.set()
        server.close()
        await server.wait_closed()
        emit("stopped", reason=reason)
        return 0

    return asyncio.run(run())


# ---------------------------------------------------------------------------
# Entry point


def build_parser() -> argparse.ArgumentParser:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="CTR solo runtime wrapper")
    parser.add_argument("--runtime", default=here, help="solo-runtime folder")
    parser.add_argument("--solo", default=None, help="writable solo folder (default <client>/solo)")
    parser.add_argument("--apworld", default=None, help="ctr.apworld (default <client>/ctr.apworld)")
    parser.add_argument("--core", default=None, help="Archipelago core (default <runtime>/archipelago)")
    parser.add_argument("--apworld-sha256", default=None, help="expected ctr.apworld SHA-256")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    cmd = sub.add_parser("tracks")
    cmd.add_argument("--assets", default=None, help="the client's assets folder (default <client>/assets)")
    cmd = sub.add_parser("describe")
    cmd.add_argument("--yaml", default=None, help="report the overlay options' values in this YAML")
    for name in ("validate", "generate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--yaml", required=True)
        cmd.add_argument("--name", default=None)
        cmd.add_argument("--set", action="append", default=[], metavar="OPTION=VALUE")
        cmd.add_argument("--stamp-requires", action="store_true",
                         help="add requires: for a YAML this client wrote (presets, options screen)")
        cmd.add_argument("--assets", default=None, help="the client's assets folder (default <client>/assets)")
        cmd.add_argument("--track", action="append", default=[], metavar="PACKAGE_ID",
                         help="include this installed custom track (repeatable)")
        cmd.add_argument("--guarantee", action="append", default=[], metavar="PACKAGE_ID",
                         help="give this picked track an Adventure pad (repeatable)")
        if name == "generate":
            cmd.add_argument("--seed", type=int, default=None)
            cmd.add_argument("--preset", default=None)
    cmd = sub.add_parser("import-yaml")
    cmd.add_argument("file")
    cmd = sub.add_parser("import-room")
    cmd.add_argument("file")
    cmd = sub.add_parser("serve")
    cmd.add_argument("--room", required=True)
    cmd.add_argument("--game-pid", type=int, default=None)
    cmd.add_argument("--port-first", type=int, default=PORT_FIRST)
    cmd.add_argument("--port-last", type=int, default=PORT_LAST)
    cmd.add_argument("--password", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = os.path.abspath(args.runtime)
    client = os.path.dirname(runtime)
    paths = Paths(runtime, args.solo or os.path.join(client, "solo"),
                  args.apworld or os.path.join(client, "ctr.apworld"),
                  args.core or os.path.join(runtime, "archipelago"))
    try:
        paths.ensure()
        if args.command == "list":
            bootstrap_core(paths, load_worlds=False)
            emit("result", **list_all(paths))
            return 0
        apworld_sha = check_apworld(paths, args.apworld_sha256)
        if args.command == "serve":
            bootstrap_core(paths, load_worlds=True)
            return serve(paths, args.room, args.game_pid, (args.port_first, args.port_last), args.password)
        emit("progress", phase="Starting runtime")
        if args.command in ("validate", "generate", "import-yaml", "import-room"):
            clear_tmp(paths)
        bootstrap_core(paths, load_worlds=True)
        assets = os.path.abspath(getattr(args, "assets", None) or os.path.join(client, "assets"))
        tracks = ({"assets": assets, "picked": args.track, "guaranteed": args.guarantee}
                  if args.command in ("validate", "generate") else None)
        if args.command == "describe":
            emit("result", **describe(paths, args.yaml))
        elif args.command == "tracks":
            emit("result", **list_tracks(paths, assets))
        elif args.command == "validate":
            emit("result", **validate(paths, args.yaml, args.name, args.set, args.stamp_requires, tracks))
        elif args.command == "generate":
            emit("result", **generate(paths, args.yaml, args.name, args.set, args.stamp_requires,
                                      args.seed, args.preset, apworld_sha, tracks))
        elif args.command == "import-yaml":
            emit("result", **import_yaml(paths, args.file))
        elif args.command == "import-room":
            emit("result", **import_room(paths, args.file, apworld_sha))
        return 0
    except SoloError as error:
        emit("error", kind=error.kind, message=error.message, **error.detail)
        return 2
    except Exception as error:  # last resort: the client shows "Solo runtime is damaged"
        import traceback
        traceback.print_exc(file=sys.stderr)
        emit("error", kind="internal", message=f"{error.__class__.__name__}: {error}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
