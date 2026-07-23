"""Regression guard for issue #75: no default-config seed geography-caps sphere-0
breadth below the repair threshold.

Background. #75 is the residual of the #65 sphere-0 work -- "seeds whose sphere-0
breadth cannot be widened by ANY free-subset choice." A 2026-07-22 measurement pass
on #75 found that class EMPTY on main: 0 / 2500 default seeds capped over a 16-roll
probe (2x the shipped 8-roll budget), the single worst seed still reaching max
breadth 7. The gems-and-arenas-on flagship defaults widened sphere 0 far above the
_SPHERE0_MIN_BREADTH threshold, dissolving the narrow pre-flip geometry #75 described.

This test locks that in. It changes NO generation behaviour; it only asserts a
property of the shipped defaults, so a FUTURE default flip in Options.py that
re-narrows sphere 0 is caught here (as a fast unit failure) instead of in the field
as an intermittent multiworld FillError. The intent of #75: the capped class is
empty today, keep it that way by construction.

Metric -- identical instrument to the research, not a re-implementation. For each of
a batch of default-config seeds, roll ``_run_sphere_search_once`` the shipped repair
budget of ``_SPHERE0_REPAIR_TRIES`` times (each roll redraws the free subset from
``world.random``), measure ``_sphere0_breadth`` on each roll, and take the max. A
seed is "geography-capped" iff that max stays below ``_SPHERE0_MIN_BREADTH`` -- i.e.
no free-subset draw within the shipped budget widens sphere 0 past the threshold, the
exact condition the ``run_sphere_search`` re-roll exists to defeat. The guard asserts
zero capped seeds.

N is a few hundred, not the research's 2500: enough power to catch a default flip
that re-narrows the whole class (in the pre-flip regime narrow rolls were common and
seeds capped in bulk) while staying a fast unit test. The 2500-seed breadth census
and the 6000-seed multiworld fill census are the full evidence behind #75.
"""

import unittest

from .. import Regions, warp_pad_logic as wpl
from . import CTRTestBase

# Contiguous 0-based seed range, matching the research census's sampling.
_GUARD_SEEDS = 300
_SEED0 = 0


class TestSphere0BreadthGuardDefault(CTRTestBase):
    """Shipped defaults: no option overrides, so this guard tracks whatever the
    live Options.py defaults are. Keeping ``options`` empty also means the heavy
    WorldTestBase default battery does not re-run for this class (see
    ``run_default_tests``); only the guard below executes."""

    options: dict = {}

    def _breadth_probe(self, seed):
        """Roll the world's own live sphere-search instrument for one seed.

        Returns ``(world, breadths)`` where ``breadths`` is the per-roll sphere-0
        breadth over the shipped repair budget. Mirrors the 2026-07-22 census loop
        exactly (same ``mode`` / ``reward_track_for`` / ``include_gem_cups`` args,
        same ``_run_sphere_search_once`` -> ``_sphere0_breadth`` path)."""
        self.world_setup(seed=seed)
        world = self.world
        mode = getattr(world, "_ctr_unlock_mode", 1)
        rtf = Regions._build_reward_track_resolver(world)
        gems = bool(world.options.include_gem_cups.value)
        breadths = [
            wpl._sphere0_breadth(
                world,
                wpl._run_sphere_search_once(world, mode, rtf, False, gems),
                rtf, gems)
            for _ in range(wpl._SPHERE0_REPAIR_TRIES)
        ]
        return world, breadths

    def test_no_default_seed_caps_sphere0_breadth(self):
        min_breadth = wpl._SPHERE0_MIN_BREADTH
        capped = []          # (seed, breadths) for every geography-capped seed
        worst = None         # (seed, max_breadth): the narrowest max seen, for the record
        for seed in range(_SEED0, _SEED0 + _GUARD_SEEDS):
            world, breadths = self._breadth_probe(seed)
            mx = max(breadths)
            if worst is None or mx < worst[1]:
                worst = (seed, mx)
            if mx < min_breadth:
                capped.append((seed, breadths))
            if seed == _SEED0:
                # Instrument-honesty guard (Lessons Learned 11/13): the breadth
                # census is only meaningful while two-stage gating is actually
                # active on the default config -- that is what holds locations back
                # into stage 2 and can narrow sphere 0. If a future default turns
                # two-stage off, sphere 0 is never held back and this guard would
                # pass vacuously; fail loudly here instead.
                self.assertTrue(
                    getattr(world, "_ctr_two_stage_active", False),
                    "two-stage gating is inactive on the default config; the "
                    "sphere-0 breadth guard would be vacuous")
        self.assertEqual(
            capped, [],
            f"{len(capped)} of {_GUARD_SEEDS} default-config seeds geography-capped "
            f"sphere-0 breadth below _SPHERE0_MIN_BREADTH={min_breadth} over the "
            f"{wpl._SPHERE0_REPAIR_TRIES}-roll shipped budget. #75 requires this "
            f"class to stay empty on the shipped defaults; a default flip likely "
            f"re-narrowed sphere 0. Narrowest max breadth over the batch was "
            f"{worst[1]} (seed {worst[0]}). First capped seeds: {capped[:3]}")


if __name__ == "__main__":
    unittest.main()
