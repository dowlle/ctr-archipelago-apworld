import unittest
from types import SimpleNamespace

from ..custom_lettersanity import CUSTOM_LETTERSANITY_CLASS
from ..custom_lettersanity import CUSTOM_LETTER_ITEM_DATA
from .. import ctrAPWorld
from ..Items import load_item_table


class TestCustomLetterIdentities(unittest.TestCase):


    def test_separate_item_map_preserves_positional_table(self):
        self.assertEqual(len(CUSTOM_LETTER_ITEM_DATA), 396)
        old = load_item_table()
        self.assertEqual([item["code"] for item in old],
                         list(range(35010000, 35010200)))
        self.assertFalse({item["code"] for item in old}.intersection(
            item["code"] for item in CUSTOM_LETTER_ITEM_DATA))
        self.assertFalse({item["name"] for item in old}.intersection(
            item["name"] for item in CUSTOM_LETTER_ITEM_DATA))
        for item in CUSTOM_LETTER_ITEM_DATA:
            self.assertEqual(ctrAPWorld.item_name_to_id[item["name"]], item["code"])
            self.assertEqual(item["count"], 0)

    def test_complete_permanent_slot_family(self):
        rows = CUSTOM_LETTERSANITY_CLASS.all_locations()
        self.assertEqual(len(rows), 396)
        self.assertEqual(rows[0], ("Custom Track 1: Letter C", 35020000,
                                   "Custom Track 1"))
        self.assertEqual(rows[-1], ("Custom Track 132: Letter R", 35020395,
                                    "Custom Track 132"))
        self.assertEqual(len({code for _, code, _ in rows}), 396)
        for slot in range(1, 133):
            for li, letter in enumerate(("C", "T", "R")):
                self.assertEqual(CUSTOM_LETTERSANITY_CLASS.code_for(slot, letter),
                                 35020000 + (slot - 1) * 3 + li)

    def test_declared_letters_do_not_auto_activate_mode(self):
        options = SimpleNamespace(custom_tracks=SimpleNamespace(value={
            "baby_t_park": {"flags": {"ctr_letters": True}}}),
            lettersanity=SimpleNamespace(value=2))
        self.assertEqual(CUSTOM_LETTERSANITY_CLASS.created_location_names(options), [])
