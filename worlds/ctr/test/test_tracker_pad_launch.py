"""Tracker pad launch (#375): a presentation and input option with no logic.

Pins the default (on), the always-emitted Boolean on ordinary and
content-plan rooms, the Universal Tracker restore from on, off, absent and
non-Boolean wire data, and that turning it off changes nothing but the
emitted Boolean: same locations, items, rules and placements.
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive

from .. import tracker_pad_launch
from ..Options import TrackerPadLaunch
from .test_content_plan import make_world, profile_options

KEY = tracker_pad_launch.WIRE_KEY
ORDINARY = {"accessibility": "full"}


def placements(world):
    distribute_items_restrictive(world.multiworld)
    return sorted((loc.name, loc.item.name if loc.item else None)
                  for loc in world.multiworld.get_locations(world.player))


class TestOption(unittest.TestCase):
    def test_default_on(self):
        self.assertEqual(TrackerPadLaunch.default, 1)
        world = make_world(ORDINARY, seed=375)
        self.assertTrue(world.options.tracker_pad_launch.value)
        self.assertIs(world.fill_slot_data()["ctr_options"][KEY], True)

    def test_emitted_both_ways(self):
        for profile in (ORDINARY, profile_options()):
            for enabled in (False, True):
                with self.subTest(content_plan="content_pool" in profile, enabled=enabled):
                    world = make_world(dict(profile, tracker_pad_launch=enabled), seed=375)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    self.assertIs(wire["ctr_options"][KEY], enabled)
                    self.assertEqual(wire["ctr_options"]["schema_version"], 18)


class TestNoLogic(unittest.TestCase):
    def test_on_and_off_generate_the_same_seed(self):
        for profile in (ORDINARY, dict(ORDINARY, box_locations=True, lettersanity=1),
                        profile_options()):
            for seed in (1, 2, 3):
                with self.subTest(content_plan="content_pool" in profile, seed=seed):
                    on = make_world(dict(profile, tracker_pad_launch=True), seed=seed)
                    off = make_world(dict(profile, tracker_pad_launch=False), seed=seed)
                    self.assertEqual(sorted(i.name for i in on.multiworld.itempool),
                                     sorted(i.name for i in off.multiworld.itempool))
                    self.assertEqual(placements(on), placements(off))
                    wire_on = json.loads(json.dumps(on.fill_slot_data()))
                    wire_off = json.loads(json.dumps(off.fill_slot_data()))
                    self.assertIs(wire_on["ctr_options"].pop(KEY), True)
                    self.assertIs(wire_off["ctr_options"].pop(KEY), False)
                    self.assertEqual(wire_on, wire_off)

    def test_no_rule_reads_it(self):
        world = make_world(dict(ORDINARY, tracker_pad_launch=False), seed=7)
        state = CollectionState(world.multiworld)
        for item in world.multiworld.itempool:
            if item.advancement:
                state.collect(item, True)
        state.sweep_for_advancements()
        for location in world.multiworld.get_locations(1):
            self.assertTrue(location.can_reach(state), location.name)


class TestTrackerRestore(unittest.TestCase):
    def test_on_off_absent_and_invalid(self):
        for profile in (ORDINARY, profile_options()):
            for enabled in (False, True):
                with self.subTest(content_plan="content_pool" in profile, enabled=enabled):
                    world = make_world(dict(profile, tracker_pad_launch=enabled), seed=375)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    restored = make_world(dict(profile, tracker_pad_launch=not enabled), seed=999,
                                          passthrough=copy.deepcopy(wire))
                    self.assertEqual(bool(restored.options.tracker_pad_launch.value), enabled)
                    self.assertIs(restored.fill_slot_data()["ctr_options"][KEY], enabled)
                    self.assertEqual(sorted(l.address for l in restored.multiworld.get_locations(1) if l.address),
                                     sorted(l.address for l in world.multiworld.get_locations(1) if l.address))
        world = make_world(ORDINARY, seed=375)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        for value in ("absent", 1, "true"):
            with self.subTest(value=value):
                bad = copy.deepcopy(wire)
                if value == "absent":
                    bad["ctr_options"].pop(KEY)
                else:
                    bad["ctr_options"][KEY] = value
                restored = make_world(dict(ORDINARY, tracker_pad_launch=True), seed=999, passthrough=bad)
                self.assertFalse(restored.options.tracker_pad_launch.value)


if __name__ == "__main__":
    unittest.main()
