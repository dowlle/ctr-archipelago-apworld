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

from .. import content_cups, content_plan, cortex_vortex, named_tracks, relic_perfect
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
    options = check_options(rungs=True, custom=custom, order=order)
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

class TestCortexVortexTrack(unittest.TestCase):
    def test_standalone_laps_record(self):
        # A4-13 (ruling of 2026-11-09): standalone races are two laps; the
        # authored laps stay three, so cup legs keep the cup lap rule.
        self.assertNotIn("standalone_laps", content_plan.cortex_track())
        track = content_plan.cortex_track(standalone=True)
        self.assertEqual(track["laps"], 3)
        self.assertEqual(track["standalone_laps"], 2)
        self.assertEqual(content_cups.leg_laps(track, False), 3)
        self.assertEqual(content_cups.leg_laps(track, True), 1)

    def test_record_modes_and_frozen_codes(self):
        world = make_world(cv_options(podium_placement_checks=True, wumpa_check="per_track",
                                      lettersanity=1, letters_per_track=3), seed=4)
        plan = world.ctr_content_plan
        track = track_of(plan, CV)
        self.assertEqual(track, dict(id=CV, origin="cortex_vortex", package_id="bundled/cortex-vortex",
                                     display_name="Cortex Vortex", laps=3, standalone_laps=2,
                                     modes=["trophy", "ctr", "relic"],
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
            items = set(content_plan.plan_letter_items(plan)) & set(cortex_vortex.LETTER_ITEM_CODES)
            with self.subTest(mode=mode):
                if mode == 3:
                    self.assertEqual(items, set(cortex_vortex.LETTER_ITEM_CODES))
                    self.assertFalse(letters)
                else:
                    self.assertEqual(len(letters), 2)
                    self.assertEqual({35010200 + code - 35026006 for code in letters}, items)
                pooled = [i.name for i in world.multiworld.itempool if i.code in items]
                self.assertEqual(sorted(pooled), sorted(cortex_vortex.letter_item_name(l)
                                                        for l, c in zip("CTR", cortex_vortex.LETTER_ITEM_CODES)
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

    @staticmethod
    def saphi_cortex_vortex():
        saphi = copy.deepcopy(UNKNOWN)
        saphi.update(id="package/cortex-vortex/1.1.2", content_id="cortex-vortex", revision="1.1.2",
                     uuid="f1a619f0-9176-5e75-ad96-00db77d8cf2b", display_name="Cortex Vortex", author="Lockheart")
        saphi["files"] = [dict(f, sha256=h * 32) for f, h in zip(saphi["files"], ("aa", "bb"))]
        return saphi

    def test_a_downloaded_cortex_vortex_with_the_bundled_one_is_refused(self):
        # A tester report (alpha2, 2026-11-04): a seed had two Cortex Vortex pads,
        # the bundled track and a downloaded copy listed in custom_tracks.
        for required in (True, False):
            with self.subTest(own_pad=required), self.assertRaises(OptionError) as caught:
                make_world(cv_options(custom=[self.saphi_cortex_vortex()], required=required), seed=6)
            message = str(caught.exception)
            self.assertIn("package/cortex-vortex/1.1.2", message)
            self.assertIn("one Cortex Vortex", message)

    def swap_options(self, pinned=False):
        """`cortex_vortex_track: off` and a downloaded copy listed with the other tracks;
        `pinned` also puts the copy in `required_entries`."""
        custom = [copy.deepcopy(content_plan.PACKAGES[1]), copy.deepcopy(UNKNOWN), relic_named(),
                  self.saphi_cortex_vortex()]
        options = cv_options(cortex=False, custom=custom)
        required = options["content_pool"]["required_entries"]
        if not pinned:
            required.remove("custom/cortex-vortex/1.1.2")
        return options

    def test_the_bundled_cortex_vortex_replaces_a_downloaded_copy_when_the_option_is_off(self):
        # Ruling of 2026-11-05: "Bundled replaces it". Same pool as in_pool with the copy removed.
        drawn = 0
        for seed in range(12):
            world = make_world(self.swap_options(), seed=seed)
            plan = world.ctr_content_plan
            ids = {t["id"] for t in plan["tracks"]}
            self.assertNotIn("custom/cortex-vortex/1.1.2", ids)
            self.assertNotIn("package/cortex-vortex/1.1.2", {p["id"] for p in plan["packages"]})
            self.assertNotIn("Cortex Vortex (Custom)", json.dumps(plan))
            self.assertEqual(world.options.cortex_vortex_track.value, content_plan.CORTEX_IN_POOL)
            self.assertEqual(world.ctr_cortex_swap, ["package/cortex-vortex/1.1.2"])
            self.assertIn("package/north-pole/1.1.0", {p["id"] for p in plan["packages"]})
            if CV in ids:
                drawn += 1
                self.assertEqual(track_of(plan, CV)["package_id"], "bundled/cortex-vortex")
        self.assertGreater(drawn, 0)

    def test_a_required_downloaded_copy_becomes_the_own_pad_bundled_track(self):
        for seed in range(4):
            world = make_world(self.swap_options(pinned=True), seed=seed)
            self.assertEqual(world.options.cortex_vortex_track.value, content_plan.CORTEX_OWN_PAD)
            self.assertIn(CV, {t["id"] for t in world.ctr_content_plan["tracks"]})
            self.assertEqual(world.ctr_cortex_swap_mode, "own_pad")

    def test_the_swap_matches_in_pool_without_the_copy(self):
        swapped = make_world(self.swap_options(), seed=4).ctr_content_plan
        options = self.swap_options()
        options["content_pool"]["tracks"]["custom"].pop()
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        plain = make_world(options, seed=4).ctr_content_plan
        self.assertEqual(json.dumps(swapped, sort_keys=True), json.dumps(plain, sort_keys=True))

    def test_a_track_mode_override_on_the_copy_carries_over(self):
        # The test options name tracks by id; the copy's id reaches the generator as its key "cortex-vortex".
        options = self.swap_options(pinned=True)
        options["content_pool"]["tracks"]["overrides"] = {"custom/cortex-vortex/1.1.2": ["relic"]}
        plan = make_world(options, seed=3).ctr_content_plan
        self.assertEqual(track_of(plan, CV)["modes"], ["relic"])
        # An override under a renamed copy's own title carries over too.
        options = self.swap_options(pinned=True)
        options["content_pool"]["tracks"]["custom"][-1]["display_name"] = "Cortex Vortex Remix"
        world = make_world(options, seed=3, stop_before="generate_early")
        world.options.track_modes.value = {"default": ["trophy", "ctr", "relic"], "Cortex Vortex Remix": ["relic"]}
        content_plan.swap_in_bundled_cortex(world)
        self.assertEqual(world.options.track_modes.value["Cortex Vortex"], ["relic"])
        self.assertNotIn("Cortex Vortex Remix", world.options.track_modes.value)
        content_plan.generate(world)
        self.assertEqual(track_of(world.ctr_content_plan, CV)["modes"], ["relic"])

    def test_the_swap_is_written_to_the_spoiler(self):
        import io
        out = io.StringIO()
        make_world(self.swap_options(), seed=6).write_spoiler(out)
        self.assertIn("downloaded copy (package/cortex-vortex/1.1.2) was replaced", out.getvalue())
        self.assertIn("(cortex_vortex_track in_pool)", out.getvalue())
        out = io.StringIO()
        make_world(cv_options(cortex=False), seed=6).write_spoiler(out)
        self.assertNotIn("was replaced by the Cortex Vortex", out.getvalue())

    def test_the_tracker_restores_a_swapped_seed(self):
        from NetUtils import convert_to_base_types
        world = make_world(self.swap_options(), seed=2)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        for options in ({}, self.swap_options()):
            tracker = make_world(options, seed=999, passthrough=convert_to_base_types(wire))
            self.assertEqual(tracker.ctr_content_plan, world.ctr_content_plan)
            self.assertEqual(tracker.fill_slot_data(), wire)


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
                tiers = content_plan.plan_relics(plan, track)
                if not tiers:
                    continue
                sapphire = mw.get_location(content_plan.mode_checks(track, "relic", tiers)[0][1], 1)
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
