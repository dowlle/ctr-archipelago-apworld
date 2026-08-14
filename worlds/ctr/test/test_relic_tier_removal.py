"""Tests for issue #171 (exact-count relic options) + issue #28 R1-R3 (removal,
not pinning), worlds/ctr/relic_tiers.py + the create_regions/create_items/
forced_options integration.

Real-generation coverage (edge counts 0/1/17/18 per tier, the Turbo Track
comfort-guard clamp, the two new gate-count guards) lives in the build note's
evidence, not here -- this file is the fast, direct unit layer: the draw
itself, location creation/removal, UT reconstruction, and the P1 INFO log.
"""
import unittest

from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld, forced_options
from ..relic_tiers import (
    RELIC_TIERS, draw_relic_tier_keep, restore_relic_tier_keep_from_wire,
    tier_location_pool,
)
from . import CTRTestBase

EARLY = ("generate_early",)
REGIONS = ("generate_early", "create_regions")
LOGGER_NAME = "worlds.ctr.forced_options"
RELIC_LOGGER_NAME = "worlds.ctr.relic_tiers"
REGIONS_LOGGER_NAME = "worlds.ctr.Regions"


def _early(options):
    return setup_multiworld(ctrAPWorld, EARLY, options=options)


def _with_regions(options):
    return setup_multiworld(ctrAPWorld, REGIONS, options=options)


class TestDrawRelicTierKeep(unittest.TestCase):
    """The draw itself: exact counts, subset-of-18, deterministic per seed."""

    def test_created_counts_match_options(self):
        mw = _early({
            "accessibility": "minimal",
            "sapphire_relic_count": 5, "gold_relic_count": 12,
            "platinum_relic_count": 0,
        })
        world = mw.worlds[1]
        self.assertEqual(world._ctr_relic_created["Sapphire Relic"], 5)
        self.assertEqual(world._ctr_relic_created["Gold Relic"], 12)
        self.assertEqual(world._ctr_relic_created["Platinum Relic"], 0)
        self.assertEqual(len(world._ctr_relic_keep["Sapphire Relic"]), 5)
        self.assertEqual(len(world._ctr_relic_keep["Gold Relic"]), 12)
        self.assertEqual(len(world._ctr_relic_keep["Platinum Relic"]), 0)

    def test_kept_names_are_a_subset_of_the_18(self):
        mw = _early({"accessibility": "minimal", "sapphire_relic_count": 7})
        world = mw.worlds[1]
        pool = set(tier_location_pool(world.location_name_to_id, "Sapphire"))
        self.assertEqual(len(pool), 18)
        self.assertTrue(world._ctr_relic_keep["Sapphire Relic"] <= pool)

    def test_boundary_zero_and_eighteen(self):
        mw = _early({
            "accessibility": "minimal",
            "sapphire_relic_count": 0, "gold_relic_count": 18,
            "platinum_relic_count": 0,
        })
        world = mw.worlds[1]
        self.assertEqual(world._ctr_relic_keep["Sapphire Relic"], frozenset())
        self.assertEqual(
            world._ctr_relic_keep["Gold Relic"],
            set(tier_location_pool(world.location_name_to_id, "Gold")))

    def test_deterministic_for_the_same_seed(self):
        opts = {"accessibility": "minimal", "sapphire_relic_count": 9}
        mw_a = setup_multiworld(ctrAPWorld, EARLY, seed=12345, options=opts)
        mw_b = setup_multiworld(ctrAPWorld, EARLY, seed=12345, options=opts)
        self.assertEqual(
            mw_a.worlds[1]._ctr_relic_keep["Sapphire Relic"],
            mw_b.worlds[1]._ctr_relic_keep["Sapphire Relic"])


