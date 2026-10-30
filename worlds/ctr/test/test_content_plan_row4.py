"""One generator row 4: items fixed to their own check behind content_pool."""
import copy
import json
import unittest

from BaseClasses import ItemClassification
from Options import OptionError
from worlds.AutoWorld import call_all

from .. import content_bosses, content_fixed, content_item_pool, content_plan, content_requirements as cr
from .test_content_plan import make_world
from .test_content_plan_row3 import SHAPE, filled, occupied, options, records

KEY = content_item_pool.ITEMS["Key"]
BOSS_NAMES = [content_plan.LOCATION_BY_CODE[code] for code in content_bosses.BOSS_CODES]
GEM_CHECKS = [(f"{name.removesuffix(' Gem')} Gem Cup: Gem", name) for name in content_fixed.GEM_NAMES]
FINAL = dict(oxide_goal="101_percent", oxide_1_optional="filler")
OXIDE_FIRST = content_plan.LOCATION_BY_CODE[content_bosses.OXIDE_FIRST]
OXIDE_FINAL = content_plan.LOCATION_BY_CODE[content_bosses.OXIDE_FINAL]
VANILLA = dict(warppad_unlock_requirements="vanilla")


def row(world, name):
    return next(r for r in world.ctr_content_items.rows if r.name == name)


def holding(world, name):
    return world.multiworld.get_location(name, world.player).item


def pool(world, name):
    return sum(item.name == name and item.player == world.player for item in world.multiworld.itempool)


def base_copies(world, name):
    r = row(world, name)
    return r.base + r.extra - r.start_from_pool


def cups(count):
    return {**copy.deepcopy(SHAPE), "cups": dict(count=count)}


class TestPins(unittest.TestCase):
    def test_shuffled_plans_have_no_record(self):
        plan = make_world(options()).ctr_content_plan
        self.assertNotIn("fixed_items", plan)
        self.assertNotIn(content_fixed.FEATURE, plan["required_features"])
        self.assertEqual(plan["items"]["locked_checks"], 0)

    def test_keys_stay_on_their_boss(self):
        world = make_world(options(shuffle_keys=False), stop_before="pre_fill")
        self.assertEqual(world.ctr_content_plan["fixed_items"], dict(keys=True))
        self.assertIn(content_fixed.FEATURE, world.ctr_content_plan["required_features"])
        for name in BOSS_NAMES:
            location = world.multiworld.get_location(name, 1)
            self.assertEqual(location.item.name, "Key")
            self.assertTrue(location.locked)
        self.assertEqual(pool(world, "Key"), 0)
        key = row(world, "Key")
        self.assertEqual((key.locked_selected, key.remaining), (4, 0))
        self.assertEqual(world.ctr_content_items.locked_checks, 4)

    def test_gems_stay_on_their_cup(self):
        world = make_world(options(shuffle_gems=False), stop_before="pre_fill")
        self.assertEqual(world.ctr_content_plan["fixed_items"], dict(gems=True))
        for location, gem in GEM_CHECKS:
            self.assertEqual(holding(world, location).name, gem)
            self.assertEqual(pool(world, gem), 0)
        self.assertEqual(world.ctr_content_items.locked_checks, 5)

    def test_gems_shuffle_silently_with_a_cup_missing(self):
        for goal in (0, 3):
            with self.assertNoLogs("worlds.ctr", level="WARNING"):
                world = make_world(options(shuffle_gems=False, gems_required_goal=goal, content_pool=cups(4)),
                                   stop_before="pre_fill")
            self.assertNotIn("fixed_items", world.ctr_content_plan)
            self.assertEqual(sum(pool(world, gem) for gem in content_fixed.GEM_NAMES), 5)

    def test_keys_shuffle_without_garages(self):
        pool_ = {**copy.deepcopy(SHAPE), "bosses": dict(enabled=False)}
        world = make_world(options(shuffle_keys=False, content_pool=pool_, oxide_goal="disabled", gems_required_goal=1),
                           stop_before="pre_fill")
        self.assertNotIn("fixed_items", world.ctr_content_plan)
        self.assertEqual(pool(world, "Key"), 4)

    def test_extras_stay_shuffled(self):
        item_pool = dict(extra=dict(keys=2, gems=dict(red=1)))
        world = make_world(options(shuffle_keys=False, shuffle_gems=False, item_pool=item_pool), stop_before="pre_fill")
        self.assertEqual((pool(world, "Key"), pool(world, "Red Gem")), (2, 1))
        self.assertEqual((row(world, "Key").locked_selected, row(world, "Red Gem").locked_selected), (4, 1))

    def test_missing_base_colour_is_not_pinned(self):
        item_pool = dict(base=dict(gems=["red", "green", "blue", "yellow"]), extra=dict(gems=dict(purple=1)))
        world = make_world(options(shuffle_gems=False, item_pool=item_pool), stop_before="pre_fill")
        self.assertIsNone(holding(world, "Purple Gem Cup: Gem"))
        self.assertEqual(pool(world, "Purple Gem"), 1)

    def test_every_check_has_one_item(self):
        for overrides in (dict(shuffle_keys=False), dict(shuffle_gems=False), FINAL,
                          dict(shuffle_keys=False, shuffle_gems=False, **FINAL)):
            world = make_world(options(**overrides), stop_before="pre_fill")
            placed = sum(l.address is not None and l.item is not None for l in world.multiworld.get_locations(1))
            self.assertEqual(placed, world.ctr_content_items.locked_checks)
            self.assertEqual(sum(i.player == 1 for i in world.multiworld.itempool) + placed,
                             world.ctr_content_items.coded_checks)


