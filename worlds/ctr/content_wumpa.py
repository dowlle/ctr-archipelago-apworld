"""The Wumpa Shop and the Wumpa goal on content plans (job J11, decisions 3,
19, 20, 22 and 24 of 2026-10-28).

The ordinary room's shop and goal (wumpa_shop.py) carried over to the
content plan as plan data. Both are absent when off, so a plan with
`wumpa_shop_slots: 0` and `goal_wumpa: 0` keeps its wire byte for byte.

SHOP. With `wumpa_shop_slots` N above 0 the plan has the record
`wumpa_shop: {slots, prices, progression, hints}` (feature `wumpa_shop_v1`)
and 5 x N checks, appended after every other check family, hub order N.
Sanity Beach, Gem Stone Valley, Lost Ruins, Glacier Park, Citadel City, slot
order 1..N. Each is the frozen `<Hub> Shop: Slot <n>` location
(wumpa_shop.shop_code), owned by `hub:<level id>`, kind `wumpa_shop`, no
route (no pad pays it), with its final `price` and its `unlock_banked`
(wumpa_shop.unlock_banked). The price is the ordinary one: a band price
drawn at generation and scaled by `prices`, or the band bottom when the slot
holds progression after fill; it is written when slot_data is built
(`final_prices`). There is no top-level `wumpa_shop` block and no new
envelope key: native builds its shop from the plan.

LOGIC. A shop slot needs its hub's Key floor (`KEY_FLOORS`) and `Wumpa
Income`. On a content plan `Wumpa Income` is reached by any route of a track
entry on a normal pad whose track is a retail race track 0..15, in a Trophy
Race or CTR Challenge the entry has, with that route's pad gates (entrance,
stage 1, the mode's stage-2 gate, racer lock) and the track's finish rank (the
rank a Finish (Any Position) rung carries there). Custom tracks, Cortex
Vortex, cup legs, arenas and boss races bank natively but add no income
route: stricter, never looser, as on the ordinary room. `excluded` keeps
progression out of every shop slot with an item rule (useful, filler and
traps may go there), and the plan refuses when its non-progression supply
(filler and traps, and the always-useful pack items) is below 5 x N.

GOAL. With `goal_wumpa` G above 0 the goal gains `{"op": "wumpa_banked",
"count": G}` (feature `wumpa_goal_v1`), the last arm of the AND. Its logic is
`Wumpa Income`. N. Oxide's garage waits for the target natively (decision
19), so both Oxide encounters also need `Wumpa Income` in apworld logic.
"""
from random import Random

from Options import OptionError

from . import logic_terms, wumpa_shop

SHOP_FEATURE = "wumpa_shop_v1"
GOAL_FEATURE = "wumpa_goal_v1"
KIND = wumpa_shop.LOCATION_TYPE
GOAL_OP = "wumpa_banked"
GOAL_MAX = 5000
RECORD_KEYS = ("slots", "prices", "progression", "hints")
PROGRESSION = ("allowed", "excluded")
PRICES_MIN, PRICES_MAX = 25, 400
#: Key floor of each hub's shop (the hub's own Key gate).
KEY_FLOORS = {"N. Sanity Beach": 0, "Gem Stone Valley": 1, "Lost Ruins": 1,
              "Glacier Park": 2, "Citadel City": 3}
KEY_ITEM = 35010014
#: Retail race tracks (engine ids 0..15) bank fruit in logic.
INCOME_RETAIL_MAX = 15
INCOME_MODES = ("trophy", "ctr")
INCOME = wumpa_shop.WUMPA_INCOME


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options):
    """The plan's `wumpa_shop` record, or None with the shop off. No draw."""
    slots = wumpa_shop.shop_slots(options)
    if not slots:
        return None
    return dict(slots=slots, prices=int(options.wumpa_shop_prices.value),
                progression=PROGRESSION[1 if wumpa_shop.progression_excluded(options) else 0],
                hints=bool(options.wumpa_shop_hints.value))


def check_settings(record):
    """Shape and values of a plan's `wumpa_shop` record."""
    if not isinstance(record, dict) or set(record) != set(RECORD_KEYS):
        error("wumpa_shop must be a mapping of exactly " + ", ".join(RECORD_KEYS) + ".")
    if type(record["slots"]) is not int or not 1 <= record["slots"] <= wumpa_shop.SHOP_SLOTS_PER_HUB:
        error(f"wumpa_shop.slots must be 1 to {wumpa_shop.SHOP_SLOTS_PER_HUB}.")
    if type(record["prices"]) is not int or not PRICES_MIN <= record["prices"] <= PRICES_MAX:
        error(f"wumpa_shop.prices must be {PRICES_MIN} to {PRICES_MAX}.")
    if record["progression"] not in PROGRESSION:
        error("wumpa_shop.progression must be allowed or excluded.")
    if type(record["hints"]) is not bool:
        error("wumpa_shop.hints must be true or false.")
    return record


def check_count(record):
    return len(wumpa_shop.SHOP_HUBS) * record["slots"] if record else 0


