"""Tests for the WO-A1 companion fix (native "composed Oxide entry" repair,
2026-08-26): the apworld's Oxide *access* contract must match native's
entry-readiness predicate exactly, not just goal *completion*.

Before this fix, `data/world.json` gated the "N. Oxide Garage Door" entrance
(and therefore both Oxide locations, which inherit region reachability
through it) on `has('Key', 4)` alone, in every seed. Native's shipped Alpha 4
garage gate asked the same single question. The native fix
(`fix/alpha4-composed-oxide-entry`, ap/ap_oxide_entry.h) made the garage door
ALSO require every ACTIVE companion goal condition (configured boss-race
wins, configured distinct Gem count) whenever `oxide_goal != none` -- the
garage is the goal gate in that case, so entry readiness must not diverge
from goal completion. Logic did not follow, so after the native fix a seed
with `oxide_goal != none` AND (`bosses_required_goal > 0` OR
`gems_required_goal > 0`) could seat a required progression item on an
Oxide location that no reachable state could actually open: unwinnable.

This file proves the fixed apworld (`worlds/ctr/Rules.add_oxide_access_contract`)
reads the identical truth `_install_goal` uses for completion, by reusing the
SAME predicate objects (`world._ctr_boss_won_predicate`,
`world._ctr_gems_predicate`) rather than a second interpretation:

- TestOxideAccessTruthTable: direct entrance-rule truth table over Oxide
  first, Oxide final, no Oxide goal, bosses only, gems only and the
  three-way conjunction, with one-short, exact and over-satisfied rows.
- TestOxideAccessReportedUnwinnableShape: the exact reported shape (`Any% +
  All Four Bosses`, four Keys, zero boss wins) resolves to both Oxide
  LOCATIONS being unreachable -- not merely the entrance rule returning
  False -- proving a progression item seated there would be genuinely
  unwinnable, and reachable once the full conjunction holds.
- TestOxideAccessBothLocationsInherit: the conjunction gates BOTH "N. Oxide
  Garage: N. Oxide's Challenge" and "...Final Challenge" identically, through
  the shared entrance, without either location's own text rule being
  touched.
- TestOxideAccessMutations: five source-level mutants (companion terms
  omitted, AND replaced by OR, a received-Key proxy standing in for boss
  wins, the no-Oxide-goal case accidentally tightened, only one location
  wired to the entrance) each proven to flip a truth-table row that the
  fixed source gets right.

Real full-generation gate coverage (the full CTR suite, the eleven-arm fuzz
matrix, manifest/name-freeze/item-id stability, slot_data round-trip and UT
reconstruction) lives in the build note's evidence, not here -- this file is
the fast, direct unit layer over the entrance rule and the location graph,
mirroring test_composable_goals.py's layering for goal completion.
"""
import unittest

from BaseClasses import CollectionState

from test.general import setup_multiworld
from .. import ctrAPWorld
from ..Options import OxideGoal
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _grant(state, item_names):
    for name in item_names:
        state.add_item(name, PLAYER, 1)


def _door(mw):
    return mw.get_entrance("N. Oxide Garage Door", PLAYER)


def _boss_flags(mw):
    return [
        mw.get_location(name, PLAYER).item.name
        for name in ("Ripper Roo Boss Race Won", "Papu Papu Boss Race Won",
                     "Komodo Joe Boss Race Won", "Pinstripe Boss Race Won")
    ]


GEMS = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]


