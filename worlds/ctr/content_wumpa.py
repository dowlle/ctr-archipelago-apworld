"""The Wumpa Shop and the Wumpa goal on content plans (job J11, decisions 3,
19, 20, 22 and 24 of 2026-10-28).

The ordinary room's shop and goal (wumpa_shop.py) carried over to the
content plan as plan data. Both are absent when off, so a plan with
`wumpa_shop_slots: 0` and `goal_wumpa: 0` keeps its wire byte for byte.

SHOP. With `wumpa_shop_slots` N above 0 the plan has the record
`wumpa_shop: {slots, prices, progression, hints, logic_scale}`
(features `wumpa_shop_v1` and `wumpa_shop_key_tiers_v1`)
and 5 x N checks, appended after every other check family, hub order N.
Sanity Beach, Gem Stone Valley, Lost Ruins, Glacier Park, Citadel City, slot
order 1..N. Each is the frozen `<Hub> Shop: Slot <n>` location
(wumpa_shop.shop_code), owned by `hub:<level id>`, kind `wumpa_shop`, no
route (no pad pays it), with its final `price` and its `unlock_banked`
(wumpa_shop.unlock_banked). The price is a band price drawn at generation and
scaled by `prices`, the same way whatever the slot holds, so the price says
nothing about the item (ruling of 2026-11-02; progression no longer costs the
band bottom). There is no top-level `wumpa_shop` block and no new envelope
key: native builds its shop from the plan.

LOGIC. A shop slot needs its hub's Key floor (`KEY_FLOORS`) and `Wumpa
Income`, plus its price/shelf budget from `key_floor`. Legacy plans without
`logic_scale` keep the original hub-only floor. On a content plan `Wumpa
Income` is reached by any route of a track
entry on a normal pad whose track banks fruit (`income_track`: a retail race
track 0..15, or a custom track whose package has measured Wumpa capability,
ruling of 2026-11-02), in a Trophy Race or CTR Challenge the entry has, with that
route's pad gates (entrance, stage 1, the mode's stage-2 gate, racer lock) and
the track's finish rank (the rank a Finish (Any Position) rung carries there).
Custom tracks call the same `RB_Player_ModifyWumpa` in game. A custom track
without measured Wumpa capability adds no route, also with owned Progressive
Starting Wumpa (that item is useful, not progression, so logic cannot hold
it). Cortex Vortex, cup legs, arenas and boss races bank natively but add no
income route, with one exception: a plan whose normal pads hold no such
Trophy Race or CTR Challenge (every pad a cup or an arena, the 27-cup seed of
0.3.0-alpha3 job A3-7, ruled 2026-11-05) takes every cup leg on an
`income_track` as its income routes instead (`cup_income_routes`). A cup leg
is an Adventure race and banks its fruit at the finish or on leaving, and a
cup pad stays enterable once Done, so the route repeats. It needs the cup
pad's gates and racer lock and the finish rank of every leg up to and
including its own (content_cups.prefix_boost plus the leg's finish, as a
Complete One Lap cup route). A plan with a Trophy or CTR income route keeps
its routes exactly. `keep_income_track` is only the fallback for a draw with
no income route at all. `excluded` keeps
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
LOGIC_FEATURE = "wumpa_shop_key_tiers_v1"
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
#: Retail race tracks (engine ids 0..15) bank fruit in logic, as do custom
#: tracks with measured Wumpa capability (`income_track`).
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
                hints=bool(options.wumpa_shop_hints.value),
                logic_scale=int(options.wumpa_shop_logic_scale.value))


def check_settings(record):
    """Shape and values of a plan's `wumpa_shop` record."""
    if not isinstance(record, dict) or set(record) not in (set(RECORD_KEYS), set(RECORD_KEYS) | {"logic_scale"}):
        error("wumpa_shop must contain " + ", ".join(RECORD_KEYS) + ", optionally logic_scale.")
    if "logic_scale" in record and (type(record["logic_scale"]) is not int or not 25 <= record["logic_scale"] <= 400):
        error("wumpa_shop.logic_scale must be 25 to 400.")
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


def key_floor(record, hub, check):
    """Shared shop rule for opening placement and the installed AP rules."""
    floor = KEY_FLOORS[hub]
    if "logic_scale" in record:
        floor = max(floor, wumpa_shop.logic_key_floor(check["price"], check["unlock_banked"], record["logic_scale"]))
    return floor


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
    """The shop checks, each with its drawn price scaled."""
    if not record:
        return []
    return [check(record, hub, n, wumpa_shop._scale(base_prices[name], record["prices"]))
            for hub, n, _code, name in slots(record)]


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
    scaled by `wumpa_shop_prices`. Native recomputes the same set (J11 review
    round 1)."""
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


def income_track(track, package=None):
    """Does a pad race on this track bank fruit in logic: a retail race track
    0..15, or a custom track whose package has measured Wumpa capability
    (ruling of 2026-11-02)."""
    if track.get("origin") == "retail":
        return 0 <= track.get("retail_id", -1) <= INCOME_RETAIL_MAX
    return track.get("origin") == "custom" and bool(package and package["capabilities"].get("wumpa"))


def income_package(plan, track):
    """The package of an income route's track, or None for a retail track."""
    return next((p for p in plan["packages"] if p["id"] == track.get("package_id")), None)


