import unittest

from BaseClasses import CollectionState

from . import CTRTestBase
from test.general import setup_multiworld
from .. import ctrAPWorld

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


class TestOxideFinalVenue(CTRTestBase):
    pass


class TestOxideStationFinalVenue(CTRTestBase):
    options = {"oxide_final_track": "oxide_station"}


class TestCortexVortexWumpaIdentity(CTRTestBase):
    options = {"wumpa_check": "per_track"}


class TestOxideStationDoesNotMintCortexVortexWumpa(CTRTestBase):
    options = {"wumpa_check": "per_track", "oxide_final_track": "oxide_station"}


class TestDisabledOxideDoesNotMintCortexVortexWumpa(CTRTestBase):
    options = {"wumpa_check": "per_track", "oxide_goal": "disabled",
               "bosses_required_goal": 1}


class TestOxideFinalVenueGenerationMatrix(CTRTestBase):
    pass


class TestCortexVortexFinalNeedsUsf(unittest.TestCase):
    """Cortex Vortex cannot be finished without USF, so winning the Final
    Challenge there needs two Progressive Boosts with no hard-shortcut escape.
    The Wumpa check fires mid-race and stays free of the finish term."""

    VORTEX = "Cortex Vortex: Reach 10 Wumpa"
    FINAL = "N. Oxide Garage: N. Oxide's Final Challenge"
    BASE = ["Key"] * 4 + ["Sapphire Relic"] * 18

    def _state(self, mw, boosts):
        state = CollectionState(mw)
        for name in self.BASE + ["Progressive Boost"] * boosts:
            state.add_item(name, 1, 1)
        state.stale[1] = True
        return state

    def _build(self, **options):
        return setup_multiworld(ctrAPWorld, STEPS, seed=1, options={
            "wumpa_check": "per_track", "progressive_boost": "shared_global",
            **options})

    def test_final_challenge_needs_usf_even_with_hard_shortcut_knowledge(self):
        for knowledge in ("medium", "hard"):
            mw = self._build(shortcut_knowledge=knowledge)
            final = mw.get_location(self.FINAL, 1)
            for boosts, expected in ((0, False), (1, False), (2, True)):
                with self.subTest(knowledge=knowledge, boosts=boosts):
                    self.assertEqual(final.can_reach(self._state(mw, boosts)),
                                     expected)


    def test_101_goal_needs_usf_on_cortex_vortex(self):
        mw = self._build(oxide_goal="101_percent", shortcut_knowledge="hard")
        event = mw.get_location("N. Oxide's Final Challenge Cleared", 1)
        for boosts, expected in ((0, False), (2, True)):
            with self.subTest(boosts=boosts):
                state = self._state(mw, boosts)
                self.assertEqual(event.can_reach(state), expected)
                if expected:
                    state.collect(event.item, True, event)
                self.assertEqual(mw.has_beaten_game(state, 1), expected)

    def test_oxide_station_venue_keeps_its_rules(self):
        mw = self._build(oxide_final_track="oxide_station",
                         oxide_goal="101_percent", shortcut_knowledge="hard")
        self.assertFalse(mw.get_location(self.FINAL, 1).can_reach(
            self._state(mw, 0)))
        self.assertTrue(mw.get_location(self.FINAL, 1).can_reach(
            self._state(mw, 1)))