def slots(record):
    """[(hub, n, code, name)] of a record's slots, in wire order."""
    return [(hub, n, wumpa_shop.shop_code(hub, n), wumpa_shop.shop_name(hub, n))
            for hub in wumpa_shop.SHOP_HUBS for n in range(1, record["slots"] + 1)]


def check(record, hub, n, price):
    return dict(location=wumpa_shop.shop_code(hub, n), owner=f"hub:{wumpa_shop.SHOP_LEVEL_IDS[hub]}", kind=KIND,
                display_name=wumpa_shop.shop_name(hub, n), routes=[], price=price,
                unlock_banked=wumpa_shop.unlock_banked(n, record["slots"], record["prices"]))


def draw_prices(world, record):
    """{slot name: drawn band price before scaling}: one world.random draw
    seeding the per-slot band draws, as the ordinary room does. Only called
    with the shop on."""
    rng = Random(world.random.getrandbits(64))
    out = {}
    for hub, _n, _code, name in slots(record):
        low, high = wumpa_shop.PRICE_BANDS[hub]
        out[name] = rng.randint(low, high)
    return out


def checks(record, base_prices):
    """The shop checks with their prices before fill (the drawn price scaled)."""
    if not record:
        return []
    return [check(record, hub, n, wumpa_shop._scale(base_prices[name], record["prices"]))
            for hub, n, _code, name in slots(record)]


def final_prices(world, plan):
    """Write each shop check's final price once the fill has placed its item:
    the band bottom for progression, else the drawn price scaled
    (wumpa_shop.slot_price)."""
    record = plan.get("wumpa_shop")
    if not record:
        return
    by_code = {c["location"]: c for c in plan["checks"]}
    base = getattr(world, "ctr_wumpa_shop_base_prices", None) or {}
    for hub, _n, code, name in slots(record):
        if name not in base:
            continue  # Universal Tracker: the room's prices stand.
        location = world.multiworld.get_location(name, world.player)
        if location.item is not None and location.item.advancement:
            price = wumpa_shop.price_band(hub, record["prices"])[0]
        else:
            price = wumpa_shop._scale(base[name], record["prices"])
        by_code[code]["price"] = price


def expected_checks(plan, record):
    """The shop checks a record allows, taking each price from the plan after
    checking it lies in its hub's scaled band (the draw is not recomputed)."""
    by_code = {c["location"]: c for c in plan["checks"] if isinstance(c, dict)}
    out = []
    for hub, n, code, _name in slots(record):
        price = by_code.get(code, {}).get("price")
        low, high = wumpa_shop.price_band(hub, record["prices"])
        if type(price) is not int or price not in attainable_prices(hub, record["prices"]):
            error(f"{wumpa_shop.shop_name(hub, n)}: price is not a scaled price of its hub's band {low} to {high}")
        out.append(check(record, hub, n, price))
    return out


def attainable_prices(hub, percent):
    """Every price the draw can give a slot of `hub`: each whole band price
    scaled by `wumpa_shop_prices` (the band bottom, the progression price,
    included). Native recomputes the same set (J11 review round 1)."""
    low, high = wumpa_shop.PRICE_BANDS[hub]
    return {wumpa_shop._scale(value, percent) for value in range(low, high + 1)}


def non_progression_codes():
    """Ledger item codes that are never progression on a content plan: the
    pool-only pack items and the surface items (all `useful`)."""
    from .content_item_pool import ITEMS, SURFACE_NAMES
    from .content_plan import PACK_ITEMS, pack_code
    return {pack_code(name) for _key, name in PACK_ITEMS} | {ITEMS[name] for name in SURFACE_NAMES}


def non_progression_supply(items):
    """Copies in a plan's item ledger (`items` wire record) that can never be
    progression: filler and traps, and the pack items in the pool."""
    codes = non_progression_codes()
    return items["filler_count"] + sum(row["remaining"] for row in items["rows"] if row["item"] in codes)


def check_supply(record, items, reserved=0):
    """`excluded` needs one non-progression copy per shop slot, on top of the
    `reserved` filler copies other checks already claim (the excluded Oxide
    goal check holds one; J11 review round 1)."""
    if not record or record["progression"] != "excluded":
        return
    need = check_count(record) + reserved
    have = non_progression_supply(items)
    if have < need:
        error(f"wumpa_shop_progression: excluded keeps progression out of all {need} shop slots, but the item "
              f"pool holds only {have} filler, trap and other non-progression copies"
              + (f" and one of them is kept for the Oxide goal check." if reserved else ".") + f" Lower wumpa_shop_slots, "
              "add filler (lower an item_pool count or add content) or set wumpa_shop_progression: allowed. "
              "Your settings were not changed.")


def goal_count(options):
    return wumpa_shop.goal_wumpa(options)


def goal_term(count):
    return dict(op=GOAL_OP, count=count)


def goal_arm(goal):
    """The `wumpa_banked` arm of a plan goal, or None."""
    if goal.get("op") == GOAL_OP:
        return goal
    if goal.get("op") == "all":
        found = [t for t in goal.get("terms", ()) if isinstance(t, dict) and t.get("op") == GOAL_OP]
        return found[0] if len(found) == 1 else None
    return None


