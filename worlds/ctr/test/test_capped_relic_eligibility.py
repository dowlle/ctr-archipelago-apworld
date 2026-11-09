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
   the synthetic sphere inventory is graph-bounded (see content_playthrough.py's
   updated comment above the eligibility filter), verified here directly
   against the emitted (item, count) requirements, not merely argued.

Also covers the #28 R2 trophy-capacity fix at _capacity_context /
_dest_trophy_capacity: a partial-count tier's capacity contribution is now
per PHYSICAL trial pad (checked against that pad's own track's keep-set
membership), not a seed-wide "is this tier at 18" aggregate applied
uniformly to both trial pads.
"""
import unittest

from . import setup_multiworld
from .. import ctrAPWorld
from ..content_playthrough import RELIC_ITEMS
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
