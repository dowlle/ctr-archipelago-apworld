"""Arena-off seeds keep Purple CTR Tokens in token requirements (#364).

include_battle_arenas off removes the four arena locations only. The Purple
Token items stay in the pool, so direct and AnyCtrToken requirements may still
name Purple, and the seed must stay beatable without the removed locations.
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
    """Rules._scoped_agg_names no longer drops Purple with arenas off."""

    def test_token_aggregate_keeps_purple_either_way(self):
        for arenas_on in (True, False):
            names = _scoped_agg_names(_StubWorld(arenas_on), _AGG_TOKENS)
            self.assertIn("Purple CTR Token", names)
            self.assertEqual(names, _AGG_TOKENS)

    def test_relic_and_gem_aggregates_never_scoped(self):
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


_CRYSTAL_SUFFIX = "Crystal Challenge"


class ArenaNotRequiredAtAPLevelMixin:
    """AP-level (post-fill) guard for #364.

    This pins what the finished multiworld MEANS. For a batch of arenas-off seeds we run the real
    fill, verify the four Crystal Challenges are absent, and assert the
    seed's completion_condition remains reachable without them.

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
                self.assertEqual(len(arena), 0,
                                 "arena-off seeds must omit Crystal Challenges")

                # Collect advancement items from every created location in
                # reachability order, then check the win condition.
                non_arena = [loc for loc in mw.get_locations(player)
                             if not loc.name.endswith(_CRYSTAL_SUFFIX)]
                state = CollectionState(mw)
                state.sweep_for_advancements(non_arena)
                self.assertTrue(
                    mw.completion_condition[player](state),
                    "seed is not beatable without collecting an arena location: "
                    "arena play is logically required (#364)")


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
