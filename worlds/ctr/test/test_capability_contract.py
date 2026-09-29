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
    OPTIONAL_TROPHY_TRACKS,
    EASY_TROPHY_GROUP,
    RULED_TROPHY_GROUP,
    STATUS_CONFIRMED,
    STATUS_RULED,
    difficulty_gated_tracks,
    held_first_gated_tracks,
    unconditional_usf_finish_tracks,
    usf_or_hard_finish_tracks,
)
from ..itemsanity import DIFFICULTY_WEAPON_FAMILY_MIN, ITEM_NAMES
from ..item_boxes import BOX_RULES, ITEM_BOX_CLASS
from ..podium import created_rung_keys_from_options, location_name
from ..progressive_capability import (ROSTER, boost_item_name,
                                      track_required_character)
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


def _track_options(track):
    """Options that create `track`'s Trophy Race. A record in
    OPTIONAL_TROPHY_TRACKS (the Cortex Vortex pad track) only has one with its
    option on, and so does each trial track (#203); every retail record keeps
    the default seed."""
    from ..trial_trophy import TRIAL_TRACKS
    if track in OPTIONAL_TROPHY_TRACKS:
        return {"cortex_vortex_track": True}
    if track in TRIAL_TRACKS:
        return {"slide_coliseum_races": "trophy_race",
                "turbo_track_races": "trophy_race"}
    return {}


class TestConfirmedFinishBoundaries(unittest.TestCase):
    def test_zero_one_two_copy_boundary_for_every_confirmed_finish(self):
        for record in CONFIRMED_FINISH_CAPABILITIES:
            if record.hard_shortcut_escape:
                options = {"shortcut_knowledge": "medium"}
            else:
                options = {}
            options.update(_track_options(record.track))
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
        for record in CONFIRMED_FINISH_CAPABILITIES:
            mw = _build(progressive_boost="shared_global",
                        shortcut_knowledge="medium",
                        **_track_options(record.track))
            # One boost clears the every-track Held 1st floor (ruling
            # 2026-09-28), so what is left is the record's own USF gate.
            first_rank = _state(mw, boost=1)
            actual = first_rank.can_reach(
                location_name(record.track, "held_1st"), "Location", PLAYER)
            with self.subTest(track=record.track):
                self.assertEqual(actual,
                                 record.track not in held_first_gated_tracks())


class TestRacerLockResolution(unittest.TestCase):
    """The lock a capability rule reads must belong to the pad that LOADS the
    track, not the pad that happens to share its name.

    `ctr_racer_locks` is keyed by pad exit name, and create_regions keeps each
    exit's physical name while retargeting it to a shuffled destination, so
    under shuffle those are two different pads. This went uncaught because every
    earlier fixture derived its expected racer from the same wrong key the code
    used, so expectation and bug agreed.

    The expectation here is therefore rebuilt from `warp_pad_map` and
    `warp_pad_ids` directly -- the seed's own destination wiring -- and never
    from the helper under test.
    """

    @staticmethod
    def _expected_locks(world):
        """{track -> racer} derived only from the seed's pad wiring."""
        id_to_track = {
            meta["level_id"]: pad[: -len(" Warp Pad")]
            for pad, meta in getattr(world, "warp_pad_ids", {}).items()
            if pad.endswith(" Warp Pad")
        }
        locks = world.ctr_racer_locks or {}
        out = {}
        for pad, dest_lid in getattr(world, "warp_pad_map", {}).items():
            if not pad.endswith(" Warp Pad"):
                continue
            dest = id_to_track.get(dest_lid)
            if dest is not None:
                out[dest] = locks.get(pad)
        return out

    def test_resolver_matches_the_seed_wiring_on_shuffled_seeds(self):
        compared = mismatches = 0
        for seed in range(1, 30):
            mw = _build(seed=seed, progressive_boost="per_character",
                        itemsanity=True, racer_locked_pads=True,
                        warp_pad_shuffle_categories=["tracks"])
            w = mw.worlds[PLAYER]
            expected = self._expected_locks(w)
            if not expected or not (w.ctr_racer_locks or {}):
                continue
            for track, racer in expected.items():
                got = track_required_character(w, track)
                compared += 1
                if got != racer:
                    mismatches += 1
                    if mismatches == 1:
                        first = (seed, track, racer, got)
        self.assertGreater(compared, 0, "no shuffled seed produced a pad map")
        self.assertEqual(
            mismatches, 0,
            f"{mismatches}/{compared} tracks resolved to the wrong racer; "
            f"first: seed {first[0]} track {first[1]!r} expected {first[2]!r} "
            f"got {first[3]!r}" if mismatches else "")


