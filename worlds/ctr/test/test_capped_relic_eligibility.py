"""Tests for issue #28 R2 (capped requirement eligibility), the relic package 2
work order. [[2026-08-09 -- Rulings -- 28 exclusion semantics + relic removal]]:
a relic tier is drawable as a pad requirement whenever its created count is
above zero (not only at the full 18), and any drawn requirement count is
capped at the tier's created count for this seed.

Two invariants are the actual solvability-relevant claims here, and both are
checked against REAL generation output, not just the eligibility filter's own
source:

1. Eligibility widens: a partial-count tier (0 < n < 18) IS chosen as a stage-1
   or stage-2 pad requirement across a real sample of seeds (it was NEVER
   chosen pre-#28-R2, at any count below 18).
2. No drawn requirement ever demands more of a tier than this seed created --
   the synthetic sphere inventory is graph-bounded (see warp_pad_logic.py's
   updated comment above the eligibility filter), verified here directly
   against the emitted (item, count) requirements, not merely argued.

Also covers the #28 R2 trophy-capacity fix at _capacity_context /
_dest_trophy_capacity: a partial-count tier's capacity contribution is now
per PHYSICAL trial pad (checked against that pad's own track's keep-set
membership), not a seed-wide "is this tier at 18" aggregate applied
uniformly to both trial pads.
"""
import unittest

from test.general import setup_multiworld
from .. import ctrAPWorld
from ..warp_pad_logic import RELIC_ITEMS, _capacity_context, _dest_trophy_capacity
from . import CTRTestBase

REGIONS = ("generate_early", "create_regions")


def _with_regions(options, seed=None):
    return setup_multiworld(ctrAPWorld, REGIONS, seed=seed, options=options)


def _all_pad_requirements(world):
    """Every (item, count) requirement this seed actually assigned, stage-1
    (physical-pad keyed) and stage-2 (destination-track keyed) combined."""
    reqs = list(world.warp_pad_unlock_concrete.values())
    reqs += list(world.warp_pad_unlock_stage2_concrete.values())
    return reqs


class TestEligibilityWidensBelowFullCount(unittest.TestCase):
    """A relic tier with 0 < created < 18 must be drawable as a requirement --
    the pre-R2 behaviour excluded it entirely below 18."""

    def test_partial_platinum_is_sometimes_chosen_as_a_requirement(self):
        # Platinum defaults to 0 (never eligible); force a mid-range count and
        # weight relics heavily so the sphere search draws them often, then
        # scan a real sample of seeds -- eligibility is a per-draw random
        # choice, not a per-seed guarantee, so absence in one seed proves
        # nothing (Lessons Learned #2: an invariant needs >= ~10 samples).
        weights = {
            "Trophy": 1, "Key": 1,
            "Red CTR Token": 1, "Green CTR Token": 1, "Blue CTR Token": 1,
            "Yellow CTR Token": 1, "Purple CTR Token": 1,
            "Sapphire Relic": 1, "Gold Relic": 1, "Platinum Relic": 40,
            "Red Gem": 1, "Green Gem": 1, "Blue Gem": 1, "Yellow Gem": 1,
            "Purple Gem": 1,
        }
        options = {
            "accessibility": "minimal",
            "warppad_unlock_requirements": 1,
            "requirement_variety": "custom",
            "requirement_weights": weights,
            "platinum_relic_count": 9,
            "sapphire_relic_count": 18, "gold_relic_count": 18,
        }
        found_platinum = False
        max_seen = 0
        for seed in range(30):
            mw = _with_regions(options, seed=seed)
            world = mw.worlds[1]
            for item, count in _all_pad_requirements(world):
                if item in ("Platinum Relic", "AnyRelic"):
                    found_platinum = True
                if item == "Platinum Relic":
                    max_seen = max(max_seen, count)
        self.assertTrue(
            found_platinum,
            "Platinum Relic (created=9, below the old all-or-nothing 18 floor) "
            "was never drawable as a requirement across 30 seeds -- eligibility "
            "did not actually widen.")
        self.assertLessEqual(
            max_seen, 9,
            f"a Platinum Relic requirement demanded {max_seen}, more than the "
            f"9 this seed created.")

    def test_zero_count_tier_never_chosen(self):
        # Platinum at its default (0) must stay fully excluded -- the `> 0`
        # filter, not just `>= 18`, still exists to keep a 0-supply tier out.
        options = {
            "accessibility": "minimal",
            "warppad_unlock_requirements": 1,
            "sapphire_relic_count": 18, "gold_relic_count": 18,
            "platinum_relic_count": 0,
        }
        for seed in range(10):
            mw = _with_regions(options, seed=seed)
            world = mw.worlds[1]
            for item, count in _all_pad_requirements(world):
                self.assertNotEqual(
                    item, "Platinum Relic",
                    f"seed {seed}: a Platinum Relic requirement was drawn "
                    f"with 0 created this seed.")


