"""Validation and canonical hashing for experimental track fill files."""

import hashlib
import json
import pkgutil
import re
from functools import lru_cache


FEATURE = "track_fill_v1"
SCHEMA = 19
TIERS = ("sapphire", "gold", "platinum")
MAX_TICKS = 960 * 60 * 60
MAX_CRATES = 127  # The retail perfect bonus reads the driver's count as signed.
# Weapon crates (WF1) share the sanity budget of a LEV family: at most 80.
MAX_WEAPON_CRATES = 80
FAMILIES = ("time_crates", "letters", "fruit_crates", "loose_fruit", "weapon_crates", "grid")
EMPTY_FAMILIES = {"letters": {}, "fruit_crates": [], "loose_fruit": []}
#: Rank of a copied weapon crate, OV1 rule 5: the donor object's ruling, start
#: ground at Boost 0, otherwise USF. `rank` uses the box spot `needs` scale.
RANK_SOURCES = ("donor_ruling", "start_ground", "default_usf")
RANK_NAMES = ("none", "boost", "usf")
HEX_SHA = re.compile(r"[0-9a-f]{64}")
TRACK_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def payload_sha256(fill):
    payload = {key: value for key, value in fill.items() if key != "fill_sha256"}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _fields(value, keys):
    return type(value) is dict and value.keys() == set(keys)


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _sha(value):
    return type(value) is str and HEX_SHA.fullmatch(value) is not None


def _position(value):
    return type(value) is list and len(value) == 3 and all(_int(axis, -32768, 32767) for axis in value)


def validate(fill, lev_sha, laps):
    """Validate the frozen record against the package LEV and lap count."""
    if not _fields(fill, (
            "schema", "lev_sha256", "generator", "donors", "families",
            "counts", "relic_targets", "fill_sha256")):
        raise ValueError("fill has unsupported or incomplete record fields")
    if not _int(fill["schema"], 1, 1):
        raise ValueError("unsupported track fill schema")
    if not _sha(lev_sha) or fill["lev_sha256"] != lev_sha:
        raise ValueError("track fill LEV hash differs from the package pin")
    generator = fill["generator"]
    if (not _fields(generator, ("name", "version")) or generator["name"] != "ctr-track-fill"
            or not _int(generator["version"], 1, 1)):
        raise ValueError("unsupported track fill generator")
    donors = fill["donors"]
    if type(donors) is not list or not 1 <= len(donors) <= 2:
        raise ValueError("track fill requires one or two donors")
    seen = {lev_sha}
    for donor in donors:
        if (not _fields(donor, ("lev_sha256", "road_sha256", "kind", "overlap"))
                or not _sha(donor["lev_sha256"]) or donor["lev_sha256"] in seen
                or not _sha(donor["road_sha256"])):
            raise ValueError("invalid track fill donor identity")
        seen.add(donor["lev_sha256"])
        overlap = donor["overlap"]
        # Overlap is in hundred-thousandths to keep the wire integer-only.
        if (not _int(overlap, 95000, 100000)
                or donor["kind"] not in ("identical", "similar>=0.95")
                or (donor["kind"] == "identical" and overlap != 100000)):
            raise ValueError("track fill requires a same-road donor")
    families = fill["families"]
    if not _fields(families, FAMILIES) or any(families[key] != empty for key, empty in EMPTY_FAMILIES.items()):
        raise ValueError("unsupported track fill families")
    crates = families["time_crates"]
    weapons = families["weapon_crates"]
    if (type(crates) is not list or len(crates) > MAX_CRATES or type(weapons) is not list
            or len(weapons) > MAX_WEAPON_CRATES or not crates and not weapons):
        raise ValueError("invalid time crate set size")
    seen_positions = set()
    for crate in weapons:
        if (not _fields(crate, ("pos", "rot", "rank", "rank_source")) or not _position(crate["pos"])
                or not _position(crate["rot"]) or not _int(crate["rank"], 0, 2)
                or crate["rank_source"] not in RANK_SOURCES
                or crate["rank_source"] == "start_ground" and crate["rank"] != 0
                or crate["rank_source"] == "default_usf" and crate["rank"] != 2
                or tuple(crate["pos"]) in seen_positions):
            raise ValueError("invalid track fill weapon crate")
        # Native finds a spawned crate by its exact position (seat and sanity).
        seen_positions.add(tuple(crate["pos"]))
    for crate in crates:
        if (not _fields(crate, ("pos", "type")) or not _position(crate["pos"])
                or not _int(crate["type"], 1, 3)):
            raise ValueError("invalid track fill time crate")
    grid = families["grid"]
    if grid is not None and (
            type(grid) is not list or len(grid) != 8 or any(
                not _fields(spawn, ("pos", "rot_y")) or not _position(spawn["pos"])
                or not _int(spawn["rot_y"], -32768, 32767) for spawn in grid)):
        raise ValueError("invalid track fill starting grid")
    counts = fill["counts"]
    if (not _fields(counts, FAMILIES) or any(
            not _int(counts[name], len(families[name] or ()), len(families[name] or ()))
            for name in FAMILIES)):
        raise ValueError("track fill counts differ from its families")
    targets = fill["relic_targets"]
    if not crates:
        # A weapon-only fill opens no Relic Race and carries no targets.
        if targets is not None:
            raise ValueError("track fill relic targets need time crates")
    elif not _fields(targets, (*TIERS, "source", "laps")) or targets["source"] not in ("saphi", "author"):
        raise ValueError("track fill requires relic targets from Saphi or the author")
    elif not _int(targets["laps"], 1, 7) or targets["laps"] != laps:
        raise ValueError("track fill relic target laps differ from the package")
    elif (any(not _int(targets[tier], 1, MAX_TICKS) for tier in TIERS)
            or not targets["sapphire"] > targets["gold"] > targets["platinum"]):
        raise ValueError("track fill relic targets must descend from sapphire to platinum")
    if not _sha(fill["fill_sha256"]) or fill["fill_sha256"] != payload_sha256(fill):
        raise ValueError("track fill SHA-256 mismatch")
    return fill