class TestStarts(unittest.TestCase):
    def test_started_key_is_not_pinned_again(self):
        world = make_world(options(shuffle_keys=False, start_inventory_from_pool={"Key": 1}), stop_before="pre_fill")
        key = row(world, "Key")
        self.assertEqual((key.start_from_pool, key.locked_selected, key.remaining), (1, 3, 0))
        self.assertEqual([holding(world, n).name if holding(world, n) else None for n in BOSS_NAMES],
                         ["Key", "Key", "Key", None])

    def test_started_key_takes_an_extra_first(self):
        world = make_world(options(shuffle_keys=False, start_inventory_from_pool={"Key": 1},
                                   item_pool=dict(extra=dict(keys=1))))
        key = row(world, "Key")
        self.assertEqual((key.base + key.extra, key.start_from_pool, key.locked_selected, key.remaining), (5, 1, 4, 0))

    def test_started_gem_leaves_its_cup_free(self):
        world = make_world(options(shuffle_gems=False, start_inventory_from_pool={"Red Gem": 1}), stop_before="pre_fill")
        self.assertIsNone(holding(world, "Red Gem Cup: Gem"))
        self.assertEqual(holding(world, "Green Gem Cup: Gem").name, "Green Gem")
        self.assertEqual(world.ctr_content_items.locked_checks, 4)
        self.assertEqual(pool(world, "Red Gem"), 0)

    def test_too_many_starts_are_refused(self):
        with self.assertRaisesRegex(OptionError, "cannot supply"):
            make_world(options(shuffle_keys=False, start_inventory_from_pool={"Key": 5}))

    def test_all_copies_counted_after_the_fill(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False, start_inventory_from_pool={"Key": 2, "Blue Gem": 1}))
        mw = filled(world)
        placed = [l.item.name for l in mw.get_locations(1) if l.item is not None and l.address is not None]
        self.assertEqual(placed.count("Key"), 2)
        self.assertEqual(placed.count("Blue Gem"), 0)
        self.assertEqual(placed.count("Red Gem"), 1)


