"""Tests for issue #152 (composable goal conditions, Package C).

The legacy single `goal` Choice (oxide/oxidefinal/allbosses/allgemcups) is
replaced by three independent conditions ANDed together: `oxide_goal`
(none/first/final), `bosses_required_goal` (0-4) and `gems_required_goal`
(0-5). This file covers what the #152 build note calls out as the gates:

- a goal-completion truth table at generation level: each condition alone,
  every pairwise conjunction, the three-way conjunction, and the four
  single-condition combinations that are byte-equivalent to a legacy goal
  value (0 oxide / 1 oxidefinal / 3 allbosses / 4 allgemcups);
- the new/generalized generate_early guards (C1 empty goal, C2 gems+cups,
  C3/C4 oxide-final progression, kept in lockstep with
  _relic_progression_map);
- UT restore round-trip, both directions: a pre-#152 seed's legacy `goal`
  int translated into the equivalent composed options, and a #152 seed's
  goal_oxide/goal_bosses/goal_gems keys restored directly.

Real full-generation gate coverage (manifest --check, the ELEVEN-check fuzz
matrix, the before/after comparison for the C5/C6 sphere-search drift fix)
lives in the build note's evidence, not here -- this file is the fast,
direct unit layer over completion_condition and the wire.
"""
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld
from ..Options import OxideGoal
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
EARLY = ("generate_early",)


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _early(seed=1, **options):
    return setup_multiworld(ctrAPWorld, EARLY, seed=seed, options=options)


def _grant(state, mw, player, item_names):
    """Add one copy of each named item/flag directly to a scratch
    CollectionState's prog_items -- exactly what state.has()/has_from_list*
    read, and exactly what completion_condition predicates check, without
    going through region reachability or the real fill (this project's
    completion predicates are event-flag/singleton-item counts by design,
    Spec §5, so a direct prog_items bump is a faithful, minimal probe)."""
    for name in item_names:
        state.add_item(name, player, 1)


