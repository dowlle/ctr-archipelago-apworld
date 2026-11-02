"""One generator row 10i: parity fixes from the design audit.

Reach 10 Wumpa from cup legs and boss races, podium rungs from cup legs, vanilla
garages that open free without Trophies, and Turbo Track's five Gems of five
colours (content_race_routes, content_bosses, content_requirements)."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive

from .test_content_plan import make_world
from .test_content_plan_row3 import options as shape_options, records
from .. import content_bosses, content_capability, content_plan, content_race_routes, content_requirements

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


def cup_only(**extra):
    # Eight cups leave some tracks raced only as Gem Cup legs.
    return per_track(wumpa_check="off", cup_only_podium_rungs=True, **extra)


def gem_cup_legs(plan):
    """{track id: [(entry id, leg id)]} of every leg of a cup on a pad."""
    pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
    legs = {}
    for entry in plan["entries"]:
        if entry["kind"] == "cup" and entry["id"] in pads:
            for leg in entry["legs"]:
                legs.setdefault(leg["track_id"], []).append((entry["id"], leg["id"]))
    return legs


class TestCupOnlyRungs(unittest.TestCase):
    """cup_only_podium_rungs (ruling of 2026-11-02): a track raced only as a Gem
    Cup leg gets the rungs podium_rungs lists, earned in its cup legs only."""

    @classmethod
    def setUpClass(cls):
        cls.world = make_world(cup_only(), seed=1)
        cls.plan = cls.world.ctr_content_plan

    def test_a_cup_only_track_has_the_rungs_of_a_pad_track(self):
        plan = self.plan
        own = standalone_tracks(plan)
        legs = gem_cup_legs(plan)
        tracks = {t["id"]: t for t in plan["tracks"]}
        keys = plan["track_checks"]["podium_rungs"]
        rungs = {}
        for check in plan["checks"]:
            if check["kind"] == "podium":
                rungs.setdefault(check["owner"], []).append(check)
        cup_only_tracks = set(legs) - set(own)
        self.assertTrue(cup_only_tracks)
        self.assertEqual(set(rungs), set(own) | cup_only_tracks)
        for track_id in cup_only_tracks:
            track = tracks[track_id]
            self.assertEqual([c["location"] for c in rungs[track_id]],
                             [content_plan.track_location(track, key, content_plan.RUNG_SUFFIX[key])[1] for key in keys])
            for key, check in zip(keys, rungs[track_id]):
                self.assertEqual(check["display_name"],
                                 f"{content_plan.room_title(track)}: {content_plan.RUNG_SUFFIX[key]}")
                self.assertEqual([(r["entry_id"], r["leg_id"]) for r in check["routes"]], legs[track_id])
                self.assertTrue(all(r["mode"] == "cup" and r["award"] == key and r["encounter_id"] is None
                                    for r in check["routes"]))
        self.assertTrue(content_race_routes.cup_only_on(plan["checks"]))
        self.assertTrue(content_plan.validate(plan))

    def test_no_new_location_id(self):
        # Every rung code of every track kind exists in the datapackage.
        for track in self.plan["tracks"]:
            if "arena_id" in track:
                continue
            for key in content_plan.RUNG_SUFFIX:
                name, code = content_plan.track_location(track, key, content_plan.RUNG_SUFFIX[key])
                self.assertEqual(content_plan.LOCATION_BY_CODE[code], name)

    def test_off_and_empty_rungs_add_nothing(self):
        off = make_world(per_track(wumpa_check="off"), seed=1).ctr_content_plan
        own = standalone_tracks(off)
        self.assertFalse({c["owner"] for c in off["checks"] if c["kind"] == "podium"} - set(own))
        self.assertFalse(content_race_routes.cup_only_on(off["checks"]))
        empty_on = make_world(cup_only(podium_rungs=[]), seed=1).ctr_content_plan
        empty_off = make_world(per_track(wumpa_check="off", podium_rungs=[]), seed=1).ctr_content_plan
        self.assertEqual(json.dumps(empty_on, sort_keys=True), json.dumps(empty_off, sort_keys=True))

    def test_the_seed_fills_with_every_location_reachable(self):
        for options in (cup_only(), cup_only(progressive_boost="shared_global")):
            world = make_world(options, seed=2)
            mw = world.multiworld
            distribute_items_restrictive(mw)
            self.assertTrue(mw.can_beat_game())
            state = CollectionState(mw)
            state.sweep_for_advancements()
            self.assertTrue(all(loc.can_reach(state) for loc in mw.get_locations(1)))

    def test_a_rung_keeps_the_boost_rank_of_a_trophy_race_rung(self):
        plan = make_world(cup_only(progressive_boost="shared_global"), seed=1).ctr_content_plan
        own = standalone_tracks(plan)
        tracks = {t["id"]: t for t in plan["tracks"]}
        rungs = [c for c in plan["checks"] if c["kind"] == "podium" and c["owner"] not in own]
        self.assertTrue(rungs)
        for check in rungs:
            need = content_capability.check_boost(tracks[check["owner"]], "podium", check["routes"][0]["award"],
                                                  plan["capability"])
            self.assertEqual(check.get("boost", 0), need)
        self.assertTrue(any("boost" in c for c in rungs))
        self.assertTrue(content_plan.validate(plan))

    def test_forged_rungs_are_refused(self):
        own = standalone_tracks(self.plan)
        extra = [c for c in self.plan["checks"] if c["kind"] == "podium" and c["owner"] not in own]
        # One cup-only track without its rungs while another keeps them.
        plan = copy.deepcopy(self.plan)
        plan["checks"] = [c for c in plan["checks"] if c["location"] != extra[0]["location"]]
        with self.assertRaises(Exception):
            content_plan.validate(plan)
        # A rung earned in a boss race or with a leg dropped.
        plan = copy.deepcopy(self.plan)
        check = next(c for c in plan["checks"] if c["location"] == extra[0]["location"])
        check["routes"] = check["routes"][1:] or [dict(check["routes"][0], mode="boss_cup")]
        with self.assertRaises(Exception):
            content_plan.validate(plan)

    def test_tracker_restores_the_option_from_the_plan(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, self.plan)
        self.assertEqual(other.options.cup_only_podium_rungs.value, 1)
        self.assertEqual(other.fill_slot_data(), wire)


#: Four retail tracks whose pads offer no Trophy Race; each is a Gem Cup leg.
NO_TROPHY = {"Crash Cove": ["relic"], "Roo's Tubes": ["relic"], "Mystery Caves": ["relic"],
             "Sewer Speedway": ["relic"]}


def pad_no_trophy(on=True, **extra):
    modes = dict(default=["trophy", "ctr", "relic"], **NO_TROPHY)
    return per_track(wumpa_check="off", cup_only_podium_rungs=on, track_modes=modes, **extra)


class TestPadTracksWithoutTrophyRace(unittest.TestCase):
    """cup_only_podium_rungs (ruling of 2026-11-02): a track with its own
    pad but no Trophy Race, raced in a cup, gets the rungs podium_rungs lists
    too, earned in its cup legs only."""

    @classmethod
    def setUpClass(cls):
        cls.world = make_world(pad_no_trophy(), seed=1)
        cls.plan = cls.world.ctr_content_plan
        own = standalone_tracks(cls.plan)
        legs = gem_cup_legs(cls.plan)
        cls.tracks = [t for t, e in own.items() if "trophy" not in e["modes"] and t in legs]

    def test_a_pad_track_without_a_trophy_race_has_cup_rungs(self):
        plan = self.plan
        self.assertGreaterEqual(len(self.tracks), 2)
        legs = gem_cup_legs(plan)
        tracks = {t["id"]: t for t in plan["tracks"]}
        keys = plan["track_checks"]["podium_rungs"]
        rungs = {}
        for check in plan["checks"]:
            if check["kind"] == "podium":
                rungs.setdefault(check["owner"], []).append(check)
        self.assertTrue(any(len(legs[t]) > 1 for t in self.tracks))
        for track_id in self.tracks:
            track = tracks[track_id]
            self.assertEqual([c["location"] for c in rungs[track_id]],
                             [content_plan.track_location(track, key, content_plan.RUNG_SUFFIX[key])[1] for key in keys])
            for key, check in zip(keys, rungs[track_id]):
                self.assertEqual([(r["entry_id"], r["leg_id"]) for r in check["routes"]], legs[track_id])
                self.assertTrue(all(r["mode"] == "cup" and r["award"] == key and r["encounter_id"] is None
                                    for r in check["routes"]))
        self.assertTrue(content_race_routes.cup_only_on(plan["checks"]))
        self.assertTrue(content_plan.validate(plan))

    def test_off_gives_them_no_rungs(self):
        off = make_world(pad_no_trophy(on=False), seed=1).ctr_content_plan
        owners = {c["owner"] for c in off["checks"] if c["kind"] == "podium"}
        self.assertFalse(owners & set(self.tracks))
        self.assertFalse(content_race_routes.cup_only_on(off["checks"]))
        empty_on = make_world(pad_no_trophy(podium_rungs=[]), seed=1).ctr_content_plan
        empty_off = make_world(pad_no_trophy(on=False, podium_rungs=[]), seed=1).ctr_content_plan
        self.assertEqual(json.dumps(empty_on, sort_keys=True), json.dumps(empty_off, sort_keys=True))

    def test_the_seed_fills_with_every_location_reachable(self):
        world = make_world(pad_no_trophy(), seed=2)
        mw = world.multiworld
        distribute_items_restrictive(mw)
        self.assertTrue(mw.can_beat_game())
        state = CollectionState(mw)
        state.sweep_for_advancements()
        self.assertTrue(all(loc.can_reach(state) for loc in mw.get_locations(1)))

    def test_partial_or_forged_sets_are_refused(self):
        # One pad track's rung set dropped while the others keep theirs.
        plan = copy.deepcopy(self.plan)
        gone = {c["location"] for c in plan["checks"] if c["kind"] == "podium" and c["owner"] == self.tracks[0]}
        plan["checks"] = [c for c in plan["checks"] if c["location"] not in gone]
        with self.assertRaises(Exception):
            content_plan.validate(plan)
        # A rung of such a track routed from its own pad, or from a boss cup.
        for forge in (lambda r, pad: dict(r, mode="trophy", leg_id=None, entry_id="entry/" + self.tracks[0],
                                          own_pad_id=pad),
                      lambda r, pad: dict(r, mode="boss_cup")):
            plan = copy.deepcopy(self.plan)
            pad = next(p["id"] for p in plan["pads"] if p["entry_id"] == "entry/" + self.tracks[0])
            check = next(c for c in plan["checks"] if c["kind"] == "podium" and c["owner"] == self.tracks[0])
            check["routes"] = [forge(check["routes"][0], pad)] + check["routes"][1:]
            with self.assertRaises(Exception):
                content_plan.validate(plan)

    def test_tracker_restores_the_option_from_the_plan(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, self.plan)
        self.assertEqual(other.options.cup_only_podium_rungs.value, 1)
        self.assertEqual(other.fill_slot_data(), wire)


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


    def test_the_start_check_asks_the_colours_that_exist(self):
        rule = content_requirements.vanilla_rule(TURBO_TRACK)
        held = {"Red Gem": 1, "Green Gem": 1, "Blue Gem": 1}
        base = {"Red Gem": 1, "Green Gem": 1, "Blue Gem": 1, "Yellow Gem": 0, "Purple Gem": 0}
        self.assertTrue(content_plan.rule_met(rule, held, base))
        self.assertFalse(content_plan.rule_met(rule, held))
        self.assertFalse(content_plan.rule_met(rule, {"Red Gem": 5}, base))


class TestRouteHelper(unittest.TestCase):
    def test_nothing_changes_without_the_families(self):
        checks = [dict(location=1, owner="retail:0", kind="podium", routes=[dict(award="held_1st")])]
        self.assertEqual(content_race_routes.extend(checks, {}, [], [], [], {}, None, None, {}), [])
        self.assertEqual(len(checks[0]["routes"]), 1)


if __name__ == "__main__":
    unittest.main()
