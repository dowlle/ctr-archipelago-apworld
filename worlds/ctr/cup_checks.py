"""Cup check names minted in the 0.3.0 id step: cup points wins, cup sweeps
(#246) and Cup Leg Victory. Names only; no seed creates them yet.

WHAT THESE CHECK. `<Cup>: Win` is the points win of one logical Cup drawn from
the named cup pool. `<Cup>: Win All Legs` (#246) is winning all four legs of
that Cup in first place; `<Colour> Gem Cup: Win All Legs` is the same for the
five retail Gem Cups. `<Track>: Cup Leg Victory` is the first-place check of a
track that appears only as a Cup leg in a seed, with no standalone Trophy Race;
repeated legs share it (ruling 17, 2026-09-01; semantics ruling 29).

WHO OWNS THE SEMANTICS. The apworld owns the names, codes and the per-seed
subset; native owns the leg results and the sends. Neither half is built here:
every class below returns an empty per-seed subset, so no seed changes.

THE CUP NAME POOL (ruled 2026-10-13 21:47 CEST). Every cup name is a real,
frozen location name, and each seed draws which named cups it uses from the
pool. Index i of CUP_NAMES owns `35027000 + i` (Win) and `35027200 + i`
(Win All Legs), so a later name appended at index 100 + j gets the matching
pair `35027100 + j` and `35027300 + j`. 35027027 is Cortex Vortex's Cup Leg
Victory and stays outside the pool.

DATAPACKAGE STABILITY. Code blocks: 35027000 (Win 0..26, Cortex Vortex leg
27, reserved growth 100..199), 35027200 (Win All Legs 0..26, reserved growth
300..399), 35028300 (Gem Cup sweeps), 35016800 (retail and generic Cup Leg
Victory). Every name registers unconditionally. Approved in the 0.3.0 minting
register (ruled 2026-10-13 22:02 CEST).

FROZEN-NAME WARNING: once released these names and codes are permanent. New
cup names append to CUP_NAMES; nothing is reordered or renamed.
"""
from typing import List, Tuple

from . import destinations
from .custom_check_namespace import CUSTOM_SLOT_COUNT
from .item_boxes import BOX_TRACKS
from .location_class import LocationClass

#: The approved named cup pool, in code order. APPEND ONLY (up to 100 more).
CUP_NAMES: Tuple[str, ...] = (
    "Patries Cup", "Icebound Cup", "Taor Cup", "JurnthReinal Cup", "Lockheart Cup",
    "Hypnoshark Cup", "Appie Cup", "TheCodingBob Cup", "Superstarxalien Cup",
    "TheRedhotbr Cup", "Avery Cup", "MarioSpore Cup", "Venusyprime Cup", "BEXUS99 Cup",
    "Bethany Cup", "Niko1Point0 Cup", "Aalhendi Cup", "MateusFavarin Cup",
    "TheUbMunster Cup", "Kabarakh Cup", "DragRedSim Cup", "Stroodlydoodles Cup",
    "Bob90 Cup", "Turbo Cup", "Relic Cup", "Multiworld Cup", "Sphere Cup",
)
#: Room reserved for later cup names, ruled 2026-10-13 21:47 CEST.
CUP_NAME_CAPACITY = 127

CUP_WIN_CODE_BASE = 35027000
CUP_WIN_GROWTH_BASE = 35027100
CUP_SWEEP_CODE_BASE = 35027200
CUP_SWEEP_GROWTH_BASE = 35027300
CORTEX_VORTEX_CUP_LEG_CODE = 35027027
GEM_CUP_SWEEP_CODE_BASE = 35028300
RETAIL_CUP_LEG_CODE_BASE = 35016800
CUSTOM_CUP_LEG_CODE_BASE = 35016820

