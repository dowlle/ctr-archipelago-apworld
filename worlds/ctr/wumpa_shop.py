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
the ordinary retail trophy tracks this seed keeps (`track_finish_t`, the same
finish term every race check uses). Every retail track has fruit crates, so a
finish there always banks. Custom tracks, trial tracks and Cortex Vortex add
no income route in logic (native still banks there): fewer routes only makes
logic stricter. A shop slot needs its hub region and `Wumpa Income`; the
goal arm needs `Wumpa Income`. Prices and shelf unlocks cost time, not
items, so they are not in logic (design 2026-10-13, "Generation and logic").

PLACEMENT. The first `initial_shelves(n)` slots of each hub are on sale from
the start; only they may hold progression, and a slot holding progression is
priced at its hub's lowest band price after fill. Later slots open at a
lifetime banked total and take useful items or filler. `excluded` makes
every slot EXCLUDED. Shop slots never count as starting checks
(`sphere0_guard`).

DATAPACKAGE STABILITY. `35028600 + 40 * hub + (n - 1)`, hub order N. Sanity
Beach, Gem Stone Valley, Lost Ruins, Glacier Park, Citadel City, inside the
reservation 35028600..35028799. Each hub keeps its 15 unused codes (n 26..40)
unminted for growth. Every name registers unconditionally. Approved in the
0.3.0 minting register (Wumpa Shop row, second minting pass).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from random import Random
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
        n = shop_slots(options)
        return [shop_name(hub, k) for hub in SHOP_HUBS for k in range(1, n + 1)]


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
WUMPA_INCOME_REGION = "Wumpa Income"
SHOP_BLOCK_VERSION = 1
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


def banking_active(options) -> bool:
    """Native banks fruit when the shop or the Wumpa goal is on."""
    return shop_slots(options) > 0 or goal_wumpa(options) > 0


