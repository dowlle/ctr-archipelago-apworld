"""Sanity picks, route ownership, admission, permanent names and Tracker."""
import copy
import json
import unittest

from Options import OptionError
from .. import content_plan, sanity
from ..Options import Itemboxsanity, Wumpasanity
from .test_content_plan import make_world, profile_options


class TestSanity(unittest.TestCase):
    def world(self, **options):
        return make_world(dict(profile_options(), **options), seed=3)

    def test_option_bounds(self):
        self.assertEqual(Itemboxsanity.default, 0)
        self.assertEqual(Wumpasanity.default, 0)
        for value in (-1, 51):
            with self.assertRaises(Exception):
                Itemboxsanity.from_any(value)

    def test_defaults_omit_record_and_features(self):
        a = self.world().fill_slot_data()
        b = self.world(itemboxsanity=0, wumpasanity="off").fill_slot_data()
        self.assertEqual(a, b)
        self.assertNotIn("sanity", a["content_plan"])
        self.assertFalse(set(sanity.FEATURES) & set(a["content_plan"]["required_features"]))

    def test_counts_modes_and_tracker(self):
        for boxes, wumpa, ap_boxes in ((5, "off", 0), (50, "off", 50), (0, "both", 0), (50, "both", 50)):
            with self.subTest(boxes=boxes, wumpa=wumpa, ap_boxes=ap_boxes):
                world = self.world(itemboxsanity=boxes, wumpasanity=wumpa, item_box_count=ap_boxes)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                for row in plan["sanity"]["tracks"]:
                    if row["track_id"].startswith("retail:"):
                        self.assertEqual(len(row["weapon_crate"]), min(boxes, row["counts"][0]))
                        self.assertEqual(len(row["wumpa_crate"]), row["counts"][1] if wumpa == "both" else 0)
                        self.assertEqual(len(row["wumpa_fruit"]), row["counts"][2] if wumpa == "both" else 0)
                wire = json.loads(json.dumps(world.fill_slot_data()))
                tracker = make_world(profile_options(), passthrough=wire)
                self.assertEqual(tracker.ctr_content_plan, plan)
                self.assertEqual(tracker.options.itemboxsanity.value, boxes)
                self.assertEqual(tracker.options.wumpasanity.value, Wumpasanity.from_any(wumpa).value)

    def test_pick_is_stable_and_does_not_follow_ap_box_count(self):
        plans = [self.world(itemboxsanity=5, item_box_count=n).ctr_content_plan for n in (0, 5, 50)]
        retail = lambda p: [r for r in p["sanity"]["tracks"] if r["track_id"].startswith("retail:")]
        self.assertEqual(retail(plans[0]), retail(plans[1]))
        self.assertEqual(retail(plans[0]), retail(plans[2]))
        self.assertTrue(any(r["weapon_crate"] != list(range(1, 6)) for r in retail(plans[0])))

    def test_named_budget_and_identity_freeze(self):
        names = sanity.SANITY_CLASS.name_to_code()
        self.assertEqual(len(names), len(set(names.values())))
        for t in sanity.destinations.NAMED_TRACKS:
            for suffix, count in zip(sanity.SUFFIXES, sanity.BUDGETS):
                self.assertIn(f"{t.ap_name}: {suffix} {count}", names)
        self.assertFalse(any(n.startswith("Custom Track ") for n in names))

    def test_tampered_pick_counts_routes_and_feature_refused(self):
        original = self.world(itemboxsanity=5, wumpasanity="both").ctr_content_plan
        for mutation in ("ordinal", "counts", "hash", "route", "feature", "missing"):
            plan = copy.deepcopy(original)
            if mutation == "ordinal":
                plan["sanity"]["tracks"][0]["weapon_crate"][0] = 81
            elif mutation == "counts":
                plan["sanity"]["tracks"][0]["counts"][0] += 1
            elif mutation == "hash":
                plan["sanity"]["tracks"][0]["lev_sha256"] = "0" * 64
            elif mutation == "route":
                next(c for c in plan["checks"] if c["kind"] in sanity.KINDS)["routes"][0]["award"] = "box"
            elif mutation == "feature":
                plan["required_features"].remove(sanity.FEATURES[0])
            else:
                del plan["sanity"]
            with self.subTest(mutation=mutation), self.assertRaises(OptionError):
                content_plan.validate(plan)

    def test_geometry_pending_review_is_usf(self):
        self.assertEqual(sanity.CATALOG["retail:7"]["needs"]["wumpa_crate"]["4"]["needs"], "usf")
        self.assertEqual(sanity.CATALOG["retail:6"]["needs"]["weapon_crate"]["9"]["needs"], "usf")

    def test_usf_rank_and_tiger_door_terms(self):
        from .test_capability_packs import first_world
        options = dict(profile_options(), itemboxsanity=50, wumpasanity="both", itemsanity=True,
                       progressive_boost="shared_global", progressive_boost_blue_fire=True)
        world = first_world(options, seed=3)
        checks = {c["display_name"]: c for c in world.ctr_content_plan["checks"]}
        for name in ("Hot Air Skyway: Wumpa Crate 4", "Roo's Tubes: Weapon Crate 9"):
            self.assertEqual(checks[name]["boost"], 2)  # USF, not the optional Blue Fire rank.
        for n in (5, 6, 7, 8):
            name = f"Tiger Temple: Wumpa Crate {n}"
            self.assertTrue(sanity.CATALOG["retail:4"]["needs"]["wumpa_crate"][str(n)]["door"])
            self.assertEqual(checks[name]["boost"], 2)

    def test_cup_and_boss_routes_precede_own_pad(self):
        from .test_27_cups import cups_options
        world = make_world(cups_options(itemboxsanity=5, wumpasanity="both"), seed=1)
        checks = [c for c in world.ctr_content_plan["checks"] if c["kind"] in sanity.KINDS]
        self.assertTrue(checks)
        self.assertTrue(any(any(r["mode"] == "boss_race" for r in c["routes"]) for c in checks))
        self.assertTrue(all(r["mode"] in ("cup", "boss_cup", "boss_race") for c in checks for r in c["routes"]))
        self.assertTrue(content_plan.validate(world.ctr_content_plan))

    def test_location_exclusion_groups(self):
        from .. import ctrAPWorld
        for group, suffix in (("Weapon Crates", "Weapon Crate "), ("Wumpa Crates", "Wumpa Crate "),
                              ("Loose Wumpa Fruit", "Wumpa Fruit ")):
            names = ctrAPWorld.location_name_groups[group]
            self.assertTrue(names)
            self.assertTrue(all(suffix in n for n in names))
