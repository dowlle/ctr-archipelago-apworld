"""A real stage 2 gate is never already met by its own pad's stage 1 (issue #342).

WHY THIS FILE EXISTS
--------------------
The sphere search draws a pad's stage 1 and stage 2 independently, then lowers
each independently in `_post_process`, and stage 2 has the lower count ceiling
(4 against 8). Before #342 that regularly produced rows like "8 trophies, then
4 trophies": the stage 2 gate is met the moment the pad opens, so it never
blocks anything. Over 120 default seeds that was 1.5 such gates per seed, about
four times Icebound's rate (0.4 per seed over 300 standalone seeds).

The rule now: same item type is allowed only if stage 2 is strictly higher;
otherwise stage 2 is redrawn from another item family. A stage 2 may still be an
EXACT copy of stage 1, which is the intended collapse ("no gate beyond the
trophy race").

The invariant is asserted on the wire rows native parses
(`fill_slot_data()["warp_pad_unlock"]`), physical-pad keyed, so it covers the
real host pad under destination shuffle.
"""

import unittest

from . import CTRTestBase
from .. import content_playthrough
from ..content_playthrough import stage2_met_by_stage1

# Wire types (content_playthrough.to_slot_req): 0 none, 1 trophies, 2 keys, 3 token,
# 4 relic tier, 5 gem, 6 any token, 7 any relic, 8 any gem.
_FAMILY = {1: "Trophy", 2: "Key", 3: "Token", 4: "Relic", 5: "Gem",
           6: "Token", 7: "Relic", 8: "Gem"}
_ANY_TYPES = (6, 7, 8)


def _wire_met_by_stage1(s1, s2):
    """Wire-level mirror of stage2_met_by_stage1, written independently so the
    world-level assertion does not just re-run the code under test."""
    t1, t2 = s1["type"], s2["type"]
    if t1 == 0 or t2 == 0:
        return False
    same_item = t1 == t2 and s1["colour"] == s2["colour"]
    any_of_family = t2 in _ANY_TYPES and _FAMILY[t1] == _FAMILY[t2]
    return (same_item or any_of_family) and s2["count"] <= s1["count"]


class TestStage2MetByStage1(unittest.TestCase):

    def test_same_item_at_or_below_stage1_is_met(self):
        self.assertTrue(stage2_met_by_stage1(("Trophy", 8), ("Trophy", 4)))
        self.assertTrue(stage2_met_by_stage1(("Trophy", 4), ("Trophy", 4)))
        self.assertTrue(stage2_met_by_stage1(("Key", 2), ("Key", 1)))

    def test_same_item_strictly_higher_is_a_real_gate(self):
        self.assertFalse(stage2_met_by_stage1(("Trophy", 3), ("Trophy", 4)))

    def test_any_of_stage1_family_at_or_below_is_met(self):
        self.assertTrue(stage2_met_by_stage1(("Gold Relic", 6), ("AnyRelic", 4)))
        self.assertTrue(stage2_met_by_stage1(("Red CTR Token", 3),
                                             ("AnyCtrToken", 3)))
        self.assertTrue(stage2_met_by_stage1(("AnyGem", 3), ("AnyGem", 2)))

    def test_other_colour_or_tier_is_a_real_gate(self):
        # Owning 3 Red tokens says nothing about Blue; owning any 6 tokens says
        # nothing about 2 Red specifically.
        self.assertFalse(stage2_met_by_stage1(("Red CTR Token", 3),
                                              ("Blue CTR Token", 2)))
        self.assertFalse(stage2_met_by_stage1(("AnyCtrToken", 6),
                                              ("Red CTR Token", 2)))
        self.assertFalse(stage2_met_by_stage1(("Gold Relic", 6),
                                              ("Sapphire Relic", 2)))

    def test_other_family_or_open_is_never_met(self):
        self.assertFalse(stage2_met_by_stage1(("Trophy", 8), ("Key", 1)))
        self.assertFalse(stage2_met_by_stage1(None, ("Trophy", 1)))
        self.assertFalse(stage2_met_by_stage1(("Trophy", 4), None))


class _Stage2Matrix:
    seeds = range(1, 41)

    def _rows(self):
        rows = self.world.fill_slot_data().get("warp_pad_unlock", {})
        for lid, stages in rows.items():
            yield lid, stages["stage1"], stages["stage2"]

    def _scan(self, seeds):
        """Returns (violations, strictly_higher_same_family, real_gates)."""
        violations, same_family_higher, real_gates = [], 0, 0
        for seed in seeds:
            self.world_setup(seed=seed)
            for lid, s1, s2 in self._rows():
                if s2["type"] == 0 or s2 == s1:
                    continue  # no stage 2, or the intended collapse copy
                real_gates += 1
                if _wire_met_by_stage1(s1, s2):
                    violations.append((seed, lid, s1, s2))
                elif (s1["type"] != 0
                      and _FAMILY[s1["type"]] == _FAMILY[s2["type"]]):
                    same_family_higher += 1
        return violations, same_family_higher, real_gates




class TestDefaultOptions(_Stage2Matrix, CTRTestBase):
    run_default_tests = False
    auto_construct = False
    options = {}


class TestNoDestinationShuffle(_Stage2Matrix, CTRTestBase):
    """Shuffle off: the collapsed-copy re-key (step 3b) now runs here too."""
    run_default_tests = False
    auto_construct = False
    options = {"two_stage_density": "full",
               "warp_pad_shuffle_categories": []}


class TestMergedShuffle(_Stage2Matrix, CTRTestBase):
    """Merged destination shuffle: re-validation runs after the rule and can
    redraw a stage 1, which the post-revalidation collapse must cover."""
    run_default_tests = False
    auto_construct = False
    options = {"two_stage_density": "full",
               "include_gem_cups": True,
               "include_battle_arenas": True,
               "warp_pad_shuffle_categories": ["tracks", "cups", "crystals"],
               "warp_pad_shuffle_grouping": "merged"}
