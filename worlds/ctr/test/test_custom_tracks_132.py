"""Up to 132 custom tracks per YAML: the generic slots.

A seed gives each listed package a slot by sorted id and carries the packages it
races. Slots 1 to 32 keep their live ids; 33 to 132 use the race family v2 ids
and the families reserved for all 132 slots. Every id already exists, so this
only opens the limit.
"""
import copy
import json
import pathlib
import unittest

from .. import content_plan, content_wumpa, custom_packages
from ..Locations import CTR_LOCATION_IDS
from ..custom_check_namespace import CUSTOM_SLOT_COUNT
from .test_content_plan import make_world, profile_options
from .test_custom_packages import UNKNOWN, options_with

SCHEMA = pathlib.Path(content_plan.__file__).with_name("data") / "content-plan-v1.schema.json"
RETAIL_TRACKS = 18


def fixture(index, **capabilities):
    d = copy.deepcopy(UNKNOWN)
    key = f"fixture-{index:03d}"
    d.update(id=f"package/{key}/1.0", content_id=key, revision="1.0", display_name=f"Fixture {index:03d}",
             uuid=f"0f0e0d0c-0b0a-4908-8706-{index:012x}")
    d["capabilities"].update(ctr_tokens=True, wumpa=True, **capabilities)
    d["files"][0]["sha256"] = f"{index:064x}"
    d["files"][1]["sha256"] = f"{index + 1000:064x}"
    return d


def fixtures(count):
    return [fixture(i) for i in range(1, count + 1)]


def many_cups(count=27):
    """Every normal pad a cup: the most tracks one plan can race."""
    options = options_with(fixtures(132), required=[])
    options["content_pool"]["cups"] = dict(count=dict(min=count, max=count), composition=dict(
        custom_legs=dict(min=0, max=4), legs="random"))
    options["content_pool"]["crystal_challenges"] = dict(min=0, max=0)
    return options


class TestLimit(unittest.TestCase):
    def test_the_limit_is_the_generic_slot_count(self):
        self.assertEqual(custom_packages.MAX_PACKAGES, CUSTOM_SLOT_COUNT)
        self.assertEqual(len(custom_packages.admit_all(fixtures(132))), 132)
        with self.assertRaisesRegex(custom_packages.PackageError, "at most 132"):
            custom_packages.admit_all(fixtures(133))

    def test_the_schema_holds_every_track_of_a_full_seed(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["packages"]["maxItems"], custom_packages.MAX_PACKAGES)
        self.assertEqual(schema["properties"]["tracks"]["maxItems"], RETAIL_TRACKS + custom_packages.MAX_PACKAGES + 1)


class TestHighSlots(unittest.TestCase):
    def test_a_slot_above_32_races_on_its_frozen_ids(self):
        last = fixtures(132)
        required = [f"custom/{d['content_id']}/{d['revision']}" for d in last[-4:]]
        plan = make_world(options_with(last, required)).ctr_content_plan
        self.assertTrue(content_plan.validate(plan))
        slots = {t["custom_slot"]: t for t in plan["tracks"] if t.get("origin") == "custom"}
        self.assertLessEqual({129, 130, 131, 132}, set(slots))
        checks = {c["location"] for c in plan["checks"]}
        self.assertIn(CTR_LOCATION_IDS["Custom Track 132: Trophy Race"], checks)
        self.assertEqual(CTR_LOCATION_IDS["Custom Track 132: Trophy Race"], 35019000 + 6 * 131)

    def test_validate_refuses_a_slot_past_the_last(self):
        plan = make_world(options_with(fixtures(2))).ctr_content_plan
        forged = copy.deepcopy(plan)
        track = next(t for t in forged["tracks"] if t.get("origin") == "custom")
        track["custom_slot"] = 133
        with self.assertRaises(Exception):
            content_plan.validate(forged)

    def test_the_most_tracks_one_plan_can_race(self):
        world = make_world(many_cups())
        plan = world.ctr_content_plan
        self.assertTrue(content_plan.validate(plan))
        custom = [t for t in plan["tracks"] if t.get("origin") == "custom"]
        # More than the 64 tracks a plan could hold before, and each on its own slot.
        self.assertGreater(len(plan["tracks"]), 64)
        self.assertEqual(len({t["custom_slot"] for t in custom}), len(custom))
        self.assertEqual({p["id"] for p in plan["packages"]}, {t["package_id"] for t in custom})


class TestShopIncome(unittest.TestCase):
    def test_a_long_list_keeps_a_track_that_banks_fruit(self):
        # The Wumpa Shop is on by default and needs a retail race on a pad; with
        # 132 custom tracks a plain draw left none on 35 of 1,000 seeds.
        options = options_with(fixtures(132), required=[])
        options["wumpa_shop_slots"] = 10
        for seed in range(40):
            with self.subTest(seed=seed):
                plan = make_world(options, seed=seed).ctr_content_plan
                self.assertTrue(content_wumpa.income_routes(plan))

    def test_a_seed_with_an_income_track_draws_as_before(self):
        retail = dict(id="retail:0", origin="retail", retail_id=0, modes=["trophy"])
        slide = dict(id="retail:16", origin="retail", retail_id=16, modes=["trophy"])
        custom = dict(id="custom/x/1", origin="custom", modes=["trophy"])

        class World:
            class options:
                class wumpa_shop_slots:
                    value = 10

                class goal_wumpa:
                    value = 0
            random = None

        self.assertEqual(content_wumpa.keep_income_track(World, [retail, custom], [custom], [custom]), [custom])
        World.options.wumpa_shop_slots.value = 0
        self.assertEqual(content_wumpa.keep_income_track(World, [custom], [custom], [custom, retail]), [custom])
        World.options.wumpa_shop_slots.value = 10
        self.assertEqual(content_wumpa.keep_income_track(World, [custom], [custom], [custom, slide]), [custom])
