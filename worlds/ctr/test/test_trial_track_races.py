"""Generation, identity and wire gates for issue #203 trial-track races."""
import json
import unittest

from worlds.AutoWorld import call_all
from test.general import setup_multiworld
from .. import ctrAPWorld

from ..trial_trophy import TRIAL_TROPHY_CLASS
from . import CTRTestBase


class TestTrialPodiumUT(unittest.TestCase):
    def test_absent_and_partial_trial_rows_stay_exact(self):
        from ..podium import PODIUM_CLASS
        options = {"slide_coliseum_races":"trophy_race", "turbo_track_races":"trophy_race"}
        original = setup_multiworld(ctrAPWorld, options=options, seed=23)
        for row in (None, [35015200, -1, -1, -1, -1], (35015200, -1, -1, -1, -1)):
            wire = original.worlds[1].fill_slot_data()
            wire["podium_checks"]["locations"].pop("17", None)
            if row is None:
                wire["podium_checks"]["locations"].pop("16", None)
            else:
                wire["podium_checks"]["locations"]["16"]=row
            rebuilt = setup_multiworld(ctrAPWorld, options=options, steps=(), seed=24)
            rebuilt.re_gen_passthrough={ctrAPWorld.game:wire}
            for step in ("generate_early", "create_regions", "create_items", "set_rules"):
                call_all(rebuilt,step)
            names={loc.name for loc in rebuilt.get_locations(1)}
            for ti,track in enumerate(("Slide Coliseum","Turbo Track")):
                for key in ("held_1st","held_3rd","held_5th","finish_podium","finish_any"):
                    self.assertEqual(PODIUM_CLASS.location_name(track,key) in names,
                                     ti==0 and row is not None and key=="held_1st")
            emitted=rebuilt.worlds[1].fill_slot_data()["podium_checks"]["locations"]
            self.assertNotIn("17",emitted)
            if row is None: self.assertNotIn("16",emitted)
            else: self.assertEqual(emitted["16"],list(row))


class TestTrialTrackRacesOff(CTRTestBase):
    def test_default_is_inert(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertFalse(set(TRIAL_TROPHY_CLASS.names()) & names)
        wire = self.world.fill_slot_data()
        self.assertNotIn("trial_track_checks", wire)
        self.assertEqual(wire["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["slide_coliseum_races"], 0)
        self.assertEqual(wire["ctr_options"]["turbo_track_races"], 0)


class TestSlideTrophyOnly(CTRTestBase):
    options = {"slide_coliseum_races": "trophy_race"}

    def test_only_slide_trophy_is_created(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn("Slide Coliseum: Trophy Race", names)
        self.assertNotIn("Slide Coliseum: CTR Token Challenge", names)
        self.assertNotIn("Turbo Track: Trophy Race", names)
        self.assertEqual(self.world.fill_slot_data()["trial_track_checks"], {
            "enabled": True,
            "locations": {"16": [35016200, -1], "17": [-1, -1]},
        })


class TestBothFamilies(CTRTestBase):
    options = {
        "slide_coliseum_races": "trophy_and_ctr_challenge",
        "turbo_track_races": "trophy_and_ctr_challenge",
        "wumpa_check": "per_track",
    }

    def test_trial_podium_matches_selected_retail_rungs(self):
        from ..podium import PODIUM_CLASS, SLOT_ORDER
        wire = self.world.fill_slot_data()["podium_checks"]
        selected = PODIUM_CLASS.created_rung_keys(self.world.options)
        for ti, track in enumerate(("Slide Coliseum", "Turbo Track")):
            expected = [35015200 + ti*5 + ri if key in selected else -1
                        for ri, key in enumerate(SLOT_ORDER)]
            self.assertEqual(wire["locations"][str(16+ti)], expected)
            for key in selected:
                self.multiworld.get_location(PODIUM_CLASS.location_name(track, key), self.player)

    def test_both_tracks_create_four_checks_and_two_wumpa_routes(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertTrue(set(TRIAL_TROPHY_CLASS.names()) <= names)
        self.assertIn("Slide Coliseum: Reach 10 Wumpa", names)
        self.assertIn("Turbo Track: Reach 10 Wumpa", names)
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(wire["trial_track_checks"]["locations"], {
            "16": [35016200, 35016210],
            "17": [35016201, 35016211],
        })
        self.assertIn("16", wire["wumpa_checks"]["retail_tracks"])
        self.assertIn("17", wire["wumpa_checks"]["retail_tracks"])

    def test_universal_tracker_restores_both_options(self):
        wire = self.world.fill_slot_data()
        self.world.options.slide_coliseum_races.value = 0
        self.world.options.turbo_track_races.value = 0
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.slide_coliseum_races.value, 2)
        self.assertEqual(self.world.options.turbo_track_races.value, 2)
