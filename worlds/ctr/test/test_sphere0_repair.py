"""Regression guard for the sphere-0 breadth repair (warp_pad_logic).

CTR generation used to fail with AP's FillError on ~0.3% of multiworld seeds.
The DAG is always solvable by construction; what failed was fill_restrictive
running out of reachable slots because sphere 0 was too NARROW. Measured over
10k default-config seeds, every failure sat at a sphere-0 breadth of 2 or 3;
breadth >= 4 produced zero failures over ~19.5k samples. run_sphere_search
therefore re-rolls the search a bounded number of times, keeping the first roll
that clears _SPHERE0_MIN_BREADTH, and falls back to collapsing stage 2 on the
geography-capped seeds where no free-pad subset can widen sphere 0.

See the SPHERE-0 BREADTH REPAIR comment block in warp_pad_logic.py. This is
deliberately NOT a complete fix (residual ~3 failures per 10k is accepted and
documented); these tests lock in the mechanism, not a zero-failure claim.

Guarded here:
- the wrapper stops at the first roll that clears the threshold;
- it terminates on a capped seed instead of spinning, and takes the documented
  stage-2-collapse escape hatch;
- when the caller already asked for a collapsed stage 2 there is no escape
  hatch left, so it returns the WIDEST roll it saw rather than the last;
- on a real generated world the wrapper's postcondition holds: either sphere-0
  breadth clears the threshold, or every stage-2 gate is open;
- the result is deterministic on the seed;
- vanilla warp-pad mode never runs a sphere search at all, so none of this can
  touch it.
"""

import types
import unittest
from unittest import mock

from .. import Regions, warp_pad_logic as wpl
from . import CTRTestBase


def _fake_out(tag):
    """A minimal run_sphere_search-shaped result, tagged so tests can identify
    which roll came back."""
    return {t: {1: None, 2: tag} for t in wpl.HUB_STATIC}


class TestSphere0RepairControlFlow(unittest.TestCase):
    """Wrapper control flow, with the roll + breadth measurement stubbed so the
    behaviour under test does not depend on any particular seed's geography."""

    def _run(self, breadths, collapse_stage2=False):
        """Drive run_sphere_search against a scripted breadth sequence.
        Returns (result, calls) where calls records every _run_sphere_search_once
        invocation as (tag, collapse_stage2_flag)."""
        calls = []
        seq = list(breadths)

        def fake_once(world, mode, reward_track_for=None,
                      collapse_stage2=False, include_gem_cups=False):
            tag = len(calls)
            calls.append((tag, collapse_stage2))
            return _fake_out(tag)

        def fake_breadth(world, out, reward_track_for, include_gem_cups):
            return seq.pop(0) if seq else seq_default

        seq_default = 0
        world = types.SimpleNamespace(_ctr_two_stage_active=True)
        with mock.patch.object(wpl, "_run_sphere_search_once", fake_once), \
                mock.patch.object(wpl, "_sphere0_breadth", fake_breadth):
            out = wpl.run_sphere_search(world, 1, None, collapse_stage2, False)
        return out, calls, world

    def test_stops_at_first_roll_clearing_threshold(self):
        """A narrow roll is re-rolled; the first roll at/above the threshold is
        returned immediately and no further rolls happen."""
        wide = wpl._SPHERE0_MIN_BREADTH
        out, calls, world = self._run([2, 3, wide, 99])
        self.assertEqual(len(calls), 3, "wrapper kept rolling past the threshold")
        self.assertEqual(next(iter(out.values()))[2], 2,
                         "wrapper did not return the roll that cleared the threshold")
        self.assertFalse(any(c[1] for c in calls),
                         "wrapper collapsed stage 2 even though a roll succeeded")
        self.assertTrue(world._ctr_two_stage_active,
                        "wrapper disabled two-stage on a seed that did not need it")

    def test_accepts_first_roll_when_already_wide(self):
        """The common case: one roll, no extra build_graph churn beyond the
        single breadth measurement."""
        _out, calls, _world = self._run([wpl._SPHERE0_MIN_BREADTH + 5])
        self.assertEqual(len(calls), 1)

    def test_capped_seed_terminates_and_falls_back(self):
        """Geography-capped seed: no roll ever clears. The wrapper must stop
        after its bounded budget (not spin) and take the stage-2-collapse
        escape hatch, flagging two-stage off so __init__ skips its probe."""
        narrow = wpl._SPHERE0_MIN_BREADTH - 1
        tries = wpl._SPHERE0_REPAIR_TRIES
        out, calls, world = self._run([narrow] * (tries + 5))
        self.assertEqual(
            len(calls), tries + 1,
            f"expected {tries} bounded rolls plus one collapsed fallback roll")
        self.assertFalse(any(c[1] for c in calls[:tries]),
                         "a budgeted roll asked for a collapsed stage 2")
        self.assertTrue(calls[-1][1],
                        "fallback roll did not request collapse_stage2=True")
        self.assertEqual(next(iter(out.values()))[2], tries,
                         "wrapper did not return the fallback roll")
        self.assertFalse(world._ctr_two_stage_active,
                         "fallback did not turn two-stage off for this seed")

    def test_capped_seed_already_collapsed_returns_widest_roll(self):
        """When the caller already asked for a collapsed stage 2 (two_stage_density
        = off) there is no escape hatch left, so the wrapper returns the WIDEST
        roll it saw, not the last one."""
        tries = wpl._SPHERE0_REPAIR_TRIES
        breadths = [1] * tries
        breadths[3] = wpl._SPHERE0_MIN_BREADTH - 1  # widest, still under threshold
        out, calls, _world = self._run(breadths, collapse_stage2=True)
        self.assertEqual(len(calls), tries, "wrapper exceeded its roll budget")
        self.assertTrue(all(c[1] for c in calls),
                        "wrapper dropped the caller's collapse_stage2 request")
        self.assertEqual(next(iter(out.values()))[2], 3,
                         "wrapper returned the last roll instead of the widest")

    def test_breadth_helper_consumes_no_rng(self):
        """The measurement must not perturb generation determinism."""
        import random as _random
        rnd = _random.Random(12345)
        world = types.SimpleNamespace(random=rnd, start_region=None)
        before = rnd.getstate()
        with mock.patch.object(wpl, "build_graph",
                               lambda *a, **k: ({}, {}, None)):
            wpl._sphere0_breadth(world, {}, lambda t: t, False)
        self.assertEqual(rnd.getstate(), before,
                         "_sphere0_breadth consumed world.random")