def income_routes(plan):
    """[(entry id, pad id, mode, track)] of every route that banks fruit in
    logic: a Trophy Race or CTR Challenge of a track entry on a normal pad
    whose track banks fruit (`income_track`), in physical pad order, then mode
    order."""
    tracks = {t["id"]: t for t in plan["tracks"]}
    packages = {p["id"]: p for p in plan["packages"]}
    pad_of = {p["entry_id"]: p for p in plan["pads"] if p["kind"] == "normal" and p["entry_id"] is not None}
    out = []
    for entry in plan["entries"]:
        if entry.get("kind") != "track" or entry["id"] not in pad_of:
            continue
        track = tracks.get(entry["track_id"])
        if not track or not income_track(track, packages.get(track.get("package_id"))):
            continue
        pad = pad_of[entry["id"]]
        out.extend((entry["id"], pad["id"], mode, track) for mode in INCOME_MODES if mode in entry["modes"])
    return sorted(out, key=lambda r: (int(r[1].split(":")[1]), INCOME_MODES.index(r[2])))


def cup_income_routes(plan):
    """[(entry id, pad id, leg id, track)] of every cup leg that banks fruit in
    logic, in physical pad order, then leg order: the income routes of a plan
    with no Trophy or CTR income route (`income_routes` empty), and none
    otherwise. A leg banks when its track is an `income_track`."""
    if income_routes(plan):
        return []
    from .content_cups import KIND as CUP_KIND
    tracks = {t["id"]: t for t in plan["tracks"]}
    packages = {p["id"]: p for p in plan["packages"]}
    pad_of = {p["entry_id"]: p for p in plan["pads"] if p["kind"] == "normal" and p["entry_id"] is not None}
    out = []
    for entry in plan["entries"]:
        if entry.get("kind") != CUP_KIND or entry["id"] not in pad_of:
            continue
        pad = pad_of[entry["id"]]
        for leg in entry["legs"]:
            track = tracks[leg["track_id"]]
            if income_track(track, packages.get(track.get("package_id"))):
                out.append((int(pad["id"].split(":")[1]), entry["id"], pad["id"], leg["id"], track))
    return [r[1:] for r in sorted(out, key=lambda r: r[0])]


def cup_income_need(plan, entry_id, leg_id):
    """The rank a cup income route needs: the finish of every leg up to and
    including its own. 0 without boost."""
    from .content_capability import finish_boost
    from .content_cups import prefix_boost
    capability = plan.get("capability", {})
    if not capability.get("boost_mode"):
        return 0
    tracks = {t["id"]: t for t in plan["tracks"]}
    packages = {p["id"]: p for p in plan["packages"]}
    entry = next(e for e in plan["entries"] if e["id"] == entry_id)
    track = tracks[next(leg["track_id"] for leg in entry["legs"] if leg["id"] == leg_id)]
    return max(prefix_boost(entry, leg_id, tracks, capability, packages),
               finish_boost(track, capability, packages.get(track.get("package_id"))))


def keep_income_track(world, chosen, drawn, optional, packages=None):
    """The tracks drawn for the pads, with one swapped for a track that can bank
    fruit when the shop or the Wumpa goal needs one and the draw left none. A long
    `custom_tracks` list of tracks without measured Wumpa capability leaves that to
    chance on a seed check_income then refuses, so a seed that had one draws as
    before and no draw is ever refused for this. Only the fallback: a custom track
    with measured Wumpa capability is an income route itself (ruling of 2026-11-02).
    `packages` maps package id to package."""
    o = world.options
    packages = packages or {}
    if not (o.wumpa_shop_slots.value or goal_count(o)) or not drawn or any(earns_income(t, packages) for t in chosen):
        return drawn
    spare = [t for t in optional if earns_income(t, packages) and t not in drawn]
    if not spare:
        return drawn
    kept = list(drawn)
    kept[world.random.randrange(len(kept))] = world.random.choice(spare)
    return kept


def earns_income(track, packages):
    """Does a drawn track give an income route: `income_track` with a Trophy
    Race or CTR Challenge among its modes. `packages` maps package id to
    package."""
    return (income_track(track, packages.get(track.get("package_id")))
            and any(mode in track.get("modes", ()) for mode in INCOME_MODES))


