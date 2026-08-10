"""Tests for the elastic-option bounds mechanism (issue #179).

No elastic option exists on `main` yet (#109/#148 are unbuilt), so the pure
resolution logic and the host-veto helper are exercised against a small
synthetic test-only option and a lightweight duck-typed fake world -- not
against any part of CTR's real option surface. The excluded-location reserve
helpers ARE tested against real generation, because the thing they reserve
for (issue #27's goal exclusion, a player's own `exclude_locations`) exists
on `main` today independently of #179's own elastic options.
"""
import unittest

from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import podium
from ..elastic_bounds import (
    CTRSettings,
    ElasticCountOption,
    apply_elastic_veto,
    clamp_elastic_option,
    elastic_supply_ceiling,
    estimated_filler_reserve,
    exact_filler_reserve,
    goal_excluded_location_reserve,
    player_exclude_locations_reserve,
    resolve_elastic_bounds,
)


class _TestElasticCount(ElasticCountOption):
    """Synthetic elastic option: absolute 0-100, friendly 10-60. Test-only --
    never registered on any world's options_dataclass."""
    range_start = 0
    range_end = 100
    friendly_minimum = 10
    friendly_maximum = 60
    default = 10


class _TestElasticCountNoFriendlyBounds(ElasticCountOption):
    """Synthetic elastic option with no friendly bounds declared: both sides
    must fall back to the absolute range."""
    range_start = 5
    range_end = 50
    default = 5


class _FakeMultiWorld:
    def __init__(self, player_name="Tester"):
        self.player_name = {1: player_name}


class _FakeWorld:
    """Duck-typed stand-in for a World, carrying only what
    clamp_elastic_option/apply_elastic_veto touch: .options, .player,
    .multiworld.player_name, .settings.enforce_friendly_options."""

    def __init__(self, option_value, *, friendly=True):
        self.player = 1
        self.multiworld = _FakeMultiWorld()
        self.options = type("Options", (), {})()
        self.options.my_count = _TestElasticCount(option_value)
        self.settings = CTRSettings()
        self.settings.enforce_friendly_options = friendly


class TestElasticCountOptionBoundResolution(unittest.TestCase):
    """Pure classmethod resolution -- issue #179 invariant 1 (deterministic,
    no side effects)."""

    def test_friendly_bounds_are_tighter_than_absolute(self):
        self.assertEqual(_TestElasticCount.resolved_minimum(True), 10)
        self.assertEqual(_TestElasticCount.resolved_maximum(True), 60)

    def test_friendly_off_falls_back_to_absolute(self):
        self.assertEqual(_TestElasticCount.resolved_minimum(False), 0)
        self.assertEqual(_TestElasticCount.resolved_maximum(False), 100)

    def test_no_friendly_bounds_declared_falls_back_to_absolute_either_way(self):
        for friendly in (True, False):
            self.assertEqual(
                _TestElasticCountNoFriendlyBounds.resolved_minimum(friendly), 5)
            self.assertEqual(
                _TestElasticCountNoFriendlyBounds.resolved_maximum(friendly), 50)

    def test_friendly_bound_never_widens_past_absolute(self):
        # A subclass that (mis)declares a friendly bound outside its own
        # absolute range must still be clamped to the absolute range -- the
        # friendly bound can only narrow, never widen.
        class _Overshoot(ElasticCountOption):
            range_start = 0
            range_end = 20
            friendly_minimum = -5
            friendly_maximum = 999
            default = 0
        self.assertEqual(_Overshoot.resolved_minimum(True), 0)
        self.assertEqual(_Overshoot.resolved_maximum(True), 20)


class TestResolveElasticBounds(unittest.TestCase):
    def test_friendly_pair(self):
        self.assertEqual(
            resolve_elastic_bounds(_TestElasticCount, friendly=True), (10, 60))

    def test_absolute_pair(self):
        self.assertEqual(
            resolve_elastic_bounds(_TestElasticCount, friendly=False), (0, 100))

    def test_dynamic_ceiling_tightens_the_maximum(self):
        self.assertEqual(
            resolve_elastic_bounds(_TestElasticCount, friendly=True,
                                   dynamic_ceiling=30),
            (10, 30))

    def test_dynamic_ceiling_above_the_static_bound_has_no_effect(self):
        self.assertEqual(
            resolve_elastic_bounds(_TestElasticCount, friendly=True,
                                   dynamic_ceiling=999),
            (10, 60))

    def test_dynamic_ceiling_below_the_minimum_inverts_the_pair_without_raising(self):
        # A genuine per-seed infeasibility. resolve_elastic_bounds only
        # resolves numbers; it is the caller's job to decide what an
        # inverted pair means (clamp_elastic_option raises on it below).
        lo, hi = resolve_elastic_bounds(_TestElasticCount, friendly=True,
                                        dynamic_ceiling=3)
        self.assertEqual((lo, hi), (10, 3))
        self.assertGreater(lo, hi)