class TestLocationRemoval(unittest.TestCase):
    """create_regions must build Location objects for exactly the kept set,
    and no others (R1: registered but not created)."""

    def test_removed_slots_have_no_location_object(self):
        mw = _with_regions({
            "accessibility": "minimal",
            "sapphire_relic_count": 3, "gold_relic_count": 18,
            "platinum_relic_count": 0,
        })
        world = mw.worlds[1]
        created = set(mw.regions.location_cache[1].keys())
        sapphire_pool = set(tier_location_pool(world.location_name_to_id, "Sapphire"))
        platinum_pool = set(tier_location_pool(world.location_name_to_id, "Platinum"))
        self.assertEqual(len(created & sapphire_pool), 3)
        self.assertEqual(len(created & platinum_pool), 0)
        # Every kept name IS a created location, every removed name is NOT.
        for name in world._ctr_relic_keep["Sapphire Relic"]:
            self.assertIn(name, created)
        for name in sapphire_pool - world._ctr_relic_keep["Sapphire Relic"]:
            self.assertNotIn(name, created)

    def test_datapackage_superset_unaffected_by_creation(self):
        # The frozen datapackage (location_name_to_id) always has all 18 per
        # tier, independent of what this seed created -- the #176 convention.
        mw = _with_regions({"accessibility": "minimal", "platinum_relic_count": 0})
        world = mw.worlds[1]
        self.assertEqual(
            len(tier_location_pool(world.location_name_to_id, "Platinum")), 18)


class TestUTReconstruction(unittest.TestCase):
    """Universal Tracker must rebuild the SAME keep-set the real seed created,
    not re-roll a different one."""

    def test_wire_roundtrip_matches_real_seed(self):
        mw = _early({"accessibility": "minimal", "sapphire_relic_count": 6,
                     "gold_relic_count": 11, "platinum_relic_count": 2})
        world = mw.worlds[1]
        real_keep = {k: set(v) for k, v in world._ctr_relic_keep.items()}
        real_created = dict(world._ctr_relic_created)

        wire_relic_tier_locations = {
            relic_item: sorted(
                world.location_name_to_id[name]
                for name in world._ctr_relic_keep.get(relic_item, ()))
            for _tier_label, relic_item, _opt in RELIC_TIERS
        }
        keep, created = restore_relic_tier_keep_from_wire(
            world, {"relic_tier_locations": wire_relic_tier_locations})
        self.assertEqual({k: set(v) for k, v in keep.items()}, real_keep)
        self.assertEqual(created, real_created)

    def test_missing_wire_key_falls_back_to_full_18(self):
        mw = _early({"accessibility": "minimal", "sapphire_relic_count": 4})
        world = mw.worlds[1]
        keep, created = restore_relic_tier_keep_from_wire(world, {})
        for _tier_label, relic_item, _opt in RELIC_TIERS:
            self.assertEqual(created[relic_item], 18)
            self.assertEqual(len(keep[relic_item]), 18)


class TestP1NeverCreatedExcludeLog(unittest.TestCase):
    """Issue #28 P1: excluding a name this seed never created logs one INFO
    line and changes nothing else."""

    def test_logs_for_a_removed_relic_slot(self):
        with self.assertLogs(REGIONS_LOGGER_NAME, level="INFO") as cm:
            _with_regions({
                "platinum_relic_count": 0,
                "exclude_locations": ["Crash Cove: Platinum Time Trial"],
            })
        joined = "\n".join(cm.output)
        self.assertIn("Crash Cove: Platinum Time Trial", joined)
        self.assertIn("never created", joined)

    def test_does_not_log_for_a_created_location(self):
        import logging
        logger = logging.getLogger(REGIONS_LOGGER_NAME)
        with self.assertRaises(AssertionError):
            # No INFO record expected -- assertLogs itself raises when nothing
            # was logged at/above the given level, which is the assertion we want.
            with self.assertLogs(REGIONS_LOGGER_NAME, level="INFO"):
                _with_regions({
                    "gold_relic_count": 18,
                    "exclude_locations": ["Crash Cove: Gold Time Trial"],
                })


