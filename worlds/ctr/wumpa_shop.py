"""The Wumpa Shop (#249): five hub shops whose slots are checks, the banked
Wumpa goal arm and the `Wumpa Income` event both depend on.

WHAT THIS CHECKS. `<Hub> Shop: Slot <n>`: buying shelf n of the Wumpa Shop on
that hub's save screen. Five hubs, n 1..25 decimal and unpadded (the approved
25-slot cap; 10 per hub is the planned option default). A server-Collected slot
is SOLD without a charge. `Wumpa Income` is an address-free event, not minted.

WHO OWNS THE SEMANTICS. The apworld owns names, codes, the per-seed subset
(`wumpa_shop_slots` per hub), prices, shelf unlocks, placement limits and the
`wumpa_shop` slot_data block; native owns banking, the wallet, the purchase
and its DataStorage records.

LOGIC. Fruit can be earned again by replaying a race, so logic models it as
one code-free event, `Wumpa Income`, reached by finishing a race on any of
the ordinary retail trophy tracks this seed keeps (the USF finish term on USF
tracks, as the race checks use it). Every retail track has fruit crates, so a
finish there always banks. Custom tracks, trial tracks and Cortex Vortex add
no income route in logic (native still banks there): fewer routes only makes
logic stricter. A shop slot needs its hub region and `Wumpa Income`; the
goal arm needs `Wumpa Income`. Prices and shelf unlocks cost time, not
items, so they are not in logic (design 2026-10-13, "Generation and logic").

PLACEMENT. The first `initial_shelves(n)` slots of each hub are on sale from
the start; later slots open at a lifetime banked total. With `allowed` any
slot may hold any item, progression and traps included (ruled 2026-10-28,
decisions 24 and 25); a slot holding progression is priced at its hub's
lowest band price after fill. `excluded` keeps progression out of every slot
(useful items, filler and traps only). Shop slots never count as starting checks
(`sphere0_guard`).

DATAPACKAGE STABILITY. `35028600 + 40 * hub + (n - 1)`, hub order N. Sanity
Beach, Gem Stone Valley, Lost Ruins, Glacier Park, Citadel City, inside the
reservation 35028600..35028799. Each hub keeps its 15 unused codes (n 26..40)
unminted for growth. Every name registers unconditionally. Approved in the
0.3.0 minting register (Wumpa Shop row, second minting pass).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from typing import Dict, List, Tuple

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


# ── seed data ───────────────────────────────────────────────────────────────
#: Engine level id of each hub, in `SHOP_HUBS` order (`namespace_Level.h`).
SHOP_LEVEL_IDS: Dict[str, int] = {"N. Sanity Beach": 26, "Gem Stone Valley": 25,
                                  "Lost Ruins": 27, "Glacier Park": 28,
                                  "Citadel City": 29}

#: Provisional price bands before `wumpa_shop_prices` (design, "Prices and the
#: fruit economy"). Not measured yet; calibrate before release.
PRICE_BANDS: Dict[str, Tuple[int, int]] = {
    "N. Sanity Beach": (10, 30), "Gem Stone Valley": (20, 45),
    "Lost Ruins": (20, 45), "Glacier Park": (30, 60), "Citadel City": (40, 80)}

#: Lifetime banked fruit per later shelf before scaling: the first later
#: shelf opens at 50, the next at 100, and so on. Provisional like the bands.
UNLOCK_STEP = 50

WUMPA_INCOME = "Wumpa Income"
LOCATION_TYPE = "wumpa_shop"


def _value(options, key: str, fallback: int) -> int:
    """An option's value, read defensively: the location-class tests drive
    classes with stand-in option objects that carry only the options under
    test, and an absent option answers off."""
    option = getattr(options, key, None)
    if option is None:
        return fallback
    try:
        return int(option.value)
    except (AttributeError, TypeError, ValueError):
        return fallback


def shop_slots(options) -> int:
    n = _value(options, "wumpa_shop_slots", 0)
    return n if 0 <= n <= SHOP_SLOTS_PER_HUB else 0


def goal_wumpa(options) -> int:
    return max(0, _value(options, "goal_wumpa", 0))


def initial_shelves(slots: int) -> int:
    """Slots on sale from the start: the first half, rounded up, and at least
    two (design review 2026-10-16)."""
    return min(slots, max(2, (slots + 1) // 2))


def _scale(value: int, percent: int) -> int:
    return max(1, (value * percent + 50) // 100)


def price_band(hub: str, percent: int) -> Tuple[int, int]:
    low, high = PRICE_BANDS[hub]
    return _scale(low, percent), _scale(high, percent)


def progression_excluded(options) -> bool:
    return _value(options, "wumpa_shop_progression", 0) == 1


def unlock_banked(slot: int, slots: int, percent: int) -> int:
    """Lifetime banked fruit that puts `slot` on sale (0 = from the start)."""
    later = slot - initial_shelves(slots)
    return 0 if later <= 0 else _scale(UNLOCK_STEP * later, percent)


