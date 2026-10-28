#!/usr/bin/env python3
"""CTR solo runtime wrapper (#89).

The native client starts this script with the bundled interpreter to generate
solo seeds and to host a private MultiServer for one solo room. It talks JSON
lines on stdout; everything else (Archipelago logging, prints) goes to stderr
or a log file.

Layout inside a client folder (see RUNTIME.txt for the pinned parts):

    <client>/ctr.apworld            the release world, the only one loaded
    <client>/solo-runtime/          this script, presets, overlay, the core
    <client>/solo/                  rooms, YAMLs, inbox and ap-home (writable)

Commands:
    list                      rooms, saved YAMLs, inbox YAMLs and presets
    describe                  options of the loaded world plus the overlay
    validate  --yaml F        roll the settings and run the option checks
    generate  --yaml F        generate a room into solo/rooms/<room id>/
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
        self.presets = os.path.join(self.runtime, "presets")
        self.overlay = os.path.join(self.runtime, "options-overlay.json")

    def ensure(self) -> None:
        for path in (self.solo, self.ap_home, self.rooms, self.yamls, self.inbox, self.tmp):
            os.makedirs(path, exist_ok=True)

    def room_dir(self, room_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{%d}" % ROOM_ID_HEX, room_id or ""):
            raise SoloError("bad_room", f"Not a room id: {room_id!r}")
        return os.path.join(self.rooms, room_id)


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


def describe(paths: Paths) -> dict:
    cls = world_class()
    options = [describe_option(name, option)
               for name, option in cls.options_dataclass.type_hints.items()]
    return {"game": GAME, "world_version": world_version(), "ap_version": ap_version(),
            "options": options, "overlay": load_overlay(paths), "presets": list_presets(paths)}


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
    except UnicodeDecodeError:
        raise SoloError("yaml", "The YAML is not UTF-8 text.", file=os.path.basename(path))
    except OSError as error:
        raise SoloError("yaml", f"Could not read the YAML: {error}", file=os.path.basename(path))
    try:
        docs = [doc for doc in parse_yamls(text) if doc is not None]
    except Exception as error:  # yaml.MarkedYAMLError carries the line number
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        raise SoloError("yaml", f"The YAML could not be read: {error}",
                        file=os.path.basename(path), line=line)
    return docs


def read_player_yaml(path: str) -> dict:
    """One document, one CTR player. Returns the document."""
    docs = _load_yaml_documents(path)
    if not docs:
        raise SoloError("yaml", "The YAML is empty.", file=os.path.basename(path))
    if len(docs) > 1:
        raise SoloError("players", "Solo seeds have one player. This YAML has more than one document.",
                        file=os.path.basename(path), documents=len(docs))
    doc = docs[0]
    if not isinstance(doc, dict):
        raise SoloError("yaml", "The YAML is not a player settings file.", file=os.path.basename(path))
    game = doc.get("game")
    games = [k for k, v in game.items() if v] if isinstance(game, dict) else [game]
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
    named = [name for name, option in hints.items()
             if re.search(r"\b%s\b" % re.escape(name), text)
             or re.search(r"\b%s\b" % re.escape(getattr(option, "display_name", name)), text)]
    fill = error.__class__.__name__ in ("FillError",)
    if fill:
        return SoloError("fill", "This combination could not be generated. Try again or change options.",
                         detail=text)
    if isinstance(error, (Options.OptionError, ValueError, KeyError, TypeError)) or named:
        return SoloError("option", text, option=named[0] if named else None, options=named)
    return SoloError("generate", text, error=error.__class__.__name__)


def _run_generation(player_yaml: str, out_dir: str, seed: int | None, stop_after_options: bool,
                    spoiler: int) -> str | None:
    """Run Generate and Main in process. Returns the room zip path."""
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
    rooms = [name for name in os.listdir(out_dir) if name.startswith("AP_") and name.endswith(".zip")]
    if len(rooms) != 1:
        raise SoloError("generate", "Generation finished without exactly one room file.")
    return os.path.join(out_dir, rooms[0])


def prepare_yaml(paths: Paths, source: str, name: str | None, settings: list[str],
                 stamp: bool) -> tuple[dict, str]:
    """Read and override a YAML, write the exact input to a temp file."""
    doc = read_player_yaml(source)
    doc = apply_overrides(doc, name, settings)
    if stamp:
        doc = stamp_requires(doc)
    fd, tmp = tempfile.mkstemp(prefix="player-", suffix=".yaml", dir=paths.tmp)
    os.close(fd)
    dump_yaml(doc, tmp)
    return doc, tmp


def validate(paths: Paths, source: str, name: str | None, settings: list[str], stamp: bool) -> dict:
    _, tmp = prepare_yaml(paths, source, name, settings, stamp)
    work = tempfile.mkdtemp(prefix="validate-", dir=paths.tmp)
    try:
        _run_generation(tmp, work, None, stop_after_options=True, spoiler=0)
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
             seed: int | None, preset: str | None, apworld_sha: str) -> dict:
    doc, tmp = prepare_yaml(paths, source, name, settings, stamp)
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
    save = os.path.join(room, os.path.splitext(meta.get("room_file", ""))[0] + ".apsave")
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
        meta["running"] = live_lock(folder) is not None
        rooms.append(meta)
    rooms.sort(key=lambda m: m.get("created", ""), reverse=True)
    return {"rooms": rooms, "yamls": _yaml_entries(paths.yamls, "saved"),
            "inbox": _yaml_entries(paths.inbox, "inbox"), "presets": list_presets(paths),
            "inbox_path": paths.inbox}


# ---------------------------------------------------------------------------
# serve


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
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


def live_lock(room: str) -> dict | None:
    path = os.path.join(room, "session.lock")
    try:
        lock = read_json(path)
    except (OSError, ValueError):
        return None
    if pid_alive(int(lock.get("pid", 0))):
        return lock
    return None


def port_free(port: int) -> bool:
    """Something already answering on the port is never ours to reuse."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        if probe.connect_ex((HOST, port)) == 0:
            return False
    finally:
        probe.close()
    test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            test.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        test.bind((HOST, port))
        return True
    except OSError:
        return False
    finally:
        test.close()


