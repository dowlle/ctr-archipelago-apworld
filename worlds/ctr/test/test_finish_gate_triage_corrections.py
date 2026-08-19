"""The two 2026-08-19 triage finish-gate corrections.

1. Both Oxide goal events inherit Oxide Station's confirmed finish capability:
   a composed goal with an Oxide condition must not become true from Key 4 and
   the companion flag alone while the ordinary Oxide Station Trophy Race logic
   still demands the finish term. Medium needs exactly two Progressive Boosts;
   hard shortcut knowledge escapes the gate; an unrandomized boost chain keeps
   the term vacuous so legacy seeds are unchanged.

2. `N. Gin Labs: Platinum Time Trial` alone carries the USF term: without USF
   two of the track's item boxes are unreachable in a Relic Race, removing the
   ten-second perfect-box bonus and USF speed together. The track's Trophy
   Race, Sapphire, Gold and CTR Token Challenge stay ungated, and there is no
   hard-shortcut escape for this location.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..usf_finish import PLATINUM_USF_LOCATIONS, USF_BOOST_COUNT
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
LABS = "N. Gin Labs"
PLATINUM = f"{LABS}: Platinum Time Trial"


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _grant(state, player, item_names):
    for name in item_names:
        state.add_item(name, player, 1)


def _state_all_but_boost(mw, boost=0):
    """Every item in the seed except the boost chain, plus `boost` copies of
    it, so a False verdict can only come from the gate under test."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item != BOOST and not item.startswith(f"{BOOST} ("):
            state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


def _reachable(mw, state, name):
    return state.can_reach(name, "Location", PLAYER)


class TestOxideGoalFinishGate(unittest.TestCase):
    """completion_condition rows, evaluated on a scratch CollectionState with
    exactly the flags/items each row needs (the test_composable_goals probe)."""

    def _condition(self, mw):
        return mw.completion_condition[PLAYER]

    def _first_flag(self, mw):
        return mw.get_location("N. Oxide's Challenge Cleared", PLAYER).item.name

    def _final_flag(self, mw):
        return mw.get_location(
            "N. Oxide's Final Challenge Cleared", PLAYER).item.name

    def test_first_goal_boost_rows_on_medium(self):
        mw = _build(oxide_goal="first", progressive_boost="shared_global",
                    shortcut_knowledge="medium")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + [self._first_flag(mw)])
        self.assertFalse(cc(st), "flag + Key 4 with zero boosts must not win")
        _grant(st, PLAYER, [BOOST])
        self.assertFalse(cc(st), "one boost is below the USF rank")
        _grant(st, PLAYER, [BOOST])
        self.assertTrue(cc(st), "two boosts reach USF and complete the goal")

    def test_final_goal_boost_rows_on_medium(self):
        mw = _build(oxide_goal="final", progressive_boost="shared_global",
                    shortcut_knowledge="medium")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + ["Sapphire Relic"] * 18
               + [self._final_flag(mw)])
        self.assertFalse(cc(st), "relics + flag with zero boosts must not win")
        _grant(st, PLAYER, [BOOST])
        self.assertFalse(cc(st))
        _grant(st, PLAYER, [BOOST])
        self.assertTrue(cc(st))

    def test_hard_shortcut_knowledge_escapes_the_goal_gate(self):
        mw = _build(oxide_goal="first", progressive_boost="shared_global",
                    shortcut_knowledge="hard")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + [self._first_flag(mw)])
        self.assertTrue(cc(st), "hard knowledge keeps the bare-boost route")

    def test_unrandomized_boost_keeps_the_legacy_goal_shape(self):
        mw = _build(oxide_goal="first")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + [self._first_flag(mw)])
        self.assertTrue(cc(st), "vacuous term when the chain is not randomized")

    def test_composed_boss_conjunction_still_needs_the_finish_term(self):
        mw = _build(oxide_goal="first", bosses_required_goal=2,
                    progressive_boost="shared_global",
                    shortcut_knowledge="medium")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + [self._first_flag(mw)])
        _grant(st, PLAYER, ["Ripper Roo Boss Race Won", "Papu Papu Boss Race Won"])
        self.assertFalse(cc(st), "boss flags cannot substitute for the boosts")
        _grant(st, PLAYER, [BOOST] * USF_BOOST_COUNT)
        self.assertTrue(cc(st))

    def test_composed_gem_conjunction_still_needs_the_finish_term(self):
        mw = _build(oxide_goal="first", gems_required_goal=3,
                    progressive_boost="shared_global",
                    shortcut_knowledge="medium")
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, PLAYER, ["Key"] * 4 + [self._first_flag(mw)])
        _grant(st, PLAYER, ["Red Gem", "Green Gem", "Blue Gem"])
        self.assertFalse(cc(st), "gems cannot substitute for the boosts")
        _grant(st, PLAYER, [BOOST] * USF_BOOST_COUNT)
        self.assertTrue(cc(st))


class TestLabsPlatinumGate(unittest.TestCase):
    """The narrow Platinum-only location gate."""

    def test_the_ruled_set_is_exactly_the_labs_platinum(self):
        self.assertEqual(PLATINUM_USF_LOCATIONS, frozenset({PLATINUM}))

    def test_platinum_boost_rows(self):
        mw = _build(progressive_boost="shared_global", platinum_relic_count=18)
        self.assertFalse(_reachable(mw, _state_all_but_boost(mw, 0), PLATINUM))
        self.assertFalse(_reachable(mw, _state_all_but_boost(mw, 1), PLATINUM))
        self.assertTrue(_reachable(
            mw, _state_all_but_boost(mw, USF_BOOST_COUNT), PLATINUM))

    def test_sibling_locations_stay_ungated(self):
        mw = _build(progressive_boost="shared_global", platinum_relic_count=18)
        state = _state_all_but_boost(mw, 0)
        for name in (f"{LABS}: Trophy Race", f"{LABS}: Sapphire Time Trial",
                     f"{LABS}: Gold Time Trial", f"{LABS}: CTR Token Challenge"):
            self.assertTrue(_reachable(mw, state, name), name)

    def test_no_hard_shortcut_escape_for_platinum(self):
        mw = _build(progressive_boost="shared_global",
                    shortcut_knowledge="hard", platinum_relic_count=18)
        self.assertFalse(_reachable(mw, _state_all_but_boost(mw, 0), PLATINUM),
                         "route knowledge does not restore the two boxes")
        self.assertTrue(_reachable(
            mw, _state_all_but_boost(mw, USF_BOOST_COUNT), PLATINUM))

    def test_vacuous_when_the_boost_chain_is_not_randomized(self):
        mw = _build(platinum_relic_count=18)
        self.assertTrue(_reachable(mw, _state_all_but_boost(mw, 0), PLATINUM))


if __name__ == "__main__":
    unittest.main()
