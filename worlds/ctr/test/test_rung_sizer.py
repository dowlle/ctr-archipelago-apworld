"""Issue #71 adaptive podium-rung sizing.

The tests pin the nine effective ladder rows, upward-only selection, host and
master vetoes, live-pool prediction, and the retained #109 per-character
block.  No test relies on a future #109/#145 implementation: optional classes
are counted only through the live #176 registry.
"""
import unittest

from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld, podium, progressive_capability, rung_sizer, traps
from ..elastic_bounds import (goal_excluded_location_reserve,
                               predicted_goal_excluded_reserve)
from ..Options import OxideGoal


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


def _make_short_by(world, short_by=1):
    """Pad the raw exclude_locations option (counted by the sizer whether or
    not the names exist) until this world's demand sits `short_by` locations
    above the supply of its current rung layout: a seed that is really short."""
    current = rung_sizer.category_count(world.options)
    supply = rung_sizer.location_supply(world, current)
    world.options.exclude_locations.value = frozenset()
    pad = supply - rung_sizer._demand(world) + short_by
    world.options.exclude_locations.value = frozenset(
        f"synthetic exclude {i}" for i in range(max(pad, 0)))
    return rung_sizer._demand(world), supply


def _rungs_off(world):
    world.options.podium_finish_rungs.value = False
    world.options.podium_any_position_rung.value = False
    world.options.podium_held_rungs.value = False
    world.options.podium_held_fifth_rung.value = False


