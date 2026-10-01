"""Sphere-0 opener: give a slot that starts with no reachable check the one
item that opens the most checks (fuzz failures 32541, 6813, 10634, 2026-10-01).

WHY THIS EXISTS
---------------
With Progressive Boost randomized and logic difficulty easy or medium, every
Trophy Race on the difficulty-gated tracks needs the first boost rank (or,
with Itemsanity, enough weapon families), and easy also gates Finish on
Podium and Held 1st (`Rules.add_capability_difficulty_rules`, ruling
2026-09-27, #329). When every track the slot can reach at the start is such a
track, and no ungated location class is on (Item Box Locations, held or
any-position rungs, Hit Character, Itemsanity boxes on an open track), the
slot has ZERO locations reachable from its starting inventory.

AP's fill cannot place the item that opens the first check anywhere in that
slot, because no location of the slot is reachable without it:

- solo, every seed dead-ends and only the rollback backstop rescues it, by
  precollecting whatever the start_inventory panic strands. When that is a
  Gem and the goal is one Gem, the slot starts with its goal complete, the
  minimal fill then places progression without access checks, and AP's
  accessibility check raises on the empty first sphere (fuzz 32541);
- in a room, the opener can only sit in another slot's early checks, so the
  fill fails whenever the other slots are tight too (fuzz 6813, about 1 in 6
  AP seeds for that pair, and 10634, every AP seed).

Before the 2026-10-01 refusal ruling the rung sizer's working margin forced
three rung categories on every capability-pack seed without Item Box
Locations. Held rungs are not difficulty-gated, so that margin kept sphere 0
non-empty as a side effect; it was never measured as such. The ruling removed
the margin from the refusal path and these seeds became admissible.

WHAT IT DOES
------------
Only when the slot has no reachable empty location at zero items: move one
copy of the progression item that opens the most of the slot's locations
from the item pool into starting inventory, and add one filler so item count
still equals location count. Same mechanism as the rollback backstop, but
decided from the rules alone, so it works in a room as well as solo, takes no
random draw, and runs in `generate_basic` where the two-stage probe's mirror
repeats it. An item whose collection completes the slot's goal is never
chosen. A seed whose sphere 0 is non-empty is untouched.
"""
from typing import List, Optional, Tuple


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


def choose_opener(world) -> Tuple[Optional[str], int]:
    """(item name, locations it opens) for the best single opener, or
    (None, 0) when no single pool item opens a location."""
    mw = world.multiworld
    player = world.player
    base = _base_state(world)
    start_suffix = f"({getattr(world, 'ctr_starting_character', '')})"
    seen = set()
    best = None  # (sort key, name, opened)
    for item in mw.itempool:
        if item.player != player or not item.advancement or item.name in seen:
            continue
        seen.add(item.name)
        state = base.copy()
        state.collect(item, True)
        state.sweep_for_advancements(
            locations=[loc for loc in mw.get_locations(player)
                       if loc.item is not None])
        if mw.has_beaten_game(state, player):
            continue  # never start a slot with its goal complete
        opened = _reachable_empty(world, state)
        if not opened:
            continue
        # Most locations first; prefer the starting racer's own copy of a
        # per-character item; then name order, so the choice is a pure
        # function of the rules.
        key = (-opened, -int(item.name.endswith(start_suffix)), item.name)
        if best is None or key < best[0]:
            best = (key, item.name, opened)
    return (best[1], best[2]) if best else (None, 0)


def apply(world) -> List[str]:
    """Precollect one opener when sphere 0 is empty. Returns the moved names."""
    if sphere0_breadth(world) > 0:
        return []
    name, _opened = choose_opener(world)
    if name is None:
        return []
    mw = world.multiworld
    for i, item in enumerate(mw.itempool):
        if item.player == world.player and item.name == name:
            del mw.itempool[i]
            mw.push_precollected(item)
            mw.itempool.append(world.create_filler())
            return [name]
    return []
