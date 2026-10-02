"""The 2026-10-01 rulings on the two largest option-refusal families.

Measured on a 1,500-roll fuzzer refusal tally of 0.2.3. The podium half
(refuse only when locations are really short, clearer wording) is covered in
test_rung_sizer.py. This file covers the relic
half:

- Ruling 3: when Oxide's Final Challenge asks for more relics than the seed
  creates, `oxide_final_challenge_relic_count` is lowered to the created
  supply, with a notice, in every seed (also `minimal`). The lowered value is
  what slot_data's `oxide_final_count` carries, and what Universal Tracker
  restores.
- Ruling 4: in vanilla warp-pad mode with fewer than 10 Sapphire Relics
  created, the player's `sapphire_relic_count` is kept and the Slide Coliseum
  pad opens at the Sapphires that exist. The apworld emits the lowered gate as
  pad 16's stage-1 requirement and its logic uses the same value; a seed
  without that entry (any seed rolled before the rule) keeps 10, on the
  tracker as in native.
"""
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..relic_tiers import (SLIDE_COLISEUM_LEVEL_ID, SLIDE_COLISEUM_PAD,
                           slide_coliseum_sapphire_gate)

EARLY = ("generate_early",)
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
LOGGER_NAME = "worlds.ctr.forced_options"
PLAYER = 1
FINAL = "N. Oxide Garage: N. Oxide's Final Challenge"


def _build(options, steps=STEPS, seed=None):
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _rebuild(wire, **local):
    """Universal Tracker re-generation from a seed's slot_data, with the
    tracking player's own YAML in `local`."""
    tracker = setup_multiworld(ctrAPWorld, steps=(), seed=99, options=local)
    tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
    for step in STEPS:
        call_all(tracker, step)
    return tracker


def _state_with(mw, name, count):
    state = CollectionState(mw)
    if count:
        state.add_item(name, PLAYER, count)
    state.stale[PLAYER] = True
    return state


def _pad16(wire):
    return wire["warp_pad_unlock"][str(SLIDE_COLISEUM_LEVEL_ID)]["stage1"]


def _notices(cm, needle):
    return [line for line in cm.output if needle in line]


# ---------------------------------------------------------------------------
# Ruling 3: the Final Challenge count is lowered to the created supply.
# ---------------------------------------------------------------------------

