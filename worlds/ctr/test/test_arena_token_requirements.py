"""Regression guard for issue #118: include_battle_arenas OFF still let
warp-pad requirements demand Purple CTR Tokens.

#50 fixed the FILL side of the option (arenas off -> the four Crystal Bonus
Round checks are vanilla-pinned with their Purple CTR Tokens, so no foreign
progression can hide there). The REQUIREMENT side was never covered: the
sphere-search's `allowed` filter only excluded relic tiers by slider, so
Purple CTR Token stayed a drawable stage-1/stage-2 requirement, and the
AnyCtrToken collapse sized its counts over all five colours (the synthetic
inventory keeps collecting Purples from the vanilla-gated crystal pads).
Either way a player who opted out of battle arenas was routinely routed
through them: every Purple is locked behind arena play by #50's own pinning.

The fix (mirroring the relic-slider mechanism): arenas off -> Purple CTR
Token leaves the `allowed` requirement set AND the AnyCtrToken collapse
total is summed over the allowed colours only. Deliberate asymmetry with
excluded relic tiers (which remain findable progression): the option's
intent is that NO arena play is ever required, so Purple leaves the
aggregate count too. slot_data schema is unchanged -- only which
requirements generation draws changes.

These tests lock in:
- arenas OFF: no stage-1/stage-2 requirement names Purple CTR Token
  (wire type 3 colour 4), and no any-token requirement (wire type 6)
  exceeds 16 (4 non-purple colours x cap 4);
- arenas ON: the collapse total still spans all five colours (unchanged
  behaviour, byte-identical RNG consumption);
- the collapse-total scoping itself, deterministically, via a scripted RNG.
"""

import math

from . import CTRTestBase
from .. import warp_pad_logic
from ..warp_pad_logic import Inv, TOKEN_ITEMS, _choose_requirement

# Wire encoding (warp_pad_logic.to_slot_req): type 3 = concrete CTR token,
# colour index 4 = Purple; type 6 = AnyCtrToken aggregate.
_TYPE_TOKEN = 3
_COLOUR_PURPLE = 4
_TYPE_ANY_TOKEN = 6
# 4 allowed colours x per-colour cap 4 (Inv.CAPS): the most tokens obtainable
# without arena play.
_MAX_TOKENS_WITHOUT_ARENAS = 16


class _ScriptedRandom:
    """Forces _choose_requirement down a fixed path: choices() picks the first
    token candidate, randrange() always fires the collapse roll."""

    def choices(self, values, weights=None, k=1):
        assert k == 1
        token_cands = [v for v in values if v[0] in TOKEN_ITEMS]
        assert token_cands, "no token candidate offered to choices()"
        return [token_cands[0]]

    def randrange(self, n):
        return 0  # always < every collapse chance


class TestAnyTokenCollapseScoping(CTRTestBase):
    """Unit-level guard on the collapse total (no seed randomness involved)."""

    auto_construct = False

    @staticmethod
    def _full_inventory():
        inv = Inv()
        for colour in TOKEN_ITEMS:
            for _ in range(4):
                inv.add(colour)
        return inv

    @staticmethod
    def _expected_collapse_count(total):
        # Derived from the live module globals so the test holds under any
        # requirement_variety preset a sibling test left loaded.
        cnt = max(1, math.ceil(total * warp_pad_logic._TOKEN_COLLAPSE_SCALE))
        if warp_pad_logic._TOKEN_COLLAPSE_CAP is not None:
            cnt = min(cnt, warp_pad_logic._TOKEN_COLLAPSE_CAP)
        return cnt

    def test_collapse_total_excludes_disallowed_purple(self):
        # The #118 shape: 4 of each colour owned (20 total, Purples included
        # because the vanilla-gated crystal pads still feed the synthetic
        # inventory), but Purple is NOT in `allowed`.
        inv = self._full_inventory()
        allowed = set(warp_pad_logic.REQ_WEIGHTS) - {"Purple CTR Token"}
        item, cnt = _choose_requirement(_ScriptedRandom(), inv, allowed)
        self.assertEqual(item, "AnyCtrToken")
        self.assertEqual(
            cnt, self._expected_collapse_count(16),
            "AnyCtrToken collapse total must sum the 4 allowed colours (16), "
            "not all five (20): the 4 Purples are only reachable by arena play")

    def test_collapse_total_spans_all_colours_when_all_allowed(self):
        # Arenas ON (or no filter at all): unchanged pre-#118 behaviour.
        inv = self._full_inventory()
        item, cnt = _choose_requirement(_ScriptedRandom(), inv, None)
        self.assertEqual(item, "AnyCtrToken")
        self.assertEqual(cnt, self._expected_collapse_count(20))
        item, cnt = _choose_requirement(
            _ScriptedRandom(), inv, set(warp_pad_logic.REQ_WEIGHTS))
        self.assertEqual(item, "AnyCtrToken")
        self.assertEqual(cnt, self._expected_collapse_count(20))

    def test_purple_not_choosable_when_disallowed(self):
        # Direct-pick guard: with ONLY Purples owned and Purple disallowed,
        # nothing is eligible (the pad goes free) instead of a Purple gate.
        inv = Inv()
        for _ in range(4):
            inv.add("Purple CTR Token")
        allowed = set(warp_pad_logic.REQ_WEIGHTS) - {"Purple CTR Token"}
        self.assertIsNone(_choose_requirement(_ScriptedRandom(), inv, allowed))


