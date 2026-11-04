"""Sphere-0 guard: refuse a slot that starts with no reachable check
(fuzz failures 32541, 6813 and 10634, 2026-10-01; refusal ruled the same
evening), and since 2026-10-02 a slot that starts with only one (fuzz
14603; see MIN_STARTING_CHECKS).

WHY THIS EXISTS
---------------
With Progressive Boost randomized and logic difficulty easy or medium, every
Trophy Race on the difficulty-gated tracks needs the first boost rank (or,
with Itemsanity, enough weapon families), and easy also gates Finish on
Podium and Held 1st (`Rules.add_capability_difficulty_rules`, ruling
2026-09-27, #329). When every track the slot can reach at the start is such a
track, and no ungated location class is on (Item Box Locations, held or
any-position rungs), the slot has ZERO locations reachable from its starting
inventory.

AP's fill cannot place the item that opens the first check anywhere in that
slot, because no location of the slot is reachable without it:

- solo, every seed dead-ends and only the rollback backstop rescued it, by
  precollecting whatever the start_inventory panic strands. When that was a
  Gem and the goal was one Gem, the slot started with its goal complete and
  AP's accessibility check raised (fuzz 32541);
- in a room, the opener can only sit in another slot's early checks, so the
  fill fails whenever the other slots are tight too (fuzz 6813, 10634).

Before the 2026-10-01 refusal ruling the rung sizer's working margin forced
three rung categories on every capability-pack seed without Item Box
Locations. Held rungs are not difficulty-gated, so that margin kept sphere 0
non-empty as a side effect. The ruling removed the margin from the refusal
path; this guard refuses exactly the seeds it used to protect that cannot
start. The 2026-10-01 ruling refuses them rather than giving the slot a
starting item.

Runs in `generate_basic`, after every rule exists. Takes no random draw.
"""
from Options import OptionError

from . import content_opening


def _reachable_empty(world, state) -> int:
    """Empty coded locations reachable in `state`. Wumpa Shop slots never
    count: a paid or delayed shelf must not disguise a narrow start (#249,
    design review 2026-10-16: two non-shop starting checks)."""
    from .wumpa_shop import LOCATION_TYPE as SHOP
    return sum(1 for loc in world.multiworld.get_locations(world.player)
               if loc.item is None and loc.address is not None
               and getattr(loc, "type", None) != SHOP
               and loc.can_reach(state))


def _own_item(world, item) -> bool:
    """An item of this slot's opening: its own, or an item link group's copy of an
    item this slot shares. Linked items leave the slot's pool before pre_fill, and
    the group's copy is what the fill places."""
    if item.player == world.player:
        return True
    group = getattr(world.multiworld, "groups", {}).get(item.player)
    return group is not None and world.player in group["players"] and item.name in group["item_pool"]


def _placed(world):
    """Locations whose items count for this slot: its own, and its receipts of the
    item link groups it shares in."""
    mw, player = world.multiworld, world.player
    placed = [loc for loc in mw.get_locations(player) if loc.item is not None]
    for group_id, group in getattr(mw, "groups", {}).items():
        if player in group["players"]:
            placed += [loc for loc in mw.get_locations(group_id) if loc.item is not None and loc.item.player == player]
    return placed


def _base_state(world):
    from BaseClasses import CollectionState
    state = CollectionState(world.multiworld)
    # Locked rewards and goal events are already placed; collect what is
    # reachable of them, since the fill would too.
    state.sweep_for_advancements(locations=_placed(world))
    return state


def sphere0_breadth(world) -> int:
    """Empty locations of this slot reachable from its starting inventory."""
    return _reachable_empty(world, _base_state(world))


def openers(world):
    """Sorted names of this slot's pool items that alone open a location
    beyond those reachable at the start."""
    mw = world.multiworld
    base = _base_state(world)
    start = _reachable_empty(world, base)
    names = set()
    for item in mw.itempool:
        if (item.player != world.player or not item.advancement
                or item.name in names):
            continue
        state = base.copy()
        state.collect(item, True)
        if _reachable_empty(world, state) > start:
            names.add(item.name)
    return sorted(names)


