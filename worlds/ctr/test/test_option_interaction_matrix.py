"""Tests for the option interaction / constraint matrix (issue #178,
worlds/ctr/forced_options.py).

Scope: the four already-shipping interaction groups named in the build host run
that built this (podium sub-toggle inertness, gem-cup/arena includes,
two_stage_density, warp-pad modes), plus regression coverage for the three
pre-existing RAISE guards (#87, #50, #23) that moved into forced_options.py
unchanged. #50 already has direct coverage in test_gem_cups.py and #87 in
test_requirement_weights.py; this file adds #23's first direct unit test
(previously reachable only through full generation, never asserted on
directly) plus all seven new DOWNGRADE-WITH-WARNING cases.

Two of those RAISE guards have since become RESOLVE-WITH-WARNING entries
(2026-09-18 for the Oxide final relic count, 2026-09-21 for #50's Gem goal
with the Gem Cups excluded); their coverage lives in the two blocks at the
bottom of this file, and a resolve test asserts the opposite of a downgrade
test -- the option's stored value MUST have changed.

Every DOWNGRADE test proves three things per constraint: the warning fires on
the conflicting combination, it does NOT fire on the matching non-conflicting
combination, and -- because this module is log-only by design (see
forced_options.py's module docstring) -- the option's own stored value is
byte-identical before and after forced_options.apply() runs, even when it
warned. That last assertion is the direct proof that a downgrade here never
reshapes a seed; it only reports what already-shipping generation logic does.
"""
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld, forced_options
from . import CTRTestBase

EARLY = ("generate_early",)
FULL = ("generate_early", "create_regions", "create_items", "set_rules")
LOGGER_NAME = "worlds.ctr.forced_options"
PLAYER = 1


def _early(options):
    return setup_multiworld(ctrAPWorld, EARLY, options=options)


