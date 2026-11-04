"""Boss track shuffle (#169 tier 1, schema 18).

Design: the 0.3.0 #169 design with independent switches, ruled 2026-10-13.
Each of the four ordinary garages
races its own boss, with its own retail attack, on a drawn certified track.
The physical check, Key, door, personal-win event and Oxide stay fixed. Only
the boss win's finish term and the garage's Wumpa route follow the venue.
"""
import json
import os
import unittest
from unittest import mock

from BaseClasses import CollectionState
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from .. import boss_track_shuffle as bts
from ..destinations import boss_garage_tracks

BOSS_WUMPA_TRACKS = boss_garage_tracks()

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "boss_venues.json")


def _build(seed=1, venues=None, **options):
    options.setdefault("wumpa_check", "per_track")
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    if venues is not None:
        mw.worlds[PLAYER].options._boss_track_venues = dict(venues)
    for step in STEPS:
        call_all(mw, step)
    return mw


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _sources(mw, region):
    return {e.parent_region.name for e in mw.get_region(region, PLAYER).entrances}


def _everything(mw, boost):
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item == BOOST or item.startswith(f"{BOOST} ("):
            continue
        state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


class TestSharedFixture(unittest.TestCase):
    """The venue table and the four garages' retail attack schedules are
    shared, byte for byte, with native `tools/fixtures/boss_venues.json`."""

    def test_tables_equal_the_fixture(self):
        with open(FIXTURE, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["block_version"], bts.BLOCK_VERSION)
        self.assertEqual({row["name"]: row["restart_points"] for row in doc["venues"]},
                         bts.VENUES)
        self.assertEqual({row["name"]: row["level_id"] for row in doc["venues"]},
                         bts.VENUE_LEVEL_IDS)
        self.assertEqual(sorted(row["level_id"] for row in doc["venues"]),
                         list(range(18)))
        self.assertEqual(
            [(g["key"], g["location"], g["home_level_id"], tuple(g["attack_checkpoints"]))
             for g in doc["garages"]],
            [(k, c, bts.VENUE_LEVEL_IDS[h], bts.RETAIL_ATTACK_CHECKPOINTS[k])
             for k, _r, c, h in bts.GARAGES])
        self.assertEqual([g["index"] for g in doc["garages"]], [0, 1, 2, 3])

    def test_garage_codes_are_the_frozen_boss_race_codes(self):
        for key, region, code, _home in bts.GARAGES:
            self.assertEqual(ctrAPWorld.location_name_to_id[f"{region}: Boss Race"], code)

    def test_retail_home_tracks_match_the_destination_table(self):
        self.assertEqual({region: home for _k, region, _c, home in bts.GARAGES},
                         {g: t for g, t in BOSS_WUMPA_TRACKS.items()
                          if g != "N. Oxide Garage"})


class TestCertification(unittest.TestCase):

    def test_home_track_maps_to_itself(self):
        for key, _r, _c, home in bts.GARAGES:
            self.assertEqual(bts.translated_schedule(key, home),
                             bts.RETAIL_ATTACK_CHECKPOINTS[key])

    def test_every_recorded_track_carries_every_inherited_attack(self):
        for key, _r, _c, _h in bts.GARAGES:
            for track in bts.VENUES:
                with self.subTest(garage=key, track=track):
                    self.assertTrue(bts.inherited_attack_certified(key, track))

    def test_a_track_too_short_for_the_schedule_is_refused(self):
        with mock.patch.dict(bts.VENUES, {"Crash Cove": 4}):
            self.assertFalse(bts.inherited_attack_certified("papu_papu", "Crash Cove"))
        self.assertFalse(bts.inherited_attack_certified("papu_papu", "Cortex Vortex"))

    def test_translation_keeps_relative_lap_position(self):
        # Pinstripe's last segment starts at 0x46 of Hot Air Skyway's 174.
        self.assertEqual(bts.translated_schedule("pinstripe", "Crash Cove"),
                         (0, 6, 13, 19, 28))




class TestDraw(unittest.TestCase):








    def test_ordinary_pad_use_never_counts_as_a_repeat(self):
        # Crash Cove keeps its own pad and Trophy Race while Roo races there.
        mw = _build(boss_track_shuffle=True, venues={
            "ripper_roo": "Crash Cove", "papu_papu": "Papu's Pyramid",
            "komodo_joe": "Dragon Mines", "pinstripe": "Hot Air Skyway"})
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertIn("Crash Cove: Trophy Race", names)


SWAPPED = {"ripper_roo": "Cortex Castle", "papu_papu": "Crash Cove",
           "komodo_joe": "Turbo Track", "pinstripe": "Coco Park"}






class TestUniversalTracker(unittest.TestCase):

    def _ut(self, passthrough, seed=99, **options):
        mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
        mw.re_gen_passthrough = {"Crash Team Racing": passthrough}
        for step in STEPS:
            call_all(mw, step)
        return mw


    def test_off_seed_restores_off_even_from_an_on_yaml(self):
        wire = _wire(_build(seed=13))
        mw = self._ut(wire, boss_track_shuffle=True,
                      boss_track_allowlist=["Crash Cove"])
        self.assertFalse(mw.worlds[PLAYER].options.boss_track_shuffle.value)
        self.assertNotIn("boss_encounters", _wire(mw))



class TestParseWire(unittest.TestCase):

    def setUp(self):
        self.block = bts.wire_block(type("O", (), {
            "boss_track_shuffle": type("T", (), {"value": 1})(),
            "_boss_track_venues": dict(SWAPPED)})())

    def test_round_trip(self):
        self.assertEqual(bts.parse_wire(self.block), SWAPPED)

    def test_multidata_tuples_parse(self):
        # A server round trip turns JSON arrays into tuples (seen in the
        # Universal Tracker fuzz arm).
        block = json.loads(json.dumps(self.block))
        for row in block["garages"].values():
            row["packages"] = ()
        self.assertEqual(bts.parse_wire(block), SWAPPED)

    def _refused(self, mutate):
        block = json.loads(json.dumps(self.block))
        mutate(block)
        with self.assertRaises(ValueError):
            bts.parse_wire(block)

    def test_refusals(self):
        self._refused(lambda b: b.update(version=2))
        self._refused(lambda b: b["garages"].pop("pinstripe"))
        self._refused(lambda b: b["garages"].update(oxide=b["garages"]["pinstripe"]))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(location=35011101))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(track=110))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(track="3"))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(opponent="crash"))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(attack="composed"))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(ai_profile="hard"))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(packages=["x"]))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(extra=1))
        self._refused(lambda b: b["garages"]["ripper_roo"].update(home_track=3))


if __name__ == "__main__":
    unittest.main()