def _cause(world) -> str:
    from .progressive_capability import BOOST_CHAIN
    difficulty = world.options.logic_difficulty.current_key
    found = openers(world)
    if any(name.startswith(BOOST_CHAIN) for name in found):
        weapons = [n for n in found if not n.startswith(BOOST_CHAIN)]
        tail = (" or a weapon such as " + weapons[0]) if weapons else ""
        return (f"every track it can reach first needs the first Progressive "
                f"Boost{tail} at logic difficulty {difficulty}")
    if found:
        return f"every check it can reach first needs an item such as {found[0]}"
    return "no single item opens a check at the start"


# Fewest starting checks a slot may have (ruling 2026-10-02: refuse only when
# really short). With one starting check the fill has a single early spot for
# the item that opens the next check; in a room another slot's early items or a
# minimal-accessibility partner's items can take it (fuzz 14603, 2026-10-01:
# both slots start with one check and the room fails on about 1 in 12 AP
# seeds). Measured 2026-10-02: no seed that 0.2.3 generates starts with fewer
# than two checks (2,380 solo fuzzer rolls and 201 two-slot rooms), so two
# refuses nothing 0.2.3 accepts. Three would.
MIN_STARTING_CHECKS = 2


# Content plans with second-stage gates (#133 PR 3a). A stage-2 gate on a
# starting pad keeps that pad's later modes shut, so the start can hold only two
# or three open checks. The fill then dead-ends when it puts items that open
# nothing new in every one of them (CI fuzz artifact 244; seed 710 of the
# two-stage per-pad profile puts a Sapphire Relic in all three). Measured
# 2026-10-17 on 6,000 seeds of that profile: 3 dead ends, all with 2 or 3 open
# starting checks, none with 4 or more. Ruling 2026-10-17: no fill
# simulation (the Ionium generation cost); a narrow start gets one local early
# Key, or the item that opens the most checks when the seed has no Key opener.
# Nothing is precollected and supply and gates stay as drawn.
NARROW_START_CHECKS = 4


def early_opener(world):
    """Name of the item to place early for a narrow content-plan start, or
    None when the start is wide enough or no single item opens a check."""
    base = _base_state(world)
    start = _reachable_empty(world, base)
    if start >= NARROW_START_CHECKS:
        return None
    reach = {}
    for item in world.multiworld.itempool:
        if (item.player != world.player or not item.advancement
                or item.name in reach):
            continue
        state = base.copy()
        state.collect(item, True)
        reach[item.name] = _reachable_empty(world, state)
    opening = {name: n for name, n in reach.items() if n > start}
    if not opening:
        return None
    if "Key" in opening:
        return "Key"
    return max(sorted(opening), key=opening.get)


def mark_early_opener(world) -> None:
    """Narrow content-plan start with second-stage gates: ask AP's early-item
    step to place one opener in this slot's starting checks. Takes no random
    draw; a wide start, or a plan without second-stage gates, is unchanged."""
    from .content_plan import STAGE2_PREFIX
    plan = world.ctr_content_plan
    if not any(row["id"].startswith(STAGE2_PREFIX) for row in plan["requirements"]):
        return
    name = early_opener(world)
    if name is None:
        return
    mw, player = world.multiworld, world.player
    target = (mw.early_items if name in world.options.non_local_items.value
              else mw.local_early_items)
    slot = target.setdefault(player, {})
    slot[name] = max(slot.get(name, 0), 1)
    world._ctr_early_opener = name


