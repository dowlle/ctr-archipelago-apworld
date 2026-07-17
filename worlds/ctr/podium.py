"""Podium placement checks -- position-rung location rework (v0.2.0, Phase A).

Per adventure trophy race (16 tracks) the game exposes a rung ladder. v0.1.x
shipped a 3-rung finish ladder; v0.2.0 reworks it into a 5-rung superset that
splits live-position ("held") rungs from finish-line rungs:

    slot 0  held_1st       "Held 1st"            live position hit 1st
    slot 1  held_3rd       "Held 3rd"            live position hit top-3
    slot 2  held_5th       "Held 5th"            live position hit top-5 (DEFAULT OFF)
    slot 3  finish_podium  "Finish on Podium"    crossed the line 1st..3rd
    slot 4  finish_any     "Finish (Any Position)" crossed the line at all

The listener/ladder semantics (a higher rung granting every lower one, live
debounce, the win backstop) live NATIVE-side; the apworld only registers the
names, creates the per-seed subset, and puts each created rung in logic. Every
created rung is reachable exactly when its destination track is raceable -- the
same assumption the shipped podium checks used -- so no rung ever adds a
solvability burden (a winnable race yields every rung).

DATAPACKAGE STABILITY. name<->id is global to the game and must never move once
shipped, so this module registers the FULL superset unconditionally:

  * the 3 v0.1.x names -- "Finish 1st", "Finish 2nd or 3rd", "Finish (Any
    Position)" -- stay registered FOREVER at the original 35015000 block. "Finish
    1st" and "Finish 2nd or 3rd" are RETIRED FROM CREATION (a live 1st is now
    "Held 1st"; 2nd-or-3rd is now "Finish on Podium") but remain dead datapackage
    entries. "Finish (Any Position)" keeps being created -- it IS the finish_any
    rung, reusing its original code.
  * the 4 genuinely-new names -- "Held 1st", "Held 3rd", "Held 5th", "Finish on
    Podium" -- get an additive new base block (35015100, stride 4). Nothing
    shipped is renumbered (the 35015000 precedent: additive blocks never move).

This module is the single source of the podium layout (names, codes, slot order,
creation subset) and is consumed by Locations.py (datapackage), Regions.py
(per-seed creation), Rules.py (reachability), and __init__._resolve_podium_checks
(the schema-6 slot_data fan-out array).
"""
import json
import pkgutil

# v0.1.x block (retired-but-registered names + the still-created finish_any).
PODIUM_CODE_BASE = 35015000
# v0.2.0 additive block for the four new rungs. Does NOT overlap 35015000..047
# (16 tracks * 3). Kept clear of that range with headroom.
HELD_CODE_BASE = 35015100

# Shipped rungs (name suffix per rung). Order == code offset within the 35015000
# block, frozen by v0.1.x. All three stay registered forever.
SHIPPED_RUNGS = [
    ("first",  "Finish 1st"),            # retired from creation
    ("podium", "Finish 2nd or 3rd"),     # retired from creation
    ("any",    "Finish (Any Position)"),  # still created, == finish_any
]
_SHIPPED_INDEX = {key: i for i, (key, _s) in enumerate(SHIPPED_RUNGS)}

# New rungs (v0.2.0). Order == code offset within the 35015100 block.
NEW_RUNGS = [
    ("held_1st",      "Held 1st"),
    ("held_3rd",      "Held 3rd"),
    ("held_5th",      "Held 5th"),
    ("finish_podium", "Finish on Podium"),
]
_NEW_INDEX = {key: i for i, (key, _s) in enumerate(NEW_RUNGS)}

# The schema-6 slot_data 5-slot array order, agreed with the native session. Each
# per-track podium_checks entry is [held_1st, held_3rd, held_5th, finish_podium,
# finish_any] of location codes (-1 = rung absent from this seed).
SLOT_ORDER = ["held_1st", "held_3rd", "held_5th", "finish_podium", "finish_any"]

# rung key -> location-name suffix. finish_any reuses the shipped "any" name so
# the created finish_any location IS the shipped "Finish (Any Position)" entry.
_RUNG_SUFFIX = dict(SHIPPED_RUNGS)
_RUNG_SUFFIX.update(dict(NEW_RUNGS))
_RUNG_SUFFIX["finish_any"] = _RUNG_SUFFIX["any"]


