"""Cortex Vortex as a content-plan track and Relic Race Perfect checks (#133 PR 3c, #453).

Cortex Vortex is the bundled Lockheart pair under its own frozen `Cortex
Vortex:` names (35026000 block, letter items 35010200 to 35010202, Wumpa
35016121). It is not a package row and takes no custom slot. With
`relic_perfect_checks` on, every track entry with a Relic Race owns one
`<title>: Relic Race Perfect` check on that route: retail tracks their frozen
35012400 codes, a named block its offset 10, a generic slot `Custom Track N:
Relic Race Perfect` (35024000 + N - 1) and Cortex Vortex 35026005. The paired
native parser applies the same rules (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_plan, cortex_vortex_track, named_tracks, relic_perfect
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN, named_fixture
from .test_track_checks import check_options, checks_of, track_of
from .test_track_modes import entry_of, pad_of

CV = content_plan.CORTEX_TRACK_ID
LOOP = "custom/fixture-loop/2.1"
BTP = "custom/baby-t-park/1.0.2"


def relic_named():
    """Test data on a real named key (North Pole, block 53) with a Relic Race."""
    d = named_fixture()
    d.update(id="package/north-pole/1.1.0", content_id="north-pole", revision="1.1.0",
             uuid="5e0e0d0c-0b0a-4908-8706-050403020100", display_name="North Pole", laps=3)
    d["capabilities"].update(relic=True)
    d["relic_targets"] = dict(sapphire=120000, gold=110000, platinum=100000)
    d["files"] = [dict(f, sha256=h * 32) for f, h in zip(d["files"], ("e7", "f8"))]
    return d


def cv_options(cortex=True, perfect=True, required=True, custom=None, order="per_pad", **extra):
    if custom is None:
        custom = [copy.deepcopy(content_plan.PACKAGES[1]), copy.deepcopy(UNKNOWN), relic_named()]
    options = check_options(rungs=False, custom=custom, order=order)
    options["content_pool"]["tracks"]["cortex_vortex"] = cortex
    if cortex and required:
        options["content_pool"]["required_entries"].append(CV)
    options["relic_perfect_checks"] = perfect
    options.update(extra)
    return options


def perfect_code(track):
    if track["origin"] == "retail":
        return relic_perfect.RELIC_PERFECT_CLASS.code_for(track["display_name"])
    if track["origin"] == content_plan.CORTEX_ORIGIN:
        return 35026005
    if "named_block" in track:
        return named_tracks.location_code(track["named_block"], "relic_perfect")
    return 35024000 + track["custom_slot"] - 1


class TestOffKeepsThePlan(unittest.TestCase):
    def test_no_cortex_and_no_perfect_by_default(self):
        plan = make_world(cv_options(cortex=False, perfect=False), seed=2).ctr_content_plan
        self.assertNotIn(CV, {t["id"] for t in plan["tracks"]})
        self.assertFalse(checks_of(plan, "perfect"))
        self.assertNotIn(content_plan.PERFECT_FEATURE, plan["required_features"])
        self.assertNotIn("relic_perfect", plan.get("track_checks", {}))

    def test_cortex_vortex_false_and_absent_draw_the_same_plan(self):
        absent = cv_options(cortex=False, perfect=False)
        del absent["content_pool"]["tracks"]["cortex_vortex"]
        for seed in (1, 7):
            with self.subTest(seed=seed):
                self.assertEqual(make_world(absent, seed=seed).ctr_content_plan,
                                 make_world(cv_options(cortex=False, perfect=False), seed=seed).ctr_content_plan)

    def test_cortex_vortex_must_be_a_boolean(self):
        for value in (1, "true", None):
            with self.subTest(value=value), self.assertRaisesRegex(OptionError, "cortex_vortex"):
                make_world(cv_options(cortex=value, required=False), seed=1)

    def test_legacy_cortex_track_still_refused(self):
        with self.assertRaisesRegex(OptionError, "legacy custom_tracks/cortex_vortex_track"):
            make_world(cv_options(cortex_vortex_track="on"), seed=1)


class TestCortexVortexTrack(unittest.TestCase):
    def test_record_modes_and_frozen_codes(self):
        world = make_world(cv_options(podium_placement_checks=True, wumpa_check="per_track",
                                      lettersanity=1, letters_per_track=3), seed=4)
        plan = world.ctr_content_plan
        track = track_of(plan, CV)
        self.assertEqual(track, dict(id=CV, origin="cortex_vortex", package_id="bundled/cortex-vortex",
                                     display_name="Cortex Vortex", laps=3, modes=["trophy", "ctr", "relic"],
                                     capabilities=["trophy", "ctr", "relic"], field_size=8))
        self.assertNotIn("custom_slot", track)
        mine = {c["location"]: c for c in plan["checks"] if c["owner"] == CV}
        self.assertEqual(sorted(mine), [35016121] + list(range(35026000, 35026009)) + [35026010, 35026011,
                                                                                      35026013, 35026014])
        self.assertEqual(mine[35026000]["display_name"], "Cortex Vortex: Trophy Race")
        self.assertEqual(mine[35026005]["display_name"], "Cortex Vortex: Relic Race Perfect")
        self.assertEqual(mine[35016121]["display_name"], "Cortex Vortex: Reach 10 Wumpa")
        self.assertEqual([r["mode"] for r in mine[35016121]["routes"]], ["trophy", "ctr"])
        # No package row: the bundled pair is the build's own.
        self.assertNotIn("bundled/cortex-vortex", {p["id"] for p in plan["packages"]})

    def test_letter_items_are_cortex_vortex_items(self):
        for mode in (2, 3):
            world = make_world(cv_options(lettersanity=mode, letters_per_track=2), seed=5)
            plan = world.ctr_content_plan
            letters = {c["location"] for c in checks_of(plan, "letter", CV)}
            items = set(content_plan.plan_letter_items(plan)) & set(cortex_vortex_track.LETTER_ITEM_CODES)
            with self.subTest(mode=mode):
                if mode == 3:
                    self.assertEqual(items, set(cortex_vortex_track.LETTER_ITEM_CODES))
                    self.assertFalse(letters)
                else:
                    self.assertEqual(len(letters), 2)
                    self.assertEqual({35010200 + code - 35026006 for code in letters}, items)
                pooled = [i.name for i in world.multiworld.itempool if i.code in items]
                self.assertEqual(sorted(pooled), sorted(cortex_vortex_track.letter_item_name(l)
                                                        for l, c in zip("CTR", cortex_vortex_track.LETTER_ITEM_CODES)
                                                        if c in items))

    def test_overrides_and_optional_draw(self):
        options = cv_options()
        options["content_pool"]["tracks"]["overrides"] = {CV: ["relic"]}
        plan = make_world(options, seed=3).ctr_content_plan
        self.assertEqual(track_of(plan, CV)["modes"], ["relic"])
        self.assertEqual({c["kind"] for c in plan["checks"] if c["owner"] == CV}, {"relic", "perfect"})
        # Selected but not required: it competes for a pad like any track.
        drawn = sum(CV in {t["id"] for t in make_world(cv_options(required=False), seed=s).ctr_content_plan["tracks"]}
                    for s in range(12))
        self.assertGreater(drawn, 0)

    def test_saphi_cortex_vortex_package_keeps_its_own_identity(self):
        saphi = copy.deepcopy(UNKNOWN)
        saphi.update(id="package/cortex-vortex/1.1.2", content_id="cortex-vortex", revision="1.1.2",
                     uuid="f1a619f0-9176-5e75-ad96-00db77d8cf2b", display_name="Cortex Vortex", author="Lockheart")
        saphi["files"] = [dict(f, sha256=h * 32) for f, h in zip(saphi["files"], ("aa", "bb"))]
        plan = make_world(cv_options(custom=[saphi]), seed=6).ctr_content_plan
        custom = track_of(plan, "custom/cortex-vortex/1.1.2")
        self.assertEqual(custom["room_title"], "Cortex Vortex (Custom)")
        names = [c["display_name"] for c in plan["checks"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("Cortex Vortex: Trophy Race", names)
        self.assertIn("Cortex Vortex (Custom): Trophy Race", names)


class TestRelicRacePerfect(unittest.TestCase):
    def test_one_perfect_per_relic_race_with_its_frozen_code(self):
        for seed in range(4):
            plan = make_world(cv_options(), seed=seed).ctr_content_plan
            self.assertIn(content_plan.PERFECT_FEATURE, plan["required_features"])
            self.assertIs(plan["track_checks"]["relic_perfect"], True)
            perfects = {c["owner"]: c for c in checks_of(plan, "perfect")}
            for track in plan["tracks"]:
                with self.subTest(seed=seed, track=track["id"]):
                    if "relic" not in track["modes"]:
                        self.assertNotIn(track["id"], perfects)
                        continue
                    check = perfects[track["id"]]
                    self.assertEqual(check["location"], perfect_code(track))
                    self.assertEqual(check["display_name"], f"{content_plan.room_title(track)}: Relic Race Perfect")
                    self.assertEqual([(r["mode"], r["award"]) for r in check["routes"]], [("relic", "perfect")])
            # Baby T Park has no Relic Race (no targets), so it has no perfect.
            self.assertNotIn(BTP, perfects)
            self.assertIn(LOOP, perfects)
            self.assertIn(CV, perfects)

    def test_named_and_generic_codes(self):
        plan = make_world(cv_options(), seed=1).ctr_content_plan
        self.assertEqual(checks_of(plan, "perfect", "custom/north-pole/1.1.0")[0]["location"],
                         named_tracks.location_code(53, "relic_perfect"))
        loop = track_of(plan, LOOP)
        self.assertEqual(checks_of(plan, "perfect", LOOP)[0]["location"], 35024000 + loop["custom_slot"] - 1)

    def test_no_relic_mode_means_no_perfect(self):
        options = cv_options()
        options["content_pool"]["tracks"]["modes"] = ["trophy", "ctr"]
        options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(content_plan.PACKAGES[1])]
        options["content_pool"]["required_entries"] = [BTP, CV]
        plan = make_world(options, seed=2).ctr_content_plan
        self.assertFalse(checks_of(plan, "perfect"))
        # The setting still says the option is on.
        self.assertIs(plan["track_checks"]["relic_perfect"], True)

    def test_perfect_follows_the_relic_race_gate(self):
        for seed in range(6):
            world = make_world(cv_options(order="per_pad"), seed=seed)
            plan, mw = world.ctr_content_plan, world.multiworld
            for check in checks_of(plan, "perfect"):
                track = track_of(plan, check["owner"])
                sapphire = mw.get_location(content_plan.mode_checks(track, "relic")[0][1], 1)
                perfect = mw.get_location(content_plan.LOCATION_BY_CODE[check["location"]], 1)
                self.assertIs(perfect.parent_region, sapphire.parent_region)
                for name in ("Key", "Trophy", "Sapphire Relic", "Red CTR Token", "Red Gem"):
                    for count in range(5):
                        state = CollectionState(mw)
                        for _ in range(count):
                            state.collect(world.create_item(name), True)
                        with self.subTest(seed=seed, check=check["display_name"], item=name, count=count):
                            self.assertEqual(perfect.can_reach(state), sapphire.can_reach(state))

    def test_items_cover_the_new_checks(self):
        off = make_world(cv_options(perfect=False), seed=8).ctr_content_plan
        on = make_world(cv_options(), seed=8).ctr_content_plan
        added = len(checks_of(on, "perfect"))
        self.assertGreater(added, 0)
        self.assertEqual(on["items"]["coded_checks"], off["items"]["coded_checks"] + added)
        self.assertEqual(on["items"]["filler_count"], off["items"]["filler_count"] + added)


class TestTrackerAndForgery(unittest.TestCase):
    def test_tracker_restores_cortex_and_perfects(self):
        from NetUtils import convert_to_base_types
        for seed, extra in ((3, {}), (4, dict(lettersanity=3, wumpa_check="global", podium_placement_checks=True))):
            world = make_world(cv_options(**extra), seed=seed)
            wire = json.loads(json.dumps(world.fill_slot_data()))
            with self.subTest(seed=seed):
                tracker = make_world({}, seed=999, passthrough=convert_to_base_types(wire))
                self.assertEqual(tracker.ctr_content_plan, world.ctr_content_plan)
                self.assertEqual(tracker.fill_slot_data(), wire)
                self.assertEqual(tracker.options.relic_perfect_checks.value, 1)

    def test_forged_plans_are_refused(self):
        wire = make_world(cv_options(lettersanity=2, letters_per_track=1), seed=4).fill_slot_data()

        def cv(p):
            return track_of(p, CV)

        def perfect(p, owner=CV):
            return checks_of(p, "perfect", owner)[0]

        def drop_perfect(p):
            p["checks"].remove(perfect(p, LOOP))
            p["items"]["coded_checks"] -= 1
            p["items"]["filler_count"] -= 1

        def perfect_on_trophy_only(p):
            entry = entry_of(p, BTP)
            p["checks"].append(dict(location=content_plan.named_tracks.location_code(8, "relic_perfect"),
                                    owner=BTP, kind="perfect", display_name="Baby T Park: Relic Race Perfect",
                                    routes=[dict(entry_id=entry["id"], mode="relic", leg_id=None, encounter_id=None,
                                                 own_pad_id=pad_of(p, entry)["id"], award="perfect")]))
            p["items"]["coded_checks"] += 1
            p["items"]["filler_count"] += 1

        def cv_as_custom_slot(p):
            cv(p)["custom_slot"] = 9

        def cv_twice(p):
            p["tracks"].append(dict(cv(p), id="cortex_vortex_2"))

        mutations = {
            "perfect dropped": drop_perfect,
            "perfect on a track without a Relic Race": perfect_on_trophy_only,
            "perfect takes the retail host's code": lambda p: perfect(p).__setitem__("location", 35012415),
            "perfect award changed": lambda p: perfect(p)["routes"][0].__setitem__("award", "sapphire"),
            "perfect routed through the Trophy Race": lambda p: perfect(p)["routes"][0].__setitem__("mode", "trophy"),
            "perfect feature dropped": lambda p: p["required_features"].remove(content_plan.PERFECT_FEATURE),
            "setting not true": lambda p: p["track_checks"].__setitem__("relic_perfect", False),
            "setting dropped": lambda p: p["track_checks"].pop("relic_perfect"),
            "cortex laps": lambda p: cv(p).__setitem__("laps", 5),
            "cortex package": lambda p: cv(p).__setitem__("package_id", "package/cortex-vortex/1.1.2"),
            "cortex name": lambda p: cv(p).__setitem__("display_name", "Oxide Station"),
            "cortex id": lambda p: cv(p).__setitem__("id", "retail:13"),
            "cortex with a custom slot": cv_as_custom_slot,
            "cortex twice": cv_twice,
            "cortex trophy takes Oxide Station's code": lambda p: next(
                c for c in p["checks"] if c["owner"] == CV and c["kind"] == "trophy").__setitem__("location", 35011013),
        }
        for name, mutate in mutations.items():
            forged = copy.deepcopy(wire)
            mutate(forged["content_plan"])
            with self.subTest(mutation=name), self.assertRaises(OptionError):
                content_plan.validate(forged["content_plan"])


class TestFill(unittest.TestCase):
    def test_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        for seed in range(12):
            order = ("fixed", "per_seed", "per_pad")[seed % 3]
            extra = dict(lettersanity=seed % 4, letters_per_track=2, wumpa_check=("off", "global", "per_track")[seed % 3])
            world = make_world(cv_options(order=order, **extra), seed=seed)
            with self.subTest(seed=seed):
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game())
                self.assertEqual(len(world.multiworld.precollected_items[1]), 0)


if __name__ == "__main__":
    unittest.main()
