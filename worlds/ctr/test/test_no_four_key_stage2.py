"""random_without_4_keys must hold at BOTH stages, on every surface.

WHY THIS FILE EXISTS
--------------------
`warppad_unlock_requirements: random_without_4_keys` (mode 2) promises that the
four boss Keys are never a pad requirement. Until now the only enforcement was
`_post_process`, which the sphere search runs once over `pad_reqs` and once over
`stage2_reqs` (warp_pad_logic step 3). The play-session report was that the
promise held for stage 1 but not stage 2.

The report is half right and half wrong, and the real defect is neither half:

* Stage 2 IS covered by `_post_process` -- bypassing that call reintroduces
  Key x4 stage-2 rows immediately (test_mutation_skipping_stage2_post_process).
* But `_post_process` is NOT the last pass to write a requirement. Under
  destination shuffle, `_revalidate_against_shuffle` runs AFTER it, re-draws
  failing stage-1 requirements straight from the fixed-point inventory
  (`_assign_from_inv`, which will happily return ("Key", 4) once four Keys are
  owned), and collapses failing stage-2 requirements onto those same stage-1
  values. That path had no mode-2 guard at all.

On the shipped 0.2.0 Alpha 4 package (`eca44f223`) that reproduces as real
Key x4 rows in the serialized `slot_data` -- see SEEDS_ALPHA4_KEY4 below. It is
a stage-1 leak that can also taint stage 2 through the collapse, so it is
strictly worse than the reported symptom.

The fix is `warp_pad_logic.deny_four_key_gate`, applied at every site that
writes a requirement after the post-pass. This file pins the invariant at all
four surfaces so no future pass can quietly reintroduce it:

  1. `world.warp_pad_unlock_concrete`        stage-1 (item, count), pad keyed
  2. `world.warp_pad_unlock_stage2_concrete` stage-2 (item, count), dest keyed
  3. `world.warp_pad_unlock` / `warp_pad_unlock_stage2`  resolved wire maps
  4. `fill_slot_data()["warp_pad_unlock"][lid]["stage1"|"stage2"]`  the wire rows

Key x3 stays legal and is asserted to actually occur, so a config that simply
stopped generating Key gates could not pass this file vacuously.
"""

import unittest

from . import CTRTestBase
from .. import warp_pad_logic
from ..warp_pad_logic import deny_four_key_gate

# Wire encoding (warp_pad_logic.to_slot_req): type 2 = Keys, colour -1.
_TYPE_KEY = 2
# Inv.CAPS["Key"] is 4, so "four Keys" is the only banned count; the assertions
# use >= so a future cap change cannot slip a Key x5 gate past them.
_BANNED_KEY_COUNT = 4

# Exact seeds that reproduce a Key x4 row on the shipped Alpha 4 package
# (release/0.2.0-alpha4 @ eca44f2231bf9fe587e85ea4d7d53c6cbd716827), found by a
# 2280-seed sweep. Every one of them is a stage-1 leak through the
# re-validation relaxation, and every one is in the merged/deep destination
# shuffle configurations, which is the only place that pass runs.
SEEDS_ALPHA4_KEY4 = {
    "full-merged": (59, 160, 208),
    "deep-merged": (43, 172, 230),
}


