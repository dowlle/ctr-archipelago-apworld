"""Issue #71 adaptive podium-rung sizing.

The tests pin the nine effective ladder rows, upward-only selection, host and
master vetoes, live-pool prediction, and the retained #109 per-character
block.  No test relies on a future #109/#145 implementation: optional classes
are counted only through the live #176 registry.
"""
import unittest

from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld, podium, progressive_capability, rung_sizer
from ..elastic_bounds import (goal_excluded_location_reserve,
                               predicted_goal_excluded_reserve)


class _Toggle:
    def __init__(self, value):
        self.value = value


class _Options:
    def __init__(self, *, master=True, finish=False, any_position=False,
                 held=False, fifth=False):
        self.podium_placement_checks = _Toggle(master)
        self.podium_finish_rungs = _Toggle(finish)
        self.podium_any_position_rung = _Toggle(any_position)
        self.podium_held_rungs = _Toggle(held)
        self.podium_held_fifth_rung = _Toggle(fifth)


class TestRungLadder(unittest.TestCase):
    def test_all_nine_effective_rows_have_the_ruled_category_count(self):
        expected = (0, 1, 2, 2, 3, 3, 4, 4, 5)
        self.assertEqual(
            tuple(row.categories for row in rung_sizer.RUNG_LADDER), expected)

    def test_category_count_honours_the_master_toggle(self):
        options = _Options(master=False, finish=True, any_position=True,
                           held=True, fifth=True)
        self.assertEqual(rung_sizer.category_count(options), 0)

    def test_reachable_rows_never_disable_an_inert_child_toggle(self):
        options = _Options(master=True, finish=False, any_position=True)
        self.assertTrue(all(row.any_position for row in rung_sizer.rows_reachable_from(options)))