# Content plans with Progressive Boost (#133 PR 4c, ruling 2026-10-18). Per-
# racer boost with Character Unlocks and racer locks left a start of a few
# boost-free checks, and the restrictive fill could spend them all on items
# that open nothing (another racer's chain, racer unlocks): 19 FillErrors in
# 3000 runs of the racer stress arm, none with shared boost alone. Ruling: when
# boost is on and the start is narrow, the starting racer's first Progressive
# Boost becomes a local early item. Nothing is precollected; a wide start, or
# a plan without boost, is unchanged. The threshold was measured on the
# failing seeds' start sizes (slice plan, PR 4c fill fix).
BOOST_NARROW_START_CHECKS = 5


def starting_boost_item(world):
    """The boost item that gives the starting racer its first rank."""
    from .progressive_capability import BOOST_CHAIN, boost_item_name
    mode = int(world.options.progressive_boost.value)
    return boost_item_name(world.ctr_starting_character) if mode == 2 else BOOST_CHAIN


def mark_early_boost(world) -> None:
    """Content plan with Progressive Boost and a narrow start: ask AP's
    early-item step to place the starting racer's first boost in this slot's
    starting checks (ruling 2026-10-18). With racer locks as well, the next
    widest opener is marked early too (second ruling 2026-10-18). Takes no
    random draw."""
    plan = world.ctr_content_plan
    if not plan.get("capability", {}).get("boost_mode"):
        return
    if sphere0_breadth(world) >= BOOST_NARROW_START_CHECKS:
        return
    name = starting_boost_item(world)
    mw, player = world.multiworld, world.player
    target = (mw.early_items if name in world.options.non_local_items.value
              else mw.local_early_items)
    slot = target.setdefault(player, {})
    slot[name] = max(slot.get(name, 0), 1)
    world._ctr_early_boost = name
    from .characters import racer_locks_effective
    if racer_locks_effective(world):
        _mark_second_opener(world)


# Boost and racer locks together (#133 PR 4c, second ruling 2026-10-18). With
# the early first boost alone, narrow starts behind many racer-locked pads still
# dead-ended: 6 FillErrors in 3000 runs of the racer stress arm, and none of the
# 3 reproduced seeds (527, 1140, 1971) filled. Ruling: when the seed has racer
# locks too, the next widest opener is also a local early item. It is measured
# with the slot's early items already collected; a further copy of an item
# already marked early (a second boost rank) can be the one chosen. Nothing is
# precollected.
def second_opener(world):
    """Name of the pool item that opens the most further checks once this
    slot's early items are collected, or None when no item opens one. A
    further copy of an item already marked early counts as a candidate, but
    loses a tie to an item that is not marked yet."""
    mw, player = world.multiworld, world.player
    early = _early_counts(world)
    pool = {}
    for item in mw.itempool:
        if item.player == player and item.advancement:
            pool.setdefault(item.name, []).append(item)
    base = _base_state(world)
    for name in sorted(early):
        for item in pool.get(name, [])[:early[name]]:
            base.collect(item, True)
    start = _reachable_empty(world, base)
    reach = {}
    for name, copies in pool.items():
        if len(copies) <= early.get(name, 0):
            continue
        state = base.copy()
        state.collect(copies[early.get(name, 0)], True)
        reach[name] = _reachable_empty(world, state)
    opening = {name: n for name, n in reach.items() if n > start}
    if not opening:
        return None
    # On a tie, an item not yet marked early wins (seed 1140: a Gem and a
    # second boost rank open the same count), then the first name.
    return max(sorted(opening), key=lambda name: (opening[name], name not in early))


def _early_counts(world):
    mw, player = world.multiworld, world.player
    counts = dict(mw.early_items.get(player, {}))
    for name, n in mw.local_early_items.get(player, {}).items():
        counts[name] = counts.get(name, 0) + n
    return counts


def _mark_second_opener(world) -> None:
    name = second_opener(world)
    if name is None:
        return
    mw, player = world.multiworld, world.player
    target = (mw.early_items if name in world.options.non_local_items.value
              else mw.local_early_items)
    slot = target.setdefault(player, {})
    slot[name] = slot.get(name, 0) + 1
    world._ctr_early_second = name


