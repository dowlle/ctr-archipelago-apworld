"""Hand-placed AP box spots (alpha3 row A3-14).

WHAT A SPOT FILE IS. One reviewed JSON file per track, shipped inside the
apworld under data/box_spots/ and listed in data/box_spots/index.json (pkgutil
cannot list a directory inside a packed apworld). Only files merged into the
apworld are ever read: there is no player-side override (ruled 2026-11-06).

  * Retail: data/box_spots/retail/<LEVEL>.json, the 18 box tracks, keyed by
    native LevelID. The 241 boxes of the 2026-08-10 placement file were
    converted one to one: spot n is the level's n-th row of native
    ap_placements_data.h, its logic fields come from the tables that used to be
    literals in item_boxes.py (test/fixtures/retail_box_tables.json keeps those
    literals, and the conversion test rebuilds them from the files). dowlle's
    Box Author Mode spots of 2026-11-24 (A7-1) follow from number 16: only
    those the ground map puts on start ground (needs none), plus Papu's
    Pyramid box 50 with spot 10's rule; held spots are not in the files.
  * Custom: data/box_spots/custom/<track_key>.json, only for a track with a
    named block (ruled 2026-11-06: a generic `Custom Track N` keeps crate
    seating), pinned to the LEV digests it was measured on. A file whose pins
    do not list the seed's LEV is not used, and the track keeps crate seating.

NUMBERS ARE PERMANENT (ruled 2026-11-06). `<Track>: Item Box <n>` is always the
same spot, n 1 to 50. Built-in retail spots keep 1 to 15; a reviewed community
spot on a retail track gets the next free number from 16. On a named custom
track numbers start at 1 (ruled 2026-11-06), so there Item Box 1 to 15 mean
crate seats until the track's file ships and spots after. A removed spot lists
its number under `retired`; a number is never reused
(test/fixtures/box_spot_numbers_lock.json).

LOGIC FIELDS (ruled 2026-11-06). `needs`: none, boost or usf, absent meaning
usf, the careful default. `blue_fire` (rank 3, TT1 2026-11-26) is for a spot
ruled "Boost 3"; it exists in a seed only with Progressive Boost and Blue Fire
on, because without them no kart reaches rank 3 (the TV World crate removal of
A4-52 does the same). Below rank 3 the seed's boost options never change a pool. `shortcut`: none, medium or hard; a spot exists in a
seed only at that Shortcut Knowledge tier or above, and a hard spot also needs
one level of each stat. `door`: Tiger Temple's stone door (Itemsanity weapon
term). `no_gate`: a spot that was ruled to need nothing although it sits past a
jump; carried so nobody gates it later. `lev_sha256` (IM1b, 2026-11-27): the
spot exists only for a package whose LEV is one of these pins, a proper subset
of the file's pins; on the file's other pins it is not in the pool and its
number stays reserved.

THE PICK (ruled 2026-11-06, "all spots equal"). Per track, the eligible spots
(not retired, tier allowed) go into one pool. With 15 or fewer all are used and
no random number is drawn, so a retail seed with only built-in files has the
same boxes as before. With more, 15 are picked by a generator of their own,
seeded from the multiworld seed, the player, "box_spots" and the track id; the
world's random stream is never touched.
"""
import hashlib
import pkgutil
import random

from . import box_spot_catalog, destinations
from .box_spot_catalog import DEFAULT_NEEDS, MAX_NUMBER, NEEDS, SHORTCUT, SpotFileError, _fail

FEATURE = "box_spots_v1"
#: Boxes a track carries in one seed at most.
PICK = 15


def _read(path):
    raw = pkgutil.get_data(__package__, path)
    if raw is None:
        raise SpotFileError(f"CTR box spot file {path}: is missing from this apworld")
    return raw


def load_index():
    return box_spot_catalog.load_index(_read)


def check_file(doc, path="<file>"):
    return box_spot_catalog.check_file(doc, SOURCE_RECORDS, path)


#: {LevelID: {doc, path, sha256}} and {track_key: {...}}, read once at import.
RETAIL_FILES, CUSTOM_FILES, SOURCE_RECORDS = box_spot_catalog.load_catalog(_read)
#: {SHA-256: entry} of replaced files kept for restoring older rooms (IM1).
LEGACY_FILES = box_spot_catalog.load_legacy(_read, SOURCE_RECORDS, CUSTOM_FILES)

# Sparse authored replacements for fallback seats, indexed by the exact LEV
# and original one-based weapon ordinal. These are ground anchors for AP
# boxes. The weapon crates keep their original coordinates and identity.
SEAT_SPOTS = box_spot_catalog.load_seat_spots(_read)


def needs_rank(spot):
    return NEEDS[spot.get("needs", DEFAULT_NEEDS)]


def tier(spot):
    return SHORTCUT[spot.get("shortcut", "none")]


