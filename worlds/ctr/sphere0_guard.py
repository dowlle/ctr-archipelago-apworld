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
            f"{_cause(world)}, so the item fill cannot begin. {fix}")
    raise OptionError(
        f"CTR: {name} can reach only {breadth} check"
        f"{'' if breadth == 1 else 's'} at the start (at least "
        f"{MIN_STARTING_CHECKS} needed): {_narrow_cause(world)}, so the item "
        f"fill can run out of early spots for the item that opens the next "
        f"check. {fix}")