class TestFiller(unittest.TestCase):
    def test_oxide_challenge_holds_wumpa(self):
        world = make_world(options(**FINAL))
        location = world.multiworld.get_location(OXIDE_FIRST, 1)
        self.assertEqual(location.item.name, "Wumpa Fruit")
        self.assertTrue(location.locked)
        plan = world.ctr_content_plan
        self.assertEqual(plan["fixed_items"], dict(oxide_1_filler=True))
        self.assertTrue(plan["bosses"]["oxide_1_optional"])
        self.assertEqual((plan["items"]["locked_checks"], sum(r["locked_selected"] for r in plan["items"]["rows"])), (1, 0))

    def test_pinned_wumpa_stays_out_of_the_trap_draw(self):
        plain = make_world(options(oxide_goal="101_percent", oxide_1_optional="optional", trap_fill_percentage=100))
        pinned = make_world(options(trap_fill_percentage=100, **FINAL))
        self.assertEqual(pinned.ctr_content_items.filler_count, plain.ctr_content_items.filler_count - 1)
        self.assertEqual(pinned.ctr_content_items.trap_count, pinned.ctr_content_items.filler_count)
        self.assertEqual(holding(pinned, OXIDE_FIRST).name, "Wumpa Fruit")

    def test_goal_check_keeps_its_filler(self):
        mw = filled(make_world(options(**FINAL)))
        item = mw.get_location(OXIDE_FINAL, 1).item
        self.assertFalse(item.advancement)

    def test_needs_a_filler_slot_for_the_goal(self):
        plain = make_world(options(**FINAL)).ctr_content_items
        extra = dict(extra=dict(trophies=plain.filler_count + len(content_item_pool.SURFACE_NAMES)))
        with self.assertRaisesRegex(OptionError, "holds only filler"):
            make_world(options(item_pool=extra, **FINAL))

    def test_ignored_on_other_goals(self):
        world = make_world(options(oxide_goal="any_percent", oxide_1_optional="filler"))
        self.assertNotIn("fixed_items", world.ctr_content_plan)
        self.assertFalse(world.ctr_content_plan["bosses"]["oxide_1_optional"])


class TestSizing(unittest.TestCase):
    def test_free_checks_follow_the_pins(self):
        plain = make_world(options()).ctr_content_items
        pinned = make_world(options(shuffle_keys=False, shuffle_gems=False)).ctr_content_items
        self.assertEqual(pinned.filler_count, plain.filler_count)
        self.assertEqual(pinned.locked_checks, 9)
        self.assertEqual(sum(r.remaining for r in pinned.rows), sum(r.remaining for r in plain.rows) - 9)

    def test_counted_items_are_still_refused_in_full(self):
        plain = make_world(options(**FINAL)).ctr_content_items
        extra = dict(extra=dict(trophies=plain.filler_count + 1 + len(content_item_pool.SURFACE_NAMES)))
        with self.assertRaisesRegex(OptionError, "locked placements 1"):
            make_world(options(item_pool=extra, **FINAL))

    def test_surface_items_go_only_after_filler(self):
        plain = make_world(options(**FINAL)).ctr_content_items
        room = plain.filler_count - 1
        kept = make_world(options(item_pool=dict(extra=dict(trophies=room)), **FINAL)).ctr_content_items
        self.assertEqual(kept.filler_count, 1)
        self.assertTrue(any(r.name in content_item_pool.SURFACE_NAMES for r in kept.rows))
        dropped = make_world(options(item_pool=dict(extra=dict(trophies=room + 1)), **FINAL)).ctr_content_items
        self.assertFalse(any(r.name in content_item_pool.SURFACE_NAMES for r in dropped.rows))

    def test_excluded_pinned_check_needs_no_filler(self):
        plain = make_world(options(shuffle_keys=False)).ctr_content_items
        room = plain.filler_count - 1
        world = make_world(options(shuffle_keys=False, oxide_goal="any_percent", item_pool=dict(extra=dict(trophies=room)),
                                   exclude_locations=set(BOSS_NAMES)))
        self.assertTrue(any(r.name in content_item_pool.SURFACE_NAMES for r in world.ctr_content_items.rows))
        self.assertEqual(holding(world, BOSS_NAMES[0]).name, "Key")


