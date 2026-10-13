"""The destination table is the one source of destination keys (#310).

Every consumer that names a track, gem cup, pad destination or custom slot
reads its keys from `destinations`. These tests fail when a consumer keeps a
private copy that drifts, and when an unknown key is accepted silently.
"""
import json
import pkgutil
import unittest

from .. import (capability_contract, custom_track_locations, custom_tracks,
                destinations, gem_cup_legs, item_boxes, lettersanity, podium,
                relic_perfect, trial_trophy, usf_finish, warp_pad_logic)
from .. import Regions


def _pads():
    return json.loads(pkgutil.get_data(
        "worlds.ctr", "data/warp_pad_ids.json").decode("utf-8"))["pads"]


class TestDestinationTable(unittest.TestCase):
    def test_shape(self):
        kinds = [d.kind for d in destinations.DESTINATIONS]
        self.assertEqual(kinds.count(destinations.KIND_RACE), 16)
        self.assertEqual(kinds.count(destinations.KIND_ARENA), 4)
        self.assertEqual(kinds.count(destinations.KIND_TRIAL), 2)
        self.assertEqual(kinds.count(destinations.KIND_CUP), 5)
        keys = [d.key for d in destinations.DESTINATIONS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_level_ids_come_from_the_pad_file(self):
        pads = _pads()
        self.assertEqual({d.pad_name: d.level_id for d in destinations.DESTINATIONS},
                         {name: meta["level_id"] for name, meta in pads.items()})
        self.assertEqual(destinations.BY_KEY["Cortex Vortex"].level_id, 110)

    def test_unknown_keys_fail(self):
        with self.assertRaises(KeyError):
            destinations.require("Not A Track")
        with self.assertRaises(KeyError):
            destinations.require_all(["Crash Cove", "Crash Cave"])
        with self.assertRaises(KeyError):
            destinations.level_ids_for(["Crash Cave"])
        with self.assertRaises(ValueError):
            destinations.check_keys({"Crash Cove": 1}, ["Crash Cove", "Coco Park"], "x")
        with self.assertRaises(KeyError):
            destinations.cup_destination("Orange Gem Cup")


class TestConsumersReadTheTable(unittest.TestCase):
    def test_warp_pad_logic(self):
        self.assertEqual(list(warp_pad_logic.HUB_STATIC),
                         [d.key for d in destinations.DESTINATIONS])
        self.assertEqual(warp_pad_logic.TRIAL_TRACKS, set(destinations.TRIAL_TRACKS))
        self.assertEqual(warp_pad_logic.CUP_TRACKS, set(destinations.CUP_PAD_TRACKS))
        self.assertEqual(warp_pad_logic.ARENA_TRACKS, set(destinations.ARENA_TRACKS))
        self.assertEqual(warp_pad_logic.TROPHY_TRACKS, set(destinations.RACE_TRACKS))
        self.assertEqual(set(warp_pad_logic.TRACK_TOKEN_COLOUR),
                         set(destinations.RACE_TRACKS))
        destinations.require_all(warp_pad_logic.FREE_CANDIDATES)

    def test_track_families(self):
        for family in (item_boxes.BOX_TRACKS, podium.TROPHY_TRACKS,
                       lettersanity.LETTER_TRACKS, relic_perfect.RELIC_TRACKS):
            destinations.require_all(family)
        self.assertEqual(set(podium.TROPHY_TRACKS), set(destinations.RACE_TRACKS))
        self.assertEqual(set(lettersanity.LETTER_TRACKS), set(destinations.RACE_TRACKS))
        self.assertEqual(set(item_boxes.BOX_TRACKS),
                         set(destinations.RACE_TRACKS) | set(destinations.TRIAL_TRACKS))
        self.assertIs(podium.TRIAL_TRACKS, destinations.TRIAL_TRACKS)
        self.assertIs(trial_trophy.TRIAL_TRACKS, destinations.TRIAL_TRACKS)
        self.assertEqual(item_boxes.TRACK_LEVEL_IDS,
                         destinations.level_ids_for(item_boxes.BOX_TRACKS))
        self.assertEqual(relic_perfect.track_level_ids(),
                         destinations.level_ids_for(relic_perfect.RELIC_TRACKS))
        self.assertEqual(gem_cup_legs.track_level_ids(),
                         destinations.level_ids_for(destinations.RACE_TRACKS))
        self.assertEqual(set(item_boxes.PLACED_COUNTS), set(item_boxes.BOX_TRACKS))

    def test_gem_cups_and_custom_tracks(self):
        self.assertIs(gem_cup_legs.CUP_LEVEL_IDS, destinations.CUP_LEVEL_IDS)
        self.assertEqual(custom_tracks.REPLACEABLE_DESTINATIONS["purple_gem_cup"],
                         ("Purple Gem Cup", 104))
        self.assertEqual(custom_track_locations.CUSTOM_TRACK_SLOT_COUNT,
                         destinations.CUSTOM_TRACK_SLOT_COUNT)
        self.assertEqual(custom_track_locations.slot_region(3),
                         destinations.custom_slot_region(3))

    def test_boss_tables(self):
        self.assertEqual(Regions.BOSS_WUMPA_TRACKS, destinations.boss_garage_tracks())
        self.assertEqual(Regions.VANILLA_BOSS_TRACKS, destinations.boss_hub_level_ids())
        self.assertEqual(Regions.VANILLA_BOSS_TRACKS["ripper_roo"], [3, 6, 9, 8])

    def test_capability_tables_reference_table_keys(self):
        destinations.require_all(capability_contract.difficulty_gated_tracks())
        destinations.require_all(capability_contract.CONFIRMED_FINISH_BY_TRACK)
        destinations.require_all(usf_finish.USF_RELIC_GOLD_TRACKS
                                 | usf_finish.USF_RELIC_PLATINUM_TRACKS)
        destinations.require_all(usf_finish.ALL_USF_FINISH_TRACKS)
