"""Regression guard for the sphere-0 refusal (fuzz failures 32541, 6813 and
10634 of the 2026-10-01 generation-fixes run; refusal ruled the same
evening).

Four of the five fixture slots have zero locations reachable from their
starting inventory: Progressive Boost is randomized at easy or medium logic
difficulty, so every track the slot can reach first needs the first boost
rank (or weapon families), and no ungated location class is on. 0.2.3
refused all of them through the rung sizer's working margin; the 2026-10-01
refusal ruling admitted them, and then:

- 32541 (solo) only generated through the rollback backstop, which on the
  fuzz AP seed precollected the one Gem the goal needs; AP's accessibility
  check then raised on the empty first sphere;
- 6813 (two slots) failed the fill on about 1 in 6 AP seeds;
- 10634 (two slots, both empty) failed the fill on every AP seed.

They are now refused with a message that names the cause and the usual fix.
6813-1 has two reachable starting checks and still generates. See
sphere0_guard.py.
"""
import unittest
from pathlib import Path

import yaml

from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld, sphere0_guard

FIXTURES = Path(__file__).parent / "fixtures"
TO_RULES = ("generate_early", "create_regions", "create_items", "set_rules",
            "connect_entrances")
TO_BASIC = TO_RULES + ("generate_basic",)


def _options(name):
    doc = yaml.safe_load((FIXTURES / f"fuzz_20261001_{name}.yaml").read_text())
    return doc[ctrAPWorld.game]


class TestEmptySphere0Refused(unittest.TestCase):

    CASES = (("32541-0", 761311849), ("6813-0", 158194323),
             ("10634-0", 152696898), ("10634-1", 152696898))

    def test_each_empty_slot_is_refused(self):
        for name, seed in self.CASES:
            with self.subTest(slot=name):
                mw = setup_multiworld(ctrAPWorld, TO_RULES, seed=seed,
                                      options=_options(name))
                # Precondition: the fixture still reproduces the empty start.
                self.assertEqual(sphere0_guard.sphere0_breadth(mw.worlds[1]), 0)
                with self.assertRaises(OptionError) as cm:
                    sphere0_guard.raise_if_empty(mw.worlds[1])
                text = str(cm.exception)
                self.assertIn("no check it can reach at the start", text)
                self.assertIn("first Progressive Boost", text)
                self.assertIn("Item Box Locations", text)
                self.assertIn("logic_difficulty to hard", text)
                self.assertNotIn("—", text)

    def test_rooms_are_refused_at_generate_basic(self):
        for slots, seed in ((("6813-0", "6813-1"), 158194323),
                            (("10634-0", "10634-1"), 152696898)):
            with self.subTest(room=slots):
                with self.assertRaises(OptionError):
                    setup_multiworld([ctrAPWorld] * 2, TO_BASIC, seed=seed,
                                     options=[_options(s) for s in slots])


class TestNonEmptySphere0Untouched(unittest.TestCase):

    def test_slot_with_starting_checks_generates(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=158194323,
                              options=_options("6813-1"))
        self.assertGreater(sphere0_guard.sphere0_breadth(mw.worlds[1]), 0)

    def test_default_options(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=7)
        self.assertGreater(sphere0_guard.sphere0_breadth(mw.worlds[1]), 0)


class TestBackstopNeverCompletesGoal(unittest.TestCase):

    def test_goal_gem_is_flagged(self):
        mw = setup_multiworld(ctrAPWorld, TO_RULES, seed=761311849,
                              options=_options("32541-0"))
        world = mw.worlds[1]
        gem = next(i for i in mw.itempool
                   if i.player == 1 and i.name == "Green Gem")
        boost = next(i for i in mw.itempool
                     if i.player == 1 and i.name.startswith("Progressive Boost"))
        self.assertTrue(world._completes_goal_at_start(gem))
        self.assertFalse(world._completes_goal_at_start(boost))


if __name__ == "__main__":
    unittest.main()
