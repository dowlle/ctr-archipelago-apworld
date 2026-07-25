"""Relic-race perfect checks -- "break every time crate in the relic race" (#49).

The standalone randomizer has a mode where a relic reward requires a perfect run
(every time crate broken). Issue #49 asks for the CHECK half of that idea: an
optional location per relic race, earned by breaking every time crate in it. Per
Stef's ruling (2026-07-20, Feature Triage Register) this is:

  * a location class, NOT a reward gate. It never changes whether a relic is
    awarded -- that stricter variant (`rr_require_perfects`) is a DIFFERENT
    mechanic, backlogged, and deliberately does not share a name with this one.
  * optional, default OFF (the held-5th pattern).
  * ONE check per relic race, i.e. one per relic track -- the time crates are the
    same physical set whatever tier you are chasing, so it is 18 locations, not
    18 x 3.

The 18 relic tracks are the 16 adventure trophy tracks plus the two trial tracks
(Slide Coliseum, Turbo Track), exactly the set that carries Time Trial locations.

WHAT THE APWORLD OWNS. The apworld registers the names, creates the per-seed
subset, puts each created check in logic, and emits the native fan-out block. The
DETECTION is native's half (a separate item, not built here): the engine already
computes the signal, counting a level's time crates into `gGT->timeCratesInLEV`
at load and the driver's broken count into `driver->numTimeCrates` (it renders
the "NN/MM" counter from them), so "broke every crate" is
`numTimeCrates == timeCratesInLEV` at the end of a relic race. Until that native
half ships, a seed with this option ON creates 18 locations the client can never
send -- which is why the option is default OFF and why the block is emitted
additively (an older native ignores an unknown slot_data key).

DATAPACKAGE STABILITY. name<->id is global to the game and must never move once
shipped, so this module registers all 18 names UNCONDITIONALLY (Locations.py),
exactly like podium.py does for the rung superset; Regions.py decides which a
given seed CREATES, and get_total_locations counts only created locations so the
seed's reported TotalLocations never inflates.

Codes take an additive block at 35012400, clear of every shipped block: the
trophy/boss/gem 35011xxx family, the trial+token 35012000..35012315 family this
one extends, the crystal 35013xxx family, and the podium 35015000 / 35015100
blocks. Nothing shipped is renumbered (the 35015000 precedent: additive blocks
never move).

FROZEN-NAME WARNING. The location names below ride the single 0.2.0 datapackage
bump together with the rung superset and the item-pack names (triage-register
ruling: registering them in a later bump churns the datapackage twice). They must
be settled BEFORE that bump, because after it they are permanent.
"""
import json
import pkgutil

# Additive block for the 18 relic-perfect checks, stride 1 in RELIC_TRACKS order.
RELIC_PERFECT_CODE_BASE = 35012400

# Location-name suffix. Deliberately NOT ending in "Time Trial": the sphere-search
# vanilla reward map (warp_pad_logic._reward_for) and the stage-2 bookkeeping key
# off that suffix, and a perfect check yields no relic, so it must stay
# reward-neutral there.
RELIC_PERFECT_SUFFIX = "Relic Race Perfect"


def _relic_tracks():
    """The 18 relic-race tracks in canonical (Sapphire-trial code) order, read
    from data/locations.json so this block's codes/order can never drift from the
    relic block they parallel."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": Sapphire Time Trial") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 18 entries. Each entry is
# BOTH the track name and its AP region name: data/locations.json gives every
# Sapphire trial the region of its own track (the 16 trophy tracks and the two
# trial tracks are all regions), so a perfect check parents to the same region as
# the relic races it belongs to without a second lookup table.
RELIC_TRACKS = _relic_tracks()


def location_name(track: str) -> str:
    """AP location name for a track's perfect check, e.g.
    'Crash Cove: Relic Race Perfect'."""
    return f"{track}: {RELIC_PERFECT_SUFFIX}"


def _perfect_code(track_index: int) -> int:
    """Location code for a track, by its index in RELIC_TRACKS."""
    return RELIC_PERFECT_CODE_BASE + track_index


def created_from_options(options) -> bool:
    """Does THIS seed create the relic-perfect checks? Single source shared by
    Regions.py, Rules.py and __init__._resolve_relic_perfect so they can never
    disagree about which locations exist."""
    return bool(options.relic_perfect_checks.value)


def all_relic_perfect_locations():
    """Every possible relic-perfect check as (name, code, region) for the
    DATAPACKAGE -- the full frozen 18-name superset, independent of options.
    Which ones a given seed CREATES is decided in Regions.py."""
    return [(location_name(track), _perfect_code(ti), track)
            for ti, track in enumerate(RELIC_TRACKS)]


def code_for(track: str) -> int:
    """The location code for a track's perfect check."""
    return _perfect_code(RELIC_TRACKS.index(track))
