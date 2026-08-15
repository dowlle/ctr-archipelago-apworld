"""Ruling-to-code parity for CTR capability logic.

The field matrix is promoted into ``capability_contract`` once a row is ruled.
These tests exercise every confirmed boundary and the complete difficulty group,
so a green release cannot silently omit a ruled track.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..capability_contract import (
    CONFIRMED_FINISH_CAPABILITIES,
    EASY_TROPHY_GROUP,
    held_first_gated_tracks,
    unconditional_usf_finish_tracks,
    usf_or_hard_finish_tracks,
)
from ..itemsanity import ITEM_NAMES
from ..podium import location_name
from ..progressive_capability import ROSTER, boost_item_name
from ..usf_finish import (
    USF_FINISH_TRACKS,
    USF_OR_HARD_SK_FINISH_TRACKS,
)


STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _state(mw, boost=0, held=(), character_boosts=()):
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if (item != BOOST and not item.startswith(f"{BOOST} (")
                and item not in ITEM_NAMES):
            state.add_item(item, PLAYER, 99)
    for item in held:
        state.add_item(item, PLAYER, 1)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    for character, count in character_boosts:
        state.add_item(boost_item_name(character), PLAYER, count)
    return state


class TestContractCoverage(unittest.TestCase):
    def test_production_finish_sets_equal_the_confirmed_contract(self):
        self.assertEqual(USF_FINISH_TRACKS, unconditional_usf_finish_tracks())
        self.assertEqual(USF_OR_HARD_SK_FINISH_TRACKS,
                         usf_or_hard_finish_tracks())

    def test_every_confirmed_track_is_unique_and_named(self):
        names = [record.track for record in CONFIRMED_FINISH_CAPABILITIES]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("", names)


class TestConfirmedFinishBoundaries(unittest.TestCase):
    def test_zero_one_two_copy_boundary_for_every_confirmed_finish(self):
        for record in CONFIRMED_FINISH_CAPABILITIES:
            if record.hard_shortcut_escape:
                options = {"shortcut_knowledge": "medium"}
            else:
                options = {}
            mw = _build(progressive_boost="shared_global", **options)
            name = f"{record.track}: Trophy Race"
            with self.subTest(track=record.track, boost=0):
                self.assertFalse(_state(mw, boost=0).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=record.track, boost=1):
                self.assertFalse(_state(mw, boost=1).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=record.track, boost=2):
                self.assertTrue(_state(mw, boost=2).can_reach(
                    name, "Location", PLAYER))

    def test_held_first_gating_matches_the_contract(self):
        mw = _build(progressive_boost="shared_global",
                    shortcut_knowledge="medium")
        blocked = _state(mw, boost=0)
        for record in CONFIRMED_FINISH_CAPABILITIES:
            actual = blocked.can_reach(
                location_name(record.track, "held_1st"), "Location", PLAYER)
            with self.subTest(track=record.track):
                self.assertEqual(actual,
                                 record.track not in held_first_gated_tracks())


class TestDifficultyContract(unittest.TestCase):
    def test_slot_data_round_trips_logic_difficulty_for_universal_tracker(self):
        source = _build(logic_difficulty="easy")
        slot_data = source.worlds[PLAYER].fill_slot_data()
        self.assertEqual(slot_data["ctr_options"]["logic_difficulty"], 0)

        tracker = _build(logic_difficulty="hard")
        tracker.worlds[PLAYER]._ut_restore_options(slot_data)
        self.assertEqual(tracker.worlds[PLAYER].options.logic_difficulty.value,
                         0)

    def test_medium_trophy_requires_boost_or_two_useful_families(self):
        for track in sorted(EASY_TROPHY_GROUP.tracks):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty="medium")
            name = f"{track}: Trophy Race"
            with self.subTest(track=track, state="bare"):
                self.assertFalse(_state(mw).can_reach(name, "Location", PLAYER))
            with self.subTest(track=track, state="boost"):
                self.assertTrue(_state(mw, boost=1).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=track, state="weapons"):
                self.assertTrue(_state(mw, held=("Mask", "Warpball")).can_reach(
                    name, "Location", PLAYER))

    def test_hard_trophy_is_free_and_easy_adds_only_ruled_rung_gates(self):
        track = "Crash Cove"
        hard = _build(progressive_boost="shared_global", itemsanity=True,
                      logic_difficulty="hard")
        self.assertTrue(_state(hard).can_reach(
            f"{track}: Trophy Race", "Location", PLAYER))

        easy = _build(progressive_boost="shared_global", itemsanity=True,
                      logic_difficulty="easy")
        bare = _state(easy)
        self.assertFalse(bare.can_reach(
            f"{track}: Trophy Race", "Location", PLAYER))
        self.assertFalse(bare.can_reach(
            location_name(track, "finish_podium"), "Location", PLAYER))
        self.assertFalse(bare.can_reach(
            location_name(track, "held_1st"), "Location", PLAYER))
        self.assertTrue(bare.can_reach(
            location_name(track, "finish_any"), "Location", PLAYER))
        self.assertTrue(bare.can_reach(
            location_name(track, "held_3rd"), "Location", PLAYER))

    def test_per_character_unlocked_track_accepts_one_driveable_racer(self):
        mw = _build(progressive_boost="per_character", itemsanity=True,
                    logic_difficulty="medium", character_unlocks=False)
        racer = mw.worlds[PLAYER].ctr_starting_character
        name = "Crash Cove: Trophy Race"
        self.assertFalse(_state(mw).can_reach(name, "Location", PLAYER))
        self.assertTrue(_state(mw, character_boosts=((racer, 1),)).can_reach(
            name, "Location", PLAYER))

    def test_per_character_locked_track_requires_its_racer(self):
        mw = None
        track = required = None
        for seed in range(1, 33):
            candidate = _build(
                seed=seed, progressive_boost="per_character", itemsanity=True,
                logic_difficulty="medium", racer_locked_pads=True)
            locks = candidate.worlds[PLAYER].ctr_racer_locks
            matches = [(t, locks[f"{t} Warp Pad"])
                       for t in EASY_TROPHY_GROUP.tracks
                       if f"{t} Warp Pad" in locks]
            if matches:
                mw = candidate
                track, required = matches[0]
                break
        self.assertIsNotNone(mw, "fixture seeds produced no locked easy track")
        wrong = next(racer for racer in ROSTER if racer != required)
        name = f"{track}: Trophy Race"
        self.assertFalse(_state(
            mw, character_boosts=((wrong, 1),)).can_reach(
                name, "Location", PLAYER))
        self.assertTrue(_state(
            mw, character_boosts=((required, 1),)).can_reach(
                name, "Location", PLAYER))

    def test_option_vacuity_when_either_item_pack_is_off(self):
        for options in (
            {"progressive_boost": "off", "itemsanity": True},
            {"progressive_boost": "shared_global", "itemsanity": False},
        ):
            mw = _build(logic_difficulty="easy", **options)
            state = _state(mw)
            for track in EASY_TROPHY_GROUP.tracks:
                with self.subTest(options=options, track=track):
                    self.assertTrue(state.can_reach(
                        f"{track}: Trophy Race", "Location", PLAYER))