class Sphere0PostconditionMixin:
    """Runs the real wrapper against a real generated world."""

    def _args(self):
        world = self.world
        return (world, getattr(world, "_ctr_unlock_mode", 1),
                Regions._build_reward_track_resolver(world),
                False, bool(world.options.include_gem_cups.value))

    def test_postcondition_breadth_or_collapsed_stage2(self):
        """The wrapper's contract: it either reaches _SPHERE0_MIN_BREADTH, or it
        gave up and opened every stage-2 gate. It never returns a narrow seed
        that still carries stage-2 hold-back."""
        world, mode, rtf, collapse, gems = self._args()
        for _ in range(4):  # several fresh rolls off the live RNG stream
            out = wpl.run_sphere_search(world, mode, rtf, collapse, gems)
            breadth = wpl._sphere0_breadth(world, out, rtf, gems)
            all_open = all(v[2] is None for v in out.values())
            self.assertTrue(
                breadth >= wpl._SPHERE0_MIN_BREADTH or all_open,
                f"sphere-0 breadth {breadth} is under "
                f"{wpl._SPHERE0_MIN_BREADTH} and stage-2 gates are still closed")

    def test_result_shape_unchanged(self):
        """The wrapper is transparent: same keys and same value shape as one
        raw roll of the underlying search."""
        world, mode, rtf, collapse, gems = self._args()
        out = wpl.run_sphere_search(world, mode, rtf, collapse, gems)
        self.assertEqual(set(out), set(wpl.HUB_STATIC))
        for track, stages in out.items():
            self.assertEqual(set(stages), {1, 2}, f"bad stage keys on {track}")
            for stage in (1, 2):
                req = stages[stage]
                self.assertTrue(req is None or (isinstance(req, tuple)
                                                and len(req) == 2),
                                f"{track} stage {stage} is not None/(item,count)")

    def test_deterministic_on_seed(self):
        """Two identically seeded worlds must produce identical requirements;
        the repair loop must not introduce seed drift."""
        seeds = []
        for _ in range(2):
            self.world_setup(seed=848484)
            world, mode, rtf, collapse, gems = self._args()
            seeds.append(wpl.run_sphere_search(world, mode, rtf, collapse, gems))
        self.assertEqual(seeds[0], seeds[1])


class TestSphere0PostconditionDefault(Sphere0PostconditionMixin, CTRTestBase):
    """The shipped default config."""
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "two_stage_density": "standard",
    }


class TestSphere0PostconditionDeepShuffled(Sphere0PostconditionMixin, CTRTestBase):
    """Dense stage-2 gating plus destination shuffle: the tightest fill config,
    and the one the FillError tail was measured on."""
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
        "warp_pad_shuffle_grouping": "merged",
        "include_gem_cups": True,
        "include_battle_arenas": True,
        "two_stage_density": "deep",
    }


class TestVanillaModeSkipsSphereSearch(CTRTestBase):
    """Vanilla warp-pad mode has no sphere search, so the repair must be
    completely inert there -- including its extra build_graph calls."""
    options = {"warppad_unlock_requirements": "vanilla"}

    def test_generation_never_calls_the_sphere_search(self):
        def boom(*a, **k):
            raise AssertionError(
                "vanilla warp-pad mode called run_sphere_search; the sphere-0 "
                "repair must not run on a config that has no randomized pads")

        with mock.patch.object(Regions, "run_sphere_search", boom):
            self.world_setup(seed=13579)

    def test_all_pads_stay_free_and_ungated(self):
        world = self.world
        self.assertEqual(getattr(world, "_ctr_unlock_mode", 0), 0)
        self.assertFalse(getattr(world, "_ctr_two_stage_active", False),
                         "vanilla mode reported an active two-stage gate")
        self.assertFalse(getattr(world, "warp_pad_unlock_concrete", {}),
                         "vanilla mode produced sphere-search requirements")
        for pad, req in (getattr(world, "warp_pad_unlock", {}) or {}).items():
            self.assertEqual(req["type"], 0, f"{pad} is gated in vanilla mode")