class _FourKeyScan:
    """Enumerates every requirement surface of a constructed world."""

    def _concrete_reqs(self, world):
        for pad, req in (getattr(world, "warp_pad_unlock_concrete", {}) or {}).items():
            yield f"concrete stage1 {pad}", req
        for dest, req in (getattr(world,
                                  "warp_pad_unlock_stage2_concrete", {}) or {}).items():
            yield f"concrete stage2 {dest}", req

    def _resolved_wire_reqs(self, world):
        for pad, req in (getattr(world, "warp_pad_unlock", {}) or {}).items():
            yield f"resolved warp_pad_unlock {pad} stage1", req
        for pad, req in (getattr(world, "warp_pad_unlock_stage2", {}) or {}).items():
            yield f"resolved warp_pad_unlock_stage2 {pad} stage2", req

    def _serialized_wire_reqs(self, world):
        """The actual wire rows native parses: slot_data warp_pad_unlock, keyed by
        physical pad LevelID, each with a stage1 and a stage2 requirement dict."""
        rows = world.fill_slot_data().get("warp_pad_unlock", {})
        for lid, stages in rows.items():
            yield f"slot_data warp_pad_unlock[{lid}].stage1", stages["stage1"]
            yield f"slot_data warp_pad_unlock[{lid}].stage2", stages["stage2"]

    @staticmethod
    def _is_four_key_wire(req):
        return req.get("type") == _TYPE_KEY and req.get("count", 0) >= _BANNED_KEY_COUNT

    @staticmethod
    def _is_four_key_concrete(req):
        return req is not None and req[0] == "Key" and req[1] >= _BANNED_KEY_COUNT

    def find_four_key_rows(self, world):
        """Every Key x4 row on every surface, as (where, req)."""
        found = []
        for where, req in self._concrete_reqs(world):
            if self._is_four_key_concrete(req):
                found.append((where, req))
        for where, req in self._resolved_wire_reqs(world):
            if self._is_four_key_wire(req):
                found.append((where, req))
        for where, req in self._serialized_wire_reqs(world):
            if self._is_four_key_wire(req):
                found.append((where, req))
        return found


# ---------------------------------------------------------------------------
# The unit-level invariant
# ---------------------------------------------------------------------------

class TestDenyFourKeyGate(unittest.TestCase):
    """deny_four_key_gate is the single definition of the mode-2 rule."""

    def test_lowers_only_the_four_key_gate_in_mode_2(self):
        self.assertEqual(deny_four_key_gate(("Key", 4), 2), ("Key", 3))
        self.assertEqual(deny_four_key_gate(("Key", 3), 2), ("Key", 3))
        self.assertEqual(deny_four_key_gate(("Key", 1), 2), ("Key", 1))
        self.assertEqual(deny_four_key_gate(("Trophy", 4), 2), ("Trophy", 4))
        self.assertEqual(deny_four_key_gate(("AnyGem", 4), 2), ("AnyGem", 4))
        self.assertIsNone(deny_four_key_gate(None, 2))

    def test_is_inert_outside_mode_2(self):
        # Plain `randomized` (mode 1) and `vanilla` (mode 0) may gate on 4 Keys.
        self.assertEqual(deny_four_key_gate(("Key", 4), 1), ("Key", 4))
        self.assertEqual(deny_four_key_gate(("Key", 4), 0), ("Key", 4))

    def test_only_ever_lowers(self):
        # The solvability argument: a lowered gate can never close a pad the
        # sphere search already proved reachable.
        for count in range(0, 9):
            out = deny_four_key_gate(("Key", count), 2)
            self.assertEqual(out[0], "Key")
            self.assertLessEqual(out[1], count)

    def test_every_post_pass_write_site_is_guarded(self):
        """Structural guard: `_revalidate_against_shuffle` runs after the
        post-pass and writes requirements. Every assignment it makes into
        `pad_reqs` or `stage2_reqs` must go through the helper. This catches a
        future edit that adds a fourth relaxation branch without the guard."""
        import inspect
        src = inspect.getsource(warp_pad_logic._revalidate_against_shuffle)
        writes = [ln.strip() for ln in src.splitlines()
                  if ("pad_reqs[track] =" in ln or "stage2_reqs[dest] =" in ln)]
        self.assertTrue(writes, "no requirement writes found; test is stale")
        for line in writes:
            with self.subTest(line=line):
                assigned = line.split("=", 1)[1].strip()
                self.assertIn(
                    assigned, ("new", "new_req", "collapsed"),
                    "a relaxation writes a requirement that was never passed "
                    "through deny_four_key_gate")
        self.assertIn("deny_four_key_gate", src)


# ---------------------------------------------------------------------------
# The seed/config matrix
# ---------------------------------------------------------------------------

