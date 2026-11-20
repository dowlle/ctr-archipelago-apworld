"""A6-16c: physical awards and repeatable fill access are separate.

The Yellow leg-four fixture uses four selected tracks and the four Gem Cups
needed to include Yellow. It contains no played-room data and searches no seeds.
Production generation and validation build its gates, routes and accounting.
"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from BaseClasses import CollectionState, ItemClassification
from Fill import distribute_items_restrictive
from .. import content_opening, content_plan as cp, content_pickups as pickups
from .test_content_plan import make_world


def options(**extra):
    return dict(dict(retail_tracks=["Dingo Canyon", "Tiny Arena", "Hot Air Skyway"], custom_tracks=[],
                     cup_count=0, crystal_challenge_count=0, boss_garages=True,
                     oxide_goal="101_percent", bosses_required_goal=0, gems_required_goal=0,
                     progressive_boost="off", progressive_stats="off", character_unlocks=False,
                     itemboxsanity=2, wumpasanity="both", wumpa_check="per_track",
                     item_box_count=0, wumpa_shop_slots=0, podium_rungs=[], accessibility="full"), **extra)


#: A6-48 removed Cortex Vortex's final-only checks from these rooms, so the
#: default pool no longer fits them.
FEWER_TROPHIES = {"base": {"trophies": 10}}


def state_with(world, keys=4, trophies=4, boost=3):
    state = CollectionState(world.multiworld)
    for item in world.multiworld.itempool:
        if item.name not in ("Key", "Trophy", "Progressive Boost", "Crash Bandicoot"):
            state.collect(item, True)
    for name, count in (("Key", keys), ("Trophy", trophies), ("Progressive Boost", boost)):
        for _ in range(count):
            state.collect(world.create_item(name), True)
    return state


def oxide_checks(plan):
    return [c for c in plan["checks"] if c["owner"] == "retail:13" and c["kind"] in pickups.KINDS]


def yellow_fixture(locked=False, boost=False):
    # Control only the drawn cup and its seat. The production generator builds
    # and validates all routes, identities, requirements and item accounting.
    # A relic-only Oxide pad cannot award ordinary pickups or Reach 10 Wumpa.
    draw = cp.content_cups.draw_cups
    seat = cp.content_requirements.seat_content

    def draw_yellow(*args, **kwargs):
        cups = draw(*args, **kwargs)
        cup = cups[3]
        by_name = {t["display_name"]: t for t in args[2]}
        earlier = [by_name[t] for t in ("Dingo Canyon", "Tiny Arena", "Hot Air Skyway", "Dingo Canyon")]
        for other in cups[:3]:
            other["legs"] = earlier[:]
        cup.update(gem_cup=3, id=cp.content_cups.gem_owner(3),
                   legs=[by_name[t] for t in ("Dingo Canyon", "Tiny Arena", "Hot Air Skyway", "Oxide Station")])
        return cups

    def seat_yellow(*args, **kwargs):
        chosen, registry = seat(*args, **kwargs)
        i = next(i for i, t in enumerate(chosen) if t.get("gem_cup") == 3)
        j = next(j for j, row in enumerate(registry) if row[0] == 11)
        registry[i], registry[j] = registry[j], registry[i]
        return chosen, registry

    with patch.object(cp.content_cups, "draw_cups", draw_yellow), patch.object(cp.content_requirements, "seat_content", seat_yellow):
        world = make_world(options(retail_tracks=options()["retail_tracks"] + ["Oxide Station"],
                                   track_modes={"default": ["trophy"], "Oxide Station": ["relic"]},
                                   cup_count=4, cup_tracks="random_repeats", character_unlocks=locked,
                                   item_pool={"base": {"trophies": 4}},
                                   warp_pad_rules={cp.content_requirements.KEY_BY_PHYSICAL[11]: dict(item="Trophy", count=4)},
                                   progressive_boost="shared_global" if boost else "off"),
                           seed=3, stop_before="create_regions")
    plan = world.ctr_content_plan
    assert cp.validate(plan)
    if locked:
        next(p for p in plan["pads"] if p["entry_id"] == "entry/gem_cup:3")["racer_lock"] = 0
    cp.create_regions(world)
    cp.create_items(world)
    cp.set_rules(world)
    return world


class TestOxidePickups(unittest.TestCase):
    def test_yellow_leg_four_needs_every_gate_and_cannot_supply_its_fourth_trophy(self):
        world = yellow_fixture()
        checks = oxide_checks(world.ctr_content_plan)
        self.assertEqual({c["kind"] for c in checks}, {"weapon_crate", "wumpa_crate", "wumpa"})
        locations = {loc.address: loc for loc in world.multiworld.get_locations(1)}
        for keys, trophies, reachable in ((2, 4, False), (3, 3, False), (4, 3, False), (3, 4, True), (4, 4, True)):
            with self.subTest(keys=keys, trophies=trophies):
                state = state_with(world, keys, trophies)
                self.assertTrue(all(locations[c["location"]].can_reach(state) == reachable for c in checks))
                if keys == 4:
                    self.assertTrue(state.can_reach("entry/boss:4/0", "Region", 1))
        # The fourth Trophy cannot bootstrap itself from a pickup inside the cup.
        target = locations[checks[0]["location"]]
        target.place_locked_item(world.create_item("Trophy"))
        state = state_with(world, trophies=3)
        state.sweep_for_advancements([target])
        self.assertEqual(state.count("Trophy", 1), 3)
        self.assertFalse(target.can_reach(state))
        state.collect(world.create_item("Trophy"), True)
        self.assertTrue(target.can_reach(state))

    def test_yellow_prefix_and_racer_lock(self):
        world = yellow_fixture(locked=True, boost=True)
        locations = {loc.address: loc for loc in world.multiworld.get_locations(1)}
        checks = oxide_checks(world.ctr_content_plan)
        state = state_with(world, boost=0)
        self.assertFalse(any(locations[c["location"]].can_reach(state) for c in checks))
        boosted_without_racer = state_with(world, boost=3)
        self.assertFalse(any(locations[c["location"]].can_reach(boosted_without_racer) for c in checks))
        racer = world.create_item("Crash Bandicoot")
        # This fixture adds its lock after generation classified the racers.
        racer.classification = ItemClassification.progression
        state.collect(racer, True)
        self.assertFalse(any(locations[c["location"]].can_reach(state) for c in checks))
        for _ in range(3):
            state.collect(world.create_item("Progressive Boost"), True)
        self.assertTrue(all(locations[c["location"]].can_reach(state) for c in checks))

    def test_opening_estimator_uses_only_repeatable_oxide_routes(self):
        world = yellow_fixture()
        plan = world.ctr_content_plan
        reach = content_opening.plan_reach(world, plan)
        pickup_codes = {c["location"] for c in oxide_checks(plan)}
        held = ("Key",) * 4 + ("Trophy",) * 3
        first = next(encounter for encounter in plan["encounters"] if encounter["id"] == pickups.FIRST)
        self.assertTrue(reach.encounter_reached(first, held))
        self.assertFalse(pickup_codes & reach._open(reach._held(held)))
        self.assertTrue(pickup_codes <= reach._open(reach._held(held + ("Trophy",))))

    def test_no_repeatable_route_omits_pickups_but_keeps_lap_and_victory(self):
        for optional in ("mandatory", "optional", "filler"):
            with self.subTest(optional=optional):
                world = make_world(options(oxide_1_optional=optional, lap_completion_checks=True), seed=3)
                plan = world.ctr_content_plan
                self.assertTrue(pickups.enabled(plan))
                self.assertFalse(oxide_checks(plan))
                self.assertNotIn("retail:13", {r["track_id"] for r in plan["sanity"]["tracks"]})
                self.assertTrue(any(c["owner"] == "retail:13" and c["kind"] == "lap" for c in plan["checks"]))
                self.assertTrue(any(c["location"] == cp.content_bosses.OXIDE_FIRST for c in plan["checks"]))
                self.assertTrue(cp.validate(plan))
                self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))

    def test_final_route_and_standalone_pad_are_alternatives(self):
        world = make_world(options(retail_tracks=options()["retail_tracks"] + ["Oxide Station"],
                                   oxide_final_track="oxide_station", oxide_1_optional="optional"), seed=3)
        plan = world.ctr_content_plan
        checks = oxide_checks(plan)
        self.assertTrue(checks)
        for c in checks:
            routes = pickups.logic_routes(c, True)
            self.assertTrue(any(r["encounter_id"] == "encounter/garage:4/1" for r in routes))
            self.assertTrue(any(r["encounter_id"] is None for r in routes))
            self.assertTrue(any(r["encounter_id"] == pickups.FIRST for r in c["routes"]))
        self.assertTrue(cp.validate(plan))

    def test_own_pad_gate_cannot_be_bypassed_by_oxide_one(self):
        world = make_world(options(retail_tracks=options()["retail_tracks"] + ["Oxide Station"],
                                   pad_placement="vanilla",
                                   warp_pad_rules={"Oxide Station": dict(item="Trophy", count=4)}), seed=3)
        locations = {loc.address: loc for loc in world.multiworld.get_locations(1)}
        checks = oxide_checks(world.ctr_content_plan)
        self.assertTrue(checks)
        blocked = state_with(world, trophies=3)
        self.assertTrue(blocked.can_reach("entry/boss:4/0", "Region", 1))
        self.assertFalse(any(locations[c["location"]].can_reach(blocked) for c in checks))
        opened = state_with(world, trophies=4)
        self.assertTrue(all(locations[c["location"]].can_reach(opened) for c in checks))

    def test_full_accessibility_fill_and_tracker_restore(self):
        for final in ("cortex_vortex", "oxide_station"):
            # A6-48: a final-only venue has no checks, so the pool is smaller.
            world = make_world(options(oxide_final_track=final, item_pool=FEWER_TROPHIES), seed=5)
            distribute_items_restrictive(world.multiworld)
            state = world.multiworld.get_all_state(False)
            self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations(1)))
            wire = world.fill_slot_data()
            restored = make_world(options(item_pool=FEWER_TROPHIES), seed=5, passthrough=wire)
            self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
            self.assertEqual({l.address for l in restored.multiworld.get_locations(1)},
                             {l.address for l in world.multiworld.get_locations(1)})

    def test_old_room_restores_original_locations_and_logic(self):
        # This predates the feature: every track has a pad, so the physical
        # registry is identical. Absence retains Oxide 1 as a fill route.
        world = make_world(options(retail_tracks=options()["retail_tracks"] + ["Oxide Station"]), seed=3)
        wire = copy.deepcopy(world.fill_slot_data())
        wire["content_plan"]["required_features"].remove(pickups.FEATURE)
        restored = make_world(options(), seed=3, passthrough=wire)
        self.assertTrue(cp.validate(restored.ctr_content_plan))
        self.assertFalse(pickups.enabled(restored.ctr_content_plan))
        for c in oxide_checks(restored.ctr_content_plan):
            self.assertEqual(pickups.logic_routes(c, False), c["routes"])

    def test_pre_feature_first_only_room_keeps_its_pickups(self):
        wire = json.loads((Path(__file__).parent / "fixtures" / "oxide_first_legacy.json").read_text())
        world = make_world(options(), seed=1, passthrough=wire)
        plan = world.ctr_content_plan
        checks = oxide_checks(plan)
        self.assertTrue(checks)
        self.assertTrue(all(r["encounter_id"] == pickups.FIRST for c in checks for r in c["routes"]))
        self.assertTrue(cp.validate(plan))
        state = state_with(world)
        self.assertTrue(all(world.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))

    def test_priority_and_exclusions_cannot_restore_an_omitted_location(self):
        world = make_world(options(priority_locations={"Oxide Station: Weapon Crate 1"},
                                   exclude_locations={"Oxide Station: Wumpa Crate 1"}, item_pool=FEWER_TROPHIES), seed=3)
        self.assertFalse(oxide_checks(world.ctr_content_plan))

    def test_omitted_reach_ten_wumpa_exclusion_reserves_no_filler(self):
        opts = options(item_pool={"base": {"trophies": 10}})
        base = make_world(opts, seed=1).ctr_content_plan
        excluded = make_world(dict(opts, exclude_locations={"Oxide Station: Reach 10 Wumpa"}), seed=1).ctr_content_plan
        self.assertFalse(oxide_checks(base))
        self.assertFalse(oxide_checks(excluded))
        self.assertEqual(base["items"], excluded["items"])

    def test_loose_fruit_and_ordinary_boss_routes_are_unchanged(self):
        world = make_world(options(item_pool=FEWER_TROPHIES), seed=3)
        plan = world.ctr_content_plan
        # Oxide Station has no loose fruit. Ordinary garage venues have
        # repeatable routes, including when their track has no standalone pad.
        self.assertEqual(cp.sanity.CATALOG["retail:13"]["counts"][2], 0)
        for c in plan["checks"]:
            if c["kind"] in pickups.KINDS and c["owner"] != "retail:13":
                self.assertEqual(pickups.logic_routes(c, True), c["routes"])
        for kind in pickups.KINDS:
            check = dict(kind=kind, owner="retail:13", routes=[dict(encounter_id=pickups.FIRST)])
            self.assertFalse(pickups.omit_unrepeatable([check]))

    def test_authored_boxes_use_only_supported_pad_modes(self):
        world = make_world(options(retail_tracks=options()["retail_tracks"] + ["Oxide Station"],
                                   track_modes={"default": ["trophy", "ctr", "relic"]}, item_box_count=2), seed=3)
        boxes = [c for c in world.ctr_content_plan["checks"] if c["kind"] == "box" and c["owner"] == "retail:13"]
        self.assertTrue(boxes)
        self.assertTrue(all(r["mode"] in ("trophy", "ctr", "relic") and r["encounter_id"] is None
                            for c in boxes for r in c["routes"]))