def banking(plan):
    """Does the plan bank fruit (shop or Wumpa goal)?"""
    return bool(plan.get("wumpa_shop")) or goal_arm(plan["goal"]) is not None


def income_routes(plan):
    """[(entry id, pad id, mode, track)] of every route that banks fruit in
    logic: a Trophy Race or CTR Challenge of a track entry on a normal pad
    whose track is a retail race track 0..15, in physical pad order, then mode
    order."""
    tracks = {t["id"]: t for t in plan["tracks"]}
    pad_of = {p["entry_id"]: p for p in plan["pads"] if p["kind"] == "normal" and p["entry_id"] is not None}
    out = []
    for entry in plan["entries"]:
        if entry.get("kind") != "track" or entry["id"] not in pad_of:
            continue
        track = tracks.get(entry["track_id"])
        if not track or track.get("origin") != "retail" or not 0 <= track.get("retail_id", -1) <= INCOME_RETAIL_MAX:
            continue
        pad = pad_of[entry["id"]]
        out.extend((entry["id"], pad["id"], mode, track) for mode in INCOME_MODES if mode in entry["modes"])
    return sorted(out, key=lambda r: (int(r[1].split(":")[1]), INCOME_MODES.index(r[2])))


def check_income(plan):
    if banking(plan) and not income_routes(plan):
        error("the Wumpa Shop and the Wumpa goal need a Trophy Race or CTR Challenge on a retail race track "
              "(engine ids 0 to 15) on a pad to bank fruit, and this plan has none. Select retail tracks with "
              "the trophy or ctr mode, or turn the shop and the Wumpa goal off. No content was changed.")


def income_term(world):
    """What `Wumpa Income` stands for, for the `win_logic` export: any income
    route, with its pad's gate, as `install` built them."""
    return world.ctr_income_term


def install(world, plan, menu, stage_gate, stage_term):
    """The `Wumpa Income` event (in Menu, any income route) and the shop
    locations (in Menu, the hub's Key floor and `Wumpa Income`), with the
    `excluded` item rule. `stage_gate(route)` gives the test of a route's
    later race, or None for a pad's first race; `stage_term` its term."""
    if not banking(plan):
        return
    from BaseClasses import Location
    from .content_capability import finish_boost
    from .content_plan import LOCATION_BY_CODE
    from . import characters
    from .progressive_capability import gate_satisfied
    player = world.player
    capability = plan.get("capability", {})
    pads = {p["id"]: p for p in plan["pads"]}
    routes = []
    wires = []
    for entry_id, pad_id, mode, track in income_routes(plan):
        route = dict(own_pad_id=pad_id, mode=mode)
        test = stage_gate(route)
        lock = pads[pad_id]["racer_lock"]
        racer = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        need = finish_boost(track, capability) if capability.get("boost_mode") else 0
        routes.append((entry_id, test, need, racer))
        terms = [logic_terms.term_of(world.multiworld.get_region(entry_id, player).entrances[0])]
        stage = stage_term(route)
        if stage is not None:
            terms.append(stage)
        if need:
            terms.append(logic_terms.Cap(world, need, racer))
        wires.append(logic_terms.all_of(*terms))
    routes = tuple(routes)
    world.ctr_income_term = wires[0] if len(wires) == 1 else logic_terms.Or(*wires)

    def income(state):
        return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                   and (not need or gate_satisfied(world, state, player, boost_min=need, required_character=racer))
                   for entry, test, need, racer in routes)
    event = Location(player, INCOME, None, menu)
    event.access_rule = income
    event.place_locked_item(world.create_event(INCOME))
    menu.locations.append(event)
    record = plan.get("wumpa_shop")
    if not record:
        return
    excluded = record["progression"] == "excluded"
    from .content_plan import ITEM_BY_CODE
    key = ITEM_BY_CODE[KEY_ITEM]
    for hub, _n, code, name in slots(record):
        location = Location(player, LOCATION_BY_CODE[code], code, menu)
        location.type = KIND
        floor = KEY_FLOORS[hub]
        location.access_rule = (lambda state, floor=floor: state.has(INCOME, player)
                                and (not floor or state.has(key, player, floor)))
        if excluded:
            location.item_rule = lambda item: not item.advancement
        menu.locations.append(location)


def restore_options(world, plan):
    """Universal Tracker: the five options from the plan."""
    o = world.options
    record = plan.get("wumpa_shop")
    arm = goal_arm(plan["goal"])
    o.wumpa_shop_slots.value = record["slots"] if record else 0
    o.wumpa_shop_prices.value = record["prices"] if record else 100
    o.wumpa_shop_progression.value = PROGRESSION.index(record["progression"]) if record else 0
    o.wumpa_shop_hints.value = int(record["hints"]) if record else 1
    o.goal_wumpa.value = arm["count"] if arm else 0
    world.ctr_wumpa_shop_base_prices = {}
