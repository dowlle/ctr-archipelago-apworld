"""Focused gates for the #145 Itemsanity apworld activation."""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import progressive_capability
from ..itemsanity import (ITEMSANITY_CLASS, ITEMSANITY_CODE_BASE, ITEM_NAMES,
                          USEFUL_WEAPON_FAMILIES, WEAPONS, family_count)
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _grant(state, player, *items):
    for item in items:
        state.add_item(item, player, 1)


class TestItemsanityOff(CTRTestBase):
    def test_no_itemsanity_locations_or_pool_items(self):
        for name in ITEMSANITY_CLASS.names():
            with self.subTest(location=name):
                with self.assertRaises(KeyError):
                    self.multiworld.get_location(name, self.player)
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertEqual(set(pool_names) & set(ITEM_NAMES), set())



class TestItemsanityOn(CTRTestBase):
    run_default_tests = False
    options = {"itemsanity": True}

    def test_all_frozen_locations_are_created_in_order(self):
        created = ITEMSANITY_CLASS.created_locations(self.world.options)
        self.assertEqual(len(created), 22)
        self.assertEqual([code for _name, code, _region in created],
                         list(range(ITEMSANITY_CODE_BASE, ITEMSANITY_CODE_BASE + 22)))
        self.assertEqual([name for name, _code, _region in created],
                         list(ITEMSANITY_CLASS.names()))

    def test_one_of_each_weapon_enters_the_progression_pool(self):
        # The start bootstrap may have seated a weapon on a check in pre_fill.
        items = [item for item in self.multiworld.itempool
                 if item.player == self.player and item.name in ITEM_NAMES]
        items += [location.item for location in self.multiworld.get_locations(self.player)
                  if location.item is not None and location.item.name in ITEM_NAMES]
        self.assertEqual(sorted(item.name for item in items), sorted(ITEM_NAMES))
        self.assertTrue(all(item.advancement for item in items))


    def test_early_items_are_one_weapon_type(self):
        # One early weapon, not one or two: AP locks early items into the
        # starting checks (fuzz 36720, 2026-10-01).
        early = self.multiworld.early_items[self.player]
        weapons = {name: count for name, count in early.items() if name in ITEM_NAMES}
        self.assertEqual(len(weapons), 1)
        self.assertEqual(set(weapons), set(weapons) & set(WEAPONS))
        self.assertEqual(set(weapons.values()), {1})


class TestItemsanityAccessRules(unittest.TestCase):
    PLAYER = 1

    def _state(self, **options):
        mw = _build(itemsanity=True, **options)
        return mw, CollectionState(mw)

    def test_turbo_is_reachable_with_vanilla_boost_when_pack_off(self):
        mw, state = self._state()
        _grant(state, self.PLAYER, "Turbo")
        for juiced in (False, True):
            self.assertTrue(state.can_reach(
                ITEMSANITY_CLASS.location_name("Turbo", juiced), "Location", self.PLAYER))

    def test_turbo_requires_progressive_boost_when_randomized(self):
        mw, state = self._state(progressive_boost="shared_global")
        _grant(state, self.PLAYER, "Turbo")
        self.assertFalse(state.can_reach("Itemsanity: Turbo", "Location", self.PLAYER))
        _grant(state, self.PLAYER, "Progressive Boost")
        self.assertTrue(state.can_reach("Itemsanity: Turbo", "Location", self.PLAYER))
        self.assertTrue(state.can_reach("Itemsanity: Turbo (Juiced)", "Location", self.PLAYER))

    def test_turbo_reads_a_driveable_private_chain(self):
        mw, state = self._state(progressive_boost="per_character")
        world = mw.worlds[self.PLAYER]
        racer = world.ctr_starting_character
        _grant(state, self.PLAYER, "Turbo")
        self.assertFalse(state.can_reach(
            "Itemsanity: Turbo", "Location", self.PLAYER))
        state.add_item(progressive_capability.boost_item_name(racer),
                       self.PLAYER, 1)
        self.assertTrue(state.can_reach(
            "Itemsanity: Turbo", "Location", self.PLAYER))

    def test_every_non_turbo_pair_requires_its_weapon_only(self):
        for weapon in WEAPONS[1:]:
            with self.subTest(weapon=weapon):
                mw, state = self._state()
                plain = ITEMSANITY_CLASS.location_name(weapon, False)
                juiced = ITEMSANITY_CLASS.location_name(weapon, True)
                self.assertFalse(state.can_reach(plain, "Location", self.PLAYER))
                _grant(state, self.PLAYER, weapon)
                self.assertTrue(state.can_reach(plain, "Location", self.PLAYER))
                self.assertTrue(state.can_reach(juiced, "Location", self.PLAYER))

    def test_non_turbo_weapons_ignore_progressive_boost_when_randomized(self):
        """Regression for the 2026-08-10 fuzz FillErrors: the boost term must
        attach to Turbo ONLY (Decision 2 ruling), never to the other ten."""
        for weapon in WEAPONS[1:]:
            with self.subTest(weapon=weapon):
                mw, state = self._state(progressive_boost="shared_global")
                plain = ITEMSANITY_CLASS.location_name(weapon, False)
                juiced = ITEMSANITY_CLASS.location_name(weapon, True)
                _grant(state, self.PLAYER, weapon)
                self.assertTrue(state.can_reach(plain, "Location", self.PLAYER))
                self.assertTrue(state.can_reach(juiced, "Location", self.PLAYER))


class TestBoostChainClassification(unittest.TestCase):
    """The Turbo gate is only real if the boost chain is progression in
    exactly the seeds whose rules read it (create_item's per-seed upgrade)."""
    PLAYER = 1

    def _boost_items(self, **options):
        mw = _build(**options)
        return [item for item in mw.itempool
                if item.player == self.PLAYER
                and item.name == "Progressive Boost"]

    def test_progression_when_itemsanity_reads_the_tier(self):
        items = self._boost_items(itemsanity=True,
                                  progressive_boost="shared_global")
        self.assertTrue(items)
        self.assertTrue(all(item.advancement for item in items))

    def test_progression_without_itemsanity_too(self):
        """The upgrade stopped being itemsanity's to grant. The USF finish gate
        (ruled 2026-08-12) reads the chain on Hot Air Skyway's Trophy
        Race, a static location in every seed, so a randomized boost chain is
        progression whether or not itemsanity is on."""
        items = self._boost_items(itemsanity=False,
                                  progressive_boost="shared_global")
        self.assertTrue(items)
        self.assertTrue(all(item.advancement for item in items))

    def test_no_boost_items_when_pack_off(self):
        self.assertEqual(self._boost_items(itemsanity=True), [])




class TestFamilyCountPrimitive(unittest.TestCase):
    PLAYER = 1

    def test_counts_distinct_families_not_alternate_items(self):
        mw = _build()
        state = CollectionState(mw)
        _grant(state, self.PLAYER, "Missile", "Missile x3", "Bomb x3", "Mask")
        self.assertEqual(family_count(state, self.PLAYER, USEFUL_WEAPON_FAMILIES), 3)

    def test_primitive_is_not_attached_to_trophy_locations(self):
        mw = _build(itemsanity=True)
        state = CollectionState(mw)
        for item in mw.worlds[self.PLAYER]._item_data_by_name:
            if item not in ITEM_NAMES and item != "Progressive Boost":
                state.add_item(item, self.PLAYER, 99)
        self.assertTrue(state.can_reach("Crash Cove: Trophy Race", "Location", self.PLAYER))
