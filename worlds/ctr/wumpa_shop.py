"""Wumpa Shop slot names (#249), minted in the 0.3.0 second id step. Names
only; no seed creates them yet.

WHAT THIS CHECKS. `<Hub> Shop: Slot <n>`: buying shelf n of the Wumpa Shop on
that hub's save screen. Five hubs, n 1..25 decimal and unpadded (the approved
25-slot cap; 10 per hub is the planned option default). A server-Collected slot
is SOLD without a charge. `Wumpa Income` is an address-free event, not minted.

WHO OWNS THE SEMANTICS. The apworld owns names, codes and the per-seed subset
(option `wumpa_shop_slots`, not built yet); native owns the purchase and its
DataStorage records. This class returns an empty per-seed subset.

DATAPACKAGE STABILITY. `35028600 + 40 * hub + (n - 1)`, hub order N. Sanity
Beach, Gem Stone Valley, Lost Ruins, Glacier Park, Citadel City, inside the
reservation 35028600..35028799. Each hub keeps its 15 unused codes (n 26..40)
unminted for growth. Every name registers unconditionally. Approved in the
0.3.0 minting register (Wumpa Shop row, second minting pass).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from typing import List, Tuple

from .location_class import LocationClass

SHOP_CODE_BASE = 35028600
SHOP_HUB_STRIDE = 40
SHOP_SLOTS_PER_HUB = 25
#: Hub regions in code order. APPEND ONLY.
SHOP_HUBS: Tuple[str, ...] = ("N. Sanity Beach", "Gem Stone Valley", "Lost Ruins",
                              "Glacier Park", "Citadel City")


def shop_name(hub: str, slot: int) -> str:
    if type(slot) is not int or not 1 <= slot <= SHOP_SLOTS_PER_HUB:
        raise ValueError(f"shop slot must be 1..{SHOP_SLOTS_PER_HUB}")
    return f"{hub} Shop: Slot {slot}"


def shop_code(hub: str, slot: int) -> int:
    shop_name(hub, slot)
    return SHOP_CODE_BASE + SHOP_HUB_STRIDE * SHOP_HUBS.index(hub) + slot - 1


class WumpaShopLocationClass(LocationClass):
    key = "wumpa_shop"
    display_name = "Wumpa Shop Slots"
    code_blocks = (SHOP_CODE_BASE,)

    def all_locations(self):
        return [(shop_name(hub, n), shop_code(hub, n), hub)
                for hub in SHOP_HUBS for n in range(1, SHOP_SLOTS_PER_HUB + 1)]

    def location_name(self, hub: str, slot: int) -> str:
        return shop_name(hub, slot)

    def created_location_names(self, options) -> List[str]:
        return []


WUMPA_SHOP_CLASS = WumpaShopLocationClass()
