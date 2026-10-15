"""Generic custom-track families and Cortex Vortex's Relic Race Perfect, minted
in the 0.3.0 id step. Names only; no seed creates them yet.

WHY THESE EXIST. The generic `Custom Track N` path (B+) was ruled to
work in 0.3.0 for tracks the apworld does not know (#306 Q3). Its letters and
CTR Token Challenge are already live; this module mints the remaining approved
reservations so the feature lanes attach to names that already sit in the
datapackage. Tracks the apworld does know use their named block instead
(named_tracks.py).

FAMILIES, all `Custom Track N` with N the generic slot:

  * Relic Race Perfect (#453), `35024000 + N - 1`, N 1..132, and Cortex
    Vortex's `Cortex Vortex: Relic Race Perfect` at 35026005 (reserved
    2026-09-13). Spelling from custom_check_namespace.
  * Relic Time Trial tiers, `35022000 + 3 * (N - 1) + tier`, Sapphire, Gold,
    Platinum, N 1..132 (reservation of 2026-09-12, minted with the perfects).
  * Race family v2, slots 33..132 only: `Trophy Race` at
    `35019000 + 6 * (N - 1)` and the five podium rungs at +1..+5 in
    podium.SLOT_ORDER. Slots 1..32 keep their live 0.2.x names and ids
    (35016300..35016559); a name can have only one id, so v2 codes
    35019000..35019191 stay permanently unused (ruled 2026-10-13 22:02 CEST,
    answer 4).
  * Reach 10 Wumpa, slot owned, `35016600 + N - 1` (approved 2026-09-02).
  * AP boxes, `Item Box M` for M 1..15, `35017000 + 15 * (N - 1) + M - 1`
    (reservation approved 2026-09-02). The box delivery model for custom
    tracks is still open; the names do not depend on it.

WHO OWNS THE SEMANTICS. The apworld owns names, codes and the per-seed subset;
native owns the sends. Every class here returns an empty per-seed subset, so no
seed changes. relic_perfect.CUSTOM_PERFECT_CREATION_ENABLED stays False.

DATAPACKAGE STABILITY. Every name registers unconditionally. Approved in the
0.3.0 minting register (ruled 2026-10-13 22:02 CEST).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from typing import List

from . import destinations
from .cortex_vortex_track import RELIC_PERFECT_RESERVED_CODE
from .custom_check_namespace import (CUSTOM_SLOT_COUNT, RELIC_TIERS, custom_check_code,
                                     custom_check_name)
from .location_class import LocationClass
from .podium import SLOT_ORDER

#: Live 0.2.x race family v1 covers slots 1..32.
RACE_V1_SLOT_COUNT = destinations.CUSTOM_TRACK_SLOT_COUNT
RACE_V2_CODE_BASE = 35019000
RACE_V2_STRIDE = 1 + len(SLOT_ORDER)
CUSTOM_WUMPA_CODE_BASE = 35016600
CUSTOM_BOX_CODE_BASE = 35017000
CUSTOM_BOXES_PER_SLOT = 15
CORTEX_VORTEX_PERFECT_CODE = RELIC_PERFECT_RESERVED_CODE
assert CORTEX_VORTEX_PERFECT_CODE == 35026005
assert RACE_V2_STRIDE == 6 and RACE_V1_SLOT_COUNT == 32

_RUNG_SUFFIX = {
    "held_1st": "Held 1st",
    "held_3rd": "Held 3rd",
    "held_5th": "Held 5th",
    "finish_podium": "Finish on Podium",
    "finish_any": "Finish (Any Position)",
}
assert list(_RUNG_SUFFIX) == list(SLOT_ORDER)


def _slot(slot: int) -> str:
    return destinations.custom_slot_region(slot)


def _slots():
    return range(1, CUSTOM_SLOT_COUNT + 1)


class CustomRelicLocationClass(LocationClass):
    """Relic Race Perfect and the three Time Trial tiers for generic slots,
    plus Cortex Vortex's perfect."""
    key = "custom_relic"
    display_name = "Custom Track Relic Checks"
    code_blocks = (35022000, 35024000, 35026000)

    def all_locations(self):
        out = [(f"{destinations.CORTEX_VORTEX}: Relic Race Perfect", CORTEX_VORTEX_PERFECT_CODE,
                destinations.CORTEX_VORTEX)]
        out += [(custom_check_name("perfect_location", slot),
                 custom_check_code("perfect_location", slot), _slot(slot)) for slot in _slots()]
        out += [(custom_check_name("relic_location", slot, tier),
                 custom_check_code("relic_location", slot, tier), _slot(slot))
                for slot in _slots() for tier in range(len(RELIC_TIERS))]
        return out

    def created_location_names(self, options) -> List[str]:
        return []


class CustomRaceV2LocationClass(LocationClass):
    """Trophy Race and the five podium rungs for generic slots 33..132."""
    key = "custom_track_race_v2"
    display_name = "Custom Track Race Checks (slots 33 to 132)"
    code_blocks = (35019000,)

    @staticmethod
    def code(slot: int, rung_index: int = 0) -> int:
        return RACE_V2_CODE_BASE + RACE_V2_STRIDE * (slot - 1) + rung_index

    def all_locations(self):
        out = []
        for slot in range(RACE_V1_SLOT_COUNT + 1, CUSTOM_SLOT_COUNT + 1):
            out.append((f"{_slot(slot)}: Trophy Race", self.code(slot), _slot(slot)))
            out += [(f"{_slot(slot)}: {_RUNG_SUFFIX[key]}", self.code(slot, i + 1), _slot(slot))
                    for i, key in enumerate(SLOT_ORDER)]
        return out

    def created_location_names(self, options) -> List[str]:
        return []


class CustomWumpaLocationClass(LocationClass):
    """Slot-owned `Custom Track N: Reach 10 Wumpa`."""
    key = "custom_wumpa"
    display_name = "Custom Track Wumpa Checks"
    code_blocks = (35016000,)

    def all_locations(self):
        return [(f"{_slot(slot)}: Reach 10 Wumpa", CUSTOM_WUMPA_CODE_BASE + slot - 1, _slot(slot))
                for slot in _slots()]

    def created_location_names(self, options) -> List[str]:
        return []


class CustomItemBoxLocationClass(LocationClass):
    """`Custom Track N: Item Box M`, 15 per slot."""
    key = "custom_item_boxes"
    display_name = "Custom Track Item Box Checks"
    code_blocks = (35017000, 35018000)

    def all_locations(self):
        return [(f"{_slot(slot)}: Item Box {box}",
                 CUSTOM_BOX_CODE_BASE + CUSTOM_BOXES_PER_SLOT * (slot - 1) + box - 1, _slot(slot))
                for slot in _slots() for box in range(1, CUSTOM_BOXES_PER_SLOT + 1)]

    def created_location_names(self, options) -> List[str]:
        return []


CUSTOM_RELIC_CLASS = CustomRelicLocationClass()
CUSTOM_RACE_V2_CLASS = CustomRaceV2LocationClass()
CUSTOM_WUMPA_CLASS = CustomWumpaLocationClass()
CUSTOM_ITEM_BOX_CLASS = CustomItemBoxLocationClass()
