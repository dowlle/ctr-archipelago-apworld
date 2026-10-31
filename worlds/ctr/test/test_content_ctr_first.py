"""adventure_structure: ctr_first on content plans (job J11, decisions 4 and 14)."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_plan
from .test_content_item_pool import small_pool
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN
from .test_track_checks import BTP, LOOP, check_options, checks_of, refused, track_of
from .test_track_modes import entry_of, pad_of

#: Crash Cove, Roo's Tubes and Slide Coliseum.
RETAIL = [3, 6, 16]
CTR_LESS = "retail:6"


def first_options(**overrides):
    """ctr_first on three retail tracks (Roo's Tubes without its CTR
    Challenge by override), Baby T Park (trophy and ctr) and the B+
    fixture-loop (trophy and relic, no CTR: decision 4 fallback), with rungs,
    per-track Wumpa and Lettersanity 1, two stages and a per-pad order."""
    custom = [copy.deepcopy(content_plan.PACKAGES[1]), copy.deepcopy(UNKNOWN)]
    options = check_options(wumpa="per_track", letters=1, per_track=2, custom=custom)
    options["content_pool"]["tracks"]["retail"] = list(RETAIL)
    options["content_pool"]["tracks"]["overrides"] = {CTR_LESS: ["trophy", "relic"]}
    options.update(adventure_structure="ctr_first", wumpa_shop_slots=0, item_pool=small_pool())
    options.update(overrides)
    return options


def full_generation(options, seed):
    """Generate, fill and output one solo world; returns (world, wire)."""
    from Fill import distribute_items_restrictive
    from worlds.AutoWorld import call_all
    world = make_world(options, seed=seed, stop_before="pre_fill")
    mw = world.multiworld
    call_all(mw, "pre_fill")
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    wire = json.loads(json.dumps(world.fill_slot_data()))
    return world, wire


def assert_complete(case, world):
    mw = world.multiworld
    case.assertTrue(mw.can_beat_game())
    state = mw.get_all_state(False)
    case.assertEqual([loc.name for loc in mw.get_locations(world.player) if not loc.can_reach(state)], [])


def first_world(seed=20261029, **overrides):
    for s in range(seed, seed + 40):
        try:
            return make_world(first_options(**overrides), seed=s)
        except OptionError:
            continue
    raise AssertionError("no seed generated")


class TestContentCtrFirst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = first_world()
        cls.plan = cls.world.ctr_content_plan

    def test_plan_key_feature_and_entry_modes(self):
        plan = self.plan
        self.assertEqual(plan["adventure_structure"], "ctr_first")
        self.assertEqual(plan["required_features"][-1], "ctr_first_v1")
        for track_id in ("retail:3", "retail:16"):
            self.assertEqual(entry_of(plan, track_id)["modes"], ["ctr", "relic"])
            self.assertEqual(track_of(plan, track_id)["modes"], ["trophy", "ctr", "relic"])
        self.assertEqual(entry_of(plan, BTP)["modes"], ["ctr"])
        # Decision 4: a track without a CTR Challenge keeps the classic order.
        self.assertEqual(sorted(entry_of(plan, CTR_LESS)["modes"]), ["relic", "trophy"])
        self.assertEqual(sorted(entry_of(plan, LOOP)["modes"]), ["relic", "trophy"])

    def test_mode_gates_ctr_first_then_relic(self):
        plan = self.plan
        entry = entry_of(plan, "retail:3")
        gates = pad_of(plan, entry)["mode_gates"]
        self.assertEqual([(g["mode"], g["stage"]) for g in gates][0], ("ctr", 1))
        self.assertEqual(gates[1]["mode"], "relic")

    def test_trophy_and_rungs_route_from_the_ctr_challenge(self):
        plan = self.plan
        entry = entry_of(plan, "retail:3")
        own = [c for c in plan["checks"] if c["owner"] == "retail:3"]
        self.assertEqual(own[0]["kind"], "trophy")
        self.assertEqual(own[0]["display_name"], "Crash Cove: Trophy Race")
        self.assertEqual(own[0]["location"], content_plan.CTR_LOCATION_IDS["Crash Cove: Trophy Race"])
        self.assertEqual([(r["mode"], r["award"]) for r in own[0]["routes"]], [("ctr", "win")])
        token = next(c for c in own if c["kind"] == "ctr")
        self.assertEqual([(r["mode"], r["award"]) for r in token["routes"]], [("ctr", "win_letters")])
        self.assertEqual(own[0]["routes"][0]["entry_id"], entry["id"])
        rungs = [c for c in own if c["kind"] == "podium"]
        self.assertTrue(rungs)
        self.assertTrue(all(c["routes"][0]["mode"] == "ctr" for c in rungs))
        # Order: the Trophy check, its rungs, then the CTR check as in classic.
        kinds = [c["kind"] for c in own]
        self.assertLess(kinds.index("trophy"), kinds.index("ctr"))
        self.assertLess(kinds.index("podium"), kinds.index("ctr"))
        wumpa = [c for c in own if c["kind"] == "wumpa"]
        self.assertEqual([r["mode"] for r in wumpa[0]["routes"]], ["ctr"])
        self.assertFalse(any(r["mode"] == "trophy" for c in plan["checks"] if c["owner"] in ("retail:3", BTP)
                             for r in c["routes"]))

    def test_fallback_track_keeps_classic_routes(self):
        own = [c for c in self.plan["checks"] if c["owner"] == LOOP and c["kind"] == "trophy"]
        self.assertEqual(own[0]["routes"][0]["mode"], "trophy")
        own = [c for c in self.plan["checks"] if c["owner"] == CTR_LESS and c["kind"] == "trophy"]
        self.assertEqual(own[0]["routes"][0]["mode"], "trophy")

    def test_same_checks_as_classic(self):
        """ctr_first changes routes only, never which checks exist."""
        classic = make_world(first_options(adventure_structure="classic"), seed=self.world.multiworld.seed)
        self.assertNotIn("adventure_structure", classic.ctr_content_plan)
        self.assertNotIn("ctr_first_v1", classic.ctr_content_plan["required_features"])
        self.assertEqual(len(classic.ctr_content_plan["checks"]), len(self.plan["checks"]))

    def test_validate_and_tracker_round_trip(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertTrue(content_plan.validate(wire["content_plan"]))
        self.assertNotIn("adventure_structure", wire["ctr_options"])
        tracker = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(int(tracker.options.adventure_structure.value), 1)
        self.assertEqual(tracker.fill_slot_data(), wire)

    def test_forged_plans_refuse(self):
        def mutate(change):
            plan = copy.deepcopy(self.plan)
            change(plan)
            return refused(plan)

        def add_trophy(p):
            entry_of(p, "retail:3")["modes"].insert(0, "trophy")

        def classic_route(p):
            next(c for c in p["checks"] if c["owner"] == "retail:3" and c["kind"] == "trophy")["routes"][0]["mode"] = "trophy"

        def rung_route(p):
            next(c for c in p["checks"] if c["owner"] == "retail:3" and c["kind"] == "podium")["routes"][0]["mode"] = "trophy"

        def trophy_award(p):
            next(c for c in p["checks"] if c["owner"] == "retail:3" and c["kind"] == "trophy")["routes"][0]["award"] = "win_letters"

        def drop_key(p):
            del p["adventure_structure"]

        def wrong_key(p):
            p["adventure_structure"] = "classic"

        def drop_feature(p):
            p["required_features"].remove("ctr_first_v1")

        def fallback_moved(p):
            entry = entry_of(p, LOOP)
            entry["modes"] = ["relic"]

        def relic_first(p):
            entry_of(p, "retail:3")["modes"] = ["relic", "ctr"]

        for change in (add_trophy, classic_route, rung_route, trophy_award, drop_key, wrong_key, drop_feature,
                       fallback_moved, relic_first):
            with self.subTest(change.__name__):
                self.assertTrue(mutate(change))


class TestContentCtrFirstLogic(unittest.TestCase):
    def test_first_place_pays_the_trophy_and_the_letters_pay_the_token(self):
        """Lettersanity 3 (ruled 2026-10-29): the CTR Token check needs its three
        letter items; the Trophy Race check and the rungs do not."""
        options = first_options(lettersanity=3)
        options["pad_layout"]["stages"] = "single"
        world = None
        for seed in range(1, 60):
            try:
                world = make_world(options, seed=seed)
                break
            except OptionError:
                continue
        self.assertIsNotNone(world)
        mw = world.multiworld
        plan = world.ctr_content_plan
        pad = pad_of(plan, entry_of(plan, "retail:3"))
        state = CollectionState(mw)
        for _ in range(4):
            state.collect(world.create_item("Key"), True)
        trophy = mw.get_location("Crash Cove: Trophy Race", 1)
        ctr = mw.get_location("Crash Cove: CTR Token Challenge", 1)
        rung = next(mw.get_location(content_plan.LOCATION_BY_CODE[c["location"]], 1) for c in plan["checks"]
                    if c["owner"] == "retail:3" and c["kind"] == "podium")
        if pad["racer_lock"] is not None:
            self.skipTest("racer-locked pad")
        self.assertTrue(state.can_reach(rung))
        self.assertTrue(state.can_reach(trophy))
        self.assertFalse(state.can_reach(ctr))
        for letter in "CTR":
            state.collect(world.create_item(f"Letter {letter} (Crash Cove)"), True)
        self.assertTrue(state.can_reach(ctr))

    def test_the_token_needs_what_the_trophy_needs(self):
        """The CTR Token check is paid by the same first place."""
        world = make_world(first_options(), seed=20261029, stop_before="pre_fill")
        trophy = world.multiworld.get_location("Crash Cove: Trophy Race", 1)
        ctr = world.multiworld.get_location("Crash Cove: CTR Token Challenge", 1)
        state = world.multiworld.get_all_state(False)
        self.assertTrue(state.can_reach(ctr))
        trophy.access_rule = lambda state: False
        self.assertFalse(state.can_reach(ctr))

    def test_the_first_race_is_proved_by_the_trophy_check(self):
        plan = make_world(first_options(lettersanity=3), seed=20261029).ctr_content_plan
        pad = pad_of(plan, entry_of(plan, "retail:3"))
        checks = [c for c in plan["checks"] if c["routes"] and c["routes"][0]["own_pad_id"] == pad["id"]]
        self.assertEqual(content_plan.first_race_checks(checks, "ctr"),
                         (content_plan.CTR_LOCATION_IDS["Crash Cove: Trophy Race"],))

    def test_each_check_keeps_its_own_boost_rank(self):
        """Progressive Boost on: the Trophy Race check needs its own rank, the
        CTR Token check its own and the Trophy Race's."""
        options = first_options(progressive_boost="shared_global", logic_difficulty="hard")
        options["pad_layout"]["stages"] = "single"
        options["content_pool"]["tracks"]["retail"] = [3, 6, 16, 7]  # Hot Air Skyway: USF finish
        world = None
        for seed in range(1, 60):
            try:
                world = make_world(options, seed=seed)
                break
            except OptionError:
                continue
        self.assertIsNotNone(world)
        plan = world.ctr_content_plan
        by_name = {c["display_name"]: c for c in plan["checks"]}
        self.assertEqual(by_name["Crash Cove: Trophy Race"].get("boost", 0), 0)
        self.assertEqual(by_name["Crash Cove: CTR Token Challenge"]["boost"], 1)
        mw = world.multiworld
        state = CollectionState(mw)
        for _ in range(4):
            state.collect(world.create_item("Key"), True)
        trophy = mw.get_location("Crash Cove: Trophy Race", 1)
        token = mw.get_location("Crash Cove: CTR Token Challenge", 1)
        if pad_of(plan, entry_of(plan, "retail:3"))["racer_lock"] is not None:
            self.skipTest("racer-locked pad")
        self.assertTrue(state.can_reach(trophy))
        self.assertFalse(state.can_reach(token))
        state.collect(world.create_item("Progressive Boost"), True)
        self.assertTrue(state.can_reach(token))
        # Hot Air Skyway: the Trophy rank (USF, two) is above the CTR floor.
        self.assertEqual(by_name["Hot Air Skyway: Trophy Race"]["boost"], 2)
        sky = mw.get_location("Hot Air Skyway: CTR Token Challenge", 1)
        if pad_of(plan, entry_of(plan, "retail:7"))["racer_lock"] is None:
            self.assertFalse(state.can_reach(sky))
            state.collect(world.create_item("Progressive Boost"), True)
            self.assertTrue(state.can_reach(sky))

    def test_no_mode_order_draw_for_ctr_first_entries(self):
        fixed = first_options()
        fixed["pad_layout"]["mode_order"] = "fixed"
        per_seed = first_options()
        per_seed["pad_layout"]["mode_order"] = "per_seed"
        for options in (fixed, per_seed):
            world = make_world(options, seed=20261029)
            self.assertEqual(entry_of(world.ctr_content_plan, "retail:3")["modes"], ["ctr", "relic"])

    def test_full_generation_accessibility_full(self):
        for seed in (1, 2):
            with self.subTest(seed=seed):
                world, wire = full_generation(first_options(accessibility="full"), seed)
                assert_complete(self, world)
                self.assertTrue(content_plan.validate(wire["content_plan"]))


if __name__ == "__main__":
    unittest.main()
