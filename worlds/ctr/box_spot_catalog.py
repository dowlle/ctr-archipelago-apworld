"""Validate the AP spot catalog at pack time and when the world imports it.

The approved evidence snapshot records each source kind, track identity, LEV
pins, original evidence SHA-256, and rows normalized as
[source ordinal, Item Box number, x, y, z, yaw]. Each spot references one row
by [source record, ordinal]. The snapshot must be checked against its original
sources before approving a new digest in this module.
"""
import hashlib
import json
import re

FORMAT = "ctr-ap-box-spots"
VERSION = 1
#: Spot numbers per track (the alpha3 data package, ruled 2026-11-06).
MAX_NUMBER = 50
#: The `needs` field as a Progressive Boost rank (USF is the second upgrade,
#: Blue Fire the optional third). A blue_fire spot exists in a seed only with
#: Progressive Boost and Blue Fire on (box_spots.eligible).
NEEDS = {"none": 0, "boost": 1, "usf": 2, "blue_fire": 3}
DEFAULT_NEEDS = "usf"
#: The `shortcut` field as the Shortcut Knowledge tier that creates the spot.
SHORTCUT = {"none": 0, "medium": 1, "hard": 2}
DOORS = ("tiger_temple",)
SPOT_FIELDS = {"number", "pos", "rot_y", "needs", "shortcut", "door", "no_gate", "source", "credit", "review",
               "note", "source_family", "provenance"}
TEXT_FIELDS = ("source", "credit", "review", "note")
_HEX64 = re.compile(r"[0-9a-f]{64}")

INDEX_PATH = "data/box_spots/index.json"
PROVENANCE_PATH = "data/box_spots/provenance.json"
SEAT_SPOTS_PATH = "data/box_spots/seat-spots-v2.json"
# Digest of the reviewed, canonical JSON evidence. Keep this approval separate
# from the catalog data so editing a source record cannot approve its own kind.
REVIEWED_PROVENANCE_SHA256 = "edbd8a6eb6f2d0de42ebbf3332aa3e5d7b7e1bdf20e660c2122cdf59564002dc"
SOURCE_FAMILIES = frozenset({"ap_box", "weapon_crate", "wumpa_crate", "loose_fruit", "time_crate", "ctr_letter"})
AP_SOURCE_KINDS = frozenset({"box_author_export", "builtin_ap_table", "community_ap_submission",
                             "reviewed_ap_proposal"})
DAY_TRACK = "custom:arabian-heights-day"
DAY_PIN = "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900"
NIGHT_PIN = "8093b663855d3fd0096fd2980a85bc6efe334c0aff250e8a33eea11909e5c21c"
DAY_SOURCE = "a6-16-night-weapon-crates"
DAY_ROWS_SHA256 = "e1870b33d79aa48311c23320f6e7c495a82df014012a30e5dcfa3597516a39ae"


class SpotFileError(ValueError):
    pass


def _fail(path, message):
    raise SpotFileError(f"CTR box spot file {path}: {message}")


def _int16(value):
    return type(value) is int and -32768 <= value <= 32767