class TestGoalCompletionTruthTable(unittest.TestCase):
    """completion_condition, evaluated against a scratch CollectionState with
    exactly the flags/items the seed's own goal conditions need -- never
    against a full fill, so each row isolates one predicate combination."""

    PLAYER = 1

    def _condition(self, mw):
        return mw.completion_condition[self.PLAYER]

    def _oxide_first_flag(self, mw):
        return mw.get_location(
            "N. Oxide's Challenge Cleared", self.PLAYER).item.name

    def _oxide_final_flag(self, mw):
        return mw.get_location(
            "N. Oxide's Final Challenge Cleared", self.PLAYER).item.name

    def _boss_flags(self, mw):
        return [
            mw.get_location(name, self.PLAYER).item.name
            for name in ("Ripper Roo Boss Race Won", "Papu Papu Boss Race Won",
                         "Komodo Joe Boss Race Won", "Pinstripe Boss Race Won")
        ]

    # -- single conditions, each byte-equivalent to a legacy goal value --

    def test_oxide_first_alone(self):
        mw = _build(oxide_goal="first")
        cc = self._condition(mw)
        st = CollectionState(mw)
        self.assertFalse(cc(st))
        _grant(st, mw, self.PLAYER, ["Key", "Key", "Key", "Key",
                                      self._oxide_first_flag(mw)])
        self.assertTrue(cc(st))

    def test_oxide_final_alone(self):
        mw = _build(oxide_goal="final")
        cc = self._condition(mw)
        st = CollectionState(mw)
        self.assertFalse(cc(st))
        # Default oxide_final_challenge_unlock (sapphire_relics) + default
        # oxide_final_challenge_relic_count (18): the relic rule needs 18
        # Sapphire Relics ANDed with the Key-4 companion flag.
        _grant(st, mw, self.PLAYER,
              ["Key"] * 4 + [self._oxide_final_flag(mw)])
        self.assertFalse(cc(st), "flag alone must not satisfy the relic rule")
        _grant(st, mw, self.PLAYER, ["Sapphire Relic"] * 18)
        self.assertTrue(cc(st))

    def test_bosses_required_four_alone(self):
        mw = _build(oxide_goal="none", bosses_required_goal=4)
        cc = self._condition(mw)
        st = CollectionState(mw)
        flags = self._boss_flags(mw)
        self.assertFalse(cc(st))
        _grant(st, mw, self.PLAYER, flags[:3])
        self.assertFalse(cc(st), "3 of 4 must not satisfy a required count of 4")
        _grant(st, mw, self.PLAYER, flags[3:])
        self.assertTrue(cc(st))

    def test_gems_required_five_alone(self):
        mw = _build(oxide_goal="none", gems_required_goal=5)
        cc = self._condition(mw)
        st = CollectionState(mw)
        gems = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        self.assertFalse(cc(st))
        _grant(st, mw, self.PLAYER, gems[:4])
        self.assertFalse(cc(st))
        _grant(st, mw, self.PLAYER, gems[4:])
        self.assertTrue(cc(st))

    # -- partial counts (the actual #152 ask: "any N", not just "all") --

    def test_bosses_required_two_of_four(self):
        mw = _build(oxide_goal="none", bosses_required_goal=2)
        cc = self._condition(mw)
        st = CollectionState(mw)
        flags = self._boss_flags(mw)
        _grant(st, mw, self.PLAYER, flags[:1])
        self.assertFalse(cc(st), "1 of 4 must not satisfy a required count of 2")
        _grant(st, mw, self.PLAYER, flags[1:2])
        self.assertTrue(cc(st), "any 2 of 4 must satisfy a required count of 2")

    def test_gems_required_three_of_five(self):
        mw = _build(oxide_goal="none", gems_required_goal=3)
        cc = self._condition(mw)
        st = CollectionState(mw)
        gems = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        _grant(st, mw, self.PLAYER, gems[:2])
        self.assertFalse(cc(st))
        _grant(st, mw, self.PLAYER, gems[2:3])
        self.assertTrue(cc(st), "any 3 of 5 must satisfy a required count of 3")

    # -- pairwise conjunctions --

    def test_oxide_first_and_bosses_conjunction(self):
        mw = _build(oxide_goal="first", bosses_required_goal=2)
        cc = self._condition(mw)
        st = CollectionState(mw)
        flags = self._boss_flags(mw)
        _grant(st, mw, self.PLAYER, ["Key"] * 4 + [self._oxide_first_flag(mw)])
        self.assertFalse(cc(st), "oxide alone must not satisfy the AND")
        _grant(st, mw, self.PLAYER, flags[:2])
        self.assertTrue(cc(st))

    def test_oxide_first_and_gems_conjunction(self):
        mw = _build(oxide_goal="first", gems_required_goal=2)
        cc = self._condition(mw)
        st = CollectionState(mw)
        _grant(st, mw, self.PLAYER, ["Key"] * 4 + [self._oxide_first_flag(mw)])
        self.assertFalse(cc(st), "oxide alone must not satisfy the AND")
        _grant(st, mw, self.PLAYER, ["Red Gem", "Green Gem"])
        self.assertTrue(cc(st))

    def test_bosses_and_gems_conjunction(self):
        mw = _build(oxide_goal="none", bosses_required_goal=2, gems_required_goal=2)
        cc = self._condition(mw)
        st = CollectionState(mw)
        flags = self._boss_flags(mw)
        _grant(st, mw, self.PLAYER, flags[:2])
        self.assertFalse(cc(st), "bosses alone must not satisfy the AND")
        _grant(st, mw, self.PLAYER, ["Red Gem", "Green Gem"])
        self.assertTrue(cc(st))

    # -- three-way conjunction --

    def test_oxide_bosses_gems_three_way_conjunction(self):
        mw = _build(oxide_goal="first", bosses_required_goal=1,
                    gems_required_goal=1)
        cc = self._condition(mw)
        st = CollectionState(mw)
        flags = self._boss_flags(mw)
        _grant(st, mw, self.PLAYER, ["Key"] * 4 + [self._oxide_first_flag(mw)])
        _grant(st, mw, self.PLAYER, flags[:1])
        self.assertFalse(cc(st), "2 of 3 conditions must not satisfy the AND")
        _grant(st, mw, self.PLAYER, ["Red Gem"])
        self.assertTrue(cc(st))

    # -- the 2026-08-21 value rename --

    def test_oxide_goal_integers_are_frozen_across_the_rename(self):
        """`first`/`final` became `any_percent`/`101_percent`, NAMES ONLY.

        slot_data's `goal_oxide` and the native parser (ap_verify.c line 598,
        ap_hooks.c AP_EvaluateGoal) read the integer and never the name, so the
        rename must not move one. This pins all three.
        """
        self.assertEqual(OxideGoal.option_none, 0)
        self.assertEqual(OxideGoal.option_any_percent, 1)
        self.assertEqual(OxideGoal.option_101_percent, 2)

    def test_old_value_spellings_still_load(self):
        """A YAML written before the rename keeps working, via the aliases."""
        for old, new, expected in (("first", "any_percent", 1),
                                   ("final", "101_percent", 2)):
            with self.subTest(old=old):
                old_world = _build(oxide_goal=old).worlds[1]
                new_world = _build(oxide_goal=new).worlds[1]
                self.assertEqual(old_world.options.oxide_goal.value, expected)
                self.assertEqual(new_world.options.oxide_goal.value, expected)
                # and the same integer reaches the wire either way
                self.assertEqual(
                    old_world.fill_slot_data()["ctr_options"]["goal_oxide"],
                    new_world.fill_slot_data()["ctr_options"]["goal_oxide"])

    # -- the four legacy-equivalent single-condition combinations --

    def test_default_matches_legacy_oxide_goal(self):
        mw = _build()  # shipped default: oxide_goal=any_percent, bosses=0, gems=0
        world = mw.worlds[1]
        self.assertEqual(world.options.oxide_goal.value, OxideGoal.option_any_percent)
        self.assertEqual(world.options.bosses_required_goal.value, 0)
        self.assertEqual(world.options.gems_required_goal.value, 0)
        self.assertEqual(world._legacy_goal_value(), 0)

    def test_oxidefinal_equivalent_wire_value(self):
        mw = _build(oxide_goal="final")
        self.assertEqual(mw.worlds[1]._legacy_goal_value(), 1)

    def test_allbosses_equivalent_wire_value(self):
        mw = _build(oxide_goal="none", bosses_required_goal=4)
        self.assertEqual(mw.worlds[1]._legacy_goal_value(), 3)

    def test_allgemcups_equivalent_wire_value(self):
        mw = _build(oxide_goal="none", gems_required_goal=5)
        self.assertEqual(mw.worlds[1]._legacy_goal_value(), 4)

    def test_composed_goal_has_no_legacy_equivalent(self):
        mw = _build(oxide_goal="first", bosses_required_goal=1)
        self.assertEqual(mw.worlds[1]._legacy_goal_value(), -1)


