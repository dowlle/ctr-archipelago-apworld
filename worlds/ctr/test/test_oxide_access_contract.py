"""Tests for the ENCOUNTER-SPECIFIC Oxide access contract (issues #320 and
#321, RC ruling of 2026-09-03).

WHAT THIS REPLACES. The first version of this contract (WO-A1, 2026-08-26)
ANDed every active companion goal arm onto the shared "N. Oxide Garage Door"
entrance whenever `oxide_goal != none`, so BOTH Oxide locations inherited the
conjunction. That is right for an Any% finale and wrong for a Final Challenge
finale: on a `101_percent` seed it locked Oxide's first challenge -- an
ordinary four-Key midpoint -- behind the Boss and Gem arms that should gate
only the Final Challenge. Alpha 7's play session hit exactly that. The old
shared-door truth table is therefore replaced here rather than extended, as
#321's implementation check 6 requires.

THE CONTRACT UNDER TEST (`Rules.add_oxide_access_contract`):

| oxide_goal   | Oxide 1              | Oxide 2                            |
|--------------|----------------------|------------------------------------|
| none         | 4 Keys               | Oxide 1 + configured relics        |
| any_percent  | 4 Keys + companions  | Oxide 1 + configured relics        |
| 101_percent  | 4 Keys               | Oxide 1 + relics + companions      |
| disabled     | absent from the seed | absent from the seed               |

"Companions" is the conjunction of this seed's ACTIVE non-Oxide goal arms,
read from the SAME predicate objects `_install_goal` uses for completion
(`world._ctr_boss_won_predicate`, `world._ctr_gems_predicate`), so an
encounter and the goal cannot drift apart about the same question.

Layers here:

- TestOxideEncounterTruthTable: reachability of both Oxide LOCATIONS across
  all four modes with no companion arm, Boss-only, Gem-only and both, at
  one-short, exact and over-satisfied tallies.
- TestOxideGoalEventsFollowTheirEncounter: the code-null companion events
  `_install_goal` lays take the same rules as their locations, so the sphere
  search cannot believe an Any% goal completes before its arms are
  satisfiable.
- TestOxideDisabledRemovesTheContent: #320 -- both locations are absent from
  the generated world (not merely excluded or unreachable), the garage door
  is shut, the wire carries `goal_oxide: 3` at schema 9, and the all-off
  combination is rejected.
- TestOxideEncounterMutations: each encounter-specific term reverted or
  bypassed in turn, each proven to flip a row the fixed source gets right.
- TestOxideAccessUniversalTrackerParity: a UT-reconstructed world answers
  identically to the originally generated one, for both encounters.

Real full-generation gate coverage (the full CTR suite, the fuzz matrix,
manifest/name-freeze/item-id stability, slot_data round-trip) lives in the
build note's evidence, not here -- this file is the fast, direct unit layer
over the two locations' reachability.
"""
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld
from ..Options import OxideGoal
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1

FIRST = "N. Oxide Garage: N. Oxide's Challenge"
FINAL = "N. Oxide Garage: N. Oxide's Final Challenge"
FIRST_EVENT = "N. Oxide's Challenge Cleared"
FINAL_EVENT = "N. Oxide's Final Challenge Cleared"

GEMS = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
KEYS = ["Key"] * 4

# A small, always-satisfiable relic requirement, so a row that is about the
# COMPANION terms is never accidentally decided by the relic term.
RELIC_OPTS = {"oxide_final_challenge_unlock": 0,
              "oxide_final_challenge_relic_count": 3}
RELICS = ["Sapphire Relic"] * 3


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _grant(state, item_names):
    """Put items straight into prog_items and invalidate the region cache.

    Deliberately NOT state.collect()/sweep_for_advancements(): a sweep would
    also collect every reachable ADVANCEMENT event, including the four
    "<boss> Boss Race Won" flags this file uses as the boss tally, which would
    satisfy the companion arm the row under test is trying to leave unmet.
    """
    for name in item_names:
        state.add_item(name, PLAYER, 1)
    state.stale[PLAYER] = True