class TestRelicGuard(unittest.TestCase):
    def guarded(self, **overrides):
        return next(w for w in (make_world(options(shuffle_gems=False, **VANILLA, **overrides), seed=seed) for seed in range(40))
                    if content_fixed.guarded_track("vanilla", w.ctr_content_plan.get("fixed_items", {}),
                                                   w.ctr_content_plan["pads"], w.ctr_content_plan["entries"]))

    def test_guard_follows_the_pad(self):
        world = self.guarded()
        plan = world.ctr_content_plan
        track_id = occupied(plan)[content_fixed.GEM_PAD]["track_id"]
        track = next(t for t in plan["tracks"] if t["id"] == track_id)
        self.assertEqual(content_plan.plan_relics(plan, track), set())
        self.assertEqual(sum(c["kind"] == "relic" and c["routes"][0]["award"] == "sapphire" for c in plan["checks"]), 17)
        self.assertIn(content_plan.RELIC_FEATURE, plan["required_features"])

    def test_item_counts_stay_exact(self):
        world = self.guarded()
        self.assertEqual(pool(world, "Sapphire Relic"), 18)
        self.assertEqual(pool(world, "Gold Relic"), 18)

    def test_turbo_track_elsewhere_keeps_its_checks(self):
        for seed in range(40):
            world = make_world(options(shuffle_gems=False, **VANILLA), seed=seed)
            plan = world.ctr_content_plan
            pads = occupied(plan)
            turbo = next((p for p, e in pads.items() if e.get("track_id") == "retail:17" or e.get("track_id") == "retail:16"
                          and next(t for t in plan["tracks"] if t["id"] == e["track_id"])["display_name"] == "Turbo Track"), None)
            if turbo is not None and turbo != content_fixed.GEM_PAD:
                track = next(t for t in plan["tracks"] if t["id"] == pads[turbo]["track_id"])
                self.assertTrue(content_plan.plan_relics(plan, track))
                return
        self.fail("no seed moved the track")

    def test_vanilla_placement_guards_turbo_track_itself(self):
        plan = make_world(options("vanilla", shuffle_gems=False, **VANILLA)).ctr_content_plan
        self.assertEqual(sum(c["kind"] == "relic" and c["routes"][0]["award"] == "gold" for c in plan["checks"]), 17)
        self.assertFalse([c for c in plan["checks"] if c["kind"] == "relic" and c["display_name"].startswith("Turbo Track")])

    def test_no_guard_elsewhere(self):
        for overrides in (dict(), dict(shuffle_gems=False), dict(**VANILLA)):
            plan = make_world(options(**overrides)).ctr_content_plan
            self.assertEqual(sum(c["kind"] == "relic" and c["routes"][0]["award"] == "gold" for c in plan["checks"]), 18)
        plan = make_world(options(shuffle_gems=False, content_pool=cups(4), **VANILLA)).ctr_content_plan
        self.assertEqual(sum(c["kind"] == "relic" and c["routes"][0]["award"] == "gold" for c in plan["checks"]), 18)

    def test_a_fixed_gem_cup_leaves_the_start_to_a_race(self):
        layout = dict(placement="shuffle", stages="two", mode_order="per_pad", merge_trophy_ctr=False)
        for seed in range(30):
            make_world(options(shuffle_gems=False, pad_layout=layout, **VANILLA), seed=seed)

    def test_gem_cup_never_needs_its_own_gem(self):
        for seed in range(60):
            plan = make_world(options(shuffle_gems=False, **VANILLA), seed=seed).ctr_content_plan
            self.assertNotEqual(occupied(plan).get(content_fixed.GEM_PAD, {}).get("kind"), "cup", seed)


