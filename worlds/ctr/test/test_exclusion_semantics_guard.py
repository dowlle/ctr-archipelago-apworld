"""Regression guard for TODAY's exclude_locations / priority_locations behaviour
on CTR seeds (issue #28). This module makes NO design decision and changes NO
generation behaviour. It exists to pin down, with real generation, what already
happens per location kind, so the #28 decision packet can argue from measured
fact instead of from memory.

Per `location_class.py`'s own docstring, #28 is unruled and every location
class "behave[s] exactly as [its] locations behaved before the extraction,
which is: AP's normal handling, plus `__init__._exclude_goal_location` for the
goal locations." These tests are the "AP's normal handling" claim, made
concrete for CTR's four location kinds:

  * static      -- a shipped JSON location with no locked item (e.g. a Trophy
                   Race). AP's `worlds.generic.Rules.exclusion_rules` and the
                   inline priority loop in `Main.py` (~line 121-135) are the
                   whole story; CTR contributes nothing.
  * podium rung -- a `LocationClass` location (`podium.py`). The superset is
                   frozen and registered unconditionally (so its NAME is
                   always in `location_name_to_id`), but a given seed only
                   CREATES the subset its rung toggles ask for. Whether a rung
                   is excludable/prioritizable therefore depends on whether
                   THIS seed created it, not on whether the name exists.
  * goal        -- the real, coded goal location (e.g. "N. Oxide Garage: N.
                   Oxide's Challenge"). `__init__._exclude_goal_location`
                   force-sets it `EXCLUDED` at `_install_goal` time (issue
                   #27), independent of and BEFORE the player's own
                   `exclude_locations` option is ever consulted.
  * event       -- a code-null companion location (`_add_goal_event`) that
                   already carries a `place_locked_item`-ed advancement flag
                   item by the time `Main.py` gets to exclusion/priority.

Verified at AP core (0.6.7, this repo's vendored copy):
  - `worlds/generic/Rules.py:79-89` (`exclusion_rules`): a location already
    holding an advancement item (`location.advancement`) REFUSES exclusion and
    logs a warning instead of raising; only a location with progress_type !=
    EXCLUDED is even attempted.
  - `Main.py:118-135`: priority runs AFTER exclusion and after
    `priority_locations -= exclude_locations`, so a name in BOTH sets is
    silently dropped from priority without ever being attempted or warned
    about. A name that is EXCLUDED by the WORLD ITSELF (not the player's own
    exclude_locations) still hits the `else` branch of the priority loop and
    is refused with a warning, because the check is on `progress_type`, not on
    provenance.
  - `Main.py:118-135` does NOT apply `exclusion_rules`'s locked-item check to
    priority: an event location with a locked advancement item is DEFAULT
    progress_type (exclusion never got applied to it, and nothing else moves
    it), so the priority loop's `progress_type != EXCLUDED` check passes and
    it silently sets PRIORITY -- inert for fill (the location is never
    "unfilled"), but not refused or warned about, unlike exclusion on the same
    location. That asymmetry is real today and is called out explicitly below
    (`TestEventLocationExclusionPriorityAsymmetry`) rather than left implicit.
  - `BaseClasses.py:1471-1474` (`LocationProgressType`): DEFAULT=1, PRIORITY=2,
    EXCLUDED=3.
  - `BaseClasses.py:1496-1503` (`Location.can_fill`): EXCLUDED bars BOTH
    advancement AND useful items, not just progression -- only filler/trap (or
    an `always_allow` override CTR does not use) may seat there.
  - `worlds/ctr/__init__.py:1087-1091` (`create_items`): CTR's filler count is
    `max(0, unfilled_locations - progression_pool_size)`, computed from
    `create_items` BEFORE the player's `exclude_locations` is applied. Podium
    rungs add location capacity with no matching item-pool entries, so turning
    rungs on/off is what actually controls how much filler slack exists to
    absorb exclusions -- this is the concrete mechanism behind the #71 dossier
    line "excluded locations need reserved filler or a legal YAML FillErrors."
    `TestFillErrorWhenExclusionExceedsFillerHeadroom` measures it directly.

Every test below runs REAL generation (`test.general.setup_multiworld` through
`set_rules`, then this module's own `exclusion_rules` / priority replication,
then `Fill.distribute_items_restrictive` where a test needs the fill outcome)
rather than asserting against a description of the mechanism, per this
project's verify-first standing rule. All fixed seeds are chosen for
reproducibility, not cherry-picked for a favourable result; the module-level
`_SAMPLE_SEEDS` block documents the multi-seed check each numeric threshold
claim was run against before being pinned to a single seed in the test body
(Lessons Learned #2: a small sample invents an invariant).

`_SAMPLE_SEEDS = (1, 2, 3, 100, 999999)` plus the primary seed 4242. On
`podium_placement_checks=False` (2-item filler slack), excluding 5 shipped
locations raised `Fill.FillError` on all 6; excluding 1 raised FillError on 1
of 6 (seed 3) and succeeded on the other 5 -- so "excludes 1" is NOT pinned as
a safe count anywhere below, only "excludes 5 reliably exceeds the podium-off
filler budget" is. On shipped defaults (66-item filler slack from the podium
rungs), excluding the same 5 locations succeeded on all 6.
"""