def time_crates(fill):
    return (fill or {}).get("families", {}).get("time_crates") or []


def weapon_crates(fill):
    return (fill or {}).get("families", {}).get("weapon_crates") or []


def package_weapons(package):
    """The weapon crates a package's frozen fill adds, in ordinal order."""
    return weapon_crates((package or {}).get("fill"))


def seated_ordinals(package, spots, lev_count=0):
    """One-based weapon ordinals an AP box takes over: a fill crate at exactly
    the position and angle of a standing spot (native ap_boxes.c does the same)."""
    where = {(tuple(s["pos"]), s["rot_y"]) for s in spots}
    return [lev_count + i for i, crate in enumerate(package_weapons(package), 1)
            if (tuple(crate["pos"]), crate["rot"][1]) in where]


@lru_cache(maxsize=1)
def _catalogue():
    # ZIP loaders raise OSError for missing entries. Check the generated
    # catalogue before asking the resource loader for an optional fill.
    return json.loads(pkgutil.get_data(__package__, "data/track_fill/index.json"))


def bundled(key, lev_sha, laps):
    """Read the apworld entry for the exact LEV and verified lap count."""
    if not TRACK_KEY.fullmatch(key) or not _sha(lev_sha):
        raise ValueError("invalid bundled track fill identity")
    pin = _catalogue().get(key, {}).get(lev_sha)
    if not pin or laps != pin["laps"]:
        return None
    data = pkgutil.get_data(__package__, f"data/track_fill/{key}/{lev_sha[:16]}.json")
    fill = validate(json.loads(data), lev_sha, laps)
    if fill["fill_sha256"] != pin["fill_sha256"]:
        raise ValueError("bundled track fill differs from its generated catalogue pin")
    return fill
