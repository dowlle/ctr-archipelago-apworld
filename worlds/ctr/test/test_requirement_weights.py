"""Regression guard for issue #87: custom requirement weights that zero out
Trophy used to crash generation with a bare ``ValueError`` from random.choices.

With randomized warp-pad requirements (modes 1/2) and requirement_variety=custom,
run_sphere_search draws pad requirements weighted by the effective custom weights.
Trophy is the ONLY item guaranteed present in the synthetic inventory at every
draw (the sphere-0 bootstrap collects the free pads' trophy races first), so a
Trophy weight of 0 makes the candidate weights sum to zero at the first
randomized draw and random.choices raised ``ValueError: Total of weights must be
greater than zero``. generate_early now rejects that config up front with a clean
Options.OptionError.

These tests use test.general.setup_multiworld directly rather than
CTRTestBase/WorldTestBase: WorldTestBase.setUp runs generation in setUp and would
surface the failure as a setup error, so it cannot host an assertRaises case.

The guard is Trophy-specific and deliberately WIDER than the issue's original
"Trophy AND Key both zero" report: Trophy=0 alone crashes at the same rate
because the crashing draws happen before the first Key exists (project ruling,
2026-07-21). Trophy>0 is both necessary and sufficient; Key=0 alone is safe.
"""

import unittest

from Options import OptionError

from test.general import setup_multiworld
from .. import ctrAPWorld


# Only generate_early needs to run to trip the guard; keep the raising cases cheap
# and independent of the rest of the pipeline.
EARLY = ("generate_early",)


def _options(mode, variety="custom", weights=None):
    opts = {
        "warppad_unlock_requirements": mode,
        "requirement_variety": variety,
    }
    if weights is not None:
        opts["requirement_weights"] = weights
    return opts


class TestZeroTrophyWeightRejected(unittest.TestCase):
    """Configs whose effective Trophy weight is 0 must raise a clean OptionError
    at generate_early instead of crashing later in run_sphere_search."""

    def test_mode2_custom_trophy_and_key_zero(self):
        # The issue's exact config.
        with self.assertRaises(OptionError):
            setup_multiworld(
                ctrAPWorld, EARLY,
                options=_options("random_without_4_keys",
                                 weights={"Trophy": 0, "Key": 0}))

    def test_mode1_custom_trophy_zero_alone(self):
        # Trophy=0 with Key at its default: empirically as broken as the pair,
        # and the reason the guard is Trophy-scoped rather than Trophy+Key.
        with self.assertRaises(OptionError):
            setup_multiworld(
                ctrAPWorld, EARLY,
                options=_options("randomized", weights={"Trophy": 0}))

    def test_mode2_custom_all_weights_zero(self):
        all_zero = {k: 0 for k in ctrAPWorld.options_dataclass
                    .type_hints["requirement_weights"].valid_keys}
        with self.assertRaises(OptionError):
            setup_multiworld(
                ctrAPWorld, EARLY,
                options=_options("random_without_4_keys", weights=all_zero))


class TestValidCustomWeightsGenerate(unittest.TestCase):
    """Configs the guard must NOT reject still generate a full world."""

    SEEDS = (1, 2, 3)

    def test_mode2_custom_key_zero_only(self):
        # Key=0 alone is provably safe: Trophy stays at its default 100.
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                setup_multiworld(
                    ctrAPWorld, seed=seed,
                    options=_options("random_without_4_keys",
                                     weights={"Key": 0}))

    def test_mode2_custom_empty_dict_uses_legacy_defaults(self):
        # Empty dict = legacy defaults (Trophy 100), so the guard passes.
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                setup_multiworld(
                    ctrAPWorld, seed=seed,
                    options=_options("random_without_4_keys", weights={}))

    def test_vanilla_mode_ignores_zeroed_weights(self):
        # Vanilla mode never reads the weights, so even Trophy=0 must generate:
        # the guard is scoped to modes 1/2.
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                setup_multiworld(
                    ctrAPWorld, seed=seed,
                    options=_options("vanilla",
                                     weights={"Trophy": 0, "Key": 0}))


if __name__ == "__main__":
    unittest.main()