def _full(options):
    return setup_multiworld(ctrAPWorld, FULL, options=options)


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
                # All-unlocked mode: podium off has no room for the 15 always-on
                # character unlock items (#54/#209) and generation raises before
                # the warning under test can be observed. This fixture is about
                # sub-toggle inertness, not the character item economy.
                "character_unlocks": False,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": True,
                "podium_held_fifth_rung": True,
            })
        world = mw.worlds[1]
        lines = [m for m in cm.output if "ignored options" in m]
        self.assertEqual(len(lines), 1, cm.output)
        # Only the sub-toggle that differs from its default is named, once,
        # under the master-off reason; the finish/held-specific notes must not
        # also fire (that would be redundant with the master-off one).
        self.assertIn("Podium: Held 5th Rung (Podium Placement Checks off)",
                      lines[0])
        self.assertNotIn("Podium Finish Rungs", lines[0])
        self.assertNotIn("Held-Position Rungs off", lines[0])
        self.assertNotIn("Podium Finish Rungs off", lines[0])
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
        self.assertTrue(any("Podium: Any-Position Rung (Podium Finish Rungs off)" in m
                            for m in cm.output))
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
        self.assertTrue(any("Podium: Held 5th Rung (Held-Position Rungs off)" in m
                            for m in cm.output))
        self.assertTrue(world.options.podium_held_fifth_rung.value)  # untouched

    def test_any_position_off_says_nothing_with_finish_off(self):
        """Finish Rungs off with Any-Position Rung also off: the player did
        not ask for the rung that is being ignored, so there is no notice."""
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": False,
                "podium_any_position_rung": False,
            })

    def test_held_fifth_off_says_nothing_with_held_off(self):
        """Held-Position Rungs off with Held 5th Rung at its default (off) --
        the report that started this: the warning named an option the player
        never turned on."""
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_held_rungs": False,
            })

    def test_every_ignored_option_shares_one_line(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "podium_placement_checks": True,
                "podium_held_rungs": False,
                "podium_held_fifth_rung": True,
                "lettersanity": "off",
                "letters_per_track": 2,
            })
        self.assertEqual(cm.output, [
            f"WARNING:{LOGGER_NAME}:CTR (Tester1): ignored options: "
            "Podium: Held 5th Rung (Held-Position Rungs off), "
            "Letters Per Track (Lettersanity off)"])

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
        self.assertTrue(any("'crystals' in Warp Pad Shuffle Categories "
                            "(Include Battle Arena Warp Pads off)" in m
                            for m in cm.output))
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
        self.assertTrue(any("'cups' in Warp Pad Shuffle Categories "
                            "(Include Gem Cup Warp Pads off)" in m
                            for m in cm.output))
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
        self.assertFalse(any("Include Gem Cup Warp Pads off" in m for m in cm.output))
        self.assertTrue(any("'cups' in Warp Pad Shuffle Categories "
                            "(vanilla warp-pad unlocks)" in m for m in cm.output))


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
        msg = next(m for m in cm.output if "ignored options" in m)
        self.assertIn("Two-Stage Gate Density, Requirement Variety, "
                      "Requirement Weights (vanilla warp-pad unlocks)", msg)
        # Log-only: the options that triggered the warning are untouched.
        self.assertEqual(world.options.two_stage_density.current_key, "deep")
        self.assertEqual(world.options.requirement_variety.current_key, "custom")
        self.assertEqual(dict(world.options.requirement_weights.value), {"Key": 40})

    def test_vanilla_mode_without_custom_weights_omits_that_clause(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "warppad_unlock_requirements": "vanilla",
                "two_stage_density": "deep",
                "requirement_variety": "icebound_beta5",
            })
        msg = next(m for m in cm.output if "ignored options" in m)
        self.assertIn("Two-Stage Gate Density (vanilla warp-pad unlocks)", msg)
        self.assertNotIn("Requirement Weights", msg)
        self.assertNotIn("Requirement Variety", msg)

    def test_vanilla_mode_with_defaulted_tuning_says_nothing(self):
        """The player did not set these, so there is nothing to tell them."""
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({"warppad_unlock_requirements": "vanilla"})

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

    def test_defaults_in_vanilla_mode_say_nothing(self):
        # Default categories = {tracks, cups, crystals}, default grouping =
        # merged: none of it was set by the player, so none of it is named.
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _early({"warppad_unlock_requirements": "vanilla"})
        world = mw.worlds[1]
        # Log-only: still reads back the raw pre-collapse YAML choice.
        self.assertEqual(world.options.warp_pad_shuffle_grouping.current_key, "merged")
        self.assertEqual(set(world.options.warp_pad_shuffle_categories.value),
                         {"tracks", "cups", "crystals"})

    def test_chosen_categories_in_vanilla_mode_name_the_ignored_parts(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({"warppad_unlock_requirements": "vanilla",
                    "warp_pad_shuffle_categories": ["tracks", "cups"]})
        msg = next(m for m in cm.output if "ignored options" in m)
        self.assertIn("Slide Coliseum and Turbo Track in the 'tracks' shuffle "
                      "category, 'cups' in Warp Pad Shuffle Categories "
                      "(vanilla warp-pad unlocks)", msg)

    def test_per_category_with_only_crystals_selected_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warppad_unlock_requirements": "vanilla",
                "warp_pad_shuffle_categories": ["crystals"],
                "warp_pad_shuffle_grouping": "per_category",
                "include_battle_arenas": True,
            })

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


# ---------------------------------------------------------------------------
# RESOLVE-WITH-WARNING guard -- over-capacity single-tier relic counts
# (2026-09-18 ruling: resolve_oxide_final_relic_count_to_mode_capacity).
# ---------------------------------------------------------------------------

