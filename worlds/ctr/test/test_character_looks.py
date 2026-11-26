"""The parked option is readable without producing new character look items."""
import json
import unittest
from collections import Counter
from types import SimpleNamespace

from BaseClasses import ItemClassification
from Generate import roll_settings
from Options import Visibility, get_option_groups

from .. import character_looks, ctrAPWorld
from ..Options import CharacterLooks
from ..minted_items_030 import MINTED_ITEMS_030
from ..notices import emit_summary, summary_lines
from ..wumpa_family import draw_filler_name, filler_weights
from .test_content_plan import make_world, profile_options


def snapshot(world):
    return (
        json.dumps(world.fill_slot_data(), sort_keys=True),
        Counter((item.name, item.code) for item in world.multiworld.itempool),
    )


class TestParkedLooks(unittest.TestCase):
    def test_reservation_and_template_visibility(self):
        self.assertIn(("Joe Mama", 35010215, ItemClassification.filler), MINTED_ITEMS_030)
        self.assertEqual(ctrAPWorld.item_name_to_id["Joe Mama"], 35010215)
        self.assertEqual(CharacterLooks.visibility, Visibility.none)
        for group in get_option_groups(ctrAPWorld).values():
            self.assertNotIn("character_looks", group)

    def test_old_yaml_rolls_and_generates_one_adjustment(self):
        game = ctrAPWorld.game
        rolled = roll_settings({"name": "Legacy", "game": game, game: {"character_looks": ["Joe Mama"]}})
        self.assertEqual(rolled.character_looks.value, {"Joe Mama"})
        with self.assertLogs("CTR", level="WARNING") as captured:
            world = make_world({"character_looks": list(rolled.character_looks.value), "box_locations": True})
            self.assertFalse(emit_summary(world))
        self.assertEqual(len(captured.output), 1)
        self.assertIn("Character Looks: turned off", captured.output[0])
        self.assertFalse(world.options.character_looks.value)
        self.assertNotIn("character_looks", world.fill_slot_data()["ctr_options"])
        self.assertNotIn("Joe Mama", {item.name for item in world.multiworld.itempool})
        self.assertEqual(world.create_item("Joe Mama").code, 35010215)

    def test_parked_item_cannot_enter_starting_inventory(self):
        world = make_world({
            "start_inventory": {"Joe Mama": 1},
            "start_inventory_from_pool": {"Joe Mama": 1},
        })
        self.assertNotIn("Joe Mama", world.options.start_inventory.value)
        self.assertNotIn("Joe Mama", world.options.start_inventory_from_pool.value)
        self.assertNotIn("Joe Mama", {item.name for item in world.multiworld.precollected_items[world.player]})

    def test_parked_item_link_uses_normal_filler_replacement(self):
        world = make_world({})
        replacements = {world.player: "Joe Mama", 2: "Wumpa Fruit"}
        world.multiworld.groups[3] = {"replacement_items": replacements}
        character_looks.park(world)
        self.assertIsNone(replacements[world.player])
        self.assertEqual(replacements[2], "Wumpa Fruit")
        self.assertIn("Character Looks: turned off", summary_lines(world)[0])

    def test_legacy_look_setting_does_not_change_new_rooms(self):
        for profile in ({"box_locations": True}, profile_options()):
            for seed in (1, 215, 759):
                with self.subTest(profile=profile, seed=seed):
                    base = make_world(profile, seed=seed)
                    parked = make_world(dict(profile, character_looks=["Joe Mama"]), seed=seed)
                    self.assertEqual(snapshot(base), snapshot(parked))
                    self.assertEqual(base.multiworld.random.getstate(), parked.multiworld.random.getstate())
                    self.assertFalse(any("Character Looks" in line for line in summary_lines(base)))

    def test_legacy_tracker_metadata_is_preserved(self):
        wire = make_world({"box_locations": True}).fill_slot_data()
        wire["ctr_options"]["character_looks"] = ("Joe Mama",)
        restored = make_world({}, passthrough=wire)
        self.assertEqual(restored.fill_slot_data()["ctr_options"]["character_looks"], ["Joe Mama"])
        self.assertEqual(restored.create_item("Joe Mama").code, 35010215)

    def test_parked_filler_does_not_use_rng_when_bundles_and_top_up_are_off(self):
        world = SimpleNamespace(options=SimpleNamespace(
            reserve_top_up=SimpleNamespace(value=0), wumpa_bundles=SimpleNamespace(value=0),
            character_looks=CharacterLooks(["Joe Mama"])),
            random=None)
        self.assertEqual(filler_weights(world), {"Wumpa Fruit": 1})
        self.assertEqual(draw_filler_name(world), "Wumpa Fruit")