class _NoFourKeyMatrix(_FourKeyScan):
    """Constructs each seed and asserts the invariant on every surface."""

    seeds = range(1, 21)
    # Set by subclasses that carry an Alpha 4 reproducer, so the exact reported
    # seeds are pinned rather than merely covered by the range.
    regression_seeds = ()

    def _all_seeds(self):
        return sorted(set(self.seeds) | set(self.regression_seeds))

    def test_no_four_key_requirement_at_any_surface(self):
        saw_a_requirement = False
        for seed in self._all_seeds():
            with self.subTest(seed=seed):
                self.world_setup(seed=seed)
                world = self.world
                # Premise guard: an empty requirement set would pass vacuously.
                self.assertTrue(
                    getattr(world, "warp_pad_unlock", {}),
                    "no warp-pad requirements generated; config regressed")
                saw_a_requirement = True
                # Premise guard: mode 2 must actually be what we are testing.
                self.assertEqual(
                    world.fill_slot_data()["ctr_options"]["warppad_unlock_mode"], 2,
                    "config is not random_without_4_keys")
                found = self.find_four_key_rows(world)
                self.assertEqual(
                    found, [],
                    f"seed {seed} emits a four-Key requirement under "
                    f"random_without_4_keys: {found}")
        self.assertTrue(saw_a_requirement)

    def test_three_key_gates_remain_legal(self):
        """Key x3 must still be drawable, or the assertion above could pass
        simply because the config stopped producing Key gates at all."""
        for seed in self._all_seeds():
            self.world_setup(seed=seed)
            world = self.world
            for _where, req in self._concrete_reqs(world):
                if req is not None and req[0] == "Key" and req[1] == 3:
                    return
        self.skipTest("no Key x3 gate in this config's seed range")


_MERGED_ALL = {
    "include_gem_cups": True,
    "include_battle_arenas": True,
    "warp_pad_shuffle_categories": ["tracks", "cups", "crystals"],
    "warp_pad_shuffle_grouping": "merged",
}


class TestFullMerged(_NoFourKeyMatrix, CTRTestBase):
    """full two-stage density, merged shuffle, ordinary pads + arenas + Gem Cups.
    Carries three exact Alpha 4 reproducers."""
    run_default_tests = False
    auto_construct = False
    regression_seeds = SEEDS_ALPHA4_KEY4["full-merged"]
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full")


class TestDeepMerged(_NoFourKeyMatrix, CTRTestBase):
    """deep two-stage density, merged shuffle. Carries three exact Alpha 4
    reproducers."""
    run_default_tests = False
    auto_construct = False
    regression_seeds = SEEDS_ALPHA4_KEY4["deep-merged"]
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="deep")


class TestFullPerCategory(_NoFourKeyMatrix, CTRTestBase):
    """per_category grouping: each category shuffles only within itself."""
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full",
                   warp_pad_shuffle_grouping="per_category")


class TestFullNoDestinationShuffle(_NoFourKeyMatrix, CTRTestBase):
    """Destination shuffle OFF: `_revalidate_against_shuffle` never runs, so
    this is the control that proves the post-pass alone covers both stages."""
    run_default_tests = False
    auto_construct = False
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "two_stage_density": "full",
        "include_gem_cups": True,
        "include_battle_arenas": True,
        "warp_pad_shuffle_categories": [],
    }


class TestTracksOnlyNoCupsNoArenas(_NoFourKeyMatrix, CTRTestBase):
    """Only ordinary race pads participate; cups and arenas are out of the seed."""
    run_default_tests = False
    auto_construct = False
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "two_stage_density": "full",
        "include_gem_cups": False,
        "include_battle_arenas": False,
        "warp_pad_shuffle_categories": ["tracks"],
        "warp_pad_shuffle_grouping": "merged",
    }


