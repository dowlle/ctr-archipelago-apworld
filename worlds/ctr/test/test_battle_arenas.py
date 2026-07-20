"""Regression guard for issue #50: include_battle_arenas OFF left the four
Crystal Bonus Round checks as live multiworld slots.

The option only ever kept the crystal warp pads out of the randomized-unlock
pool; the four locations themselves are unconditional entries in
data/world.json, so the location count is identical (213) with the option on
and off. Nothing pinned vanilla items on them either, so fill was free to
hide logic-required progression there -- measured in 4 of a 12-seed sample.
A player who opted out of arena content was still forced through it.

The fix pins the vanilla Purple CTR Token onto each of the four when the
option is OFF (the Gems / Boss Keys contract), and decrements the Purple CTR
Token pool count by the number pinned so item count still equals location
count.

These tests lock in:
- option OFF: all four pinned with their vanilla item, no arena check holds
  another world's item, and the Purple CTR Token pool count is balanced;
- option ON: nothing pinned, behaviour unchanged.
"""

import json
import pkgutil

from . import CTRTestBase

ARENA_LOCATIONS = (
    "Skull Rock: Crystal Bonus Round",
    "Rampage Ruins: Crystal Bonus Round",
    "Rocky Road: Crystal Bonus Round",
    "Nitro Court: Crystal Bonus Round",
)
VANILLA_ARENA_ITEM = "Purple CTR Token"


def _vanilla_arena_map():
    return json.loads(
        pkgutil.get_data("worlds.ctr", "data/vanilla_mapping.json").decode("utf-8")
    )["ShuffleOptions"]["Bonus Round Tokens"]


def _item_table_count(name):
    table = json.loads(
        pkgutil.get_data("worlds.ctr", "data/items.json").decode("utf-8"))
    return next(entry["count"] for entry in table if entry["name"] == name)


class ArenaPinningMixin:
    def _arena_locations(self):
        return [self.multiworld.get_location(name, self.player)
                for name in ARENA_LOCATIONS]

    def test_arena_locations_exist(self):
        # Premise of the bug: the option does not remove them.
        self.assertEqual(len(self._arena_locations()), len(ARENA_LOCATIONS))

    def test_vanilla_mapping_data_is_intact(self):
        # The fix reads this block; a rename in the data file would silently
        # turn the pinning back off.
        self.assertEqual(
            _vanilla_arena_map(),
            {name: VANILLA_ARENA_ITEM for name in ARENA_LOCATIONS})

    def test_item_and_location_counts_balance(self):
        # place_locked_item fills a location without adding a pool item, so an
        # un-decremented pool would overshoot by exactly the number pinned.
        pool = [item for item in self.multiworld.itempool
                if item.player == self.player]
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(
            len(pool), len(unfilled),
            "CTR item pool must exactly fill the unfilled locations")


class TestBattleArenasOff(ArenaPinningMixin, CTRTestBase):
    """include_battle_arenas OFF: the four checks must be vanilla-pinned."""

    run_default_tests = False
    options = {
        "include_battle_arenas": False,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
    }

    def test_all_four_pinned_with_vanilla_item(self):
        for loc in self._arena_locations():
            with self.subTest(location=loc.name):
                self.assertIsNotNone(
                    loc.item,
                    f"{loc.name} is an empty multiworld slot with arenas opted out")
                self.assertTrue(
                    loc.locked,
                    f"{loc.name} is not locked, so fill may still replace it")
                self.assertEqual(loc.item.name, VANILLA_ARENA_ITEM)
                self.assertEqual(loc.item.player, self.player)

    def test_no_arena_check_is_a_fillable_slot(self):
        unfilled = {loc.name
                    for loc in self.multiworld.get_unfilled_locations(self.player)}
        for name in ARENA_LOCATIONS:
            with self.subTest(location=name):
                self.assertNotIn(
                    name, unfilled,
                    f"{name} is still fillable; progression can land on content "
                    f"the player opted out of")

    def test_purple_token_pool_count_decremented(self):
        pinned = len(ARENA_LOCATIONS)
        expected = _item_table_count(VANILLA_ARENA_ITEM) - pinned
        self.assertEqual(expected, 0, "items.json Purple CTR Token count moved")
        in_pool = [item for item in self.multiworld.itempool
                   if item.player == self.player
                   and item.name == VANILLA_ARENA_ITEM]
        self.assertEqual(
            len(in_pool), expected,
            f"{VANILLA_ARENA_ITEM} pool count must drop by the {pinned} pinned")

    def test_total_purple_tokens_unchanged(self):
        # Pinned + pooled must still equal the item table's count, so the
        # player's total supply of the vanilla currency is untouched.
        pinned = sum(1 for loc in self._arena_locations()
                     if loc.item and loc.item.name == VANILLA_ARENA_ITEM)
        pooled = sum(1 for item in self.multiworld.itempool
                     if item.player == self.player
                     and item.name == VANILLA_ARENA_ITEM)
        self.assertEqual(pinned + pooled, _item_table_count(VANILLA_ARENA_ITEM))


class TestBattleArenasOn(ArenaPinningMixin, CTRTestBase):
    """include_battle_arenas ON: unchanged -- the checks stay in the multiworld."""

    run_default_tests = False
    options = {
        "include_battle_arenas": True,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
    }

    def test_nothing_is_pinned(self):
        for loc in self._arena_locations():
            with self.subTest(location=loc.name):
                self.assertFalse(
                    loc.locked,
                    f"{loc.name} was pinned with arenas INCLUDED; the option's "
                    f"on-state must keep them as multiworld checks")

    def test_arena_checks_remain_fillable(self):
        unfilled = {loc.name
                    for loc in self.multiworld.get_unfilled_locations(self.player)}
        for name in ARENA_LOCATIONS:
            with self.subTest(location=name):
                self.assertIn(name, unfilled)

    def test_purple_token_pool_count_unchanged(self):
        in_pool = [item for item in self.multiworld.itempool
                   if item.player == self.player
                   and item.name == VANILLA_ARENA_ITEM]
        self.assertEqual(len(in_pool), _item_table_count(VANILLA_ARENA_ITEM))


class TestBattleArenasOffVanillaPads(ArenaPinningMixin, CTRTestBase):
    """The pinning is unlock-mode independent (vanilla warp pads)."""

    run_default_tests = False
    options = {
        "include_battle_arenas": False,
        "warppad_unlock_requirements": "vanilla",
    }

    def test_all_four_pinned(self):
        for loc in self._arena_locations():
            with self.subTest(location=loc.name):
                self.assertTrue(loc.locked)
                self.assertEqual(loc.item.name, VANILLA_ARENA_ITEM)
