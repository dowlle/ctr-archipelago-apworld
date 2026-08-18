"""Focused gates for the #223 Tizi Helper apworld half.

The runtime rule (which four boxes, and the itemsanity Mask gate) is native's;
this side owns exactly three things and each one is pinned below:

  1. the appended name and its frozen code, added without disturbing anything
     the #177 freeze signed off,
  2. the option -> pool behaviour (one `useful` item on, nothing at all off,
     zero new locations either way),
  3. the always-emitted wire scalar and its Universal Tracker restore.
"""
import unittest

from BaseClasses import ItemClassification

from ..Items import load_item_table
from ..Locations import CTR_LOCATION_CLASSES
from ..tizi_helper import TIZI_HELPER_CODE, TIZI_HELPER_ITEM, TIZI_ITEMSANITY_COMPANION
from . import CTRTestBase


class TestTiziHelperName(unittest.TestCase):
    """The datapackage half: one appended name, nothing else moved."""

    def test_the_item_exists_at_its_frozen_code(self) -> None:
        table = {item["name"]: item["code"] for item in load_item_table()}
        self.assertEqual(table[TIZI_HELPER_ITEM], TIZI_HELPER_CODE)

    def test_it_is_appended_one_past_the_frozen_set(self) -> None:
        """35010187 (Gas Pedal) was the freeze's last entry, so the amendment is
        35010188. Anything else means a renumber, which #223 forbids.

        This originally also asserted that the helper was the HIGHEST code in
        the table. #224 appended the second ruled amendment at 35010189, so that
        is no longer true and asserting it would forbid the very append the
        ruling allows. What #223 actually needs pinned is its own boundary:
        Gas Pedal below it, the helper on it, and its code unmoved. Contiguity
        still catches an insertion anywhere in the table."""
        self.assertEqual(TIZI_HELPER_CODE, 35010188)
        codes = [item["code"] for item in load_item_table()]
        self.assertEqual(codes, list(range(35010000, 35010000 + len(codes))))
        by_code = {item["code"]: item["name"] for item in load_item_table()}
        self.assertEqual(by_code[TIZI_HELPER_CODE - 1], "Gas Pedal")
        self.assertEqual(by_code[TIZI_HELPER_CODE], TIZI_HELPER_ITEM)

    def test_it_ships_inert_in_the_data_file(self) -> None:
        """count 0 in data/items.json: the option decides, not the table."""
        entry = next(item for item in load_item_table()
                     if item["name"] == TIZI_HELPER_ITEM)
        self.assertEqual(entry["count"], 0)
        self.assertEqual(entry["classification"], ItemClassification.useful)

    def test_the_itemsanity_companion_the_rule_names_is_a_real_item(self) -> None:
        """The ruled gate names the separate `Mask` weapon item. If itemsanity
        ever renames it, this fails here rather than silently ungating the
        helper on native."""
        table = {item["name"]: item["code"] for item in load_item_table()}
        self.assertIn(TIZI_ITEMSANITY_COMPANION, table)
        self.assertEqual(table[TIZI_ITEMSANITY_COMPANION], 35010101)

    def test_it_mints_no_location(self) -> None:
        location_names = {n for n, _c, _r in CTR_LOCATION_CLASSES.all_locations()}
        self.assertFalse({n for n in location_names if "Tizi" in n})


class TestTiziHelperOff(CTRTestBase):
    """Default seed. The option is off, so the item does not exist."""

    def test_no_pool_item(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertNotIn(TIZI_HELPER_ITEM, pool_names)

    def test_wire_scalar_is_emitted_and_false(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertIn("tizi_helper", slot_data["ctr_options"])
        self.assertFalse(slot_data["ctr_options"]["tizi_helper"])


class TestTiziHelperOn(CTRTestBase):
    run_default_tests = False
    options = {"tizi_helper": True}

    def test_exactly_one_useful_copy_enters_the_pool(self) -> None:
        items = [item for item in self.multiworld.itempool
                 if item.player == self.player and item.name == TIZI_HELPER_ITEM]
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].advancement)
        self.assertTrue(items[0].useful)

    def test_it_adds_no_location(self) -> None:
        """The helper spends a filler slot; it does not buy itself one."""
        self.assertFalse([loc for loc in self.multiworld.get_locations(self.player)
                          if "Tizi" in loc.name])

    def test_wire_scalar_is_true(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["ctr_options"]["tizi_helper"])


class TestTiziHelperWithItemsanity(CTRTestBase):
    """The ruled gate's other half exists on the same seed: with itemsanity on,
    both the helper and the separate Mask item are receivable. Native enforces
    the AND; this only proves the apworld can supply both."""
    run_default_tests = False
    options = {"tizi_helper": True, "itemsanity": True}

    def test_both_gate_items_are_in_the_pool(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertIn(TIZI_HELPER_ITEM, pool_names)
        self.assertIn(TIZI_ITEMSANITY_COMPANION, pool_names)

    def test_both_scalars_ride_the_same_wire(self) -> None:
        options = self.world.fill_slot_data()["ctr_options"]
        self.assertTrue(options["tizi_helper"])
        self.assertTrue(options["itemsanity"])


class TestTiziHelperUniversalTrackerRestore(CTRTestBase):
    run_default_tests = False
    options = {"tizi_helper": True}

    def test_the_scalar_round_trips(self) -> None:
        wire = self.world.fill_slot_data()
        self.world.options.tizi_helper.value = 0
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.tizi_helper.value, 1)

    def test_a_pre_223_seed_restores_to_off(self) -> None:
        """No key on the wire is any seed generated before this build."""
        wire = self.world.fill_slot_data()
        del wire["ctr_options"]["tizi_helper"]
        self.world.options.tizi_helper.value = 1
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.tizi_helper.value, 0)