class ArenaTokenRequirementMixin:
    """Seed-level assertions on the emitted slot_data requirement dicts."""

    def _all_wire_reqs(self):
        world = self.world
        for pad, req in (getattr(world, "warp_pad_unlock", {}) or {}).items():
            yield f"{pad} stage1", req
        for pad, req in (getattr(world, "warp_pad_unlock_stage2", {}) or {}).items():
            yield f"{pad} stage2", req

    def _all_concrete_reqs(self):
        world = self.world
        for pad, req in (getattr(world, "warp_pad_unlock_concrete", {}) or {}).items():
            yield f"{pad} stage1", req
        for dest, req in (getattr(world,
                                  "warp_pad_unlock_stage2_concrete", {}) or {}).items():
            yield f"{dest} stage2", req

    def test_requirements_were_generated(self):
        # Premise guard: an empty requirement set would green-light the
        # assertions below vacuously.
        self.assertTrue(getattr(self.world, "warp_pad_unlock", {}),
                        "no warp-pad requirements generated; config regressed")


class ArenasOffRequirementMixin(ArenaTokenRequirementMixin):
    def test_no_requirement_names_purple_token(self):
        for where, req in self._all_wire_reqs():
            with self.subTest(requirement=where):
                self.assertFalse(
                    req["type"] == _TYPE_TOKEN and req["colour"] == _COLOUR_PURPLE,
                    f"{where} demands Purple CTR Tokens with arenas opted out: "
                    f"{req}")
        for where, req in self._all_concrete_reqs():
            with self.subTest(requirement=where):
                self.assertNotEqual(
                    req[0], "Purple CTR Token",
                    f"{where} demands Purple CTR Tokens with arenas opted out")

    def test_no_any_token_count_needs_arena_play(self):
        for where, req in self._all_wire_reqs():
            if req["type"] != _TYPE_ANY_TOKEN:
                continue
            with self.subTest(requirement=where):
                self.assertLessEqual(
                    req["count"], _MAX_TOKENS_WITHOUT_ARENAS,
                    f"{where} any-token count {req['count']} exceeds the "
                    f"{_MAX_TOKENS_WITHOUT_ARENAS} tokens obtainable without "
                    f"arena play")


class TestArenaTokensOffRandomized(ArenasOffRequirementMixin, CTRTestBase):
    """arenas OFF, randomized unlocks, default two-stage density."""

    run_default_tests = False
    options = {
        "include_battle_arenas": False,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "randomized",
    }


class TestArenaTokensOffWithout4Keys(ArenasOffRequirementMixin, CTRTestBase):
    """arenas OFF under the shipped default unlock mode + dense stage-2 gating
    (MarioSpore hit it 'mainly the 2nd stage')."""

    run_default_tests = False
    options = {
        "include_battle_arenas": False,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "random_without_4_keys",
        "two_stage_density": "deep",
    }


class TestArenaTokensOnStillDrawable(ArenaTokenRequirementMixin, CTRTestBase):
    """arenas ON: generation unchanged -- requirements exist and any-token
    counts may size on all five colours (cap 4x5=20 under the presets' own
    caps). The byte-identical-draws guarantee is covered by the scripted-RNG
    unit tests above; here we only pin that the ON path still generates."""

    run_default_tests = False
    options = {
        "include_battle_arenas": True,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "random_without_4_keys",
    }
