"""Generation contract for the comfort-only surface items (issues #14/#15)."""

from BaseClasses import ItemClassification

from worlds.ctr.Items import load_item_table

from . import CTRTestBase


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
    options = {"podium_placement_checks": False}

    def test_reduced_location_seed_omits_the_pack_atomically(self) -> None:
        pooled = {item.name for item in self.multiworld.itempool}
        self.assertTrue(SURFACE_ITEMS.isdisjoint(pooled))
        self.assertEqual(
            len(self.multiworld.itempool),
            len(self.multiworld.get_unfilled_locations(self.player)),
        )