class TestCustomSlotRacer(unittest.TestCase):
    def test_custom_slot_takes_the_racer_of_the_pad_it_displaced(self):
        """A custom-track slot has no pad of its own; the displaced cup's pad
        loads it, so that pad's racer lock is the one its capability terms
        must name (the resolver used to return None for it, which lets
        `gate_satisfied` fall through to any driveable racer)."""
        from types import SimpleNamespace
        world = SimpleNamespace(
            ctr_racer_locks={"Purple Cup Warp Pad": "Coco"},
            ctr_pad_by_destination={},
            custom_tracks={"baby-t-park": {"slot": 1,
                                           "replaces": "purple_gem_cup"}})
        self.assertEqual(track_required_character(world, "Custom Track 1"),
                         "Coco")
        self.assertIsNone(track_required_character(world, "Custom Track 2"))


class TestRuledTrophyGroup(unittest.TestCase):
    """The six tracks brought under the difficulty rule by ruling, not measurement.

    Before this they carried no capability requirement at any difficulty, which
    treated "nobody measured it" as "there is no requirement". Adding one can
    only over-restrict, so a wrong ruling costs sphere depth rather than
    stranding progression -- but it still has to actually bind, and nothing
    covered these tracks before because every assertion iterated the easy group.
    """

    def test_every_trophy_track_is_now_gated_by_something(self):
        from ..podium import TROPHY_TRACKS
        from ..trial_trophy import TRIAL_TRACKS
        from ..usf_finish import ALL_USF_FINISH_TRACKS
        ungated = (set(TROPHY_TRACKS) | set(TRIAL_TRACKS)
                   | set(OPTIONAL_TROPHY_TRACKS)) - difficulty_gated_tracks() \
            - set(ALL_USF_FINISH_TRACKS)
        self.assertEqual(ungated, set(),
                         f"trophy races with no capability gate at all: {sorted(ungated)}")

    def test_every_created_trophy_race_needs_a_capability(self):
        """Parity over the Trophy Races a seed actually CREATES, not over a
        hand-kept track list: the 16 retail races, both trial tracks (#203),
        the Cortex Vortex pad track and a custom-track slot, all on at once.

        The trial races were missed because the earlier parity check iterated
        the 16 retail tracks only, so a Trophy Race added through a location
        class could sit in logic with no requirement and nothing would notice.
        Every created one must be unreachable on a bare state at medium and
        reachable once the USF rank is held."""
        from ..custom_tracks import BABY_T_PARK_CURRENT
        import copy
        custom = copy.deepcopy(BABY_T_PARK_CURRENT)
        custom["modes"] = {"ctr_challenge": True}
        for seed in (1, 2, 3):
            mw = _build(seed=seed, progressive_boost="shared_global",
                        itemsanity=True, logic_difficulty="medium",
                        slide_coliseum_races="trophy_and_ctr_challenge",
                        turbo_track_races="trophy_and_ctr_challenge",
                        cortex_vortex_track=True, lettersanity="locations_only",
                        custom_tracks={"baby-t-park": custom})
            races = sorted(loc.name for loc in mw.get_locations(PLAYER)
                           if loc.name.endswith(": Trophy Race"))
            self.assertIn("Custom Track 1: Trophy Race", races)
            self.assertIn("Cortex Vortex: Trophy Race", races)
            self.assertGreaterEqual(len(races), 18)
            bare, usf = _state(mw), _state(mw, boost=2)
            for name in races:
                with self.subTest(seed=seed, race=name):
                    self.assertFalse(bare.can_reach(name, "Location", PLAYER))
                    self.assertTrue(usf.can_reach(name, "Location", PLAYER))

    def test_trial_track_checks_inherit_the_ruled_requirement(self):
        """The trial tracks' Time Trials, letters and easy rungs reach their
        track through the Trophy Race (or, for the rungs, the easy gate), so
        each must now need boost or three weapon families like a retail
        ruled track."""
        from ..trial_trophy import TRIAL_TRACKS
        mw = _build(progressive_boost="shared_global", itemsanity=True,
                    logic_difficulty="easy",
                    slide_coliseum_races="trophy_and_ctr_challenge",
                    turbo_track_races="trophy_and_ctr_challenge",
                    lettersanity="locations_only", podium_held_rungs=True,
                    podium_finish_rungs=True)
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        bare = _state(mw)
        three = _state(mw, held=("Mask", "Warpball", "Bomb"))
        checked = 0
        for track in TRIAL_TRACKS:
            for name in sorted(names):
                if not name.startswith(f"{track}: "):
                    continue
                if name.endswith(("Held 3rd", "Held 5th", "Finish (Any Position)")):
                    continue
                checked += 1
                with self.subTest(location=name):
                    self.assertFalse(bare.can_reach(name, "Location", PLAYER))
                    if not name.endswith(("Gold Time Trial", "Platinum Time Trial",
                                          "CTR Token Challenge")):
                        self.assertTrue(three.can_reach(name, "Location", PLAYER))
        self.assertGreater(checked, 4)

    def test_the_two_groups_keep_their_provenance_apart(self):
        self.assertEqual(EASY_TROPHY_GROUP.status, STATUS_CONFIRMED)
        self.assertEqual(RULED_TROPHY_GROUP.status, STATUS_RULED)
        self.assertFalse(EASY_TROPHY_GROUP.tracks & RULED_TROPHY_GROUP.tracks)
        self.assertEqual(difficulty_gated_tracks(),
                         EASY_TROPHY_GROUP.tracks | RULED_TROPHY_GROUP.tracks)

    def test_ruled_tracks_gate_their_trophy_race_at_medium(self):
        for track in sorted(RULED_TROPHY_GROUP.tracks):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty="medium", **_track_options(track))
            name = f"{track}: Trophy Race"
            with self.subTest(track=track, state="bare"):
                self.assertFalse(_state(mw).can_reach(name, "Location", PLAYER))
            with self.subTest(track=track, state="boost"):
                self.assertTrue(_state(mw, boost=1).can_reach(name, "Location", PLAYER))
            with self.subTest(track=track, state="two weapons"):
                self.assertFalse(_state(mw, held=("Mask", "Warpball")).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=track, state="three weapons"):
                self.assertTrue(
                    _state(mw, held=("Mask", "Warpball", "Bomb")).can_reach(
                        name, "Location", PLAYER))

    def test_ruled_tracks_are_free_at_hard(self):
        for track in sorted(RULED_TROPHY_GROUP.tracks):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty="hard", **_track_options(track))
            with self.subTest(track=track):
                self.assertTrue(_state(mw).can_reach(
                    f"{track}: Trophy Race", "Location", PLAYER))


