"""#344 lap completion checks: the option, the plan's routes and rules, boss race
laps and Universal Tracker."""
import copy
import unittest

from BaseClasses import CollectionState
from NetUtils import convert_to_base_types
from Options import OptionError

from .test_content_plan import make_world, profile_options
from .. import content_laps, content_plan
from ..lap_checks import LAP_CORTEX_VORTEX_CODE
from ..progressive_capability import boost_item_name


def lap_locations(world):
    return {loc.name: loc for loc in world.multiworld.get_locations(1) if loc.name.endswith(": Complete One Lap")}


def lap_plan_options(**extra):
    options = profile_options()
    options["lap_completion_checks"] = True
    options.update(extra)
    return options


class TestContentPlan(unittest.TestCase):
    def test_off_keeps_the_plan(self):
        baseline = make_world(profile_options()).ctr_content_plan
        self.assertFalse(any(c["kind"] == content_laps.KIND for c in baseline["checks"]))
        self.assertNotIn(content_laps.FEATURE, baseline["required_features"])

    def test_every_standalone_track_has_one_lap_check_per_mode_route(self):
        options = lap_plan_options()
        options["content_pool"]["tracks"]["modes"] = ["trophy", "ctr", "relic"]
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        world = make_world(options)
        plan = world.ctr_content_plan
        self.assertEqual(plan["required_features"][-1], content_laps.FEATURE)
        laps = [c for c in plan["checks"] if c["kind"] == content_laps.KIND]
        tracks = {e["track_id"]: e for e in plan["entries"] if e["kind"] == "track"}
        self.assertEqual({c["owner"] for c in laps} & set(tracks), set(tracks))
        for check in laps:
            entry = tracks.get(check["owner"])
            if entry is None:
                continue
            routes = [r for r in check["routes"] if r["encounter_id"] is None]
            self.assertEqual([r["mode"] for r in routes], entry["modes"])
            self.assertTrue(all(r["award"] == "lap" and r["leg_id"] is None and r["entry_id"] == entry["id"]
                                for r in routes))
            track = next(t for t in plan["tracks"] if t["id"] == check["owner"])
            self.assertEqual(check["location"], content_plan.lap_location(track))
            self.assertEqual(check["display_name"], content_plan.room_title(track) + ": Complete One Lap")
        cortex = next(c for c in laps if c["owner"] == content_plan.CORTEX_TRACK_ID)
        self.assertEqual(cortex["location"], LAP_CORTEX_VORTEX_CODE)
        custom = next(c for c in laps if c["owner"].startswith("custom/"))
        self.assertEqual(custom["display_name"], "Baby T Park: Complete One Lap")
        self.assertTrue(content_plan.validate(plan))
        self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))

    def test_cup_legs_are_routes_in_entry_then_leg_order(self):
        from .test_content_cups import cup_options
        for seed in range(6):
            options = cup_options(seed)
            options["lap_completion_checks"] = True
            try:
                world = make_world(options, seed=seed)
            except OptionError:
                continue
            plan = world.ctr_content_plan
            laps = {c["owner"]: c for c in plan["checks"] if c["kind"] == content_laps.KIND}
            pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
            want = {}
            for entry in plan["entries"]:
                if entry["kind"] == "track":
                    want.setdefault(entry["track_id"], []).extend((entry["id"], m, None) for m in entry["modes"])
                elif entry["kind"] == "cup":
                    for leg in entry["legs"]:
                        want.setdefault(leg["track_id"], []).append((entry["id"], "cup", leg["id"]))
            self.assertEqual(set(laps) & set(want), set(want), seed)
            for track, routes in want.items():
                own = [r for r in laps[track]["routes"] if r["encounter_id"] is None]
                self.assertEqual([(r["entry_id"], r["mode"], r["leg_id"]) for r in own], routes)
                self.assertTrue(all(r["own_pad_id"] == pads[r["entry_id"]] for r in own))
            self.assertTrue(content_plan.validate(plan))

    def test_validate_refuses_forged_lap_checks(self):
        plan = make_world(lap_plan_options()).ctr_content_plan
        lap = next(c for c in plan["checks"] if c["kind"] == content_laps.KIND)
        for name, change in [
                ("code", lambda p, c: c.__setitem__("location", c["location"] + 1)),
                ("award", lambda p, c: c["routes"][0].__setitem__("award", "win")),
                ("name", lambda p, c: c.__setitem__("display_name", "Lap")),
                ("feature", lambda p, c: p["required_features"].remove(content_laps.FEATURE)),
                ("dropped", lambda p, c: p["checks"].remove(c))]:
            forged = copy.deepcopy(plan)
            check = next(c for c in forged["checks"] if c["location"] == lap["location"])
            change(forged, check)
            with self.subTest(name), self.assertRaises(OptionError):
                content_plan.validate(forged)

    def test_tracker_restores_the_switch_from_the_plan(self):
        world = make_world(lap_plan_options())
        wire = convert_to_base_types(world.fill_slot_data())
        self.assertNotIn("lap_completion_checks", wire["ctr_options"])
        tracker = make_world({}, seed=5, passthrough=wire)
        self.assertTrue(tracker.options.lap_completion_checks.value)
        self.assertEqual({l.address for l in tracker.multiworld.get_locations(1)},
                         {l.address for l in world.multiworld.get_locations(1)})

    def test_lap_rule_needs_the_finish_rank_not_a_win(self):
        options = lap_plan_options(progressive_boost="shared_global")
        options["content_pool"]["required_entries"] = ["retail:10", "custom/baby-t-park/1.0.2"]
        world = make_world(options)
        plan = world.ctr_content_plan
        hot_air = next(c for c in plan["checks"] if c["kind"] == content_laps.KIND and c["owner"] == "retail:10")
        location = world.multiworld.get_location(content_plan.LOCATION_BY_CODE[hot_air["location"]], 1)
        state = CollectionState(world.multiworld)
        for item in world.multiworld.itempool:
            if not item.name.startswith("Progressive Boost"):
                state.collect(item, True)
        self.assertFalse(location.can_reach(state))
        for _ in range(2):
            state.collect(world.create_item(boost_item_name()), True)
        self.assertTrue(location.can_reach(state))


