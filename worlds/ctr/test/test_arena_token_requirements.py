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
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from worlds.AutoWorld import call_all

from . import CTRTestBase
from .. import warp_pad_logic
from ..warp_pad_logic import Inv, TOKEN_ITEMS, _choose_requirement
from ..Rules import _scoped_agg_names, _AGG_TOKENS, _AGG_RELICS, _AGG_GEMS

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


class _StubOption:
    def __init__(self, value):
        self.value = value


class _StubOptions:
    def __init__(self, arenas_on):
        self.include_battle_arenas = _StubOption(arenas_on)


class _StubWorld:
    """Just enough of a world for Rules._scoped_agg_names -- no generation."""
    def __init__(self, arenas_on):
        self.options = _StubOptions(arenas_on)


class TestAggTokenScoping(unittest.TestCase):
    """Tight guard on the Rules.py side of the fix (the AP-logic counting that
    the AP-level beatability tests below exercise end-to-end). This is the test
    that fails if _scoped_agg_names stops dropping Purple: with arenas OFF the
    token aggregate that _agg_has sums over -- feeding the type-6 warp-pad gate
    (Rules.add_warp_pad_unlock_rules) and the AnyCtrToken stage-2 gate
    (Rules.add_time_trial_and_ctr_requirements) -- must exclude Purple CTR
    Token, so no aggregate token gate can be met via the four vanilla-pinned
    arena Purples."""

    def test_purple_dropped_from_token_aggregate_when_arenas_off(self):
        names = _scoped_agg_names(_StubWorld(arenas_on=False), _AGG_TOKENS)
        self.assertNotIn("Purple CTR Token", names)
        self.assertEqual(
            names,
            ["Red CTR Token", "Green CTR Token", "Blue CTR Token", "Yellow CTR Token"],
            "arenas off: only the 4 non-arena token colours count toward an "
            "any-token gate")

    def test_token_aggregate_intact_when_arenas_on(self):
        names = _scoped_agg_names(_StubWorld(arenas_on=True), _AGG_TOKENS)
        self.assertIn("Purple CTR Token", names)
        self.assertEqual(names, _AGG_TOKENS)

    def test_relic_and_gem_aggregates_never_scoped(self):
        # The exclusion is token-only; relic/gem any-of gates are untouched
        # regardless of the arena option.
        for arenas_on in (True, False):
            self.assertEqual(
                _scoped_agg_names(_StubWorld(arenas_on), _AGG_RELICS), _AGG_RELICS)
            self.assertEqual(
                _scoped_agg_names(_StubWorld(arenas_on), _AGG_GEMS), _AGG_GEMS)


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


_CRYSTAL_SUFFIX = "Crystal Bonus Round"


class ArenaNotRequiredAtAPLevelMixin:
    """AP-level (post-fill) guard for issue #118.

    The slot_data tests above pin what generation EMITS; this pins what the
    finished multiworld MEANS. For a batch of arenas-off seeds we run the real
    fill, then rebuild reachability collecting advancement items from every
    location EXCEPT the four Crystal Bonus Rounds (the arena checks) and assert
    the seed's completion_condition is still satisfied. That is the property the
    option promises: no arena play is ever logically required. It would fail if
    any gate on the beatable path counted the arena-locked Purple CTR Tokens
    (Rules._agg_has over the token aggregate) -- the AP-side sibling of the
    sphere-search exclusion that the slot_data tests cover.

    Subclasses set `options` and (optionally) `seeds`."""

    seeds = range(1, 7)

    def test_completion_never_requires_an_arena_location(self):
        for seed in self.seeds:
            with self.subTest(seed=seed):
                self.world_setup(seed=seed)
                distribute_items_restrictive(self.multiworld)
                call_all(self.multiworld, "post_fill")

                mw, player = self.multiworld, self.player
                arena = [loc for loc in mw.get_locations(player)
                         if loc.name.endswith(_CRYSTAL_SUFFIX)]
                # Premise guards: arenas off must still leave the 4 crystal checks
                # in the seed, vanilla-pinned with their own Purple CTR Tokens
                # (#50). Without this a vacuous pass could hide a regression.
                self.assertEqual(len(arena), 4,
                                 "expected the 4 vanilla-pinned Crystal Bonus Rounds")
                for loc in arena:
                    self.assertEqual(
                        loc.item.name, "Purple CTR Token",
                        f"{loc.name} should hold its vanilla Purple CTR Token")

                # Collect advancement items from every NON-arena location only,
                # in reachability order (a real sphere sweep restricted to that
                # set), then check the win condition. Reaching completion here
                # means the arena Purples were never on the critical path.
                non_arena = [loc for loc in mw.get_locations(player)
                             if not loc.name.endswith(_CRYSTAL_SUFFIX)]
                state = CollectionState(mw)
                state.sweep_for_advancements(non_arena)
                self.assertTrue(
                    mw.completion_condition[player](state),
                    "seed is not beatable without collecting an arena location: "
                    "arena play is logically required (issue #118)")


class TestArenaNotRequiredRandomizedDeep(ArenaNotRequiredAtAPLevelMixin, CTRTestBase):
    """arenas OFF, randomized unlocks, dense two-stage gating -- the mode most
    likely to draw an AnyCtrToken second gate."""

    run_default_tests = False
    auto_construct = False
    options = {
        "include_battle_arenas": False,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "randomized",
        "two_stage_density": "deep",
    }


class TestArenaNotRequiredWithout4KeysFull(ArenaNotRequiredAtAPLevelMixin, CTRTestBase):
    """arenas OFF, random_without_4_keys, full two-stage density (every eligible
    pad gated) -- maximum ordering pressure and the most interlocked token
    gates."""

    run_default_tests = False
    auto_construct = False
    options = {
        "include_battle_arenas": False,
        "include_gem_cups": True,
        "warppad_unlock_requirements": "random_without_4_keys",
        "two_stage_density": "full",
    }