class TestOxideFinalRelicCountResolvesToModeCapacity(unittest.TestCase):
    SINGLE_TIER_MODES = ("sapphire_relics", "gold_relics", "platinum_relics",
                         "any_relic_type")

    def test_each_single_tier_mode_resolves_above_18_to_18(self):
        for mode in self.SINGLE_TIER_MODES:
            with self.subTest(mode=mode):
                mw = _full({
                    "oxide_final_challenge_unlock": mode,
                    "oxide_final_challenge_relic_count": 40,
                    "sapphire_relic_count": 18,
                    "gold_relic_count": 18,
                    "platinum_relic_count": 18,
                    "accessibility": "minimal",
                })
                world = mw.worlds[PLAYER]
                self.assertEqual(
                    world.options.oxide_final_challenge_relic_count.value, 18)
                self.assertEqual(
                    world.fill_slot_data()["ctr_options"]["oxide_final_count"],
                    18)

    def test_resolution_warns_exactly_once_per_player(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "oxide_final_challenge_unlock": "gold_relics",
                "oxide_final_challenge_relic_count": 40,
                "gold_relic_count": 18,
            })
        matches = [m for m in cm.output
                  if "Relic Count lowered" in m]
        self.assertEqual(len(matches), 1)
        self.assertIn("lowered from 40 to 18", matches[0])
        self.assertIn("gold_relics", matches[0])

    def test_total_relics_above_18_is_untouched(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _early({
                "oxide_final_challenge_unlock": "total_relics",
                "oxide_final_challenge_relic_count": 40,
                "sapphire_relic_count": 18,
                "gold_relic_count": 18,
                "platinum_relic_count": 18,
            })
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value,
            40)

    def test_count_at_18_is_untouched_in_a_single_tier_mode(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _early({
                "oxide_final_challenge_unlock": "sapphire_relics",
                "oxide_final_challenge_relic_count": 18,
            })
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value,
            18)

    def test_count_below_18_is_untouched_in_a_single_tier_mode(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _early({
                "oxide_final_challenge_unlock": "platinum_relics",
                "oxide_final_challenge_relic_count": 5,
                "platinum_relic_count": 5,
            })
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value,
            5)

    def test_resolved_count_gates_the_final_challenge_rule_exactly_like_18(self):
        # Rule behaviour after resolution must match an explicit count of 18:
        # 17 Gold Relics is short, 18 satisfies it.
        mw = _full({
            "oxide_final_challenge_unlock": "gold_relics",
            "oxide_final_challenge_relic_count": 40,
            "gold_relic_count": 18,
        })
        world = mw.worlds[PLAYER]
        relic_rule = world._oxide_final_relic_rule()
        short = CollectionState(mw)
        short.add_item("Gold Relic", PLAYER, 17)
        short.stale[PLAYER] = True
        self.assertFalse(relic_rule(short))
        met = CollectionState(mw)
        met.add_item("Gold Relic", PLAYER, 18)
        met.stale[PLAYER] = True
        self.assertTrue(relic_rule(met))


# ---------------------------------------------------------------------------
# RESOLVE-WITH-WARNING guard -- a Gem goal with the Gem Cups excluded
# (2026-09-21 ruling: resolve_shuffle_gems_off_when_gem_goal_excludes_cups).
#
# This combination used to be #50's RAISE guard
# (raise_if_gems_required_goal_needs_excluded_cups) and failed generation for
# the WHOLE multiworld. It now resolves shuffle_gems OFF for the conflicting
# slot: the five Gems stay on their own vanilla Gem Cups, which is the
# already-supported shuffle-off path, and nothing the player excluded enters
# the seed.
# ---------------------------------------------------------------------------

CUP_LOCATIONS = {
    "Red Gem Cup: Gem": "Red Gem",
    "Green Gem Cup: Gem": "Green Gem",
    "Blue Gem Cup: Gem": "Blue Gem",
    "Yellow Gem Cup: Gem": "Yellow Gem",
    "Purple Gem Cup: Gem": "Purple Gem",
}
CONFLICT = {
    "oxide_goal": "none",
    "gems_required_goal": 5,
    "shuffle_gems": True,
    "include_gem_cups": False,
}
RESOLVED_MARKER = "Shuffle Gems turned off"


def _early_capturing_warnings(options):
    """(world, warning messages) for one generate_early.

    assertNoLogs is too blunt for the neighbour configurations: cups-off seeds
    legitimately emit the unrelated `warn_shuffle_cups_without_include`
    downgrade line, which predates this ruling and must keep firing. These
    tests care only about whether the RESOLVE line appeared."""
    import logging
    records = []
    handler = logging.Handler(level=logging.WARNING)
    handler.emit = records.append
    module_logger = logging.getLogger(LOGGER_NAME)
    module_logger.addHandler(handler)
    try:
        mw = _early(options)
    finally:
        module_logger.removeHandler(handler)
    return mw.worlds[PLAYER], [r.getMessage() for r in records]


