"""Authored item-box locations (#109).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. One check per authored
item-box position on a track. The boxes are position-keyed and mode-agnostic per
the 2026-08-06 positioning design: a box sits at a place, not at a race type, so
the same physical box is the same check whichever race mode is running on that
track. Breaking it sends the check and grants nothing locally.

WHO OWNS THE SEMANTICS. The apworld owns the names, the per-seed subset (a #179
elastic count) and the difficulty-tier logic exclusions; native owns the spawner,
the collision answer and the loader. Neither half is built here.

THE NAME COUNT IS A CEILING, NOT A PLACEMENT (Stef, 2026-08-10 16:23). This block
freezes the FULL 18 tracks x 15 slots = 270-name ceiling, index-based per track,
NOT the 241 boxes currently authored. Future box work -- the pending curation
pass, lap-skip additions, curation swaps -- moves which slots a seed creates and
never needs another datapackage bump. The 241 authored placements live in
`Development/Placement Backups/2026-08-10 154700 -- AP box placements -- FINAL
241 across 18 tracks (logic survey complete).json` in the vault and are the
placement truth; this module is the name truth, and the two are deliberately
decoupled.

The 18 box tracks are the 16 adventure trophy tracks plus Slide Coliseum and
Turbo Track -- the boxes-on-all-race-types ruling (12:01) extended by the
boxes-in-relic-races ruling (13:58). That is the same 18-track set the relic
races use, and the same 18 tracks the placement file carries.

DATAPACKAGE STABILITY. This class claims the additive block 35014000, stride 15
per track in BOX_TRACKS order, and registers all 270 names UNCONDITIONALLY.
35014xxx was recorded as free by #177's own issue body; the block is clear of the
static 35011xxx-35013xxx families, the relic-perfect 35012400 block, the
lettersanity 35012500 block, the podium 35015000 / 35015100 blocks and the
itemsanity 35016xxx family.

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

NAMES LAND INERT. `created_location_names` returns nothing, unconditionally,
because no option creates these locations yet -- the 0.2.0 freeze mints names,
not features.
"""
import json
import pkgutil

from .location_class import LocationClass

# Additive block for the 270 item-box checks, stride 15 per track.
ITEM_BOX_CODE_BASE = 35014000

#: Per-track slot ceiling. The curation model's "roughly 15 candidate slots per
#: track", taken as the hard naming ceiling per the 16:23 ruling. Frozen: it is
#: the per-track stride, so changing it would renumber every track after the
#: first.
SLOTS_PER_TRACK = 15


def _box_tracks():
    """The 18 box tracks in canonical (Sapphire-trial code) order, read from
    data/locations.json so this block's codes/order can never drift. The box set
    is the 16 trophy tracks plus the two trial tracks, which is exactly the set
    that carries Time Trial locations -- the same canon relic_perfect.py uses."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": Sapphire Time Trial") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 18 entries.
BOX_TRACKS = _box_tracks()


class ItemBoxLocationClass(LocationClass):
    """The 270 authored item-box checks as a `LocationClass` (#176)."""

    key = "item_boxes"
    display_name = "Item Box Checks"
    code_blocks = (ITEM_BOX_CODE_BASE,)

    def all_locations(self):
        return [(self.location_name(track, slot + 1),
                 ITEM_BOX_CODE_BASE + ti * SLOTS_PER_TRACK + slot,
                 track)
                for ti, track in enumerate(BOX_TRACKS)
                for slot in range(SLOTS_PER_TRACK)]

    def location_name(self, track: str, slot: int) -> str:
        """AP location name for a track's box slot, e.g.
        'Crash Cove: Item Box 1'. `slot` is 1-based because the name is
        player-visible in hints and trackers and a 0-based first box would read
        as a bug; the CODE is 0-based off the block, as everywhere else."""
        return f"{track}: Item Box {slot}"

    def created_location_names(self, options):
        """Nothing, until #109's option exists. See the module docstring."""
        return []


#: The registered item-box class. `Locations.py` registers this instance.
ITEM_BOX_CLASS = ItemBoxLocationClass()
