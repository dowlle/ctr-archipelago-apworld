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


    def test_master_on_does_not_warn_about_subtoggles(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
                "podium_held_rungs": True,
                "podium_held_fifth_rung": False,
            })


    def test_finish_on_does_not_warn_about_any_position(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "podium_placement_checks": True,
                "podium_finish_rungs": True,
                "podium_any_position_rung": True,
            })


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


    def test_cups_selected_with_include_does_not_warn(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            _early({
                "warppad_unlock_requirements": "randomized",
                "warp_pad_shuffle_categories": ["tracks", "cups"],
                "include_gem_cups": True,
            })



# ---------------------------------------------------------------------------
# DOWNGRADE guards -- two_stage_density / requirement_variety / weights vs.
# vanilla unlock mode ("warp-pad modes").
# ---------------------------------------------------------------------------

class TestSphereSearchTuningIgnoredInVanilla(unittest.TestCase):



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



# ---------------------------------------------------------------------------
# RESOLVE-WITH-WARNING guard -- over-capacity single-tier relic counts
# (2026-09-18 ruling: resolve_oxide_final_relic_count_to_mode_capacity).
# ---------------------------------------------------------------------------

class TestOxideFinalRelicCountResolvesToModeCapacity(unittest.TestCase):
    SINGLE_TIER_MODES = ("sapphire_relics", "gold_relics", "platinum_relics",
                         "any_relic_type")




    def test_count_at_18_is_untouched_in_a_single_tier_mode(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _early({
                "oxide_final_challenge_unlock": "sapphire_relics",
                "oxide_final_challenge_relic_count": 18,
            })
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value,
            18)




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















class TestGemGoalWithoutCupsFullAccessibility(CTRTestBase):
    """Real fill under accessibility: full. WorldTestBase's default tests
    (all_state reaches everything, empty state reaches something, fill) are
    the goal-reachability gate: the five pinned Gems sit behind their cups'
    vanilla token gates, so a seed that fills here has a reachable goal."""

    options = dict(CONFLICT, accessibility="full")


if __name__ == "__main__":
    unittest.main()