def _atomic_save(ctx) -> bool:
    import pickle
    import zlib
    try:
        encoded = zlib.compress(pickle.dumps(ctx.get_save()))
        tmp = ctx.save_filename + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, ctx.save_filename)
    except Exception as error:  # a failed save is logged; the client resends on reconnect
        ctx.logger.exception(error)
        return False
    return True


def serve(paths: Paths, room_id: str, game_pid: int | None, ports: tuple[int, int],
          password: str | None) -> int:
    import asyncio
    import functools
    import logging
    import MultiServer
    import websockets

    room = paths.room_dir(room_id)
    meta_path = os.path.join(room, "room.json")
    if not os.path.isfile(meta_path):
        raise SoloError("bad_room", "That solo room does not exist.", room_id=room_id)
    meta = read_json(meta_path)
    lock = live_lock(room)
    if lock is not None:
        raise SoloError("running", "This room already has a running server.",
                        port=lock.get("port"), pid=lock.get("pid"))
    room_file = os.path.join(room, meta["room_file"])
    save_file = os.path.splitext(room_file)[0] + ".apsave"
    if os.path.isfile(save_file):
        shutil.copyfile(save_file, save_file + ".bak")
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
    ctx.save_filename = save_file
    ctx._save = lambda exit_save=False: _atomic_save(ctx)  # noqa: E731
    ctx.init_save(True)
    # Save on every check batch, so a crash cannot lose a check.
    original_checks = MultiServer.register_location_checks

    def register_location_checks(c, team, slot, locations, *args, **kwargs):
        result = original_checks(c, team, slot, locations, *args, **kwargs)
        c.save_dirty = False
        _atomic_save(c)
        return result

    MultiServer.register_location_checks = register_location_checks
    if ctx.seed_name != meta.get("seed_name"):
        raise SoloError("room", "The room file does not match room.json.")

    async def run() -> int:
        server = None
        port = None
        for candidate in range(ports[0], ports[1] + 1):
            if not port_free(candidate):
                continue
            try:
                server = await websockets.serve(functools.partial(MultiServer.server, ctx=ctx), host=HOST,
                                                port=candidate,
                                                extensions=[MultiServer.server_per_message_deflate_factory])
            except OSError:
                continue
            port = candidate
            break
        if server is None:
            raise SoloError("ports", f"No free port between {ports[0]} and {ports[1]}.")
        ctx.port = port
        ctx.server = server
        write_json_atomic(os.path.join(room, "session.lock"),
                          {"pid": os.getpid(), "port": port, "password": password, "seed_name": ctx.seed_name,
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

    try:
        return asyncio.run(run())
    finally:
        try:
            lock_path = os.path.join(room, "session.lock")
            if os.path.isfile(lock_path) and read_json(lock_path).get("pid") == os.getpid():
                os.remove(lock_path)
        except (OSError, ValueError):
            pass


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
    sub.add_parser("describe")
    for name in ("validate", "generate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--yaml", required=True)
        cmd.add_argument("--name", default=None)
        cmd.add_argument("--set", action="append", default=[], metavar="OPTION=VALUE")
        cmd.add_argument("--stamp-requires", action="store_true",
                         help="add requires: for a YAML this client wrote (presets, options screen)")
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
        bootstrap_core(paths, load_worlds=True)
        if args.command == "describe":
            emit("result", **describe(paths))
        elif args.command == "validate":
            emit("result", **validate(paths, args.yaml, args.name, args.set, args.stamp_requires))
        elif args.command == "generate":
            emit("result", **generate(paths, args.yaml, args.name, args.set, args.stamp_requires,
                                      args.seed, args.preset, apworld_sha))
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
