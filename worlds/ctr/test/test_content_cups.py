"""Cups on content plans (#133 PR 5): counts, composition, laps, checks,
logic and the Universal Tracker restore. With Hit Character on (#133 PR 5b),
each cup's frozen field comes from its own encounter order and every leg is
a Hit route."""
import copy
import json
import unittest

from Options import OptionError

from BaseClasses import CollectionState

from .. import content_cups, content_global_checks, content_plan, cup_checks, hit_character
from .test_content_plan import make_world, profile_options
from .test_custom_packages import UNKNOWN, named_fixture


def cup_options(seed=0):
    """A varied cup profile for the seed: counts, sources, repeats, laps,
    sweeps, boost, racer locks and custom tracks."""
    options = profile_options()
    pool = options["content_pool"]
    pool["tracks"]["modes"] = [["trophy"], ["trophy", "ctr", "relic"], ["ctr", "relic"]][seed % 3]
    pool["tracks"]["custom"] = [[copy.deepcopy(content_plan.PACKAGES[1])],
                                [copy.deepcopy(content_plan.PACKAGES[1]), named_fixture(), copy.deepcopy(UNKNOWN)],
                                []][seed % 3]
    pool["required_entries"] = []
    pool["tracks"]["cortex_vortex"] = seed % 4 == 1
    pool["cups"] = dict(count=dict(min=1, max=2 + seed % 6))
    if seed % 8 == 7:
        # Enough cups that some leg tracks get no standalone pad.
        pool["cups"]["count"] = dict(min=8, max=10)
    composition = {}
    if seed % 5 == 1:
        composition["repeats"] = dict(within_cup=True, across_cups=True)
    if seed % 5 == 2:
        composition["repeats"] = dict(within_cup=False, across_cups=False)
    if seed % 5 == 3:
        composition["repeats"] = dict(within_cup=True, across_cups=False)
    if seed % 7 == 4 and seed % 3 != 2:
        composition["sources"] = ["custom", "retail"]
        composition["custom_legs"] = dict(min=1, max=2)
    if seed % 8 == 7:
        composition.pop("repeats", None)  # eight or more cups need repeats across cups
    if composition:
        pool["cups"]["composition"] = composition
    pool["crystals"] = dict(count=dict(min=0, max=seed % 4))
    options["one_lap_cups"] = seed % 2 == 0
    options["cup_sweep_checks"] = seed % 4 in (1, 2) or seed % 8 == 7
    if seed % 4 == 2:
        options["progressive_boost"] = "shared_global"
        options["logic_difficulty"] = "hard"
    if seed % 6 == 5:
        options["logic_difficulty"] = "hard"
        options["podium_placement_checks"] = True
        options["progressive_boost"] = "per_character"
        options["character_unlocks"] = True
        options["racer_locked_pads"] = 4
    return options


def cups_of(plan):
    return [e for e in plan["entries"] if e["kind"] == "cup"]