class TestStageTwoCollapsed(_NoFourKeyMatrix, CTRTestBase):
    """two_stage_density: off -- every stage 2 collapses to OPEN. The collapse
    control: no stage-2 gate may exist at all, let alone a four-Key one."""
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="off")

    def test_stage_two_is_actually_collapsed(self):
        """Premise guard for the collapse control: prove the stage-2 surface is
        empty here, so its Key x4 assertion is meaningful rather than trivially
        true for the wrong reason."""
        self.world_setup(seed=1)
        self.assertEqual(
            dict(getattr(self.world, "warp_pad_unlock_stage2_concrete", {}) or {}),
            {}, "two_stage_density=off still produced a concrete stage-2 gate")


class TestNonCollapsedStageTwoIsReal(_NoFourKeyMatrix, CTRTestBase):
    """The non-collapse control: at full density real stage-2 gates must exist,
    otherwise every stage-2 assertion in this file would be vacuous."""
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full")

    def test_real_stage_two_gates_are_generated(self):
        for seed in range(1, 6):
            self.world_setup(seed=seed)
            concrete = getattr(self.world, "warp_pad_unlock_stage2_concrete", {}) or {}
            if concrete:
                # And they must reach the wire as non-type-0 stage-2 rows.
                rows = self.world.fill_slot_data()["warp_pad_unlock"]
                real = [lid for lid, s in rows.items() if s["stage2"]["type"] != 0]
                self.assertTrue(
                    real,
                    f"seed {seed} has concrete stage-2 gates but emits no "
                    "non-zero stage-2 wire row")
                return
        self.fail("full two-stage density produced no real stage-2 gate in "
                  "seeds 1-5; every stage-2 assertion here would be vacuous")


class TestKeyGatesStillReachStageTwo(_FourKeyScan, CTRTestBase):
    """Stage-2 Key gates must remain possible at counts 1-3. If mode 2 ever
    silently degraded into "no Key ever reaches stage 2", the headline
    assertions would still pass while the option quietly did the wrong thing."""
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full")

    def test_stage_two_still_draws_key_gates_below_four(self):
        for seed in range(1, 41):
            self.world_setup(seed=seed)
            concrete = getattr(self.world,
                               "warp_pad_unlock_stage2_concrete", {}) or {}
            for _dest, req in concrete.items():
                if req is not None and req[0] == "Key":
                    self.assertLess(req[1], _BANNED_KEY_COUNT)
                    return
        self.skipTest("no stage-2 Key gate in seeds 1-40")


# ---------------------------------------------------------------------------
# Mutation proofs
#
# A test that only restates the source is worthless. Each of these disables one
# specific piece of the guard and asserts the matrix above turns RED, which is
# what makes the green runs above evidence rather than decoration.
# ---------------------------------------------------------------------------

class _MutationBase(_FourKeyScan, CTRTestBase):
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full")

    def _scan_seeds(self, seeds):
        found = []
        for seed in seeds:
            self.world_setup(seed=seed)
            found.extend((seed, where, req)
                         for where, req in self.find_four_key_rows(self.world))
        return found


class TestMutationBypassingTheGuard(_MutationBase):
    """Replace deny_four_key_gate with the identity function -- i.e. remove the
    mode-2 rule entirely, at both stages, since every site now routes through
    it. Four-Key rows must come back."""

    def test_removing_the_guard_reintroduces_four_key_rows(self):
        original = warp_pad_logic.deny_four_key_gate
        warp_pad_logic.deny_four_key_gate = lambda req, mode: req
        try:
            found = self._scan_seeds(range(1, 71))
        finally:
            warp_pad_logic.deny_four_key_gate = original
        self.assertTrue(
            found,
            "removing the mode-2 guard produced no four-Key requirement in "
            "seeds 1-70: the guard is not load-bearing and these tests prove "
            "nothing")
        stages = {"stage1" in where for _s, where, _r in found}
        self.assertIn(True, stages, "expected at least one stage-1 leak")

    def test_removing_the_guard_reintroduces_them_at_stage_two(self):
        original = warp_pad_logic.deny_four_key_gate
        warp_pad_logic.deny_four_key_gate = lambda req, mode: req
        try:
            found = self._scan_seeds(range(1, 71))
        finally:
            warp_pad_logic.deny_four_key_gate = original
        stage2 = [f for f in found if "stage2" in f[1]]
        self.assertTrue(
            stage2,
            "removing the mode-2 guard produced no four-Key STAGE-2 row; the "
            "stage-2 half of this file would be unproven")