def _narrow_cause(world) -> str:
    from .progressive_capability import BOOST_CHAIN
    difficulty = world.options.logic_difficulty.current_key
    found = openers(world)
    if any(name.startswith(BOOST_CHAIN) for name in found):
        return (f"most tracks it can reach first need the first Progressive "
                f"Boost at logic difficulty {difficulty}")
    if found:
        return f"its next checks need an item such as {found[0]}"
    return "few of its first checks are open without items"


def _manual_rules_note(world) -> str:
    """Sentence naming the player's warp_pad_rules when the slot has any."""
    from . import warp_pad_rules
    rules = warp_pad_rules.fixed(world)
    if not rules:
        return ""
    listed = ", ".join(f"{pad}: {warp_pad_rules.describe(rule)}"
                       for pad, rule in sorted(rules.items()))
    return (f" Your warp_pad_rules ({listed}) are fixed and were not changed; "
            f"make one of them free or lower to open more starting checks.")


def raise_if_narrow(world) -> None:
    """Refuse the slot when fewer than MIN_STARTING_CHECKS locations are
    reachable from its starting inventory."""
    breadth = sphere0_breadth(world)
    if breadth >= MIN_STARTING_CHECKS:
        return
    name = world.multiworld.player_name[world.player]
    fix = ("Usual fix: turn on Item Box Locations, turn on Held-Position "
           "Rungs (or more Podium Rung categories), or set logic_difficulty "
           "to hard.")
    if breadth == 0:
        raise OptionError(
            f"CTR: {name} has no check it can reach at the start: "
            f"{_cause(world)}, so the item fill cannot begin. {fix}"
            f"{_manual_rules_note(world)}")
    raise OptionError(
        f"CTR: {name} can reach only {breadth} check"
        f"{'' if breadth == 1 else 's'} at the start (at least "
        f"{MIN_STARTING_CHECKS} needed): {_narrow_cause(world)}, so the item "
        f"fill can run out of early spots for the item that opens the next "
        f"check. {fix}{_manual_rules_note(world)}")


# Start bootstrap for content plans (0.3.0 review finding 1, 2026-10-27).
#
# Root cause of the remaining content-plan FillErrors (CI fuzz 505 of the
# content-plan-bosses arm; reproduced as seed 2601 of its YAML, and seeds 130,
# 705, 2601, 3958, 4612, 4687 and 5632 of the same YAML with per-racer boost
# pinned): AP's fill places items backwards. The last item it places must go
# to a check reachable without it, and with Character Unlocks, racer locks and
# Progressive Boost a content plan can start with two to five open checks that
# widen by one to three checks per item. By the time the fill places the item
# the start depends on, those few checks already hold items that open nothing,
# and swapping cannot recover (seed 5632: 124 items placed, then a Red Gem with
# only 6 reachable checks, all full). The early items above only reach the
# checks open at the very start: two early items on a start of two fill it
# completely, and when more items are marked than the start has checks, AP
# drops one ("Could not fulfill rules of early items", the CI symptom), and a
# start of five qualified for none of them (seed 5632).
#
# Fix: before the fill, place openers in the start one after another until at
# least BOOTSTRAP_START_CHECKS checks are open and empty, or a quarter of the
# slot's checks on a small plan (a 19-check plan opens 4, not most of itself).
# The items the rulings above marked early go first, in the order they were
# marked; then the item that opens the most further checks; when no single
# item opens one (a pad needing two Red CTR Tokens, seed 4088), two to four
# copies of one item, then two different items. Each item goes to a random
# open check of this slot.
# Nothing is precollected, no supply, gate or rule changes, and the fill is not
# simulated: like the early items, this only measures what opens. A plan whose
# start already has the open checks takes no draw and is unchanged.
#
# That order measures one item at a time and can spend the last spots in front of
# a gate that needs several (one generator row 8b: a start of two, two Keys and a
# boost seated, no spot left for two Trophies). When it stops short of the target
# nothing of it stays: content_opening.search plans the whole opening on the real
# rules, with the fixed Keys it reaches, and it is reserved before any of it locks.
BOOTSTRAP_START_CHECKS = 12
BOOTSTRAP_MAX_COPIES = 4