def _sha256(value):
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def check_draft_file(doc, path="<file>"):
    """Check a proposal's geometry and fields before its source is reviewed."""
    if not isinstance(doc, dict) or set(doc) != {"format", "version", "track", "spots", "retired"}:
        _fail(path, "must hold exactly format, version, track, spots and retired")
    if doc["format"] != FORMAT or doc["version"] != VERSION:
        _fail(path, f"format must be {FORMAT} version {VERSION}")
    track = doc["track"]
    if not isinstance(track, dict) or track.get("kind") not in ("retail", "custom"):
        _fail(path, "track.kind must be retail or custom")
    if track["kind"] == "retail":
        if set(track) != {"kind", "level_id", "name"} or type(track["level_id"]) is not int:
            _fail(path, "a retail track names exactly kind, level_id and name")
    else:
        if set(track) != {"kind", "track_key", "name", "lev_sha256"}:
            _fail(path, "a custom track names exactly kind, track_key, name and lev_sha256")
        pins = track["lev_sha256"]
        if not isinstance(pins, list) or not pins or not all(_sha256(p) for p in pins):
            _fail(path, "lev_sha256 must be a nonempty list of lowercase SHA-256 digests")
    retired = doc["retired"]
    if not isinstance(retired, list) or any(type(n) is not int or not 1 <= n <= MAX_NUMBER for n in retired) \
            or len(set(retired)) != len(retired):
        _fail(path, f"retired must be distinct numbers 1 to {MAX_NUMBER}")
    spots = doc["spots"]
    if not isinstance(spots, list):
        _fail(path, "spots must be a list")
    seen = set()
    for spot in spots:
        if not isinstance(spot, dict) or not {"number", "pos", "rot_y"} <= set(spot) or set(spot) - SPOT_FIELDS:
            _fail(path, "a spot holds number, pos and rot_y, and only known fields")
        n = spot["number"]
        if type(n) is not int or not 1 <= n <= MAX_NUMBER or n in seen:
            _fail(path, f"spot numbers must be distinct, 1 to {MAX_NUMBER}")
        if n in retired:
            _fail(path, f"spot {n} is retired")
        seen.add(n)
        pos = spot["pos"]
        if not isinstance(pos, list) or len(pos) != 3 or not all(_int16(v) for v in pos):
            _fail(path, f"spot {n}: pos must be three signed 16-bit LEV units")
        # An engine angle, 0x1000 a full turn; kept as authored (the built-in
        # rows hold values outside 0 to 4095), so only the LEV width is checked.
        if not _int16(spot["rot_y"]):
            _fail(path, f"spot {n}: rot_y must be a signed 16-bit engine angle")
        if spot.get("needs", DEFAULT_NEEDS) not in NEEDS:
            _fail(path, f"spot {n}: needs must be none, boost, usf or blue_fire")
        if spot.get("needs") == "blue_fire" and track["kind"] != "custom":
            # The retail fallback tables (box_spots._retail_tables) have no
            # Blue Fire filter, so rank 3 stays on custom files.
            _fail(path, f"spot {n}: needs blue_fire is only for custom tracks")
        if spot.get("shortcut", "none") not in SHORTCUT:
            _fail(path, f"spot {n}: shortcut must be none, medium or hard")
        if "door" in spot and (spot["door"] not in DOORS or track.get("level_id") != 4 or track["kind"] != "retail"):
            _fail(path, f"spot {n}: door is only tiger_temple, on retail Tiger Temple")
        if "no_gate" in spot and (spot["no_gate"] is not True or spot.get("needs") != "none"):
            _fail(path, f"spot {n}: no_gate is true only, on a spot that needs none")
        if any(not isinstance(spot.get(k, ""), str) for k in TEXT_FIELDS):
            _fail(path, f"spot {n}: source, credit, review and note are text")
    return doc


def _check_source(spot, track_id, pins, source_records, path):
    n = spot["number"]
    family = spot.get("source_family")
    if not isinstance(family, str) or family not in SOURCE_FAMILIES:
        _fail(path, f"spot {n}: missing or unknown source_family")
    ref = spot.get("provenance")
    if (not isinstance(ref, list) or len(ref) != 2
            or not isinstance(ref[0], str) or type(ref[1]) is not int or ref[1] < 1):
        _fail(path, f"spot {n}: provenance must name a source record and positive row ordinal")
    source_id, ordinal = ref
    source = source_records.get(source_id)
    if source is None or source["track"] != track_id or source["pins"] != pins:
        _fail(path, f"spot {n}: provenance must match a reviewed source for this track and its LEV pins")
    expected = [n, *spot["pos"], spot["rot_y"]]
    if source["rows"].get(ordinal) != expected:
        _fail(path, f"spot {n}: number, position or rotation differs from provenance")

    if source["kind"] == "lev_model_extract":
        # A6-16 extracted the pointed-to weapon model (8) from Night 1.1.0.
        # TY1, "Check to prevent another crossover", records why alpha6/7's
        # 27 Day rows are retained until the weapon-fill conversion.
        if (family == "weapon_crate" and source_id == DAY_SOURCE and track_id == DAY_TRACK
                and pins == [DAY_PIN] and source["donor_lev_sha256"] == NIGHT_PIN
                and source["model_id"] == 8 and n == ordinal and 1 <= n <= 27):
            return
        _fail(path, f"spot {n}: LEV donor models cannot supply authored AP spots")
    if family != "ap_box" or source["kind"] not in AP_SOURCE_KINDS:
        _fail(path, f"spot {n}: only authored ap_box sources may supply AP spots")


def check_file(doc, source_records, path="<file>"):
    """Validate a catalog file against its reviewed sources before generation."""
    check_draft_file(doc, path)
    track = doc["track"]
    track_id = (f"retail:{track['level_id']}" if track["kind"] == "retail"
                else f"custom:{track['track_key']}")
    for spot in doc["spots"]:
        _check_source(spot, track_id, track.get("lev_sha256", []), source_records, path)
    return doc