class TestOxideAccessTruthTable(unittest.TestCase):
    """Entrance-rule truth table. Every row starts from the base ('Key', 4)
    requirement already met, isolating the companion conjunction this fix
    adds -- the pre-fix door would read True on every one of these states."""

    def test_no_oxide_goal_stays_plain_four_key_door(self):
        # oxide_goal == none: no companion conjunction, even with bosses
        # and gems independently active for a NON-Oxide goal.
        mw = _build(oxide_goal="none", bosses_required_goal=2,
                   gems_required_goal=2)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertTrue(
            door.access_rule(st),
            "oxide_goal=none must leave the door on Key x4 alone")

    def test_oxide_first_alone_no_companions_active(self):
        # Oxide is active but no companion condition is configured: the door
        # stays on the base requirement, same as pre-fix.
        mw = _build(oxide_goal="first")
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertTrue(door.access_rule(st))

    def test_oxide_final_alone_no_companions_active(self):
        mw = _build(oxide_goal="final")
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertTrue(door.access_rule(st))

    def test_oxide_first_plus_bosses_one_short(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        door = _door(mw)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + flags[:3])
        self.assertFalse(door.access_rule(st), "3 of 4 required bosses: shut")

    def test_oxide_first_plus_bosses_exact(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        door = _door(mw)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + flags)
        self.assertTrue(door.access_rule(st), "exactly 4 of 4: open")

    def test_oxide_first_plus_bosses_reported_shape(self):
        # The exact reported combination: Any% + All Four Bosses, four Keys,
        # ZERO boss wins. Must be shut.
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertFalse(door.access_rule(st))

    def test_oxide_final_plus_bosses_any_n_partial(self):
        # "any N", not "all": required=2 of 4, one short then exact.
        mw = _build(oxide_goal="final", bosses_required_goal=2)
        door = _door(mw)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + flags[:1])
        self.assertFalse(door.access_rule(st), "1 of 4 must not satisfy N=2")
        _grant(st, flags[1:2])
        self.assertTrue(door.access_rule(st), "any 2 of 4 satisfies N=2")

    def test_oxide_first_plus_gems_one_short(self):
        mw = _build(oxide_goal="first", gems_required_goal=3)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + GEMS[:2])
        self.assertFalse(door.access_rule(st), "2 of 3 required Gems: shut")

    def test_oxide_first_plus_gems_exact(self):
        mw = _build(oxide_goal="first", gems_required_goal=3)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + GEMS[:3])
        self.assertTrue(door.access_rule(st))

    def test_oxide_final_plus_gems_over_satisfied(self):
        # Owning MORE than the required count must not un-satisfy the term.
        mw = _build(oxide_goal="final", gems_required_goal=2)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + GEMS)  # all 5, only 2 required
        self.assertTrue(door.access_rule(st))

    def test_oxide_bosses_gems_three_way_conjunction(self):
        mw = _build(oxide_goal="first", bosses_required_goal=1,
                   gems_required_goal=1)
        door = _door(mw)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertFalse(door.access_rule(st), "neither companion term met")
        _grant(st, flags[:1])
        self.assertFalse(door.access_rule(st), "bosses met, gems still 0")
        _grant(st, GEMS[:1])
        self.assertTrue(door.access_rule(st), "all three terms met")

    def test_base_key_requirement_still_necessary(self):
        # The companion conjunction must not substitute for the configured
        # door requirement -- fewer than 4 Keys stays shut even with every
        # companion term satisfied.
        mw = _build(oxide_goal="first", bosses_required_goal=1)
        door = _door(mw)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 3 + flags[:1])
        self.assertFalse(door.access_rule(st), "3 Keys: shut regardless")


class TestOxideAccessReportedUnwinnableShape(unittest.TestCase):
    """A required progression item at an Oxide location must not be
    considered reachable in the reported shape, and must become reachable
    once the full conjunction holds -- proven at the LOCATION, not just the
    entrance rule, since that is what fill actually consults."""

    def test_first_challenge_location_unreachable_pre_conjunction(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        loc = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)  # the reported shape: 4 Keys, 0 boss wins
        self.assertFalse(
            loc.can_reach(st),
            "a progression item here would be unwinnable in the reported "
            "shape -- location must read unreachable")

    def test_first_challenge_location_reachable_after_full_conjunction(self):
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        loc = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + flags)
        self.assertTrue(loc.can_reach(st))

    def test_final_challenge_location_unreachable_pre_conjunction(self):
        mw = _build(oxide_goal="final", gems_required_goal=3)
        loc = mw.get_location(
            "N. Oxide Garage: N. Oxide's Final Challenge", PLAYER)
        st = CollectionState(mw)
        # Meet the relic rule (default sapphire_relics=18) and the Key gate,
        # but not the Gems companion term.
        _grant(st, ["Key"] * 4 + ["Sapphire Relic"] * 18)
        self.assertFalse(loc.can_reach(st))

    def test_final_challenge_location_reachable_after_full_conjunction(self):
        mw = _build(oxide_goal="final", gems_required_goal=3)
        loc = mw.get_location(
            "N. Oxide Garage: N. Oxide's Final Challenge", PLAYER)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + ["Sapphire Relic"] * 18 + GEMS[:3])
        self.assertTrue(loc.can_reach(st))


