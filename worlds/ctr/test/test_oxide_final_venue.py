import unittest

from BaseClasses import CollectionState

from . import CTRTestBase
from test.general import setup_multiworld
from .. import ctrAPWorld

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


class TestOxideFinalVenue(CTRTestBase):
    def test_default_is_exact_cortex_vortex_pair(self):
        wire = self.world.fill_slot_data()
        self.assertEqual(wire["schema_version"], 13)
        self.assertEqual(wire["ctr_options"]["oxide_final_track"], 0)
        self.assertEqual(wire["oxide_final_venue"], {
            "version": 1,
            "track": "cortex_vortex",
            "opponent": "nitros_oxide",
            "location": 35011105,
            "wumpa_location": -1,
            "host_level_id": 13,
            "lev_sha256": "4e3a2daf56c67be3ac645d3bb5375e516c828a0bca24c35ac69b3366c466fe13",
            "vrm_sha256": "4131444b9d1d53971befcfd11349efceaf887c20b795c8890fdcb2c36bdff07d",
        })


class TestOxideStationFinalVenue(CTRTestBase):
    options = {"oxide_final_track": "oxide_station"}

    def test_retail_choice_keeps_stable_encounter_identity(self):
        wire = self.world.fill_slot_data()
        venue = wire["oxide_final_venue"]
        self.assertEqual(wire["ctr_options"]["oxide_final_track"], 1)
        self.assertEqual(venue["track"], "oxide_station")
        self.assertEqual(venue["opponent"], "nitros_oxide")
        self.assertEqual(venue["location"], 35011105)
        self.assertEqual(venue["wumpa_location"], -1)

    def test_universal_tracker_restores_choice(self):
        wire = self.world.fill_slot_data()
        self.world.options.oxide_final_track.value = 0
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.oxide_final_track.value, 1)


class TestCortexVortexWumpaIdentity(CTRTestBase):
    options = {"wumpa_check": "per_track"}

    def test_has_an_independent_location_and_wire_code(self):
        wire = self.world.fill_slot_data()
        self.assertEqual(wire["oxide_final_venue"]["wumpa_location"], 35016121)
        location = self.multiworld.get_location(
            "Cortex Vortex: Reach 10 Wumpa", self.player)
        self.assertEqual(location.address, 35016121)


class TestOxideStationDoesNotMintCortexVortexWumpa(CTRTestBase):
    options = {"wumpa_check": "per_track", "oxide_final_track": "oxide_station"}

    def test_retail_final_keeps_only_the_retail_identity(self):
        wire = self.world.fill_slot_data()
        self.assertEqual(wire["oxide_final_venue"]["wumpa_location"], -1)
        with self.assertRaises(KeyError):
            self.multiworld.get_location(
                "Cortex Vortex: Reach 10 Wumpa", self.player)


class TestDisabledOxideDoesNotMintCortexVortexWumpa(CTRTestBase):
    options = {"wumpa_check": "per_track", "oxide_goal": "disabled",
               "bosses_required_goal": 1}

    def test_removed_encounter_has_no_wumpa_identity(self):
        wire = self.world.fill_slot_data()
        self.assertEqual(wire["oxide_final_venue"]["wumpa_location"], -1)
        with self.assertRaises(KeyError):
            self.multiworld.get_location(
                "Cortex Vortex: Reach 10 Wumpa", self.player)


class TestOxideFinalVenueGenerationMatrix(CTRTestBase):
    def test_both_venues_cross_goals_relic_modes_and_key_shuffle(self):
        for venue in ("cortex_vortex", "oxide_station"):
            for goal in ("none", "any_percent", "101_percent", "disabled"):
                for relic_mode in ("sapphire_relics", "gold_relics",
                                   "platinum_relics", "any_relic_type",
                                   "total_relics"):
                    for shuffle_keys in (False, True):
                        options = {
                            "oxide_final_track": venue,
                            "oxide_goal": goal,
                            "bosses_required_goal": 1,
                            "oxide_final_challenge_unlock": relic_mode,
                            "oxide_final_challenge_relic_count": 1,
                            "sapphire_relic_count": 1,
                            "gold_relic_count": 1,
                            "platinum_relic_count": 1,
                            "accessibility": "minimal",
                            "shuffle_keys": shuffle_keys,
                        }
                        with self.subTest(**options):
                            mw = setup_multiworld(ctrAPWorld, seed=321,
                                                  options=options)
                            wire = mw.worlds[1].fill_slot_data()
                            self.assertEqual(wire["oxide_final_venue"]["track"],
                                             venue)
                            self.assertEqual(wire["oxide_final_venue"]["location"],
                                             35011105)


class TestCortexVortexWumpaFollowsFinalChallenge(unittest.TestCase):
    """The check fires only during the Final Challenge race, so it must not be
    in logic at Oxide 1 access (four Keys) before the Final Challenge is."""

    VORTEX = "Cortex Vortex: Reach 10 Wumpa"
    FINAL = "N. Oxide Garage: N. Oxide's Final Challenge"
    BOSS_FLAGS = ("Ripper Roo Boss Race Won", "Papu Papu Boss Race Won",
                  "Komodo Joe Boss Race Won", "Pinstripe Boss Race Won")

    def _reach(self, mw, items):
        state = CollectionState(mw)
        for name in items:
            state.add_item(name, 1, 1)
        state.stale[1] = True
        return (mw.get_location(self.VORTEX, 1).can_reach(state),
                mw.get_location(self.FINAL, 1).can_reach(state))

    def test_keys_alone_do_not_reach_the_check(self):
        mw = setup_multiworld(ctrAPWorld, STEPS, seed=1,
                              options={"wumpa_check": "per_track"})
        self.assertEqual(self._reach(mw, ["Key"] * 4), (False, False))
        self.assertEqual(self._reach(mw, ["Key"] * 4 + ["Sapphire Relic"] * 18),
                         (True, True))

    def test_matches_the_final_challenge_in_every_goal_mode(self):
        for goal in ("none", "any_percent", "101_percent"):
            mw = setup_multiworld(ctrAPWorld, STEPS, seed=1, options={
                "wumpa_check": "per_track", "oxide_goal": goal,
                "bosses_required_goal": 1,
                "oxide_final_challenge_relic_count": 3})
            bosses = [mw.get_location(name, 1).item.name
                      for name in self.BOSS_FLAGS]
            for items in (["Key"] * 4,
                          ["Key"] * 4 + ["Sapphire Relic"] * 2,
                          ["Key"] * 4 + ["Sapphire Relic"] * 3,
                          ["Key"] * 4 + ["Sapphire Relic"] * 3 + bosses,
                          ["Key"] * 3 + ["Sapphire Relic"] * 3 + bosses):
                with self.subTest(goal=goal, items=len(items)):
                    vortex, final = self._reach(mw, items)
                    self.assertEqual(vortex, final)
