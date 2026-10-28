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
from ..Regions import BOSS_WUMPA_TRACKS

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


class TestOptionOff(unittest.TestCase):

    def test_no_block_scalar_false_and_retail_venues(self):
        mw = _build()
        wire = _wire(mw)
        self.assertIs(wire["ctr_options"]["boss_track_shuffle"], False)
        self.assertNotIn("boss_encounters", wire)
        self.assertEqual(bts.garage_tracks(mw.worlds[PLAYER].options), BOSS_WUMPA_TRACKS)

    def test_off_draws_nothing(self):
        mw = setup_multiworld(ctrAPWorld, (), seed=3, options={})
        world = mw.worlds[PLAYER]
        world.random = mock.Mock(wraps=world.random)
        bts.draw(world)
        self.assertEqual(world.random.method_calls, [])

    def test_filters_without_the_switch_are_ignored(self):
        base = _wire(_build(seed=4))
        for name in ("boss_track_allowlist", "boss_track_blocklist"):
            with self.subTest(option=name):
                mw = _build(seed=4, **{name: ["Crash Cove"]})
                self.assertEqual(_wire(mw), base)
                label = name.replace("_", " ").title() + " (Boss Track Shuffle off)"
                self.assertIn(label, mw.worlds[PLAYER].options._ctr_notices["ignored"])

    def test_content_plan_path_needs_its_garages(self):
        # A content plan with empty garages refuses the switch; with boss
        # garages (#133 PR 6) the plan draws the venues (test_content_bosses).
        from Options import OptionError
        from .test_content_plan import make_world, profile_options
        from .test_content_bosses import boss_options
        options = profile_options()
        options["boss_track_shuffle"] = True
        with self.assertRaisesRegex(OptionError, "boss_track_shuffle needs content_pool.bosses.enabled"):
            make_world(options)
        world = make_world(boss_options(boss_track_shuffle=True))
        self.assertTrue(world.ctr_content_plan["bosses"]["track_shuffle"])


class TestDraw(unittest.TestCase):

    def test_four_distinct_certified_venues_on_the_wire(self):
        for seed in range(1, 9):
            with self.subTest(seed=seed):
                mw = _build(seed=seed, boss_track_shuffle=True)
                wire = _wire(mw)
                self.assertIs(wire["ctr_options"]["boss_track_shuffle"], True)
                block = wire["boss_encounters"]
                self.assertEqual(block["version"], 1)
                self.assertEqual(list(block["garages"]),
                                 ["ripper_roo", "papu_papu", "komodo_joe", "pinstripe"])
                tracks = [row["track"] for row in block["garages"].values()]
                self.assertEqual(len(set(tracks)), 4)
                for key, _r, code, home in bts.GARAGES:
                    row = block["garages"][key]
                    self.assertEqual(row, {
                        "location": code, "home_track": bts.VENUE_LEVEL_IDS[home],
                        "track": row["track"], "opponent": key, "ai_profile": "retail",
                        "attack": "inherited", "packages": []})
                self.assertEqual(bts.parse_wire(block),
                                 mw.worlds[PLAYER].options._boss_track_venues)

    def test_deterministic_per_seed_and_varies_across_seeds(self):
        first = _wire(_build(seed=11, boss_track_shuffle=True))["boss_encounters"]
        again = _wire(_build(seed=11, boss_track_shuffle=True))["boss_encounters"]
        self.assertEqual(first, again)
        draws = {json.dumps(_wire(_build(seed=s, boss_track_shuffle=True))["boss_encounters"])
                 for s in range(20, 26)}
        self.assertGreater(len(draws), 1)

    def test_allowlist_of_exactly_four_uses_all_four(self):
        allowed = ["Crash Cove", "Coco Park", "Polar Pass", "N. Gin Labs"]
        mw = _build(seed=5, boss_track_shuffle=True, boss_track_allowlist=allowed)
        self.assertEqual(sorted(mw.worlds[PLAYER].options._boss_track_venues.values()),
                         sorted(allowed))

    def test_blocklist_applies_after_allowlist(self):
        allowed = ["Crash Cove", "Coco Park", "Polar Pass", "N. Gin Labs", "Tiny Arena"]
        mw = _build(seed=5, boss_track_shuffle=True, boss_track_allowlist=allowed,
                    boss_track_blocklist=["Tiny Arena"])
        self.assertEqual(sorted(mw.worlds[PLAYER].options._boss_track_venues.values()),
                         sorted(allowed[:4]))

    def test_impossible_four_way_matching_fails_instead_of_repeating(self):
        with self.assertRaises(OptionError):
            _build(boss_track_shuffle=True,
                   boss_track_allowlist=["Crash Cove", "Coco Park", "Polar Pass"])

    def test_empty_pool_names_the_garage(self):
        with self.assertRaises(OptionError) as caught:
            _build(boss_track_shuffle=True, boss_track_allowlist=["Crash Cove"],
                   boss_track_blocklist=["Crash Cove"])
        self.assertIn("Ripper Roo Garage", str(caught.exception))

    def test_venues_never_repeat(self):
        # Decision 7 (2026-10-28): the repeats-allowed option is gone.
        with self.assertRaises(OptionError):
            _build(boss_track_shuffle=True, boss_track_allowlist=["Crash Cove"])

    def test_ordinary_pad_use_never_counts_as_a_repeat(self):
        # Crash Cove keeps its own pad and Trophy Race while Roo races there.
        mw = _build(boss_track_shuffle=True, venues={
            "ripper_roo": "Crash Cove", "papu_papu": "Papu's Pyramid",
            "komodo_joe": "Dragon Mines", "pinstripe": "Hot Air Skyway"})
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertIn("Crash Cove: Trophy Race", names)


