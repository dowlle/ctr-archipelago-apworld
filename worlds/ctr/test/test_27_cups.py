"""27-cup seeds (0.3.0-alpha3 job A3-7, ruled 2026-11-05: "27 cups definitely
is a design choice I want available").

With every normal pad a cup, a plan has no Trophy Race or CTR Challenge.
Itemsanity and Wumpa Income then route from the cup legs instead
(content_global_checks.checks, content_wumpa.cup_income_routes); Hit
Character already routed from every leg. A plan with a Trophy Race or CTR
Challenge keeps its routes exactly."""
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_cups, content_plan, content_wumpa
from .test_content_plan import make_world


def cups_options(**extra):
    options = dict(cup_count=27, crystal_challenge_count=0, accessibility="full")
    options.update(extra)
    return options


def leg_count(plan):
    return sum(len(e["legs"]) for e in plan["entries"] if e["kind"] == content_cups.KIND)


class TestTwentySevenCups(unittest.TestCase):
    def test_every_pad_is_a_cup(self):
        world = make_world(cups_options(), seed=1)
        plan = world.ctr_content_plan
        self.assertTrue(content_plan.validate(plan))
        kinds = [e["kind"] for e in plan["entries"] if e["kind"] in ("track", content_cups.KIND)]
        self.assertEqual(kinds.count(content_cups.KIND), 27)
        self.assertNotIn("track", kinds)

    def test_itemsanity_hit_and_shop_generate_and_restore(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                world = make_world(cups_options(itemsanity=True, hit_character=True), seed=seed)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                legs = leg_count(plan)
                items = [c for c in plan["checks"] if c["kind"] == "itemsanity"]
                hits = [c for c in plan["checks"] if c["kind"] == "hit"]
                self.assertEqual(len(items), 22)
                self.assertEqual(len(hits), 16)
                for check in items:
                    self.assertEqual({r["mode"] for r in check["routes"]}, {content_cups.MODE})
                    self.assertEqual(len(check["routes"]), legs)
                    self.assertTrue(all(r["leg_id"] for r in check["routes"]))
                # Itemsanity routes are the Hit routes with the use award.
                strip = lambda routes: [(r["entry_id"], r["leg_id"]) for r in routes if r["mode"] == "cup"]
                self.assertEqual(strip(items[0]["routes"]), strip(hits[0]["routes"]))
                self.assertTrue(content_wumpa.banking(plan))
                self.assertFalse(content_wumpa.income_routes(plan))
                self.assertEqual(len(content_wumpa.cup_income_routes(plan)), legs)
                self.assertEqual(len([loc for loc in world.multiworld.get_locations(1) if loc.address is not None]),
                                 len(plan["checks"]))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                restored = make_world({}, passthrough=wire)
                self.assertEqual(restored.ctr_content_plan, plan)

    def test_wumpa_options_generate(self):
        for extra in (dict(wumpa_check="global", itemsanity=True), dict(wumpa_check="per_track", hit_character=True),
                      dict(goal_wumpa=500, itemsanity=True, hit_character=True),
                      dict(itemsanity=True, hit_character=True, progressive_boost="shared_global",
                           logic_difficulty="hard"),
                      dict(itemsanity=True, hit_character=True, racer_locked_pads=6, character_unlocks=True),
                      dict(itemsanity=True, hit_character=True, boss_cups=4),
                      dict(itemsanity=True, hit_character=True, pad_approach_hints=True),
                      dict(itemsanity=True, cup_sweep_checks=True, lap_completion_checks=True, box_locations=True)):
            with self.subTest(**extra):
                world = make_world(cups_options(**extra), seed=2)
                self.assertTrue(content_plan.validate(world.ctr_content_plan))
                world.fill_slot_data()

    def test_itemsanity_needs_its_weapon_and_a_cup(self):
        world = make_world(cups_options(itemsanity=True), seed=3)
        mw = world.multiworld
        location = mw.get_location("Itemsanity: Beaker", 1)
        advancement = [i for i in mw.itempool if i.advancement]
        state = CollectionState(mw)
        for item in advancement:
            if item.name != "Beaker":
                state.collect(item, prevent_sweep=True)
        self.assertFalse(location.can_reach(state))
        state.collect(world.create_item("Beaker"), prevent_sweep=True)
        self.assertTrue(location.can_reach(state))

    def test_income_needs_an_open_cup(self):
        world = make_world(cups_options(), seed=4)
        mw = world.multiworld
        income = mw.get_location(content_wumpa.INCOME, 1)
        empty = CollectionState(mw)
        cups = [e["id"] for e in world.ctr_content_plan["entries"] if e["kind"] == content_cups.KIND]
        self.assertEqual(income.can_reach(empty), any(mw.get_region(c, 1).can_reach(empty) for c in cups))
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.advancement:
                state.collect(item, prevent_sweep=True)
        self.assertTrue(income.can_reach(state))

    def test_a_plan_with_a_race_keeps_its_routes(self):
        world = make_world(cups_options(cup_count=26, itemsanity=True), seed=1)
        plan = world.ctr_content_plan
        items = [c for c in plan["checks"] if c["kind"] == "itemsanity"]
        self.assertTrue(items)
        for check in items:
            self.assertTrue(all(r["mode"] in ("trophy", "ctr") and r["leg_id"] is None for r in check["routes"]))
        self.assertTrue(content_wumpa.income_routes(plan))
        self.assertEqual(content_wumpa.cup_income_routes(plan), [])

    def test_crystals_still_take_pads(self):
        with self.assertRaisesRegex(OptionError, "27 cups do not fit"):
            make_world(dict(cup_count=27), seed=1)


if __name__ == "__main__":
    unittest.main()