def _boss_flags(mw):
    return [
        mw.get_location(name, PLAYER).item.name
        for name in ("Ripper Roo Boss Race Won", "Papu Papu Boss Race Won",
                     "Komodo Joe Boss Race Won", "Pinstripe Boss Race Won")
    ]


def _reach(mw, items):
    """(oxide 1 reachable, oxide 2 reachable) from a fresh state holding
    `items`. Uses can_reach, not the bare access_rule, because the four-Key
    half of every row lives on the shared entrance and only region
    reachability applies it."""
    st = CollectionState(mw)
    _grant(st, items)
    return (mw.get_location(FIRST, PLAYER).can_reach(st),
            mw.get_location(FINAL, PLAYER).can_reach(st))


class TestOxideEncounterTruthTable(unittest.TestCase):
    """Location-level truth table. Every row grants the base four Keys, so
    what varies is exactly the encounter-specific terms this fix installs."""

    # --- no companion arm active: both encounters are their plain rules ---

    def test_no_companions_first_opens_on_keys_in_every_mode(self):
        # `none` is absent here on purpose: with no Boss or Gem arm active it
        # is the all-off combination generate_early rejects, so a
        # companion-free `none` seed does not exist. Its own row is
        # test_none_ignores_boss_and_gem_arms_on_both_encounters below.
        for goal in ("first", "final"):
            with self.subTest(goal=goal):
                mw = _build(oxide_goal=goal, **RELIC_OPTS)
                first, final = _reach(mw, KEYS)
                self.assertTrue(first, "Oxide 1 must open on four Keys")
                self.assertFalse(final, "Oxide 2 still needs its relics")

    def test_no_companions_final_opens_on_keys_plus_relics(self):
        for goal in ("first", "final"):
            with self.subTest(goal=goal):
                mw = _build(oxide_goal=goal, **RELIC_OPTS)
                first, final = _reach(mw, KEYS + RELICS)
                self.assertTrue(first)
                self.assertTrue(final)

    # --- oxide_goal: none -- neither race is gated by a non-Oxide goal ---

    def test_none_ignores_boss_and_gem_arms_on_both_encounters(self):
        # Boss-only and Gem-only goals are independently active here. Oxide is
        # ordinary optional content in this mode, so neither arm may tighten
        # either race (#321 implementation check 4).
        mw = _build(oxide_goal="none", bosses_required_goal=4,
                    gems_required_goal=5, **RELIC_OPTS)
        first, final = _reach(mw, KEYS + RELICS)
        self.assertTrue(first, "oxide_goal=none must leave Oxide 1 on Keys")
        self.assertTrue(final, "oxide_goal=none must leave Oxide 2 on relics")

    # --- oxide_goal: any_percent -- companions gate Oxide 1 ---

    def test_any_percent_bosses_one_short_shuts_first(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4, **RELIC_OPTS)
        flags = _boss_flags(mw)
        first, _ = _reach(mw, KEYS + flags[:3])
        self.assertFalse(first)

    def test_any_percent_bosses_exact_opens_first(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4, **RELIC_OPTS)
        flags = _boss_flags(mw)
        first, _ = _reach(mw, KEYS + flags)
        self.assertTrue(first)

    def test_any_percent_bosses_over_satisfied_opens_first(self):
        mw = _build(oxide_goal="first", bosses_required_goal=2, **RELIC_OPTS)
        flags = _boss_flags(mw)
        first, _ = _reach(mw, KEYS + flags)
        self.assertTrue(first)

    def test_any_percent_gems_one_short_shuts_first(self):
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        first, _ = _reach(mw, KEYS + GEMS[:4])
        self.assertFalse(first)

    def test_any_percent_gems_exact_opens_first(self):
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        first, _ = _reach(mw, KEYS + GEMS)
        self.assertTrue(first)

    def test_any_percent_three_way_needs_every_arm(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4,
                    gems_required_goal=5, **RELIC_OPTS)
        flags = _boss_flags(mw)
        self.assertFalse(_reach(mw, KEYS + flags[:3] + GEMS)[0],
                         "bosses one short must shut Oxide 1")
        self.assertFalse(_reach(mw, KEYS + flags + GEMS[:4])[0],
                         "gems one short must shut Oxide 1")
        self.assertFalse(_reach(mw, flags + GEMS)[0],
                         "the four-Key base requirement is still necessary")
        self.assertTrue(_reach(mw, KEYS + flags + GEMS)[0])

    def test_any_percent_final_inherits_the_first_challenge_gate(self):
        # THE ROW THAT MAKES INHERITANCE LOAD-BEARING. Under any_percent the
        # companions are what let the player clear Oxide 1 at all, so Oxide 2
        # -- offered only after that clear -- cannot be reachable while they
        # are unmet, even with the relics in hand.
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        self.assertFalse(_reach(mw, KEYS + RELICS + GEMS[:4])[1])
        self.assertTrue(_reach(mw, KEYS + RELICS + GEMS)[1])

    # --- oxide_goal: 101_percent -- companions gate Oxide 2 only ---

    def test_final_goal_leaves_first_challenge_on_four_keys(self):
        # THE ALPHA 7 REGRESSION, stated directly: a Final-goal seed with
        # every companion arm unmet must still reach Oxide 1 at four Keys.
        mw = _build(oxide_goal="final", bosses_required_goal=4,
                    gems_required_goal=5, **RELIC_OPTS)
        first, final = _reach(mw, KEYS)
        self.assertTrue(first, "101_percent must not gate Oxide 1 on Boss/Gem arms")
        self.assertFalse(final)

    def test_final_goal_bosses_one_short_shuts_final_only(self):
        mw = _build(oxide_goal="final", bosses_required_goal=4, **RELIC_OPTS)
        flags = _boss_flags(mw)
        first, final = _reach(mw, KEYS + RELICS + flags[:3])
        self.assertTrue(first)
        self.assertFalse(final)

    def test_final_goal_bosses_exact_opens_final(self):
        mw = _build(oxide_goal="final", bosses_required_goal=4, **RELIC_OPTS)
        flags = _boss_flags(mw)
        self.assertTrue(_reach(mw, KEYS + RELICS + flags)[1])

    def test_final_goal_gems_one_short_shuts_final_only(self):
        mw = _build(oxide_goal="final", gems_required_goal=5, **RELIC_OPTS)
        first, final = _reach(mw, KEYS + RELICS + GEMS[:4])
        self.assertTrue(first)
        self.assertFalse(final)

    def test_final_goal_gems_exact_opens_final(self):
        mw = _build(oxide_goal="final", gems_required_goal=5, **RELIC_OPTS)
        self.assertTrue(_reach(mw, KEYS + RELICS + GEMS)[1])

    def test_final_goal_three_way_needs_relics_and_every_arm(self):
        mw = _build(oxide_goal="final", bosses_required_goal=4,
                    gems_required_goal=5, **RELIC_OPTS)
        flags = _boss_flags(mw)
        self.assertFalse(_reach(mw, KEYS + flags + GEMS)[1],
                         "relics are still required")
        self.assertFalse(_reach(mw, KEYS + RELICS + flags[:3] + GEMS)[1])
        self.assertFalse(_reach(mw, KEYS + RELICS + flags + GEMS[:4])[1])
        self.assertTrue(_reach(mw, KEYS + RELICS + flags + GEMS)[1])

    def test_configured_relic_mode_and_count_are_honoured_not_the_legacy_18(self):
        # The world.json text rule on the Final Challenge is the legacy fixed
        # 18-Sapphire gate; the contract replaces it with the configured
        # mode + count. Platinum mode proves the replacement really happened:
        # Sapphires must not satisfy it, Platinums must.
        mw = _build(oxide_goal="none", oxide_final_challenge_unlock=2,
                    oxide_final_challenge_relic_count=2,
                    platinum_relic_count=4, bosses_required_goal=4)
        self.assertFalse(_reach(mw, KEYS + ["Sapphire Relic"] * 18)[1])
        self.assertTrue(_reach(mw, KEYS + ["Platinum Relic"] * 2)[1])


