"""Cups on content plans (#133 PR 5): counts, composition, laps, checks,
logic and the Universal Tracker restore."""
import copy
import json
import unittest

from Options import OptionError

from .. import content_cups, content_plan, cup_checks
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


if __name__ == "__main__":
    unittest.main()
