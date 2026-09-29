"""Relic Race perfect checks (#49): option, creation, rule, wire, UT restore.

The 18 names and codes were frozen in 0.2.0 (35012400.., RELIC_TRACKS order);
this feature only decides which of them a seed creates. Covers:

* option off (default and explicit false): nothing created, no block, no RNG
  or item-pool change;
* option on: all 18 created, pool balanced with filler only, exact
  LevelID -> [code] wire block;
* the logic rule: the track's Sapphire Time Trial rule (race entry), with no
  Gold/Platinum term, plus the USF crate term on every track at every logic
  difficulty under Progressive Boost (ruling 2026-09-29), bound to the pad's
  racer, trial tracks included;
* Cortex Vortex: the dropped destination's check is absent, no Cortex Vortex
  perfect is created, 17 wire rows;
* Universal Tracker: regeneration from the real wire reproduces the same
  locations and the same block, and malformed wires are refused;
* custom tracks: capability enumeration only, creation stays off, reserved
  codes are not in the datapackage.
"""
import json
import unittest
from collections import Counter

from BaseClasses import CollectionState, ItemClassification
from NetUtils import convert_to_base_types
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from .. import relic_perfect as rp
from ..Locations import CTR_LOCATION_IDS
from ..custom_tracks import BABY_T_PARK_CURRENT
from ..relic_perfect import RELIC_PERFECT_CLASS, RELIC_TRACKS
from ..progressive_capability import ROSTER, boost_item_name
from ..usf_finish import (RELIC_PERFECT_BOOST_OVERRIDES, USF_BOOST_COUNT,
                          relic_perfect_boost_min)

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
NAMES = tuple(RELIC_PERFECT_CLASS.location_name(t) for t in RELIC_TRACKS)

#: Engine LevelIDs of the 18 relic tracks, spelled out independently of the
#: code under test (warp_pad_ids.json / native LevelID enum).
LEVEL_IDS = {
    "Crash Cove": 3, "Roo's Tubes": 6, "Mystery Caves": 9,
    "Sewer Speedway": 8, "Coco Park": 14, "Tiger Temple": 4,
    "Papu's Pyramid": 5, "Dingo Canyon": 0, "Blizzard Bluff": 2,
    "Dragon Mines": 1, "Polar Pass": 12, "Tiny Arena": 15,
    "Hot Air Skyway": 7, "Cortex Castle": 10, "N. Gin Labs": 11,
    "Oxide Station": 13, "Slide Coliseum": 16, "Turbo Track": 17,
}


def _build(seed=1, dropped=None, steps=STEPS, **options):
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    if dropped is not None:
        mw.worlds[PLAYER].options._cortex_vortex_dropped = dropped
    for step in steps:
        call_all(mw, step)
    return mw


def _names(mw):
    return {loc.name for loc in mw.get_locations(PLAYER)}


def _wire(mw):
    return json.loads(json.dumps(convert_to_base_types(
        mw.worlds[PLAYER].fill_slot_data())))


def _ut_regen(wire, seed=99):
    mw = setup_multiworld(ctrAPWorld, (), seed=seed)
    mw.re_gen_passthrough = {ctrAPWorld.game: wire}
    mw.generation_is_fake = True
    for step in STEPS:
        call_all(mw, step)
    return mw