def spots_by_number(entry):
    return {spot["number"]: spot for spot in entry["doc"]["spots"]}


#: The `needs` rank that exists only with Blue Fire on.
BLUE_FIRE_RANK = NEEDS["blue_fire"]


def rule_rank(spot, package, blue_fire, logic_difficulty):
    """A `rule_of` spot's rank: the rank object_rulings gives the crate it
    names, for the package's exact LEV. None means the ruling removes it in
    this seed. Fails closed. The plan's capability record, the only place a
    restored room finds Logic Difficulty, is empty when Progressive Boost and
    Progressive Stats are both off; with no Logic Difficulty the spot is removed
    (a crate keeps its check on hard there, a spot does not). Where no ruling
    covers the package it takes the spot's own `needs` (blue_fire, so only with
    Blue Fire), never a lower rank."""
    if logic_difficulty is None:
        return None
    from . import object_rulings
    kind, ordinal = box_spot_catalog.parse_rule(spot["rule_of"])
    cap = dict(logic_difficulty=logic_difficulty, boost_blue_fire=bool(blue_fire))
    rank = object_rulings.pinned_rank((package or {}).get("content_id"), lev_pin(package), kind, ordinal, cap)
    if rank == 0:
        return needs_rank(spot) if blue_fire else None
    return rank


def check_rules():
    """Every shipped `rule_of` names a ruling row of its file's own LEV pins;
    raises SpotFileError otherwise. Run by the tests and the pack check."""
    from . import object_rulings
    for key, entry in CUSTOM_FILES.items():
        pins = entry["doc"]["track"]["lev_sha256"]
        for spot in entry["doc"]["spots"]:
            if "rule_of" not in spot:
                continue
            kind, ordinal = box_spot_catalog.parse_rule(spot["rule_of"])
            rows = [object_rulings.RULINGS.get((content, kind, ordinal))
                    for content in dict.fromkeys((destinations.canonical_track_key(key), key))]
            if not any(row is not None and row["lev_sha256"] in pins for row in rows):
                _fail(entry["path"], f"spot {spot['number']}: rule_of names no ruling for this file's LEV")


def eligible(entry, knowledge, blue_fire=False, logic_difficulty=None, package=None):
    """Sorted numbers of a file's spots a Shortcut Knowledge tier creates; a
    blue_fire spot only when the seed has Progressive Boost with Blue Fire. A
    `rule_of` spot exists as its crate ruling says (easy/medium need Blue Fire,
    else it is removed and its ID stays registered). A spot limited to some
    of the file's LEV pins exists only for a package on one of them."""
    pin = lev_pin(package)
    return sorted(s["number"] for s in entry["doc"]["spots"]
                  if tier(s) <= knowledge
                  and ("lev_sha256" not in s or pin in s["lev_sha256"])
                  and ((rule_rank(s, package, blue_fire, logic_difficulty) is not None) if "rule_of" in s
                       else (blue_fire or needs_rank(s) < BLUE_FIRE_RANK)))


def spot_rank(spot, package, blue_fire, logic_difficulty):
    """The Progressive Boost rank a spot needs in this seed."""
    if "rule_of" in spot:
        rank = rule_rank(spot, package, blue_fire, logic_difficulty)
        if rank is None:
            raise ValueError("a removed spot has no rank")
        return rank
    return needs_rank(spot)


def pick(numbers, seed, player, track_id, count=PICK):
    """The numbers a seed uses from the eligible `numbers`: all when 15 or
    fewer (no random draw), else 15 drawn by a generator of their own. Sorted."""
    numbers = sorted(numbers)
    if len(numbers) <= count:
        return numbers
    key = f"{seed}:{player}:box_spots:{track_id}".encode("utf-8")
    rng = random.Random(int.from_bytes(hashlib.sha256(key).digest(), "big"))
    return sorted(rng.sample(numbers, count))


def lev_pin(package):
    """The package's LEV SHA-256 file pin, or None."""
    return next((pin.get("sha256") for pin in (package or {}).get("files", ()) if isinstance(pin, dict)
                 and pin.get("role") == "lev"), None)


def file_for(track, package=None, file_sha256=None):
    """The spot file entry a plan track uses, or None. Retail by LevelID; a
    named custom track only when the package's LEV is one of the file's pins
    (a generic `Custom Track N` never uses one, ruled 2026-11-06). With the
    `file_sha256` of a saved spot set that names a restore-only file of the
    same track and pin (LEGACY_FILES), that older file."""
    if track.get("origin") == "retail":
        return RETAIL_FILES.get(track["retail_id"])
    if track.get("origin") == "custom" and "named_block" in track and package:
        entry = CUSTOM_FILES.get(destinations.canonical_track_key(package.get("content_id")))
        if entry and lev_pin(package) in entry["doc"]["track"]["lev_sha256"]:
            legacy = LEGACY_FILES.get(file_sha256) if file_sha256 != entry["sha256"] else None
            if (legacy and legacy["doc"]["track"]["track_key"] == entry["doc"]["track"]["track_key"]
                    and lev_pin(package) in legacy["doc"]["track"]["lev_sha256"]):
                return legacy
            return entry
    return None


