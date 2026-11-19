"""Generation contract for the comfort-only surface items (issues #14/#15)."""
import random
import unittest

from BaseClasses import ItemClassification, PlandoOptions
from Options import ExcludeLocations, PlandoItem, StartHints

from worlds.ctr.Items import load_item_table

from . import CTRTestBase
from .test_content_plan import make_world
from .. import ctrAPWorld


SURFACE_ITEMS = {
    "Ignore Grass",
    "Ignore Dirt",
    "Ignore Snow",
    "Ignore Water",
    "Ignore Ice",
}


class TestSurfaceItemData(CTRTestBase):
    def test_surface_items_are_one_each_and_useful(self) -> None:
        entries = {entry["name"]: entry for entry in load_item_table()}

        for name in SURFACE_ITEMS:
            with self.subTest(item=name):
                self.assertEqual(entries[name]["count"], 1)
                self.assertEqual(
                    entries[name]["classification"], ItemClassification.useful
                )

    def test_ignore_sand_stays_reserved_but_out_of_the_pool(self) -> None:
        entries = {entry["name"]: entry for entry in load_item_table()}

        self.assertEqual(entries["Ignore Sand"]["code"], 35010026)
        self.assertEqual(entries["Ignore Sand"]["count"], 0)

    def test_generated_pool_contains_exactly_one_of_each_surface_item(self) -> None:
        for name in SURFACE_ITEMS:
            with self.subTest(item=name):
                self.assertEqual(
                    sum(item.name == name for item in self.multiworld.itempool), 1
                )

        self.assertFalse(
            any(item.name == "Ignore Sand" for item in self.multiworld.itempool)
        )


class TestSurfaceItemCapacityFallback(CTRTestBase):
    """A seed with no podium rungs has room for fewer than five comfort items."""

    run_default_tests = False
    # See the character-phase note in test_location_class_infra: a podium-off
    # seed has no room for the 15 always-on character unlocks, and
    # all-unlocked mode is the named fix. Keeps this fixture about the
    # comfort-pack trim rather than about the character item economy.
    options = {"podium_placement_checks": False, "character_unlocks": False, "wumpa_shop_slots": 0}


class TestOriginLetterGroups(unittest.TestCase):
    def test_legacy_group_expansion_preserves_the_tight_item_pool_and_hint_text(self):
        excluded = ExcludeLocations.from_any(["Acid Lake"])
        hints = StartHints.from_any(["CTR Letters"])
        for option in (excluded, hints):
            option.verify(ctrAPWorld, "ContentPlan", PlandoOptions.none)
        legacy_excluded = excluded.value - {"Acid Lake: Letter K", "Acid Lake: Letter N"}
        legacy_hints = {name for name in hints.value if not name.startswith(("Letter K (", "Letter N ("))}
        options = dict(accessibility="full", track_origin_letters=False, lettersanity="locations_and_items",
                       letters_per_track=3, item_pool={"extra": {"trophies": 40}},
                       start_inventory={"Ignore Dirt": 1})
        control = make_world(dict(options, exclude_locations=legacy_excluded, start_hints=legacy_hints), seed=123)
        world = make_world(dict(options, exclude_locations=excluded.value, start_hints=hints.value), seed=123)
        self.assertEqual(world.fill_slot_data(), control.fill_slot_data())
        self.assertEqual(world.options.exclude_locations.current_option_name, control.options.exclude_locations.current_option_name)
        self.assertEqual(world.options.start_hints.current_option_name, control.options.start_hints.current_option_name)

    def test_random_name_rolls_keep_the_legacy_candidate_list(self):
        types = ctrAPWorld.options_dataclass.type_hints
        state = random.getstate()
        try:
            random.seed(123)
            plando = types["plando_items"]([PlandoItem({"CTR Letters": 3}, ["Crash Cove: Trophy Race"])])
            plando.verify(ctrAPWorld, "ContentPlan", PlandoOptions.items)
            self.assertEqual(plando.value[0].items,
                             {"Letter C (Custom Track 110)": 1, "Letter C (Custom Track 14)": 1,
                              "Letter R (Custom Track 124)": 1})
            random.seed(123)
            hints = types["start_hints"].from_text("random-low")
            hints.verify(ctrAPWorld, "ContentPlan", PlandoOptions.none)
            self.assertEqual(len(hints.value), 23)
            self.assertIn("Letter C (Custom Track 5)", hints.value)
            self.assertTrue(all(not name.startswith(("Letter K (", "Letter N (")) for name in hints.value))
        finally:
            random.setstate(state)

