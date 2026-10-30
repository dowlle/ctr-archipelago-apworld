"""Reserve Top-Up spends existing filler slots and never gates reachability."""
import json
import random
import unittest
from types import SimpleNamespace

from BaseClasses import ItemClassification
from . import CTRTestBase
from .test_content_plan import make_world, profile_options
from ..wumpa_family import draw_filler_name, filler_weights


def fake(enabled, bundles=False, seed=451):
    return SimpleNamespace(options=SimpleNamespace(
        reserve_top_up=SimpleNamespace(value=enabled),
        wumpa_bundles=SimpleNamespace(value=bundles)), random=random.Random(seed))


class TestFillerWeights(unittest.TestCase):
    def test_reviewed_weights(self):
        self.assertEqual(filler_weights(fake(True)), {"Wumpa Fruit": 6, "Reserve Top-Up": 1})
        self.assertEqual(filler_weights(fake(True, True)),
                         {"Wumpa Fruit": 6, "Small Wumpa Bundle": 3,
                          "Big Wumpa Bundle": 1, "Reserve Top-Up": 1})
        self.assertEqual(filler_weights(fake(False)), {"Wumpa Fruit": 1})
        self.assertEqual(filler_weights(fake(False, True)),
                         {"Wumpa Fruit": 6, "Small Wumpa Bundle": 3, "Big Wumpa Bundle": 1})

    def test_off_without_bundles_consumes_no_rng(self):
        world = fake(False)
        world.random = None
        self.assertEqual(draw_filler_name(world), "Wumpa Fruit")

    def test_deterministic_weighted_draw(self):
        a, b = fake(True), fake(True)
        results = [draw_filler_name(a) for _ in range(7000)]
        self.assertEqual(results, [draw_filler_name(b) for _ in range(7000)])
        self.assertLess(abs(results.count("Reserve Top-Up")-1000), 130)


class TestReserveOn(CTRTestBase):
    options = {"reserve_top_up": True, "box_locations": True}

    def test_minted_filler_is_drawn_and_balanced(self):
        copies = [i for i in self.multiworld.itempool if i.name == "Reserve Top-Up"]
        self.assertTrue(copies)
        self.assertEqual({(i.code, i.classification) for i in copies},
                         {(35010203, ItemClassification.filler)})
        self.assertEqual(len(self.multiworld.itempool),
                         len(self.multiworld.get_unfilled_locations(self.player)))
        self.assertTrue(self.world.fill_slot_data()["ctr_options"]["reserve_top_up"])


class TestReserveOff(CTRTestBase):
    options = {"reserve_top_up": False}

    def test_no_new_filler(self):
        self.assertNotIn("Reserve Top-Up", {i.name for i in self.multiworld.itempool})
        self.assertFalse(self.world.fill_slot_data()["ctr_options"]["reserve_top_up"])


class TestTrapPrecedence(CTRTestBase):
    run_default_tests = False
    options = {"reserve_top_up": True, "trap_fill_percentage": 100, "box_locations": True}

    def test_traps_take_the_filler_budget_first(self):
        self.assertNotIn("Reserve Top-Up", {i.name for i in self.multiworld.itempool})
        self.assertTrue(any(i.classification == ItemClassification.trap for i in self.multiworld.itempool))


class TestTrackerAndContentPlan(unittest.TestCase):
    def test_tracker_on_off_and_absent(self):
        for profile in ({}, profile_options()):
            for enabled in (False, True):
                with self.subTest(content_plan=bool(profile), enabled=enabled):
                    options = dict(profile, reserve_top_up=enabled)
                    world = make_world(options, seed=451)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    restored = make_world({"reserve_top_up": not enabled}, seed=999, passthrough=wire)
                    restored_wire = restored.fill_slot_data()
                    self.assertEqual(restored_wire["ctr_options"]["reserve_top_up"], enabled)
                    if profile:
                        self.assertEqual(restored_wire, wire)
                    self.assertEqual(sorted(l.address for l in restored.multiworld.get_locations(1) if l.address),
                                     sorted(l.address for l in world.multiworld.get_locations(1) if l.address))
                    self.assertEqual(bool(restored.options.reserve_top_up.value), enabled)
                    # The real generation's pre_fill may place start openers
                    # (sphere0_guard.bootstrap_start); the tracker skips pre_fill.
                    placed = len(getattr(world, "_ctr_start_bootstrap", ()))
                    self.assertEqual(len(restored.multiworld.itempool), len(world.multiworld.itempool) + placed)
                    if not enabled:
                        self.assertNotIn("Reserve Top-Up", {i.name for i in restored.multiworld.itempool})
                    wire["ctr_options"].pop("reserve_top_up")
                    old = make_world({"reserve_top_up": True}, seed=999, passthrough=wire)
                    self.assertFalse(old.fill_slot_data()["ctr_options"]["reserve_top_up"])

    def test_content_plan_uses_the_common_filler_draw(self):
        names = set()
        for seed in range(20):
            world = make_world(dict(profile_options(), reserve_top_up=True), seed=seed)
            self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))
            names.update(i.name for i in world.multiworld.itempool)
        self.assertIn("Reserve Top-Up", names)