def _trophy_tracks():
    """The 16 trophy-race track names in canonical (trophy-code) order, read from
    data/locations.json so the podium codes/order can never drift from the
    trophy block they parallel."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": Trophy Race") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 16 entries.
TROPHY_TRACKS = _trophy_tracks()


def location_name(track: str, rung_key: str) -> str:
    """AP location name for a track's rung, e.g. 'Crash Cove: Held 1st'."""
    return f"{track}: {_RUNG_SUFFIX[rung_key]}"


def _rung_code(track_index: int, rung_key: str) -> int:
    """Location code for a (track, rung). Shipped rungs (first/podium/any) and
    finish_any resolve into the frozen 35015000 block; the four new rungs resolve
    into the additive 35015100 block. Never renumbers a shipped code."""
    if rung_key in _SHIPPED_INDEX:
        return PODIUM_CODE_BASE + track_index * len(SHIPPED_RUNGS) + _SHIPPED_INDEX[rung_key]
    if rung_key == "finish_any":
        return PODIUM_CODE_BASE + track_index * len(SHIPPED_RUNGS) + _SHIPPED_INDEX["any"]
    return HELD_CODE_BASE + track_index * len(NEW_RUNGS) + _NEW_INDEX[rung_key]


def created_rung_keys(finish_on: bool, any_on: bool,
                      held_on: bool, held_fifth_on: bool):
    """The rung keys a seed CREATES as locations, given the four sub-toggles
    (the master Podium Placement Checks gate is applied by the caller). Uses the
    creation-side keys -- 'finish_any' (not the shipped 'any'), so the created
    finish rung reuses the shipped 'Finish (Any Position)' name/code.

      held rungs on   -> Held 1st + Held 3rd (+ Held 5th when its toggle is on)
      finish rungs on -> Finish on Podium (+ Finish (Any Position) when any-pos on)
    """
    keys = []
    if held_on:
        keys.append("held_1st")
        keys.append("held_3rd")
        if held_fifth_on:
            keys.append("held_5th")
    if finish_on:
        keys.append("finish_podium")
        if any_on:
            keys.append("finish_any")
    return keys


def created_rung_keys_from_options(options):
    """created_rung_keys read straight off a seed's options, honouring the master
    Podium Placement Checks gate. Single source of the creation subset shared by
    Regions.py, Rules.py and __init__._resolve_podium_checks so they can never
    disagree on which rungs a seed has."""
    if not bool(options.podium_placement_checks.value):
        return []
    return created_rung_keys(
        finish_on=bool(options.podium_finish_rungs.value),
        any_on=bool(options.podium_any_position_rung.value),
        held_on=bool(options.podium_held_rungs.value),
        held_fifth_on=bool(options.podium_held_fifth_rung.value),
    )


def podium_slot_codes(track: str, created_keys) -> list:
    """The schema-6 5-slot code array for a track: SLOT_ORDER mapped to each
    rung's location code, or -1 where that rung is absent from this seed."""
    ti = TROPHY_TRACKS.index(track)
    created = set(created_keys)
    return [(_rung_code(ti, slot_key) if slot_key in created else -1)
            for slot_key in SLOT_ORDER]


def all_podium_locations():
    """Every possible podium rung as (name, code, region) for the DATAPACKAGE --
    the full frozen superset independent of options: the 3 shipped rungs at the
    35015000 block PLUS the 4 new rungs at the 35015100 block, for all 16 tracks
    (7 entries/track; finish_any is not double-registered -- it shares the shipped
    'any' name/code). Which rungs a given seed CREATES is decided in Regions.py."""
    out = []
    for ti, track in enumerate(TROPHY_TRACKS):
        for rung_key, suffix in SHIPPED_RUNGS:
            out.append((f"{track}: {suffix}", _rung_code(ti, rung_key), track))
        for rung_key, suffix in NEW_RUNGS:
            out.append((f"{track}: {suffix}", _rung_code(ti, rung_key), track))
    return out