class TestCupDraw(unittest.TestCase):
    def test_varied_profiles_generate_validate_and_restore(self):
        for seed in range(24):
            with self.subTest(seed=seed):
                options = cup_options(seed)
                world = make_world(options, seed=seed)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                cups = cups_of(plan)
                low, high = options["content_pool"]["cups"]["count"].values()
                self.assertTrue(low <= len(cups) <= high)
                self.assertIn(content_cups.FEATURE, plan["required_features"])
                self.assertEqual(plan["required_features"][-1], content_cups.FEATURE)
                tracks = {t["id"]: t for t in plan["tracks"]}
                names = [e["display_name"] for e in cups]
                self.assertEqual(len(set(names)), len(names))
                for cup in cups:
                    self.assertEqual(len(cup["legs"]), 4)
                    ids = [leg["track_id"] for leg in cup["legs"]]
                    within = options["content_pool"]["cups"].get("composition", {}).get("repeats", {}).get(
                        "within_cup", False)
                    if not within:
                        self.assertEqual(len(set(ids)), 4)
                    for leg in cup["legs"]:
                        full = tracks[leg["track_id"]]["laps"]
                        self.assertEqual(leg["laps"], max(1, full // 2) if options["one_lap_cups"] else full)
                checks = {c["kind"] for c in plan["checks"]}
                self.assertEqual("cup_sweep" in checks, options["cup_sweep_checks"])
                self.assertEqual(len(world.multiworld.get_locations(1)), len(plan["checks"]))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                restored = make_world({}, passthrough=wire)
                self.assertEqual(restored.ctr_content_plan, plan)
                self.assertEqual(bool(restored.options.cup_sweep_checks.value), options["cup_sweep_checks"])

    def test_no_cups_draws_nothing(self):
        plan = make_world(profile_options()).ctr_content_plan
        self.assertFalse(cups_of(plan))
        self.assertNotIn(content_cups.FEATURE, plan["required_features"])

    def test_across_cups_off_keeps_tracks_apart(self):
        options = cup_options(2)
        options["content_pool"]["cups"]["count"] = 4
        for seed in range(6):
            plan = make_world(options, seed=seed).ctr_content_plan
            legs = [leg["track_id"] for cup in cups_of(plan) for leg in cup["legs"]]
            self.assertEqual(len(legs), len(set(legs)))

    def test_custom_leg_range(self):
        options = cup_options(1)
        options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(content_plan.PACKAGES[1]), named_fixture()]
        options["content_pool"]["cups"] = dict(count=3, composition=dict(custom_legs=dict(min=1, max=2)))
        for seed in range(6):
            plan = make_world(options, seed=seed).ctr_content_plan
            tracks = {t["id"]: t for t in plan["tracks"]}
            for cup in cups_of(plan):
                custom = sum(tracks[leg["track_id"]]["origin"] != "retail" for leg in cup["legs"])
                self.assertTrue(1 <= custom <= 2)

    def test_retail_legs_are_race_tracks(self):
        options = cup_options(0)
        options["content_pool"]["cups"] = dict(count=3, composition=dict(sources=["retail"]))
        plan = make_world(options).ctr_content_plan
        for cup in cups_of(plan):
            for leg in cup["legs"]:
                self.assertRegex(leg["track_id"], r"^retail:(\d|1[0-5])$")

    def test_feasible_pairs(self):
        spec = dict(bounds=(25, 27), repeats=dict(content_cups.DEFAULT_REPEATS), custom_legs=(0, 4))
        other = [object()] * 16
        pairs = content_cups.feasible_pairs(spec, (1, 2), 4, 0, 0, other, [])
        self.assertEqual(pairs, [(25, 1), (25, 2), (26, 1)])

    def test_refusals(self):
        for name, change, text in [
                ("count missing", lambda o: o["content_pool"]["cups"].pop("count"), "cups.count is required"),
                ("count too high", lambda o: o["content_pool"]["cups"].__setitem__("count", 28), "cups.count"),
                ("bad source", lambda o: o["content_pool"]["cups"].__setitem__(
                    "composition", dict(sources=["trial"])), "sources"),
                ("no fit", lambda o: o["content_pool"]["cups"].__setitem__(
                    "composition", dict(repeats=dict(within_cup=False, across_cups=False))), "no cup and crystal"),
                ("custom legs without custom", lambda o: o["content_pool"]["cups"].__setitem__(
                    "composition", dict(sources=["retail"], custom_legs=dict(min=1, max=4))), "no cup and crystal")]:
            with self.subTest(name):
                options = cup_options(2)
                options["content_pool"]["cups"]["count"] = 5 if name == "no fit" else 1
                change(options)
                with self.assertRaisesRegex(OptionError, text):
                    make_world(options)


class TestCupChecks(unittest.TestCase):
    def test_win_codes_and_leg_victories(self):
        for seed in range(12):
            options = cup_options(seed)
            plan = make_world(options, seed=seed).ctr_content_plan
            trophy = {e["track_id"] for e in plan["entries"] if e["kind"] == "track" and "trophy" in e["modes"]}
            legs = {leg["track_id"] for cup in cups_of(plan) for leg in cup["legs"]}
            for cup in cups_of(plan):
                index = int(cup["id"].split(":")[1])
                win = next(c for c in plan["checks"] if c["location"] == 35027000 + index)
                self.assertEqual(win["display_name"], f"{cup_checks.CUP_NAMES[index]}: Win")
            victories = [c for c in plan["checks"] if c["kind"] == "cup_leg"]
            self.assertEqual({c["owner"] for c in victories}, legs - trophy)
            for check in victories:
                self.assertTrue(check["display_name"].endswith(": Cup Leg Victory"))
                self.assertEqual(len(check["routes"]), sum(leg["track_id"] == check["owner"]
                                                           for cup in cups_of(plan) for leg in cup["legs"]))

    def test_cup_win_needs_usf_for_a_usf_leg(self):
        options = cup_options(2)
        options["progressive_boost"] = "shared_global"
        options["logic_difficulty"] = "hard"
        options["content_pool"]["cups"] = dict(count=6, composition=dict(sources=["retail"]))
        found = False
        for seed in range(10):
            plan = make_world(options, seed=seed).ctr_content_plan
            for cup in cups_of(plan):
                win = next(c for c in plan["checks"] if c["kind"] == "cup" and c["routes"][0]["entry_id"] == cup["id"])
                usf = any(leg["track_id"] in ("retail:7", "retail:13") for leg in cup["legs"])  # Hot Air Skyway, Oxide Station
                if usf:
                    found = True
                    self.assertEqual(win.get("boost"), 2)
        self.assertTrue(found)

    def test_ordered_prefix_route_rank(self):
        record = dict(boost_mode=1, boost_blue_fire=False, stats_mode=0, logic_difficulty=2, shortcut_knowledge=0)
        tracks = {f"retail:{i}": dict(id=f"retail:{i}", origin="retail", retail_id=i,
                                      display_name=content_plan.RETAIL[i], laps=3) for i in (0, 7)}
        cup = dict(id="entry/cup:0", legs=[dict(id="entry/cup:0/leg:0", track_id="retail:7"),
                                           dict(id="entry/cup:0/leg:1", track_id="retail:0")])
        # Hot Air Skyway (7) first: its finish needs USF for every later leg too.
        self.assertEqual(content_cups.route_boost(cup, "entry/cup:0/leg:1", tracks, record), 2)
        cup["legs"].reverse()  # now Dingo Canyon (leg:1) races first
        self.assertEqual(content_cups.route_boost(cup, "entry/cup:0/leg:1", tracks, record), 0)


    def test_prefix_rank_stops_before_the_leg(self):
        # A Hit route on a leg (#133 PR 5b) needs every earlier leg's finish,
        # never the leg's own win.
        record = dict(boost_mode=1, boost_blue_fire=False, stats_mode=0, logic_difficulty=2, shortcut_knowledge=0)
        tracks = {f"retail:{i}": dict(id=f"retail:{i}", origin="retail", retail_id=i,
                                      display_name=content_plan.RETAIL[i], laps=3) for i in (0, 7)}
        cup = dict(id="entry/cup:0", legs=[dict(id="entry/cup:0/leg:0", track_id="retail:0"),
                                           dict(id="entry/cup:0/leg:1", track_id="retail:7"),
                                           dict(id="entry/cup:0/leg:2", track_id="retail:0")])
        self.assertEqual(content_cups.prefix_boost(cup, "entry/cup:0/leg:0", tracks, record), 0)
        self.assertEqual(content_cups.prefix_boost(cup, "entry/cup:0/leg:1", tracks, record), 0)
        self.assertEqual(content_cups.prefix_boost(cup, "entry/cup:0/leg:2", tracks, record), 2)
        self.assertEqual(content_cups.prefix_boost(cup, "entry/cup:0/leg:2", tracks, None), 0)


def hit_cup_options(seed=0, **extra):
    options = cup_options(seed)
    options.update(hit_character=True, itemsanity=False)
    options.update(extra)
    return options


class TestCupHitCharacter(unittest.TestCase):
    def test_orders_routes_and_restore(self):
        seen_custom_leg = False
        for seed in range(16):
            with self.subTest(seed=seed):
                try:
                    world = make_world(hit_cup_options(seed), seed=seed)
                except OptionError as exc:
                    self.assertIn("at the start", str(exc))
                    continue
                plan = world.ctr_content_plan
                wire = json.loads(json.dumps(world.fill_slot_data()))
                block = wire["hit_character_encounters"]
                indices = sorted(int(e["id"].split(":")[1]) for e in cups_of(plan))
                self.assertEqual(sorted(map(int, block["content_cups"])), indices)
                seed32 = block["policy"]["seed"]
                for index in indices:
                    self.assertEqual(block["content_cups"][str(index)]["order"],
                                     hit_character.destination_order(seed32, 200 + index))
                tracks = {t["id"]: t for t in plan["tracks"]}
                pad_of = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
                expected_legs = sorted(
                    ((int(pad_of[c["id"]].split(":")[1]), n), (c["id"], leg["id"]))
                    for c in cups_of(plan) for n, leg in enumerate(c["legs"]))
                hits = [c for c in plan["checks"] if c["kind"] == "hit"]
                self.assertEqual(len(hits), 16)
                for check in hits:
                    # Every target the same routes, guests included.
                    self.assertEqual(check["routes"], hits[0]["routes"])
                    legs = [(r["entry_id"], r["leg_id"]) for r in check["routes"] if r["mode"] == "cup"]
                    self.assertEqual(legs, [x for _k, x in expected_legs])
                seen_custom_leg |= any(tracks[leg["track_id"]]["origin"] != "retail"
                                       for c in cups_of(plan) for leg in c["legs"])
                restored = make_world({}, passthrough=copy.deepcopy(wire))
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
        self.assertTrue(seen_custom_leg)

    def test_hit_off_keeps_the_cup_wire(self):
        world = make_world(cup_options(3), seed=3)
        self.assertNotIn("hit_character_encounters", world.fill_slot_data())
        self.assertFalse(any(c["kind"] == "hit" for c in world.ctr_content_plan["checks"]))

    def test_a_cup_alone_routes_every_hit(self):
        # Standalone tracks hold relic races only, so the cup is the only race.
        options = hit_cup_options(0)
        pool = options["content_pool"]
        pool["tracks"]["modes"] = ["relic"]
        pool["tracks"]["custom"] = []
        pool["tracks"]["retail"] = [0, 1, 2, 3, 4, 5]
        pool["cups"] = dict(count=1, composition=dict(sources=["retail"]))
        pool["crystals"] = dict(count=0)
        options["progressive_boost"] = "off"
        world = None
        for seed in range(20):
            try:
                world = make_world(options, seed=seed)
                break
            except OptionError as exc:
                self.assertIn("at the start", str(exc))
        plan = world.ctr_content_plan
        cup = cups_of(plan)[0]
        crash = world.multiworld.get_location("Hit Crash Bandicoot", 1)
        self.assertEqual([r["mode"] for r in next(c for c in plan["checks"] if c["kind"] == "hit")["routes"]],
                         ["cup"] * 4)
        state = CollectionState(world.multiworld)
        self.assertEqual(crash.can_reach(state), state.can_reach(cup["id"], "Region", 1))
        everything = CollectionState(world.multiworld)
        for item in world.multiworld.itempool:
            everything.collect(item, prevent_sweep=True)
        self.assertTrue(crash.can_reach(everything))

    def test_leg_boost_binds_to_the_drawn_against_racer(self):
        # Per-character boost: only Crash can finish the first leg, and the
        # field never seats the player, so Hit Crash has no racer that both
        # reaches the second leg and can be drawn against him.
        from types import SimpleNamespace as NS
        from .. import progressive_capability as pc

        class State:
            boosted = "Crash Bandicoot"

            def can_reach(self, *args):
                return True

            def has(self, *args):
                return False

            def count(self, name, player):
                return 2 if name == pc.BOOST_NAME_BY_CHARACTER[self.boosted] else 0

        cup = dict(id="entry/cup:0", legs=[dict(id="leg:0", track_id="first"), dict(id="leg:1", track_id="second")])
        plan = dict(global_checks=dict(hit_character=True), pads=[dict(id="pad:0", racer_lock=None)], entries=[cup],
                    tracks=[dict(id="first", origin="custom", package_id="p"),
                            dict(id="second", origin="retail", display_name="Crash Cove")],
                    packages=[dict(id="p", content_id="probe", capabilities=dict(weapon_crates=0, super_turbo_pads=True))],
                    capability=dict(boost_mode=2, shortcut_knowledge=0))
        world = NS(player=1, ctr_content_plan=plan, ctr_starting_character="Coco Bandicoot",
                   ctr_hit_character_fallback={},
                   options=NS(progressive_boost=NS(value=2), progressive_stats=NS(value=0),
                              character_unlocks=NS(value=0)))
        route = dict(own_pad_id="pad:0", entry_id="entry/cup:0", leg_id="leg:1", mode="cup")
        self.assertEqual(content_cups.prefix_boost(cup, "leg:1", {t["id"]: t for t in plan["tracks"]},
                                                   plan["capability"], {"p": plan["packages"][0]}), 2)
        for target, expected in ((35025000, False), (35025001, True)):  # Crash, then Cortex
            location = NS(access_rule=None)
            content_global_checks.install(world, dict(location=target, kind="hit"), location,
                                          [("entry/cup:0", None, route)])
            self.assertIs(location.access_rule(State()), expected, target)

    def test_forged_cup_orders_refuse(self):
        world = None
        for seed in range(10):
            try:
                world = make_world(hit_cup_options(1), seed=seed)
                break
            except OptionError:
                continue
        wire = json.loads(json.dumps(world.fill_slot_data()))
        plan = wire["content_plan"]
        block = wire["hit_character_encounters"]
        index = next(iter(block["content_cups"]))

        def drop_all(b):
            b.pop("content_cups")

        def extra_cup(b):
            b["content_cups"]["26" if index != "26" else "25"] = copy.deepcopy(b["content_cups"][index])

        def short_order(b):
            b["content_cups"][index]["order"].pop()

        def drop_leg_route(p):
            check = next(c for c in p["checks"] if c["location"] == 35025009)
            check["routes"] = [r for r in check["routes"] if r["mode"] != "cup"]

        for change in (drop_all, extra_cup, short_order):
            bad = copy.deepcopy(wire)
            change(bad["hit_character_encounters"])
            with self.assertRaises(OptionError):
                content_global_checks.check_encounter_block(bad["content_plan"], bad)
            with self.assertRaises(OptionError):
                make_world({}, passthrough=bad)
        forged = copy.deepcopy(plan)
        drop_leg_route(forged)
        with self.assertRaises(OptionError):
            content_plan.validate(forged)
        # A normal room never carries the key.
        normal = hit_character.build_encounters(5)
        normal["content_cups"] = copy.deepcopy(block["content_cups"])
        with self.assertRaises(OptionError):
            hit_character._validate_block(normal)


if __name__ == "__main__":
    unittest.main()