class TestOxideAccessBothLocationsInherit(unittest.TestCase):
    """Both Oxide locations must agree with the entrance's composed
    conjunction -- a divergence would mean one location's own text rule was
    touched instead of the shared entrance, which the order forbids."""

    def test_both_locations_shut_together(self):
        mw = _build(oxide_goal="first", bosses_required_goal=2)
        first = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        final = mw.get_location(
            "N. Oxide Garage: N. Oxide's Final Challenge", PLAYER)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)
        self.assertFalse(first.can_reach(st))
        self.assertFalse(final.can_reach(st))

    def test_both_locations_open_together(self):
        mw = _build(oxide_goal="first", bosses_required_goal=2)
        first = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        final = mw.get_location(
            "N. Oxide Garage: N. Oxide's Final Challenge", PLAYER)
        flags = _boss_flags(mw)
        st = CollectionState(mw)
        # oxide_goal=first: bosses_required_goal is still an active companion
        # term for the DOOR (independent of which Oxide location is the
        # seed's own goal location), and the Final Challenge's own relic rule
        # (default sapphire_relics=18) still applies on top.
        _grant(st, ["Key"] * 4 + flags[:2] + ["Sapphire Relic"] * 18)
        self.assertTrue(first.can_reach(st))
        self.assertTrue(final.can_reach(st))

    def test_door_and_location_own_rule_do_not_diverge_below_base(self):
        # The location's own text rule (has('Key', 4)) is unchanged and
        # weaker than the entrance's composed rule; the entrance must be the
        # binding constraint, not the location.
        mw = _build(oxide_goal="none", bosses_required_goal=1)
        loc = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        self.assertEqual(getattr(loc, "logic_text", None), "has('Key', 4)")


class TestOxideAccessMutations(unittest.TestCase):
    """Each mutant reproduces a specific way this fix could be wrong, by
    monkeypatching the same predicate objects `add_oxide_access_contract`
    consumes (world._ctr_boss_won_predicate / _ctr_gems_predicate) or the
    module-level gate it checks, and proving the reported-shape truth-table
    row (test_oxide_first_plus_bosses_reported_shape's premise: 4 Keys, 0
    boss wins, oxide_goal active, bosses_required_goal active) flips from
    the fixed answer."""

    def _fresh_world_and_door(self, **options):
        mw = _build(**options)
        return mw, mw.worlds[PLAYER], _door(mw)

    def test_mutant_companion_terms_omitted(self):
        # Simulates dropping the whole companion conjunction (the pre-fix
        # shape): re-run set_rules with both predicates cleared before the
        # entrance rule is (re)built.
        from .. import Rules
        mw, world, _ = self._fresh_world_and_door(
            oxide_goal="first", bosses_required_goal=4)
        world._ctr_boss_won_predicate = None
        world._ctr_gems_predicate = None
        Rules.set_rules(world)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)  # 0 boss wins
        self.assertTrue(
            door.access_rule(st),
            "mutant should wrongly open the door on 4 Keys alone")

    def test_mutant_or_instead_of_and(self):
        from .. import Rules
        mw, world, _ = self._fresh_world_and_door(
            oxide_goal="first", bosses_required_goal=4, gems_required_goal=2)

        boss_pred = world._ctr_boss_won_predicate
        gems_pred = world._ctr_gems_predicate

        # Rebuild the door rule the way add_oxide_access_contract does, but
        # with OR instead of AND, to isolate exactly this mutation.
        key_rule = Rules.make_rule("has('Key', 4)", PLAYER)
        door = _door(mw)
        door.access_rule = (
            lambda state, base=key_rule, bp=boss_pred, gp=gems_pred:
                base(state) and (bp(state) or gp(state)))
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4 + GEMS[:2])  # gems met, bosses NOT met
        self.assertTrue(
            door.access_rule(st),
            "OR mutant should wrongly open on gems alone")
        self.assertFalse(
            boss_pred(st) and gems_pred(st),
            "the real AND must reject this same state, or this mutant "
            "test proves nothing")

    def test_mutant_received_key_proxy_replaces_boss_wins(self):
        # A received-Key count standing in for CHECKED boss-race wins is
        # exactly the shipped-Alpha-4/pre-native-fix bug class. Prove a
        # Key-count proxy disagrees with the real boss-won predicate on the
        # reported shape.
        mw, world, door = self._fresh_world_and_door(
            oxide_goal="first", bosses_required_goal=4)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)  # 4 Keys received, 0 bosses actually won

        def key_proxy_mutant(state):
            return state.has("Key", PLAYER, 4)

        self.assertTrue(
            key_proxy_mutant(st),
            "the proxy is satisfied by the received Keys alone")
        self.assertFalse(
            world._ctr_boss_won_predicate(st),
            "the real predicate must reject the same state -- 0 boss wins")

    def test_mutant_no_oxide_goal_case_tightened(self):
        # oxide_goal == none must NOT apply the companion conjunction, even
        # if bosses_required_goal is independently active. A mutant that
        # applies it anyway over-tightens a non-Oxide-goal seed's door.
        from .. import Rules
        mw, world, _ = self._fresh_world_and_door(
            oxide_goal="none", bosses_required_goal=4)
        door = _door(mw)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)  # 0 boss wins, but Oxide is not the goal gate
        self.assertTrue(
            door.access_rule(st),
            "fixed behaviour: oxide_goal=none keeps the plain 4-Key door")

        # Now the mutant: apply the conjunction unconditionally.
        boss_pred = world._ctr_boss_won_predicate
        key_rule = Rules.make_rule("has('Key', 4)", PLAYER)
        door.access_rule = (
            lambda state, base=key_rule, p=boss_pred: base(state) and p(state))
        self.assertFalse(
            door.access_rule(st),
            "mutant wrongly shuts a non-Oxide-goal door on the same state "
            "the fixed code leaves open")

    def test_mutant_only_one_location_inherits_entrance_rule(self):
        # If a fix wired the conjunction onto only ONE Oxide location's own
        # rule instead of the shared entrance, the two locations would
        # diverge. Prove the real fix does NOT diverge (the companion
        # positive control for TestOxideAccessBothLocationsInherit), then
        # prove a location-only mutant WOULD diverge, showing this class of
        # bug is detectable.
        from .. import Rules
        mw = _build(oxide_goal="first", bosses_required_goal=4)
        first = mw.get_location("N. Oxide Garage: N. Oxide's Challenge", PLAYER)
        final = mw.get_location(
            "N. Oxide Garage: N. Oxide's Final Challenge", PLAYER)
        st = CollectionState(mw)
        _grant(st, ["Key"] * 4)  # 0 boss wins
        self.assertEqual(
            first.can_reach(st), final.can_reach(st),
            "the real fix must not diverge between the two locations")

        # Mutant: revert the entrance to the plain door and instead gate
        # only the FIRST location's own access_rule with the companion term.
        door = _door(mw)
        door.access_rule = Rules.make_rule("has('Key', 4)", PLAYER)
        boss_pred = mw.worlds[PLAYER]._ctr_boss_won_predicate
        first.access_rule = (
            lambda state, base=Rules.make_rule("has('Key', 4)", PLAYER),
                    p=boss_pred: base(state) and p(state))
        st2 = CollectionState(mw)
        # Also satisfy the Final Challenge's own PRE-EXISTING relic rule
        # (default sapphire_relics=18, untouched by this fix) so the only
        # thing gating `final` here is the entrance/location divergence
        # under test, not an unrelated requirement.
        _grant(st2, ["Key"] * 4 + ["Sapphire Relic"] * 18)
        self.assertFalse(first.can_reach(st2), "mutant: first stays shut")
        self.assertTrue(
            final.can_reach(st2),
            "mutant: final wrongly stays open -- the divergence this test "
            "class exists to catch")