def initial_shelves(slots: int) -> int:
    """Slots on sale from the start: the first half, rounded up, and at least
    two (design review 2026-10-16)."""
    return min(slots, max(2, (slots + 1) // 2))


def _scale(value: int, percent: int) -> int:
    return max(1, (value * percent + 50) // 100)


def price_band(hub: str, percent: int) -> Tuple[int, int]:
    low, high = PRICE_BANDS[hub]
    return _scale(low, percent), _scale(high, percent)


def restricted_slot_count(options) -> int:
    """Shop slots that cannot hold progression: every slot with `excluded`,
    else the later shelves. The rung sizer leaves them out of its supply,
    because each takes only the filler its own location adds."""
    slots = shop_slots(options)
    per_hub = slots if _value(options, "wumpa_shop_progression", 0) == 1 \
        else slots - initial_shelves(slots)
    return len(SHOP_HUBS) * per_hub


def unlock_banked(slot: int, slots: int, percent: int) -> int:
    """Lifetime banked fruit that puts `slot` on sale (0 = from the start)."""
    later = slot - initial_shelves(slots)
    return 0 if later <= 0 else _scale(UNLOCK_STEP * later, percent)


def income_tracks(world) -> List[str]:
    """Retail trophy tracks this seed keeps whose finish banks fruit."""
    from . import cortex_vortex_track
    from .wumpa_checks import WUMPA_ALWAYS_RACEABLE_TRACKS
    dropped = cortex_vortex_track.dropped_track(world.options)
    return [t for t in WUMPA_ALWAYS_RACEABLE_TRACKS if t != dropped]


# ── generation ──────────────────────────────────────────────────────────────

def create_locations(world, regions: list, region_lookup: dict) -> None:
    """Create the `Wumpa Income` event and this seed's shop slots. Draws one
    random value only when the shop is on, so a seed with the shop off keeps
    its random stream."""
    from BaseClasses import Entrance, Location, LocationProgressType, Region
    from .Locations import create_location
    o, player, mw = world.options, world.player, world.multiworld
    world.ctr_wumpa_shop_base_prices = {}
    if not banking_active(o):
        return
    income = Region(WUMPA_INCOME_REGION, player, mw)
    income.type = "wumpa_income"
    mw.regions.append(income)
    regions.append(income)
    region_lookup[income.name] = income
    world.ctr_wumpa_income_entrances = []
    for track in income_tracks(world):
        source = region_lookup.get(track)
        if source is None:
            continue
        ent = Entrance(player=player, name=f"{track} -> {WUMPA_INCOME_REGION}",
                       parent=source)
        ent.access_rule_text = "True"
        ent.connect(income)
        source.exits.append(ent)
        mw.regions.entrance_cache[player][ent.name] = ent
        world.ctr_wumpa_income_entrances.append((track, ent.name))
    if not world.ctr_wumpa_income_entrances:
        from Options import OptionError
        raise OptionError("CTR: the Wumpa Shop and the Wumpa goal need a retail "
                          "race to bank fruit, and this seed keeps none.")
    event = Location(player, WUMPA_INCOME, None, income)
    event.logic_text = "True"
    event.place_locked_item(world.create_event(WUMPA_INCOME))
    income.locations.append(event)
    mw.regions.location_cache[player][WUMPA_INCOME] = event

    slots = shop_slots(o)
    if not slots:
        return
    rng = Random(world.random.getrandbits(64))
    excluded = _value(o, "wumpa_shop_progression", 0) == 1
    first = initial_shelves(slots)
    for hub in SHOP_HUBS:
        region = region_lookup[hub]
        low, high = PRICE_BANDS[hub]
        for n in range(1, slots + 1):
            name = shop_name(hub, n)
            loc = create_location(player, name, region)
            loc.type = LOCATION_TYPE
            loc.logic_text = "True"
            if excluded:
                loc.progress_type = LocationProgressType.EXCLUDED
            elif n > first:
                loc.item_rule = lambda item: not item.advancement
            region.locations.append(loc)
            mw.regions.location_cache[player][name] = loc
            world.ctr_wumpa_shop_base_prices[name] = rng.randint(low, high)


def install_rules(world, player: int) -> None:
    """Income routes take the track's finish term; shop slots need income."""
    from .logic_terms import Has, and_term
    from .usf_finish import track_finish_t
    mw = world.multiworld
    for track, name in getattr(world, "ctr_wumpa_income_entrances", ()):
        and_term(mw.get_entrance(name, player), track_finish_t(track, world))
    for name in getattr(world, "ctr_wumpa_shop_base_prices", {}):
        and_term(mw.get_location(name, player), Has(WUMPA_INCOME, 1, player))


def goal_term(world):
    """The goal arm's logic: fruit can be banked at all. The amount is time."""
    from .logic_terms import Has
    return Has(WUMPA_INCOME, 1, world.player)


def slot_price(world, name: str) -> int:
    """Final price: the drawn band price scaled, or the hub's lowest price
    when the slot holds progression after fill."""
    hub = name.split(" Shop: Slot ")[0]
    percent = _value(world.options, "wumpa_shop_prices", 100)
    loc = world.multiworld.get_location(name, world.player)
    if loc.item is not None and loc.item.advancement:
        return price_band(hub, percent)[0]
    return _scale(world.ctr_wumpa_shop_base_prices[name], percent)


def options_to_wire(options) -> Dict[str, object]:
    """The five `ctr_options` keys, emitted when banking is on."""
    return {"wumpa_shop_slots": shop_slots(options),
            "wumpa_shop_prices": _value(options, "wumpa_shop_prices", 100),
            "wumpa_shop_progression": _value(options, "wumpa_shop_progression", 0),
            "wumpa_shop_hints": bool(_value(options, "wumpa_shop_hints", 1)),
            "goal_wumpa": goal_wumpa(options)}


def block_from(slots: int, percent: int, price_of) -> Dict[str, object]:
    """The `wumpa_shop` block for `slots` per hub; `price_of(name)` gives each
    slot's final price. Pure, so the shared wire fixture can pin it."""
    return {"version": SHOP_BLOCK_VERSION, "hubs": [
        {"level": SHOP_LEVEL_IDS[hub],
         "slots": [{"code": shop_code(hub, n),
                    "price": price_of(shop_name(hub, n)),
                    "unlock_banked": unlock_banked(n, slots, percent)}
                   for n in range(1, slots + 1)]}
        for hub in SHOP_HUBS]}


def wire_block(world) -> Dict[str, object]:
    """The `wumpa_shop` slot_data block (emitted when slots > 0)."""
    o = world.options
    return block_from(shop_slots(o), _value(o, "wumpa_shop_prices", 100),
                      lambda name: slot_price(world, name))


def restore_options(options, wire: Dict[str, object]) -> None:
    """Universal Tracker: the seed's five values. A wire without them is a
    seed with banking off, whatever the tracking player's YAML says. Prices
    and shelf unlocks are not in logic, so the block itself is not needed."""
    co = wire.get("ctr_options", {}) or {}
    for key, fallback in (("wumpa_shop_slots", 0), ("wumpa_shop_prices", 100),
                          ("wumpa_shop_progression", 0), ("wumpa_shop_hints", 1),
                          ("goal_wumpa", 0)):
        value = co.get(key, fallback)
        option = getattr(options, key)
        option.value = int(value) if type(value) in (int, bool) else fallback


def disable_for_content_plan(world, refuse: bool) -> None:
    """Content plans own their checks and goal, and have no shop or Wumpa
    goal record yet. A Wumpa goal there is refused; the shop count, which
    defaults on, is set to 0 so the plan path is unchanged."""
    o = world.options
    if refuse and goal_wumpa(o) > 0:
        from Options import OptionError
        raise OptionError("CTR: goal_wumpa is not supported with a content_pool "
                          "yet; set goal_wumpa to 0.")
    o.goal_wumpa.value = 0
    o.wumpa_shop_slots.value = 0