class TestGemGoalWithoutCupsResolvesShuffleGemsOff(unittest.TestCase):
    def test_the_combination_generates(self):
        # The whole point of the ruling: no OptionError, no aborted room.
        mw = _full(dict(CONFLICT))
        self.assertIsNotNone(mw.worlds[PLAYER])

    def test_resolved_option_value_is_off(self):
        world = _early(dict(CONFLICT)).worlds[PLAYER]
        self.assertEqual(world.options.shuffle_gems.value, 0)

    def test_the_players_own_options_are_not_rewritten(self):
        # Only shuffle_gems moves. The opt-out and the goal are the player's.
        world = _early(dict(CONFLICT)).worlds[PLAYER]
        self.assertEqual(world.options.include_gem_cups.value, 0)
        self.assertEqual(world.options.gems_required_goal.value, 5)

    def test_warning_is_logged_once_and_names_both_ways_out(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early(dict(CONFLICT))
        matches = [m for m in cm.output if RESOLVED_MARKER in m]
        self.assertEqual(len(matches), 1)
        message = matches[0]
        self.assertIn("CTR (Tester1)", message)
        self.assertIn("Gems Required Goal", message)
        self.assertIn("Include Gem Cup Warp Pads", message)
        # Both escape routes from the ruling.
        self.assertIn("turn that on to keep Gems shuffled", message)
        self.assertIn("set Shuffle Gems off yourself", message)

    def test_warning_is_logged_once_through_a_full_generation(self):
        # One warning per full generation. The resolution is idempotent, so a
        # second generate_early pass would find nothing to say.
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _full(dict(CONFLICT))
        self.assertEqual(
            len([m for m in cm.output if RESOLVED_MARKER in m]), 1)

    def test_the_five_gems_sit_on_their_own_vanilla_cups(self):
        mw = _full(dict(CONFLICT))
        for loc_name, gem in CUP_LOCATIONS.items():
            with self.subTest(location=loc_name):
                loc = mw.get_location(loc_name, PLAYER)
                self.assertTrue(loc.locked)
                self.assertEqual(loc.item.name, gem)
                self.assertEqual(loc.item.player, PLAYER)
        # ...and therefore nowhere else: no Gem is left in the pool to hide.
        pooled = [item for item in mw.itempool
                  if item.player == PLAYER and item.name in CUP_LOCATIONS.values()]
        self.assertEqual(pooled, [])

    def test_slot_data_reports_shuffle_gems_false(self):
        # The native client and the spoiler must agree with the resolution.
        mw = _full(dict(CONFLICT))
        wire = mw.worlds[PLAYER].fill_slot_data()
        self.assertFalse(wire["ctr_options"]["shuffle_gems"])
        self.assertEqual(wire["ctr_options"]["goal_gems"], 5)

    def test_universal_tracker_regeneration_reproduces_the_resolved_state(self):
        # UT restores shuffle_gems from the wire (already resolved) and never
        # reaches the resolution itself -- so no second warning, and the
        # re-generated world matches the seed's own pinned Gems.
        import json

        from test.general import call_all
        source = _full(dict(CONFLICT))
        wire = json.loads(json.dumps(source.worlds[PLAYER].fill_slot_data()))
        tracker = setup_multiworld(ctrAPWorld, (), seed=99)
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        tracker.generation_is_fake = True
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            for step in FULL:
                call_all(tracker, step)
        self.assertEqual(
            tracker.worlds[PLAYER].options.shuffle_gems.value, 0)
        for loc_name, gem in CUP_LOCATIONS.items():
            with self.subTest(location=loc_name):
                loc = tracker.get_location(loc_name, PLAYER)
                self.assertTrue(loc.locked)
                self.assertEqual(loc.item.name, gem)


    def test_universal_tracker_takes_the_turbo_track_guard_from_the_seed(self):
        # Vanilla warp-pad requirements plus the resolved shuffle_gems OFF set
        # force_vanilla_turbotrack on the seed. The tracker's own YAML still
        # has shuffle_gems on, so the flag must come from the restored options.
        import json

        from test.general import call_all
        options = dict(CONFLICT)
        options["warppad_unlock_requirements"] = 0
        options["accessibility"] = "minimal"
        source = _full(options)
        self.assertTrue(source.worlds[PLAYER]._ctr_force_vanilla_turbotrack)
        wire = json.loads(json.dumps(source.worlds[PLAYER].fill_slot_data()))
        tracker = setup_multiworld(ctrAPWorld, (), seed=99)
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        tracker.generation_is_fake = True
        for step in FULL:
            call_all(tracker, step)
        self.assertTrue(tracker.worlds[PLAYER]._ctr_force_vanilla_turbotrack)


class TestGemGoalWithoutCupsResolvesBeforeTheRNGDraws(unittest.TestCase):
    """The resolution runs at the TOP of generate_early, not from
    forced_options.apply, because three shuffle_gems readers run before apply:
    the Cortex Vortex dropped-destination draw, the cached comfort-guard flags
    and the relic-tier keep draw (the last two through
    relic_tiers.resolve_comfort_guards, whose force_vanilla_turbotrack
    condition contains `not shuffle_gems`). A resolution that landed in apply
    would leave those three reading the pre-resolution value.

    The proof is equivalence: the resolved seed must behave exactly like the
    same YAML with shuffle_gems written False by hand."""

    # accessibility minimal keeps the unrelated relic-supply guard out of the
    # way: the comfort guard clamps Sapphire to 17, which a `full` seed with
    # the default 18-relic Oxide gate rejects for reasons of its own.
    EQUIVALENT = dict(CONFLICT, warppad_unlock_requirements="vanilla",
                      accessibility="minimal")

    def test_comfort_guard_matches_an_explicit_shuffle_off_seed(self):
        resolved = _early(dict(self.EQUIVALENT)).worlds[PLAYER]
        explicit = _early(dict(self.EQUIVALENT, shuffle_gems=False)).worlds[PLAYER]
        # Vanilla unlock + gems not shuffled = the Turbo Track comfort guard.
        # It is False before the resolution and True after it, so a late
        # resolution would show up right here.
        self.assertTrue(resolved._ctr_force_vanilla_turbotrack)
        self.assertEqual(resolved._ctr_force_vanilla_turbotrack,
                         explicit._ctr_force_vanilla_turbotrack)

    def test_relic_draw_matches_an_explicit_shuffle_off_seed(self):
        # The relic-tier keep draw reads the comfort guard, so a late
        # resolution would create a different set of Time Trial locations.
        resolved = _early(dict(self.EQUIVALENT)).worlds[PLAYER]
        explicit = _early(dict(self.EQUIVALENT, shuffle_gems=False)).worlds[PLAYER]
        self.assertEqual(resolved._ctr_relic_keep, explicit._ctr_relic_keep)
        self.assertEqual(resolved._ctr_relic_created, explicit._ctr_relic_created)


class TestGemGoalWithoutCupsNeighboursAreUntouched(unittest.TestCase):
    """The three configurations one step away from the conflict must behave
    exactly as they did before the ruling: no warning, no option rewritten."""

    def test_cups_on_with_shuffle_on_is_unaffected(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            world = _early(dict(CONFLICT, include_gem_cups=True)).worlds[PLAYER]
        self.assertEqual(world.options.shuffle_gems.value, 1)
        self.assertEqual(world.options.include_gem_cups.value, 1)

    def test_shuffle_off_with_cups_off_is_unaffected(self):
        world, warnings = _early_capturing_warnings(
            dict(CONFLICT, shuffle_gems=False))
        self.assertEqual([w for w in warnings if RESOLVED_MARKER in w], [])
        self.assertEqual(world.options.shuffle_gems.value, 0)
        self.assertEqual(world.options.include_gem_cups.value, 0)

    def test_no_gem_goal_with_the_same_other_options_is_unaffected(self):
        # gems_required_goal == 0 is not a Gem goal, so the #50 cup pin (not
        # this resolution) is what handles cups-off + shuffle-on: shuffle_gems
        # must survive at ON.
        world, warnings = _early_capturing_warnings(
            dict(CONFLICT, gems_required_goal=0, bosses_required_goal=4))
        self.assertEqual([w for w in warnings if RESOLVED_MARKER in w], [])
        self.assertEqual(world.options.shuffle_gems.value, 1)
        self.assertEqual(world.options.include_gem_cups.value, 0)


class TestGemGoalWithoutCupsFullAccessibility(CTRTestBase):
    """Real fill under accessibility: full. WorldTestBase's default tests
    (all_state reaches everything, empty state reaches something, fill) are
    the goal-reachability gate: the five pinned Gems sit behind their cups'
    vanilla token gates, so a seed that fills here has a reachable goal."""

    options = dict(CONFLICT, accessibility="full")


if __name__ == "__main__":
    unittest.main()
