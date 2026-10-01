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

Round 2 of the same fuzz (36720, 6165, 14603) and the 2026-10-02 rulings:

- 36720 (solo, minimal) starts with two checks. 0.2.3's four early Keys and
  one or two early weapons took both, so the item that opens the next check
  had nowhere to go. CTR now requests no early Key and one early weapon; the
  slot is admitted and generates.
- 14603 (two slots, one full and one minimal) starts with one check per slot
  and failed the fill on about 1 in 12 AP seeds. A slot needs at least
  MIN_STARTING_CHECKS (two) starting checks, so both slots are refused.
- 6165 (two slots, full plus minimal) starts wider (2 to 13 checks) and is
  admitted. Its residual fill failures come from AP placing the minimal
  partner's items without an access check; no starting-check minimum that
  keeps every 0.2.3 seed closes them (research note, 2026-10-02).
"""
import unittest
from pathlib import Path

import yaml

from Fill import distribute_items_restrictive
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
                    sphere0_guard.raise_if_narrow(mw.worlds[1])
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


class TestNarrowStartRefused(unittest.TestCase):
    """14603: each slot reaches exactly one check at the start."""

    SEED = 313592192

    def test_each_one_check_slot_is_refused(self):
        for name in ("14603-0", "14603-1"):
            with self.subTest(slot=name):
                mw = setup_multiworld(ctrAPWorld, TO_RULES, seed=self.SEED,
                                      options=_options(name))
                # Precondition: the fixture still reproduces the one-check start.
                self.assertEqual(sphere0_guard.sphere0_breadth(mw.worlds[1]), 1)
                with self.assertRaises(OptionError) as cm:
                    sphere0_guard.raise_if_narrow(mw.worlds[1])
                text = str(cm.exception)
                self.assertIn("can reach only 1 check at the start", text)
                self.assertIn(f"at least {sphere0_guard.MIN_STARTING_CHECKS} "
                              f"needed", text)
                self.assertIn("Item Box Locations", text)
                self.assertIn("logic_difficulty to hard", text)
                self.assertNotIn("—", text)

    def test_room_is_refused_at_generate_basic(self):
        with self.assertRaises(OptionError):
            setup_multiworld([ctrAPWorld] * 2, TO_BASIC, seed=self.SEED,
                             options=[_options("14603-0"), _options("14603-1")])

    def test_minimum_is_two(self):
        # Three would refuse seeds 0.2.3 generates (2026-10-02 measurement).
        self.assertEqual(sphere0_guard.MIN_STARTING_CHECKS, 2)


class TestAdmittedStartsUntouched(unittest.TestCase):

    def test_slot_with_two_starting_checks_generates(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=158194323,
                              options=_options("6813-1"))
        self.assertGreaterEqual(sphere0_guard.sphere0_breadth(mw.worlds[1]),
                                sphere0_guard.MIN_STARTING_CHECKS)

    def test_default_options(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=7)
        self.assertGreaterEqual(sphere0_guard.sphere0_breadth(mw.worlds[1]),
                                sphere0_guard.MIN_STARTING_CHECKS)

    def test_6165_room_is_admitted(self):
        mw = setup_multiworld([ctrAPWorld] * 2, TO_BASIC, seed=996425125,
                              options=[_options("6165-0"), _options("6165-1")])
        for player in (1, 2):
            self.assertGreaterEqual(
                sphere0_guard.sphere0_breadth(mw.worlds[player]),
                sphere0_guard.MIN_STARTING_CHECKS)


class TestEarlyItemsLeaveAStartingCheckFree(unittest.TestCase):
    """36720: vanilla warp pads, Keys shuffled, Itemsanity, two starting
    checks. 0.2.3 requested four early Keys plus one or two weapons."""

    def test_36720_requests_no_key_and_one_weapon(self):
        for seed in (411837586, 1, 2, 3):
            with self.subTest(seed=seed):
                mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=seed,
                                      options=_options("36720-0"))
                early = mw.early_items.get(1, {})
                self.assertNotIn("Key", early)
                self.assertEqual(sum(early.values()), 1)
                self.assertGreater(
                    sphere0_guard.sphere0_breadth(mw.worlds[1]),
                    sum(early.values()))

    def test_36720_fills_on_the_fuzz_seed(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC + ("pre_fill",),
                              seed=411837586, options=_options("36720-0"))
        self.assertFalse(getattr(mw.worlds[1], "_ctr_backstop_fired", False))
        distribute_items_restrictive(mw)
        self.assertTrue(mw.fulfills_accessibility())
        self.assertTrue(mw.can_beat_game())

    def test_vanilla_shuffled_keys_request_no_early_key(self):
        mw = setup_multiworld(ctrAPWorld, TO_BASIC, seed=11, options={
            "warppad_unlock_requirements": "vanilla", "shuffle_keys": True})
        self.assertNotIn("Key", mw.early_items.get(1, {}))


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