class TestOxideGoalEventsFollowTheirEncounter(unittest.TestCase):
    """`_install_goal` lays a code-null companion event beside the selected
    Oxide race, and completion_condition reads THAT, not the location. An
    event left on the bare `has('Key', 4)` text rule would let the sphere
    search believe an Any% goal completes before its companion arms are even
    satisfiable, so the events must carry the same encounter rules."""

    def test_any_percent_event_is_gated_by_its_companions(self):
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        ev = mw.get_location(FIRST_EVENT, PLAYER)
        st = CollectionState(mw)
        _grant(st, KEYS + GEMS[:4])
        self.assertFalse(ev.can_reach(st))
        _grant(st, GEMS[4:])
        self.assertTrue(ev.can_reach(st))

    def test_final_goal_event_is_gated_by_relics_and_companions(self):
        mw = _build(oxide_goal="final", bosses_required_goal=2, **RELIC_OPTS)
        flags = _boss_flags(mw)
        ev = mw.get_location(FINAL_EVENT, PLAYER)
        st = CollectionState(mw)
        _grant(st, KEYS + RELICS)
        self.assertFalse(ev.can_reach(st), "companions still unmet")
        _grant(st, flags[:2])
        self.assertTrue(ev.can_reach(st))

    def test_final_goal_event_still_needs_its_relics(self):
        mw = _build(oxide_goal="final", bosses_required_goal=2, **RELIC_OPTS)
        flags = _boss_flags(mw)
        ev = mw.get_location(FINAL_EVENT, PLAYER)
        st = CollectionState(mw)
        _grant(st, KEYS + flags[:2])
        self.assertFalse(ev.can_reach(st))
        _grant(st, RELICS)
        self.assertTrue(ev.can_reach(st))

    def test_completion_condition_agrees_with_the_events(self):
        # The goal predicate is the AND of the active arms over the SAME
        # flags; this proves the two halves of the contract were not wired to
        # different truths.
        mw = _build(oxide_goal="first", bosses_required_goal=2, **RELIC_OPTS)
        flags = _boss_flags(mw)
        flag_item = mw.get_location(FIRST_EVENT, PLAYER).item.name
        st = CollectionState(mw)
        _grant(st, KEYS + flags[:2])
        self.assertFalse(mw.completion_condition[PLAYER](st))
        _grant(st, [flag_item])
        self.assertTrue(mw.completion_condition[PLAYER](st))


