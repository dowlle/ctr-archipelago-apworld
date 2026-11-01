"""The Wumpa Shop and the Wumpa goal on content plans (job J11)."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_plan, content_wumpa, sphere0_guard, wumpa_shop
from .test_content_bosses import boss_options
from .test_content_ctr_first import assert_complete, full_generation
from .test_content_plan import make_world, profile_options
from .test_track_checks import refused


def shop_options(slots=3, progression="excluded", goal=750, **overrides):
    options = profile_options()
    options.update(wumpa_shop_slots=slots, wumpa_shop_progression=progression, goal_wumpa=goal,
                   wumpa_shop_prices=150)
    options.update(overrides)
    return options


def shop_checks(plan):
    return [c for c in plan["checks"] if c["kind"] == content_wumpa.KIND]


class TestContentWumpaShop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = make_world(shop_options(), seed=20261029)
        cls.plan = cls.world.ctr_content_plan

    def test_record_features_and_goal(self):
        plan = self.plan
        self.assertEqual(plan["wumpa_shop"], dict(slots=3, prices=150, progression="excluded", hints=True))
        self.assertEqual(plan["required_features"][-3:], ["wumpa_shop_v1", "wumpa_goal_v1", "pad_client_v1"])
        self.assertEqual(plan["goal"]["op"], "all")
        self.assertEqual(plan["goal"]["terms"][-1], dict(op="wumpa_banked", count=750))
        self.assertEqual(plan["goal"]["terms"][0]["op"], "distinct")

    def test_shop_checks_are_last_in_hub_order(self):
        plan = self.plan
        shop = shop_checks(plan)
        self.assertEqual(len(shop), 15)
        self.assertEqual(plan["checks"][-15:], shop)
        self.assertEqual([c["location"] for c in shop],
                         [wumpa_shop.shop_code(h, n) for h in wumpa_shop.SHOP_HUBS for n in (1, 2, 3)])
        self.assertEqual(shop[0]["owner"], "hub:26")
        self.assertEqual(shop[3]["owner"], "hub:25")
        self.assertEqual(shop[0]["display_name"], "N. Sanity Beach Shop: Slot 1")
        for c in shop:
            self.assertEqual(c["routes"], [])
            hub = c["display_name"].split(" Shop: ")[0]
            low, high = wumpa_shop.price_band(hub, 150)
            self.assertTrue(low <= c["price"] <= high)
        self.assertEqual([c["unlock_banked"] for c in shop[:3]], [0, 0, 75])
        self.assertFalse(any(c["owner"].startswith("hub:") for c in plan["checks"][:-15]))

    def test_no_top_level_block_and_no_envelope_key(self):
        wire = self.world.fill_slot_data()
        self.assertNotIn("wumpa_shop", wire)
        for key in ("wumpa_shop_slots", "goal_wumpa", "wumpa_shop_hints"):
            self.assertNotIn(key, wire["ctr_options"])

    def test_excluded_is_an_item_rule(self):
        mw = self.world.multiworld
        location = mw.get_location("Citadel City Shop: Slot 2", 1)
        self.assertFalse(location.item_rule(self.world.create_item("Key")))
        self.assertTrue(location.item_rule(self.world.create_item("Wumpa Fruit")))
        self.assertEqual(location.progress_type.name, "DEFAULT")

    def test_logic_needs_income_and_the_hub_key_floor(self):
        world = make_world(shop_options(), seed=20261029, stop_before="pre_fill")
        mw = world.multiworld
        state = CollectionState(mw)
        beach = mw.get_location("N. Sanity Beach Shop: Slot 1", 1)
        citadel = mw.get_location("Citadel City Shop: Slot 1", 1)
        income = mw.get_location(content_wumpa.INCOME, 1)
        self.assertFalse(beach.can_reach(state))  # the event is not collected yet
        state.sweep_for_advancements()
        self.assertEqual(beach.can_reach(state), income.can_reach(state))
        state.collect(world.create_item("Key"), True)
        state.collect(world.create_item("Key"), True)
        self.assertFalse(citadel.can_reach(state))
        for _ in range(2):
            state.collect(world.create_item("Key"), True)
        state.sweep_for_advancements()
        self.assertTrue(income.can_reach(state))
        self.assertTrue(citadel.can_reach(state))

    def test_income_routes_are_retail_race_tracks_only(self):
        routes = content_wumpa.income_routes(self.plan)
        self.assertTrue(routes)
        self.assertTrue(all(t["origin"] == "retail" and t["retail_id"] <= 15 for _e, _p, _m, t in routes))

    def test_shop_slots_never_count_as_starting_checks(self):
        off = make_world(shop_options(slots=0), seed=20261029, stop_before="pre_fill")
        on = make_world(shop_options(slots=25, progression="allowed"), seed=20261029, stop_before="pre_fill")
        self.assertEqual(sphere0_guard.sphere0_breadth(on), sphere0_guard.sphere0_breadth(off))
        self.assertTrue(all(getattr(loc, "type", None) == wumpa_shop.LOCATION_TYPE
                            for loc in on.multiworld.get_locations(1) if "Shop: Slot" in loc.name))

    def test_tracker_restores_the_five_options(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        tracker = make_world(dict(wumpa_shop_slots=25, goal_wumpa=0, wumpa_shop_prices=400), seed=999,
                             passthrough=wire)
        o = tracker.options
        self.assertEqual((o.wumpa_shop_slots.value, o.wumpa_shop_prices.value, o.wumpa_shop_progression.value,
                          o.wumpa_shop_hints.value, o.goal_wumpa.value), (3, 150, 1, 1, 750))
        self.assertEqual(tracker.fill_slot_data(), wire)

    def test_forged_plans_refuse(self):
        def mutate(change):
            plan = copy.deepcopy(self.plan)
            change(plan)
            return refused(plan)

        def last(p):
            return p["checks"][-1]

        cases = dict(
            price_high=lambda p: last(p).update(price=1000),
            price_low=lambda p: last(p).update(price=1),
            # Inside Citadel City's band at 150 percent (60 to 120), but no
            # whole band price scales to 61 (40 gives 60, 41 gives 62).
            price_unreachable=lambda p: last(p).update(price=61),
            unlock=lambda p: last(p).update(unlock_banked=last(p)["unlock_banked"] + 1),
            route=lambda p: last(p)["routes"].append(copy.deepcopy(p["checks"][0]["routes"][0])),
            owner=lambda p: last(p).update(owner="hub:26"),
            drop_slot=lambda p: p["checks"].pop(),
            order=lambda p: p["checks"].insert(0, p["checks"].pop()),
            slots=lambda p: p["wumpa_shop"].update(slots=2),
            prices=lambda p: p["wumpa_shop"].update(prices=100),
            progression=lambda p: p["wumpa_shop"].update(progression="sometimes"),
            hints=lambda p: p["wumpa_shop"].update(hints=1),
            no_record=lambda p: p.pop("wumpa_shop"),
            no_feature=lambda p: p["required_features"].remove("wumpa_shop_v1"),
            no_goal_feature=lambda p: p["required_features"].remove("wumpa_goal_v1"),
            goal_zero=lambda p: p["goal"]["terms"][-1].update(count=0),
            goal_high=lambda p: p["goal"]["terms"][-1].update(count=5001),
            goal_first=lambda p: p["goal"]["terms"].reverse(),
            goal_dropped=lambda p: p.update(goal=p["goal"]["terms"][0]),
            arm_in_requirement=lambda p: p["requirements"].__setitem__(
                1, dict(id="keys:1", predicate=dict(op="wumpa_banked", count=5))),
        )
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(mutate(change))


class TestContentWumpaRules(unittest.TestCase):
    def test_off_keeps_the_plan(self):
        """wumpa_shop_slots 0 and goal_wumpa 0: no record, no check, no arm."""
        plan = make_world(shop_options(slots=0, goal=0), seed=7).ctr_content_plan
        self.assertNotIn("wumpa_shop", plan)
        self.assertFalse(shop_checks(plan))
        self.assertEqual(plan["goal"]["op"], "distinct")
        self.assertFalse(set(plan["required_features"]) & {"wumpa_shop_v1", "wumpa_goal_v1"})

    def test_wumpa_only_goal(self):
        plan = make_world(shop_options(slots=0, goal=1000, gems_required_goal=0), seed=7).ctr_content_plan
        self.assertEqual(plan["goal"], dict(op="wumpa_banked", count=1000))
        self.assertEqual(plan["required_features"][-2:], ["wumpa_goal_v1", "pad_client_v1"])
        self.assertTrue(content_plan.validate(plan))

    def test_no_goal_still_refuses(self):
        with self.assertRaises(OptionError):
            make_world(shop_options(slots=0, goal=0, gems_required_goal=0), seed=7)

    def test_excluded_supply_refusal(self):
        options = shop_options(slots=25, progression="excluded", goal=0)
        options["content_pool"]["tracks"]["retail"] = [3]
        options["content_pool"]["required_entries"] = ["retail:3"]
        options["content_pool"]["tracks"]["custom"] = []
        with self.assertRaises(OptionError) as caught:
            make_world(options, seed=7)
        self.assertIn("wumpa_shop_progression: excluded", str(caught.exception))
        # The same plan with `allowed` generates.
        options["wumpa_shop_progression"] = "allowed"
        self.assertTrue(make_world(options, seed=7, stop_before="generate_basic").ctr_content_plan["wumpa_shop"])

    def test_oxide_reserve_counts_against_the_shop(self):
        """The excluded Oxide goal check keeps one filler copy, so the shop
        cannot also count it (J11 review round 1)."""
        record = dict(slots=1, prices=100, progression="excluded", hints=True)
        items = dict(filler_count=5, rows=[])
        content_wumpa.check_supply(record, items)
        with self.assertRaises(OptionError):
            content_wumpa.check_supply(record, items, reserved=1)
        content_wumpa.check_supply(record, dict(filler_count=6, rows=[]), reserved=1)

    def test_forged_supply_refuses(self):
        plan = copy.deepcopy(make_world(shop_options(slots=25), seed=7).ctr_content_plan)
        self.assertTrue(content_plan.validate(plan))
        items = plan["items"]
        # Move filler copies into extra Trophies until one non-progression
        # copy is missing; the item accounting still adds up.
        short = content_wumpa.non_progression_supply(items) - 125 + 1
        self.assertGreater(short, 0)
        row = next(r for r in items["rows"] if r["item"] == content_plan.content_item_pool.ITEMS["Trophy"])
        row.update(extra=row["extra"] + short, remaining=row["remaining"] + short,
                   receipt_cap=row["receipt_cap"] + short)
        items["filler_count"] -= short
        items["trap_count"] = min(items["trap_count"], items["filler_count"])
        with self.assertRaises(OptionError) as caught:
            content_plan.validate(plan)
        self.assertIn("excluded", str(caught.exception))

    def test_no_retail_race_refuses(self):
        options = shop_options(slots=5, progression="allowed", goal=0)
        options["content_pool"]["tracks"]["retail"] = [16, 17]
        with self.assertRaises(OptionError) as caught:
            make_world(options, seed=7)
        self.assertIn("bank fruit", str(caught.exception))

    def test_oxide_races_wait_for_the_wumpa_goal(self):
        world = make_world(boss_options(goal_wumpa=300, wumpa_shop_slots=0), seed=3)
        mw = world.multiworld
        entrance = mw.get_entrance("encounter/garage:4/0", 1)
        state = CollectionState(mw)
        for _ in range(4):
            state.collect(world.create_item("Key"), True)
        state.sweep_for_advancements()
        self.assertTrue(state.has(content_wumpa.INCOME, 1))
        self.assertTrue(entrance.can_reach(state))
        bare = CollectionState(mw)
        for _ in range(4):
            bare.collect(world.create_item("Key"), True)
        self.assertFalse(entrance.access_rule(bare))

    def test_progression_slot_price_is_the_band_bottom(self):
        options = shop_options(slots=10, progression="allowed", goal=0, accessibility="full")
        for seed in range(1, 8):
            world, wire = full_generation(options, seed)
            assert_complete(self, world)
            plan = wire["content_plan"]
            self.assertTrue(content_plan.validate(plan))
            mw = world.multiworld
            progression = [c for c in shop_checks(plan)
                           if mw.get_location(c["display_name"], 1).item.advancement]
            for c in progression:
                hub = c["display_name"].split(" Shop: ")[0]
                self.assertEqual(c["price"], wumpa_shop.price_band(hub, 150)[0])
            if progression:
                return
        self.fail("no seed placed progression in a shop slot")

    def test_full_generation_excluded(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                world, wire = full_generation(shop_options(slots=6, accessibility="full"), seed)
                assert_complete(self, world)
                mw = world.multiworld
                self.assertFalse(any(mw.get_location(c["display_name"], 1).item.advancement
                                     for c in shop_checks(wire["content_plan"])))


if __name__ == "__main__":
    unittest.main()
