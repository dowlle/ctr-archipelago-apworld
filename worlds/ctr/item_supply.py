"""Overflow shedding: what a seed gives up when it has more items than places.

Archipelago requires a seed to end with exactly as many items as unfilled
locations. CTR normally reaches that by TOP-UP: build the items the seed must
have, then mint `Wumpa Fruit` for every location left over (42 of them on a
default seed). That direction is easy and lives in `create_items`.

This module owns the other direction, which is rare and was wrong until
2026-08-18: what to give up when the pool comes out BIGGER than the supply.

THE ORDER IS RULED (Stef, 2026-08-18), not a preference:

  1. FILLER, because that is what filler is for. A comfort item is never
     dropped while a SHEDDABLE filler item is still in the pool.

     Not all filler is sheddable. Archipelago fills `EXCLUDED` locations from
     the filler pool ALONE (`Fill.py`: excluded locations are filled from
     `filleritempool`, and `usefulitempool` only joins for ordinary locations
     afterwards), so a seed must keep at least one filler item per excluded
     location or fill dies with "Not enough filler items for excluded
     locations". CTR always has at least one: `_install_goal` marks the goal
     location EXCLUDED (#27) so that no world's progression can land on it, and
     a player's own `exclude_locations` adds more.

     This was found the hard way on 2026-08-18: a first cut of this module shed
     filler without a floor, passed its own 2000-seed item/location arm, and
     then failed the matrix's default arm on two seeds out of five thousand
     with exactly that FillError. Shedding the last filler in favour of keeping
     comfort items is the one way to satisfy the item/location count and still
     make the seed unfillable.
  2. The COMFORT PACK, whole. The 2026-08-10 ruling that it ships together or
     not at all stands, and costs nothing here: dropping five to cover an
     overflow of one leaves the pool four under, and `create_items`' top-up
     refills those four slots with filler immediately. The seed trades the
     comfort pack for filler, which is the trade the pack was designed to make.
  3. Nothing else. A seed still over after both is genuinely unsatisfiable and
     `create_items` refuses it with an OptionError naming the shortfall.

WHAT IS NEVER SHED. Progression, because dropping it can make a seed
unwinnable. And the option-created single items (`Tizi Helper`, `Turbo Grant`):
those are toggles the player switched on, so a seed that cannot fit them is
refused rather than silently ignoring the option. Neither is filler-classified,
so both fall out of tier 1 for free; this module never needs to name them.

TIER 1 KEYS ON CLASSIFICATION, NOT ON A NAME. `Wumpa Fruit` is the only filler
the static table creates today, but `Small Wumpa Bundle` and `Big Wumpa Bundle`
are filler too and currently sit frozen-but-inert at count 0. They join tier 1
automatically on the day an option creates them, with no change here.

WHY THIS EXISTS AS A FUNCTION. The behaviour it replaced was four lines inline
in `create_items` and could only be tested by generating a seed whose option
combination happened to land on the exact overflow under test. That is how the
all-or-nothing bug survived: it needed a seed six over, which is roughly one in
five hundred. Here every tier is reachable with a synthetic pool.
"""
from typing import Iterable, List, Sequence

from BaseClasses import Item, ItemClassification


def shed_overflow(pool: Sequence[Item], unfilled: int,
                  surface_item_names: Iterable[str],
                  filler_floor: int = 0) -> List[Item]:
    """Return the pool reduced toward `unfilled`, in the ruled order.

    `filler_floor` is how many filler items this seed must KEEP for its
    `EXCLUDED` locations, which only filler can fill. Callers pass
    `elastic_bounds.estimated_filler_reserve`, which is the estimate rather than
    the exact count on purpose: AP core applies a player's `exclude_locations`
    as location progress state AFTER every world's `create_items`, so the exact
    number is not knowable here.

    Returns the pool unchanged when it already fits. May return a pool that is
    still too big (tier 3 is the caller's refusal) or, after tier 2, one that is
    now SMALLER than `unfilled`; the caller's filler top-up closes that gap.
    """
    if len(pool) <= unfilled:
        return list(pool)

    surface_names = frozenset(surface_item_names)

    # Tier 1: filler, exactly as much as the overflow needs and no more, and
    # never below the floor the excluded locations require.
    overflow = len(pool) - unfilled
    total_filler = sum(1 for item in pool
                       if item.classification == ItemClassification.filler)
    sheddable = max(0, total_filler - max(0, filler_floor))
    to_shed = min(overflow, sheddable)

    shed = 0
    kept: List[Item] = []
    for item in pool:
        if shed < to_shed and item.classification == ItemClassification.filler:
            shed += 1
            continue
        kept.append(item)
    pool = kept

    if len(pool) <= unfilled:
        return pool

    # Tier 2: the comfort pack, whole or not at all. Dropping it is only worth
    # doing if it actually resolves the overflow; if the seed is still over
    # afterwards the pack has been spent for nothing, so leave it in and let the
    # caller refuse with the pack's slots still counted in the shortfall.
    without_surface = [item for item in pool if item.name not in surface_names]
    if len(without_surface) <= unfilled:
        return without_surface

    return pool
