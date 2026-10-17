"""Podium rungs, Reach 10 Wumpa and Lettersanity on content-plan tracks (#133 PR 3b).

Retail tracks keep their frozen codes, a named custom track uses its block and
any other custom track its generic `Custom Track N` family. A package's
capabilities decide what it can offer: rungs need a Trophy Race, letters a CTR
Challenge, Wumpa a Trophy Race or CTR Challenge plus the `wumpa` flag. The
paired native parser applies the same rules (native
tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_plan, named_tracks, podium
from ..custom_check_namespace import custom_check_code
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN
from .test_track_modes import entry_of, mode_options, pad_of

BTP = "custom/baby-t-park/1.0.2"
LOOP = "custom/fixture-loop/2.1"


def check_options(rungs=True, wumpa="off", letters=0, per_track=3, stages="two", order="per_pad",
                  custom=None, modes=("trophy", "ctr", "relic")):
    if custom is None:
        custom = [copy.deepcopy(content_plan.PACKAGES[1]), copy.deepcopy(UNKNOWN)]
    options = mode_options(modes=modes, stages=stages, order=order, custom=custom)
    options.update(podium_placement_checks=rungs, wumpa_check=wumpa, lettersanity=letters,
                   letters_per_track=per_track)
    return options


def checks_of(plan, kind, owner=None):
    return [c for c in plan["checks"] if c["kind"] == kind and (owner is None or c["owner"] == owner)]


def track_of(plan, track_id):
    return next(t for t in plan["tracks"] if t["id"] == track_id)


def refused(plan):
    try:
        content_plan.validate(plan)
    except OptionError:
        return True
    return False


class TestOffKeepsTheWire(unittest.TestCase):
    def test_no_family_means_no_record_and_no_feature(self):
        world = make_world(check_options(rungs=False), seed=3)
        plan = world.ctr_content_plan
        self.assertNotIn("track_checks", plan)
        self.assertFalse({content_plan.PODIUM_FEATURE, content_plan.WUMPA_FEATURE,
                          content_plan.LETTER_FEATURE} & set(plan["required_features"]))
        self.assertEqual({c["kind"] for c in plan["checks"]}, {"trophy", "ctr", "relic"})

    def test_podium_toggle_on_with_no_sub_rung_is_off(self):
        options = check_options()
        options.update(podium_finish_rungs=False, podium_held_rungs=False)
        self.assertNotIn("track_checks", make_world(options, seed=3).ctr_content_plan)


class TestPodiumRungs(unittest.TestCase):
    def test_every_trophy_race_carries_the_seed_rungs_with_frozen_codes(self):
        world = make_world(check_options(), seed=5)
        plan = world.ctr_content_plan
        rungs = plan["track_checks"]["podium_rungs"]
        self.assertEqual(rungs, ["held_1st", "held_3rd", "finish_podium", "finish_any"])
        for track in plan["tracks"]:
            mine = {c["routes"][0]["award"]: c for c in checks_of(plan, "podium", track["id"])}
            self.assertEqual(sorted(mine) if "trophy" in track["modes"] else [],
                             sorted(rungs) if "trophy" in track["modes"] else [])
            for key, check in mine.items():
                self.assertEqual(check["routes"][0]["mode"], "trophy")
                if track["origin"] == "retail":
                    expected = podium.PODIUM_CLASS.code_for(track["display_name"], key)
                elif "named_block" in track:
                    expected = named_tracks.location_code(track["named_block"], key)
                else:
                    expected = content_plan.CTR_LOCATION_IDS[f"Custom Track {track['custom_slot']}: "
                                                             f"{content_plan.RUNG_SUFFIX[key]}"]
                self.assertEqual(check["location"], expected)
                self.assertEqual(check["display_name"],
                                 f"{content_plan.room_title(track)}: {content_plan.RUNG_SUFFIX[key]}")

    def test_sub_toggles_choose_the_rung_set(self):
        for held, fifth, finish, anypos, expected in (
                (True, True, False, False, ["held_1st", "held_3rd", "held_5th"]),
                (False, False, True, False, ["finish_podium"]),
                (True, False, True, True, ["held_1st", "held_3rd", "finish_podium", "finish_any"])):
            options = check_options()
            options.update(podium_held_rungs=held, podium_held_fifth_rung=fifth,
                           podium_finish_rungs=finish, podium_any_position_rung=anypos)
            with self.subTest(expected=expected):
                self.assertEqual(make_world(options, seed=1).ctr_content_plan["track_checks"]["podium_rungs"],
                                 expected)

    def test_rungs_follow_the_trophy_gate(self):
        world = make_world(check_options(order="fixed"), seed=9)
        plan, mw = world.ctr_content_plan, world.multiworld
        for track in plan["tracks"]:
            if "trophy" not in track["modes"]:
                continue
            trophy = mw.get_location(content_plan.mode_checks(track, "trophy")[0][1], 1)
            for check in checks_of(plan, "podium", track["id"]):
                rung = mw.get_location(content_plan.LOCATION_BY_CODE[check["location"]], 1)
                self.assertIs(rung.parent_region, trophy.parent_region)
                for keys in range(5):
                    state = CollectionState(mw)
                    for _ in range(keys):
                        state.collect(world.create_item("Key"), True)
                    self.assertEqual(rung.can_reach(state), trophy.can_reach(state))


class TestWumpa(unittest.TestCase):
    def test_per_track_codes_routes_and_capability(self):
        world = make_world(check_options(wumpa="per_track"), seed=4)
        plan = world.ctr_content_plan
        by_owner = {c["owner"]: c for c in checks_of(plan, "wumpa")}
        for track in plan["tracks"]:
            reach = [m for m in ("trophy", "ctr") if m in track["modes"]]
            if track["origin"] == "custom":
                package = next(p for p in plan["packages"] if p["id"] == track["package_id"])
                if not package["capabilities"]["wumpa"]:
                    reach = []
            if not reach:
                self.assertNotIn(track["id"], by_owner)
                continue
            check = by_owner[track["id"]]
            self.assertEqual([r["mode"] for r in check["routes"]], reach)
            self.assertEqual({r["award"] for r in check["routes"]}, {"wumpa"})
            if track["origin"] == "retail":
                self.assertEqual(check["location"],
                                 content_plan.CTR_LOCATION_IDS[f"{track['display_name']}: Reach 10 Wumpa"])
            elif "named_block" in track:
                self.assertEqual(check["location"], named_tracks.location_code(track["named_block"], "wumpa"))
        # UNKNOWN measures no Wumpa route: it gets no check.
        self.assertNotIn(LOOP, by_owner)
        self.assertIn(BTP, by_owner)

    def test_relic_only_entry_has_no_wumpa(self):
        options = check_options(wumpa="per_track")
        options["content_pool"]["tracks"]["overrides"] = {"retail:3": ["relic"]}
        plan = make_world(options, seed=4).ctr_content_plan
        self.assertNotIn("retail:3", {c["owner"] for c in checks_of(plan, "wumpa")})

    def test_generic_slot_uses_custom_track_family(self):
        wumpa = copy.deepcopy(UNKNOWN)
        wumpa["capabilities"]["wumpa"] = True
        plan = make_world(check_options(wumpa="per_track", custom=[wumpa]), seed=4).ctr_content_plan
        check = checks_of(plan, "wumpa", LOOP)[0]
        self.assertEqual(check["location"], 35016600)  # Custom Track 1: Reach 10 Wumpa

    def test_per_track_check_opens_on_any_route(self):
        for seed in range(30):
            world = make_world(check_options(wumpa="per_track"), seed=seed)
            plan, mw = world.ctr_content_plan, world.multiworld
            for check in checks_of(plan, "wumpa"):
                location = mw.get_location(content_plan.LOCATION_BY_CODE[check["location"]], 1)
                pad = next(p for p in plan["pads"] if p["id"] == check["routes"][0]["own_pad_id"])
                stages = {g["mode"]: g["stage"] for g in pad["mode_gates"]}
                free = any(stages[r["mode"]] == 1 for r in check["routes"])
                with self.subTest(seed=seed, check=check["display_name"]):
                    self.assertEqual(location.access_rule is location.__class__.access_rule, free)

    def test_global_is_one_check_with_every_route(self):
        world = make_world(check_options(wumpa="global"), seed=6)
        plan, mw = world.ctr_content_plan, world.multiworld
        [check] = checks_of(plan, "wumpa")
        self.assertEqual((check["location"], check["owner"], check["display_name"]),
                         (35016100, "global", "Wumpa: Reach 10 Wumpa"))
        routes = [(r["own_pad_id"], r["mode"]) for r in check["routes"]]
        self.assertEqual(routes, sorted(routes, key=lambda r: (int(r[0].split(":")[1]),
                                                               content_plan.MODES.index(r[1]))))
        wanted = sum(len(content_plan.wumpa_modes(t, next((p for p in plan["packages"]
                                                            if p["id"] == t.get("package_id")), None)))
                     for t in plan["tracks"])
        self.assertEqual(len(routes), wanted)
        location = mw.get_location("Wumpa: Reach 10 Wumpa", 1)
        self.assertEqual(location.parent_region.name, "Menu")
        pads = {p["id"]: p for p in plan["pads"]}
        for keys in range(5):
            state = CollectionState(mw)
            for _ in range(keys):
                state.collect(world.create_item("Key"), True)
            free_route = any(
                mw.get_region(r["entry_id"], 1).can_reach(state)
                and all(not (g["stage"] == 2 and g["mode"] == r["mode"]) for g in pads[r["own_pad_id"]]["mode_gates"])
                for r in check["routes"])
            self.assertEqual(location.can_reach(state), free_route)


class TestLettersanity(unittest.TestCase):
    def test_modes_shape_checks_and_items(self):
        for mode, per_track in ((1, 2), (2, 1), (2, 3), (3, 3)):
            world = make_world(check_options(letters=mode, per_track=per_track), seed=8)
            plan = world.ctr_content_plan
            items = content_plan.plan_letter_items(plan)
            ctr_tracks = [t for t in plan["tracks"] if "ctr" in t["modes"]]
            with self.subTest(mode=mode, per_track=per_track):
                self.assertEqual(plan["track_checks"]["lettersanity"], mode)
                self.assertEqual("letters_per_track" in plan["track_checks"], mode in (1, 2))
                for track in ctr_tracks:
                    letters = checks_of(plan, "letter", track["id"])
                    self.assertEqual(len(letters), per_track if mode in (1, 2) else 0)
                    for check in letters:
                        self.assertEqual(check["routes"][0]["mode"], "ctr")
                self.assertEqual(len(items), {1: 0, 2: per_track, 3: 3}[mode] * len(ctr_tracks))
                pooled = [item.name for item in world.multiworld.itempool if item.code in items]
                self.assertEqual(sorted(pooled), sorted(items.values()))
                rows = {r["item"]: r for r in plan["items"]["rows"]}
                self.assertTrue(all(rows[code]["base"] == 1 for code in items))

    def test_letter_codes_and_items_per_identity(self):
        world = make_world(check_options(letters=3), seed=8)
        plan = world.ctr_content_plan
        items = content_plan.plan_letter_items(plan)
        btp = track_of(plan, BTP)
        crash = track_of(plan, "retail:3")
        self.assertEqual(items[named_tracks.item_code(8, "letter_c")], "Letter C (Baby T Park)")
        self.assertEqual(items[35010139], "Letter C (Crash Cove)")
        self.assertIn(btp["id"], [t["id"] for t in plan["tracks"]])
        from ..lettersanity import LETTERSANITY_CLASS
        self.assertEqual(content_plan.letter_code(crash, 0), LETTERSANITY_CLASS.code_for("Crash Cove", "C"))
        trial = track_of(plan, "retail:16")
        self.assertEqual(content_plan.letter_item(trial, 0), ("Letter C (Slide Coliseum)", 35010194))
        generic = dict(origin="custom", custom_slot=2, display_name="X", modes=["ctr"])
        self.assertEqual(content_plan.letter_item(generic, 1)[1], custom_check_code("letter_item", 2, 1))

    def test_rules_follow_the_legacy_shapes(self):
        world = make_world(check_options(letters=2, per_track=2, stages="single"), seed=2)
        plan, mw = world.ctr_content_plan, world.multiworld
        crash = track_of(plan, "retail:3")
        letters, items = content_plan.plan_letters(plan, crash, plan["track_checks"])
        token = mw.get_location("Crash Cove: CTR Token Challenge", 1)

        def state_without(name):
            state = CollectionState(mw)
            for item in mw.itempool:
                if item.name != name:
                    state.collect(item, True)
            return state
        self.assertTrue(token.can_reach(state_without(None)))
        self.assertEqual(len(items), 2)
        for i in items:
            self.assertFalse(token.can_reach(state_without(content_plan.letter_item(crash, i)[0])))
        for i in letters:
            loc = mw.get_location(f"Crash Cove: Letter {content_plan.LETTERS[i]}", 1)
            self.assertTrue(loc.can_reach(state_without(None)))
            self.assertFalse(loc.can_reach(state_without(content_plan.letter_item(crash, i)[0])),
                             "a mode 2 letter needs its own item")

    def test_mode_one_adds_no_item_rule(self):
        world = make_world(check_options(letters=1, per_track=3, stages="single"), seed=2)
        self.assertEqual(content_plan.letter_requirements(world.ctr_content_plan), {})

    def test_generic_letter_items_take_the_room_title_in_the_room(self):
        from ..custom_track_presentation import item_aliases
        ctr = copy.deepcopy(UNKNOWN)
        ctr["capabilities"]["ctr_tokens"] = True
        world = make_world(check_options(letters=3, custom=[ctr]), seed=2)
        title = track_of(world.ctr_content_plan, LOOP)["room_title"]
        self.assertEqual(item_aliases(world)[custom_check_code("letter_item", 1, 0)], f"Letter C ({title})")


class TestValidateRefuses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = make_world(check_options(wumpa="per_track", letters=2, per_track=2), seed=11).ctr_content_plan

    def altered(self, change):
        plan = copy.deepcopy(self.plan)
        change(plan)
        return plan

    def test_generated_plan_validates(self):
        self.assertTrue(content_plan.validate(copy.deepcopy(self.plan)))

    def test_forgeries(self):
        def drop_letter(p):
            p["checks"].remove(checks_of(p, "letter")[0])
        def drop_rung(p):
            p["checks"].remove(checks_of(p, "podium")[0])
        def drop_letter_item(p):
            code = next(iter(content_plan.plan_letter_items(p)))
            p["items"]["rows"] = [r for r in p["items"]["rows"] if r["item"] != code]
        def double_letter_item(p):
            code = next(iter(content_plan.plan_letter_items(p)))
            row = next(r for r in p["items"]["rows"] if r["item"] == code)
            row.update(base=2, remaining=2, receipt_cap=2, requirement_ceiling=2)
        def bad_rungs(p):
            p["track_checks"]["podium_rungs"] = ["held_3rd"]
        def lpt_mode_three(p):
            p["track_checks"]["lettersanity"] = 3
        def wumpa_global(p):
            p["track_checks"]["wumpa"] = "global"
        def wumpa_route_relic(p):
            checks_of(p, "wumpa")[0]["routes"][0]["mode"] = "relic"
        def drop_feature(p):
            p["required_features"].remove(content_plan.WUMPA_FEATURE)
        def empty_record(p):
            p["track_checks"] = {}
        def swap_letter(p):
            check = checks_of(p, "letter")[0]
            track = track_of(p, check["owner"])
            used = {c["location"] for c in checks_of(p, "letter", track["id"])}
            other = next(i for i in range(3) if content_plan.letter_code(track, i) not in used)
            check["location"] = content_plan.letter_code(track, other)
        for change in (drop_letter, drop_rung, drop_letter_item, double_letter_item, bad_rungs,
                       lpt_mode_three, wumpa_global, wumpa_route_relic, drop_feature, empty_record):
            with self.subTest(change=change.__name__):
                self.assertTrue(refused(self.altered(change)))
        # Moving a letter check to another letter of the same track is a valid
        # different draw only if its item moves too; alone it is refused.
        self.assertTrue(refused(self.altered(swap_letter)))


class TestTrackerAndFill(unittest.TestCase):
    def test_tracker_restores_every_family(self):
        for wumpa, letters in (("per_track", 2), ("global", 3), ("off", 1)):
            world = make_world(check_options(wumpa=wumpa, letters=letters, per_track=2), seed=13)
            wire = json.loads(json.dumps(world.fill_slot_data()))
            other = make_world({}, seed=999, passthrough=wire)
            with self.subTest(wumpa=wumpa, letters=letters):
                self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
                self.assertEqual(other.fill_slot_data(), wire)
                self.assertEqual(sorted(loc.address for loc in other.multiworld.get_locations(1)),
                                 sorted(loc.address for loc in world.multiworld.get_locations(1)))
                state_a = CollectionState(world.multiworld)
                state_b = CollectionState(other.multiworld)
                for name in ("Key", "Key", "Trophy"):
                    state_a.collect(world.create_item(name), True)
                    state_b.collect(other.create_item(name), True)
                self.assertEqual(
                    sorted(l.address for l in other.multiworld.get_reachable_locations(state_b, 1)),
                    sorted(l.address for l in world.multiworld.get_reachable_locations(state_a, 1)))

    def test_real_fill_with_every_family(self):
        from Fill import distribute_items_restrictive
        shapes = [("per_track", 2, 2), ("global", 3, 3), ("per_track", 1, 1), ("off", 2, 3)]
        for seed in range(16):
            wumpa, letters, per_track = shapes[seed % len(shapes)]
            world = make_world(check_options(wumpa=wumpa, letters=letters, per_track=per_track,
                                             order=("fixed", "per_seed", "per_pad")[seed % 3]), seed=seed)
            with self.subTest(seed=seed):
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game())
                self.assertEqual(len(world.multiworld.precollected_items[1]), 0)


if __name__ == "__main__":
    unittest.main()
