"""Relic-race perfect checks -- "break every time crate in the relic race" (#49).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. One check per relic
race, earned by breaking every time crate in it. The engine already computes the
signal: it counts a level's time crates into `gGT->timeCratesInLEV` at load and
the driver's broken count into `driver->numTimeCrates` (it renders the "NN/MM"
counter from them), so "broke every crate" is `numTimeCrates == timeCratesInLEV`
at the end of a relic race. Per Stef's ruling (2026-07-20, Feature Triage
Register) this is a location class, NOT a reward gate: it never changes whether a
relic is awarded. The stricter `rr_require_perfects` variant is a DIFFERENT
mechanic, backlogged, and deliberately does not share a name with this one.

WHO OWNS THE SEMANTICS. The apworld owns the names and (once the option exists)
the per-seed subset and the logic rules; native owns the detection. Neither half
is built here.

The 18 relic tracks are the 16 adventure trophy tracks plus the two trial tracks
(Slide Coliseum, Turbo Track), exactly the set that carries Time Trial locations.

DATAPACKAGE STABILITY. This class claims the additive block 35012400, stride 1 in
RELIC_TRACKS order, and registers all 18 names UNCONDITIONALLY. The block is
clear of every shipped block: the trophy/boss/gem 35011xxx family, the
trial+token 35012000..35012315 family this one extends, the crystal 35013xxx
family, and the podium 35015000 / 35015100 blocks. Nothing shipped is renumbered
(the 35015000 precedent: additive blocks never move).

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

NAMES LAND INERT. `created_location_names` returns nothing, unconditionally,
because no option creates these locations yet -- the 0.2.0 freeze mints names,
not features. When #49's build lands it replaces the body of that one method with
the real per-seed predicate; nothing else in this module changes.

Prior art: `feat/49-relic-perfect-checks` carries a full pre-#176 implementation
of this class (option, regions, rules, slot_data block). That branch is NOT on
`main` -- the #177 freeze table's "apworld half already on `main`" row was wrong,
corrected by the 08-10 balance sheet and re-verified here. The names below match
that branch's names, codes and track order exactly, so landing it later is a
behaviour change with no datapackage churn.
"""
import json
import pkgutil

from .location_class import LocationClass

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


class RelicPerfectLocationClass(LocationClass):
    """The 18 relic-race perfect checks as a `LocationClass` (#176)."""

    key = "relic_perfect"
    display_name = "Relic Race Perfect Checks"
    code_blocks = (RELIC_PERFECT_CODE_BASE,)

    def all_locations(self):
        return [(self.location_name(track), RELIC_PERFECT_CODE_BASE + ti, track)
                for ti, track in enumerate(RELIC_TRACKS)]

    def location_name(self, track: str) -> str:
        """AP location name for a track's perfect check, e.g.
        'Crash Cove: Relic Race Perfect'."""
        return f"{track}: {RELIC_PERFECT_SUFFIX}"

    def created_location_names(self, options):
        """Nothing, until #49's option exists. See the module docstring."""
        return []


#: The registered relic-perfect class. `Locations.py` registers this instance.
RELIC_PERFECT_CLASS = RelicPerfectLocationClass()