def bootstrap_target(world) -> int:
    """Open empty checks the start bootstrap aims for on this slot."""
    from .wumpa_shop import LOCATION_TYPE as SHOP
    checks = sum(1 for loc in world.multiworld.get_locations(world.player)
                 if loc.address is not None and getattr(loc, "type", None) != SHOP)
    return min(BOOTSTRAP_START_CHECKS, checks // 4)


def _open_empty(world, state):
    """Open empty checks the bootstrap may seat an opener on. Wumpa Shop
    slots never count as starting checks (content plans, job J11)."""
    from BaseClasses import LocationProgressType
    from .wumpa_shop import LOCATION_TYPE as SHOP
    return [loc for loc in world.multiworld.get_unfilled_locations(world.player)
            if loc.address is not None
            and loc.progress_type != LocationProgressType.EXCLUDED
            and getattr(loc, "type", None) != SHOP
            and loc.can_reach(state)]


def _next_openers(world, state, start, pool):
    """Names of the pool items to place next: one item that opens the most
    further checks, else the fewest copies of one item, else two different
    items, that open some. Only groups that fit in the open checks count.
    Empty when nothing opens a check."""
    single = {}
    for name, copies in pool.items():
        probe = state.copy()
        probe.collect(copies[0], True)
        opened = len(_open_empty(world, probe))
        if opened > start:
            single[name] = opened
    if single:
        return [max(sorted(single), key=single.get)]
    groups = {}
    for name, copies in pool.items():
        for count in range(2, min(len(copies), BOOTSTRAP_MAX_COPIES, start) + 1):
            probe = state.copy()
            for item in copies[:count]:
                probe.collect(item, True)
            opened = len(_open_empty(world, probe))
            if opened > start:
                groups[(name,) * count] = opened
                break
    if not groups and start >= 2:
        import itertools
        for first, second in itertools.combinations(sorted(pool), 2):
            probe = state.copy()
            probe.collect(pool[first][0], True)
            probe.collect(pool[second][0], True)
            opened = len(_open_empty(world, probe))
            if opened > start:
                groups[(first, second)] = opened
    if not groups:
        return []
    return list(max(sorted(groups), key=lambda g: (groups[g] - start) / len(g)))


def _room(world, state):
    """Spots an opening may take: the open checks, then the Wumpa Shop slots that
    can hold progression. Excluded checks hold filler only."""
    from BaseClasses import LocationProgressType
    from .wumpa_shop import LOCATION_TYPE as SHOP
    shop = not int(world.options.wumpa_shop_progression.value)
    return [loc for loc in world.multiworld.get_unfilled_locations(world.player)
            if loc.address is not None and loc.progress_type != LocationProgressType.EXCLUDED
            and (shop or getattr(loc, "type", None) != SHOP) and loc.can_reach(state)]


def _collect(world, state, items):
    """`state` with `items` held and every placed item it now reaches."""
    probe = state.copy()
    for item in items:
        probe.collect(item, True)
    probe.sweep_for_advancements(locations=_placed(world))
    return probe


def _reserve(world, state, items):
    """[(item, spot)] seating `items` in order, each on a spot open before it, or
    None when one finds no spot. Locks nothing. The checks go first, then the shop."""
    chosen, probe = [], state
    for index, item in enumerate(items):
        taken = [location for _item, location in chosen]
        spots = [loc for loc in sorted(_room(world, probe), key=lambda loc: loc.name)
                 if loc not in taken and loc.can_fill(probe, item, True)]
        if not spots:
            return None
        checks = _open_empty(world, probe)
        chosen.append((item, world.random.choice([loc for loc in spots if loc in checks] or spots)))
        probe = _collect(world, state, items[:index + 1])
    return chosen


def _lock(world, chosen):
    """Lock a reservation, with the items' early marks."""
    mw, player = world.multiworld, world.player
    marked = mw.local_early_items.setdefault(player, {})
    for item, location in chosen:
        # Item equality is by name; remove this very copy.
        del mw.itempool[next(i for i, pooled in enumerate(mw.itempool) if pooled is item)]
        location.place_locked_item(item)
        if marked.get(item.name):
            marked[item.name] -= 1
            if not marked[item.name]:
                del marked[item.name]


def _first_key_tight(world, state, items):
    """Do the checks in front of a fixed first Key leave too few to spare, with
    `items` seated? Everything else held, the Key's own opening excluded."""
    mw = world.multiworld
    probe = state.copy()
    for item in mw.itempool:
        if _own_item(world, item) and item.advancement and item.name != "Key":
            probe.collect(item, True)
    probe.sweep_for_advancements(locations=[loc for loc in _placed(world) if loc.item.name != "Key"])
    return len(_room(world, probe)) - len(items) < bootstrap_target(world)


def _seat_first_key(world, state):
    """A fixed first Key waits behind its garage, and on a narrow start only a few
    checks stand in front of it. Left to the fill, other items take those checks
    and the last items the garage asks for have nowhere to go, with vanilla or
    random requirements. So when few checks are to spare, the opening that reaches
    the Key is seated here, on the hub's Wumpa Shop when the pads run out. All of
    it or nothing: it is reserved before any of it locks. A pooled Key also pays
    for its support path; reserve it when those copies crowd the initial cut,
    only with a witness that leaves at least the initial room. Returns the state after."""
    mw, player = world.multiworld, world.player
    fixed = world.ctr_content_plan.get("fixed_items", {}).get("keys")
    non_local = set(world.options.non_local_items.value)
    if fixed:
        items, _spots = plan_opening(world, state, 1, non_local, "Key")
        tight = bool(items) and _first_key_tight(world, state, items)
    else:
        if state.has("Key", player):
            return state
        if "Key" in non_local or not any(_own_item(world, item) and item.name == "Key"
                                         and item.location is None for item in mw.itempool):
            return state
        initial = len(_room(world, state))
        target = bootstrap_target(world)
        # A pooled Key can open no check alone. Pay for its real support path
        # and leave at least the initial room, rather than consuming the cut.
        items, _spots = plan_opening(world, state, max(target, initial), non_local, "Key")
        if _spots < max(target, initial):
            return state
        # A Key path may use one more opening check than the ordinary route.
        # Keep the Key reserved: otherwise reverse fill can spend its support
        # checks before placing it. If that cost leaves exactly the target,
        # let the ordinary bootstrap seek one spare check after this path.
        needs_margin = initial < target and _spots < plan_opening(world, state, target, non_local)[1]
        tight = initial - len(items) < target
    if not items or not _collect(world, state, items).has("Key", player) or not tight:
        return state
    draw = world.random.getstate() if not fixed else None
    chosen = _reserve(world, state, items)
    if chosen is None:
        if draw is not None:
            world.random.setstate(draw)
        return state
    _lock(world, chosen)
    world._ctr_start_bootstrap = [(item.name, location.name) for item, location in chosen]
    if not fixed and needs_margin:
        world._ctr_pooled_key_needs_margin = True
    return _collect(world, state, [])


def _seat_first_win(world, state):
    """An auxiliary-only wide start still needs a paid route to a real win.

    Held-position, Hit and Wumpa checks can fill the opening without making
    a win reachable. Reserve a bounded, actually seatable winning prefix only
    when it preserves the opening's free room after paying every copy.
    """
    from .content_plan import win_kinds
    plan = world.ctr_content_plan
    if not plan.get("checks"):
        return state
    kinds = win_kinds(plan)
    wins = [loc for loc in world.multiworld.get_locations(world.player) if loc.address in kinds]
    reached = lambda probe: any(loc.can_reach(probe) for loc in wins)
    if not wins or reached(state):
        return state
    initial = len(_room(world, state))
    if not initial:
        return state
    target = max(initial, bootstrap_target(world))
    items, room = plan_opening(world, state, target, set(world.options.non_local_items.value),
                               condition=reached)
    if not items or room < target or not reached(_collect(world, state, items)):
        return state
    draw = world.random.getstate()
    chosen = _reserve(world, state, items)
    if chosen is None:
        world.random.setstate(draw)
        return state
    _lock(world, chosen)
    world._ctr_start_bootstrap = list(getattr(world, "_ctr_start_bootstrap", None) or ()) + [
        (item.name, location.name) for item, location in chosen]
    return _collect(world, state, [])


def _place_openers(world, state, base, target, queue, non_local):
    """The greedy bootstrap: one opener after another, each item measured alone,
    until `target` checks are open and empty. Returns (name, location name) pairs."""
    mw, player = world.multiworld, world.player
    marked = mw.local_early_items.setdefault(player, {})
    placed = []
    while True:
        spots = _open_empty(world, state)
        if len(spots) >= target or not spots:
            break
        pool = {}
        for item in mw.itempool:
            if (_own_item(world, item) and item.advancement and item.location is None
                    and item.name not in non_local
                    and item.name not in mw.early_items.get(player, {})):
                pool.setdefault(item.name, []).append(item)
        names = []
        while queue and not names:
            name = queue.pop(0)
            if name in pool:
                names = [name]
        # A marked item that opens nothing yet waits for what does: on a start
        # of two it would leave one spot for an opener that needs two (row 3).
        if names:
            probe = state.copy()
            probe.collect(pool[names[0]][0], True)
            if len(_open_empty(world, probe)) <= len(spots):
                openers = _next_openers(world, state, len(spots), pool)
                if openers and len(openers) <= len(spots):
                    queue.insert(0, names[0])
                    names = openers
        if not names:
            names = _next_openers(world, state, len(spots), pool)
        if not names or len(names) > len(spots):
            break
        # Items AP's own early pass still has to seat (Itemsanity's weapon) need
        # a check open from the very start: keep that many of those free.
        owed = sum(n for name, n in mw.early_items.get(player, {}).items()
                   if name not in non_local)
        taken = {}
        for name in names:
            item = pool[name][taken.get(name, 0)]
            taken[name] = taken.get(name, 0) + 1
            fits = [loc for loc in sorted(_open_empty(world, state), key=lambda loc: loc.name)
                    if loc.can_fill(state, item, True)]
            base_open = {loc.name for loc in _open_empty(world, base)}
            if len(base_open) <= owed:
                fits = [loc for loc in fits if loc.name not in base_open]
            if not fits:
                break
            location = world.random.choice(fits)
            _lock(world, [(item, location)])
            placed.append((name, location.name))
        else:
            state.sweep_for_advancements(locations=_placed(world))
            continue
        break
    return placed


def _unlock(world, placed):
    """Take the greedy bootstrap's placements back."""
    mw = world.multiworld
    for _name, location_name in placed:
        location = mw.get_location(location_name, world.player)
        item = location.item
        location.locked = False
        location.item = None
        item.location = None


def plan_opening(world, state, target, non_local, reach=None, condition=None):
    """(items to seat, spots they leave) of the best opening on the real rules. With
    `reach`, an item name, the opening has to hold it, on a fixed check or in `held`.
    `condition`, when supplied, must hold on the same resulting real-rule state."""
    from .content_plan import ITEM_BY_CODE
    mw, player = world.multiworld, world.player
    plan = world.ctr_content_plan
    gates = content_opening.gate_names(plan, ITEM_BY_CODE, starting_boost_item(world)
                                       if plan.get("capability", {}).get("boost_mode") else None)
    pool, spare = {}, {}
    for item in mw.itempool:
        if _own_item(world, item) and item.advancement and item.location is None and item.name not in non_local:
            (pool if item.name in gates else spare).setdefault(item.name, []).append(item)
    bundles = content_opening.letter_bundles(plan, {name: len(copies) for name, copies in spare.items()})
    pool.update((name, spare[name]) for bundle in bundles for name in bundle)

    def held_items(held):
        taken = {}
        items = []
        for name in held:
            items.append(pool[name][taken.get(name, 0)])
            taken[name] = taken.get(name, 0) + 1
        return items

    states = {}

    def after(held):
        if held not in states:
            states[held] = _collect(world, state, held_items(held))
        return states[held]

    reached = None
    if reach or condition is not None:
        def reached(held):
            probe = after(held)
            return (not reach or probe.has(reach, player)) and (condition is None or condition(probe))

    names, room = content_opening.search({name: len(copies) for name, copies in pool.items()},
                                         lambda held: len(_room(world, after(held))), target,
                                         reached,
                                         bundles=bundles,
                                         goals=(("Key",),) if reach == "Key" and pool.get("Key") else (),
                                         groups_with_singles=condition is not None)
    return held_items(names), room


def bootstrap_start(world) -> None:
    """Content plans: place openers in this slot's start until at least
    bootstrap_target checks are open and empty (see above). Runs in
    pre_fill, after plando and item links. Draws only when it places."""
    from BaseClasses import CollectionState
    mw, player = world.multiworld, world.player
    target = bootstrap_target(world)
    state = _seat_first_key(world, _base_state(world))
    # A narrow paid Key path may land exactly on the stop threshold. Seed 445
    # then leaves Boost to reverse fill, where the remaining checks cannot
    # take it. One more productive opener restores a spare non-shop check.
    if getattr(world, "_ctr_pooled_key_needs_margin", False) and len(_open_empty(world, state)) <= target:
        target += 1
    # The start as AP's early pass sees it: only event items (no address) are
    # swept, placed items never are.
    base = CollectionState(mw)
    base.sweep_for_advancements(
        locations=[loc for loc in mw.get_locations(player)
                   if loc.item is not None and loc.address is None])
    if len(_open_empty(world, state)) >= target:
        _seat_first_win(world, state)
        return
    # A player's non_local_items stay out of their own start.
    non_local = set(world.options.non_local_items.value)
    # Itemsanity's early weapon opens nothing. On a start with no spare check
    # it would take the spot of the item that does, and the fill dead-ends
    # (vanilla requirements with two single-check pads open, row 3), so it
    # gives up its early place. Nothing is precollected.
    early = mw.early_items.get(player, {})
    if len(_open_empty(world, base)) <= sum(n for name, n in early.items() if name not in non_local) + 1:
        for name in [name for name in early if name not in non_local]:
            del early[name]
    marked = mw.local_early_items.setdefault(player, {})
    queue = [name for name, count in list(marked.items()) for _ in range(count)]
    # The greedy order measures one item at a time, so it can spend the last spots
    # in front of a gate that needs several. When it stops short, its placements
    # are taken back and a whole opening that leaves more room is seated instead.
    pool, marks, draw = list(mw.itempool), dict(marked), world.random.getstate()
    trial = state.copy()
    placed = _place_openers(world, trial, base, target, list(queue), non_local)
    if len(_open_empty(world, trial)) < target:
        room = len(_room(world, trial))
        _unlock(world, placed)
        mw.itempool[:] = pool
        marked.clear()
        marked.update(marks)
        world.random.setstate(draw)
        items, best = plan_opening(world, state, target, non_local)
        chosen = _reserve(world, state, items) if best > room else None
        if chosen is None:
            world.random.setstate(draw)
            placed = _place_openers(world, state.copy(), base, target, queue, non_local)
        else:
            _lock(world, chosen)
            placed = [(item.name, location.name) for item, location in chosen]
    if placed:
        world._ctr_start_bootstrap = getattr(world, "_ctr_start_bootstrap", []) + placed