class TestGarages(unittest.TestCase):
    def rows(self, **overrides):
        return make_world(options(shuffle_keys=False, **overrides)).ctr_content_items.rows

    def test_a_key_garage_is_stuck(self):
        rows = self.rows()
        pins = dict.fromkeys(content_bosses.BOSS_CODES, "Key")
        trophy = dict(op="count", item=content_item_pool.ITEMS["Trophy"], count=1)
        self.assertEqual(content_fixed.stuck_garages({g: trophy for g in range(4)}, rows, pins, []), [])
        stuck = {0: dict(op="count", item=KEY, count=1), 1: trophy, 2: trophy, 3: trophy}
        self.assertEqual(content_fixed.stuck_garages(stuck, rows, pins, []), [0, 1, 2, 3])

    def test_an_extra_key_frees_it(self):
        rows = self.rows(item_pool=dict(extra=dict(keys=1)))
        pins = dict.fromkeys(content_bosses.BOSS_CODES, "Key")
        trophy = dict(op="count", item=content_item_pool.ITEMS["Trophy"], count=1)
        self.assertEqual(content_fixed.stuck_garages({0: dict(op="count", item=KEY, count=1), 1: trophy, 2: trophy, 3: trophy},
                                                     rows, pins, []), [])

    def test_a_gem_garage_behind_its_own_cup_is_stuck(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False))
        pads = world.ctr_content_plan["pads"]
        red = next(p for p in pads if p["entry_id"] == "entry/gem_cup:0")
        trophy = dict(op="count", item=content_item_pool.ITEMS["Trophy"], count=1)
        keep = red["entrance_req"]
        red["entrance_req"] = "keys:1"
        pins = content_fixed.plan_placements(world.ctr_content_plan)
        gem = dict(op="count", item=content_item_pool.ITEMS["Red Gem"], count=1)
        self.assertEqual(content_fixed.stuck_garages({0: gem, 1: trophy, 2: trophy, 3: trophy},
                                                     world.ctr_content_items.rows, pins, pads), [0, 1, 2, 3])
        red["entrance_req"] = keep

    def test_generated_garages_are_never_stuck(self):
        for seed in range(40):
            world = make_world(options(shuffle_keys=False, shuffle_gems=False), seed=seed)
            plan = world.ctr_content_plan
            reqs = {int(r["id"].split(":")[1]): r["predicate"] for r in plan["requirements"] if r["id"].startswith("boss:")}
            self.assertEqual(content_fixed.stuck_garages(reqs, world.ctr_content_items.rows,
                                                         content_fixed.plan_placements(plan), plan["pads"]), [], seed)

    def test_pads_only_ask_what_the_pins_allow(self):
        # The plain fill proves it: every location of the seed is reachable.
        for seed in range(12):
            mw = filled(make_world(options(shuffle_keys=False, shuffle_gems=False), seed=seed))
            self.assertTrue(mw.fulfills_accessibility())

    def test_second_stages_survive_fixed_keys(self):
        count = [len(records(make_world(options(shuffle_keys=False), seed=seed).ctr_content_plan, "stage2:"))
                 for seed in range(30)]
        self.assertGreater(sum(count) / len(count), 15)

    def test_stand_ins_hold_the_pins(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False))
        plan = world.ctr_content_plan
        stands = cr.stand_ins(world, plan["checks"], plan["entries"], plan["pads"],
                              {int(p["id"].split(":")[1]): next(e for e in plan["entries"] if e["id"] == p["entry_id"]).get("modes", ())
                               for p in plan["pads"] if p["entry_id"] is not None and p["kind"] == "normal"},
                              world.ctr_content_items.rows, set(), content_fixed.plan_placements(plan))
        for code in content_bosses.BOSS_CODES:
            self.assertEqual(stands[code], "Key")
        self.assertEqual(sum(name == "Key" for name in stands.values()), 4)
        self.assertEqual(stands[content_fixed.GEM_CHECK], "Red Gem")


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.world = make_world(options(shuffle_keys=False, shuffle_gems=False, **FINAL))
        self.plan = json.loads(json.dumps(self.world.ctr_content_plan))
        content_plan.validate(self.plan)

    def refused(self, change, source=None):
        plan = copy.deepcopy(source or self.plan)
        change(plan)
        with self.assertRaises(OptionError):
            content_plan.validate(plan)

    def test_ledger(self):
        def row_of(p, item):
            return next(r for r in p["items"]["rows"] if r["item"] == item)

        self.refused(lambda p: p["items"].update(locked_checks=9))
        self.refused(lambda p: row_of(p, KEY).update(locked_selected=3, remaining=1))
        self.refused(lambda p: row_of(p, KEY).update(remaining=1))

    def test_record(self):
        self.refused(lambda p: p.pop("fixed_items"))
        self.refused(lambda p: p["fixed_items"].update(keys=False))
        self.refused(lambda p: p["fixed_items"].update(other=True))
        self.refused(lambda p: p["required_features"].remove(content_fixed.FEATURE))
        self.refused(lambda p: p.update(fixed_items={}))

    def test_filler_needs_its_goal(self):
        self.refused(lambda p: p["bosses"].update(oxide_1_optional=False))
        other = make_world(options(oxide_goal="any_percent", shuffle_keys=False))
        def forge(p):
            p["fixed_items"]["oxide_1_filler"] = True
        self.refused(forge, json.loads(json.dumps(other.ctr_content_plan)))

    def test_gems_need_all_five_cups(self):
        world = make_world(options(content_pool=cups(4), shuffle_keys=False))
        self.refused(lambda p: p["fixed_items"].update(gems=True), json.loads(json.dumps(world.ctr_content_plan)))

    def test_guarded_track_holds_no_tier_check(self):
        guard = TestRelicGuard().guarded()
        plan = json.loads(json.dumps(guard.ctr_content_plan))
        content_plan.validate(plan)
        self.refused(lambda p: p.pop("fixed_items"), plan)


