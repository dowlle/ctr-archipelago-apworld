"""Gates for overflow shedding: filler first, then the comfort pack, then refuse.

The bug these exist to prevent (2026-08-18): the previous trim considered only
the comfort pack and dropped it only when dropping all five was enough on its
own, so a seed six over dropped NOTHING and reached fill overfull. It survived
every 500-seed fuzz run in the project's history because reaching that exact
overflow needs roughly a 1-in-500 option combination.

So the tier tests below drive the pure function with synthetic pools rather than
hunting for a seed that lands on the right overflow, and the generation tests
pin the end-to-end invariant that actually matters: items == locations.
"""
import unittest

from BaseClasses import Item, ItemClassification

from ..item_supply import shed_overflow
from .. import SURFACE_ITEM_NAMES
from . import CTRTestBase


def _item(name: str, classification: ItemClassification) -> Item:
    return Item(name, classification, None, 1)


def _pool(progression: int = 0, useful: int = 0, filler: int = 0,
          surface: bool = False):
    pool = []
    pool += [_item(f"Prog {i}", ItemClassification.progression)
             for i in range(progression)]
    pool += [_item(f"Useful {i}", ItemClassification.useful)
             for i in range(useful)]
    pool += [_item(f"Wumpa {i}", ItemClassification.filler)
             for i in range(filler)]
    if surface:
        pool += [_item(name, ItemClassification.useful)
                 for name in sorted(SURFACE_ITEM_NAMES)]
    return pool


def _names(pool):
    return [item.name for item in pool]


class TestShedNothingWhenItFits(unittest.TestCase):
    def test_a_pool_that_fits_is_returned_untouched(self) -> None:
        pool = _pool(progression=10, filler=5, surface=True)
        self.assertEqual(_names(shed_overflow(pool, 100, SURFACE_ITEM_NAMES)),
                         _names(pool))

    def test_an_exactly_full_pool_is_returned_untouched(self) -> None:
        pool = _pool(progression=10, filler=5, surface=True)
        self.assertEqual(_names(shed_overflow(pool, len(pool), SURFACE_ITEM_NAMES)),
                         _names(pool))


class TestTierOneFillerFirst(unittest.TestCase):
    """The ruled order's whole point: comfort items outlive filler."""

    def test_one_over_sheds_one_filler_and_keeps_the_comfort_pack(self) -> None:
        pool = _pool(progression=10, filler=3, surface=True)
        result = shed_overflow(pool, len(pool) - 1, SURFACE_ITEM_NAMES)
        self.assertEqual(len(result), len(pool) - 1)
        for name in SURFACE_ITEM_NAMES:
            self.assertIn(name, _names(result))
        self.assertEqual(sum(1 for n in _names(result) if n.startswith("Wumpa")), 2)

    def test_it_sheds_only_as_much_filler_as_the_overflow_needs(self) -> None:
        pool = _pool(progression=10, filler=8, surface=True)
        result = shed_overflow(pool, len(pool) - 3, SURFACE_ITEM_NAMES)
        self.assertEqual(sum(1 for n in _names(result) if n.startswith("Wumpa")), 5)
        for name in SURFACE_ITEM_NAMES:
            self.assertIn(name, _names(result))

    def test_progression_is_never_shed(self) -> None:
        pool = _pool(progression=10, filler=1)
        result = shed_overflow(pool, 1, SURFACE_ITEM_NAMES)
        self.assertEqual(sum(1 for n in _names(result) if n.startswith("Prog")), 10)


class TestTierTwoComfortPack(unittest.TestCase):
    def test_filler_goes_before_the_pack_even_when_both_are_needed(self) -> None:
        """Six over with one filler: the filler goes first, then the whole pack."""
        pool = _pool(progression=20, filler=1, surface=True)
        result = shed_overflow(pool, len(pool) - 6, SURFACE_ITEM_NAMES)
        self.assertNotIn("Wumpa 0", _names(result))
        for name in SURFACE_ITEM_NAMES:
            self.assertNotIn(name, _names(result))

    def test_the_pack_goes_whole_and_may_undershoot(self) -> None:
        """Dropping five to cover one leaves the pool under; the caller's filler
        top-up closes that, which is what makes the whole-pack ruling free."""
        pool = _pool(progression=20, surface=True)
        result = shed_overflow(pool, len(pool) - 1, SURFACE_ITEM_NAMES)
        self.assertEqual(len(result), len(pool) - 5)

    def test_the_pack_is_kept_when_dropping_it_would_not_be_enough(self) -> None:
        """Spending the pack for nothing helps no one: the caller refuses, and
        the shortfall it reports should count the pack's slots honestly."""
        pool = _pool(progression=20, surface=True)
        result = shed_overflow(pool, len(pool) - 6, SURFACE_ITEM_NAMES)
        for name in SURFACE_ITEM_NAMES:
            self.assertIn(name, _names(result))