def load_sources(read):
    records = json.loads(read(PROVENANCE_PATH).decode("utf-8"))
    if not isinstance(records, dict):
        _fail(PROVENANCE_PATH, "expected an object keyed by source record ID")
    evidence = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(evidence).hexdigest() != REVIEWED_PROVENANCE_SHA256:
        _fail(PROVENANCE_PATH, "source evidence does not match the reviewed SHA-256")
    for source_id, source in records.items():
        if not isinstance(source, dict):
            _fail(PROVENANCE_PATH, f"{source_id}: expected a source record object")
        kind = source.get("kind")
        fields = {"kind", "track", "pins", "record", "sha256", "rows"}
        if kind == "lev_model_extract":
            fields |= {"donor_lev_sha256", "model_id"}
        if (set(source) != fields or not isinstance(kind, str)
                or kind not in AP_SOURCE_KINDS | {"lev_model_extract"}
                or not isinstance(source["record"], str) or not source["record"].strip()
                or not _sha256(source["sha256"])
                or not isinstance(source["track"], str) or not isinstance(source["pins"], list)
                or not all(_sha256(pin) for pin in source["pins"])):
            _fail(PROVENANCE_PATH, f"{source_id}: invalid source record")
        rows = source["rows"]
        if (not isinstance(rows, list) or not rows
                or any(not isinstance(row, list) or len(row) != 6
                       or type(row[0]) is not int or row[0] < 1
                       or type(row[1]) is not int or not 1 <= row[1] <= MAX_NUMBER
                       or not all(_int16(v) for v in row[2:]) for row in rows)
                or len({row[0] for row in rows}) != len(rows)):
            _fail(PROVENANCE_PATH, f"{source_id}: expected distinct positive ordinals and number/XYZ/yaw rows")
        if source_id == DAY_SOURCE:
            frozen = json.dumps(rows, separators=(",", ":")).encode()
            if kind != "lev_model_extract" or hashlib.sha256(frozen).hexdigest() != DAY_ROWS_SHA256:
                _fail(PROVENANCE_PATH, "the Arabian Heights Day exception must match its published geometry")
        source["rows"] = {row[0]: row[1:] for row in rows}
    return records


def load_index(read):
    return json.loads(read(INDEX_PATH).decode("utf-8"))


def load_seat_spots(read):
    """Read the frozen v2 replacements for individual fallback crate ordinals."""
    path = SEAT_SPOTS_PATH
    catalog = json.loads(read(path))
    if not isinstance(catalog, dict) or not catalog:
        _fail(path, "expected reviewed seats keyed by LEV SHA-256")
    for pin, seats in catalog.items():
        if not _sha256(pin) or not isinstance(seats, dict) or not seats:
            _fail(path, "a pin needs a nonempty set of replacements")
        for ordinal, spot in seats.items():
            if (not re.fullmatch(r"[1-9][0-9]{0,4}", ordinal) or int(ordinal) > 65536
                    or not isinstance(spot, dict) or set(spot) != {"pos", "rot_y"}
                    or not isinstance(spot["pos"], list) or len(spot["pos"]) != 3
                    or not all(_int16(v) for v in (*spot["pos"], spot["rot_y"]))):
                _fail(path, f"invalid seat replacement {pin}/{ordinal}")
    return catalog


def load_catalog(read, *, paths=None):
    source_records = load_sources(read)
    index = load_index(read)
    if (not isinstance(index, dict) or set(index) != {"retail", "custom"}
            or any(not isinstance(names, list)
                   or any(not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", name) for name in names)
                   for names in index.values())):
        raise SpotFileError(f"CTR box spot index {INDEX_PATH} must list retail and custom")
    indexed = {f"data/box_spots/{kind}/{name}.json" for kind in index for name in index[kind]}
    if paths is not None and indexed != paths:
        _fail(INDEX_PATH, f"files and index differ: {sorted(indexed ^ paths)}")
    retail, custom = {}, {}
    for kind, out, key in (("retail", retail, "level_id"), ("custom", custom, "track_key")):
        for name in index[kind]:
            path = f"data/box_spots/{kind}/{name}.json"
            raw = read(path)
            doc = check_file(json.loads(raw.decode("utf-8")), source_records, path)
            if doc["track"]["kind"] != kind:
                _fail(path, f"sits under {kind} but describes a {doc['track']['kind']} track")
            if kind == "custom" and doc["track"]["track_key"] != name:
                _fail(path, "file name and track_key differ")
            if doc["track"][key] in out:
                _fail(path, "a second file for the same track")
            out[doc["track"][key]] = dict(doc=doc, path=path, sha256=hashlib.sha256(raw).hexdigest())
    return retail, custom, source_records
