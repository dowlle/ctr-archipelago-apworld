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


class TestRollsKeepTheirAlphabet(unittest.TestCase):
    """With no looks enabled, random name rolls and group draws roll the same
    names as before the look items existed."""

    def test_legacy_view_leaves_looks_out_of_rolls_and_shared_groups(self):
        from .. import ctrAPWorld
        from ..track_origins import legacy_option_world
        view = legacy_option_world(ctrAPWorld)
        self.assertNotIn("Joe Mama", view.item_names)
        self.assertNotIn("Joe Mama", view.item_name_groups["Filler"])
        self.assertNotIn("Joe Mama", view.item_name_groups["Everything"])
        self.assertEqual(set(view.item_name_groups["Character Looks"]), {"Joe Mama"})
        self.assertIn("Joe Mama", ctrAPWorld.item_name_groups["Filler"])

    def test_filler_group_plando_rolls_as_before(self):
        from BaseClasses import PlandoOptions
        from Options import PlandoItem
        from .. import ctrAPWorld
        types = ctrAPWorld.options_dataclass.type_hints
        for seed in range(40):
            state = random.getstate()
            try:
                random.seed(seed)
                plando = types["plando_items"]([PlandoItem({"Filler": 1}, ["Crash Cove: Trophy Race"])])
                plando.verify(ctrAPWorld, "ContentPlan", PlandoOptions.items)
                self.assertNotIn("Joe Mama", plando.value[0].items)
            finally:
                random.setstate(state)

    def test_explicit_look_names_still_verify(self):
        from BaseClasses import PlandoOptions
        from Options import PlandoItem
        from .. import ctrAPWorld
        types = ctrAPWorld.options_dataclass.type_hints
        plando = types["plando_items"]([PlandoItem({"Joe Mama": 1}, ["Crash Cove: Trophy Race"])])
        plando.verify(ctrAPWorld, "ContentPlan", PlandoOptions.items)
        hints = types["start_hints"](["Joe Mama"])
        hints.verify(ctrAPWorld, "ContentPlan", PlandoOptions.none)

    def test_malformed_wire_restores_to_none(self):
        for value in (None, "Joe Mama", 3, ["Joe Biden"]):
            with self.subTest(value=value):
                world = SimpleNamespace(game="Crash Team Racing",
                                        options=SimpleNamespace(character_looks=SimpleNamespace(value={"Joe Mama"})),
                                        multiworld=SimpleNamespace(re_gen_passthrough={
                                            "Crash Team Racing": {"ctr_options": {"character_looks": value}}}))
                self.assertEqual(character_looks.allowed_looks(world), [])


class TestSavedRoomsAndLinks(unittest.TestCase):
    """Saved rooms hold tuples, and group links keep
    the looks their slots allow."""

    def test_saved_room_tuple_restores(self):
        for value, expected in ((("Joe Mama",), ["Joe Mama"]), ([{}], []), (("Joe Mama", 3), ["Joe Mama"])):
            with self.subTest(value=value):
                world = SimpleNamespace(game="Crash Team Racing",
                                        options=SimpleNamespace(character_looks=SimpleNamespace(value=set())),
                                        multiworld=SimpleNamespace(re_gen_passthrough={
                                            "Crash Team Racing": {"ctr_options": {"character_looks": value}}}))
                self.assertEqual(character_looks.allowed_looks(world), expected)

    def test_filler_link_shares_enabled_looks(self):
        from .. import ctrAPWorld
        from ..track_origins import restore_legacy_link_pools

        def slot(looks):
            links = SimpleNamespace(value=[{"name": "Shared", "item_pool": ["Filler"]}], legacy_value=[])
            return SimpleNamespace(game=ctrAPWorld.game, ctr_content_plan={"required_features": []},
                                   multiworld=SimpleNamespace(re_gen_passthrough={}),
                                   options=SimpleNamespace(item_links=links,
                                                           character_looks=SimpleNamespace(value=set(looks))))

        for looks, expected in ((["Joe Mama"], True), ([], False)):
            with self.subTest(looks=looks):
                group = {"game": ctrAPWorld.game, "players": {1, 2}, "name": "Shared",
                         "item_pool": set(), "local_items": set(), "non_local_items": set()}
                mw = SimpleNamespace(groups={3: group}, worlds={1: slot(looks), 2: slot([])})
                restore_legacy_link_pools(mw, ctrAPWorld)
                self.assertEqual("Joe Mama" in group["item_pool"], expected)
                self.assertIn("Wumpa Fruit", group["item_pool"])

    def test_expanded_link_pool_keeps_enabled_looks(self):
        """The framework has expanded the group already and the slot's link
        option holds the legacy names (round 3 repro)."""
        from .. import ctrAPWorld
        from ..track_origins import legacy_option_world, restore_legacy_link_pools
        legacy_filler = sorted(legacy_option_world(ctrAPWorld).item_name_groups["Filler"])

        def slot(looks):
            links = SimpleNamespace(value=[{"name": "Shared", "item_pool": legacy_filler}], legacy_value=[])
            return SimpleNamespace(game=ctrAPWorld.game, ctr_content_plan={"required_features": []},
                                   multiworld=SimpleNamespace(re_gen_passthrough={}),
                                   options=SimpleNamespace(item_links=links,
                                                           character_looks=SimpleNamespace(value=set(looks))))

        for looks, expected in ((["Joe Mama"], True), ([], False)):
            with self.subTest(looks=looks):
                group = {"game": ctrAPWorld.game, "players": {1, 2}, "name": "Shared",
                         "item_pool": set(legacy_filler) | {"Joe Mama"}, "local_items": set(),
                         "non_local_items": set()}
                mw = SimpleNamespace(groups={3: group}, worlds={1: slot(looks), 2: slot(looks)})
                restore_legacy_link_pools(mw, ctrAPWorld)
                self.assertEqual("Joe Mama" in group["item_pool"], expected)