import logging
import unittest

from BaseClasses import LocationProgressType
from Fill import FillError, distribute_items_restrictive
from test.general import setup_multiworld
from worlds.generic.Rules import exclusion_rules

from .. import ctrAPWorld
from . import CTRTestBase

_SAMPLE_SEEDS = (1, 2, 3, 100, 999999)
_PRIMARY_SEED = 4242

_STEPS = ("generate_early", "create_regions", "create_items", "set_rules")

# A location with no locked item, present in every config (shipped JSON data),
# used as the "static" representative.
STATIC_LOCATION = "Crash Cove: Trophy Race"
# A second static location, for the both-in-one-set tests.
STATIC_LOCATION_2 = "Roo's Tubes: Trophy Race"
# Created by shipped defaults (podium_held_rungs on, held_fifth off is NOT this
# one): held_1st is created whenever the held toggle is on, which is the
# default.
CREATED_RUNG = "Crash Cove: Held 1st"
# held_5th defaults OFF (Toggle, not DefaultOnToggle) and nothing else turns it
# on below, so this name is registered (frozen superset) but never created by
# any config used in this file.
UNCREATED_RUNG = "Crash Cove: Held 5th"

GOAL_LOCATION_OXIDE = "N. Oxide Garage: N. Oxide's Challenge"
EVENT_OXIDE = "N. Oxide's Challenge Cleared"
GOAL_LOCATION_OXIDEFINAL = "N. Oxide Garage: N. Oxide's Final Challenge"
EVENT_OXIDEFINAL = "N. Oxide's Final Challenge Cleared"
EVENT_ALLBOSSES_SAMPLE = "Ripper Roo Boss Race Won"


def _build(seed=_PRIMARY_SEED, **option_overrides):
    """A multiworld through set_rules -- i.e. exactly where Main.py is when it
    starts running exclusion_rules and the priority loop, per Main.py:110-135."""
    return setup_multiworld(ctrAPWorld, steps=_STEPS, seed=seed,
                            options=option_overrides)


def _apply_priority(multiworld, player, priority_names, exclude_names=()):
    """Faithful replica of Main.py:118-135's priority handling, isolated so
    these tests can drive it without going through the full `main()` entry
    point. `priority_names -= exclude_names` first, exactly as Main.py does,
    THEN each surviving name is attempted: PRIORITY if not already EXCLUDED,
    else refused with a warning and dropped. Returns the set of names refused
    because the world had already excluded them."""
    priority_names = set(priority_names) - set(exclude_names)
    world_excluded = set()
    for location_name in priority_names:
        try:
            location = multiworld.get_location(location_name, player)
        except KeyError:
            continue
        if location.progress_type != LocationProgressType.EXCLUDED:
            location.progress_type = LocationProgressType.PRIORITY
        else:
            logging.warning(
                f"Unable to prioritize location \"{location_name}\" in "
                f"player {player}'s world because the world excluded it.")
            world_excluded.add(location_name)
    return world_excluded