class TestComposedGoalGuards(unittest.TestCase):
    """generate_early's raise guards for the composed goal (dossier §2.3):
    C1 empty goal, C2 gems+shuffle+excluded-cups, C3/C4 oxide-final with no
    satisfying progression tier."""

    def test_all_off_raises(self):
        with self.assertRaises(OptionError) as ctx:
            _early(oxide_goal="none", bosses_required_goal=0, gems_required_goal=0)
        self.assertIn("gems_required_goal", str(ctx.exception))

    def test_only_oxide_active_does_not_raise(self):
        _early(oxide_goal="first")  # must not raise

    def test_only_bosses_active_does_not_raise(self):
        _early(oxide_goal="none", bosses_required_goal=1)  # must not raise

    def test_only_gems_active_does_not_raise(self):
        _early(oxide_goal="none", gems_required_goal=1)  # must not raise

    def test_gems_required_with_shuffle_and_excluded_cups_raises(self):
        with self.assertRaises(OptionError) as ctx:
            _early(oxide_goal="none", gems_required_goal=1,
                  shuffle_gems=True, include_gem_cups=False)
        self.assertIn("gems_required_goal", str(ctx.exception))
        self.assertIn("include_gem_cups", str(ctx.exception))

    def test_gems_required_with_shuffle_and_included_cups_does_not_raise(self):
        _early(oxide_goal="none", gems_required_goal=1,
              shuffle_gems=True, include_gem_cups=True)  # must not raise

    def test_gems_required_with_shuffle_off_and_excluded_cups_does_not_raise(self):
        # shuffle_gems OFF: gemgoal() pins the Gems directly onto the cups
        # regardless of include_gem_cups, so no conflict.
        _early(oxide_goal="none", gems_required_goal=1,
              shuffle_gems=False, include_gem_cups=False)  # must not raise

    def test_oxidefinal_with_no_progression_tier_raises(self):
        # Generalization of #23's guard: oxide_goal == final with the
        # configured tier's created count at 0 -- no tier can ever satisfy
        # the relic rule.
        with self.assertRaises(OptionError) as ctx:
            _early(oxide_goal="final",
                  warppad_unlock_requirements="vanilla",
                  oxide_final_challenge_unlock="gold_relics",
                  gold_relic_count=0)
        self.assertIn("oxidefinal", str(ctx.exception))

    def test_oxidefinal_composed_with_bosses_still_checks_progression_tier(self):
        # C3/C4: the guard must fire off `oxide_goal == final` even when
        # composed with another active condition, not just when oxide is the
        # only condition.
        with self.assertRaises(OptionError):
            _early(oxide_goal="final", bosses_required_goal=1,
                  warppad_unlock_requirements="vanilla",
                  oxide_final_challenge_unlock="gold_relics",
                  gold_relic_count=0)

    def test_oxidefinal_with_progression_tier_present_does_not_raise(self):
        _early(oxide_goal="final",
              warppad_unlock_requirements="vanilla",
              oxide_final_challenge_unlock="gold_relics",
              gold_relic_count=18)  # must not raise