class TestBossRaces(unittest.TestCase):
    def options(self, **extra):
        from .test_content_bosses import boss_options
        return boss_options(lap_completion_checks=True, **extra)

    def laps(self, world):
        return {c["owner"]: c for c in world.ctr_content_plan["checks"] if c["kind"] == content_laps.KIND}

    def test_every_encounter_is_a_route_of_its_venue(self):
        world = make_world(self.options())
        plan = world.ctr_content_plan
        laps = self.laps(world)
        entries = {e["id"]: e for e in plan["entries"]}
        self.assertEqual(len(plan["encounters"]), 6)
        for enc in plan["encounters"]:
            track = entries[enc["entry_id"]]["track_id"]
            routes = [r for r in laps[track]["routes"] if r["encounter_id"] == enc["id"]]
            self.assertEqual(len(routes), 1)
            self.assertEqual((routes[0]["mode"], routes[0]["own_pad_id"], routes[0]["award"], routes[0]["leg_id"]),
                             ("boss_race", enc["pad_id"], "lap", None))
        self.assertTrue(content_plan.validate(plan))

    def test_a_venue_raced_nowhere_else_has_its_check(self):
        world = make_world(self.options())
        laps = self.laps(world)
        cortex = laps[content_plan.CORTEX_TRACK_ID]
        self.assertEqual(cortex["location"], LAP_CORTEX_VORTEX_CODE)
        self.assertEqual([r["encounter_id"] for r in cortex["routes"]], ["encounter/garage:4/1"])

    def test_boss_cup_legs_are_routes(self):
        options = self.options()
        options["content_pool"]["bosses"]["cups"] = 2
        world = make_world(options)
        plan = world.ctr_content_plan
        laps = self.laps(world)
        count = 0
        for entry in plan["entries"]:
            if entry["kind"] != "boss_cup":
                continue
            enc = next(e for e in plan["encounters"] if e["entry_id"] == entry["id"])
            for leg in entry["legs"]:
                count += 1
                self.assertIn(("boss_cup", leg["id"], enc["id"]),
                              [(r["mode"], r["leg_id"], r["encounter_id"]) for r in laps[leg["track_id"]]["routes"]])
        self.assertEqual(count, 8)
        self.assertTrue(content_plan.validate(plan))

    def test_a_boss_route_needs_the_encounter_and_no_win(self):
        options = self.options(warppad_unlock_requirements="vanilla")
        world = make_world(options)
        cortex = self.laps(world)[content_plan.CORTEX_TRACK_ID]
        lap = world.multiworld.get_location(content_plan.LOCATION_BY_CODE[cortex["location"]], 1)
        self.assertFalse(lap.can_reach(CollectionState(world.multiworld)))
        self.assertTrue(lap.can_reach(world.multiworld.get_all_state(False)))

    def test_forged_boss_routes_are_refused(self):
        plan = make_world(self.options()).ctr_content_plan
        for name, change in [
                ("encounter", lambda r: r.__setitem__("encounter_id", "encounter/garage:0/0")),
                ("mode", lambda r: r.__setitem__("mode", "trophy")),
                ("pad", lambda r: r.__setitem__("own_pad_id", "garage:0"))]:
            forged = copy.deepcopy(plan)
            check = next(c for c in forged["checks"] if c["kind"] == content_laps.KIND
                         and c["owner"] == content_plan.CORTEX_TRACK_ID)
            change(check["routes"][0])
            with self.subTest(name), self.assertRaises(OptionError):
                content_plan.validate(forged)


if __name__ == "__main__":
    unittest.main()