class TestClampElasticOption(unittest.TestCase):
    def test_value_already_in_friendly_bounds_is_untouched(self):
        world = _FakeWorld(30, friendly=True)
        message = clamp_elastic_option(world, "my_count")
        self.assertIsNone(message)
        self.assertEqual(world.options.my_count.value, 30)

    def test_value_above_friendly_maximum_is_clamped_down(self):
        world = _FakeWorld(90, friendly=True)
        message = clamp_elastic_option(world, "my_count")
        self.assertEqual(world.options.my_count.value, 60)
        self.assertIn("90", message)
        self.assertIn("60", message)

    def test_value_below_friendly_minimum_is_clamped_up(self):
        world = _FakeWorld(2, friendly=True)
        clamp_elastic_option(world, "my_count")
        self.assertEqual(world.options.my_count.value, 10)

    def test_friendly_off_only_enforces_the_absolute_range(self):
        world = _FakeWorld(90, friendly=False)
        message = clamp_elastic_option(world, "my_count")
        self.assertIsNone(message)
        self.assertEqual(world.options.my_count.value, 90)

    def test_explicit_friendly_argument_bypasses_world_settings(self):
        world = _FakeWorld(90, friendly=True)
        # world.settings says friendly, but the explicit arg wins.
        clamp_elastic_option(world, "my_count", friendly=False)
        self.assertEqual(world.options.my_count.value, 90)

    def test_dynamic_ceiling_below_resolved_minimum_raises_optionerror(self):
        world = _FakeWorld(50, friendly=True)
        with self.assertRaises(OptionError):
            clamp_elastic_option(world, "my_count", dynamic_ceiling=3)


class TestApplyElasticVeto(unittest.TestCase):
    def test_allowed_is_a_noop_regardless_of_activity(self):
        world = _FakeWorld(90)
        for active in (True, False):
            result = apply_elastic_veto(
                world, allowed=True, is_active=active, option_name="my_count",
                on_refuse="raise", reason="irrelevant")
            self.assertIsNone(result)
        self.assertEqual(world.options.my_count.value, 90)

    def test_disallowed_but_inactive_is_a_noop(self):
        world = _FakeWorld(90)
        result = apply_elastic_veto(
            world, allowed=False, is_active=False, option_name="my_count",
            on_refuse="raise", reason="irrelevant")
        self.assertIsNone(result)
        self.assertEqual(world.options.my_count.value, 90)

    def test_disallowed_and_active_raise_mode_raises(self):
        world = _FakeWorld(90)
        with self.assertRaises(OptionError) as ctx:
            apply_elastic_veto(
                world, allowed=False, is_active=True, option_name="my_count",
                on_refuse="raise", reason="host does not want this feature")
        self.assertIn("host does not want this feature", str(ctx.exception))

    def test_disallowed_and_active_replace_mode_mutates_and_logs(self):
        world = _FakeWorld(90)
        message = apply_elastic_veto(
            world, allowed=False, is_active=True, option_name="my_count",
            on_refuse="replace", replacement=0, reason="replaced by policy")
        self.assertEqual(world.options.my_count.value, 0)
        self.assertIn("replaced by policy", message)

    def test_replace_mode_without_a_replacement_value_is_a_programming_error(self):
        world = _FakeWorld(90)
        with self.assertRaises(ValueError):
            apply_elastic_veto(
                world, allowed=False, is_active=True, option_name="my_count",
                on_refuse="replace", reason="no replacement given")

    def test_unknown_on_refuse_is_a_programming_error(self):
        world = _FakeWorld(90)
        with self.assertRaises(ValueError):
            apply_elastic_veto(
                world, allowed=False, is_active=True, option_name="my_count",
                on_refuse="shrug", reason="bad mode")