class TestTracker(unittest.TestCase):
    def test_restore_keeps_the_pins(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False, start_inventory_from_pool={"Key": 1}, **FINAL))
        wire = json.loads(json.dumps(world.fill_slot_data()))
        restored = make_world({}, passthrough=wire)
        self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(restored.ctr_content_items.locked_checks, world.ctr_content_items.locked_checks)
        self.assertEqual(restored.options.shuffle_keys.value, 0)
        self.assertEqual(restored.options.shuffle_gems.value, 0)
        self.assertEqual(restored.options.oxide_1_optional.value, 2)
        self.assertEqual(holding(restored, BOSS_NAMES[0]).name, "Key")
        self.assertEqual(holding(restored, OXIDE_FIRST).name, "Wumpa Fruit")
        self.assertEqual(holding(restored, "Red Gem Cup: Gem").name, "Red Gem")

    def test_restore_of_a_shuffled_plan_leaves_the_tracker_yaml_out(self):
        world = make_world(options())
        restored = make_world(dict(shuffle_keys=False, shuffle_gems=False), passthrough=json.loads(json.dumps(world.fill_slot_data())))
        self.assertEqual((restored.options.shuffle_keys.value, restored.options.shuffle_gems.value), (1, 1))


class TestFramework(unittest.TestCase):
    def test_pins_do_not_count_as_plando(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False, **FINAL), stop_before="pre_fill")
        call_all(world.multiworld, "pre_fill")
        self.assertFalse(any(world.ctr_framework_accounting.values()))

    def test_pinned_items_are_progression(self):
        world = make_world(options(shuffle_keys=False, shuffle_gems=False))
        self.assertTrue(holding(world, BOSS_NAMES[0]).classification & ItemClassification.progression)
        self.assertTrue(holding(world, "Red Gem Cup: Gem").classification & ItemClassification.progression)
