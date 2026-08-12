"""Tests for the option interaction / constraint matrix (issue #178,
worlds/ctr/forced_options.py).

Scope: the four already-shipping interaction groups named in the Atlas Run
that built this (podium sub-toggle inertness, gem-cup/arena includes,
two_stage_density, warp-pad modes), plus regression coverage for the three
pre-existing RAISE guards (#87, #50, #23) that moved into forced_options.py
unchanged. #50 already has direct coverage in test_gem_cups.py and #87 in
test_requirement_weights.py; this file adds #23's first direct unit test
(previously reachable only through full generation, never asserted on
directly) plus all seven new DOWNGRADE-WITH-WARNING cases.

Every DOWNGRADE test proves three things per constraint: the warning fires on
the conflicting combination, it does NOT fire on the matching non-conflicting
combination, and -- because this module is log-only by design (see
forced_options.py's module docstring) -- the option's own stored value is
byte-identical before and after forced_options.apply() runs, even when it
warned. That last assertion is the direct proof that a downgrade here never
reshapes a seed; it only reports what already-shipping generation logic does.
"""
import unittest

from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld, forced_options
from . import CTRTestBase

EARLY = ("generate_early",)
LOGGER_NAME = "worlds.ctr.forced_options"


def _early(options):
    return setup_multiworld(ctrAPWorld, EARLY, options=options)


# ---------------------------------------------------------------------------
# RAISE guards -- regression coverage for the move into forced_options.py.
# ---------------------------------------------------------------------------

class TestRaiseOxidefinalNoProgressionTier(unittest.TestCase):
    """Issue #23's guard (raise_if_oxidefinal_goal_has_no_progression_tier) had
    no direct unit test before this issue -- only reachable via a full
    generation run. Added here as part of verifying the migration, not as new
    behaviour: the guard body is byte-identical to what generate_early used to
    run inline.

    Sapphire is unconditionally progression on any oxidefinal seed (see
    _relic_progression_map's "mode-independent" comment), so a sapphire-tier
    goal can never trip this guard through the counts alone -- these tests use
    the gold tier, whose vanilla-mode progression is count-gated with no such
    exception. (Issue #171: the option was a 0-100 percentage slider, now a
    0-18 exact count; 0 still means "none of this tier", 18 is the new "all".)
    """

    def test_vanilla_mode_goal_tier_count_at_zero_raises(self):
        with self.assertRaises(OptionError) as ctx:
            _early({
                "oxide_goal": "final",
                "warppad_unlock_requirements": "vanilla",
                "oxide_final_challenge_unlock": "gold_relics",
                "gold_relic_count": 0,
            })
        self.assertIn("oxidefinal", str(ctx.exception))

    def test_vanilla_mode_goal_tier_count_above_zero_generates(self):
        # Non-conflicting: the goal's own tier has a created count > 0, and the
        # default oxide_final_challenge_relic_count (18) is exactly met.
        _early({
            "oxide_goal": "final",
            "warppad_unlock_requirements": "vanilla",
            "oxide_final_challenge_unlock": "gold_relics",
            "gold_relic_count": 18,
        })

    def test_randomized_mode_ignores_the_counts(self):
        # Randomized modes keep every tier progression regardless of count
        # value (_relic_progression_map returns early for unlock_mode != 0),
        # so the same zeroed count that raises in vanilla mode is safe here
        # (0 created also means the guard's "any(created >= n)" is vacuously
        # false for that tier, but oxide_final_challenge_relic_count defaults
        # to 18 and this test's mode targets ONLY gold -- 0 created gold with
        # a progression classification of True and n defaulting to 18 would
        # actually raise even in randomized mode now that the guard checks
        # created supply, not just classification, so this uses a count of 1
        # to keep the assertion about mode-independent classification without
        # colliding with the new supply check).
        _early({
            "oxide_goal": "final",
            "warppad_unlock_requirements": "randomized",
            "oxide_final_challenge_unlock": "gold_relics",
            "oxide_final_challenge_relic_count": 1,
            "gold_relic_count": 1,
        })


# ---------------------------------------------------------------------------
# DOWNGRADE guards -- podium sub-toggle inertness.
# ---------------------------------------------------------------------------