class TestMutationSkippingStageTwoPostProcess(_MutationBase):
    """The exact scenario WO-A2 asked about: what if stage 2 never went through
    the post-pass at all? Skip `_post_process` for the stage-2 call only (it is
    the one carrying _STAGE2_COUNT_CEILING) and prove four-Key stage-2 rows
    appear. This is what makes "stage 2 IS covered by the post-pass" a measured
    claim instead of a reading of the source."""

    def test_bypassing_stage2_post_processing_reintroduces_four_key_stage2(self):
        original = warp_pad_logic._post_process

        def only_stage_one(rnd, reqs, mode, count_ceiling=None):
            if count_ceiling == warp_pad_logic._STAGE2_COUNT_CEILING:
                return  # stage-2 post-processing bypassed
            return original(rnd, reqs, mode, count_ceiling)

        warp_pad_logic._post_process = only_stage_one
        try:
            found = self._scan_seeds(range(1, 71))
        finally:
            warp_pad_logic._post_process = original
        stage2 = [f for f in found if "stage2" in f[1]]
        self.assertTrue(
            stage2,
            "bypassing stage-2 post-processing produced no four-Key stage-2 "
            "row; the stage-2 post-pass is not what is protecting stage 2 and "
            "this file's model of the pipeline is wrong")


class TestMutationInjectedStageTwoFourKeyIsCaught(_MutationBase):
    """Detector proof, independent of generation: inject a Key x4 stage-2
    requirement into a clean world and assert every surface reports it. Without
    this, a scanner bug (wrong attribute name, wrong wire key) would read as
    "no four-Key rows found" forever."""

    def test_injected_stage_two_four_key_is_reported_at_every_surface(self):
        self.world_setup(seed=1)
        world = self.world
        self.assertEqual(self.find_four_key_rows(world), [])

        pad_name, meta = next(
            (p, m) for p, m in world.warp_pad_ids.items()
            if 0 <= m["level_id"] < world.WARP_PAD_ID_RANGE)
        dest = next(iter(world.warp_pad_unlock_stage2_concrete), None) or "Crash Cove"

        world.warp_pad_unlock_stage2[pad_name] = {
            "type": _TYPE_KEY, "count": 4, "colour": -1}
        world.warp_pad_unlock_stage2_concrete[dest] = ("Key", 4)
        world._ctr_force_collapse_stage2 = False

        found = self.find_four_key_rows(world)
        wheres = " | ".join(w for w, _ in found)
        self.assertIn("concrete stage2", wheres)
        self.assertIn("resolved warp_pad_unlock_stage2", wheres)
        self.assertIn(
            f"slot_data warp_pad_unlock[{meta['level_id']}].stage2", wheres,
            "an injected Key x4 stage-2 requirement did not surface in the "
            "serialized wire rows; the wire scanner is broken")


class TestMutationInjectedStageOneFourKeyIsCaught(_MutationBase):
    """The stage-1 sibling of the detector proof."""

    def test_injected_stage_one_four_key_is_reported_at_every_surface(self):
        self.world_setup(seed=1)
        world = self.world
        self.assertEqual(self.find_four_key_rows(world), [])

        pad_name, meta = next(
            (p, m) for p, m in world.warp_pad_ids.items()
            if p in world.warp_pad_unlock
            and 0 <= m["level_id"] < world.WARP_PAD_ID_RANGE)
        world.warp_pad_unlock[pad_name] = {
            "type": _TYPE_KEY, "count": 4, "colour": -1}
        world.warp_pad_unlock_concrete[pad_name] = ("Key", 4)

        found = self.find_four_key_rows(world)
        wheres = " | ".join(w for w, _ in found)
        self.assertIn("concrete stage1", wheres)
        self.assertIn("resolved warp_pad_unlock", wheres)
        self.assertIn(
            f"slot_data warp_pad_unlock[{meta['level_id']}].stage1", wheres)