class TestDifficultyContract(unittest.TestCase):
    def test_slot_data_round_trips_logic_difficulty_for_universal_tracker(self):
        source = _build(logic_difficulty="easy")
        slot_data = source.worlds[PLAYER].fill_slot_data()
        self.assertEqual(slot_data["ctr_options"]["logic_difficulty"], 0)

        tracker = _build(logic_difficulty="hard")
        tracker.worlds[PLAYER]._ut_restore_options(slot_data)
        self.assertEqual(tracker.worlds[PLAYER].options.logic_difficulty.value,
                         0)

    def test_medium_trophy_requires_boost_or_three_useful_families(self):
        """Ruling 2026-09-20: the weapon-family arm moved from two to three.

        Two families is what the alpha2 stream seed handed out in sphere 1, so
        the boundary that matters is two False / three True -- not just "some
        weapons open it".
        """
        self.assertEqual(DIFFICULTY_WEAPON_FAMILY_MIN, 3)
        for track in sorted(difficulty_gated_tracks()):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty="medium", **_track_options(track))
            name = f"{track}: Trophy Race"
            with self.subTest(track=track, state="bare"):
                self.assertFalse(_state(mw).can_reach(name, "Location", PLAYER))
            with self.subTest(track=track, state="boost"):
                self.assertTrue(_state(mw, boost=1).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=track, state="one weapon"):
                self.assertFalse(_state(mw, held=("Mask",)).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=track, state="two weapons"):
                self.assertFalse(_state(mw, held=("Mask", "Warpball")).can_reach(
                    name, "Location", PLAYER))
            with self.subTest(track=track, state="three weapons"):
                self.assertTrue(
                    _state(mw, held=("Mask", "Warpball", "Bomb")).can_reach(
                        name, "Location", PLAYER))

    def test_three_family_arm_counts_families_not_items(self):
        """The x3 variants share a family with their x1 counterpart, so four
        weapon ITEMS spanning two families must still fail. This is the arm
        the stream seed satisfied (`Bomb x3` plus `Missile`)."""
        track = sorted(difficulty_gated_tracks())[0]
        mw = _build(progressive_boost="shared_global", itemsanity=True,
                    logic_difficulty="medium")
        name = f"{track}: Trophy Race"
        self.assertFalse(_state(
            mw, held=("Bomb", "Bomb x3", "Missile", "Missile x3")).can_reach(
                name, "Location", PLAYER))
        self.assertTrue(_state(
            mw, held=("Bomb x3", "Missile", "N. Tropy Clock")).can_reach(
                name, "Location", PLAYER))

    def test_easy_rung_gates_follow_the_same_three_family_term(self):
        """Easy gates Finish on Podium and Held 1st with the SAME term, so the
        raise has to move all three locations together."""
        track = "Crash Cove"
        mw = _build(progressive_boost="shared_global", itemsanity=True,
                    logic_difficulty="easy")
        two = _state(mw, held=("Mask", "Warpball"))
        three = _state(mw, held=("Mask", "Warpball", "Bomb"))
        for name in (f"{track}: Trophy Race",
                     location_name(track, "finish_podium"),
                     location_name(track, "held_1st")):
            with self.subTest(location=name):
                self.assertFalse(two.can_reach(name, "Location", PLAYER))
                self.assertTrue(three.can_reach(name, "Location", PLAYER))

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
            # Ask the production resolver rather than re-deriving the pad
            # name. Deriving it here is what let the destination-shuffle bug
            # pass its own test: the expectation was computed from the same
            # wrong key as the code, so the two agreed while both were wrong.
            matches = [(t, track_required_character(candidate.worlds[PLAYER], t))
                       for t in difficulty_gated_tracks()
                       if track_required_character(candidate.worlds[PLAYER], t)]
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

    def test_locked_track_item_box_gate_binds_its_racer(self):
        """`add_item_box_rules` read the lock as `ctr_racer_locks.get(track)`.

        That map is keyed by pad ENTRANCE name, so the lookup never matched and
        every locked track's box gate fell through to the any-driveable-racer
        arm -- logic believed a box was reachable on a racer the track will not
        let you drive. The whole box-rule suite ran with `racer_locked_pads`
        off, so nothing exercised the locked case. This test turns it on.
        """
        mw = track = slot = required = None
        for seed in range(1, 65):
            candidate = _build(
                seed=seed, progressive_boost="per_character", itemsanity=True,
                box_locations=True, racer_locked_pads=True)
            locks = candidate.worlds[PLAYER].ctr_racer_locks
            created = set(ITEM_BOX_CLASS.created_location_names(
                candidate.worlds[PLAYER].options))
            w = candidate.worlds[PLAYER]
            hits = [(t, s, track_required_character(w, t))
                    for (t, s), (boost_min, _stats) in BOX_RULES.items()
                    if boost_min >= 1 and track_required_character(w, t)
                    and ITEM_BOX_CLASS.location_name(t, s) in created]
            if hits:
                mw = candidate
                track, slot, required = hits[0]
                break
        self.assertIsNotNone(
            mw, "fixture seeds produced no racer-locked boost-gated box slot")
        name = ITEM_BOX_CLASS.location_name(track, slot)
        wrong = next(racer for racer in ROSTER if racer != required)
        self.assertFalse(
            _state(mw, character_boosts=((wrong, 3),)).can_reach(
                name, "Location", PLAYER),
            f"{name} is locked to {required} but cleared on {wrong}")
        self.assertTrue(
            _state(mw, character_boosts=((required, 3),)).can_reach(
                name, "Location", PLAYER))

    def test_medium_leaves_every_placement_rung_at_the_demonstrated_floor(self):
        """`LogicDifficulty.medium` documents the requirement as applying to
        the Trophy Race ONLY, with placement rungs staying at the demonstrated
        floor. The rungs used to reach their own track through
        `can_reach(<track>: Trophy Race)`, so they inherited that requirement
        and the option contradicted itself.

        Asserted across the WHOLE easy group, not one sample track: the earlier
        difficulty coverage only ever checked Crash Cove, whose plain Red cup
        gave the rungs a second reachable branch and hid the inheritance on the
        tracks that have no plain legging cup (Roo's Tubes, Coco Park).
        """
        for track in sorted(difficulty_gated_tracks()):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty="medium", **_track_options(track))
            bare = _state(mw)
            names = {loc.name for loc in mw.get_locations(PLAYER)}
            with self.subTest(track=track, spot="trophy race"):
                self.assertFalse(bare.can_reach(
                    f"{track}: Trophy Race", "Location", PLAYER))
            for rung_key in sorted(created_rung_keys_from_options(
                    mw.worlds[PLAYER].options)):
                name = location_name(track, rung_key)
                if name not in names:
                    continue
                with self.subTest(track=track, rung=rung_key):
                    # Held 1st carries its own every-difficulty floor (ruling
                    # 2026-09-28): one useful weapon family clears it.
                    state = (_state(mw, held=("Mask",))
                             if rung_key == "held_1st" else bare)
                    self.assertTrue(state.can_reach(name, "Location", PLAYER))

    def test_option_vacuity_when_the_boost_pack_is_off(self):
        """With Progressive Boost off every kart has vanilla boost, so the
        rule is vacuous whether Itemsanity is on or off."""
        for itemsanity in (True, False):
            mw = _build(logic_difficulty="easy", progressive_boost="off",
                        itemsanity=itemsanity, podium_held_rungs=True,
                        podium_finish_rungs=True,
                        **_track_options("Slide Coliseum"))
            state = _state(mw)
            for track in difficulty_gated_tracks():
                for name in (f"{track}: Trophy Race",
                             location_name(track, "finish_podium"),
                             location_name(track, "held_1st")):
                    with self.subTest(itemsanity=itemsanity, location=name):
                        self.assertTrue(state.can_reach(
                            name, "Location", PLAYER))


