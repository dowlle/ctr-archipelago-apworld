"""Track modes, stages and mode orders in content plans (#133 PR 3).

Retail tracks run Trophy, CTR Challenge and Relic Race; a custom package runs
the modes its measured capabilities allow. With two stages the first mode of a
pad uses the entrance requirement and the others share one drawn second-stage
requirement. No mode needs a win in another one. The paired native parser
applies the same rules (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from worlds.AutoWorld import call_all

from .. import content_plan, named_tracks, sphere0_guard
from .test_content_plan import make_world, profile_options
from .test_custom_packages import UNKNOWN, named_fixture

CTR_PACKAGE = "custom/baby-t-park/1.0.2"


def mode_pool():
    """Base items in every counted family, so second-stage draws vary. Relic
    Time Trial checks follow these counts, so every Relic Race of the full
    profiles keeps all three tiers."""
    return {"base": {"trophies": 6, "relics": {"sapphire": 18, "gold": 18, "platinum": 18},
                     "tokens": {"red": 2, "green": 2, "blue": 1, "yellow": 0, "purple": 0},
                     "gems": ["red", "green", "blue", "yellow", "purple"], "keys": 4}}


def relic_only():
    """A test package with time crates and a lap graph but no AI grid."""
    d = copy.deepcopy(UNKNOWN)
    d.update(id="package/relic-loop/1", content_id="relic-loop", revision="1",
             uuid="1e0e0d0c-0b0a-4908-8706-050403020100", display_name="Relic Loop")
    d["capabilities"].update(arcade=False, ctr_tokens=False)
    d["files"] = [dict(f, sha256=h * 32) for f, h in zip(d["files"], ("e5", "f6"))]
    return d


def mode_options(modes=("trophy", "ctr", "relic"), stages="two", order="fixed", custom=None, overrides=None):
    options = profile_options()
    tracks = options["content_pool"]["tracks"]
    tracks["modes"] = list(modes)
    if custom is not None:
        tracks["custom"] = custom
        options["content_pool"]["required_entries"] = [
            f"custom/{d['content_id']}/{d['revision']}" for d in custom]
    if overrides is not None:
        tracks["overrides"] = overrides
    options["pad_layout"] = dict(placement="shuffle", stages=stages, mode_order=order, merge_trophy_ctr=False)
    options["item_pool"] = mode_pool()
    return options


def entry_of(plan, track_id):
    return next(e for e in plan["entries"] if e.get("track_id") == track_id)


def pad_of(plan, entry):
    return next(p for p in plan["pads"] if p["entry_id"] == entry["id"])


class TestModesByCapability(unittest.TestCase):
    def test_retail_tracks_run_all_three_modes(self):
        plan = make_world(mode_options(custom=[])).ctr_content_plan
        for track in plan["tracks"]:
            self.assertEqual(track["modes"], ["trophy", "ctr", "relic"])
            self.assertEqual(track["capabilities"], track["modes"])
        self.assertEqual(len(plan["checks"]), 18 * 5)
        self.assertIn(content_plan.MODE_FEATURE, plan["required_features"])

    def test_custom_modes_follow_measured_capabilities(self):
        ctr_capable = copy.deepcopy(content_plan.PACKAGES[1])  # arcade + letters, no relic
        plan = make_world(mode_options(custom=[ctr_capable, copy.deepcopy(UNKNOWN), relic_only()])).ctr_content_plan
        modes = {t["id"]: t["modes"] for t in plan["tracks"] if t["origin"] == "custom"}
        self.assertEqual(modes, {CTR_PACKAGE: ["trophy", "ctr"],
                                 "custom/fixture-loop/2.1": ["trophy", "relic"],
                                 "custom/relic-loop/1": ["relic"]})

    def test_relic_needs_a_lap_graph(self):
        d = relic_only()
        d["capabilities"]["time_trial"] = False
        with self.assertRaisesRegex(OptionError, "can run none of the races"):
            make_world(mode_options(custom=[d]))

    def test_global_modes_filter_and_overrides_narrow(self):
        options = mode_options(modes=["trophy", "relic"], custom=[], overrides={"retail:3": ["relic"]})
        options["item_pool"]["base"]["trophies"] = 0
        plan = make_world(options).ctr_content_plan
        by_id = {t["id"]: t["modes"] for t in plan["tracks"]}
        self.assertEqual(by_id.get("retail:3", ["relic"]), ["relic"])
        self.assertTrue(all(m == ["trophy", "relic"] for i, m in by_id.items() if i != "retail:3"))
        self.assertFalse(any(c["kind"] == "ctr" for c in plan["checks"]))

    def test_override_refusals(self):
        cases = [({"nowhere": ["relic"]}, ["relic"], "not a track of this seed"),
                 ({"fixture-loop": ["ctr"]}, ["trophy", "ctr", "relic"], "ctr without trophy"),
                 ({"retail:3": []}, ["relic"], "nonempty list")]
        for overrides, modes, message in cases:
            with self.subTest(overrides=overrides), self.assertRaisesRegex(OptionError, message):
                make_world(mode_options(modes=modes, custom=[copy.deepcopy(UNKNOWN)], overrides=overrides))

    def test_modes_list_is_checked(self):
        for modes in ([], ["trophy", "trophy"], ["merged"], "trophy"):
            options = mode_options()
            options["content_pool"]["tracks"]["modes"] = modes
            with self.subTest(modes=modes), self.assertRaisesRegex(OptionError, "track_modes"):
                make_world(options)


class TestCheckIdentities(unittest.TestCase):
    def test_retail_tracks_keep_their_frozen_codes(self):
        plan = make_world(mode_options(custom=[])).ctr_content_plan
        codes = {c["display_name"]: c["location"] for c in plan["checks"]}
        self.assertEqual(codes["Crash Cove: CTR Token Challenge"], 35012300)
        self.assertEqual(codes["Crash Cove: Sapphire Time Trial"], 35012000)
        self.assertEqual(codes["Crash Cove: Gold Time Trial"], 35012100)
        self.assertEqual(codes["Crash Cove: Platinum Time Trial"], 35012200)
        self.assertEqual(codes["Slide Coliseum: CTR Token Challenge"], 35016210)
        self.assertEqual(codes["Turbo Track: Platinum Time Trial"], 35012217)
        for check in plan["checks"]:
            self.assertEqual(content_plan.CTR_LOCATION_IDS[check["display_name"]], check["location"])

    def test_named_and_generic_custom_codes(self):
        named = named_fixture()
        named["capabilities"].update(ctr_tokens=True, relic=True)
        named["relic_targets"] = dict(sapphire=90000, gold=80000, platinum=70000)
        plan = make_world(mode_options(custom=[named, copy.deepcopy(UNKNOWN)])).ctr_content_plan
        tv = named_tracks.location_code(78, "trophy")
        by_name = {c["display_name"]: c for c in plan["checks"]}
        self.assertEqual(by_name["TV World: CTR Token Challenge"]["location"], tv + 9)
        self.assertEqual([by_name[f"TV World: {t} Time Trial"]["location"] for t in content_plan.RELIC_TIERS],
                         [tv + 6, tv + 7, tv + 8])
        # The B+ track is Custom Track 1 (sorted package ids).
        self.assertEqual([by_name[f"Fixture Loop: {t} Time Trial"]["location"] for t in content_plan.RELIC_TIERS],
                         [35022000, 35022001, 35022002])
        self.assertEqual(by_name["Fixture Loop: Trophy Race"]["location"], 35016300)
        self.assertEqual(by_name["Fixture Loop: Gold Time Trial"]["routes"][0]["award"], "gold")
        self.assertEqual(by_name["TV World: CTR Token Challenge"]["routes"][0]["award"], "win_letters")

    def test_generic_ctr_code(self):
        d = copy.deepcopy(UNKNOWN)
        d["capabilities"]["ctr_tokens"] = True
        plan = make_world(mode_options(custom=[d])).ctr_content_plan
        check = next(c for c in plan["checks"] if c["display_name"] == "Fixture Loop: CTR Token Challenge")
        self.assertEqual(check["location"], 35023000)


class TestStagesAndOrders(unittest.TestCase):
    def test_two_stages_draw_one_gate_per_multi_mode_pad(self):
        for seed in range(12):
            plan = make_world(mode_options(custom=[copy.deepcopy(UNKNOWN), relic_only()]), seed=seed).ctr_content_plan
            records = {r["id"]: r["predicate"] for r in plan["requirements"]}
            rows = {r["item"]: r for r in plan["items"]["rows"]}
            for pad in plan["pads"]:
                gates = pad["mode_gates"]
                if not gates or gates[0]["mode"] == "crystal":
                    continue
                self.assertEqual(gates[0]["stage"], 1)
                stage2 = f"stage2:{pad['id'].split(':')[1]}"
                if len(gates) == 1:
                    self.assertNotIn(stage2, records)
                    continue
                if stage2 not in records:  # nothing held could back one
                    self.assertTrue(all(g["stage"] == 1 for g in gates))
                    continue
                self.assertTrue(all(g["stage"] == 2 and g["requirement_id"] == stage2 for g in gates[1:]))
                predicate = records[stage2]
                items = predicate.get("items", [predicate.get("item")])
                supply = sum(rows[i]["requirement_ceiling"] for i in items)
                ceiling = 4 if 35010014 not in items else supply
                self.assertTrue(1 <= predicate["count"] <= min(ceiling, supply))

    def test_single_stage_uses_the_entrance_gate_for_every_mode(self):
        plan = make_world(mode_options(stages="single")).ctr_content_plan
        self.assertFalse(any(r["id"].startswith("stage2:") for r in plan["requirements"]))
        for pad in plan["pads"]:
            first = {g["requirement_id"] for g in pad["mode_gates"]}
            self.assertLessEqual(len(first), 1)
            self.assertTrue(all(g["stage"] == 1 for g in pad["mode_gates"]))

    def test_fixed_order_puts_trophy_first(self):
        plan = make_world(mode_options()).ctr_content_plan
        for entry in plan["entries"]:
            self.assertEqual(entry["modes"], [m for m in content_plan.MODES if m in entry["modes"]])

    def test_per_seed_order_is_shared_and_per_pad_order_varies(self):
        orders = set()
        for seed in range(6):
            plan = make_world(mode_options(order="per_seed"), seed=seed).ctr_content_plan
            seen = {tuple(e["modes"]) for e in plan["entries"] if len(e.get("modes", ())) == 3}
            self.assertEqual(len(seen), 1)
            orders |= seen
        self.assertGreater(len(orders), 1)
        plan = make_world(mode_options(order="per_pad"), seed=3).ctr_content_plan
        self.assertGreater(len({tuple(e["modes"]) for e in plan["entries"]}), 1)
        for entry in plan["entries"]:
            self.assertEqual(pad_of(plan, entry)["mode_gates"][0]["mode"], entry["modes"][0])

    def test_trophy_only_plan_keeps_its_earlier_wire(self):
        plan = make_world(profile_options()).ctr_content_plan
        self.assertNotIn(content_plan.MODE_FEATURE, plan["required_features"])
        self.assertTrue(all(e["modes"] == ["trophy"] for e in plan["entries"] if e["kind"] == "track"))
        self.assertTrue(all(t["capabilities"] == ["trophy"] for t in plan["tracks"]))

    def test_a_later_mode_needs_its_gate_and_the_first_race_won(self):
        tested = 0
        for seed in range(6):
            tested += self.later_modes_of(seed)
        self.assertGreater(tested, 0)

    def later_modes_of(self, seed):
        world = make_world(mode_options(order="per_pad"), seed=seed)
        plan = world.ctr_content_plan
        mw = world.multiworld
        records = {r["id"]: r["predicate"] for r in plan["requirements"]}
        names = {c["location"]: content_plan.LOCATION_BY_CODE[c["location"]] for c in plan["checks"]}
        tested = 0
        for entry in plan["entries"]:
            pad = pad_of(plan, entry)
            if (pad["entrance_req"] != "free" or len(entry["modes"]) < 2 or pad["mode_gates"][0]["requirement_id"] != "free"
                    or f"stage2:{pad['id'].split(':')[1]}" not in records):
                continue
            predicate = records[f"stage2:{pad['id'].split(':')[1]}"]
            first = [c for c in plan["checks"] if c["routes"][0]["entry_id"] == entry["id"]
                     and c["routes"][0]["mode"] == entry["modes"][0]]
            later = [c for c in plan["checks"] if c["routes"][0]["entry_id"] == entry["id"]
                     and c["routes"][0]["mode"] != entry["modes"][0]]
            empty = CollectionState(mw)
            for check in first:
                self.assertTrue(mw.get_location(names[check["location"]], 1).can_reach(empty))
            for check in later:
                self.assertFalse(mw.get_location(names[check["location"]], 1).can_reach(empty))
            held = CollectionState(mw)
            items = predicate.get("items", [predicate.get("item")])
            for _ in range(predicate["count"]):
                for item in items:
                    held.collect(world.create_item(content_plan.ITEM_BY_CODE[item]), True)
            for check in later:
                self.assertTrue(mw.get_location(names[check["location"]], 1).can_reach(held))
            # The items alone are not enough: without a first race won, nothing.
            wins = [mw.get_location(names[check["location"]], 1) for check in first if check["kind"] == entry["modes"][0]]
            if wins:
                for win in wins:
                    win.access_rule = lambda state: False
                for check in later:
                    self.assertFalse(mw.get_location(names[check["location"]], 1).can_reach(held))
            tested += 1
        return tested


class TestTrackerAndForgery(unittest.TestCase):
    def test_tracker_restores_every_order_without_reroll(self):
        from NetUtils import convert_to_base_types
        for order in ("fixed", "per_seed", "per_pad"):
            for stages in ("single", "two"):
                world = make_world(mode_options(order=order, stages=stages,
                                                custom=[copy.deepcopy(UNKNOWN), relic_only()]), seed=11)
                wire = json.loads(json.dumps(world.fill_slot_data()))
                with self.subTest(order=order, stages=stages):
                    tracker = make_world({}, seed=999, passthrough=convert_to_base_types(wire))
                    self.assertEqual(tracker.ctr_content_plan, world.ctr_content_plan)
                    self.assertEqual(tracker.fill_slot_data(), wire)

    def test_forged_modes_and_gates_are_refused(self):
        wire = make_world(mode_options(custom=[copy.deepcopy(UNKNOWN), relic_only()]), seed=4).fill_slot_data()

        def multi_pad(p):
            return next(x for x in p["pads"] if len(x["mode_gates"]) == 3)

        def stage2_of(p, pad):
            return next(r for r in p["requirements"] if r["id"] == pad["mode_gates"][1]["requirement_id"])

        def custom_track(p, key):
            return next(t for t in p["tracks"] if t["id"].startswith(f"custom/{key}/"))

        def claim_ctr(p):
            t = custom_track(p, "fixture-loop")
            t["modes"] = t["capabilities"] = ["trophy", "ctr", "relic"]
            entry = entry_of(p, t["id"])
            entry["modes"] = ["trophy", "ctr", "relic"]
            pad = pad_of(p, entry)
            pad["mode_gates"].insert(1, dict(mode="ctr", stage=2, requirement_id=pad["mode_gates"][1]["requirement_id"]))
            p["checks"].append(dict(location=35023000, owner=t["id"], kind="ctr",
                                    display_name="Fixture Loop: CTR Token Challenge",
                                    routes=[dict(entry_id=entry["id"], mode="ctr", leg_id=None, encounter_id=None,
                                                 own_pad_id=pad["id"], award="win_letters")]))
            p["items"]["coded_checks"] += 1
            p["items"]["filler_count"] += 1

        mutations = {
            "stage two gate as stage one": lambda p: multi_pad(p)["mode_gates"][1].__setitem__("stage", 1),
            "later gate on the entrance record": lambda p: multi_pad(p)["mode_gates"][2].__setitem__("requirement_id", "free"),
            "stage two record dropped": lambda p: p["requirements"].remove(stage2_of(p, multi_pad(p))),
            "stage two count above supply": lambda p: stage2_of(p, multi_pad(p))["predicate"].__setitem__("count", 99),
            "stage two record on an empty pad": lambda p: p["requirements"].append(
                dict(id="stage2:" + next(x for x in p["pads"] if x["entry_id"] is None and x["kind"] == "normal")["id"].split(":")[1],
                     predicate=dict(op="count", item=35010000, count=1))),
            "entry mode missing": lambda p: next(e for e in p["entries"] if len(e["modes"]) == 3)["modes"].pop(),
            "track modes out of order": lambda p: next(t for t in p["tracks"] if t["origin"] == "retail").__setitem__(
                "modes", ["ctr", "trophy", "relic"]),
            "capabilities differ from modes": lambda p: next(t for t in p["tracks"] if t["origin"] == "retail").__setitem__(
                "capabilities", ["trophy"]),
            "custom claims a mode its package lacks": claim_ctr,
            "feature dropped": lambda p: p["required_features"].remove(content_plan.MODE_FEATURE),
            "relic award swapped": lambda p: next(c for c in p["checks"] if c["kind"] == "relic")["routes"][0].__setitem__("award", "platinum"),
            "merged entry": lambda p: p["entries"][0].__setitem__("merged", True),
        }
        for name, mutate in mutations.items():
            forged = copy.deepcopy(wire)
            mutate(forged["content_plan"])
            with self.subTest(mutation=name), self.assertRaises(OptionError):
                content_plan.validate(forged["content_plan"])


class TestFill(unittest.TestCase):
    def test_multi_mode_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        for seed in range(20):
            order = ("fixed", "per_seed", "per_pad")[seed % 3]
            world = make_world(mode_options(order=order, custom=[copy.deepcopy(UNKNOWN), relic_only()]), seed=seed)
            with self.subTest(seed=seed):
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game())
                self.assertEqual(len(world.multiworld.precollected_items[1]), 0)


def artifact_244_options(stages="two"):
    """The CI content-plan profile that dead-ended (fuzz artifact 244), without
    custom packages: 5 Trophies, 6/4/2 relics, two of each red, green and blue
    Token, all five Gems and the four Keys."""
    options = mode_options(custom=[], stages=stages, order="per_pad")
    options["item_pool"] = {"base": {"trophies": 5, "relics": {"sapphire": 6, "gold": 4, "platinum": 2},
                                     "tokens": {"red": 2, "green": 2, "blue": 2, "yellow": 0, "purple": 0},
                                     "gems": ["red", "green", "blue", "yellow", "purple"], "keys": 4}}
    return options


class TestNarrowStartEarlyOpener(unittest.TestCase):
    """Ruling 2026-10-17: a narrow start under second-stage gates gets one local
    early opener instead of a fill simulation; nothing is precollected."""

    def test_a_narrow_start_places_an_early_key_and_fills(self):
        from Fill import distribute_items_restrictive
        from .. import sphere0_guard
        world = make_world(artifact_244_options(), seed=716, stop_before="pre_fill")
        mw = world.multiworld
        start = [loc for loc in mw.get_reachable_locations(CollectionState(mw), 1) if loc.address]
        self.assertLess(len(start), sphere0_guard.NARROW_START_CHECKS)
        self.assertEqual(mw.local_early_items[1], {"Key": 1})
        call_all(mw, "pre_fill")
        distribute_items_restrictive(mw)
        self.assertTrue(mw.can_beat_game())
        self.assertIn("Key", [loc.item.name for loc in start])
        self.assertEqual(len(mw.precollected_items[1]), 0)

    def test_wide_start_takes_no_early_item(self):
        wide = 0
        for seed in range(700, 730):
            world = make_world(artifact_244_options(), seed=seed, stop_before="pre_fill")
            mw = world.multiworld
            start = [loc for loc in mw.get_reachable_locations(CollectionState(mw), 1) if loc.address]
            if len(start) >= sphere0_guard.NARROW_START_CHECKS:
                wide += 1
                self.assertEqual(mw.local_early_items[1], {})
        self.assertGreater(wide, 0)

    def test_plan_without_second_stage_gates_takes_no_early_item(self):
        world = make_world(artifact_244_options(stages="single"), seed=710, stop_before="pre_fill")
        self.assertEqual(world.multiworld.local_early_items[1], {})

    def test_without_a_key_opener_the_widest_opener_is_chosen(self):
        from .. import sphere0_guard
        narrow = None
        for seed in range(700, 760):
            world = make_world(artifact_244_options(), seed=seed, stop_before="pre_fill")
            mw = world.multiworld
            mw.itempool = [item for item in mw.itempool if item.name != "Key"]
            if sphere0_guard.early_opener(world) is not None:
                narrow = world
                break
        world = narrow
        mw = world.multiworld
        state = sphere0_guard._base_state(world)
        start = sphere0_guard._reachable_empty(world, state)
        reach = {}
        for item in mw.itempool:
            if item.advancement and item.name not in reach:
                trial = state.copy()
                trial.collect(item, True)
                reach[item.name] = sphere0_guard._reachable_empty(world, trial)
        chosen = sphere0_guard.early_opener(world)
        self.assertIsNotNone(chosen)
        self.assertGreater(reach[chosen], start)
        self.assertEqual(reach[chosen], max(reach.values()))