class TestPodiumSubtogglesInertness(unittest.TestCase):

    def test_master_off_warns_once_and_does_not_touch_suboptions(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "podium_placement_checks": False,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": True,
                "podium_held_fifth_rung": True,
            })
        world = mw.worlds[1]
        self.assertEqual(
            sum("Podium Placement Checks is off" in m for m in cm.output), 1)
        # Scoped to master-off only: the finish/held-specific warnings must not
        # also fire (that would be redundant with the master-off message).
        self.assertFalse(any("Any-Position Rung has no effect" in m for m in cm.output))
        self.assertFalse(any("Held 5th Rung has no effect" in m for m in cm.output))
        # Log-only: every sub-toggle keeps the exact value this test set.
        self.assertTrue(world.options.podium_finish_rungs.value)
        self.assertTrue(world.options.podium_any_position_rung.value)
        self.assertTrue(world.options.podium_held_rungs.value)
        self.assertTrue(world.options.podium_held_fifth_rung.value)

    def test_master_on_does_not_warn_about_subtoggles(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": True,
                "podium_held_fifth_rung": False,
            })

    def test_any_position_without_finish_warns(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": False,
                "podium_any_position_rung": True,
            })
        world = mw.worlds[1]
        self.assertTrue(any("Any-Position Rung has no effect" in m for m in cm.output))
        self.assertTrue(world.options.podium_any_position_rung.value)  # untouched

    def test_finish_on_does_not_warn_about_any_position(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
            })

    def test_held_fifth_without_held_warns(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "podium_placement_checks": True,
                "podium_held_rungs": False,
                "podium_held_fifth_rung": True,
            })
        world = mw.worlds[1]
        self.assertTrue(any("Held 5th Rung has no effect" in m for m in cm.output))
        self.assertTrue(world.options.podium_held_fifth_rung.value)  # untouched

    def test_held_on_does_not_warn_about_held_fifth(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_held_rungs": True,
                "podium_held_fifth_rung": True,
            })


# ---------------------------------------------------------------------------
# DOWNGRADE guards -- gem cup / battle arena include vs. destination shuffle.
# ---------------------------------------------------------------------------

class TestShuffleCategoryIncludeGuards(unittest.TestCase):

    def test_crystals_selected_without_arenas_warns(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "warp_pad_shuffle_categories": ["tracks", "crystals"],
                "include_battle_arenas": False,
            })
        world = mw.worlds[1]
        self.assertTrue(any("'crystals' entry" in m for m in cm.output))
        self.assertIn("crystals", set(world.options.warp_pad_shuffle_categories.value))
        self.assertFalse(world.options.include_battle_arenas.value)

    def test_crystals_selected_with_arenas_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warp_pad_shuffle_categories": ["tracks", "crystals"],
                "include_battle_arenas": True,
            })

    def test_crystals_not_selected_never_warns_regardless_of_include(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warp_pad_shuffle_categories": ["tracks"],
                "include_battle_arenas": False,
            })

    def test_cups_selected_without_include_warns_in_randomized_mode(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "warppad_unlock_requirements": "randomized",
                "warp_pad_shuffle_categories": ["tracks", "cups"],
                "include_gem_cups": False,
            })
        world = mw.worlds[1]
        self.assertTrue(any("'cups' entry" in m for m in cm.output))
        self.assertIn("cups", set(world.options.warp_pad_shuffle_categories.value))

    def test_cups_selected_with_include_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warppad_unlock_requirements": "randomized",
                "warp_pad_shuffle_categories": ["tracks", "cups"],
                "include_gem_cups": True,
            })

    def test_cups_without_include_in_vanilla_mode_does_not_double_warn(self):
        # Vanilla mode excludes cups unconditionally; that case belongs to
        # warn_vanilla_unlock_collapses_destination_shuffle, not this guard --
        # firing both would describe the same no-op twice.
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "warppad_unlock_requirements": "vanilla",
                "warp_pad_shuffle_categories": ["tracks", "cups"],
                "include_gem_cups": False,
            })
        self.assertFalse(any("Include Gem Cup Warp Pads is off" in m for m in cm.output))
        self.assertTrue(any("'vanilla' collapses destination shuffle" in m for m in cm.output))


# ---------------------------------------------------------------------------
# DOWNGRADE guards -- two_stage_density / requirement_variety / weights vs.
# vanilla unlock mode ("warp-pad modes").
# ---------------------------------------------------------------------------