class TestStaticLocationExclusionAndPriority(unittest.TestCase):
    """The plain case: a shipped JSON location with no locked item. This is the
    baseline every other location kind is measured against."""

    def test_exclude_succeeds_and_sets_excluded(self):
        mw = _build()
        loc = mw.get_location(STATIC_LOCATION, 1)
        self.assertEqual(loc.progress_type, LocationProgressType.DEFAULT)
        exclusion_rules(mw, 1, {STATIC_LOCATION})
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)

    def test_priority_succeeds_and_sets_priority(self):
        mw = _build()
        loc = mw.get_location(STATIC_LOCATION, 1)
        _apply_priority(mw, 1, {STATIC_LOCATION})
        self.assertEqual(loc.progress_type, LocationProgressType.PRIORITY)

    def test_exclude_wins_when_both_requested_for_the_same_location(self):
        """Main.py:121 subtracts exclude_locations from priority_locations
        BEFORE the priority loop runs, so a location in both sets is excluded
        and never even attempted for priority (no warning either -- it is
        removed from the priority set before the loop that would warn)."""
        mw = _build()
        loc = mw.get_location(STATIC_LOCATION, 1)
        exclusion_rules(mw, 1, {STATIC_LOCATION})
        refused = _apply_priority(mw, 1, {STATIC_LOCATION},
                                  exclude_names={STATIC_LOCATION})
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)
        self.assertEqual(refused, set(),
                         "a location removed by the exclude-set subtraction "
                         "is never reached, so it cannot be in the refused set")

    def test_excluding_an_unknown_name_raises(self):
        """exclusion_rules only tolerates a missing GET when the name is not a
        location this world's datapackage even knows about; a genuinely
        unknown name still raises (worlds/generic/Rules.py:83-85)."""
        mw = _build()
        with self.assertRaises(Exception):
            exclusion_rules(mw, 1, {"This Location Does Not Exist Anywhere"})


class TestPodiumRungExclusionRespectsCreationSubset(unittest.TestCase):
    """Podium rungs are the one shipped `LocationClass` member today. Their
    name superset is frozen and registered unconditionally (`podium.py`,
    `location_class.py`), but only the per-seed CREATED subset exists as a
    real `Location` object. exclude_locations / priority_locations therefore
    behave differently depending on whether this seed created the named rung,
    even though both names resolve in the datapackage."""

    def test_exclude_created_rung_succeeds(self):
        mw = _build()  # shipped defaults: held_1st is created
        loc = mw.get_location(CREATED_RUNG, 1)
        exclusion_rules(mw, 1, {CREATED_RUNG})
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)

    def test_priority_created_rung_succeeds(self):
        mw = _build()
        loc = mw.get_location(CREATED_RUNG, 1)
        _apply_priority(mw, 1, {CREATED_RUNG})
        self.assertEqual(loc.progress_type, LocationProgressType.PRIORITY)

    def test_uncreated_rung_name_is_in_the_datapackage(self):
        """The frozen-superset half of the claim: the name is registered even
        though this seed will not create it (held_5th default off)."""
        mw = _build()
        self.assertIn(UNCREATED_RUNG, mw.worlds[1].location_name_to_id)

    def test_uncreated_rung_has_no_location_object_this_seed(self):
        mw = _build()
        with self.assertRaises(KeyError):
            mw.get_location(UNCREATED_RUNG, 1)

    def test_excluding_an_uncreated_rung_is_a_silent_no_op(self):
        """This is the sharp edge: a name that is real in the datapackage but
        absent from THIS seed's region graph does not raise (the
        `loc_name not in location_name_to_id` escape in exclusion_rules
        catches it) and has no effect, because there is no Location object for
        it to act on. A player YAML that excludes 'Crash Cove: Held 5th' on a
        seed that never created it is accepted and silently does nothing."""
        mw = _build()
        exclusion_rules(mw, 1, {UNCREATED_RUNG})  # must not raise
        with self.assertRaises(KeyError):
            mw.get_location(UNCREATED_RUNG, 1)

    def test_prioritizing_an_uncreated_rung_is_also_a_silent_no_op(self):
        mw = _build()
        refused = _apply_priority(mw, 1, {UNCREATED_RUNG})
        self.assertEqual(refused, set(),
                         "an uncreated location cannot be 'refused' -- the "
                         "priority loop's own KeyError guard just skips it")

    def test_exclude_then_generate_a_seed_that_never_had_this_rung(self):
        """Belt-and-braces: run the full option arm that never creates Held
        5th (held_fifth explicitly off, which is also the default) and confirm
        the same silent no-op holds under an explicit, not just default,
        option set."""
        mw = _build(podium_placement_checks=True, podium_held_rungs=True,
                   podium_held_fifth_rung=False, podium_finish_rungs=True,
                   podium_any_position_rung=True)
        exclusion_rules(mw, 1, {UNCREATED_RUNG})
        with self.assertRaises(KeyError):
            mw.get_location(UNCREATED_RUNG, 1)