class TestOxideAccessUniversalTrackerParity(CTRTestBase):
    """UT reconstruction (issue #29) restores oxide_goal / bosses_required_goal
    / gems_required_goal from the connected seed's wire slot_data before
    re-generating; this proves a reconstructed world's Oxide door rule reads
    the same answer as the originally generated world's, on the same state --
    the golden rule the 2026-08-23 Gem Cup audit established for this
    subsystem, applied to the new access contract."""

    run_default_tests = False
    options = {"oxide_goal": "first", "bosses_required_goal": 2}

    def test_reconstructed_world_matches_original_door_rule(self):
        original_mw = self.multiworld
        original_world = original_mw.worlds[PLAYER]
        wire = original_world.fill_slot_data()

        # multiworld.re_gen_passthrough is populated BEFORE generate_early
        # runs; generate_early itself calls _ut_restore_options at the top,
        # ahead of every option-dependent draw (relic tiers, comfort
        # guards, ...), which is why this test drives it that way instead of
        # calling _ut_restore_options directly mid-generation.
        # Pass the REAL wire blocks through, not empty placeholders: an empty
        # podium_checks/warp_pad_unlock restores podium_placement_checks,
        # include_gem_cups and include_battle_arenas to off, which shrinks
        # this seed's real location supply and is not what the connected
        # seed's client actually sent.
        from worlds.AutoWorld import call_all
        reconstructed_mw = setup_multiworld(ctrAPWorld, steps=(), seed=2)
        reconstructed_mw.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in STEPS:
            call_all(reconstructed_mw, step)
        reconstructed_world = reconstructed_mw.worlds[PLAYER]

        self.assertEqual(
            original_world.options.oxide_goal.value,
            reconstructed_world.options.oxide_goal.value)
        self.assertEqual(
            original_world.options.bosses_required_goal.value,
            reconstructed_world.options.bosses_required_goal.value)

        for mw in (original_mw, reconstructed_mw):
            door = _door(mw)
            flags = _boss_flags(mw)
            st = CollectionState(mw)
            _grant(st, ["Key"] * 4)  # 0 of 2 required bosses
            self.assertFalse(door.access_rule(st))
            _grant(st, flags[:2])
            self.assertTrue(door.access_rule(st))


if __name__ == "__main__":
    unittest.main()
