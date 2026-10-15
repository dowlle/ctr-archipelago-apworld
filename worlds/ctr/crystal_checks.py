"""Position-owned Crystalsanity checks (#236), minted in the 0.3.0 id step.
The optional seed subset inherits the arena's actual entry gates.

WHAT THIS CHECKS. `<Arena>: Crystal NN`, one check per authored crystal in a
retail battle arena's Crystal Challenge, NN 01..20 by authored instance
position (ruled 2026-10-13 21:37 CEST, #236 answer 7).

WHY 20. Counted from the retail NTSC-U BIGFILE (sha256 98779a79...fce7) on
2026-10-15: every LEV variant of Skull Rock, Rampage Ruins, Rocky Road and
Nitro Court carries exactly 20 STATIC_CRYSTAL (model 0x60) instances, the
same count INSTANCE.c adds into numCrystalsInLEV.

THE ARCADE ARENAS ARE NOT MINTED. Parking Lot, The North Bowl and Lab Basement
carry 0 crystal instances in every LEV variant, so `<Arena>: Crystal NN` and a
Crystal Challenge on them name nothing in the retail data. Their block
35028500..35028599 (#259) stays reserved without names until the #259 design
says where their crystals come from.

WHO OWNS THE SEMANTICS. The apworld owns names, codes and the per-seed subset
(option `crystalsanity`); native owns the pickup send in
game/231/RB_Crystal.c. The four completion checks stay the frozen
`<Arena>: Crystal Challenge` ids at 35013000..35013003.

DATAPACKAGE STABILITY. `35028400 + 20 * arena + (NN - 1)`, arena order Skull
Rock, Rampage Ruins, Rocky Road, Nitro Court (the 35013000 order). Every name
registers unconditionally. Approved in the 0.3.0 minting register (ruled
2026-10-13 22:02 CEST).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from typing import List, Tuple

from . import destinations
from .location_class import LocationClass

CRYSTAL_CODE_BASE = 35028400
CRYSTALS_PER_ARENA = 20
#: Retail arenas in completion-code order (35013000..35013003).
CRYSTAL_ARENAS: Tuple[str, ...] = ("Skull Rock", "Rampage Ruins", "Rocky Road", "Nitro Court")
assert CRYSTAL_ARENAS == destinations.ARENA_TRACKS

#: #259 arcade arenas: reserved, not minted (no authored crystals).
ARCADE_ARENA_RESERVED_RANGE = (35028500, 35028599)


def crystal_name(arena: str, number: int) -> str:
    if type(number) is not int or not 1 <= number <= CRYSTALS_PER_ARENA:
        raise ValueError(f"crystal number must be 1..{CRYSTALS_PER_ARENA}")
    return f"{arena}: Crystal {number:02d}"


class CrystalLocationClass(LocationClass):
    key = "crystalsanity"
    display_name = "Crystal Checks"
    code_blocks = (CRYSTAL_CODE_BASE,)

    def all_locations(self):
        return [(crystal_name(arena, n), CRYSTAL_CODE_BASE + ai * CRYSTALS_PER_ARENA + n - 1, arena)
                for ai, arena in enumerate(CRYSTAL_ARENAS)
                for n in range(1, CRYSTALS_PER_ARENA + 1)]

    def location_name(self, arena: str, number: int) -> str:
        return crystal_name(arena, number)

    def created_location_names(self, options) -> List[str]:
        if not (getattr(getattr(options, "crystalsanity", None), "value", 0)
                and options.include_battle_arenas.value):
            return []
        from .cortex_vortex_track import dropped_region
        dropped = dropped_region(options)
        return [name for name, _code, arena in self.all_locations() if arena != dropped]


CRYSTAL_CLASS = CrystalLocationClass()

# NTSC-U: the 20 crystals are consecutive and position order agrees across
# every player-count variant. Three arenas omit preceding crates in 4P.
ARENA_LEVELS = (21, 19, 23, 18)
INSTANCE_BASES = ((8, 8, 8, 0), (28, 28, 28, 19),
                  (25, 25, 25, 25), (45, 45, 45, 41))


def wire_block(world):
    """Only actual seed locations travel, in authored-position order."""
    names = {loc.name for loc in world.multiworld.get_locations(world.player)}
    arenas = {}
    for ai, arena in enumerate(CRYSTAL_ARENAS):
        codes = [CRYSTAL_CLASS.code_for(arena, n) for n in range(1, 21)
                 if crystal_name(arena, n) in names]
        if codes:
            if len(codes) != 20:
                raise ValueError(f"{arena}: crystalsanity needs exactly 20 positions")
            arenas[str(ARENA_LEVELS[ai])] = {
                "instance_bases": list(INSTANCE_BASES[ai]), "locations": codes}
    return {"version": 1, "arenas": arenas}
