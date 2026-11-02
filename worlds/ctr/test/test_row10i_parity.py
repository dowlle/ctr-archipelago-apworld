"""One generator row 10i: parity fixes from the design audit.

Reach 10 Wumpa from cup legs and boss races, podium rungs from cup legs, vanilla
garages that open free without Trophies, and Turbo Track's five Gems of five
colours (content_race_routes, content_bosses, content_requirements)."""
import copy
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive

from .test_content_plan import make_world
from .test_content_plan_row3 import options as shape_options, records
from .. import content_bosses, content_plan, content_race_routes, content_requirements

TURBO_TRACK = 17
GEMS = list(range(35010009, 35010014))


def per_track(**extra):
    # Eight cups leave some tracks without a pad of their own.
    return dict(dict(wumpa_check="per_track", cup_count=8, accessibility="full"), **extra)


def standalone_tracks(plan):
    pads = {p["entry_id"] for p in plan["pads"] if p["entry_id"]}
    return {e["track_id"]: e for e in plan["entries"] if e["kind"] == "track" and e["id"] in pads}


def checks_of(plan, kind):
    return {c["owner"]: c for c in plan["checks"] if c["kind"] == kind}


class TestWumpaRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = make_world(per_track(), seed=1)
        cls.plan = cls.world.ctr_content_plan

    def test_every_cup_leg_and_boss_race_is_a_route(self):
        plan = self.plan
        wumpa = checks_of(plan, "wumpa")
        pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
        encounters = {e["entry_id"]: e for e in plan["encounters"]}
        own = standalone_tracks(plan)
        want = {}
        for track_id, entry in own.items():
            want[track_id] = [(entry["id"], m, None, None) for m in entry["modes"] if m in ("trophy", "ctr")]
        for entry in plan["entries"]:
            if entry["kind"] == "cup" and entry["id"] in pads:
                for leg in entry["legs"]:
                    want.setdefault(leg["track_id"], []).append((entry["id"], "cup", leg["id"], None))
            elif entry["id"] in encounters and entry["kind"] == "boss_race":
                want.setdefault(entry["track_id"], []).append(
                    (entry["id"], "boss_race", None, encounters[entry["id"]]["id"]))
        self.assertEqual(set(wumpa), set(want))
        for track_id, check in wumpa.items():
            self.assertEqual([(r["entry_id"], r["mode"], r["leg_id"], r["encounter_id"]) for r in check["routes"]],
                             want[track_id], track_id)
            self.assertTrue(all(r["award"] == "wumpa" for r in check["routes"]))

    def test_tracks_raced_only_in_cups_or_boss_races_keep_their_check(self):
        plan = self.plan
        wumpa = checks_of(plan, "wumpa")
        own = standalone_tracks(plan)
        extra = [check for owner, check in wumpa.items() if owner not in own]
        self.assertTrue(any(r["mode"] == "cup" for c in extra for r in c["routes"]))
        cortex = wumpa[content_plan.CORTEX_TRACK_ID]
        self.assertEqual(cortex["location"], 35016121)
        self.assertEqual([r["mode"] for r in cortex["routes"]], ["boss_race"])
        for check in extra:
            track = next(t for t in plan["tracks"] if t["id"] == check["owner"])
            self.assertEqual(check["location"], content_plan.wumpa_location(track))
            self.assertEqual(check["display_name"], content_plan.room_title(track) + ": Reach 10 Wumpa")
        self.assertTrue(content_plan.validate(plan))

    def test_a_cup_route_needs_the_cup_and_not_the_track_pad(self):
        plan = self.plan
        own = standalone_tracks(plan)
        check = next(c for owner, c in checks_of(plan, "wumpa").items()
                     if owner not in own and all(r["mode"] == "cup" for r in c["routes"]))
        location = self.world.multiworld.get_location(content_plan.LOCATION_BY_CODE[check["location"]], 1)
        state = CollectionState(self.world.multiworld)
        for item in self.world.multiworld.itempool:
            state.collect(item, True)
        state.sweep_for_advancements()
        self.assertTrue(location.can_reach(state))
        self.assertEqual(location.parent_region.name, "Menu")

    def test_the_seed_fills_with_every_location_reachable(self):
        world = make_world(per_track(), seed=2)
        mw = world.multiworld
        distribute_items_restrictive(mw)
        self.assertTrue(mw.can_beat_game())
        state = CollectionState(mw)
        state.sweep_for_advancements()
        self.assertTrue(all(loc.can_reach(state) for loc in mw.get_locations(1)))

    def test_forged_routes_are_refused(self):
        plan = copy.deepcopy(self.plan)
        check = next(c for c in plan["checks"] if c["kind"] == "wumpa" and any(r["mode"] == "cup" for r in c["routes"]))
        check["routes"] = [r for r in check["routes"] if r["mode"] != "cup"] or check["routes"][:1]
        with self.assertRaises(Exception):
            content_plan.validate(plan)
        plan = copy.deepcopy(self.plan)
        plan["checks"] = [c for c in plan["checks"] if c["owner"] != content_plan.CORTEX_TRACK_ID or c["kind"] != "wumpa"]
        with self.assertRaises(Exception):
            content_plan.validate(plan)

    def test_global_and_off_are_unchanged(self):
        for value in ("off", "global"):
            plan = make_world(per_track(wumpa_check=value), seed=1).ctr_content_plan
            self.assertFalse(any(c["kind"] == "wumpa" and c["owner"] != "global" for c in plan["checks"]))
            self.assertFalse(any(r["mode"] not in ("trophy", "ctr") for c in plan["checks"]
                                 if c["kind"] == "wumpa" for r in c["routes"]))


