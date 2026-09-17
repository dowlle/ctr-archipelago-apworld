"""Approved 0.2.1 boost requirements at real location and event rules."""
import unittest

from test.general import setup_multiworld

from .. import ctrAPWorld
from .test_finish_gate_triage_corrections import _state_all_but_boost

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


class TestBoostReviewMatrix(unittest.TestCase):
    def build(self, **options):
        return setup_multiworld(ctrAPWorld, STEPS, seed=1, options={
            "progressive_boost": "shared_global", "platinum_relic_count": 18,
            "oxide_goal": "none", "bosses_required_goal": 4, **options})

    def test_platinum_difficulty_and_blue_fire(self):
        for difficulty, blue_fire, expected in (
                ("easy", False, 2), ("easy", True, 3),
                ("medium", False, 2), ("medium", True, 2),
                ("hard", False, 1)):
            mw = self.build(logic_difficulty=difficulty,
                            progressive_boost_blue_fire=blue_fire)
            loc = mw.get_location("Crash Cove: Platinum Time Trial", 1)
            with self.subTest(difficulty=difficulty, blue_fire=blue_fire):
                self.assertFalse(loc.can_reach(_state_all_but_boost(mw, expected - 1)))
                self.assertTrue(loc.can_reach(_state_all_but_boost(mw, expected)))

    def test_boss_venue_and_companion_events(self):
        mw = self.build(bosses_required_goal=4, shortcut_knowledge="medium",
                        oxide_final_track="oxide_station")
        for location, event, expected in (
                ("Ripper Roo Garage: Boss Race", "Ripper Roo Boss Race Won", 1),
                ("Papu Papu Garage: Boss Race", "Papu Papu Boss Race Won", 1),
                ("Komodo Joe Garage: Boss Race", "Komodo Joe Boss Race Won", 1),
                ("Pinstripe Garage: Boss Race", "Pinstripe Boss Race Won", 2)):
            for name in (location, event):
                with self.subTest(name=name):
                    loc = mw.get_location(name, 1)
                    self.assertFalse(loc.can_reach(_state_all_but_boost(mw, expected - 1)))
                    self.assertTrue(loc.can_reach(_state_all_but_boost(mw, expected)))

    def test_oxide_station_hard_shortcut_still_needs_one_boost(self):
        mw = self.build(shortcut_knowledge="hard", oxide_final_track="oxide_station")
        for name in ("N. Oxide Garage: N. Oxide's Challenge",
                     "N. Oxide Garage: N. Oxide's Final Challenge"):
            loc = mw.get_location(name, 1)
            self.assertFalse(loc.can_reach(_state_all_but_boost(mw, 0)))
            self.assertTrue(loc.can_reach(_state_all_but_boost(mw, 1)))

    def test_oxide_first_event_matches_win_at_station(self):
        mw = self.build(oxide_goal="any_percent", bosses_required_goal=0,
                        shortcut_knowledge="medium")
        for name in ("N. Oxide Garage: N. Oxide's Challenge",
                     "N. Oxide's Challenge Cleared"):
            loc = mw.get_location(name, 1)
            self.assertFalse(loc.can_reach(_state_all_but_boost(mw, 1)))
            self.assertTrue(loc.can_reach(_state_all_but_boost(mw, 2)))
