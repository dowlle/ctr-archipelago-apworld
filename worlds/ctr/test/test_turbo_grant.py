"""Focused gates for the #224 Turbo Grant apworld half.

Every runtime rule the issue lists -- the race window, the empty-slot
precondition, the per-slot queue, the reconnect and race-restart accounting, and
what firing does at each Progressive Boost tier -- is NATIVE's, and none of it is
observable from here. This side owns exactly three things and each one is pinned
below:

  1. the appended name and its frozen code, added without disturbing anything
     the #177 freeze or the #223 amendment signed off,
  2. the option -> pool behaviour (one `useful` item on, nothing at all off,
     zero new locations either way),
  3. the always-emitted wire scalar and its Universal Tracker restore.

It also pins the one thing the ruling forbids: a second Mask-grant name. The
Mask half of this family is the already-frozen `Invincibility Mask`, and the
test below fails if anything ever mints a sibling for it.
"""
import unittest

from BaseClasses import ItemClassification

from ..Items import load_item_table
from ..Locations import CTR_LOCATION_CLASSES
from .. import rung_sizer
from ..tizi_helper import TIZI_HELPER_CODE
from ..turbo_grant import (
    RULED_MASK_SIBLING,
    TURBO_GRANT_CODE,
    TURBO_GRANT_ITEM,
    TURBO_ITEMSANITY_COMPANION,
)
from . import CTRTestBase


class TestTurboGrantName(unittest.TestCase):
    """The datapackage half: one appended name, nothing else moved."""

    def test_the_item_exists_at_its_frozen_code(self) -> None:
        table = {item["name"]: item["code"] for item in load_item_table()}
        self.assertEqual(table[TURBO_GRANT_ITEM], TURBO_GRANT_CODE)

    def test_it_is_appended_one_past_the_223_amendment(self) -> None:
        """35010188 (Tizi Helper) was the previous last entry, so this one is
        35010189 -- the code the Contract's #223 datapackage note reserved.
        Anything else means a renumber, which #224 forbids.

        Turbo Grant is no longer the LAST entry: #280 appended three trap
        identities after it. That is append-only and renumbers nothing, so the
        property this test guards is unchanged; it is spelled out here rather
        than dropped, so a future entry that does renumber still fails."""
        self.assertEqual(TURBO_GRANT_CODE, 35010189)
        self.assertEqual(TURBO_GRANT_CODE, TIZI_HELPER_CODE + 1)
        table = load_item_table()
        codes = [item["code"] for item in table]
        self.assertEqual(codes, list(range(35010000, 35010000 + len(codes))))
        after = [item["name"] for item in table
                 if item["code"] > TURBO_GRANT_CODE]
        # Literal on purpose: importing the module under test's own list would
        # let any append that also updated the registry slip past this guard.
        self.assertEqual(after, ["Upside Down", "Mirror Mode", "Warpball Ambush"])

    def test_it_ships_inert_in_the_data_file(self) -> None:
        """count 0 in data/items.json: the option decides, not the table. The
        classification matches the three frozen sibling grants."""
        entry = next(item for item in load_item_table()
                     if item["name"] == TURBO_GRANT_ITEM)
        self.assertEqual(entry["count"], 0)
        self.assertEqual(entry["classification"], ItemClassification.useful)

    def test_the_itemsanity_companion_the_rule_names_is_a_real_item(self) -> None:
        """The ruled gate names the separate `Turbo` weapon item, which is the
        FIRST itemsanity weapon (held ID 0), so it sits at 35010095. If
        itemsanity ever renames or reorders it, this fails here rather than
        silently ungating the grant on native."""
        table = {item["name"]: item["code"] for item in load_item_table()}
        self.assertIn(TURBO_ITEMSANITY_COMPANION, table)
        self.assertEqual(table[TURBO_ITEMSANITY_COMPANION], 35010095)

    def test_the_mask_sibling_is_the_frozen_name_and_stays_singular(self) -> None:
        """Ruled 2026-08-11: the Mask filler IS `Invincibility Mask`; do not
        mint a duplicate Mask-grant name. Pinned as a census so a later 'Mask
        Grant' addition fails here."""
        names = {item["name"] for item in load_item_table()}
        self.assertIn(RULED_MASK_SIBLING, names)
        mask_grants = {n for n in names if "Mask" in n}
        self.assertEqual(mask_grants, {RULED_MASK_SIBLING, "Mask"})

    def test_it_mints_no_location(self) -> None:
        location_names = {n for n, _c, _r in CTR_LOCATION_CLASSES.all_locations()}
        self.assertFalse({n for n in location_names if "Turbo Grant" in n})