class TestOxideDisabledRemovesTheContent(unittest.TestCase):
    """Issue #320: `disabled` is a stronger value than `none` -- the garage
    never opens and both races leave the seed entirely."""

    def _disabled(self, **extra):
        opts = {"oxide_goal": "disabled", "bosses_required_goal": 4}
        opts.update(extra)
        return _build(**opts)

    def test_both_locations_are_absent_from_the_generated_world(self):
        mw = self._disabled()
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertNotIn(FIRST, names)
        self.assertNotIn(FINAL, names)

    def test_none_keeps_both_locations(self):
        # The distinction that justifies a separate wire value: `none` is
        # optional Oxide, not absent Oxide.
        mw = _build(oxide_goal="none", bosses_required_goal=4)
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertIn(FIRST, names)
        self.assertIn(FINAL, names)

    def test_locations_are_removed_not_merely_excluded(self):
        # "They must not remain as excluded or permanently unreachable
        # checks" (#320 expected behavior 2). An EXCLUDED location would
        # still be in get_locations and would still be sent by the client.
        mw = self._disabled()
        for loc in mw.get_locations(PLAYER):
            self.assertNotIn("N. Oxide's", loc.name)

    def test_the_garage_door_is_shut(self):
        mw = self._disabled()
        st = CollectionState(mw)
        _grant(st, KEYS + ["Sapphire Relic"] * 18)
        self.assertFalse(
            mw.get_entrance("N. Oxide Garage Door", PLAYER).can_reach(st))

    def test_no_oxide_goal_events_are_laid(self):
        mw = self._disabled()
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertNotIn(FIRST_EVENT, names)
        self.assertNotIn(FINAL_EVENT, names)

    def test_boss_only_goal_still_completes(self):
        mw = self._disabled()
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, flags)
        self.assertTrue(mw.completion_condition[PLAYER](st))

    def test_gem_only_goal_still_completes(self):
        mw = self._disabled(bosses_required_goal=0, gems_required_goal=5)
        st = CollectionState(mw)
        _grant(st, GEMS)
        self.assertTrue(mw.completion_condition[PLAYER](st))

    def test_combined_boss_and_gem_goal_is_conjunctive(self):
        mw = self._disabled(bosses_required_goal=2, gems_required_goal=3)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, flags[:2])
        self.assertFalse(mw.completion_condition[PLAYER](st))
        _grant(st, GEMS[:3])
        self.assertTrue(mw.completion_condition[PLAYER](st))

    def test_all_goal_arms_off_is_rejected(self):
        with self.assertRaises(OptionError) as ctx:
            setup_multiworld(ctrAPWorld, ("generate_early",), seed=1,
                             options={"oxide_goal": "disabled",
                                      "bosses_required_goal": 0,
                                      "gems_required_goal": 0})
        self.assertIn("disabled", str(ctx.exception))

    def test_wire_carries_value_three_at_the_bumped_schema(self):
        mw = self._disabled()
        wire = mw.worlds[PLAYER].fill_slot_data()
        self.assertEqual(wire["ctr_options"]["goal_oxide"],
                         OxideGoal.option_disabled)
        self.assertEqual(wire["ctr_options"]["goal_oxide"], 3)
        self.assertEqual(wire["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["goal"], -1,
                         "disabled has no legacy single-goal analogue")

    def test_total_locations_drops_by_exactly_the_two_races(self):
        common = {"bosses_required_goal": 4, "gems_required_goal": 0}
        optional = _build(oxide_goal="none", **common)
        disabled = _build(oxide_goal="disabled", **common)
        # `none` additionally lays no Oxide goal events, so the two worlds
        # differ by the two race locations alone.
        self.assertEqual(
            optional.worlds[PLAYER].fill_slot_data()["TotalLocations"] - 2,
            disabled.worlds[PLAYER].fill_slot_data()["TotalLocations"])

    def test_final_challenge_unlock_mode_and_count_are_ignored(self):
        # #320 acceptance 4: a mode/count pair that a `none` seed rejects
        # outright must generate cleanly when the location does not exist.
        with self.assertRaises(OptionError):
            setup_multiworld(ctrAPWorld, ("generate_early",), seed=1,
                             options={"oxide_goal": "none",
                                      "bosses_required_goal": 4,
                                      "oxide_final_challenge_unlock": 0,
                                      "oxide_final_challenge_relic_count": 30})
        mw = self._disabled(oxide_final_challenge_unlock=0,
                            oxide_final_challenge_relic_count=30)
        self.assertIsNotNone(mw)

    def test_full_accessibility_generates_without_the_removed_locations(self):
        mw = self._disabled(accessibility="full")
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertNotIn(FINAL, names)


class TestOxideEncounterMutations(unittest.TestCase):
    """Each mutant is a distinct way an encounter-specific term could be
    reverted or bypassed. Every one asserts a row the FIXED source gets right
    and the mutant gets wrong, so the truth table above is sensitive to that
    term rather than merely consistent with it."""

    def _rules(self):
        from .. import Rules
        return Rules

    def test_mutant_companions_applied_to_the_shared_door_again(self):
        # The pre-RC shape: put the conjunction back on the entrance, so both
        # encounters inherit it. Distinguished by the Alpha 7 regression row.
        mw = _build(oxide_goal="final", gems_required_goal=5, **RELIC_OPTS)
        self.assertTrue(_reach(mw, KEYS)[0],
                        "fixed source: Final-goal Oxide 1 opens on four Keys")
        door = mw.get_entrance("N. Oxide Garage Door", PLAYER)
        base = door.access_rule
        companions = self._rules().oxide_companion_predicate(mw.worlds[PLAYER])
        door.access_rule = (lambda st, b=base, c=companions:
                            b(st) and c(st))
        self.assertFalse(_reach(mw, KEYS)[0],
                         "mutant: the shared door wrongly re-locks Oxide 1")

    def test_mutant_companion_terms_omitted_entirely(self):
        # Drop the companion conjunction from both encounters (the state this
        # subsystem had before WO-A1). Distinguished by the Any% row.
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        self.assertFalse(_reach(mw, KEYS)[0])
        # Restate Oxide 1 as the bare pre-WO-A1 rule (the entrance still
        # supplies the four Keys), rather than re-running the installer --
        # the installer ANDs onto whatever it already tightened, so a second
        # pass could not loosen anything and would prove nothing.
        mw.get_location(FIRST, PLAYER).access_rule = lambda st: True
        self.assertTrue(_reach(mw, KEYS)[0],
                        "mutant: Any% Oxide 1 wrongly opens with no Gems")

    def test_mutant_companions_wired_to_the_wrong_encounter(self):
        # Swap which encounter the companions gate (any_percent <-> final).
        # Distinguished in both directions at once.
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        first_ok, final_ok = _reach(mw, KEYS + RELICS + GEMS[:4])
        self.assertFalse(first_ok, "fixed: Any% gates Oxide 1")
        companions = self._rules().oxide_companion_predicate(mw.worlds[PLAYER])
        relic = mw.worlds[PLAYER]._oxide_final_relic_rule()
        mw.get_location(FIRST, PLAYER).access_rule = lambda st: True
        mw.get_location(FINAL, PLAYER).access_rule = (
            lambda st, r=relic, c=companions: r(st) and c(st))
        self.assertTrue(_reach(mw, KEYS + RELICS + GEMS[:4])[0],
                        "mutant: Any% Oxide 1 wrongly opens with Gems short")

    def test_mutant_final_drops_its_inheritance_of_the_first_challenge(self):
        # Oxide 2 re-stated as "Keys + relics" instead of "Oxide 1 + relics".
        # Distinguished under any_percent, where the companions are what make
        # the first clear possible at all.
        mw = _build(oxide_goal="first", gems_required_goal=5, **RELIC_OPTS)
        self.assertFalse(_reach(mw, KEYS + RELICS + GEMS[:4])[1],
                         "fixed: Oxide 2 is behind an unclearable Oxide 1")
        relic = mw.worlds[PLAYER]._oxide_final_relic_rule()
        mw.get_location(FINAL, PLAYER).access_rule = lambda st, r=relic: r(st)
        self.assertTrue(_reach(mw, KEYS + RELICS + GEMS[:4])[1],
                        "mutant: Oxide 2 wrongly reachable without the clear")

    def test_mutant_final_drops_its_relic_term(self):
        mw = _build(oxide_goal="none", bosses_required_goal=4, **RELIC_OPTS)
        self.assertFalse(_reach(mw, KEYS)[1], "fixed: relics are required")
        mw.get_location(FINAL, PLAYER).access_rule = lambda st: True
        self.assertTrue(_reach(mw, KEYS)[1],
                        "mutant: Oxide 2 wrongly opens with no relics")

    def test_mutant_none_mode_accidentally_tightened(self):
        # Applying the conjunction whenever ANY arm is active, without asking
        # whether Oxide is the goal. Distinguished by the `none` row.
        mw = _build(oxide_goal="none", bosses_required_goal=4,
                    gems_required_goal=5, **RELIC_OPTS)
        self.assertTrue(_reach(mw, KEYS)[0], "fixed: none leaves Oxide 1 open")
        companions = self._rules().oxide_companion_predicate(mw.worlds[PLAYER])
        self.assertIsNotNone(
            companions,
            "the arms ARE active here -- that is what makes this mutant "
            "reachable rather than vacuous")
        mw.get_location(FIRST, PLAYER).access_rule = (
            lambda st, c=companions: c(st))
        self.assertFalse(_reach(mw, KEYS)[0],
                         "mutant: optional Oxide wrongly becomes a goal gate")

    def test_mutant_disabled_leaves_the_locations_in_the_seed(self):
        # Distinguished by the removal assertion itself: prove the skip in
        # create_regions is what removes them, by showing the same seed keeps
        # them under every other value.
        disabled_names = {loc.name for loc in
                          _build(oxide_goal="disabled",
                                 bosses_required_goal=4).get_locations(PLAYER)}
        for goal in ("none", "first", "final"):
            with self.subTest(goal=goal):
                kept = {loc.name for loc in
                        _build(oxide_goal=goal,
                               bosses_required_goal=4).get_locations(PLAYER)}
                self.assertIn(FIRST, kept)
                self.assertNotIn(FIRST, disabled_names)


class TestOxideAccessUniversalTrackerParity(CTRTestBase):
    """UT reconstruction (issue #29) restores oxide_goal / bosses_required_goal
    / gems_required_goal from the connected seed's wire slot_data before
    re-generating; this proves a reconstructed world answers the same for BOTH
    encounters as the originally generated world, on the same state -- the
    golden rule this subsystem's 2026-08-23 Gem Cup audit established, applied
    to the encounter-aware contract."""

    run_default_tests = False
    options = {"oxide_goal": "final", "bosses_required_goal": 2,
               "oxide_final_challenge_unlock": 0,
               "oxide_final_challenge_relic_count": 3}

    def _reconstruct(self, wire, seed=2):
        from worlds.AutoWorld import call_all
        mw = setup_multiworld(ctrAPWorld, steps=(), seed=seed)
        mw.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in STEPS:
            call_all(mw, step)
        return mw

    def test_reconstructed_world_matches_both_encounter_rules(self):
        original_mw = self.multiworld
        original_world = original_mw.worlds[PLAYER]
        wire = original_world.fill_slot_data()

        # multiworld.re_gen_passthrough is populated BEFORE generate_early
        # runs; generate_early itself calls _ut_restore_options at the top,
        # ahead of every option-dependent draw, which is why this drives the
        # real step sequence instead of calling _ut_restore_options directly.
        reconstructed_mw = self._reconstruct(wire)
        reconstructed_world = reconstructed_mw.worlds[PLAYER]

        for opt in ("oxide_goal", "bosses_required_goal", "gems_required_goal"):
            self.assertEqual(getattr(original_world.options, opt).value,
                             getattr(reconstructed_world.options, opt).value)

        for mw in (original_mw, reconstructed_mw):
            flags = _boss_flags(mw)
            # Final goal: Oxide 1 opens on four Keys alone in BOTH worlds...
            self.assertTrue(_reach(mw, KEYS)[0])
            # ...and Oxide 2 waits for relics AND the two boss wins.
            self.assertFalse(_reach(mw, KEYS + RELICS)[1])
            self.assertFalse(_reach(mw, KEYS + flags[:2])[1])
            self.assertTrue(_reach(mw, KEYS + RELICS + flags[:2])[1])

    def test_reconstructed_disabled_world_also_drops_the_locations(self):
        # A disabled seed's wire carries goal_oxide 3; UT must rebuild the
        # same location set, or the tracker would list two checks the server
        # does not have.
        source = _build(oxide_goal="disabled", bosses_required_goal=4)
        wire = source.worlds[PLAYER].fill_slot_data()
        self.assertEqual(wire["ctr_options"]["goal_oxide"], 3)
        rebuilt = self._reconstruct(wire, seed=3)
        self.assertEqual(rebuilt.worlds[PLAYER].options.oxide_goal.value,
                         OxideGoal.option_disabled)
        names = {loc.name for loc in rebuilt.get_locations(PLAYER)}
        self.assertNotIn(FIRST, names)
        self.assertNotIn(FINAL, names)


if __name__ == "__main__":
    unittest.main()
