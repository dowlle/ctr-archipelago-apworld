"""A4-79: `oxide_final_challenge_relic_count: 0` asks no relic for N. Oxide's
Final Challenge.

With 0 the Final Challenge's requirement carries no relic term: the goal's
companion terms alone when Oxide is the goal, and `always` when nothing else
gates it. Every `oxide_final_challenge_unlock` mode and every `oxide_goal`
behaves the same. The relic pool and the relic locations do not change, the
Universal Tracker restore keeps the 0, and a mode whose tiers hold no relic is
no longer refused (nothing is asked of them).
"""
import copy
import json
import random
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_bosses, content_plan
from ..Options import FinalOxideRelicCount
from .test_content_bosses import BOSS_NAMES, boss_options
from .test_content_plan import make_world

UNLOCKS = ["sapphire_relics", "gold_relics", "platinum_relics", "any_relic_type", "total_relics"]
GOALS = ["none", "any_percent", "101_percent"]
FINAL = BOSS_NAMES[5]
FIRST = BOSS_NAMES[4]


def requirements(world):
    return {r["id"]: r["predicate"] for r in world.ctr_content_plan["requirements"]}


def reach(world, items):
    mw = world.multiworld
    state = CollectionState(mw)
    for name, count in items.items():
        state.add_item(name, 1, count)
    state.stale[1] = True
    return mw.get_location(FIRST, 1).can_reach(state), mw.get_location(FINAL, 1).can_reach(state)


class TestZeroRelicsOption(unittest.TestCase):
    def test_range_allows_zero_and_keeps_the_default(self):
        self.assertEqual(FinalOxideRelicCount.range_start, 0)
        self.assertEqual(FinalOxideRelicCount.default, 18)
        self.assertEqual(FinalOxideRelicCount.special_range_names, {"all": 18})
        self.assertEqual(FinalOxideRelicCount.from_any(0).value, 0)
        with self.assertRaises(Exception):
            FinalOxideRelicCount.from_any(-1)

    def test_record_accepts_zero_and_refuses_negative(self):
        record = make_world(boss_options(oxide_final_challenge_relic_count=0)).ctr_content_plan["bosses"]
        self.assertEqual(content_bosses.check_settings(copy.deepcopy(record))["oxide_final_count"], 0)
        for unlock, count in ((0, -1), (4, -1), (0, 19), (4, 55)):
            with self.subTest(unlock=unlock, count=count):
                bad = copy.deepcopy(record)
                bad.update(oxide_final_unlock=unlock, oxide_final_count=count)
                with self.assertRaises(OptionError):
                    content_bosses.check_settings(bad)


class TestZeroRelicsRequirement(unittest.TestCase):
    def test_every_goal_and_unlock_mode_drops_the_relic_term(self):
        for goal in GOALS:
            for unlock in UNLOCKS:
                with self.subTest(goal=goal, unlock=unlock):
                    world = make_world(boss_options(oxide_goal=goal, oxide_final_challenge_unlock=unlock,
                                                    oxide_final_challenge_relic_count=0,
                                                    bosses_required_goal=0 if goal != "none" else 1))
                    plan = world.ctr_content_plan
                    self.assertTrue(content_plan.validate(plan))
                    self.assertEqual(plan["bosses"]["oxide_final_count"], 0)
                    self.assertEqual(plan["bosses"]["oxide_final_unlock"], UNLOCKS.index(unlock)
                                     if unlock != "total_relics" else 4)
                    self.assertEqual(requirements(world)["oxide:final"], dict(op="always"))

    def test_companions_alone_gate_the_final_with_zero(self):
        world = make_world(boss_options(oxide_goal="101_percent", oxide_final_challenge_relic_count=0,
                                        bosses_required_goal=2, gems_required_goal=3))
        plan = world.ctr_content_plan
        gem = content_bosses.gem_term_of(plan["goal"])
        bosses = dict(op="checked", locations=list(content_bosses.BOSS_CODES), count=2)
        self.assertEqual(requirements(world)["oxide:final"], dict(op="all", terms=[bosses, gem]))
        # Not one relic item appears in the predicate.
        self.assertNotIn("sum", json.dumps(requirements(world)["oxide:final"]))
        # any_percent: the companions gate both challenges, the final adds nothing.
        world = make_world(boss_options(oxide_goal="any_percent", oxide_final_challenge_relic_count=0,
                                        bosses_required_goal=2, gems_required_goal=3))
        req = requirements(world)
        self.assertEqual(req["oxide:final"], req["oxide:first"])

    def test_nonzero_counts_are_unchanged(self):
        world = make_world(boss_options(oxide_final_challenge_relic_count=1))
        self.assertEqual(requirements(world)["oxide:final"],
                         dict(op="count", item=content_bosses.RELIC_ITEMS[0], count=1))

    def test_oxide_disabled_ignores_zero(self):
        world = make_world(boss_options(oxide_goal="disabled", bosses_required_goal=4,
                                        oxide_final_challenge_relic_count=0))
        self.assertEqual(world.ctr_content_plan["bosses"]["oxide_final_count"], 18)
        self.assertEqual(world.ctr_content_plan["bosses"]["oxide_final_unlock"], 0)

    def test_a_mode_with_no_relic_is_allowed_at_zero_and_refused_above(self):
        options = boss_options(oxide_final_challenge_unlock="platinum_relics",
                               oxide_final_challenge_relic_count=0)
        options["item_pool"]["base"]["relics"] = dict(sapphire=6, gold=4, platinum=0)
        world = make_world(options)
        self.assertEqual(requirements(world)["oxide:final"], dict(op="always"))
        options["oxide_final_challenge_relic_count"] = 1
        with self.assertRaisesRegex(OptionError, "no base relic"):
            make_world(options)