class TestTurboGrantOff(CTRTestBase):
    """Default seed. The option is off, so the item does not exist."""

    def test_no_pool_item(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertNotIn(TURBO_GRANT_ITEM, pool_names)

    def test_wire_scalar_is_emitted_and_false(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertIn("turbo_grant", slot_data["ctr_options"])
        self.assertFalse(slot_data["ctr_options"]["turbo_grant"])


class TestTurboGrantOn(CTRTestBase):
    run_default_tests = False
    options = {"turbo_grant": True}

    def test_exactly_one_useful_copy_enters_the_pool(self) -> None:
        items = [item for item in self.multiworld.itempool
                 if item.player == self.player and item.name == TURBO_GRANT_ITEM]
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0].advancement)
        self.assertTrue(items[0].useful)

    def test_it_adds_no_location(self) -> None:
        """The grant spends a filler slot; it does not buy itself one."""
        self.assertFalse([loc for loc in self.multiworld.get_locations(self.player)
                          if "Turbo Grant" in loc.name])

    def test_wire_scalar_is_true(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["ctr_options"]["turbo_grant"])

    def test_the_rung_sizer_counts_the_supply_spend(self) -> None:
        with_grant = rung_sizer.predicted_mandatory_pool(self.world)
        self.world.options.turbo_grant.value = 0
        without_grant = rung_sizer.predicted_mandatory_pool(self.world)
        self.assertEqual(with_grant, without_grant + 1)


class TestTurboGrantWithItemsanity(CTRTestBase):
    """The ruled gate's other half exists on the same seed: with itemsanity on,
    both the grant and the separate `Turbo` weapon item are receivable. Native
    enforces the AND; this only proves the apworld can supply both."""
    run_default_tests = False
    options = {"turbo_grant": True, "itemsanity": True}

    def test_both_gate_items_are_in_the_pool(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertIn(TURBO_GRANT_ITEM, pool_names)
        self.assertIn(TURBO_ITEMSANITY_COMPANION, pool_names)

    def test_both_scalars_ride_the_same_wire(self) -> None:
        options = self.world.fill_slot_data()["ctr_options"]
        self.assertTrue(options["turbo_grant"])
        self.assertTrue(options["itemsanity"])


class TestTurboGrantWithItsRuledSiblings(CTRTestBase):
    """#224 rides alongside #223 without either disturbing the other: both
    amendments on one seed, one copy each, both scalars on the wire."""
    run_default_tests = False
    options = {"turbo_grant": True, "tizi_helper": True}

    def test_both_amendments_create_exactly_one_copy_each(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertEqual(pool_names.count(TURBO_GRANT_ITEM), 1)
        self.assertEqual(pool_names.count("Tizi Helper"), 1)

    def test_the_frozen_mask_grant_is_not_created_by_either(self) -> None:
        """`Invincibility Mask` stays inert on this branch: its own feature has
        not been built, and neither amendment may create it as a side effect."""
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertNotIn(RULED_MASK_SIBLING, pool_names)


class TestTurboGrantWithBoxLocations(CTRTestBase):
    """#224 item 9 names the authored AP box item pool. Boxes are ordinary
    locations that items seat into freely, so the interaction to pin is a supply
    one: the grant costs one slot and the seed still fills."""
    run_default_tests = False
    options = {"turbo_grant": True, "box_locations": True}

    def test_the_grant_seats_on_a_seed_that_authored_box_locations(self) -> None:
        pool_names = [item.name for item in self.multiworld.itempool
                      if item.player == self.player]
        self.assertEqual(pool_names.count(TURBO_GRANT_ITEM), 1)
        self.assertTrue([loc for loc in self.multiworld.get_locations(self.player)
                         if "Item Box" in loc.name])


class TestTurboGrantUniversalTrackerRestore(CTRTestBase):
    run_default_tests = False
    options = {"turbo_grant": True}

    def test_the_scalar_round_trips(self) -> None:
        wire = self.world.fill_slot_data()
        self.world.options.turbo_grant.value = 0
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.turbo_grant.value, 1)

    def test_a_pre_224_seed_restores_to_off(self) -> None:
        """No key on the wire is any seed generated before this build."""
        wire = self.world.fill_slot_data()
        del wire["ctr_options"]["turbo_grant"]
        self.world.options.turbo_grant.value = 1
        self.world._ut_restore_options(wire)
        self.assertEqual(self.world.options.turbo_grant.value, 0)