class TestRungRoutes(unittest.TestCase):
    def test_cup_legs_route_the_rungs_of_tracks_with_a_trophy_race(self):
        world = make_world(per_track(wumpa_check="off"), seed=1)
        plan = world.ctr_content_plan
        own = standalone_tracks(plan)
        pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
        legs = {}
        for entry in plan["entries"]:
            if entry["kind"] == "cup" and entry["id"] in pads:
                for leg in entry["legs"]:
                    legs.setdefault(leg["track_id"], []).append((entry["id"], "cup", leg["id"]))
        rungs = [c for c in plan["checks"] if c["kind"] == "podium"]
        self.assertTrue(rungs)
        for check in rungs:
            first, *rest = check["routes"]
            self.assertEqual(first["leg_id"], None)
            self.assertEqual([(r["entry_id"], r["mode"], r["leg_id"]) for r in rest], legs.get(check["owner"], []))
            self.assertTrue(all(r["award"] == first["award"] and r["encounter_id"] is None for r in rest))
        # A track raced only in cups has no Trophy Race, so no rungs (item 7).
        self.assertFalse({c["owner"] for c in rungs} - set(own))
        self.assertTrue(set(legs) - set(own))
        self.assertTrue(content_plan.validate(plan))

    def test_no_rung_route_comes_from_a_boss_race(self):
        plan = make_world(per_track(wumpa_check="off"), seed=3).ctr_content_plan
        self.assertFalse(any(r["encounter_id"] for c in plan["checks"] if c["kind"] == "podium" for r in c["routes"]))


class TestGarages(unittest.TestCase):
    def test_vanilla_garages_open_free_without_trophies(self):
        o = shape_options(warppad_unlock_requirements="vanilla")
        o["item_pool"] = {"base": {"trophies": 0}}
        plan = make_world(o, seed=1).ctr_content_plan
        garages = records(plan, "boss:")
        self.assertEqual(garages, {g: content_bosses.FREE_GARAGE for g in range(4)})
        self.assertTrue(content_plan.validate(plan))

    def test_a_free_garage_is_refused_when_trophies_exist(self):
        world = make_world(shape_options(warppad_unlock_requirements="vanilla"), seed=1)
        rows = world.ctr_content_items.rows
        with self.assertRaises(Exception):
            content_bosses.check_garage_requirement(content_bosses.FREE_GARAGE, rows, 0, "vanilla")
        with self.assertRaises(Exception):
            content_bosses.check_garage_requirement(content_bosses.FREE_GARAGE, rows, 0, "randomized")


class TestTurboTrack(unittest.TestCase):
    def test_vanilla_turbo_track_asks_one_gem_of_each_colour(self):
        world = make_world(shape_options("vanilla", warppad_unlock_requirements="vanilla"), seed=1)
        plan = world.ctr_content_plan
        self.assertEqual(records(plan, content_requirements.STAGE1_PREFIX)[TURBO_TRACK],
                         dict(op="distinct", items=GEMS, count=5))
        term = content_plan.predicate(world, dict(op="distinct", items=GEMS, count=5))
        state = CollectionState(world.multiworld)
        state.prog_items[1]["Red Gem"] = 5
        self.assertFalse(term(state))
        for name in ("Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"):
            state.prog_items[1][name] = 1
        self.assertTrue(term(state))

    def test_fewer_colours_ask_the_colours_that_exist(self):
        by_name = {n: type("Row", (), dict(item=GEMS[i], requirement_ceiling=int(i < 3)))
                   for i, n in enumerate(("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"))}
        self.assertEqual(content_requirements.rule_predicate(("EachGem", 5), by_name),
                         dict(op="distinct", items=GEMS[:3], count=3))
        none = {n: type("Row", (), dict(item=row.item, requirement_ceiling=0)) for n, row in by_name.items()}
        self.assertIsNone(content_requirements.rule_predicate(("EachGem", 5), none))


class TestRouteHelper(unittest.TestCase):
    def test_nothing_changes_without_the_families(self):
        checks = [dict(location=1, owner="retail:0", kind="podium", routes=[dict(award="held_1st")])]
        self.assertEqual(content_race_routes.extend(checks, {}, [], [], [], {}, None, None, {}), [])
        self.assertEqual(len(checks[0]["routes"]), 1)


if __name__ == "__main__":
    unittest.main()