class TestZeroRelicsLogicAndPool(unittest.TestCase):
    def test_final_opens_on_four_keys_and_no_relic(self):
        for goal in GOALS:
            for unlock in UNLOCKS:
                with self.subTest(goal=goal, unlock=unlock):
                    world = make_world(boss_options(oxide_goal=goal, oxide_final_challenge_unlock=unlock,
                                                    oxide_final_challenge_relic_count=0,
                                                    bosses_required_goal=0 if goal != "none" else 1))
                    first, final = reach(world, {"Key": 4})
                    self.assertTrue(final)
                    # The same room with the default count still waits on relics.
                    held = make_world(boss_options(oxide_goal=goal, oxide_final_challenge_unlock=unlock,
                                                   bosses_required_goal=0 if goal != "none" else 1))
                    self.assertFalse(reach(held, {"Key": 4})[1])

    def test_relic_items_and_locations_do_not_change(self):
        for unlock in ("sapphire_relics", "total_relics"):
            with self.subTest(unlock=unlock):
                zero = make_world(boss_options(oxide_final_challenge_unlock=unlock,
                                               oxide_final_challenge_relic_count=0), seed=7)
                six = make_world(boss_options(oxide_final_challenge_unlock=unlock,
                                              oxide_final_challenge_relic_count=1), seed=7)
                self.assertEqual(zero.ctr_content_plan["items"], six.ctr_content_plan["items"])
                kinds = lambda w: sorted(c["kind"] for c in w.ctr_content_plan["checks"])
                self.assertEqual(kinds(zero), kinds(six))
                self.assertEqual([loc.name for loc in zero.multiworld.get_locations(1)],
                                 [loc.name for loc in six.multiworld.get_locations(1)])
                relics = lambda w: sum(1 for i in w.multiworld.itempool if i.name.endswith("Relic"))
                self.assertEqual(relics(zero), relics(six))
                self.assertGreater(relics(zero), 0)

    def test_universal_tracker_restore_keeps_zero(self):
        for goal in GOALS:
            with self.subTest(goal=goal):
                world = make_world(boss_options(oxide_goal=goal, oxide_final_challenge_relic_count=0,
                                                bosses_required_goal=0 if goal != "none" else 1))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                restored = make_world({}, passthrough=copy.deepcopy(wire))
                self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
                self.assertEqual(restored.options.oxide_final_challenge_relic_count.value, 0)
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
                self.assertTrue(reach(restored, {"Key": 4})[1])


class TestZeroRelicsFuzz(unittest.TestCase):
    """Random boss profiles at count 0 generate, validate and restore."""

    def test_random_profiles(self):
        rng = random.Random(4079)
        for n in range(12):
            goal = rng.choice(GOALS + ["disabled"])
            bosses = rng.randrange(5)
            gems = rng.choice([0, 1, 3, 5])
            if goal in ("none", "disabled") and bosses == 0 and gems == 0:
                gems = 2
            options = boss_options(oxide_goal=goal, bosses_required_goal=bosses, gems_required_goal=gems,
                                   oxide_final_challenge_unlock=rng.choice(UNLOCKS),
                                   oxide_final_challenge_relic_count=0,
                                   oxide_1_optional=rng.choice(["mandatory", "optional"]),
                                   oxide_final_track=rng.choice(["cortex_vortex", "oxide_station"]),
                                   boss_track_shuffle=rng.random() < 0.5)
            with self.subTest(n=n, goal=goal):
                world = make_world(options, seed=n)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                restored = make_world({}, passthrough=copy.deepcopy(wire))
                self.assertEqual(restored.ctr_content_plan, plan)
                if goal != "disabled":
                    self.assertEqual(plan["bosses"]["oxide_final_count"], 0)


if __name__ == "__main__":
    unittest.main()
