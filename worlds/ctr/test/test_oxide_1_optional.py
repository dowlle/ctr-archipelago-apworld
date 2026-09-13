"""Optional-first wire, reachability and UT contract without deleting rewards."""
import unittest
from pathlib import Path
import yaml

from worlds.AutoWorld import call_all
from BaseClasses import ItemClassification
from test.general import setup_multiworld
from .. import ctrAPWorld
from .test_oxide_access_contract import (
    _build, _reach, _boss_flags, FIRST, FINAL, KEYS, RELICS, RELIC_OPTS, STEPS,
)


class TestOxide1Optional(unittest.TestCase):
    def test_filler_tight_pool_reserves_excluded_reward_with_capabilities(self):
        from ..elastic_bounds import estimated_filler_reserve
        options=yaml.safe_load((Path(__file__).parent / "fixtures/oxide_filler_tight_pool.yaml").read_text())[ctrAPWorld.game]
        mw=_build(seed=159968982, **options)
        self.assertEqual(mw.get_location(FIRST,1).item.classification,ItemClassification.filler)
        self.assertGreaterEqual(sum(item.classification==ItemClassification.filler for item in mw.itempool),
                                estimated_filler_reserve(mw.worlds[1]))
        self.assertEqual(len(mw.get_unfilled_locations(1)),len(mw.itempool))

    def test_default_is_mandatory_and_only_final_goal_activates_option(self):
        for goal in ("none", "any_percent", "101_percent", "disabled"):
            for enabled in (False, True, "filler", "true_filler"):
                with self.subTest(goal=goal, enabled=enabled):
                    mw = _build(oxide_goal=goal, oxide_1_optional=enabled,
                                bosses_required_goal=2, **RELIC_OPTS)
                    wire = mw.worlds[1].fill_slot_data()
                    self.assertEqual(wire["schema_version"], 15)
                    self.assertEqual(wire["ctr_options"]["schema_version"], 15)
                    self.assertEqual(wire["ctr_options"]["oxide_1_optional"],
                                     (2 if enabled in ("filler", "true_filler") else int(enabled))
                                     if goal == "101_percent" else 0)
        wire = _build(oxide_goal="final").worlds[1].fill_slot_data()
        self.assertEqual(wire["ctr_options"]["oxide_1_optional"], 0)

    def test_rewards_ids_and_final_companions_preserved(self):
        for enabled in (False, True, "true_filler"):
            mw = _build(oxide_goal="final", oxide_1_optional=enabled,
                        bosses_required_goal=2, **RELIC_OPTS)
            self.assertEqual(mw.get_location(FIRST, 1).address, 35011104)
            self.assertEqual(mw.get_location(FINAL, 1).address, 35011105)
            flags = _boss_flags(mw)
            self.assertEqual(_reach(mw, KEYS), (True, False))
            self.assertEqual(_reach(mw, KEYS + RELICS), (True, False))
            self.assertEqual(_reach(mw, KEYS + flags[:2]), (True, False))
            self.assertEqual(_reach(mw, KEYS + RELICS + flags[:2]), (True, True))
            # The first reward can still supply a missing final prerequisite;
            # the optional selector only takes over after all terms are met.
            self.assertEqual(_reach(mw, KEYS + RELICS + flags[:1]), (True, False))

    def test_ut_restores_connected_room_not_local_toggle(self):
        for enabled in (False, True, "true_filler"):
            original = _build(oxide_goal="final", oxide_1_optional=enabled,
                              bosses_required_goal=2, **RELIC_OPTS)
            wire = original.worlds[1].fill_slot_data()
            rebuilt = setup_multiworld(ctrAPWorld, steps=(), seed=12,
                                      options={"oxide_1_optional": not enabled})
            rebuilt.re_gen_passthrough = {ctrAPWorld.game: wire}
            for step in STEPS:
                call_all(rebuilt, step)
            self.assertEqual(rebuilt.worlds[1].options.oxide_1_optional.value,
                             2 if enabled == "true_filler" else int(enabled))
            for mw in (original, rebuilt):
                flags = _boss_flags(mw)
                self.assertEqual(_reach(mw, KEYS + RELICS), (True, False))
                self.assertEqual(_reach(mw, KEYS + RELICS + flags[:2]), (True, True))

    def test_older_room_ignores_local_enabled_toggle(self):
        wire = _build(oxide_goal="final").worlds[1].fill_slot_data()
        del wire["ctr_options"]["oxide_1_optional"]
        rebuilt = setup_multiworld(ctrAPWorld, steps=(), seed=13,
                                  options={"oxide_1_optional": True})
        rebuilt.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in STEPS:
            call_all(rebuilt, step)
        self.assertEqual(rebuilt.worlds[1].options.oxide_1_optional.value, 0)

    def test_true_filler_locked_even_with_all_traps_and_capacity_balanced(self):
        for traps in (0, 100):
            for pads in ("vanilla", "randomized"):
                with self.subTest(traps=traps, pads=pads):
                    mw = _build(oxide_goal="final", oxide_1_optional="true_filler",
                                trap_fill_percentage=traps,
                                warppad_unlock_requirements=pads, **RELIC_OPTS)
                    loc = mw.get_location(FIRST, 1)
                    self.assertTrue(loc.locked)
                    self.assertEqual(loc.item.name, "Wumpa Fruit")
                    self.assertEqual(loc.item.classification, ItemClassification.filler)
                    self.assertEqual(loc.item.player, 1)
                    self.assertEqual(len(mw.get_unfilled_locations(1)),
                                     sum(item.player == 1 for item in mw.itempool))

    def test_other_goals_do_not_lock_first_reward(self):
        for goal in ("none", "any_percent"):
            mw = _build(oxide_goal=goal, oxide_1_optional="true_filler",
                        bosses_required_goal=2, **RELIC_OPTS)
            self.assertFalse(mw.get_location(FIRST, 1).locked)

    def test_malformed_wire_modes_do_not_enable_skip(self):
        wire = _build(oxide_goal="final").worlds[1].fill_slot_data()
        for bad in (True, False, 1.5, 2.5, "true_filler", None, 4294967297):
            with self.subTest(bad=bad):
                wire["ctr_options"]["oxide_1_optional"] = bad
                rebuilt = setup_multiworld(ctrAPWorld, steps=(), seed=13,
                                          options={"oxide_1_optional": True})
                rebuilt.worlds[1]._ut_restore_options(wire)
                self.assertEqual(rebuilt.worlds[1].options.oxide_1_optional.value, 0)

    def test_early_sizer_accounts_for_locked_first_slot(self):
        from ..rung_sizer import _base_location_supply, predicted_mandatory_pool
        optional = _build(oxide_goal="final", oxide_1_optional=True, **RELIC_OPTS)
        filler = _build(oxide_goal="final", oxide_1_optional="true_filler", **RELIC_OPTS)
        self.assertEqual(_base_location_supply(filler.worlds[1]),
                         _base_location_supply(optional.worlds[1]) - 1)
        self.assertEqual(predicted_mandatory_pool(filler.worlds[1]),
                         predicted_mandatory_pool(optional.worlds[1]))
