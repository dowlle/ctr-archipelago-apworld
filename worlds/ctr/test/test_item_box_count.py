"""Count, compatibility, 50-spot capacity and Tracker admission."""
import contextlib
import copy
import hashlib
import json
import random
import unittest
from unittest import mock

from Options import OptionError
from .. import box_spots, content_plan
from ..Options import ItemBoxCount
from .test_content_item_boxes import box_options, boxes, first_world, btp
from .test_content_plan import make_world


@contextlib.contextmanager
def fifty_spots(custom=False):
    """Synthetic capacity fixture only, never a shipped placement."""
    entry = copy.deepcopy(box_spots.RETAIL_FILES[3])
    entry["doc"]["spots"] = [dict(number=n, pos=[n * 10, 0, n * 20], rot_y=0, needs="none")
                              for n in range(1, 51)]
    entry["sha256"] = hashlib.sha256(json.dumps(entry["doc"]).encode()).hexdigest()
    named = copy.deepcopy(entry)
    named["doc"]["track"] = dict(track_key="baby-t-park", lev_sha256=[box_spots.lev_pin(btp())])
    with mock.patch.dict(box_spots.RETAIL_FILES, {3: entry}), mock.patch.dict(
            box_spots.CUSTOM_FILES, {"baby-t-park": named} if custom else {}):
        yield


def count_world(count):
    return first_world(box_options(item_box_count=count, shortcut_knowledge="hard"), seed=3)


class TestItemBoxCount(unittest.TestCase):
    def test_bounds_and_default(self):
        self.assertEqual(ItemBoxCount.default, 15)
        for count in (-1, 51):
            with self.assertRaises(Exception):
                ItemBoxCount.from_any(count)

    def test_yaml_migration(self):
        from ..legacy_yaml import migrate_box_count
        self.assertEqual(migrate_box_count({"box_locations": False}), {"item_box_count": 0})
        self.assertEqual(migrate_box_count({"box_locations": True}), {"item_box_count": 15})
        self.assertEqual(migrate_box_count({"box_locations": {False: 2, True: 3}}), {"item_box_count": {0: 2, 15: 3}})
        self.assertEqual(migrate_box_count({"box_locations": False, "item_box_count": 15}), {"item_box_count": 15})

    def test_yaml_roll_migrates_before_the_new_option(self):
        from .test_legacy_yaml import _roll
        for raw, expected in ((False, 0), (True, 15), ({False: 1, True: 0}, 0), ({False: 0, True: 1}, 15)):
            self.assertEqual(_roll({"box_locations": raw}).item_box_count.value, expected)
        self.assertEqual(_roll({"box_locations": False, "item_box_count": 15}).item_box_count.value, 15)

    def test_legacy_switch_and_new_default(self):
        off = first_world(box_options(box_locations=False)).fill_slot_data()
        self.assertNotIn("item_boxes", off["content_plan"])
        self.assertNotIn("item_box_count", off["ctr_options"])
        new = box_options()
        new.pop("box_locations")
        new["box_locations"] = -1  # bypass the old-scenario test adapter
        self.assertEqual(first_world(new).options.item_box_count.value, 15)
        self.assertEqual(first_world(box_options(box_locations=False, item_box_count=1)).options.item_box_count.value, 1)

    def test_default_pick_keeps_original_key_and_algorithm(self):
        for seed in range(100):
            numbers = list(range(1, 51))
            key = f"{seed}:1:box_spots:retail:3".encode()
            expected = sorted(random.Random(int.from_bytes(hashlib.sha256(key).digest(), "big")).sample(numbers, 15))
            self.assertEqual(box_spots.pick(numbers, seed, 1, "retail:3", 15), expected)

    def test_counts_and_tracker(self):
        with fifty_spots():
            for count in (0, 1, 15, 50):
                with self.subTest(count=count):
                    world = count_world(count)
                    plan = world.ctr_content_plan
                    own = boxes(plan, "retail:3")
                    self.assertEqual(len(own), count)
                    if count:
                        fallback = boxes(plan, "custom/baby-t-park/1.0.2")
                        self.assertEqual(len(fallback), min(count, 8))
                        self.assertEqual("box_count" in plan["item_boxes"], count != 15)
                        self.assertEqual("box_count_v1" in plan["required_features"], count != 15)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    restored = make_world({}, seed=999, passthrough=wire)
                    self.assertEqual(restored.fill_slot_data(), wire)
                    self.assertEqual(restored.options.item_box_count.value, count)

    def test_forged_counts_and_picks_refused(self):
        with fifty_spots():
            wire = count_world(50).fill_slot_data()
            for value in (0, 15, 51, True, "50"):
                forged = copy.deepcopy(wire)
                forged["content_plan"]["item_boxes"]["box_count"] = value
                with self.assertRaises(OptionError):
                    make_world({}, passthrough=forged)
            forged = copy.deepcopy(wire)
            forged["ctr_options"]["item_box_count"] = 1
            with self.assertRaises(OptionError):
                make_world({}, passthrough=forged)

    def test_named_track_uses_fifty_spots(self):
        with fifty_spots(custom=True):
            world = count_world(50)
            self.assertEqual(len(boxes(world.ctr_content_plan, "custom/baby-t-park/1.0.2")), 50)
            wire = world.fill_slot_data()
            self.assertEqual(make_world({}, passthrough=wire).fill_slot_data(), wire)
            forged = copy.deepcopy(wire)
            forged["content_plan"]["required_features"].remove("box_count_v1")
            with self.assertRaises(OptionError):
                make_world({}, passthrough=forged)
            forged = copy.deepcopy(wire)
            forged["content_plan"]["item_boxes"]["spot_sets"][0]["picked"].pop()
            with self.assertRaises(OptionError):
                make_world({}, passthrough=forged)
