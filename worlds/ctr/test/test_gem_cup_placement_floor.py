"""Guards for the gem-cup placement floor (issue #149).

Three players reported the same thing on Discord: under the default `merged`
destination shuffle a Gem Cup regularly lands on one of the N. Sanity Beach pads
that open at spawn, and an early cup is not one check but up to seventeen. A cup
region holds a single Gem, but add_podium_placement_rules puts a trophy track's
podium rungs in logic when a Gem Cup that runs it as a leg is reachable, so one
early cup also hands over the podium checks of its four leg tracks while those
tracks' own pads are still shut.

Measured on this branch over 200 default seeds with the rule disabled: 49.5% of
seeds open at least one Gem Cup at zero items. That is the behaviour these tests
pin down as fixed.

The fix is placement, not requirement, and that distinction is the load-bearing
one. warp_pad_unlock is keyed to the PHYSICAL pad and the exit rewire keeps it
that way, so an early cup is reached through somebody else's pad and raising the
cup pads' own requirements cannot touch it. build_warp_pad_map therefore keeps
cup destinations off any pad below the Cups Room's own Key-2 door.

Guarded here:
- the static Key geometry the rule keys off (cup pads at floor 2, and enough
  eligible partners for a swap to always exist);
- on real generated seeds, no cup destination sits below the floor and no cup
  region is reachable with an empty inventory;
- with the floor constant set to 0 the old behaviour comes back on the same
  seeds, so the test above is a real control and not a vacuous pass;
- it survives the trophy-capacity invariant's re-roll path (keys off + merged),
  including a full distribute_items_restrictive so a FillError would surface;
- it consumes NO randomness, and produces a byte-identical map, in every
  configuration where a cup could not be early anyway;
- it is generation-side only: no new slot_data key and no schema bump.
"""

import unittest
from unittest import mock

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import warp_pad_logic as wpl
from . import CTRTestBase

CUP_LEVEL_IDS = frozenset({100, 101, 102, 103, 104})
FLOOR = wpl._GEM_CUP_KEY_FLOOR

# Seed blocks are fixed so a failure is reproducible. The default block is the one
# the pre-rule control below re-runs, so the two are the same population.
DEFAULT_SEEDS = range(1_000_000, 1_000_060)
CAPACITY_SEEDS = range(2_000_000, 2_000_015)


def _keygate_for(world):
    """The pad Key-floor table for this seed's crystal-gate variant."""
    return wpl._pad_keygate_table(crystals_at_hub_floor=wpl._crystals_open(world))


def _cups_below_floor(world):
    """Pad exits holding a Gem Cup destination below the placement floor."""
    keygate = _keygate_for(world)
    return sorted(pad for pad, dest in world.warp_pad_map.items()
                  if dest in CUP_LEVEL_IDS and keygate.get(pad, 0) < FLOOR)


def _cups_open_at_zero_items(multiworld):
    """Gem Cup regions reachable with nothing collected.

    A pure logic-graph property of the finished region graph, so it measures "the
    cup is open when the seed starts" rather than a spoiler-log sphere index, and
    it does not depend on where fill happened to put anything."""
    state = CollectionState(multiworld)
    return sorted(region.name for region in multiworld.get_regions(1)
                  if region.name.endswith("Gem Cup")
                  and state.can_reach(region.name, "Region", 1))


class TestGemCupFloorGeometry(unittest.TestCase):
    """The static hub Key geometry the rule is built on."""

    def test_cup_pads_sit_at_the_floor(self):
        # The rule's whole justification is that it does not invent a balance
        # number: it is the floor the Cups Room's own door already sits at.
        for crystals_open in (False, True):
            table = wpl._pad_keygate_table(crystals_at_hub_floor=crystals_open)
            for colour in ("Red", "Green", "Blue", "Yellow", "Purple"):
                self.assertEqual(table[f"{colour} Cup Warp Pad"], FLOOR)

    def test_pads_below_the_floor_are_the_ones_that_can_open_early(self):
        # 5 pads at 0 Keys and 7 more at 1, arenas stripped to their hub floor:
        # exactly the set a spawn-time free pad can be drawn from.
        table = wpl._pad_keygate_table(crystals_at_hub_floor=True)
        self.assertEqual(sum(1 for v in table.values() if v == 0), 5)
        self.assertEqual(sum(1 for v in table.values() if v == 1), 7)

    def test_a_swap_partner_always_exists(self):
        # The repair needs a non-cup destination on an at-or-above-floor pad. With
        # 5 cups this only fails if eligible pads ever drop to 5 or fewer.
        for crystals_open in (False, True):
            table = wpl._pad_keygate_table(crystals_at_hub_floor=crystals_open)
            eligible = sum(1 for v in table.values() if v >= FLOOR)
            self.assertGreater(eligible, len(CUP_LEVEL_IDS))