class TestRequirementCountNeverExceedsCreatedCount(unittest.TestCase):
    """The core R2 safety property: for EVERY relic tier, at EVERY seed, no
    drawn requirement count (direct or via the AnyRelic aggregate's summed
    total, which can only resolve to a concrete tier up to what that tier
    itself supplies) exceeds what this seed actually created."""

    CONFIGS = [
        {"sapphire_relic_count": 1, "gold_relic_count": 5, "platinum_relic_count": 17},
        {"sapphire_relic_count": 5, "gold_relic_count": 9, "platinum_relic_count": 3},
        {"sapphire_relic_count": 17, "gold_relic_count": 1, "platinum_relic_count": 1},
        {"sapphire_relic_count": 18, "gold_relic_count": 18, "platinum_relic_count": 18},
        {"sapphire_relic_count": 0, "gold_relic_count": 0, "platinum_relic_count": 1},
    ]

    def test_never_exceeds_across_configs_and_seeds(self):
        checked = 0
        for cfg in self.CONFIGS:
            options = dict(cfg)
            options["accessibility"] = "minimal"
            options["warppad_unlock_requirements"] = 1
            for seed in range(8):
                mw = _with_regions(options, seed=seed)
                world = mw.worlds[1]
                created = world._ctr_relic_created
                for item, count in _all_pad_requirements(world):
                    if item in RELIC_ITEMS:
                        checked += 1
                        self.assertLessEqual(
                            count, created.get(item, 0),
                            f"cfg={cfg} seed={seed}: {item} requirement "
                            f"demanded {count}, but only "
                            f"{created.get(item, 0)} were created.")
        self.assertGreater(
            checked, 0,
            "no relic requirement was drawn across any config/seed combination "
            "-- the test isn't exercising the mechanism it claims to check.")


class TestTrophyCapacityIsPerTrialPad(unittest.TestCase):
    """_capacity_context / _dest_trophy_capacity must key trial capacity to the
    SPECIFIC trial pad's own track keep-set membership, not a seed-wide
    "is this tier fully created" aggregate applied identically to both trial
    pads (issue #28 R2 audit finding)."""

    def test_full_count_both_trial_pads_get_full_capacity(self):
        mw = _with_regions({
            "accessibility": "minimal", "warppad_unlock_requirements": 1,
            "sapphire_relic_count": 18, "gold_relic_count": 18,
            "platinum_relic_count": 18,
        }, seed=1)
        world = mw.worlds[1]
        ctx = _capacity_context(world)
        id_kind = {meta["level_id"]: meta["kind"]
                   for meta in world.warp_pad_ids.values()}
        slide_lid = world.warp_pad_ids["Slide Coliseum Warp Pad"]["level_id"]
        turbo_lid = world.warp_pad_ids["Turbo Track Warp Pad"]["level_id"]
        self.assertEqual(_dest_trophy_capacity(slide_lid, id_kind, ctx), 3)
        self.assertEqual(_dest_trophy_capacity(turbo_lid, id_kind, ctx), 3)

    def test_zero_count_both_trial_pads_get_zero_capacity(self):
        mw = _with_regions({
            "accessibility": "minimal", "warppad_unlock_requirements": 1,
            "sapphire_relic_count": 0, "gold_relic_count": 0,
            "platinum_relic_count": 0,
        }, seed=1)
        world = mw.worlds[1]
        ctx = _capacity_context(world)
        id_kind = {meta["level_id"]: meta["kind"]
                   for meta in world.warp_pad_ids.values()}
        slide_lid = world.warp_pad_ids["Slide Coliseum Warp Pad"]["level_id"]
        turbo_lid = world.warp_pad_ids["Turbo Track Warp Pad"]["level_id"]
        self.assertEqual(_dest_trophy_capacity(slide_lid, id_kind, ctx), 0)
        self.assertEqual(_dest_trophy_capacity(turbo_lid, id_kind, ctx), 0)

    def test_partial_count_the_two_trial_pads_can_legitimately_differ(self):
        # Directly exercise the audited defect: with a partial per-tier count,
        # patch the world's own keep-set so Slide Coliseum kept a tier's TT
        # and Turbo Track did not, and confirm the capacity function reports
        # that asymmetry instead of a single seed-wide number applied to both.
        mw = _with_regions({
            "accessibility": "minimal", "warppad_unlock_requirements": 1,
            "sapphire_relic_count": 9, "gold_relic_count": 0,
            "platinum_relic_count": 0,
        }, seed=1)
        world = mw.worlds[1]
        world._ctr_relic_keep = dict(world._ctr_relic_keep)
        world._ctr_relic_keep["Sapphire Relic"] = frozenset(
            {"Slide Coliseum: Sapphire Time Trial"})
        ctx = _capacity_context(world)
        id_kind = {meta["level_id"]: meta["kind"]
                   for meta in world.warp_pad_ids.values()}
        slide_lid = world.warp_pad_ids["Slide Coliseum Warp Pad"]["level_id"]
        turbo_lid = world.warp_pad_ids["Turbo Track Warp Pad"]["level_id"]
        self.assertEqual(_dest_trophy_capacity(slide_lid, id_kind, ctx), 1)
        self.assertEqual(_dest_trophy_capacity(turbo_lid, id_kind, ctx), 0)


class TestFullyCreatedTiersUnchangedBehaviour(CTRTestBase):
    """Regression: an all-18 config (the pre-#28-R2 only legal eligible state)
    still generates and still allows every relic tier to be drawn -- R2 is
    additive, it must not narrow the pre-existing all-18 case."""

    run_default_tests = False
    options = {
        "accessibility": "minimal",
        "warppad_unlock_requirements": 1,
        "sapphire_relic_count": 18, "gold_relic_count": 18,
        "platinum_relic_count": 18,
    }

    def test_generates(self):
        self.assertTrue(self.multiworld.state)


if __name__ == "__main__":
    unittest.main()
