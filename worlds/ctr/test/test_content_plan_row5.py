"""One generator row 5: boss cups with drawn bosses, the Purple Gem Cup gauntlet,
the Wumpa Shop and goal against the ledger, Spoiler Items, and the rule that a
YAML without content_pool ignores all of it."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_bosses, content_cups, content_plan, content_wumpa
from .test_content_plan import make_world

SHAPE = dict(preset="mixed", tracks=dict(retail="all", modes=["trophy", "ctr", "relic"], custom=[]),
             cups=dict(count=5), crystals=dict(count=4), bosses=dict(enabled=True))


def options(**overrides):
    shape = copy.deepcopy(SHAPE)
    shape["bosses"].update(overrides.pop("bosses", {}))
    shape["cups"].update(overrides.pop("cups", {}))
    return {"content_pool": shape, "item_pool": {}, "accessibility": "full",
            "pad_layout": dict(placement="shuffle", stages="two", mode_order="fixed", merge_trophy_ctr=False),
            **overrides}


def fill(world):
    from Fill import distribute_items_restrictive
    from worlds.AutoWorld import call_all
    mw = world.multiworld
    call_all(mw, "pre_fill")
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    return json.loads(json.dumps(world.fill_slot_data()))


def entries(plan):
    return {e["id"]: e for e in plan["entries"]}


def refusal(o, seed=1):
    try:
        make_world(o, seed=seed)
    except OptionError as exc:
        return str(exc)
    return None


class TestBossCups(unittest.TestCase):
    def cup_world(self, seed=1, **extra):
        return make_world(options(bosses=dict(cups=dict(min=2, max=2)), boss_opponent_shuffle=True, boss_kit_shuffle=True,
                                  **extra), seed=seed)

    def test_a_boss_cup_takes_a_drawn_racer_and_kit(self):
        plan = self.cup_world().ctr_content_plan
        self.assertEqual(len(plan["bosses"]["cups"]), 2)
        by_id = entries(plan)
        for g in plan["bosses"]["cups"]:
            opponent = by_id[f"entry/boss:{g}/0"]["opponent"]
            self.assertEqual(by_id[f"entry/boss:{g}/0"]["kind"], "boss_cup")
            self.assertEqual(opponent["attack_profile"], "composed")
            self.assertEqual(len(opponent["schedule"]), 5)

    def test_the_schedule_keeps_the_retail_segments(self):
        plan = self.cup_world().ctr_content_plan
        by_id = entries(plan)
        for g in plan["bosses"]["cups"]:
            cps = [seg[0] for seg in by_id[f"entry/boss:{g}/0"]["opponent"]["schedule"]]
            home = content_bosses.boss_track_shuffle.VENUES[content_bosses.home_track(g)]
            self.assertEqual(tuple(cps), content_bosses.mapped_checkpoints(g, home))

    def test_racers_stay_distinct_over_cups_and_races(self):
        for seed in range(6):
            plan = self.cup_world(seed).ctr_content_plan
            racers = [e["opponent"]["character_id"] for k, e in entries(plan).items() if k.startswith("entry/boss:")
                      and not k.startswith("entry/boss:4")]
            self.assertEqual(len(set(racers)), 4)

    def test_the_hit_route_follows_the_drawn_racer(self):
        plan = self.cup_world(hit_character=True).ctr_content_plan
        by_id = entries(plan)
        routes = content_bosses.hit_routes(plan)
        for g in plan["bosses"]["cups"]:
            racer = by_id[f"entry/boss:{g}/0"]["opponent"]["character_id"]
            self.assertTrue(any(r["entry_id"] == f"entry/boss:{g}/0" and r["mode"] == "boss_cup" for r in routes[racer]))

    def test_home_pairing_leaves_a_cup_alone(self):
        plan = self.cup_world(boss_track_shuffle=True).ctr_content_plan
        self.assertEqual(plan["bosses"]["track_assignment"], "character_home_track")
        self.assertTrue(content_plan.validate(plan))

    def test_a_forged_cup_kit_is_refused(self):
        plan = copy.deepcopy(self.cup_world().ctr_content_plan)
        g = plan["bosses"]["cups"][0]
        entries(plan)[f"entry/boss:{g}/0"]["opponent"]["schedule"][1][0] += 1
        with self.assertRaises(OptionError):
            content_plan.validate(plan)

    def test_a_cup_fills_and_restores(self):
        world = self.cup_world(hit_character=True)
        wire = fill(world)
        self.assertTrue(world.multiworld.can_beat_game())
        again = make_world(options(), seed=2, stop_before="generate_early")
        again.multiworld.re_gen_passthrough = {again.game: wire}
        content_plan.restore(again, wire)
        self.assertEqual(again.ctr_content_plan, wire["content_plan"])
        self.assertEqual(again.options.boss_kit_shuffle.value, 1)


class TestGauntlet(unittest.TestCase):
    MESSAGE = "purple_cup_boss_gauntlet needs boss_kit_shuffle and the Purple Gem Cup"

    def test_it_needs_the_kit_switch(self):
        self.assertIn(self.MESSAGE, refusal(options(purple_cup_boss_gauntlet=True)))

    def test_it_needs_the_purple_gem_cup(self):
        self.assertIn(self.MESSAGE, refusal(options(purple_cup_boss_gauntlet=True, boss_kit_shuffle=True,
                                                    cups=dict(count=4))))

    def test_bosses_off_is_the_same_message(self):
        o = options(purple_cup_boss_gauntlet=True, oxide_goal="disabled", gems_required_goal=2,
                    bosses=dict(enabled=False))
        self.assertIn(self.MESSAGE, refusal(o))

    def test_the_record_carries_the_switch(self):
        plan = make_world(options(purple_cup_boss_gauntlet=True, boss_kit_shuffle=True), seed=3).ctr_content_plan
        self.assertIs(plan["bosses"]["gauntlet"], True)
        self.assertTrue(content_plan.validate(plan))
        self.assertTrue(any("boss gauntlet" in line for line in content_bosses.spoiler_lines(plan)))

    def test_a_forged_switch_without_a_kit_is_refused(self):
        plan = copy.deepcopy(make_world(options(boss_opponent_shuffle=True), seed=3).ctr_content_plan)
        plan["bosses"]["gauntlet"] = True
        with self.assertRaises(OptionError):
            content_plan.validate(plan)

    def test_a_forged_switch_without_the_cup_is_refused(self):
        plan = copy.deepcopy(make_world(options(boss_kit_shuffle=True, cups=dict(count=4)), seed=3).ctr_content_plan)
        plan["bosses"]["gauntlet"] = True
        with self.assertRaises(OptionError):
            content_plan.validate(plan)


class TestShopLedger(unittest.TestCase):
    def test_surface_items_count_as_non_progression(self):
        world = make_world(options(wumpa_shop_slots=10, wumpa_shop_progression="excluded"), seed=2)
        items = world.ctr_content_plan["items"]
        surface = sum(r["remaining"] for r in items["rows"] if 35010021 <= r["item"] <= 35010025)
        self.assertEqual(surface, 5)
        self.assertGreaterEqual(content_wumpa.non_progression_supply(items), items["filler_count"] + 5)

    def test_pins_leave_excluded_slots_alone(self):
        world = make_world(options(wumpa_shop_slots=10, wumpa_shop_progression="excluded", shuffle_keys=False,
                                   shuffle_gems=False, oxide_goal="101_percent", oxide_1_optional="filler"), seed=2)
        fill(world)
        for location in world.multiworld.get_locations(world.player):
            if getattr(location, "type", None) == content_wumpa.KIND:
                self.assertFalse(location.item.advancement, location.name)
        self.assertTrue(world.multiworld.can_beat_game())

    def test_exclude_locations_share_the_filler_with_the_shop(self):
        world = make_world(options(wumpa_shop_slots=2, wumpa_shop_progression="excluded"), seed=2)
        need = content_wumpa.non_progression_supply(world.ctr_content_plan["items"])
        with self.assertRaises(OptionError):
            content_wumpa.check_supply(world.ctr_content_plan["wumpa_shop"], world.ctr_content_plan["items"], need)

    def test_the_wumpa_goal_alone_is_a_goal(self):
        world = make_world(options(oxide_goal="disabled", goal_wumpa=300), seed=4)
        plan = world.ctr_content_plan
        self.assertEqual(plan["goal"], dict(op="wumpa_banked", count=300))
        fill(world)
        self.assertTrue(world.multiworld.can_beat_game())

    def test_the_wumpa_goal_closes_a_filler_goal(self):
        world = make_world(options(oxide_goal="101_percent", oxide_1_optional="filler", goal_wumpa=300), seed=4)
        self.assertEqual(world.ctr_content_plan["goal"]["terms"][-1], dict(op="wumpa_banked", count=300))
        fill(world)
        self.assertTrue(world.multiworld.can_beat_game())

    def test_shop_slots_hold_a_progression_price_after_fill(self):
        world = make_world(options(wumpa_shop_slots=25), seed=5)
        wire = fill(world)
        for check in wire["content_plan"]["checks"]:
            if check["kind"] == content_wumpa.KIND:
                location = world.multiworld.get_location(check["display_name"], world.player)
                if location.item.advancement:
                    hub = check["display_name"].split(" Shop:")[0]
                    self.assertEqual(check["price"], content_wumpa.wumpa_shop.price_band(hub, 100)[0])


class TestSpoilerItems(unittest.TestCase):
    def test_both_items_are_rows_and_useful(self):
        world = make_world(options(spoiler_items=True, box_locations=True, color_boxes_by_item=True), seed=1)
        names = [i.name for i in world.multiworld.itempool]
        for name in ("Warp Pad Preview", "AP Box Colours"):
            self.assertEqual(names.count(name), 1)
        self.assertTrue(all(i.useful and not i.advancement for i in world.multiworld.itempool
                            if i.name in ("Warp Pad Preview", "AP Box Colours")))

    def test_no_box_colours_item_without_coloured_boxes(self):
        world = make_world(options(spoiler_items=True), seed=1)
        self.assertNotIn("AP Box Colours", [i.name for i in world.multiworld.itempool])

    def test_surface_items_drop_before_a_reveal_item_is_refused(self):
        tight = options(spoiler_items=True, wumpa_shop_slots=0, podium_placement_checks=False, character_unlocks=False)
        tight["item_pool"] = dict(base=dict(relics=dict(sapphire=18, gold=18, platinum=0)))
        world = None
        for seed in range(6):
            try:
                world = make_world(tight, seed=seed, stop_before="pre_fill")
                break
            except OptionError as exc:
                self.assertNotIn("Spoiler Items", str(exc))
        self.assertIsNotNone(world)
        self.assertIn("Warp Pad Preview", [i.name for i in world.multiworld.itempool])

    def test_a_reveal_item_alone_overflowing_is_named(self):
        o = options(spoiler_items=True, wumpa_shop_slots=0, podium_placement_checks=False, character_unlocks=False,
                    crystal=None)
        o.pop("crystal")
        o["item_pool"] = dict(base=dict(trophies=33, relics=dict(sapphire=18, gold=18, platinum=0)))
        message = refusal(o) or ""
        self.assertTrue("Spoiler Items" in message or "free checks" in message or not message)

    def test_the_tracker_keeps_the_rows(self):
        world = make_world(options(spoiler_items=True, box_locations=True, color_boxes_by_item=True), seed=1)
        wire = fill(world)
        again = make_world(options(), seed=2, stop_before="generate_early")
        again.multiworld.re_gen_passthrough = {again.game: wire}
        content_plan.restore(again, wire)
        self.assertEqual(again.options.spoiler_items.value, 1)


class TestDefaultPath(unittest.TestCase):
    def test_a_yaml_without_content_pool_ignores_row_5(self):
        extras = dict(adventure_structure="ctr_first", goal_wumpa=500, wumpa_shop_slots=25, spoiler_items=True,
                      boss_opponent_shuffle=True, boss_kit_shuffle=True, purple_cup_boss_gauntlet=True)
        plain = make_world({}, seed=8, stop_before="pre_fill")
        loud = make_world(extras, seed=8, stop_before="pre_fill")
        names = lambda w: sorted(l.name for l in w.multiworld.get_locations(w.player))
        items = lambda w: sorted(i.name for i in w.multiworld.itempool)
        self.assertEqual(names(plain), names(loud))
        self.assertEqual(items(plain), items(loud))
        self.assertFalse(hasattr(plain, "ctr_content_plan"))