class TestSphereSearchTuningIgnoredInVanilla(unittest.TestCase):

    def test_vanilla_mode_warns_about_density_and_variety(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "warppad_unlock_requirements": "vanilla",
                "two_stage_density": "deep",
                "requirement_variety": "custom",
                "requirement_weights": {"Key": 40},
            })
        world = mw.worlds[1]
        msg = next(m for m in cm.output if "sphere-search" in m)
        self.assertIn("Two-Stage Gate Density", msg)
        self.assertIn("Requirement Variety", msg)
        self.assertIn("Requirement Weights", msg)
        # Log-only: the options that triggered the warning are untouched.
        self.assertEqual(world.options.two_stage_density.current_key, "deep")
        self.assertEqual(world.options.requirement_variety.current_key, "custom")
        self.assertEqual(dict(world.options.requirement_weights.value), {"Key": 40})

    def test_vanilla_mode_without_custom_weights_omits_that_clause(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "warppad_unlock_requirements": "vanilla",
                "requirement_variety": "icebound_beta5",
            })
        msg = next(m for m in cm.output if "sphere-search" in m)
        self.assertNotIn("Requirement Weights", msg)

    def test_randomized_mode_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warppad_unlock_requirements": "randomized",
                "two_stage_density": "deep",
                "requirement_variety": "custom",
                "requirement_weights": {"Key": 40},
            })


# ---------------------------------------------------------------------------
# DOWNGRADE guards -- vanilla unlock mode collapses destination-shuffle shape.
# ---------------------------------------------------------------------------

class TestVanillaUnlockShuffleCollapse(unittest.TestCase):

    def test_defaults_in_vanilla_mode_warn_about_all_three_parts(self):
        # Default categories = {tracks, cups, crystals}, default grouping = merged.
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({"warppad_unlock_requirements": "vanilla"})
        world = mw.worlds[1]
        msg = next(m for m in cm.output if "collapses destination shuffle" in m)
        self.assertIn("merged", msg)
        self.assertIn("per_category", msg)
        self.assertIn("Slide Coliseum", msg)
        self.assertIn("'cups'", msg)
        # Log-only: still reads back the raw pre-collapse YAML choice.
        self.assertEqual(world.options.warp_pad_shuffle_grouping.current_key, "merged")
        self.assertEqual(set(world.options.warp_pad_shuffle_categories.value),
                         {"tracks", "cups", "crystals"})

    def test_per_category_with_only_crystals_selected_does_not_warn(self):
        # This still warns via warn_sphere_search_tuning_ignored_in_vanilla (a
        # different constraint), so check this message specifically rather
        # than asserting zero logs.
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "warppad_unlock_requirements": "vanilla",
                "warp_pad_shuffle_categories": ["crystals"],
                "warp_pad_shuffle_grouping": "per_category",
                "include_battle_arenas": True,
            })
        self.assertFalse(any("collapses destination shuffle" in m for m in cm.output))

    def test_randomized_mode_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({"warppad_unlock_requirements": "randomized"})


class TestLettersPerTrackInertOutsideLocationModes(unittest.TestCase):
    """#148 lettersanity row: `letters_per_track` only drives the per-track
    count for the two location-bearing shapes (locations_only,
    locations_and_items). In `off` and `items_only` the knob is silently
    ignored, so a non-default count there is a DOWNGRADE-WITH-WARNING."""

    def test_items_only_ignores_the_knob(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "lettersanity": "items_only",
                "letters_per_track": 1,
            })
        world = mw.worlds[1]
        self.assertTrue(any("Letters Per Track" in m for m in cm.output))
        # Log-only: the stored count is untouched.
        self.assertEqual(world.options.letters_per_track.value, 1)

    def test_off_ignores_the_knob(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "lettersanity": "off",
                "letters_per_track": 2,
            })
        world = mw.worlds[1]
        self.assertTrue(any("Letters Per Track" in m for m in cm.output))
        self.assertEqual(world.options.letters_per_track.value, 2)

    def test_location_bearing_modes_do_not_warn(self):
        for mode in ("locations_only", "locations_and_items"):
            with self.subTest(mode=mode):
                with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
                    _early({
                        "lettersanity": mode,
                        "letters_per_track": 1,
                    })

    def test_default_count_never_warns(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({"lettersanity": "items_only"})  # default letters_per_track == 3


# ---------------------------------------------------------------------------
# Sanity: an ordinary, fully-default seed triggers nothing in this module.
# ---------------------------------------------------------------------------

class TestDefaultOptionsAreConflictFree(CTRTestBase):
    """The shipped defaults (randomized unlock, all three shuffle categories
    included, podium checks on with its default sub-toggles) must clear every
    constraint in this module silently -- the matrix exists to flag YAMLs that
    deviate from the shape the defaults already describe."""

    run_default_tests = False
    options = {}

    def test_generate_early_logs_nothing(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            forced_options.apply(self.world)


if __name__ == "__main__":
    unittest.main()