def check_income(plan):
    if banking(plan) and not income_routes(plan) and not cup_income_routes(plan):
        error("the Wumpa Shop and the Wumpa goal need a Trophy Race, CTR Challenge or cup race on a pad to bank "
              "fruit, on a retail race track (engine ids 0 to 15) or a custom track with measured Wumpa capability, "
              "and this plan has none. Select such tracks with the trophy or ctr mode or in a cup, or turn the shop "
              "and the Wumpa goal off. No content was changed.")


def income_term(world):
    """What `Wumpa Income` stands for, for the `win_logic` export: any income
    route, with its pad's gate, as `install` built them. The event's own term
    is checked on every seed, so a foreign wrapper on it refuses the export
    (A3-37b review). Without Pad Approach Hints the wire stays
    `ctr_income_term`, as before; the event's term wires the same routes."""
    event = world.ctr_income_event
    term = logic_terms.term_of(event)
    if term is None:
        from .win_logic import _unexportable
        raise _unexportable(world, event, "CTR win_logic: Wumpa Income has no term-backed rule")
    if bool(world.options.pad_approach_hints.value):
        return term
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
    hints = bool(world.options.pad_approach_hints.value)
    capability = plan.get("capability", {})
    pads = {p["id"]: p for p in plan["pads"]}
    routes = []
    wires = []
    for entry_id, pad_id, mode, track in income_routes(plan):
        route = dict(own_pad_id=pad_id, mode=mode)
        test = stage_gate(route)
        lock = pads[pad_id]["racer_lock"]
        racer = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        need = finish_boost(track, capability, income_package(plan, track)) if capability.get("boost_mode") else 0
        routes.append((entry_id, test, need, racer))
        terms = [logic_terms.ReachRegion(world, entry_id) if hints else
                 logic_terms.term_of(world.multiworld.get_region(entry_id, player).entrances[0])]
        stage = stage_term(route)
        if stage is not None:
            terms.append(stage)
        if need:
            terms.append(logic_terms.Cap(world, need, racer))
        wires.append(logic_terms.all_of(*terms))
    # A plan with no Trophy or CTR income route banks in its cup legs (A3-7):
    # the cup pad's gates and lock, and the finish of every leg up to its own.
    for entry_id, pad_id, leg_id, _track in cup_income_routes(plan):
        lock = pads[pad_id]["racer_lock"]
        racer = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        need = cup_income_need(plan, entry_id, leg_id)
        routes.append((entry_id, None, need, racer))
        terms = [logic_terms.ReachRegion(world, entry_id) if hints else
                 logic_terms.term_of(world.multiworld.get_region(entry_id, player).entrances[0])]
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
    # A3-37b: always term-backed, so every shop slot gets a win_logic row.
    # Win rows keep reading `ctr_income_term` without Pad Approach Hints
    # (income_term), so their wire is unchanged.
    logic_terms.set_term(event, logic_terms.SerializedRule(income, world.ctr_income_term))
    world.ctr_income_event = event
    event.place_locked_item(world.create_event(INCOME))
    menu.locations.append(event)
    record = plan.get("wumpa_shop")
    if not record:
        return
    excluded = record["progression"] == "excluded"
    from .content_plan import ITEM_BY_CODE
    key = ITEM_BY_CODE[KEY_ITEM]
    checks = {c["location"]: c for c in plan["checks"] if c["kind"] == KIND}
    for hub, _n, code, name in slots(record):
        location = Location(player, LOCATION_BY_CODE[code], code, menu)
        location.type = KIND
        floor = key_floor(record, hub, checks[code])
        location.access_rule = (lambda state, floor=floor: state.has(INCOME, player)
                                and (not floor or state.has(key, player, floor)))
        term = logic_terms.EventTerm(INCOME, player, lambda: income_term(world))
        if floor:
            term = logic_terms.And(term, logic_terms.Has(key, floor, player))
        logic_terms.set_term(location, logic_terms.SerializedRule(location.access_rule, term))
        if excluded:
            location.item_rule = lambda item: not item.advancement
        menu.locations.append(location)


def restore_options(world, plan):
    """Universal Tracker: restore options; absent scale retains legacy rules."""
    o = world.options
    record = plan.get("wumpa_shop")
    arm = goal_arm(plan["goal"])
    o.wumpa_shop_slots.value = record["slots"] if record else 0
    o.wumpa_shop_prices.value = record["prices"] if record else 100
    o.wumpa_shop_logic_scale.value = record.get("logic_scale", 100) if record else 100
    o.wumpa_shop_progression.value = PROGRESSION.index(record["progression"]) if record else 0
    o.wumpa_shop_hints.value = int(record["hints"]) if record else 1
    o.goal_wumpa.value = arm["count"] if arm else 0