class TestRungSizingGeneration(unittest.TestCase):
    def test_legacy_host_opt_in_cannot_override_yaml(self):
        mw = setup_multiworld(ctrAPWorld, seed=711)
        world = mw.worlds[1]
        world.options.podium_finish_rungs.value = False
        world.options.podium_any_position_rung.value = False
        world.options.podium_held_rungs.value = False
        world.options.podium_held_fifth_rung.value = False
        world.options.progressive_boost.value = 1
        world.settings.allow_rung_sizing = True
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        self.assertIn("will not turn disabled rung options back on", str(ctx.exception))
        self.assertEqual(rung_sizer.category_count(world.options), 0)
        self.assertFalse(world.options.podium_held_rungs.value)
        self.assertFalse(world.options.podium_held_fifth_rung.value)
        self.assertFalse(world.options.podium_finish_rungs.value)

    def test_held_opt_out_fails_instead_of_silently_expanding(self):
        for capability in ("progressive_boost", "progressive_stats"):
            with self.subTest(capability=capability), self.assertRaises(OptionError) as ctx:
                setup_multiworld(
                    ctrAPWorld, seed=715,
                    options={
                        "podium_placement_checks": True,
                        "podium_finish_rungs": True,
                        "podium_any_position_rung": True,
                        "podium_held_rungs": False,
                        "podium_held_fifth_rung": False,
                        capability: "shared_global",
                    })
            self.assertIn("will not turn disabled rung options back on", str(ctx.exception))

    def test_box_supply_preserves_held_opt_out_under_capability_pressure(self):
        mw = setup_multiworld(
            ctrAPWorld, seed=716,
            options={
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": False,
                "podium_held_fifth_rung": False,
                "progressive_boost": "shared_global",
                "box_locations": True,
            })
        world = mw.worlds[1]
        self.assertEqual(rung_sizer.category_count(world.options), 2)
        self.assertFalse(world.options.podium_held_rungs.value)
        self.assertFalse(world.options.podium_held_fifth_rung.value)

    def test_sufficient_default_layout_is_a_noop(self):
        mw = setup_multiworld(ctrAPWorld, seed=712)
        world = mw.worlds[1]
        before = tuple(getattr(world.options, name).value
                       for name in rung_sizer._TOGGLE_NAMES)
        self.assertIsNone(rung_sizer.apply_rung_sizing(world))
        after = tuple(getattr(world.options, name).value
                      for name in rung_sizer._TOGGLE_NAMES)
        self.assertEqual(after, before)

    def test_master_toggle_is_never_enabled(self):
        with self.assertRaises(OptionError) as ctx:
            setup_multiworld(
                ctrAPWorld, seed=713,
                options={
                    "podium_placement_checks": False,
                    "progressive_boost": "shared_global",
                })
        self.assertIn("never enables that master toggle", str(ctx.exception))

    def test_host_veto_raises_instead_of_mutating(self):
        # Build a normal world first, then turn its live options into the tight
        # case and call the pure generate-early action directly.
        mw = setup_multiworld(ctrAPWorld, seed=714)
        world = mw.worlds[1]
        world.options.podium_finish_rungs.value = False
        world.options.podium_any_position_rung.value = False
        world.options.podium_held_rungs.value = False
        world.options.podium_held_fifth_rung.value = False
        world.options.progressive_boost.value = 1
        world.settings.allow_rung_sizing = False
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        self.assertIn("will not turn disabled rung options back on", str(ctx.exception))
        self.assertEqual(rung_sizer.category_count(world.options), 0)

    def test_prediction_matches_live_non_filler_pool_across_option_matrix(self):
        matrices = (
            {},
            {"shuffle_gems": False, "shuffle_keys": False,
             "include_battle_arenas": False},
            {"oxide_goal": "none", "bosses_required_goal": 4},
            {"oxide_goal": "none", "gems_required_goal": 3,
             "shuffle_gems": False, "include_gem_cups": True},
            {"progressive_boost": "shared_global",
             "progressive_boost_blue_fire": True,
             "progressive_stats": "shared_global"},
            # DeepSeek review F1/F2 (2026-08-11): the shapes the merged
            # #145/#109 features add. Itemsanity activates 11 frozen-at-zero
            # weapon items; box locations add supply but no items; the
            # combined shape exercises both sides of the ledger at once.
            {"itemsanity": True},
            {"box_locations": True, "shortcut_knowledge": "hard"},
            {"itemsanity": True, "box_locations": True,
             "shortcut_knowledge": "medium",
             "progressive_boost": "shared_global",
             "progressive_stats": "shared_global"},
        )
        for seed, options in enumerate(matrices, start=720):
            with self.subTest(options=options):
                mw = setup_multiworld(ctrAPWorld, seed=seed, options=options)
                world = mw.worlds[1]
                expected = rung_sizer.predicted_mandatory_pool(world)
                actual = sum(
                    1 for item in mw.itempool if item.player == world.player
                    and item.name != "Wumpa Fruit"
                    and item.name not in rung_sizer._SURFACE_ITEM_NAMES
                    and item.name not in {"Icy Road Trap", "Low Gravity Trap",
                                          "No Brakes Trap", "Forced Boost Trap",
                                          "First Person Trap"})
                self.assertEqual(actual, expected)

    def test_predicted_goal_reserve_matches_installed_goal(self):
        matrices = (
            {},
            {"oxide_goal": "final"},
            {"oxide_goal": "none", "bosses_required_goal": 4},
            {"oxide_goal": "none", "gems_required_goal": 3},
        )
        for seed, options in enumerate(matrices, start=730):
            with self.subTest(options=options):
                mw = setup_multiworld(ctrAPWorld, seed=seed, options=options)
                world = mw.worlds[1]
                self.assertEqual(predicted_goal_excluded_reserve(world.options),
                                 goal_excluded_location_reserve(world))

    def test_supply_poor_per_character_gets_numeric_capability_error(self):
        with self.assertRaises(OptionError) as ctx:
            setup_multiworld(ctrAPWorld, seed=740,
                             options={"progressive_stats": "per_character"})
        self.assertIn("would add 192 item(s)", str(ctx.exception))
        self.assertIn("stats=per_character", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