def spot_set(track, package, knowledge, seed, player, count=PICK, blue_fire=False, logic_difficulty=None):
    """The plan's `spot_sets` record of one track, or None without a file."""
    entry = file_for(track, package)
    if entry is None:
        return None
    pool = eligible(entry, knowledge, blue_fire, logic_difficulty, package)
    out = dict(file_sha256=entry["sha256"], pool=len(pool), picked=pick(pool, seed, player, track["id"], count))
    if track.get("origin") == "custom":
        out["lev_sha256"] = lev_pin(package)
    return out


def check_spot_set(track, package, knowledge, record, count=PICK, *, compare_digest=True, blue_fire=False,
                   logic_difficulty=None):
    """A plan's spot set against this build's file; returns the file entry.
    When restoring (no digest compare), a set that names a restore-only file
    of the track is checked against that file."""
    saved = record.get("file_sha256") if isinstance(record, dict) and not compare_digest else None
    entry = file_for(track, package, saved)
    if entry is None:
        raise SpotFileError(f"box spots for {track['id']}: this build has no spot file for the track")
    keys = {"file_sha256", "pool", "picked"} | ({"lev_sha256"} if track.get("origin") == "custom" else set())
    if not isinstance(record, dict) or set(record) != keys:
        raise SpotFileError(f"box spots for {track['id']}: the record must hold exactly {sorted(keys)}")
    if compare_digest and record["file_sha256"] != entry["sha256"]:
        raise SpotFileError(f"box spots for {track['id']}: the seed was built with a different spot file")
    if track.get("origin") == "custom" and record["lev_sha256"] != lev_pin(package):
        raise SpotFileError(f"box spots for {track['id']}: the LEV pin differs from the package")
    pool = eligible(entry, knowledge, blue_fire, logic_difficulty, package)
    picked = record["picked"]
    if (record["pool"] != len(pool) or not isinstance(picked, list) or picked != sorted(set(picked))
            or not set(picked) <= set(pool) or len(picked) != min(count, len(pool))):
        raise SpotFileError(f"box spots for {track['id']}: picked spots are not a valid pick from the file")
    return entry


def wire_spot(spot):
    """A box check's `spot` field."""
    return dict(number=spot["number"], pos=list(spot["pos"]), rot_y=spot["rot_y"])


# ── retail tables, derived from the 18 built-in files ───────────────────────

def _retail_tables():
    from . import destinations
    tracks = destinations.tracks_with_suffix(": Sapphire Time Trial")
    level_ids = destinations.level_ids_for(tracks)
    by_level = {lid: name for name, lid in level_ids.items()}
    if set(RETAIL_FILES) != set(by_level):
        raise SpotFileError("the retail spot files must cover exactly the 18 box tracks")
    placed, tiers, rules, no_gate, doors = {}, {}, {}, set(), {}
    for lid, entry in RETAIL_FILES.items():
        name = by_level[lid]
        doc = entry["doc"]
        if doc["track"]["name"] != name:
            _fail(entry["path"], f"names {doc['track']['name']!r}, LevelID {lid} is {name!r}")
        builtin = sorted(s["number"] for s in doc["spots"] if s.get("source") == "builtin")
        if builtin != list(range(1, len(builtin) + 1)) or len(builtin) > PICK:
            _fail(entry["path"], "built-in spots must be numbered 1 to their count, at most 15")
        if any(s["number"] <= PICK and s.get("source") != "builtin" for s in doc["spots"]):
            _fail(entry["path"], "numbers 1 to 15 on a retail track are the built-in range")
        placed[name] = len(builtin)
        for spot in doc["spots"]:
            key = (name, spot["number"])
            if tier(spot):
                tiers[key] = tier(spot)
            if needs_rank(spot) or tier(spot):
                rules[key] = (needs_rank(spot), tier(spot) == SHORTCUT["hard"])
            if spot.get("no_gate"):
                no_gate.add(key)
            if spot.get("door"):
                doors.setdefault(spot["door"], []).append(key)
    return placed, tiers, rules, frozenset(no_gate), doors


#: Built-in boxes per track; {(track, number): tier}; {(track, number):
#: (boost rank, needs stats)}; the no-gate spots; {door: [(track, number)]}.
#: Community spots (16 and up) are in the tier, rule and door tables too.
RETAIL_PLACED, RETAIL_TIERS, RETAIL_RULES, RETAIL_NO_GATE, RETAIL_DOORS = _retail_tables()
