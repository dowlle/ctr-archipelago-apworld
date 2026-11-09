"""The two 2026-08-19 triage finish-gate corrections.

1. Both Oxide goal events inherit Oxide Station's confirmed finish capability:
   a composed goal with an Oxide condition must not become true from Key 4 and
   the companion flag alone while the ordinary Oxide Station Trophy Race logic
   still demands the finish term. Medium needs exactly two Progressive Boosts;
   hard shortcut knowledge escapes the gate; an unrandomized boost chain keeps
   the term vacuous so legacy seeds are unchanged.

2. Relic tier boost gates (extended by the 2026-08-21 ruling, which subsumes
   the original narrow Labs-Platinum entry): every Gold and Platinum Time
   Trial requires the first Progressive Boost, Hot Air Skyway and Oxide
   Station carry the full USF term on both tiers, and N. Gin Labs carries it
   on Platinum. Sapphire stays free, and no tier gate has a hard-shortcut
   escape.
"""
import unittest

from BaseClasses import CollectionState
from . import setup_multiworld

from .. import ctrAPWorld
from ..usf_finish import (
    FIRST_BOOST_COUNT,
    USF_BOOST_COUNT,
    USF_RELIC_GOLD_TRACKS,
    USF_RELIC_PLATINUM_TRACKS,
    relic_tier_boost_min,
)
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




class TestRelicTierBoostTable(unittest.TestCase):
    """The ruled per-track tier table (2026-08-21), as data."""

    ALL_TRACKS = (
        "Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway",
        "Coco Park", "Tiger Temple", "Papu's Pyramid", "Dingo Canyon",
        "Blizzard Bluff", "Dragon Mines", "Polar Pass", "Tiny Arena",
        "Hot Air Skyway", "Cortex Castle", "N. Gin Labs", "Oxide Station",
        "Slide Coliseum", "Turbo Track")

    def test_the_ruled_usf_sets(self):
        # Cortex Vortex (pad track, 2026-09-13 contract) takes the USF tier
        # for both, like Oxide Station.
        self.assertEqual(USF_RELIC_GOLD_TRACKS,
                         frozenset({"Hot Air Skyway", "Oxide Station",
                                    "Cortex Vortex"}))
        self.assertEqual(
            USF_RELIC_PLATINUM_TRACKS,
            frozenset({"Hot Air Skyway", "Oxide Station", "N. Gin Labs",
                       "Cortex Vortex"}))

    def test_every_gold_and_platinum_has_a_boost_floor(self):
        for track in self.ALL_TRACKS:
            self.assertEqual(
                relic_tier_boost_min(track, "Gold"),
                USF_BOOST_COUNT if track in USF_RELIC_GOLD_TRACKS
                else FIRST_BOOST_COUNT, track)
            self.assertEqual(
                relic_tier_boost_min(track, "Platinum"),
                USF_BOOST_COUNT if track in USF_RELIC_PLATINUM_TRACKS
                else FIRST_BOOST_COUNT, track)
            self.assertEqual(relic_tier_boost_min(track, "Sapphire"), 0, track)


class TestRelicTierBoostGates(unittest.TestCase):
    """The installed rules, on a real generation."""



    def test_sapphire_and_trophy_stay_ungated(self):
        """Sapphire carries no tier term and the Labs race is still on the
        difficulty rule only. The CTR Token Challenge left this list on
        2026-09-20: it now carries its own first-boost floor, asserted in the
        test below. Hard logic: since the 2026-09-27 ruling (#329) easy and
        medium gate the Labs race on one boost even with Itemsanity off, and
        a Sapphire Time Trial inherits its track's race rule."""
        mw = _build(progressive_boost="shared_global", platinum_relic_count=18,
                    logic_difficulty="hard")
        state = _state_all_but_boost(mw, 0)
        for name in (f"{LABS}: Trophy Race", f"{LABS}: Sapphire Time Trial",
                     "Crash Cove: Sapphire Time Trial"):
            self.assertTrue(_reachable(mw, state, name), name)

    def test_token_challenge_carries_the_first_boost_floor(self):
        """Ruling 2026-09-20. The floor is the token's own term, not a relic
        tier: it binds on a track whose race and Sapphire are both free."""
        mw = _build(progressive_boost="shared_global", platinum_relic_count=18)
        name = f"{LABS}: CTR Token Challenge"
        self.assertFalse(_reachable(mw, _state_all_but_boost(mw, 0), name))
        self.assertTrue(_reachable(
            mw, _state_all_but_boost(mw, FIRST_BOOST_COUNT), name))




if __name__ == "__main__":
    unittest.main()
