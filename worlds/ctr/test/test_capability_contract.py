"""Ruling-to-code parity for CTR capability logic.

The field matrix is promoted into ``capability_contract`` once a row is ruled.
These tests exercise every confirmed boundary and the complete difficulty group,
so a green release cannot silently omit a ruled track.
"""
import unittest

from BaseClasses import CollectionState
from . import setup_multiworld

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


def _track_options(track):
    """Options that create `track`'s Trophy Race. A record in
    OPTIONAL_TROPHY_TRACKS (the Cortex Vortex pad track) only has one with its
    option on, and so does each trial track (#203); every retail record keeps
    the default seed."""
    from ..destinations import TRIAL_TRACKS
    if track in OPTIONAL_TROPHY_TRACKS:
        return {"cortex_vortex_track": True}
    if track in TRIAL_TRACKS:
        return {"slide_coliseum_races": "trophy_race",
                "turbo_track_races": "trophy_race"}
    return {}


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
        from ..destinations import TRIAL_TRACKS
        from ..usf_finish import ALL_USF_FINISH_TRACKS
        ungated = (set(TROPHY_TRACKS) | set(TRIAL_TRACKS)
                   | set(OPTIONAL_TROPHY_TRACKS)) - difficulty_gated_tracks() \
            - set(ALL_USF_FINISH_TRACKS)
        self.assertEqual(ungated, set(),
                         f"trophy races with no capability gate at all: {sorted(ungated)}")


    def test_trial_track_checks_inherit_the_ruled_requirement(self):
        """The trial tracks' Time Trials, letters and easy rungs reach their
        track through the Trophy Race (or, for the rungs, the easy gate), so
        each must now need boost or three weapon families like a retail
        ruled track."""
        from ..destinations import TRIAL_TRACKS
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
