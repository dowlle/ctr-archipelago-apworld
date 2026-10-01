"""Regression guard for the sphere-0 opener (fuzz failures 32541, 6813 and
10634 of the 2026-10-01 generation-fixes run).

Each fixture slot has zero locations reachable from its starting inventory:
Progressive Boost is randomized at easy or medium logic difficulty, so every
track the slot can reach first needs the first boost rank (or weapon
families), and no ungated location class is on. 0.2.3 refused all five YAMLs
through the rung sizer's working margin; the 2026-10-01 refusal ruling admits
them. Without the opener:

- 32541 (solo) only generated through the rollback backstop, which on this
  AP seed precollected the one Gem the goal needs; the slot started with its
  goal complete and AP's accessibility check raised on the empty first sphere;
- 6813 (two slots) failed the fill on about 1 in 6 AP seeds;
- 10634 (two slots, both empty) failed the fill on every AP seed.

See sphere0_opener.py for the mechanism and the fix.
"""
import unittest
from pathlib import Path

import yaml

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import setup_multiworld

from .. import ctrAPWorld, sphere0_opener

FIXTURES = Path(__file__).parent / "fixtures"
STEPS = ("generate_early", "create_regions", "create_items", "set_rules",
         "connect_entrances", "generate_basic", "pre_fill")


def _options(name):
    doc = yaml.safe_load((FIXTURES / f"fuzz_20261001_{name}.yaml").read_text())
    return doc[ctrAPWorld.game]


class TestFuzzRoomsGenerate(unittest.TestCase):
    """The three fuzz rooms on their own AP seeds: every empty slot gets an
    opener, nobody starts with the goal complete, and the fill plus AP's
    accessibility check pass."""

    CASES = (
        ("32541", ("32541-0",), 761311849),
        ("6813", ("6813-0", "6813-1"), 158194323),
        ("10634", ("10634-0", "10634-1"), 152696898),
    )

    def test_rooms(self):
        for label, slots, seed in self.CASES:
            with self.subTest(fuzz=label):
                mw = setup_multiworld([ctrAPWorld] * len(slots), STEPS,
                                      seed=seed,
                                      options=[_options(s) for s in slots])
                opened = {p: w._ctr_sphere0_opener for p, w in mw.worlds.items()}
                self.assertTrue(any(opened.values()),
                                f"{label}: no slot had an empty sphere 0; the "
                                f"fixture no longer reproduces the failure")
                for p, world in mw.worlds.items():
                    self.assertGreater(sphere0_opener.sphere0_breadth(world), 0,
                                       f"{label} slot {p}: sphere 0 still empty")
                    self.assertFalse(
                        mw.has_beaten_game(CollectionState(mw), p),
                        f"{label} slot {p}: goal complete at the start")
                distribute_items_restrictive(mw)
                self.assertTrue(mw.fulfills_accessibility())
                self.assertTrue(mw.can_beat_game())


class TestOpenerChoice(unittest.TestCase):

    def test_moves_one_item_and_keeps_counts(self):
        mw = setup_multiworld(ctrAPWorld, STEPS[:5], seed=761311849,
                              options=_options("32541-0"))
        world = mw.worlds[1]
        self.assertEqual(sphere0_opener.sphere0_breadth(world), 0)
        pool_before = len(mw.itempool)
        start_before = len(mw.precollected_items[1])
        moved = sphere0_opener.apply(world)
        self.assertEqual(len(moved), 1)
        self.assertEqual(len(mw.itempool), pool_before)
        self.assertEqual(len(mw.precollected_items[1]), start_before + 1)
        self.assertEqual(mw.precollected_items[1][-1].name, moved[0])
        # The one-Gem goal: a Gem would complete it, so it is never chosen.
        self.assertNotIn("Gem", moved[0])
        self.assertFalse(mw.has_beaten_game(CollectionState(mw), 1))

    def test_never_picks_a_goal_item(self):
        mw = setup_multiworld(ctrAPWorld, STEPS[:5], seed=761311849,
                              options=_options("32541-0"))
        world = mw.worlds[1]
        gem = next(i for i in mw.itempool
                   if i.player == 1 and i.name == "Green Gem")
        self.assertTrue(world._completes_goal_at_start(gem))
        name, _opened = sphere0_opener.choose_opener(world)
        self.assertIsNotNone(name)
        self.assertNotIn("Gem", name)

    def test_open_sphere0_is_untouched(self):
        mw = setup_multiworld(ctrAPWorld, STEPS[:6], seed=7)
        world = mw.worlds[1]
        self.assertGreater(sphere0_opener.sphere0_breadth(world), 0)
        self.assertEqual(world._ctr_sphere0_opener, [])


if __name__ == "__main__":
    unittest.main()