class TestBundlesJoinTierOneByClassification(unittest.TestCase):
    """`Small`/`Big Wumpa Bundle` are filler-classified but inert at count 0
    today. Tier 1 keys on classification, so they shed the day an option
    creates them, with no change to this module."""

    def test_any_filler_classified_item_is_shed_regardless_of_name(self) -> None:
        pool = _pool(progression=10, surface=True)
        pool.append(_item("Big Wumpa Bundle", ItemClassification.filler))
        result = shed_overflow(pool, len(pool) - 1, SURFACE_ITEM_NAMES)
        self.assertNotIn("Big Wumpa Bundle", _names(result))
        for name in SURFACE_ITEM_NAMES:
            self.assertIn(name, _names(result))


class TestDefaultSeedIsUntouched(CTRTestBase):
    """The shipped default has ample room; nothing here may change it."""

    def test_items_equal_locations(self) -> None:
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = [l for l in self.multiworld.get_unfilled_locations(self.player)]
        self.assertEqual(len(items), len(locations))

    def test_the_comfort_pack_is_present(self) -> None:
        names = [i.name for i in self.multiworld.itempool if i.player == self.player]
        for name in SURFACE_ITEM_NAMES:
            self.assertIn(name, names)


class TestTightSeedStillBalances(CTRTestBase):
    """A deliberately reduced seed: no boxes, no itemsanity, no unlocks, no key
    shuffle, plus lettersanity and an item-only option. This is the shape that
    produced the 2026-08-18 mismatch."""

    run_default_tests = False
    options = {
        "box_locations": False,
        "itemsanity": False,
        "character_unlocks": False,
        "shuffle_keys": False,
        "shuffle_gems": False,
        "include_gem_cups": False,
        "lettersanity": "locations_and_items",
        "tizi_helper": True,
    }

    def test_items_equal_locations(self) -> None:
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = [l for l in self.multiworld.get_unfilled_locations(self.player)]
        self.assertEqual(len(items), len(locations))

    def test_the_option_created_item_survived(self) -> None:
        """Tizi Helper is a toggle the player set. It is never shedding
        material: a seed that cannot fit it is refused instead."""
        names = [i.name for i in self.multiworld.itempool if i.player == self.player]
        self.assertIn("Tizi Helper", names)


class TestFillerFloorForExcludedLocations(unittest.TestCase):
    """Archipelago fills EXCLUDED locations from the filler pool ALONE, so a
    seed must keep one filler per excluded location. Shedding the last filler
    in favour of comfort items balances the counts and still makes the seed
    unfillable -- found on 2026-08-18 when a floorless first cut passed its own
    2000-seed item/location arm and then failed the matrix's default arm."""

    def test_filler_at_the_floor_is_not_shed(self) -> None:
        pool = _pool(progression=10, filler=1, surface=True)
        result = shed_overflow(pool, len(pool) - 1, SURFACE_ITEM_NAMES,
                               filler_floor=1)
        self.assertIn("Wumpa 0", _names(result))

    def test_only_filler_above_the_floor_is_shed(self) -> None:
        pool = _pool(progression=10, filler=4, surface=True)
        result = shed_overflow(pool, len(pool) - 3, SURFACE_ITEM_NAMES,
                               filler_floor=2)
        self.assertEqual(sum(1 for n in _names(result) if n.startswith("Wumpa")), 2)

    def test_the_floor_pushes_the_overflow_down_to_the_comfort_pack(self) -> None:
        """With the floor reached and the seed still over, tier 2 is what pays,
        which is the correct order: the excluded locations keep their filler."""
        pool = _pool(progression=10, filler=1, surface=True)
        result = shed_overflow(pool, len(pool) - 5, SURFACE_ITEM_NAMES,
                               filler_floor=1)
        self.assertIn("Wumpa 0", _names(result))
        for name in SURFACE_ITEM_NAMES:
            self.assertNotIn(name, _names(result))
