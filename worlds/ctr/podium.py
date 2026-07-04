"""Podium placement checks (v1 feature; feat/podium-checks).

A nested per-race rung ladder on the 16 adventure trophy races:

    "first"  -> Finish 1st
    "podium" -> Finish 2nd or 3rd
    "any"    -> Finish (Any Position)   [optional, podium_any_position_rung]

A better result satisfies every rung at or below it, so 1st fires all three.
These are NEW event-only locations: the game has no AdvProgress bit for
"finished 2nd", so they do NOT reuse the trophy/warp-pad gate bit scheme. They
are fired NATIVE-side from the placement listener (feat/podium-listener) at the
finish-line capture point -- the only surface that observes a non-1st finish,
since vanilla adventure sends anything but 1st to the Retry/Exit menu without
reaching the trophy-award code. See the 2026-07-04 podium-listener handoff.

This module is the single source of the podium layout (names, codes, ordering)
and is consumed by Locations.py (datapackage), Regions.py (per-seed location
creation), Rules.py (reachability), and __init__.fill_slot_data (the native
fan-out mapping). Codes never collide with the existing 35011/35012/35013
blocks; the podium block is 35015000+.
"""
import json
import pkgutil

# Podium location codes: PODIUM_CODE_BASE + track_index * len(RUNGS) + rung_index.
# track_index follows the canonical trophy-race order (see TROPHY_TRACKS below).
PODIUM_CODE_BASE = 35015000

# Rung keys in nesting order (best result -> broadest), with the location-name
# suffix each produces. The code offset within a track == the index here.
RUNGS = [
    ("first",  "Finish 1st"),
    ("podium", "Finish 2nd or 3rd"),
    ("any",    "Finish (Any Position)"),
]
_RUNG_SUFFIX = dict(RUNGS)
_RUNG_INDEX = {key: i for i, (key, _s) in enumerate(RUNGS)}


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
    """AP location name for a track's rung, e.g. 'Crash Cove: Finish 2nd or 3rd'."""
    return f"{track}: {_RUNG_SUFFIX[rung_key]}"


def location_code(track_index: int, rung_index: int) -> int:
    return PODIUM_CODE_BASE + track_index * len(RUNGS) + rung_index


def enabled_rung_keys(any_position: bool):
    """The rung keys present in a seed. The any-position rung is optional; the
    1st and podium rungs are always present when the feature is on."""
    keys = ["first", "podium"]
    if any_position:
        keys.append("any")
    return keys


def all_podium_locations():
    """Every possible podium rung as (name, code, region) -- ALL 48, independent
    of options. This is the DATAPACKAGE view (name<->id is global to the game);
    which rungs a given seed actually creates is decided in Regions.py."""
    out = []
    for ti, track in enumerate(TROPHY_TRACKS):
        for ri, (rung_key, _suffix) in enumerate(RUNGS):
            out.append((location_name(track, rung_key), location_code(ti, ri), track))
    return out