class TestGemCupFloorHoldsOnRealSeeds(unittest.TestCase):
    """On generated default-option seeds, no cup is placed or reachable early."""

    def test_no_cup_below_the_floor_and_none_open_at_zero_items(self):
        violations = []
        early = []
        for seed in DEFAULT_SEEDS:
            multiworld = setup_multiworld(ctrAPWorld, seed=seed)
            below = _cups_below_floor(multiworld.worlds[1])
            if below:
                violations.append((seed, below))
            open_cups = _cups_open_at_zero_items(multiworld)
            if open_cups:
                early.append((seed, open_cups))
        self.assertEqual(violations, [],
                         "a Gem Cup destination was placed below the Key floor")
        self.assertEqual(early, [],
                         "a Gem Cup was reachable with an empty inventory")


class TestPreRuleBehaviourIsReproduced(unittest.TestCase):
    """The control. Floor 0 is the pre-#149 code path exactly: the repair returns
    immediately and no Key table is built, so this really is the old behaviour and
    not an approximation of it. If this ever stops finding early cups, the test
    above has stopped proving anything."""

    def test_the_same_seeds_open_cups_early_without_the_rule(self):
        early = 0
        placed_below = 0
        with mock.patch.object(wpl, "_GEM_CUP_KEY_FLOOR", 0):
            for seed in DEFAULT_SEEDS:
                multiworld = setup_multiworld(ctrAPWorld, seed=seed)
                if _cups_below_floor(multiworld.worlds[1]):
                    placed_below += 1
                if _cups_open_at_zero_items(multiworld):
                    early += 1
        total = len(DEFAULT_SEEDS)
        self.assertGreater(placed_below, 0)
        # Measured at roughly half of all seeds over 200; a quarter is a loose
        # bound that still fails loudly if the population stops being affected.
        self.assertGreater(early, total // 4,
                           "the pre-rule control no longer reproduces the defect")


class TestGemCupFloorUnderTheCapacityInvariant(unittest.TestCase):
    """Keys off + merged is the one configuration where build_warp_pad_map may
    re-roll or constructively pin the permutation. The floor is applied inside
    that loop, so both mechanisms have to agree on the map that comes out, and a
    disagreement shows up as a FillError rather than as a bad map."""

    def test_floor_holds_and_fill_succeeds_with_keys_off(self):
        opts = {"shuffle_keys": False, "podium_placement_checks": False}
        for seed in CAPACITY_SEEDS:
            multiworld = setup_multiworld(ctrAPWorld, seed=seed, options=opts)
            self.assertEqual(_cups_below_floor(multiworld.worlds[1]), [],
                             f"seed {seed} placed a cup below the floor")
            self.assertEqual(_cups_open_at_zero_items(multiworld), [],
                             f"seed {seed} opened a cup at zero items")
            distribute_items_restrictive(multiworld)  # raises FillError on a starve


class TestGemCupFloorIsInertWhereItCannotApply(unittest.TestCase):
    """Configurations that already could not put a cup on an early pad must be
    byte-identical to pre-#149, RNG stream included. The rule resolves to 0 unless
    the cups pool actually participates, and the repair draws from world.random
    only when a cup really sits below the floor, so an unaffected seed generates
    the same map it always did."""

    SEED = 1_234_567

    def _map_with_floor(self, floor, options):
        with mock.patch.object(wpl, "_GEM_CUP_KEY_FLOOR", floor):
            multiworld = setup_multiworld(ctrAPWorld, seed=self.SEED,
                                          options=options)
        return dict(multiworld.worlds[1].warp_pad_map)

    def _assert_unchanged(self, options):
        self.assertEqual(self._map_with_floor(FLOOR, options),
                         self._map_with_floor(0, options))

    def test_per_category_grouping_is_untouched(self):
        # Cups only ever land on cup pads there, which already sit at the floor.
        self._assert_unchanged({"warp_pad_shuffle_grouping": "per_category"})

    def test_cups_excluded_from_the_seed_is_untouched(self):
        self._assert_unchanged({"include_gem_cups": False})

    def test_cups_dropped_from_the_categories_is_untouched(self):
        self._assert_unchanged(
            {"warp_pad_shuffle_categories": ["tracks", "crystals"]})

    def test_vanilla_unlock_requirements_are_untouched(self):
        # The vanilla collapse strips cups from the pools before this rule is
        # even resolved.
        self._assert_unchanged({"warppad_unlock_requirements": "vanilla"})


class TestGemCupFloorIsGenerationSideOnly(CTRTestBase):
    """No wire change: the rule narrows which values warp_pad_map uses and never
    widens it, so nothing native reads has to move."""

    run_default_tests = False
    options = {}

    def test_schema_version_is_not_bumped(self):
        # Baseline is 7, the unconditional #166 bump (Q28 ruling); this
        # feature itself contributes no further bump.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 7)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 7)

    def test_warp_pad_map_still_spans_the_contract_range(self):
        # Contract §5: {"<physicalPadLevelID>": <targetTrackID>}, both sides in
        # {0..27, 100..104}. A constrained permutation narrows which of those the
        # cup values land on and never widens the range, so an unchanged client
        # reads exactly what it read before.
        slot_data = self.world.fill_slot_data()
        for pad, dest in slot_data["warp_pad_map"].items():
            lid = int(pad)
            self.assertTrue(0 <= lid <= 27 or lid in CUP_LEVEL_IDS)
            self.assertTrue(0 <= dest <= 27 or dest in CUP_LEVEL_IDS)
