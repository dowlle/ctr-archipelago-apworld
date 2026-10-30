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


def _reachable_empty(world, state) -> int:
    return sum(1 for loc in world.multiworld.get_locations(world.player)
               if loc.item is None and loc.address is not None
               and loc.can_reach(state))


def _base_state(world):
    from BaseClasses import CollectionState
    state = CollectionState(world.multiworld)
    # Locked rewards and goal events are already placed; collect what is
    # reachable of them, since the fill would too.
    state.sweep_for_advancements(
        locations=[loc for loc in world.multiworld.get_locations(world.player)
                   if loc.item is not None])
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
BOOTSTRAP_START_CHECKS = 12
BOOTSTRAP_MAX_COPIES = 4


def bootstrap_target(world) -> int:
    """Open empty checks the start bootstrap aims for on this slot."""
    checks = sum(1 for loc in world.multiworld.get_locations(world.player)
                 if loc.address is not None)
    return min(BOOTSTRAP_START_CHECKS, checks // 4)


def _open_empty(world, state):
    from BaseClasses import LocationProgressType
    return [loc for loc in world.multiworld.get_unfilled_locations(world.player)
            if loc.address is not None
            and loc.progress_type != LocationProgressType.EXCLUDED
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


def bootstrap_start(world) -> None:
    """Content plans: place openers in this slot's start until at least
    bootstrap_target checks are open and empty (see above). Runs in
    pre_fill, after plando and item links. Draws only when it places."""
    from BaseClasses import CollectionState
    mw, player = world.multiworld, world.player
    target = bootstrap_target(world)
    state = _base_state(world)
    # The start as AP's early pass sees it: only event items (no address) are
    # swept, placed items never are.
    base = CollectionState(mw)
    base.sweep_for_advancements(
        locations=[loc for loc in mw.get_locations(player)
                   if loc.item is not None and loc.address is None])
    if len(_open_empty(world, state)) >= target:
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
    placed = []
    while True:
        spots = _open_empty(world, state)
        if len(spots) >= target or not spots:
            break
        pool = {}
        for item in mw.itempool:
            if (item.player == player and item.advancement and item.location is None
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
            # Item equality is by name; remove this very copy.
            del mw.itempool[next(i for i, pooled in enumerate(mw.itempool) if pooled is item)]
            location.place_locked_item(item)
            placed.append((name, location.name))
            if marked.get(name):
                marked[name] -= 1
                if not marked[name]:
                    del marked[name]
        else:
            state.sweep_for_advancements(
                locations=[loc for loc in mw.get_locations(player) if loc.item is not None])
            continue
        break
    if placed:
        world._ctr_start_bootstrap = placed