def _state(mw, boost=0, character_boosts=()):
    """Every item at a generous count except the boost chain."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item == BOOST or item.startswith(f"{BOOST} ("):
            continue
        state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    for character, count in character_boosts:
        state.add_item(boost_item_name(character), PLAYER, count)
    return state


def _pool(mw):
    return Counter((i.name, i.classification) for i in mw.itempool
                   if i.player == PLAYER)


class TestFrozenIdentity(unittest.TestCase):
    def test_eighteen_registered_names_keep_their_codes(self):
        for index, track in enumerate(RELIC_TRACKS):
            name = RELIC_PERFECT_CLASS.location_name(track)
            self.assertEqual(CTR_LOCATION_IDS[name], 35012400 + index)

    def test_level_ids_match_the_engine(self):
        self.assertEqual(rp.track_level_ids(), LEVEL_IDS)


class TestOptionOff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = _build(seed=11)
        cls.explicit = _build(seed=11, relic_perfect_checks=False)

    def test_nothing_is_created(self):
        self.assertFalse(_names(self.default) & set(NAMES))
        self.assertFalse(RELIC_PERFECT_CLASS.is_enabled(
            self.default.worlds[PLAYER].options))

    def test_wire_has_the_false_scalar_and_no_block(self):
        wire = _wire(self.default)
        self.assertIs(wire["ctr_options"]["relic_perfect_checks"], False)
        self.assertNotIn("relic_perfect_checks", wire)

    def test_absent_and_explicit_false_build_the_same_seed(self):
        a, b = self.default, self.explicit
        self.assertEqual(_names(a), _names(b))
        self.assertEqual(_pool(a), _pool(b))
        self.assertEqual(a.worlds[PLAYER].random.getstate(),
                         b.worlds[PLAYER].random.getstate())
        self.assertEqual(_wire(a), _wire(b))


class TestOptionOn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.off = _build(seed=5)
        cls.on = _build(seed=5, relic_perfect_checks=True)

    def test_all_eighteen_are_created_in_their_own_track_region(self):
        for track in RELIC_TRACKS:
            loc = self.on.get_location(
                RELIC_PERFECT_CLASS.location_name(track), PLAYER)
            self.assertEqual(loc.parent_region.name, track)
            self.assertEqual(loc.address, RELIC_PERFECT_CLASS.code_for(track))

    def test_only_the_perfect_locations_are_added(self):
        self.assertEqual(_names(self.on) - _names(self.off), set(NAMES))
        self.assertEqual(_names(self.off) - _names(self.on), set())

    def test_the_pool_grows_by_eighteen_filler_items(self):
        before, after = _pool(self.off), _pool(self.on)
        self.assertFalse(before - after, "an item left the pool")
        added = after - before
        self.assertEqual(sum(added.values()), 18)
        for (_name, classification) in added:
            self.assertEqual(classification & ItemClassification.progression, 0)
        pool = [i for i in self.on.itempool if i.player == PLAYER]
        self.assertEqual(len(pool),
                         len(self.on.get_unfilled_locations(PLAYER)))

    def test_wire_block_maps_level_id_to_frozen_code(self):
        wire = _wire(self.on)
        self.assertIs(wire["ctr_options"]["relic_perfect_checks"], True)
        block = wire["relic_perfect_checks"]
        self.assertIs(block["enabled"], True)
        self.assertEqual(block["locations"], {
            str(LEVEL_IDS[track]): [35012400 + index]
            for index, track in enumerate(RELIC_TRACKS)})


class TestRule(unittest.TestCase):
    """The perfect check has the Relic Race's entry rule: exactly what the
    Sapphire Time Trial gets, plus the USF crate term on every track
    (ruling 2026-09-29)."""

    @classmethod
    def setUpClass(cls):
        cls.mw = _build(seed=3, relic_perfect_checks=True,
                        progressive_boost="shared_global",
                        warppad_unlock_requirements="randomized",
                        two_stage_density="full")

    def _pairs(self):
        for track in RELIC_TRACKS:
            sapphire = f"{track}: Sapphire Time Trial"
            if sapphire not in _names(self.mw):
                continue
            yield (track,
                   self.mw.get_location(
                       RELIC_PERFECT_CLASS.location_name(track), PLAYER),
                   self.mw.get_location(sapphire, PLAYER))

    def test_matches_sapphire_on_many_states(self):
        states = [CollectionState(self.mw)]
        for boost in (0, 1, USF_BOOST_COUNT):
            states.append(_state(self.mw, boost))
        # Partial states: grow a sweep one progression item at a time.
        items = sorted((i for i in self.mw.itempool
                        if i.player == PLAYER and i.advancement),
                       key=lambda i: i.name)
        partial = CollectionState(self.mw)
        for index, item in enumerate(items):
            partial.collect(item, True)
            if index % 7 == 0:
                states.append(partial.copy())
        checked = 0
        for track, perfect, sapphire in self._pairs():
            for state in states:
                want = sapphire.can_reach(state)
                extra = relic_perfect_boost_min(track)
                self.assertEqual(extra, USF_BOOST_COUNT, track)
                want = want and state.has(BOOST, PLAYER, extra)
                self.assertEqual(perfect.can_reach(state), want,
                                 f"{track} disagrees with its Sapphire rule")
                checked += 1
        self.assertGreater(checked, 100)

    def test_no_gold_or_platinum_term(self):
        """Everything plus USF: the perfect check needs nothing beyond its
        race and USF, even where a relic tier would ask for more."""
        state = _state(self.mw, USF_BOOST_COUNT)
        for track, perfect, sapphire in self._pairs():
            self.assertEqual(perfect.can_reach(state), sapphire.can_reach(state),
                             track)

    def test_every_track_needs_usf(self):
        one = _state(self.mw, USF_BOOST_COUNT - 1)
        two = _state(self.mw, USF_BOOST_COUNT)
        for track, perfect, sapphire in self._pairs():
            with self.subTest(track=track):
                self.assertFalse(perfect.can_reach(one))
                self.assertTrue(perfect.can_reach(two))

    def test_boost_off_makes_the_term_vacuous(self):
        mw = _build(seed=3, relic_perfect_checks=True, progressive_boost="off")
        state = _state(mw, 0)
        for track in RELIC_TRACKS:
            with self.subTest(track=track):
                self.assertTrue(mw.get_location(
                    RELIC_PERFECT_CLASS.location_name(track), PLAYER
                ).can_reach(state))


class TestUsfRuling20260929(unittest.TestCase):
    """Ruling 2026-09-29 (0.2.2 feedback): a Hard-logic player had Blizzard
    Bluff's perfect in logic with no boost, but a time crate in its lake
    shortcut needs boost. Every perfect now needs USF at every difficulty."""

    TRACK = "Blizzard Bluff"

    def test_default_is_usf_with_no_override(self):
        self.assertEqual(RELIC_PERFECT_BOOST_OVERRIDES, {})
        for track in RELIC_TRACKS:
            self.assertEqual(relic_perfect_boost_min(track), USF_BOOST_COUNT)

    def test_blizzard_bluff_needs_usf_at_every_difficulty(self):
        name = RELIC_PERFECT_CLASS.location_name(self.TRACK)
        for difficulty in ("easy", "medium", "hard"):
            mw = _build(seed=3, relic_perfect_checks=True,
                        progressive_boost="shared_global",
                        logic_difficulty=difficulty)
            loc = mw.get_location(name, PLAYER)
            for boost in range(USF_BOOST_COUNT):
                with self.subTest(difficulty=difficulty, boost=boost):
                    self.assertFalse(loc.can_reach(_state(mw, boost)))
            with self.subTest(difficulty=difficulty, boost=USF_BOOST_COUNT):
                self.assertTrue(loc.can_reach(_state(mw, USF_BOOST_COUNT)))

    def test_blizzard_bluff_is_free_with_boost_off(self):
        for difficulty in ("easy", "medium", "hard"):
            mw = _build(seed=3, relic_perfect_checks=True,
                        progressive_boost="off", logic_difficulty=difficulty)
            with self.subTest(difficulty=difficulty):
                self.assertTrue(mw.get_location(
                    RELIC_PERFECT_CLASS.location_name(self.TRACK), PLAYER
                ).can_reach(_state(mw, 0)))

    def test_trial_tracks_need_usf_with_and_without_a_trophy_race(self):
        for races in ("off", "trophy_and_ctr_challenge"):
            mw = _build(seed=3, relic_perfect_checks=True,
                        progressive_boost="shared_global",
                        logic_difficulty="hard",
                        slide_coliseum_races=races, turbo_track_races=races)
            names = _names(mw)
            for track in ("Slide Coliseum", "Turbo Track"):
                with self.subTest(races=races, track=track):
                    self.assertEqual(
                        f"{track}: Trophy Race" in names, races != "off")
                    loc = mw.get_location(
                        RELIC_PERFECT_CLASS.location_name(track), PLAYER)
                    self.assertFalse(loc.can_reach(
                        _state(mw, USF_BOOST_COUNT - 1)))
                    self.assertTrue(loc.can_reach(_state(mw, USF_BOOST_COUNT)))

    def test_per_character_mode_reads_a_driveable_racer(self):
        mw = _build(seed=3, relic_perfect_checks=True,
                    progressive_boost="per_character", logic_difficulty="hard",
                    character_unlocks=False)
        racer = mw.worlds[PLAYER].ctr_starting_character
        loc = mw.get_location(
            RELIC_PERFECT_CLASS.location_name(self.TRACK), PLAYER)
        self.assertFalse(loc.can_reach(_state(
            mw, character_boosts=((racer, USF_BOOST_COUNT - 1),))))
        self.assertTrue(loc.can_reach(_state(
            mw, character_boosts=((racer, USF_BOOST_COUNT),))))

    def test_a_locked_pad_binds_its_racer(self):
        from ..progressive_capability import track_required_character
        mw = track = required = None
        for seed in range(1, 33):
            candidate = _build(seed=seed, relic_perfect_checks=True,
                               progressive_boost="per_character",
                               logic_difficulty="hard", racer_locked_pads=True)
            world = candidate.worlds[PLAYER]
            hits = [(t, track_required_character(world, t))
                    for t in RELIC_TRACKS
                    if RELIC_PERFECT_CLASS.location_name(t) in _names(candidate)]
            hits = [(t, r) for t, r in hits if r]
            if hits:
                mw, (track, required) = candidate, hits[0]
                break
        self.assertIsNotNone(mw, "fixture seeds produced no locked relic track")
        wrong = next(racer for racer in ROSTER if racer != required)
        loc = mw.get_location(RELIC_PERFECT_CLASS.location_name(track), PLAYER)
        self.assertFalse(loc.can_reach(_state(
            mw, character_boosts=((wrong, 3),))))
        self.assertTrue(loc.can_reach(_state(
            mw, character_boosts=((required, 3),))))


class TestCortexVortex(unittest.TestCase):
    CRASH_COVE = 3

    @classmethod
    def setUpClass(cls):
        cls.mw = _build(seed=2, dropped=cls.CRASH_COVE,
                        relic_perfect_checks=True, cortex_vortex_track=True)

    def test_dropped_track_has_no_perfect_and_cortex_vortex_none(self):
        names = _names(self.mw)
        self.assertNotIn("Crash Cove: Relic Race Perfect", names)
        self.assertNotIn("Cortex Vortex: Relic Race Perfect", names)
        self.assertEqual(len(names & set(NAMES)), 17)

    def test_wire_has_seventeen_rows_without_the_dropped_level(self):
        block = _wire(self.mw)["relic_perfect_checks"]
        self.assertEqual(len(block["locations"]), 17)
        self.assertNotIn(str(self.CRASH_COVE), block["locations"])

    def test_ut_regen_restores_the_same_seventeen(self):
        wire = _wire(self.mw)
        ut = _ut_regen(wire)
        self.assertEqual(_names(ut) & set(NAMES), _names(self.mw) & set(NAMES))
        self.assertEqual(_wire(ut)["relic_perfect_checks"],
                         wire["relic_perfect_checks"])


class TestUniversalTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.on_wire = _wire(_build(seed=7, relic_perfect_checks=True))
        cls.off_wire = _wire(_build(seed=7))

    def test_on_regenerates_all_eighteen_and_the_same_block(self):
        ut = _ut_regen(self.on_wire)
        self.assertEqual(_names(ut) & set(NAMES), set(NAMES))
        again = _wire(ut)
        self.assertEqual(again["relic_perfect_checks"],
                         self.on_wire["relic_perfect_checks"])
        self.assertIs(again["ctr_options"]["relic_perfect_checks"], True)

    def test_multidata_tuples_are_the_same_wire(self):
        """A room's multidata hands the tracker tuples where a JSON round trip
        has lists (seen in the check-ut fuzz arm)."""
        wire = json.loads(json.dumps(self.on_wire))
        wire["relic_perfect_checks"]["locations"] = {
            k: tuple(v) for k, v in
            wire["relic_perfect_checks"]["locations"].items()}
        ut = _ut_regen(wire)
        self.assertEqual(_names(ut) & set(NAMES), set(NAMES))

    def test_string_code_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        wire["relic_perfect_checks"]["locations"]["3"] = ["35012400"]
        self._refused(wire)

    def test_off_and_pre_feature_wires_regenerate_none(self):
        self.assertFalse(_names(_ut_regen(self.off_wire)) & set(NAMES))
        legacy = json.loads(json.dumps(self.off_wire))
        del legacy["ctr_options"]["relic_perfect_checks"]
        self.assertFalse(_names(_ut_regen(legacy)) & set(NAMES))

    def _refused(self, wire):
        with self.assertRaises(OptionError):
            _ut_regen(wire)

    def test_wrong_code_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        wire["relic_perfect_checks"]["locations"]["3"] = [35012401]
        self._refused(wire)

    def test_missing_row_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        del wire["relic_perfect_checks"]["locations"]["11"]
        self._refused(wire)

    def test_extra_row_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        wire["relic_perfect_checks"]["locations"]["03"] = [35012400]
        self._refused(wire)

    def test_scalar_without_block_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        del wire["relic_perfect_checks"]
        self._refused(wire)

    def test_block_on_an_off_seed_is_refused(self):
        wire = json.loads(json.dumps(self.off_wire))
        wire["relic_perfect_checks"] = self.on_wire["relic_perfect_checks"]
        self._refused(wire)

    def test_non_boolean_scalar_is_refused(self):
        wire = json.loads(json.dumps(self.on_wire))
        wire["ctr_options"]["relic_perfect_checks"] = 1
        self._refused(wire)


class TestCustomTrackHooks(unittest.TestCase):
    def _tracks(self, relic_crates):
        entry = dict(BABY_T_PARK_CURRENT, slot=4,
                     flags=dict(BABY_T_PARK_CURRENT["flags"],
                                relic_crates=relic_crates))
        return {"baby-t-park": entry}

    def test_capability_enumeration_reads_relic_crates(self):
        self.assertEqual(rp.relic_capable_custom_slots(self._tracks(True)), [4])
        self.assertEqual(rp.relic_capable_custom_slots(self._tracks(False)), [])
        self.assertEqual(rp.relic_capable_custom_slots({}), [])

    def test_creation_stays_disabled(self):
        self.assertFalse(rp.CUSTOM_PERFECT_CREATION_ENABLED)
        self.assertEqual(rp.created_custom_perfect_slots(self._tracks(True)), [])

    def test_reserved_codes_are_not_in_the_datapackage(self):
        self.assertEqual(rp.custom_perfect_reserved_code(1), 35024000)
        self.assertEqual(rp.custom_perfect_reserved_code(132), 35024131)
        registered = set(CTR_LOCATION_IDS.values())
        for slot in (1, 4, 132):
            self.assertNotIn(rp.custom_perfect_reserved_code(slot), registered)
        self.assertNotIn(35026005, registered)  # Cortex Vortex perfect

    def test_custom_seed_with_option_on_creates_only_retail_perfects(self):
        mw = _build(seed=4, relic_perfect_checks=True,
                    custom_tracks={"baby-t-park": dict(BABY_T_PARK_CURRENT)})
        names = _names(mw)
        self.assertEqual(names & set(NAMES), set(NAMES))
        self.assertFalse({n for n in names if n.startswith("Custom Track")
                          and n.endswith("Relic Race Perfect")})