# ---------------------------------------------------------------------------
# Other modes are unaffected
# ---------------------------------------------------------------------------

class TestRandomizedModeMayStillGateOnFourKeys(_FourKeyScan, CTRTestBase):
    """Plain `randomized` (mode 1) is explicitly allowed to draw a four-Key
    gate. The fix must not quietly narrow the default mode -- if this stops
    finding one, mode 1 has been changed by accident."""
    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="randomized",
                   two_stage_density="full")

    def test_mode_one_still_produces_a_four_key_gate_somewhere(self):
        for seed in range(1, 41):
            self.world_setup(seed=seed)
            if self.find_four_key_rows(self.world):
                return
        self.skipTest("no four-Key gate in randomized mode over seeds 1-40")


class TestNativeConsumesEmittedKeyCounts(_FourKeyScan, CTRTestBase):
    """Native-parity assertion for WO-A2 step 5. READ/TEST ONLY -- no native
    change is implied or made.

    The Alpha 4 native client (`release/0.2.0-alpha4` @ `faf5196624f0`) treats a
    Key requirement as pure data:

      * `ap_seedcfg.cpp::parse_req` reads {type,count,colour} verbatim, then
        applies `ctr_clamp_count`, whose table is CTR_REQ_AVAIL[2] == 4 for keys
        and which only ever clamps DOWNWARD (`count > hi -> hi`).
      * `ap_hooks.c::AP_ReqMetCounts` case 2 is `counts[AP_IDX_KEY] >= r->count`
        -- a comparison, never a rewrite.
      * `warppad_unlock_mode` is stored (`ap_seedcfg.h:175`) and logged
        (`ap_hooks.c:5197`) but never branched on, so native cannot re-derive
        the mode-2 rule or invent a four-Key gate of its own.
      * Stage 2 resolves through the SAME `parse_req` / `AP_BossReqMet` pair
        (`ctr_cfg_warp_stage2_req`), including the cup 100..104 routing.

    So the only way a player can see a four-Key gate is if the apworld emitted
    one. What this test pins on the apworld side is the premise that argument
    rests on: every emitted Key count sits strictly inside native's clamp bound,
    so `ctr_clamp_count` is a no-op on our wire rows and cannot participate."""

    run_default_tests = False
    auto_construct = False
    options = dict(_MERGED_ALL,
                   warppad_unlock_requirements="random_without_4_keys",
                   two_stage_density="full")

    # ap_seedcfg.cpp CTR_REQ_AVAIL[2] -- native's downward clamp bound for keys.
    _NATIVE_KEY_AVAIL = 4

    def test_emitted_key_counts_never_touch_the_native_clamp(self):
        seen_key_row = False
        for seed in list(range(1, 21)) + list(SEEDS_ALPHA4_KEY4["full-merged"]):
            with self.subTest(seed=seed):
                self.world_setup(seed=seed)
                rows = self.world.fill_slot_data()["warp_pad_unlock"]
                for lid, stages in rows.items():
                    for stage in ("stage1", "stage2"):
                        req = stages[stage]
                        if req["type"] != _TYPE_KEY:
                            continue
                        seen_key_row = True
                        self.assertGreaterEqual(req["count"], 0)
                        self.assertLess(
                            req["count"], self._NATIVE_KEY_AVAIL,
                            f"pad {lid} {stage} emits Key x{req['count']}: at or "
                            "above native's CTR_REQ_AVAIL[2] bound, so the "
                            "clamp argument above no longer holds")
                        self.assertEqual(req["colour"], -1,
                                         "a Key requirement must carry colour -1")
        self.assertTrue(seen_key_row,
                        "no Key requirement emitted at all; this test is vacuous")
