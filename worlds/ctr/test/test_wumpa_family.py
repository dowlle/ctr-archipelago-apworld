"""Gates for the wumpa family: two bundle fillers, the starting ladder, one check.

The family was minted by the 0.2.0 name freeze at count 0 and left inert. These
pin the half that makes it real, and in particular the two properties that are
easy to break without noticing:

  * a bundles-OFF seed must be generated exactly as it was before the option
    existed, including taking no RNG draw, because the vanilla fill backstop
    replays a simulated fill move for move,
  * the bundles must cost NO supply (they substitute into the filler budget)
    while the ladder DOES (every copy is one otherwise-filler slot spent), which
    is why they are handled by different functions.
"""
import unittest

from BaseClasses import ItemClassification

from ..Items import load_item_table
from ..wumpa_checks import WUMPA_CLASS, WUMPA_CODE_BASE, WUMPA_TEN_LOCATION
from ..wumpa_family import (
    BUNDLE_WUMPA_COUNT, FILLER_WEIGHTS, PROGRESSIVE_WUMPA_ITEM,
    PROGRESSIVE_WUMPA_MAX, WUMPA_BUNDLE_ITEMS, draw_filler_name, filler_weights,
)
from . import CTRTestBase


class TestFrozenNames(unittest.TestCase):
    """The datapackage half, unchanged by activation: the names and ids the
    freeze minted are exactly the ones this build creates."""

    def test_the_three_item_names_exist_in_the_table(self) -> None:
        table = {item["name"]: item for item in load_item_table()}
        for name in WUMPA_BUNDLE_ITEMS + [PROGRESSIVE_WUMPA_ITEM]:
            self.assertIn(name, table)

    def test_both_bundles_are_filler_classified(self) -> None:
        """Not cosmetic. Filler classification is what puts them in the overflow
        shedder's first tier with no rule of their own, and what lets them
        substitute into the filler budget at all."""
        table = {item["name"]: item for item in load_item_table()}
        for name in WUMPA_BUNDLE_ITEMS:
            self.assertEqual(table[name]["classification"],
                             ItemClassification.filler)

    def test_the_ladder_item_is_useful_not_filler(self) -> None:
        """It persists across a race boundary, so it is opt-in and it spends
        supply. Filler-classifying it would make the shedder eat it."""
        table = {item["name"]: item for item in load_item_table()}
        self.assertEqual(table[PROGRESSIVE_WUMPA_ITEM]["classification"],
                         ItemClassification.useful)

    def test_the_location_name_sits_at_its_frozen_code(self) -> None:
        self.assertEqual(
            [(WUMPA_TEN_LOCATION, WUMPA_CODE_BASE)],
            [(n, c) for n, c, _r in WUMPA_CLASS.all_locations()])


class TestBundleWeights(unittest.TestCase):
    def test_plain_fruit_outweighs_both_bundles_combined(self) -> None:
        """The ruling's balance point: bundles enrich the filler pool, they do
        not replace it. A pool of mostly ten-fruit bundles would trivialise the
        10-wumpa check and itemsanity's juiced checks."""
        self.assertGreater(FILLER_WEIGHTS["Wumpa Fruit"],
                           sum(FILLER_WEIGHTS[n] for n in WUMPA_BUNDLE_ITEMS))

    def test_the_big_bundle_fills_a_kart_and_the_small_one_does_not(self) -> None:
        self.assertEqual(BUNDLE_WUMPA_COUNT["Big Wumpa Bundle"],
                         PROGRESSIVE_WUMPA_MAX)
        self.assertLess(BUNDLE_WUMPA_COUNT["Small Wumpa Bundle"],
                        BUNDLE_WUMPA_COUNT["Big Wumpa Bundle"])


class _FakeOption:
    def __init__(self, value):
        self.value = value


class _FakeWorld:
    """Enough world to drive the two pure filler functions."""

    class _Options:
        pass

    def __init__(self, bundles):
        self.options = self._Options()
        self.options.wumpa_bundles = _FakeOption(bundles)
        self.random = None  # any draw would raise, which is the point below


class TestBundlesOffIsGenerationNeutral(unittest.TestCase):
    """A bundles-off seed must be byte-identical to a pre-activation seed."""

    def test_the_filler_pool_is_the_single_old_name(self) -> None:
        self.assertEqual(filler_weights(_FakeWorld(0)), {"Wumpa Fruit": 1})

    def test_no_rng_draw_is_taken(self) -> None:
        """`random` is None on the fake world, so any draw raises. Passing
        proves the single-name path returns directly instead of asking
        `random.choices` for a one-element draw -- which matters because the
        vanilla fill backstop replays a simulated fill and asserts it draws
        identically to the real one."""
        self.assertEqual(draw_filler_name(_FakeWorld(0)), "Wumpa Fruit")