_ITEMSANITY_OFF = dict(progressive_boost="shared_global", itemsanity=False,
                       podium_held_rungs=True, podium_finish_rungs=True,
                       podium_held_fifth_rung=True,
                       podium_any_position_rung=True,
                       slide_coliseum_races="trophy_race",
                       turbo_track_races="trophy_race")


class TestItemsanityOffDifficulty(unittest.TestCase):
    """Ruling 2026-09-27 (#329): with Itemsanity off there is no weapon arm,
    so easy and medium require the first boost rank on the difficulty-gated
    Trophy Races (easy also Finish on Podium and Held 1st). Hard adds
    nothing, and Progressive Boost off keeps the whole rule vacuous."""

    def test_medium_trophy_requires_one_boost(self):
        mw = _build(logic_difficulty="medium", **_ITEMSANITY_OFF)
        bare, one = _state(mw), _state(mw, boost=1)
        for track in sorted(difficulty_gated_tracks()):
            name = f"{track}: Trophy Race"
            with self.subTest(track=track):
                self.assertFalse(bare.can_reach(name, "Location", PLAYER))
                self.assertTrue(one.can_reach(name, "Location", PLAYER))
            # Medium leaves the placement rungs at the demonstrated floor;
            # Held 1st has its own every-difficulty floor (ruling 2026-09-28).
            for key in ("finish_podium", "held_3rd"):
                with self.subTest(track=track, rung=key):
                    self.assertTrue(bare.can_reach(
                        location_name(track, key), "Location", PLAYER))
            with self.subTest(track=track, rung="held_1st"):
                self.assertFalse(bare.can_reach(
                    location_name(track, "held_1st"), "Location", PLAYER))
                self.assertTrue(one.can_reach(
                    location_name(track, "held_1st"), "Location", PLAYER))

    def test_easy_gates_trophy_podium_and_held_first(self):
        mw = _build(logic_difficulty="easy", **_ITEMSANITY_OFF)
        bare, one = _state(mw), _state(mw, boost=1)
        for track in sorted(difficulty_gated_tracks()):
            for key in ("finish_podium", "held_1st"):
                name = location_name(track, key)
                with self.subTest(track=track, rung=key):
                    self.assertFalse(bare.can_reach(name, "Location", PLAYER))
                    self.assertTrue(one.can_reach(name, "Location", PLAYER))
            with self.subTest(track=track, spot="trophy race"):
                self.assertFalse(bare.can_reach(
                    f"{track}: Trophy Race", "Location", PLAYER))
            for key in ("held_3rd", "held_5th", "finish_any"):
                with self.subTest(track=track, free=key):
                    self.assertTrue(bare.can_reach(
                        location_name(track, key), "Location", PLAYER))

    def test_hard_adds_nothing(self):
        mw = _build(logic_difficulty="hard", **_ITEMSANITY_OFF)
        bare, one = _state(mw), _state(mw, boost=1)
        for track in sorted(difficulty_gated_tracks()):
            for name in (f"{track}: Trophy Race",
                         location_name(track, "finish_podium")):
                with self.subTest(location=name):
                    self.assertTrue(bare.can_reach(name, "Location", PLAYER))
            # No Held 1st floor at hard (ruling 2026-09-29): Held 1st opens
            # with its Trophy Race.
            name = location_name(track, "held_1st")
            with self.subTest(location=name):
                self.assertTrue(bare.can_reach(name, "Location", PLAYER))

    def test_custom_trophy_race_takes_the_ruled_requirement(self):
        from ..custom_tracks import BABY_T_PARK_CURRENT
        import copy
        custom = copy.deepcopy(BABY_T_PARK_CURRENT)
        for difficulty, gated in (("easy", True), ("medium", True),
                                  ("hard", False)):
            mw = _build(logic_difficulty=difficulty,
                        custom_tracks={"baby-t-park": custom},
                        **_ITEMSANITY_OFF)
            name = "Custom Track 1: Trophy Race"
            with self.subTest(difficulty=difficulty):
                self.assertEqual(_state(mw).can_reach(name, "Location", PLAYER),
                                 not gated)
                self.assertTrue(_state(mw, boost=1).can_reach(
                    name, "Location", PLAYER))

    def test_universal_tracker_regeneration_matches(self):
        """UT restores logic_difficulty, itemsanity and boost_mode from the
        wire, so a tracker whose own YAML says hard / Itemsanity on / boost
        off rebuilds the same gates as the server."""
        from worlds.AutoWorld import call_all
        for difficulty in ("easy", "medium"):
            source = _build(seed=5, logic_difficulty=difficulty,
                            **_ITEMSANITY_OFF)
            wire = source.worlds[PLAYER].fill_slot_data()
            tracker_options = dict(_ITEMSANITY_OFF, progressive_boost="off",
                                   itemsanity=True, logic_difficulty="hard")
            tracker = setup_multiworld(ctrAPWorld, steps=(), seed=5,
                                       options=tracker_options)
            tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
            tracker.generation_is_fake = True
            for step in STEPS:
                call_all(tracker, step)
            self.assertEqual(
                tracker.worlds[PLAYER].options.logic_difficulty.value,
                source.worlds[PLAYER].options.logic_difficulty.value)
            names = sorted(
                name for track in difficulty_gated_tracks()
                | {"Hot Air Skyway", "Cortex Castle"}
                for name in (f"{track}: Trophy Race",
                             location_name(track, "finish_podium"),
                             location_name(track, "held_1st"),
                             location_name(track, "held_3rd")))
            for boost in (0, 1, 2):
                server, ut = _state(source, boost=boost), _state(tracker, boost=boost)
                for name in names:
                    with self.subTest(difficulty=difficulty, boost=boost,
                                      location=name):
                        self.assertEqual(
                            ut.can_reach(name, "Location", PLAYER),
                            server.can_reach(name, "Location", PLAYER))
