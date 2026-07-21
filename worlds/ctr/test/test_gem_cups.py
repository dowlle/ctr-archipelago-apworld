"""Regression guard for issue #50 (gem-cup variant): include_gem_cups OFF left
the five "<Colour> Gem Cup: Gem" checks as live multiworld slots whenever the
Gems were shuffled.

This is the exact sibling of the battle-arena defect (test_battle_arenas.py).
include_gem_cups only ever kept the cup warp pads on their vanilla token gate
(Regions.py); the five cup locations themselves are unconditional entries in
data/world.json, so the location count is identical with the option on and off.
With Shuffle Gems ON (the DEFAULT -- ShuffleGems is a DefaultOnToggle) the five
Gems were scattered into the pool and the cup checks were free multiworld slots,
so fill could hide logic-required progression on content the player opted out of
(measured 4 of a 12-seed sample, same incidence as the arena bug).

The fix pins the vanilla Gem onto each cup when include_gem_cups is OFF and
Shuffle Gems is ON, and decrements each Gem's pool count by the number pinned so
item count still equals location count. The cups keep their vanilla
has('<Colour> CTR Token', 4) pad gate, so they stay reachable in logic.

These tests lock in:
- cups OFF + Gems shuffled: all five pinned with their vanilla Gem, no cup check
  holds another world's item, and every Gem's pool count is decremented to 0;
- cups ON: nothing pinned, behaviour unchanged (Gems ride the pool);
- Shuffle Gems OFF + cups OFF: the existing shuffle-off pin still runs exactly
  once (no double-pin crash from the new block);
- goal allgemcups + Shuffle Gems ON + cups OFF: forbidden, raises OptionError;
- goal allgemcups + Shuffle Gems OFF + cups OFF: allowed (gemgoal pins the Gems
  onto the cups), no double-pin.
"""

import json
import pkgutil

from Options import OptionError

from . import CTRTestBase

CUP_LOCATIONS = (
    "Red Gem Cup: Gem",
    "Green Gem Cup: Gem",
    "Blue Gem Cup: Gem",
    "Yellow Gem Cup: Gem",
    "Purple Gem Cup: Gem",
)
VANILLA_CUP_ITEM = {
    "Red Gem Cup: Gem": "Red Gem",
    "Green Gem Cup: Gem": "Green Gem",
    "Blue Gem Cup: Gem": "Blue Gem",
    "Yellow Gem Cup: Gem": "Yellow Gem",
    "Purple Gem Cup: Gem": "Purple Gem",
}
GEM_NAMES = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")


def _vanilla_cup_map():
    return json.loads(
        pkgutil.get_data("worlds.ctr", "data/vanilla_mapping.json").decode("utf-8")
    )["ShuffleOptions"]["Gems"]


def _item_table_count(name):
    table = json.loads(
        pkgutil.get_data("worlds.ctr", "data/items.json").decode("utf-8"))
    return next(entry["count"] for entry in table if entry["name"] == name)


class CupPinningMixin:
    def _cup_locations(self):
        return [self.multiworld.get_location(name, self.player)
                for name in CUP_LOCATIONS]

    def test_cup_locations_exist(self):
        # Premise of the bug: the option does not remove them.
        self.assertEqual(len(self._cup_locations()), len(CUP_LOCATIONS))

    def test_vanilla_mapping_data_is_intact(self):
        # The fix reads this block; a rename in the data file would silently
        # turn the pinning back off.
        self.assertEqual(_vanilla_cup_map(), VANILLA_CUP_ITEM)

    def test_item_and_location_counts_balance(self):
        # place_locked_item fills a location without adding a pool item, so an
        # un-decremented pool would overshoot by exactly the number pinned.
        pool = [item for item in self.multiworld.itempool
                if item.player == self.player]
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(
            len(pool), len(unfilled),
            "CTR item pool must exactly fill the unfilled locations")