class TestBundlesOffSeed(CTRTestBase):
    """Default seed: the family is entirely absent."""

    def test_no_bundle_and_no_ladder_item_is_created(self) -> None:
        names = {i.name for i in self.multiworld.itempool if i.player == self.player}
        for name in WUMPA_BUNDLE_ITEMS + [PROGRESSIVE_WUMPA_ITEM]:
            self.assertNotIn(name, names)

    def test_the_check_location_is_absent(self) -> None:
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        self.assertNotIn(WUMPA_TEN_LOCATION, names)

    def test_the_scalars_are_emitted_and_off(self) -> None:
        ctr_options = self.world.fill_slot_data()["ctr_options"]
        self.assertIn("wumpa_bundles", ctr_options)
        self.assertFalse(ctr_options["wumpa_bundles"])
        self.assertEqual(ctr_options["progressive_starting_wumpa"], 0)

    def test_no_wumpa_location_block_is_emitted(self) -> None:
        self.assertNotIn("wumpa_checks", self.world.fill_slot_data())


class TestBundlesOnSeed(CTRTestBase):
    run_default_tests = False
    options = {"wumpa_bundles": True}

    def test_bundles_reach_the_pool(self) -> None:
        names = {i.name for i in self.multiworld.itempool if i.player == self.player}
        self.assertTrue(names & set(WUMPA_BUNDLE_ITEMS),
                        "the weighted draw produced no bundle at all")

    def test_the_items_and_locations_still_balance(self) -> None:
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(items), len(locations))

    def test_bundles_add_no_location(self) -> None:
        """They substitute into slots the pool was already going to fill."""
        self.assertNotIn(WUMPA_TEN_LOCATION,
                         {l.name for l in self.multiworld.get_locations(self.player)})


class TestLadder(CTRTestBase):
    run_default_tests = False
    options = {"progressive_starting_wumpa": 4}

    def test_exactly_the_requested_number_of_copies(self) -> None:
        copies = [i for i in self.multiworld.itempool
                  if i.player == self.player and i.name == PROGRESSIVE_WUMPA_ITEM]
        self.assertEqual(len(copies), 4)

    def test_the_copies_are_useful_and_not_progression(self) -> None:
        copies = [i for i in self.multiworld.itempool
                  if i.player == self.player and i.name == PROGRESSIVE_WUMPA_ITEM]
        for item in copies:
            self.assertFalse(item.advancement)
            self.assertEqual(item.classification, ItemClassification.useful)

    def test_the_ladder_adds_no_location_so_it_spends_supply(self) -> None:
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(items), len(locations))

    def test_the_scalar_carries_the_count(self) -> None:
        ctr_options = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual(ctr_options["progressive_starting_wumpa"], 4)


class TestWumpaCheck(CTRTestBase):
    run_default_tests = False
    options = {"wumpa_check": True}

    def test_exactly_one_location_is_created(self) -> None:
        names = [l.name for l in self.multiworld.get_locations(self.player)
                 if l.name == WUMPA_TEN_LOCATION]
        self.assertEqual(len(names), 1)

    def test_the_wire_block_carries_the_frozen_code(self) -> None:
        """Native reads the code out of the block rather than hardcoding it, so
        a future second wumpa check needs no wire rework."""
        block = self.world.fill_slot_data()["wumpa_checks"]
        self.assertTrue(block["enabled"])
        self.assertEqual(block["locations"], [WUMPA_CODE_BASE])

    def test_it_supplies_a_location_rather_than_spending_one(self) -> None:
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(items), len(locations))


class TestNativeContract(unittest.TestCase):
    """The apworld half is only correct if it matches what the client already
    implements. These pin the three facts the native side reads.

    Verified against the client's H-dossier wumpa commit: it dispatches the two
    bundles and the ladder by ITEM TABLE INDEX (120, 121, 122), and its
    AP_EmitWumpaCheck hardcodes 35016100 and gates on
    `ap_net_location_exists`, i.e. on server location membership rather than on
    anything in slot_data.
    """

    def test_the_three_names_sit_at_the_indexes_native_dispatches_on(self) -> None:
        table = load_item_table()
        self.assertEqual(table[120]["name"], "Small Wumpa Bundle")
        self.assertEqual(table[121]["name"], "Big Wumpa Bundle")
        self.assertEqual(table[122]["name"], PROGRESSIVE_WUMPA_ITEM)

    def test_the_check_code_is_the_one_native_hardcodes(self) -> None:
        self.assertEqual(WUMPA_CODE_BASE, 35016100)

    def test_the_ladder_ceiling_matches_the_karts_own_cap(self) -> None:
        """Native clamps its bank to ten because a kart holds ten fruit. An
        eleventh copy could never be felt, so the option must not offer one."""
        self.assertEqual(PROGRESSIVE_WUMPA_MAX, 10)