#: The five retail Gem Cups in LevelID order (the `<Colour> Gem Cup: Gem` order).
GEM_CUPS: Tuple[str, ...] = tuple(region for region, _level in destinations.CUP_LEVEL_IDS)
assert GEM_CUPS == ("Red Gem Cup", "Green Gem Cup", "Blue Gem Cup",
                    "Yellow Gem Cup", "Purple Gem Cup")
assert len(set(CUP_NAMES)) == len(CUP_NAMES) <= CUP_NAME_CAPACITY


def _pool_code(base: int, growth_base: int, index: int) -> int:
    """Index 0..26 sits at `base + index`; a later name at 27.. uses the
    growth range `growth_base + (index - 27)`, because 35027027 is taken."""
    if index < 27:
        return base + index
    return growth_base + index - 27


def cup_win_name(cup: str) -> str:
    return f"{cup}: Win"


def cup_sweep_name(cup: str) -> str:
    return f"{cup}: Win All Legs"


def cup_leg_name(track: str) -> str:
    return f"{track}: Cup Leg Victory"


class CupWinLocationClass(LocationClass):
    """`<Cup>: Win`, the points win of one named cup."""
    key = "cup_win"
    display_name = "Cup Points Wins"
    code_blocks = (CUP_WIN_CODE_BASE,)

    def all_locations(self):
        return [(cup_win_name(cup), _pool_code(CUP_WIN_CODE_BASE, CUP_WIN_GROWTH_BASE, i), "Menu")
                for i, cup in enumerate(CUP_NAMES)]

    def location_name(self, cup: str) -> str:
        return cup_win_name(cup)

    def created_location_names(self, options) -> List[str]:
        return []


class CupSweepLocationClass(LocationClass):
    """#246: winning all four legs, for the named cups and the Gem Cups."""
    key = "cup_sweep"
    display_name = "Cup Sweeps"
    code_blocks = (CUP_SWEEP_CODE_BASE, GEM_CUP_SWEEP_CODE_BASE)

    def all_locations(self):
        named = [(cup_sweep_name(cup),
                  _pool_code(CUP_SWEEP_CODE_BASE, CUP_SWEEP_GROWTH_BASE, i), "Menu")
                 for i, cup in enumerate(CUP_NAMES)]
        gem = [(cup_sweep_name(cup), GEM_CUP_SWEEP_CODE_BASE + i, cup)
               for i, cup in enumerate(GEM_CUPS)]
        return named + gem

    def location_name(self, cup: str) -> str:
        return cup_sweep_name(cup)

    def created_location_names(self, options) -> List[str]:
        return list(getattr(options, "_cup_sweep_selected", ())) if getattr(
            getattr(options, "cup_sweep_checks", None), "value", 0) else []


class CupLegVictoryLocationClass(LocationClass):
    """First place in a Cup leg for a track with no standalone Trophy Race."""
    key = "cup_leg_victory"
    display_name = "Cup Leg Victories"
    code_blocks = (RETAIL_CUP_LEG_CODE_BASE, CUP_WIN_CODE_BASE)

    def all_locations(self):
        out = [(cup_leg_name(destinations.CORTEX_VORTEX), CORTEX_VORTEX_CUP_LEG_CODE,
                destinations.CORTEX_VORTEX)]
        out += [(cup_leg_name(track), RETAIL_CUP_LEG_CODE_BASE + i, track)
                for i, track in enumerate(BOX_TRACKS)]
        out += [(cup_leg_name(destinations.custom_slot_region(slot)),
                 CUSTOM_CUP_LEG_CODE_BASE + slot - 1, destinations.custom_slot_region(slot))
                for slot in range(1, CUSTOM_SLOT_COUNT + 1)]
        return out

    def location_name(self, track: str) -> str:
        return cup_leg_name(track)

    def created_location_names(self, options) -> List[str]:
        return []


CUP_WIN_CLASS = CupWinLocationClass()
CUP_SWEEP_CLASS = CupSweepLocationClass()
CUP_LEG_VICTORY_CLASS = CupLegVictoryLocationClass()