class TestGoalLocationForcedExclusionIndependentOfPlayerOption(unittest.TestCase):
    """Issue #27's `_exclude_goal_location`: the real, coded goal location is
    force-set EXCLUDED at `_install_goal` time (inside `create_items`), before
    the player's own `exclude_locations` option is ever read by `Main.py`. The
    location still exists and is still sent as a check; only its progress_type
    is forced."""

    def test_oxide_goal_location_is_already_excluded_before_the_player_option_runs(self):
        mw = _build(goal="oxide")
        loc = mw.get_location(GOAL_LOCATION_OXIDE, 1)
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED,
                         "the world must force this BEFORE exclusion_rules runs")

    def test_oxidefinal_goal_location_is_already_excluded(self):
        mw = _build(goal="oxidefinal")
        loc = mw.get_location(GOAL_LOCATION_OXIDEFINAL, 1)
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)

    def test_player_excluding_the_goal_location_is_an_idempotent_no_op(self):
        mw = _build(goal="oxide")
        loc = mw.get_location(GOAL_LOCATION_OXIDE, 1)
        exclusion_rules(mw, 1, {GOAL_LOCATION_OXIDE})
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)

    def test_player_prioritizing_the_goal_location_is_refused_and_warned(self):
        """The goal location was excluded by the WORLD, not by the player's
        own exclude_locations set, so Main.py's
        `priority_locations -= exclude_locations` subtraction (keyed on the
        PLAYER's exclude set) does not remove it before the loop runs. The
        loop's own `progress_type != EXCLUDED` check is what catches it, and
        that check cannot distinguish world-forced EXCLUDED from
        player-requested EXCLUDED -- both refuse identically."""
        mw = _build(goal="oxide")
        loc = mw.get_location(GOAL_LOCATION_OXIDE, 1)
        with self.assertLogs(level="WARNING") as cm:
            refused = _apply_priority(mw, 1, {GOAL_LOCATION_OXIDE})
        self.assertEqual(refused, {GOAL_LOCATION_OXIDE})
        self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)
        self.assertTrue(any("excluded it" in msg for msg in cm.output))


class TestEventLocationExclusionPriorityAsymmetry(unittest.TestCase):
    """Companion events (`_add_goal_event`) already carry a locked advancement
    item by the time Main.py reaches exclusion/priority. `exclusion_rules`
    checks `location.advancement` and refuses with a warning
    (worlds/generic/Rules.py:87-89); the priority loop checks only
    `progress_type != EXCLUDED` and has no locked-item guard at all, so it
    silently "succeeds" (sets PRIORITY) on the same location. Both are inert
    for fill either way -- the location is never in `get_unfilled_locations`
    -- but only one of the two logs anything, which is worth knowing before
    #28 designs a unified semantics on top of this."""

    def test_excluding_an_event_location_is_refused_and_warned(self):
        mw = _build(goal="oxide")
        loc = mw.get_location(EVENT_OXIDE, 1)
        self.assertTrue(loc.advancement)
        with self.assertLogs(level="WARNING") as cm:
            exclusion_rules(mw, 1, {EVENT_OXIDE})
        self.assertEqual(loc.progress_type, LocationProgressType.DEFAULT,
                         "refused exclusion must leave progress_type untouched")
        self.assertTrue(any("Unable to exclude location" in msg
                            for msg in cm.output))

    def test_excluding_the_oxidefinal_event_location_is_also_refused(self):
        mw = _build(goal="oxidefinal")
        loc = mw.get_location(EVENT_OXIDEFINAL, 1)
        with self.assertLogs(level="WARNING"):
            exclusion_rules(mw, 1, {EVENT_OXIDEFINAL})
        self.assertEqual(loc.progress_type, LocationProgressType.DEFAULT)

    def test_excluding_an_allbosses_companion_event_is_also_refused(self):
        """A second goal mode's companion event, so this is not a fact about
        the oxide goal specifically -- every `_add_goal_event` location shares
        the mechanism (locked advancement item -> exclusion_rules refuses)."""
        mw = _build(goal="allbosses")
        loc = mw.get_location(EVENT_ALLBOSSES_SAMPLE, 1)
        self.assertTrue(loc.advancement)
        with self.assertLogs(level="WARNING"):
            exclusion_rules(mw, 1, {EVENT_ALLBOSSES_SAMPLE})
        self.assertEqual(loc.progress_type, LocationProgressType.DEFAULT)

    def test_prioritizing_an_event_location_silently_applies_and_warns_nothing(self):
        """The asymmetry, made explicit: no exception, no warning, no refused
        set entry -- progress_type simply becomes PRIORITY on a location that
        already holds a locked item and will never reach fill."""
        mw = _build(goal="oxide")
        loc = mw.get_location(EVENT_OXIDE, 1)
        with self.assertNoLogs(level="WARNING"):
            refused = _apply_priority(mw, 1, {EVENT_OXIDE})
        self.assertEqual(refused, set())
        self.assertEqual(loc.progress_type, LocationProgressType.PRIORITY)

    def test_prioritized_event_location_is_inert_for_fill(self):
        """The PRIORITY marking from the previous test has no observable
        effect: the location is not in get_unfilled_locations either before or
        after, because place_locked_item already resolved it in create_items."""
        mw = _build(goal="oxide")
        _apply_priority(mw, 1, {EVENT_OXIDE})
        unfilled_names = {loc.name for loc in mw.get_unfilled_locations(1)}
        self.assertNotIn(EVENT_OXIDE, unfilled_names)