class TestGemCupsShuffledCupsOff(CupPinningMixin, CTRTestBase):
    """include_gem_cups OFF with Gems shuffled (the DEFAULT gem setting): the
    five cup checks must be vanilla-pinned."""

    run_default_tests = False
    options = {
        "shuffle_gems": True,
        "include_gem_cups": False,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
    }

    def test_all_five_pinned_with_vanilla_gem(self):
        for loc in self._cup_locations():
            with self.subTest(location=loc.name):
                self.assertIsNotNone(
                    loc.item,
                    f"{loc.name} is an empty multiworld slot with cups opted out")
                self.assertTrue(
                    loc.locked,
                    f"{loc.name} is not locked, so fill may still replace it")
                self.assertEqual(loc.item.name, VANILLA_CUP_ITEM[loc.name])
                self.assertEqual(loc.item.player, self.player)

    def test_no_cup_check_is_a_fillable_slot(self):
        unfilled = {loc.name
                    for loc in self.multiworld.get_unfilled_locations(self.player)}
        for name in CUP_LOCATIONS:
            with self.subTest(location=name):
                self.assertNotIn(
                    name, unfilled,
                    f"{name} is still fillable; progression can land on content "
                    f"the player opted out of")

    def test_gems_absent_from_pool(self):
        # Each Gem's items.json count is 1 and all five are pinned, so none may
        # remain in the pool.
        for gem in GEM_NAMES:
            with self.subTest(gem=gem):
                self.assertEqual(_item_table_count(gem), 1,
                                 f"items.json {gem} count moved")
                in_pool = [item for item in self.multiworld.itempool
                           if item.player == self.player and item.name == gem]
                self.assertEqual(
                    len(in_pool), 0,
                    f"{gem} must be pinned onto its cup, not left in the pool")

    def test_total_gem_supply_unchanged(self):
        # Pinned + pooled must still equal the item table count, so the player's
        # total supply of each Gem is untouched.
        for gem in GEM_NAMES:
            with self.subTest(gem=gem):
                pinned = sum(1 for loc in self._cup_locations()
                             if loc.item and loc.item.name == gem)
                pooled = sum(1 for item in self.multiworld.itempool
                             if item.player == self.player and item.name == gem)
                self.assertEqual(pinned + pooled, _item_table_count(gem))


class TestGemCupsOn(CupPinningMixin, CTRTestBase):
    """include_gem_cups ON: unchanged -- the cup checks stay in the multiworld
    and the shuffled Gems ride the pool."""

    run_default_tests = False
    options = {
        "shuffle_gems": True,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks", "cups"],
    }

    def test_nothing_is_pinned(self):
        for loc in self._cup_locations():
            with self.subTest(location=loc.name):
                self.assertFalse(
                    loc.locked,
                    f"{loc.name} was pinned with cups INCLUDED; the option's "
                    f"on-state must keep them as multiworld checks")

    def test_cup_checks_remain_fillable(self):
        unfilled = {loc.name
                    for loc in self.multiworld.get_unfilled_locations(self.player)}
        for name in CUP_LOCATIONS:
            with self.subTest(location=name):
                self.assertIn(name, unfilled)

    def test_gems_stay_in_pool(self):
        for gem in GEM_NAMES:
            with self.subTest(gem=gem):
                in_pool = [item for item in self.multiworld.itempool
                           if item.player == self.player and item.name == gem]
                self.assertEqual(len(in_pool), _item_table_count(gem))


class TestGemCupsShuffleOffCupsOff(CupPinningMixin, CTRTestBase):
    """Shuffle Gems OFF + cups OFF: the existing shuffle-off pin (the _gems_locked
    block) already places each Gem on its cup. The new #50 block must NOT also
    run -- a second place_locked_item on a filled location would raise."""

    run_default_tests = False
    options = {
        "shuffle_gems": False,
        "include_gem_cups": False,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
    }

    def test_each_cup_pinned_exactly_once(self):
        # Reaching create_items without an exception already proves no double-pin
        # crash; assert the end state is the single vanilla pin.
        for loc in self._cup_locations():
            with self.subTest(location=loc.name):
                self.assertTrue(loc.locked)
                self.assertEqual(loc.item.name, VANILLA_CUP_ITEM[loc.name])
                self.assertEqual(loc.item.player, self.player)

    def test_gems_absent_from_pool(self):
        for gem in GEM_NAMES:
            with self.subTest(gem=gem):
                in_pool = [item for item in self.multiworld.itempool
                           if item.player == self.player and item.name == gem]
                self.assertEqual(len(in_pool), 0)


class TestGemCupsAllGemsGoalShuffleOffCupsOff(CupPinningMixin, CTRTestBase):
    """goal allgemcups + Shuffle Gems OFF + cups OFF is ALLOWED: gemgoal() pins
    the five Gems onto the cups (win every cup). The new #50 block must skip this
    config (its _GEM_GOAL guard) so gemgoal's pins are not double-placed."""

    run_default_tests = False
    options = {
        "goal": "allgemcups",
        "shuffle_gems": False,
        "include_gem_cups": False,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
    }

    def test_each_cup_pinned_exactly_once(self):
        for loc in self._cup_locations():
            with self.subTest(location=loc.name):
                self.assertTrue(loc.locked)
                self.assertEqual(loc.item.name, VANILLA_CUP_ITEM[loc.name])


class TestGemCupsForbiddenCombo(CTRTestBase):
    """goal allgemcups + Shuffle Gems ON + cups OFF is FORBIDDEN: the goal's own
    races are the gem cups, so opting the cups out while the Gems scatter into the
    pool would strand the goal. generate_early must raise a clean OptionError."""

    auto_construct = False
    options = {
        "goal": "allgemcups",
        "shuffle_gems": True,
        "include_gem_cups": False,
    }

    def test_generation_raises_option_error(self):
        with self.assertRaises(OptionError) as ctx:
            self.world_setup()
        self.assertIn("allgemcups", str(ctx.exception))
        self.assertIn("include_gem_cups", str(ctx.exception))