class TestTurboTrackComfortGuardClamp(unittest.TestCase):
    """Issue #171's replacement for the old force-pin: exclude Turbo Track's
    own slot from the sample pool, clamping the achievable count by 1 with a
    warning, only while the comfort guard is active."""

    def test_clamps_and_warns_when_guard_active(self):
        with self.assertLogs(RELIC_LOGGER_NAME, level="WARNING") as cm:
            mw = _early({
                "accessibility": "minimal",
                "warppad_unlock_requirements": "vanilla",
                "shuffle_gems": False,
                "sapphire_relic_count": 18,
            })
        world = mw.worlds[1]
        self.assertEqual(world._ctr_relic_created["Sapphire Relic"], 17)
        self.assertNotIn(
            "Turbo Track: Sapphire Time Trial",
            world._ctr_relic_keep["Sapphire Relic"])
        self.assertTrue(any("Clamped to 17" in line for line in cm.output))

    def test_no_clamp_when_guard_inactive(self):
        mw = _early({
            "warppad_unlock_requirements": "randomized",
            "shuffle_gems": False,
            "sapphire_relic_count": 18,
        })
        world = mw.worlds[1]
        self.assertEqual(world._ctr_relic_created["Sapphire Relic"], 18)

    def test_no_clamp_below_the_reduced_ceiling(self):
        mw = _early({
            "accessibility": "minimal",
            "warppad_unlock_requirements": "vanilla",
            "shuffle_gems": False,
            "sapphire_relic_count": 10,
        })
        world = mw.worlds[1]
        self.assertEqual(world._ctr_relic_created["Sapphire Relic"], 10)