class TestRungSizingGeneration(unittest.TestCase):
    def test_legacy_host_opt_in_cannot_override_yaml(self):
        mw = setup_multiworld(ctrAPWorld, seed=711)
        world = mw.worlds[1]
        _rungs_off(world)
        world.options.progressive_boost.value = 1
        world.settings.allow_rung_sizing = True
        _make_short_by(world)
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        self.assertIn("will not turn disabled rung options back on", str(ctx.exception))
        self.assertEqual(rung_sizer.category_count(world.options), 0)
        self.assertFalse(world.options.podium_held_rungs.value)
        self.assertFalse(world.options.podium_held_fifth_rung.value)
        self.assertFalse(world.options.podium_finish_rungs.value)

    def test_margin_alone_never_refuses_a_held_opt_out(self):
        # Ruling 2026-10-01: refuse only when locations are really short. This
        # YAML fits with its own two categories; before the ruling the working
        # margin for a capability pack refused it. It now generates with the
        # player's layout untouched.
        for seed, capability in ((715, "progressive_boost"), (717, "progressive_stats")):
            with self.subTest(capability=capability):
                mw = setup_multiworld(
                    ctrAPWorld, seed=seed,
                    options={
                        "podium_placement_checks": True,
                        "podium_finish_rungs": True,
                        "podium_any_position_rung": True,
                        "podium_held_rungs": False,
                        "podium_held_fifth_rung": False,
                        capability: "shared_global",
                    })
                world = mw.worlds[1]
                self.assertEqual(rung_sizer.category_count(world.options), 2)
                self.assertFalse(world.options.podium_held_rungs.value)
                self.assertFalse(world.options.podium_held_fifth_rung.value)
                self.assertLessEqual(rung_sizer.required_categories(world), 2)
                self.assertGreater(rung_sizer.target_categories(world),
                                   rung_sizer.required_categories(world))

    def test_held_opt_out_fails_when_really_short(self):
        mw = setup_multiworld(
            ctrAPWorld, seed=715,
            options={
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": False,
                "podium_held_fifth_rung": False,
                "progressive_boost": "shared_global",
            })
        world = mw.worlds[1]
        demand, supply = _make_short_by(world)
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        message = str(ctx.exception)
        self.assertIn("will not turn disabled rung options back on", message)
        self.assertIn(f"needs {demand} locations", message)
        self.assertIn(f"has only {supply}", message)
        self.assertFalse(world.options.podium_held_rungs.value)

    def test_one_spare_location_is_not_refused(self):
        mw = setup_multiworld(ctrAPWorld, seed=718,
                              options={"progressive_boost": "shared_global",
                                       "box_locations": True})
        world = mw.worlds[1]
        _rungs_off(world)
        world.options.podium_placement_checks.value = False
        _make_short_by(world, short_by=0)
        self.assertIsNone(rung_sizer.apply_rung_sizing(world))
        _make_short_by(world, short_by=1)
        with self.assertRaises(OptionError):
            rung_sizer.apply_rung_sizing(world)

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

    def test_master_off_with_a_capability_pack_generates_when_it_fits(self):
        # Before 2026-10-01 every seed with Progressive Boost or Stats on and
        # Podium Placement Checks off was refused by the margin, whatever its
        # size. The master toggle stays off.
        mw = setup_multiworld(
            ctrAPWorld, seed=713,
            options={
                "podium_placement_checks": False,
                "progressive_boost": "shared_global",
                "box_locations": True,
            })
        world = mw.worlds[1]
        self.assertFalse(world.options.podium_placement_checks.value)
        self.assertEqual(rung_sizer.category_count(world.options), 0)

    def test_master_toggle_is_never_enabled(self):
        mw = setup_multiworld(ctrAPWorld, seed=713)
        world = mw.worlds[1]
        _rungs_off(world)
        world.options.podium_placement_checks.value = False
        world.options.progressive_boost.value = 1
        demand, supply = _make_short_by(world)
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        message = str(ctx.exception)
        self.assertIn("never turns that option on", message)
        self.assertFalse(world.options.podium_placement_checks.value)
        # 2026-10-01 wording: demand and supply, and the usual fix names the
        # progressive packs and Item Box Locations, not Character Unlocks.
        self.assertIn(f"needs {demand} locations", message)
        self.assertIn(f"has only {supply}", message)
        self.assertIn("Progressive Boost", message)
        self.assertIn("Item Box Locations", message)
        self.assertNotIn("Character Unlocks", message)

    def test_usual_fix_skips_item_box_locations_when_already_on(self):
        mw = setup_multiworld(
            ctrAPWorld, seed=719,
            options={"progressive_stats": "shared_global", "box_locations": True})
        world = mw.worlds[1]
        _rungs_off(world)
        world.options.podium_placement_checks.value = False
        _make_short_by(world)
        with self.assertRaises(OptionError) as ctx:
            rung_sizer.apply_rung_sizing(world)
        self.assertIn("Progressive Stats", str(ctx.exception))
        self.assertNotIn("Item Box Locations", str(ctx.exception))

    def test_host_veto_raises_instead_of_mutating(self):
        # Build a normal world first, then turn its live options into the tight
        # case and call the pure generate-early action directly.
        mw = setup_multiworld(ctrAPWorld, seed=714)
        world = mw.worlds[1]
        _rungs_off(world)
        world.options.progressive_boost.value = 1
        world.settings.allow_rung_sizing = False
        _make_short_by(world)
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
                    and item.name not in traps.ALL_TRAP_ITEM_NAMES)
                self.assertEqual(actual, expected)

    def test_predicted_goal_reserve_matches_installed_goal(self):
        matrices = (
            {},
            {"oxide_goal": "final"},
            {"oxide_goal": "none", "bosses_required_goal": 4},
            {"oxide_goal": "none", "gems_required_goal": 3},
            # Sonnet review, 2026-09-03: `disabled` (#320) was missing from
            # this matrix, which is exactly how the elastic-bounds twin
            # shipped untested against it.
            {"oxide_goal": "disabled", "bosses_required_goal": 4},
            {"oxide_goal": "disabled", "gems_required_goal": 3},
        )
        for seed, options in enumerate(matrices, start=730):
            with self.subTest(options=options):
                mw = setup_multiworld(ctrAPWorld, seed=seed, options=options)
                world = mw.worlds[1]
                self.assertEqual(predicted_goal_excluded_reserve(world.options),
                                 goal_excluded_location_reserve(world))

    def test_predicted_goal_excluded_reserve_zero_for_none_and_disabled(self):
        # 2026-09-03 repair: `predicted_goal_excluded_reserve` used to test
        # `oxide_goal.value != 0`, which happened to be right for `none` (0)
        # and any Oxide finale (1/2 -> 1) but wrongly predicted 1 for
        # `disabled` (3), which installs no goal-exclusion branch at all and
        # must predict 0 like `none`. Assert the canonical
        # `OxideGoal.oxide_is_goal` semantics directly, independent of any
        # live world.
        for value in (OxideGoal.option_none, OxideGoal.option_disabled):
            with self.subTest(oxide_goal=value):
                options = _Options.__new__(_Options)
                options.oxide_goal = _Toggle(value)
                self.assertEqual(predicted_goal_excluded_reserve(options), 0)
        for value in (OxideGoal.option_any_percent, OxideGoal.option_101_percent):
            with self.subTest(oxide_goal=value):
                options = _Options.__new__(_Options)
                options.oxide_goal = _Toggle(value)
                self.assertEqual(predicted_goal_excluded_reserve(options), 1)

    def test_disabled_goal_at_rung_ceiling_not_rejected_by_reserve_overestimate(self):
        """Boundary regression for the Sonnet review's blocker.

        Builds a real `disabled`-goal world, then uses the raw
        `exclude_locations` YAML option (whose count feeds `required_categories`
        unconditionally, regardless of whether the names exist -- see
        `player_exclude_locations_reserve`) to pad demand until it sits exactly
        on the five-category ceiling: `demand == base + len(TROPHY_TRACKS) * 5`.
        At that exact boundary the fixed predictor (reserve 0 for `disabled`)
        must still find a home (`required_categories(world) == 5`), while the
        pre-repair predictor (reserve 1 for `disabled`) would have pushed
        demand one location past every reachable category ceiling and forced
        a spurious `OptionError`. A parallel `any_percent` seed at the same
        margin proves a true Oxide goal still reserves its one location: an
        identical pad there sits one location OVER the ceiling on purpose,
        which the fixed predictor (correctly reserving 1) still rejects.
        """
        mw = setup_multiworld(
            ctrAPWorld, seed=741,
            options={"oxide_goal": "disabled", "bosses_required_goal": 4})
        world = mw.worlds[1]
        self.assertEqual(predicted_goal_excluded_reserve(world.options), 0)
        base = rung_sizer._base_location_supply(world)
        ceiling = base + len(podium.TROPHY_TRACKS) * 5
        mandatory = rung_sizer.predicted_mandatory_pool(world)
        pad_to_ceiling = ceiling - mandatory
        self.assertGreater(pad_to_ceiling, 0)
        world.options.exclude_locations.value = frozenset(
            f"synthetic exclude {i}" for i in range(pad_to_ceiling))
        # Exact boundary: demand == ceiling. The fixed reserve (0) fits.
        self.assertEqual(rung_sizer.required_categories(world), 5)
        # What the pre-repair reserve (1 for `disabled`) would have computed:
        # one location past every reachable category, i.e. rejected.
        buggy_demand = mandatory + 1 + pad_to_ceiling
        self.assertGreater(buggy_demand, ceiling)

        # A true Oxide goal (`any_percent`) genuinely does reserve one
        # location. The identical pad there lands exactly where `disabled`'s
        # buggy predictor incorrectly landed: one location over the ceiling,
        # and the FIXED predictor for a real Oxide goal correctly rejects it.
        mw_goal = setup_multiworld(
            ctrAPWorld, seed=742,
            options={"oxide_goal": "any_percent"})
        world_goal = mw_goal.worlds[1]
        self.assertEqual(predicted_goal_excluded_reserve(world_goal.options), 1)
        base_goal = rung_sizer._base_location_supply(world_goal)
        ceiling_goal = base_goal + len(podium.TROPHY_TRACKS) * 5
        mandatory_goal = rung_sizer.predicted_mandatory_pool(world_goal)
        pad_goal = ceiling_goal - mandatory_goal - 1
        self.assertGreater(pad_goal, 0)
        world_goal.options.exclude_locations.value = frozenset(
            f"synthetic exclude {i}" for i in range(pad_goal))
        self.assertEqual(rung_sizer.required_categories(world_goal), 5)
        world_goal.options.exclude_locations.value = frozenset(
            f"synthetic exclude {i}" for i in range(pad_goal + 1))
        self.assertIsNone(rung_sizer.required_categories(world_goal))

    def test_supply_poor_per_character_gets_numeric_capability_error(self):
        with self.assertRaises(OptionError) as ctx:
            setup_multiworld(ctrAPWorld, seed=740,
                             options={"progressive_stats": "per_character"})
        self.assertIn("would add 192 item(s)", str(ctx.exception))
        self.assertIn("stats=per_character", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
