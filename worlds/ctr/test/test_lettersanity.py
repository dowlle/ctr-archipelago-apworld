"""Generation and wire gates for Lettersanity (#148)."""
import unittest

from test.general import setup_multiworld

from .. import ctrAPWorld
from ..lettersanity import LETTERSANITY_CLASS, ITEM_NAMES, LETTER_TRACKS, LETTERS

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=148, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


class TestLettersanityShapes(unittest.TestCase):
    def _counts(self, mode, count=3):
        mw = _build(lettersanity=mode, letters_per_track=count)
        world = mw.worlds[1]
        locations = [name for name in LETTERSANITY_CLASS.names()
                     if name in mw.regions.location_cache[1]]
        items = [item.name for item in mw.itempool if item.name in ITEM_NAMES]
        return world, locations, items

    def test_off(self):
        world, locations, items = self._counts("off")
        self.assertEqual((locations, items), ([], []))
        self.assertNotIn("lettersanity_checks", world.fill_slot_data())

    def test_locations_only_counts(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                world, locations, items = self._counts("locations_only", count)
                self.assertEqual(len(locations), 16 * count)
                self.assertEqual(items, [])
                self.assertTrue(all(len(v) == count for v in world.options._lettersanity_selected.values()))

    def test_locations_and_items_counts(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                _world, locations, items = self._counts("locations_and_items", count)
                self.assertEqual(len(locations), 16 * count)
                self.assertEqual(len(items), 16 * count)

    def test_items_only_uses_all_letters(self):
        _world, locations, items = self._counts("items_only", 1)
        self.assertEqual(locations, [])
        self.assertEqual(set(items), set(ITEM_NAMES))

    def test_wire_uses_fixed_three_slot_arrays(self):
        world, _locations, _items = self._counts("locations_only", 2)
        block = world.fill_slot_data()["lettersanity_checks"]
        self.assertEqual(block["mode"], 1)
        self.assertEqual(block["letters_per_track"], 2)
        self.assertEqual(len(block["locations"]), len(LETTER_TRACKS))
        self.assertTrue(all(len(codes) == len(LETTERS) and codes.count(-1) == 1
                            for codes in block["locations"].values()))