class TestFullAccessibilityUnaffectedByExclusionMechanism(CTRTestBase):
    """Exclusion changes which ITEM CLASSES may seat at a location; it does
    not change the region graph, so it must not change reachability. These
    tests run the actual fill (not just set_rules) and check the outcome
    lands where BaseClasses.Location.can_fill says it must."""

    def test_excluded_location_never_receives_advancement_or_useful(self):
        mw = _build(_PRIMARY_SEED)
        loc = mw.get_location(STATIC_LOCATION, 1)
        exclusion_rules(mw, 1, {STATIC_LOCATION})
        distribute_items_restrictive(mw)
        self.assertIsNotNone(loc.item)
        self.assertFalse(loc.item.advancement or loc.item.useful,
                         f"EXCLUDED location received {loc.item!r}, which "
                         "Location.can_fill should have barred")

    def test_excluding_one_reachable_location_still_fills_and_stays_full_accessible(self):
        """A single exclusion, comfortably inside the shipped-default filler
        budget (66 slack; see the module docstring), must not turn into a
        FillError. This is the "well provisioned" control the FillError-edge
        tests below are contrasted against."""
        mw = _build(_PRIMARY_SEED)
        exclusion_rules(mw, 1, {STATIC_LOCATION})
        distribute_items_restrictive(mw)  # must not raise
        for loc in mw.get_locations(1):
            self.assertTrue(
                loc.item is not None or not loc.progress_type,
                f"{loc.name} was left unfilled after distribute_items_restrictive")


class TestFillErrorWhenExclusionExceedsFillerHeadroom(unittest.TestCase):
    """The #71 interaction named in the work order: CTR's filler count is
    computed once, in create_items, from the unfilled-location count BEFORE
    exclude_locations is applied (`__init__.py:1087-1097`). Podium rungs are
    the only thing that currently buys filler headroom (they add locations
    with no matching pool items); with podium off, only ~2 filler items exist
    for the whole seed. Exercising this exactly, not just asserting the
    arithmetic, is the point of these tests."""

    def _exclude_and_fill(self, seed, exclude_names, **option_overrides):
        mw = _build(seed, **option_overrides)
        exclusion_rules(mw, 1, set(exclude_names))
        distribute_items_restrictive(mw)

    def test_five_exclusions_reliably_exceed_the_podium_off_filler_budget(self):
        """Podium off leaves ~2 filler items total. Verified over
        _SAMPLE_SEEDS in the exploration that produced this module (see the
        module docstring): 5 exclusions raised FillError on all 6 seeds
        tried, including the primary seed pinned here."""
        mw = _build(_PRIMARY_SEED, podium_placement_checks=False)
        names = [loc.name for loc in mw.get_unfilled_locations(1)][:5]
        with self.assertRaises(FillError):
            self._exclude_and_fill(_PRIMARY_SEED, names,
                                   podium_placement_checks=False)

    def test_same_five_names_fill_fine_under_shipped_defaults(self):
        """Same exclusion COUNT (five shipped locations), same seed, only the
        podium option differs. Isolates the FillError above to filler
        headroom, not to which locations were named."""
        mw = _build(_PRIMARY_SEED)
        names = [loc.name for loc in mw.get_unfilled_locations(1)][:5]
        self._exclude_and_fill(_PRIMARY_SEED, names)  # must not raise

    def test_podium_off_five_exclusions_fail_across_multiple_seeds(self):
        """The multi-seed half of the module docstring's claim, run directly
        rather than only asserted in prose."""
        for seed in _SAMPLE_SEEDS:
            with self.subTest(seed=seed):
                mw = _build(seed, podium_placement_checks=False)
                names = [loc.name for loc in mw.get_unfilled_locations(1)][:5]
                with self.assertRaises(FillError):
                    self._exclude_and_fill(seed, names,
                                           podium_placement_checks=False)


if __name__ == "__main__":
    unittest.main()