SWAPPED = {"ripper_roo": "Cortex Castle", "papu_papu": "Crash Cove",
           "komodo_joe": "Turbo Track", "pinstripe": "Coco Park"}


class TestLogicFollowsTheVenue(unittest.TestCase):

    def test_boss_checks_and_events_keep_their_names_and_codes(self):
        mw = _build(boss_track_shuffle=True, venues=SWAPPED)
        for key, region, code, _home in bts.GARAGES:
            loc = mw.get_location(f"{region}: Boss Race", PLAYER)
            self.assertEqual(loc.address, code)
            self.assertEqual(loc.parent_region.name, region)

    def test_finish_term_moves_with_the_venue(self):
        # Retail: Pinstripe's Hot Air Skyway needs USF (2 boosts), Roo's Tubes
        # only the floor. Swapped: Roo on Cortex Castle needs USF, Pinstripe
        # on Coco Park does not.
        opts = dict(progressive_boost="shared_global", boss_track_shuffle=True)
        mw = _build(venues=SWAPPED, **opts)
        one = _everything(mw, 1)
        two = _everything(mw, 2)
        roo, pin = "Ripper Roo Garage: Boss Race", "Pinstripe Garage: Boss Race"
        self.assertFalse(one.can_reach(roo, "Location", PLAYER))
        self.assertTrue(two.can_reach(roo, "Location", PLAYER))
        self.assertTrue(one.can_reach(pin, "Location", PLAYER))
        retail = _build(progressive_boost="shared_global")
        self.assertTrue(_everything(retail, 1).can_reach(roo, "Location", PLAYER))
        self.assertFalse(_everything(retail, 1).can_reach(pin, "Location", PLAYER))

    def test_personal_win_event_takes_the_same_rule(self):
        mw = _build(venues=SWAPPED, progressive_boost="shared_global",
                    boss_track_shuffle=True, bosses_required_goal=4)
        self.assertFalse(_everything(mw, 1).can_reach(
            "Ripper Roo Boss Race Won", "Location", PLAYER))
        self.assertTrue(_everything(mw, 2).can_reach(
            "Ripper Roo Boss Race Won", "Location", PLAYER))

    def test_wumpa_route_moves_with_the_venue(self):
        mw = _build(boss_track_shuffle=True, venues=SWAPPED,
                    turbo_track_races="trophy_race")
        self.assertIn("Ripper Roo Garage", _sources(mw, "Cortex Castle: Wumpa"))
        self.assertNotIn("Ripper Roo Garage", _sources(mw, "Roo's Tubes: Wumpa"))
        self.assertIn("Papu Papu Garage", _sources(mw, "Crash Cove: Wumpa"))
        self.assertIn("Pinstripe Garage", _sources(mw, "Coco Park: Wumpa"))
        self.assertNotIn("Pinstripe Garage", _sources(mw, "Hot Air Skyway: Wumpa"))
        self.assertEqual(_sources(mw, "Oxide Station: Wumpa") & {"N. Oxide Garage"},
                         {"N. Oxide Garage"})

    def test_garage_doors_keep_their_trophy_counts(self):
        mw = _build(boss_track_shuffle=True, venues=SWAPPED)
        base = _build()
        self.assertEqual(_wire(mw)["boss_garage_req"], _wire(base)["boss_garage_req"])


