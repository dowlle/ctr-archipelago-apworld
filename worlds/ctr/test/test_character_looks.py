"""Character looks (JL2): look items are repeatable filler, pooled only when the
YAML lists them, and never change generation when the list is empty."""
import json
import random
import unittest
from types import SimpleNamespace

from BaseClasses import ItemClassification
from . import CTRTestBase
from .test_content_plan import make_world, profile_options
from .. import character_looks
from ..Options import CharacterLooks
from ..minted_items_030 import MINTED_ITEMS_030
from ..wumpa_family import draw_filler_name, filler_weights


def fake(looks=(), top_up=False, bundles=False, seed=215):
    return SimpleNamespace(options=SimpleNamespace(
        reserve_top_up=SimpleNamespace(value=top_up),
        wumpa_bundles=SimpleNamespace(value=bundles),
        character_looks=SimpleNamespace(value=set(looks))), random=random.Random(seed))


class TestLookItem(unittest.TestCase):
    def test_joe_mama_is_minted_filler_at_35010215(self):
        self.assertIn(("Joe Mama", 35010215, ItemClassification.filler), MINTED_ITEMS_030)

    def test_option_keys_are_the_look_table(self):
        self.assertEqual(set(CharacterLooks.valid_keys), set(character_looks.LOOKS))
        self.assertEqual(CharacterLooks.default, frozenset())

    def test_every_look_is_a_minted_filler_item(self):
        minted = {name: cls for name, _code, cls in MINTED_ITEMS_030}
        for look in character_looks.LOOKS:
            self.assertEqual(minted.get(look), ItemClassification.filler)


class TestFillerWeights(unittest.TestCase):
    def test_empty_list_changes_nothing(self):
        self.assertEqual(filler_weights(fake()), {"Wumpa Fruit": 1})
        self.assertEqual(filler_weights(fake(top_up=True)), {"Wumpa Fruit": 6, "Reserve Top-Up": 1})
        self.assertEqual(filler_weights(fake(top_up=True, bundles=True)),
                         {"Wumpa Fruit": 6, "Small Wumpa Bundle": 3, "Big Wumpa Bundle": 1, "Reserve Top-Up": 1})

    def test_empty_list_without_bundles_consumes_no_rng(self):
        world = fake()
        world.random = None
        self.assertEqual(draw_filler_name(world), "Wumpa Fruit")

    def test_each_look_at_weight_one_after_the_existing_names(self):
        weights = filler_weights(fake(["Joe Mama"], top_up=True, bundles=True))
        self.assertEqual(list(weights), ["Wumpa Fruit", "Small Wumpa Bundle", "Big Wumpa Bundle",
                                         "Reserve Top-Up", "Joe Mama"])
        self.assertEqual(weights["Joe Mama"], 1)
        self.assertEqual(filler_weights(fake(["Joe Mama"])), {"Wumpa Fruit": 6, "Joe Mama": 1})

    def test_unknown_names_are_ignored(self):
        self.assertEqual(filler_weights(fake(["Joe Biden"])), {"Wumpa Fruit": 1})

    def test_repeatable_weighted_draw(self):
        a, b = fake(["Joe Mama"]), fake(["Joe Mama"])
        results = [draw_filler_name(a) for _ in range(7000)]
        self.assertEqual(results, [draw_filler_name(b) for _ in range(7000)])
        self.assertLess(abs(results.count("Joe Mama") - 1000), 130)


class TestLooksOn(CTRTestBase):
    options = {"character_looks": ["Joe Mama"], "box_locations": True}

    def test_copies_in_the_pool_and_the_wire(self):
        copies = [i for i in self.multiworld.itempool if i.name == "Joe Mama"]
        self.assertGreater(len(copies), 1, "repeatable filler: more than one copy on a box seed")
        self.assertEqual({(i.code, i.classification) for i in copies}, {(35010215, ItemClassification.filler)})
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))
        self.assertEqual(self.world.fill_slot_data()["ctr_options"]["character_looks"], ["Joe Mama"])

    def test_item_group(self):
        self.assertEqual(self.world.item_name_groups["Character Looks"], {"Joe Mama"})
        self.assertIn("Joe Mama", self.world.item_name_groups["Filler"])


class TestLooksOff(CTRTestBase):
    options = {"box_locations": True}

    def test_no_copies_and_no_wire_key(self):
        self.assertNotIn("Joe Mama", {i.name for i in self.multiworld.itempool})
        self.assertNotIn("character_looks", self.world.fill_slot_data()["ctr_options"])


class TestTrapPrecedence(CTRTestBase):
    run_default_tests = False
    options = {"character_looks": ["Joe Mama"], "trap_fill_percentage": 100, "box_locations": True}

    def test_traps_take_the_filler_budget_first(self):
        self.assertNotIn("Joe Mama", {i.name for i in self.multiworld.itempool})


class TestTrackerAndContentPlan(unittest.TestCase):
    def test_tracker_restore_on_and_absent(self):
        for profile in ({}, profile_options()):
            for looks in ([], ["Joe Mama"]):
                with self.subTest(content_plan=bool(profile), looks=looks):
                    world = make_world(dict(profile, character_looks=looks, box_locations=True), seed=215)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    other = [] if looks else ["Joe Mama"]
                    restored = make_world({"character_looks": other, "box_locations": True}, seed=999,
                                          passthrough=wire)
                    restored_wire = restored.fill_slot_data()
                    self.assertEqual(restored_wire["ctr_options"].get("character_looks", []), looks)
                    self.assertEqual(sorted(restored.options.character_looks.value), looks)
                    if profile:
                        self.assertEqual(restored_wire, wire)
                    if not looks:
                        self.assertNotIn("Joe Mama", {i.name for i in restored.multiworld.itempool})

    def test_content_plan_draws_looks(self):
        names = set()
        for seed in range(10):
            world = make_world(dict(profile_options(), character_looks=["Joe Mama"]), seed=seed)
            self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))
            names.update(i.name for i in world.multiworld.itempool)
        self.assertIn("Joe Mama", names)

    def test_empty_list_is_generation_neutral(self):
        for seed in (1, 215, 4088):
            with self.subTest(seed=seed):
                base = make_world({"box_locations": True}, seed=seed)
                empty = make_world({"box_locations": True, "character_looks": []}, seed=seed)
                self.assertEqual(json.dumps(base.fill_slot_data(), sort_keys=True),
                                 json.dumps(empty.fill_slot_data(), sort_keys=True))
                self.assertEqual([i.name for i in base.multiworld.itempool],
                                 [i.name for i in empty.multiworld.itempool])