class TestFinalChallengeCountLoweredToSupply(unittest.TestCase):

    def test_full_accessibility_lowers_instead_of_refusing(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build({"accessibility": "full", "sapphire_relic_count": 17})
        world = mw.worlds[PLAYER]
        self.assertEqual(world.options.oxide_final_challenge_relic_count.value, 17)
        self.assertEqual(_wire(mw)["ctr_options"]["oxide_final_count"], 17)
        lines = _notices(cm, "Relic Count lowered")
        self.assertEqual(len(lines), 1)
        self.assertIn("lowered from 18 to 17", lines[0])
        self.assertIn("Sapphire Relics this seed creates", lines[0])

    def test_minimal_accessibility_lowers_too(self):
        # "lower to supply always makes the most sense": a minimal seed that
        # used to generate with an unreachable Final Challenge now gets one it
        # can open, and no "can never be reached" warning.
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build({"accessibility": "minimal", "oxide_goal": "first",
                         "oxide_final_challenge_unlock": "platinum_relics",
                         "oxide_final_challenge_relic_count": 10,
                         "platinum_relic_count": 2})
        world = mw.worlds[PLAYER]
        self.assertEqual(world.options.oxide_final_challenge_relic_count.value, 2)
        self.assertEqual(len(_notices(cm, "lowered from 10 to 2")), 1)
        self.assertEqual(_notices(cm, "can never be reached"), [])

    def test_101_percent_goal_lowers_instead_of_refusing(self):
        mw = _build({"oxide_goal": "final", "accessibility": "minimal",
                     "oxide_final_challenge_unlock": "gold_relics",
                     "oxide_final_challenge_relic_count": 10,
                     "gold_relic_count": 3})
        world = mw.worlds[PLAYER]
        self.assertEqual(world.options.oxide_final_challenge_relic_count.value, 3)
        rule = world._oxide_final_relic_rule()
        self.assertFalse(rule(_state_with(mw, "Gold Relic", 2)))
        self.assertTrue(rule(_state_with(mw, "Gold Relic", 3)))

    def test_total_relics_lowers_to_the_sum_of_all_tiers(self):
        mw = _build({"oxide_goal": "final", "accessibility": "minimal",
                     "warppad_unlock_requirements": "randomized",
                     "oxide_final_challenge_unlock": "total_relics",
                     "oxide_final_challenge_relic_count": 30,
                     "sapphire_relic_count": 5, "gold_relic_count": 5,
                     "platinum_relic_count": 0}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 10)

    def test_any_relic_type_lowers_to_the_largest_tier(self):
        mw = _build({"accessibility": "full",
                     "warppad_unlock_requirements": "randomized",
                     "oxide_final_challenge_unlock": "any_relic_type",
                     "oxide_final_challenge_relic_count": 18,
                     "sapphire_relic_count": 4, "gold_relic_count": 9,
                     "platinum_relic_count": 7}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 9)

    def test_above_18_then_below_supply_ends_at_the_supply(self):
        mw = _build({"accessibility": "full",
                     "oxide_final_challenge_unlock": "gold_relics",
                     "oxide_final_challenge_relic_count": 40,
                     "gold_relic_count": 11}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 11)

    def test_count_within_supply_is_untouched_and_silent(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _build({"accessibility": "full",
                         "oxide_final_challenge_unlock": "gold_relics",
                         "oxide_final_challenge_relic_count": 7,
                         "gold_relic_count": 7}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 7)

    def test_disabled_oxide_is_untouched(self):
        mw = _build({"oxide_goal": "disabled", "bosses_required_goal": 4,
                     "accessibility": "full",
                     "sapphire_relic_count": 5}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 18)

    def test_tier_with_no_relics_still_refuses_under_full(self):
        with self.assertRaises(OptionError) as ctx:
            _build({"accessibility": "full", "oxide_goal": "first",
                    "warppad_unlock_requirements": "randomized",
                    "oxide_final_challenge_unlock": "platinum_relics",
                    "oxide_final_challenge_relic_count": 5,
                    "platinum_relic_count": 0}, steps=EARLY)
        self.assertIn("Final Challenge", str(ctx.exception))

    def test_tier_with_no_relics_still_warns_under_minimal(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build({"accessibility": "minimal", "oxide_goal": "first",
                         "warppad_unlock_requirements": "randomized",
                         "oxide_final_challenge_unlock": "platinum_relics",
                         "oxide_final_challenge_relic_count": 5,
                         "platinum_relic_count": 0}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 5)
        self.assertEqual(len(_notices(cm, "can never be reached")), 1)

    def test_lowered_seed_fills_with_full_accessibility(self):
        mw = _build({"accessibility": "full",
                     "warppad_unlock_requirements": "randomized",
                     "oxide_goal": "final",
                     "oxide_final_challenge_relic_count": 14,
                     "sapphire_relic_count": 9}, seed=4101,
                    steps=STEPS + ("connect_entrances", "generate_basic", "pre_fill"))
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 9)
        distribute_items_restrictive(mw)
        self.assertTrue(mw.fulfills_accessibility())
        self.assertTrue(mw.can_beat_game())

    def test_universal_tracker_restores_the_lowered_count(self):
        options = {"accessibility": "full", "sapphire_relic_count": 12}
        original = _build(options, seed=4102)
        wire = _wire(original)
        self.assertEqual(wire["ctr_options"]["oxide_final_count"], 12)
        # The tracking player's own YAML still says 18 Sapphires and count 18.
        tracker = _rebuild(wire)
        tworld = tracker.worlds[PLAYER]
        self.assertEqual(tworld.options.oxide_final_challenge_relic_count.value, 12)
        for have in (11, 12):
            with self.subTest(sapphires=have):
                self.assertEqual(
                    tworld._oxide_final_relic_rule()(_state_with(tracker, "Sapphire Relic", have)),
                    original.worlds[PLAYER]._oxide_final_relic_rule()(
                        _state_with(original, "Sapphire Relic", have)))


# ---------------------------------------------------------------------------
# Ruling 4: the vanilla Slide Coliseum pad opens at the Sapphires that exist.
# ---------------------------------------------------------------------------

VANILLA = {"warppad_unlock_requirements": "vanilla"}


class TestSlideColiseumGateLowered(unittest.TestCase):

    def _pad_open(self, mw, sapphires):
        entrance = mw.get_entrance(SLIDE_COLISEUM_PAD, PLAYER)
        return bool(entrance.access_rule(_state_with(mw, "Sapphire Relic", sapphires)))

    def test_vanilla_full_with_six_sapphires_generates_with_gate_six(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build(dict(VANILLA, accessibility="full", sapphire_relic_count=6))
        world = mw.worlds[PLAYER]
        self.assertEqual(world.options.sapphire_relic_count.value, 6)  # kept
        self.assertEqual(slide_coliseum_sapphire_gate(world), 6)
        self.assertEqual(_pad16(_wire(mw)), {"type": 4, "count": 6, "colour": 0})
        self.assertFalse(self._pad_open(mw, 5))
        self.assertTrue(self._pad_open(mw, 6))
        lines = _notices(cm, "Slide Coliseum warp pad")
        self.assertEqual(len(lines), 1)
        self.assertIn("opens at 6 Sapphire Relics instead of 10", lines[0])
        self.assertIn("lowered", lines[0])

    def test_zero_sapphires_uses_the_free_pad_convention(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build(dict(VANILLA, accessibility="full", sapphire_relic_count=0,
                             oxide_final_challenge_unlock="gold_relics"))
        self.assertEqual(_pad16(_wire(mw)), {"type": 1, "count": 0, "colour": -1})
        self.assertTrue(self._pad_open(mw, 0))
        self.assertEqual(len(_notices(cm, "opens without Sapphire Relics")), 1)

    def test_ten_or_more_sapphires_keep_the_retail_gate(self):
        for count in (10, 18):
            with self.subTest(sapphires=count):
                mw = _build(dict(VANILLA, accessibility="full",
                                 sapphire_relic_count=count))
                self.assertEqual(_pad16(_wire(mw))["type"], 0)
                self.assertFalse(self._pad_open(mw, 9))
                self.assertTrue(self._pad_open(mw, 10))

    def test_minimal_vanilla_lowers_the_gate_too(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as cm:
            mw = _build(dict(VANILLA, accessibility="minimal", oxide_goal="first",
                             sapphire_relic_count=4, gold_relic_count=18,
                             oxide_final_challenge_unlock="gold_relics"))
        self.assertEqual(_pad16(_wire(mw)), {"type": 4, "count": 4, "colour": 0})
        self.assertEqual(_notices(cm, "can never be reached"), [])

    def test_randomized_modes_are_untouched(self):
        mw = _build({"warppad_unlock_requirements": "randomized",
                     "accessibility": "full", "sapphire_relic_count": 5,
                     "oxide_final_challenge_unlock": "gold_relics"}, steps=EARLY)
        self.assertIsNone(slide_coliseum_sapphire_gate(mw.worlds[PLAYER]))

    def test_vanilla_lowered_seed_fills_with_full_accessibility(self):
        mw = _build(dict(VANILLA, accessibility="full", sapphire_relic_count=3,
                         oxide_final_challenge_unlock="gold_relics"), seed=4103,
                    steps=STEPS + ("connect_entrances", "generate_basic", "pre_fill"))
        distribute_items_restrictive(mw)
        self.assertTrue(mw.fulfills_accessibility())
        self.assertTrue(mw.can_beat_game())

    def test_universal_tracker_reads_the_emitted_gate(self):
        original = _build(dict(VANILLA, accessibility="full", sapphire_relic_count=7),
                          seed=4104)
        wire = _wire(original)
        tracker = _rebuild(wire)
        self.assertEqual(slide_coliseum_sapphire_gate(tracker.worlds[PLAYER]), 7)
        for have in (6, 7, 10):
            with self.subTest(sapphires=have):
                self.assertEqual(self._pad_open(tracker, have),
                                 self._pad_open(original, have))

    def test_universal_tracker_keeps_ten_for_a_seed_without_the_entry(self):
        # A seed rolled before 2026-10-01 never emitted pad 16 in vanilla mode,
        # and its native keeps the retail 10 even with fewer Sapphires created.
        # The tracker must agree with that native, not lower the gate itself.
        original = _build(dict(VANILLA, accessibility="full", sapphire_relic_count=7),
                          seed=4105)
        wire = _wire(original)
        wire["warp_pad_unlock"][str(SLIDE_COLISEUM_LEVEL_ID)]["stage1"] = {
            "type": 0, "count": 0, "colour": -1}
        tracker = _rebuild(wire)
        self.assertEqual(slide_coliseum_sapphire_gate(tracker.worlds[PLAYER]), 10)
        self.assertFalse(self._pad_open(tracker, 9))
        self.assertTrue(self._pad_open(tracker, 10))


if __name__ == "__main__":
    unittest.main()
