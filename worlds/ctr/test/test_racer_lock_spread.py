"""Racer-lock spread and unlock placement (2026-09-22 racer-lock research).

Two rules, both apworld-only (no datapackage, slot_data shape or native
change):

  * a racer locks a second pad only once every candidate racer locks one, so
    no racer locks more than `ceil(locks / 15)` pads;
  * a racer's unlock item is never placed on a check of a destination whose
    pad that racer locks, including the track's Podium and Wumpa checks that
    a Gem Cup leg can reach around the lock.

The reported shape these close: Crash locks four pads, one of them loads
Polar Pass, and Crash's unlock sits on `Polar Pass: Held 3rd`, reachable only
through a Gem Cup that races Polar Pass. In logic, but the pad the player
stands on says "requires Crash" (config D seed 183 below).
"""

import math
import unittest
from collections import Counter

from Fill import distribute_items_restrictive
from Options import OptionError
from . import setup_multiworld

from .. import ctrAPWorld
from ..characters import (
    locked_destination_regions,
    racer_lock_forbidden_locations,
    spread_lock_racers,
    unlock_item_name,
)
from ..progressive_capability import ROSTER

# The research configurations. D keeps the Gems on their cups, which is what
# makes a locked Gem Cup pad matter for a Gem goal.
CONFIG_A = {"racer_locked_pads": 9, "gems_required_goal": 4,
            "oxide_goal": "none"}
CONFIG_D = dict(CONFIG_A, shuffle_gems=False)
SEEDS = (1, 2, 3, 17, 183, 404)


def _build(seed, **options):
    return setup_multiworld(ctrAPWorld, seed=seed, options=options)


def _filled(seed, **options):
    mw = _build(seed, **options)
    distribute_items_restrictive(mw)
    return mw


def _violations(world):
    """[(racer, location name)] for every unlock item on a forbidden check."""
    forbidden = racer_lock_forbidden_locations(world)
    out = []
    for loc in world.multiworld.get_filled_locations(world.player):
        item = loc.item
        if item is None or item.player != world.player:
            continue
        if loc in forbidden.get(item.name, ()):
            out.append((item.name, loc.name))
    return out


class _FakeWorld:
    def __init__(self, seed):
        import random
        self.random = random.Random(seed)


class TestSpreadDraw(unittest.TestCase):

    CANDIDATES = [f"racer {i}" for i in range(15)]

    def test_no_repeat_until_every_candidate_is_used(self):
        for n in range(0, 16):
            with self.subTest(n=n):
                racers = spread_lock_racers(_FakeWorld(n), self.CANDIDATES, n)
                self.assertEqual(len(racers), n)
                self.assertEqual(len(set(racers)), n)

    def test_above_the_roster_every_racer_takes_floor_or_ceil(self):
        """Above 15 locks the bag refills: each racer locks
        floor(n/15) or ceil(n/15) pads, never more."""
        for n in (16, 22, 27, 30, 31, 45):
            with self.subTest(n=n):
                racers = spread_lock_racers(_FakeWorld(n), self.CANDIDATES, n)
                per = Counter(racers)
                self.assertEqual(len(racers), n)
                self.assertLessEqual(max(per.values()), math.ceil(n / 15))
                self.assertEqual(set(per), set(self.CANDIDATES)
                                 if n >= 15 else set(per))
                self.assertGreaterEqual(min(per.values()), n // 15)

    def test_no_candidates_draws_nothing(self):
        self.assertEqual(spread_lock_racers(_FakeWorld(1), [], 5), [])


class TestSpreadInGeneration(unittest.TestCase):

    def test_generated_locks_respect_the_cap(self):
        for requested in (9, 15, 20, 27):
            for seed in SEEDS[:3]:
                with self.subTest(requested=requested, seed=seed):
                    world = _build(seed, racer_locked_pads=requested,
                                   gems_required_goal=5,
                                   oxide_goal="none").worlds[1]
                    locks = world.ctr_racer_locks
                    per = Counter(locks.values())
                    self.assertTrue(locks)
                    self.assertLessEqual(max(per.values()),
                                         math.ceil(len(locks) / 15))
                    self.assertNotIn(world.ctr_starting_character, per)

    def test_config_d_seed_183_no_longer_stacks_one_racer(self):
        """Research regression: on the old draw Crash locked four pads here,
        including the Yellow Cup pad that loads Polar Pass."""
        world = _build(183, **CONFIG_D).worlds[1]
        self.assertEqual(len(world.ctr_racer_locks), 9)
        self.assertEqual(max(Counter(world.ctr_racer_locks.values()).values()),
                         1)


class TestForbiddenSet(unittest.TestCase):


    def test_item_rule_rejects_only_the_owning_racer(self):
        world = _build(183, **CONFIG_D).worlds[1]
        forbidden = racer_lock_forbidden_locations(world)
        racer, locs = next(iter(forbidden.items()))
        other = next(r for r in ROSTER
                     if r != racer and r != world.ctr_starting_character)
        own_item = world.create_item(unlock_item_name(racer))
        other_item = world.create_item(unlock_item_name(other))
        for loc in locs:
            self.assertFalse(loc.item_rule(own_item), loc.name)
            if other not in forbidden or loc not in forbidden[other]:
                self.assertTrue(loc.item_rule(other_item), loc.name)


if __name__ == "__main__":
    unittest.main()