class TestDroppedDestination(unittest.TestCase):
    """`cortex_vortex_track` drops a pad; a boss race still runs on its track
    only when a garage's venue is that track (2026-09-18 ruling, now per
    seed)."""

    def _drop(self, dropped_lid, venues):
        options = {"cortex_vortex_track": True, "randomize_gem_cup_tracks": True,
                   "boss_track_shuffle": True, "wumpa_check": "per_track"}
        mw = setup_multiworld(ctrAPWorld, (), seed=2, options=options)
        mw.worlds[PLAYER].options._cortex_vortex_dropped = dropped_lid
        mw.worlds[PLAYER].options._boss_track_venues = dict(venues)
        for step in STEPS:
            call_all(mw, step)
        return mw

    def test_retail_boss_track_loses_its_check_when_its_boss_moved(self):
        mw = self._drop(6, SWAPPED)  # Roo's Tubes, Roo now on Cortex Castle
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertNotIn("Roo's Tubes: Reach 10 Wumpa", names)

    def test_drawn_venue_keeps_its_check_through_the_garage(self):
        mw = self._drop(3, SWAPPED)  # Crash Cove, Papu races there
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertIn("Crash Cove: Reach 10 Wumpa", names)
        self.assertEqual(_sources(mw, "Crash Cove: Wumpa"), {"Papu Papu Garage"})


class TestUniversalTracker(unittest.TestCase):

    def _ut(self, passthrough, seed=99, **options):
        mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
        mw.re_gen_passthrough = {"Crash Team Racing": passthrough}
        for step in STEPS:
            call_all(mw, step)
        return mw

    def test_restores_the_seed_draw_without_redrawing(self):
        src = _build(seed=13, boss_track_shuffle=True)
        wire = _wire(src)
        mw = self._ut(wire)
        self.assertEqual(mw.worlds[PLAYER].options._boss_track_venues,
                         src.worlds[PLAYER].options._boss_track_venues)
        self.assertEqual(_wire(mw)["boss_encounters"], wire["boss_encounters"])

    def test_off_seed_restores_off_even_from_an_on_yaml(self):
        wire = _wire(_build(seed=13))
        mw = self._ut(wire, boss_track_shuffle=True,
                      boss_track_allowlist=["Crash Cove"])
        self.assertFalse(mw.worlds[PLAYER].options.boss_track_shuffle.value)
        self.assertNotIn("boss_encounters", _wire(mw))

    def test_scalar_and_block_must_agree(self):
        wire = _wire(_build(seed=13, boss_track_shuffle=True))
        wire["ctr_options"]["boss_track_shuffle"] = False
        with self.assertRaises(ValueError):
            self._ut(wire)


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