class TestGateCountGuards(unittest.TestCase):
    """Issue #171/#28 R5: the two fixed-gate guards (full accessibility vs.
    the world.json Sapphire-count gates) and the extended oxide-final guard."""

    def test_full_accessibility_raises_below_18_sapphires(self):
        with self.assertRaises(OptionError) as ctx:
            _early({"accessibility": "full", "sapphire_relic_count": 17})
        self.assertIn("Sapphire Relic", str(ctx.exception))

    def test_full_accessibility_ok_at_18_sapphires(self):
        _early({"accessibility": "full", "sapphire_relic_count": 18})

    def test_minimal_accessibility_warns_not_raises(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({"accessibility": "minimal", "sapphire_relic_count": 5,
                    "oxide_goal": "none", "bosses_required_goal": 4})
        self.assertTrue(any("permanently unreachable" in line for line in cm.output))

    def test_vanilla_full_accessibility_raises_below_10_at_slide_coliseum(self):
        with self.assertRaises(OptionError) as ctx:
            _early({
                "accessibility": "full",
                "warppad_unlock_requirements": "vanilla",
                "sapphire_relic_count": 9,
            })
        self.assertIn("Slide Coliseum", str(ctx.exception))

    def test_randomized_full_accessibility_ignores_slide_coliseum_floor(self):
        # Randomized mode strips the Slide Coliseum vanilla exit gate, so only
        # the unconditional N. Oxide's Final Challenge gate (18) applies.
        _early({
            "accessibility": "full",
            "warppad_unlock_requirements": "randomized",
            "sapphire_relic_count": 18,
        })

    def test_oxidefinal_raises_when_tier_supply_below_requested_count(self):
        with self.assertRaises(OptionError) as ctx:
            _early({
                "oxide_goal": "final",
                "accessibility": "minimal",
                "oxide_final_challenge_unlock": "gold_relics",
                "oxide_final_challenge_relic_count": 10,
                "gold_relic_count": 3,
            })
        self.assertIn("oxidefinal", str(ctx.exception))

    def test_oxidefinal_ok_when_tier_supply_meets_requested_count(self):
        _early({
            "oxide_goal": "final",
            "accessibility": "minimal",
            "oxide_final_challenge_unlock": "gold_relics",
            "oxide_final_challenge_relic_count": 10,
            "gold_relic_count": 10,
        })

    def test_full_accessibility_raises_when_mode_supply_short(self):
        # Issue #53's exact field repro (native verifier profile): non-final
        # goal + platinum mode + count 10 with only 2 platinums created used
        # to GENERATE (the location kept the legacy 18-Sapphire text rule and
        # 18+ sapphires satisfied it), stranding a progression item on a
        # natively-unreachable location. Must now raise instead.
        with self.assertRaises(OptionError) as ctx:
            _early({
                "accessibility": "full",
                "oxide_goal": "first",
                "oxide_final_challenge_unlock": "platinum_relics",
                "oxide_final_challenge_relic_count": 10,
                "platinum_relic_count": 2,
            })
        self.assertIn("Final Challenge", str(ctx.exception))
        self.assertIn("platinum", str(ctx.exception))

    def test_full_accessibility_ok_when_mode_supply_meets(self):
        _early({
            "accessibility": "full",
            "oxide_goal": "first",
            "oxide_final_challenge_unlock": "platinum_relics",
            "oxide_final_challenge_relic_count": 10,
            "platinum_relic_count": 10,
        })

    def test_minimal_accessibility_mode_supply_short_warns_not_raises(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            _early({
                "accessibility": "minimal",
                "oxide_goal": "first",
                "oxide_final_challenge_unlock": "platinum_relics",
                "oxide_final_challenge_relic_count": 10,
                "platinum_relic_count": 2,
            })
        self.assertTrue(
            any("permanently unreachable" in line for line in cm.output))

    def test_oxidefinal_total_relics_sums_across_progression_tiers(self):
        # total_relics in randomized mode: all three tiers are progression, so
        # the guard must sum their CREATED counts (5+5+0=10), not just count
        # progression tiers (which would wrongly pass any count <= 18).
        _early({
            "oxide_goal": "final",
            "accessibility": "minimal",
            "warppad_unlock_requirements": "randomized",
            "oxide_final_challenge_unlock": "total_relics",
            "oxide_final_challenge_relic_count": 10,
            "sapphire_relic_count": 5,
            "gold_relic_count": 5,
            "platinum_relic_count": 0,
        })
        with self.assertRaises(OptionError):
            _early({
                "oxide_goal": "final",
                "accessibility": "minimal",
                "warppad_unlock_requirements": "randomized",
                "oxide_final_challenge_unlock": "total_relics",
                "oxide_final_challenge_relic_count": 11,
                "sapphire_relic_count": 5,
                "gold_relic_count": 5,
                "platinum_relic_count": 0,
            })


class TestOxideFinalLocationRuleFollowsMode(CTRTestBase):
    """Issue #53: the Final Challenge LOCATION rule must read the configured
    oxide_final_challenge_unlock mode + count in a NON-final-goal seed
    (native parity with AP_VF_OXIDE_FIN), not data/world.json's legacy
    18-Sapphire text."""

    run_default_tests = False
    options = {
        "accessibility": "full",
        "oxide_goal": "first",
        "oxide_final_challenge_unlock": "platinum_relics",
        "oxide_final_challenge_relic_count": 3,
        "platinum_relic_count": 3,
        "shuffle_keys": True,
    }
    LOC = "N. Oxide Garage: N. Oxide's Final Challenge"

    def test_platinums_gate_the_location_not_sapphires(self):
        # Everything except the platinums -- includes all 4 Keys and the full
        # 18 Sapphire Relics, which satisfied the legacy text rule.
        self.collect_all_but(["Platinum Relic"])
        self.assertFalse(
            self.can_reach_location(self.LOC),
            "18 Sapphires + 4 Keys opened the Final Challenge: the legacy "
            "world.json rule is still installed")
        self.collect_by_name(["Platinum Relic"])
        self.assertTrue(self.can_reach_location(self.LOC))


class TestGeneralPoolSizing(CTRTestBase):
    """create_items must reduce the general relic pool by exactly
    (18 - created), with no place_locked_item calls for removed slots (R1:
    nothing is pinned -- there is nothing left to pin)."""

    # Generic WorldTestBase reachability tests demand all_state reach EVERY
    # location regardless of the configured accessibility -- with a Sapphire
    # count below 18, "N. Oxide's Final Challenge" is legitimately
    # unreachable (the fixed world.json gate this build's guards are about).
    # Same precedent as test_ut_relic_classification.py's minimal-accessibility
    # classes.
    run_default_tests = False
    options = {
        "sapphire_relic_count": 5, "gold_relic_count": 18,
        "platinum_relic_count": 0, "accessibility": "minimal",
        "oxide_goal": "none", "bosses_required_goal": 4,
    }

    def test_pool_relic_item_counts_match_created(self):
        pool_names = [i.name for i in self.multiworld.itempool
                     if i.player == self.player]
        self.assertEqual(pool_names.count("Sapphire Relic")
                         + sum(1 for loc in self.multiworld.get_locations(self.player)
                               if loc.item and loc.item.name == "Sapphire Relic"),
                         5)
        self.assertEqual(pool_names.count("Platinum Relic")
                         + sum(1 for loc in self.multiworld.get_locations(self.player)
                               if loc.item and loc.item.name == "Platinum Relic"),
                         0)


if __name__ == "__main__":
    unittest.main()