class TestUTRestoreComposedGoal(unittest.TestCase):
    """_ut_restore_options (issue #29) must reconstruct the SAME goal a
    connected seed actually has, from either wire shape: the #152
    goal_oxide/goal_bosses/goal_gems keys (new seeds), or the legacy `goal`
    int alone (pre-#152 seeds UT re-generates against)."""

    def _restored(self, wire_ctr_options):
        mw = _build()  # any generated world to call the instance method on
        world = mw.worlds[1]
        world._ut_restore_options({"ctr_options": wire_ctr_options,
                                   "warp_pad_unlock": {}, "podium_checks": {}})
        return (world.options.oxide_goal.value,
               world.options.bosses_required_goal.value,
               world.options.gems_required_goal.value)

    def test_restores_composed_keys_directly(self):
        self.assertEqual(
            self._restored({"goal_oxide": 2, "goal_bosses": 1, "goal_gems": 3}),
            (2, 1, 3))

    def test_restores_composed_keys_even_when_legacy_goal_also_present(self):
        # A #152 seed still emits a best-effort legacy `goal` (-1 for a
        # genuinely composed seed) alongside the real fields -- the composed
        # keys must win, not the legacy int.
        self.assertEqual(
            self._restored({"goal": -1, "goal_oxide": 1, "goal_bosses": 2,
                            "goal_gems": 0}),
            (1, 2, 0))

    def test_legacy_goal_0_restores_to_oxide_first(self):
        self.assertEqual(self._restored({"goal": 0}), (1, 0, 0))

    def test_legacy_goal_1_restores_to_oxide_final(self):
        self.assertEqual(self._restored({"goal": 1}), (2, 0, 0))

    def test_legacy_goal_3_restores_to_bosses_required_four(self):
        self.assertEqual(self._restored({"goal": 3}), (0, 4, 0))

    def test_legacy_goal_4_restores_to_gems_required_five(self):
        self.assertEqual(self._restored({"goal": 4}), (0, 0, 5))

    def test_absent_goal_keys_leave_defaults_untouched(self):
        mw = _build(oxide_goal="final", bosses_required_goal=2)
        world = mw.worlds[1]
        before = (world.options.oxide_goal.value,
                 world.options.bosses_required_goal.value,
                 world.options.gems_required_goal.value)
        world._ut_restore_options(
            {"ctr_options": {}, "warp_pad_unlock": {}, "podium_checks": {}})
        after = (world.options.oxide_goal.value,
                world.options.bosses_required_goal.value,
                world.options.gems_required_goal.value)
        self.assertEqual(before, after)


class TestComposedGoalWire(CTRTestBase):
    """fill_slot_data emits the three composed fields plus the best-effort
    legacy `goal` int, and schema_version is unconditionally 7 (Q28 ruling,
    unaffected by whether the goal is composed -- #166 already made 7
    unconditional for every 0.2.0 seed)."""

    run_default_tests = False
    options = {"oxide_goal": "first", "bosses_required_goal": 2,
              "gems_required_goal": 0}

    def test_wire_carries_composed_fields(self):
        sd = self.world.fill_slot_data()
        co = sd["ctr_options"]
        self.assertEqual(co["goal_oxide"], OxideGoal.option_any_percent)
        self.assertEqual(co["goal_bosses"], 2)
        self.assertEqual(co["goal_gems"], 0)
        self.assertEqual(co["goal"], -1)  # no legacy analogue
        self.assertEqual(co["schema_version"], 7)
        self.assertEqual(sd["schema_version"], 7)


if __name__ == "__main__":
    unittest.main()