class TestCTRSettingsDefaults(unittest.TestCase):
    def test_enforce_friendly_options_defaults_true(self):
        self.assertIs(CTRSettings().enforce_friendly_options, True)

    def test_world_settings_key_avoids_the_wire_ctr_options_name(self):
        # settings_key would default to "ctr_options" (folder "ctr" +
        # "_options"), identical in NAME to the slot_data Contract's
        # top-level ctr_options dict. Explicit override avoids that.
        self.assertEqual(ctrAPWorld.settings_key, "ctr")


class TestExcludedLocationReserve(unittest.TestCase):
    """Real generation: the goal-exclusion count and the player's own
    exclude_locations, and the gap between the estimate and the exact
    count that #28's "excluded but never created" finding predicts."""

    def _sample_track(self):
        return podium._trophy_tracks()[0]

    def test_default_goal_oxide_excludes_exactly_one_location(self):
        multiworld = setup_multiworld(ctrAPWorld, seed=1)
        world = multiworld.worlds[1]
        self.assertEqual(goal_excluded_location_reserve(world), 1)

    def test_allbosses_goal_excludes_no_location(self):
        multiworld = setup_multiworld(
            ctrAPWorld, seed=1,
            options={"oxide_goal": "none", "bosses_required_goal": 4})
        world = multiworld.worlds[1]
        self.assertEqual(goal_excluded_location_reserve(world), 0)

    def test_player_exclude_locations_reserve_counts_the_raw_yaml_set(self):
        track = self._sample_track()
        real_location = f"{track}: Trophy Race"
        multiworld = setup_multiworld(
            ctrAPWorld, seed=1, options={"exclude_locations": {real_location}})
        world = multiworld.worlds[1]
        self.assertEqual(player_exclude_locations_reserve(world), 1)

    def test_estimate_matches_exact_when_the_excluded_name_is_really_created(self):
        track = self._sample_track()
        real_location = f"{track}: Trophy Race"
        multiworld = setup_multiworld(
            ctrAPWorld, seed=1, options={"exclude_locations": {real_location}})
        world = multiworld.worlds[1]
        from worlds.generic.Rules import exclusion_rules
        exclusion_rules(multiworld, 1, world.options.exclude_locations.value)
        self.assertEqual(estimated_filler_reserve(world), 2)  # goal(1) + yaml(1)
        self.assertEqual(exact_filler_reserve(world), 2)

    def test_estimate_overcounts_a_never_created_excluded_name_conservatively(self):
        # Issue #28's finding: excluding a location this seed never creates
        # (a podium rung with podium checks off) is a silent no-op on the
        # real LocationProgressType. The estimate cannot know that at
        # create_items time and stays conservative (larger, never smaller).
        track = self._sample_track()
        never_created = podium.location_name(track, "held_1st")
        multiworld = setup_multiworld(
            ctrAPWorld, seed=1,
            options={
                "podium_placement_checks": False,
                "exclude_locations": {never_created},
            })
        world = multiworld.worlds[1]
        from worlds.generic.Rules import exclusion_rules
        exclusion_rules(multiworld, 1, world.options.exclude_locations.value)
        self.assertEqual(estimated_filler_reserve(world), 2)  # goal(1) + yaml(1)
        self.assertEqual(exact_filler_reserve(world), 1)  # goal(1) only
        self.assertGreater(estimated_filler_reserve(world),
                           exact_filler_reserve(world))


class TestElasticSupplyCeiling(unittest.TestCase):
    def test_subtracts_the_estimated_reserve_from_available_supply(self):
        multiworld = setup_multiworld(ctrAPWorld, seed=1)
        world = multiworld.worlds[1]
        self.assertEqual(goal_excluded_location_reserve(world), 1)
        self.assertEqual(elastic_supply_ceiling(world, available_supply=50), 49)

    def test_floors_at_zero_when_the_reserve_exceeds_supply(self):
        multiworld = setup_multiworld(ctrAPWorld, seed=1,
                                      options={"exclude_locations": {
                                          f"{podium._trophy_tracks()[0]}: Trophy Race"}})
        world = multiworld.worlds[1]
        # reserve is goal(1) + yaml(1) = 2, supply of 1 must floor at 0
        self.assertEqual(elastic_supply_ceiling(world, available_supply=1), 0)


if __name__ == "__main__":
    unittest.main()
