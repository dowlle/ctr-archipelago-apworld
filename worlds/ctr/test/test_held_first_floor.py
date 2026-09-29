"""Held 1st floor (ruling 2026-09-28, release 0.2.2; hard exempt since the
2026-09-29 ruling).

On easy and medium every `Held 1st` rung needs the first Progressive Boost
rank or, with Itemsanity on, one useful weapon family. On hard there is no
floor: the Trophy Race win needs no boost there, and winning means holding
1st, so Held 1st opens with the win. Cortex Castle's and Hot Air Skyway's
Held 1st need USF at every difficulty. Held 3rd and Held 5th are unchanged,
and Progressive Boost off leaves the floor vacuous.
"""
import copy
import unittest

from .test_capability_contract import PLAYER, _build, _state
from ..itemsanity import HELD_FIRST_WEAPON_FAMILY_MIN
from ..podium import location_name

TRACKS = ("Crash Cove", "Dingo Canyon", "Oxide Station", "Hot Air Skyway",
          "Cortex Castle", "Slide Coliseum")
TRIALS = dict(slide_coliseum_races="trophy_race",
              turbo_track_races="trophy_race")


def _reach(state, name):
    return state.can_reach(name, "Location", PLAYER)


class TestHeldFirstFloor(unittest.TestCase):
    def test_weapon_minimum_is_one_family(self):
        self.assertEqual(HELD_FIRST_WEAPON_FAMILY_MIN, 1)

    def test_cortex_castle_held_first_needs_usf(self):
        mw = _build(progressive_boost="shared_global")
        name = location_name("Cortex Castle", "held_1st")
        self.assertFalse(_reach(_state(mw, boost=1), name))
        self.assertTrue(_reach(_state(mw, boost=2), name))
        self.assertTrue(_reach(_state(mw), location_name("Cortex Castle",
                                                         "held_3rd")))

    def test_every_held_first_needs_one_boost_on_easy_and_medium(self):
        for difficulty in ("easy", "medium"):
            mw = _build(progressive_boost="shared_global", itemsanity=False,
                        logic_difficulty=difficulty,
                        shortcut_knowledge="hard", **TRIALS)
            bare, one = _state(mw), _state(mw, boost=1)
            for track in ("Crash Cove", "Dingo Canyon", "Oxide Station",
                          "Slide Coliseum", "Turbo Track"):
                name = location_name(track, "held_1st")
                with self.subTest(difficulty=difficulty, track=track):
                    self.assertFalse(_reach(bare, name))
                    self.assertTrue(_reach(one, name))

    def test_one_useful_weapon_family_suffices_with_itemsanity(self):
        # Medium only: easy also gates Held 1st with the difficulty rule's
        # three-family arm, and hard has no floor (ruling 2026-09-29).
        for difficulty in ("medium",):
            mw = _build(progressive_boost="shared_global", itemsanity=True,
                        logic_difficulty=difficulty)
            for track in ("Crash Cove", "Dingo Canyon"):
                name = location_name(track, "held_1st")
                with self.subTest(difficulty=difficulty, track=track):
                    self.assertFalse(_reach(_state(mw), name))
                    self.assertTrue(_reach(_state(mw, held=("Mask",)), name))
                    self.assertTrue(_reach(_state(mw, held=("Bomb x3",)),
                                           name))
                    # A family outside the useful set does not count.
                    self.assertFalse(_reach(_state(mw, held=("Turbo",)), name))

    def test_usf_tracks_are_not_cleared_by_one_weapon(self):
        mw = _build(progressive_boost="shared_global", itemsanity=True,
                    logic_difficulty="hard")
        for track in ("Hot Air Skyway", "Cortex Castle"):
            name = location_name(track, "held_1st")
            with self.subTest(track=track):
                self.assertFalse(_reach(_state(mw, held=("Mask",)), name))
                self.assertTrue(_reach(_state(mw, boost=2), name))

    def test_progressive_boost_off_is_vacuous(self):
        for itemsanity in (True, False):
            mw = _build(progressive_boost="off", itemsanity=itemsanity,
                        logic_difficulty="hard", **TRIALS)
            bare = _state(mw)
            for track in TRACKS:
                with self.subTest(itemsanity=itemsanity, track=track):
                    self.assertTrue(_reach(bare, location_name(track,
                                                               "held_1st")))

    def test_held_third_and_fifth_unchanged(self):
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="hard", podium_held_fifth_rung=True,
                    **TRIALS)
        bare = _state(mw)
        for track in TRACKS:
            for key in ("held_3rd", "held_5th"):
                with self.subTest(track=track, rung=key):
                    self.assertTrue(_reach(bare, location_name(track, key)))

    def test_cup_leg_path_is_gated(self):
        """Close Crash Cove's own pad: its rungs are then reachable only
        through the Red Gem Cup leg, and Held 1st still needs the floor."""
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="medium", warp_pad_shuffle_categories=[])
        mw.get_entrance("Crash Cove Warp Pad", PLAYER).access_rule = (
            lambda state: False)
        bare, one = _state(mw), _state(mw, boost=1)
        self.assertFalse(_reach(one, "Crash Cove: Trophy Race"))
        self.assertTrue(_reach(bare, location_name("Crash Cove", "held_3rd")))
        self.assertFalse(_reach(bare, location_name("Crash Cove", "held_1st")))
        self.assertTrue(_reach(one, location_name("Crash Cove", "held_1st")))

    def test_custom_track_slot_held_first(self):
        from ..custom_tracks import BABY_T_PARK_CURRENT
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="medium",
                    custom_tracks={"baby-t-park":
                                   copy.deepcopy(BABY_T_PARK_CURRENT)})
        name = "Custom Track 1: Held 1st"
        self.assertIn(name, {loc.name for loc in mw.get_locations(PLAYER)})
        self.assertFalse(_reach(_state(mw), name))
        self.assertTrue(_reach(_state(mw, boost=1), name))
        self.assertTrue(_reach(_state(mw), "Custom Track 1: Held 3rd"))

    def test_cortex_vortex_held_first(self):
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="medium", cortex_vortex_track=True)
        name = "Cortex Vortex: Held 1st"
        self.assertFalse(_reach(_state(mw), name))
        self.assertTrue(_reach(_state(mw, boost=1), name))


class TestHardHasNoHeldFirstFloor(unittest.TestCase):
    """Ruling 2026-09-29 (0.2.2 feedback): on hard the Trophy Race win needs
    no boost, so the floor made Held 1st stricter than the win it is part of.
    Hard drops the floor; the per-track USF terms stay."""

    def test_non_usf_held_first_matches_its_trophy_race_at_zero_boost(self):
        for itemsanity in (False, True):
            mw = _build(progressive_boost="shared_global",
                        itemsanity=itemsanity, logic_difficulty="hard",
                        **TRIALS)
            bare = _state(mw)
            for track in ("Crash Cove", "Dingo Canyon", "N. Gin Labs",
                          "Slide Coliseum", "Turbo Track"):
                with self.subTest(itemsanity=itemsanity, track=track):
                    self.assertTrue(_reach(bare, f"{track}: Trophy Race"))
                    self.assertTrue(_reach(bare, location_name(track,
                                                               "held_1st")))

    def test_medium_still_has_the_floor(self):
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="medium", **TRIALS)
        bare, one = _state(mw), _state(mw, boost=1)
        for track in ("Crash Cove", "Dingo Canyon", "Slide Coliseum"):
            name = location_name(track, "held_1st")
            with self.subTest(track=track):
                self.assertFalse(_reach(bare, name))
                self.assertTrue(_reach(one, name))

    def test_usf_held_first_tracks_still_need_usf_on_hard(self):
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="hard")
        for track in ("Hot Air Skyway", "Cortex Castle", "Oxide Station"):
            name = location_name(track, "held_1st")
            with self.subTest(track=track):
                self.assertFalse(_reach(_state(mw, boost=1), name))
                self.assertTrue(_reach(_state(mw, boost=2), name))

    def test_oxide_hard_shortcut_escape_leaves_held_first_free_on_hard(self):
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="hard", shortcut_knowledge="hard")
        self.assertTrue(_reach(_state(mw),
                               location_name("Oxide Station", "held_1st")))

    def test_cortex_vortex_and_custom_slot_free_on_hard(self):
        from ..custom_tracks import BABY_T_PARK_CURRENT
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="hard", cortex_vortex_track=True)
        self.assertTrue(_reach(_state(mw), "Cortex Vortex: Held 1st"))
        mw = _build(progressive_boost="shared_global", itemsanity=False,
                    logic_difficulty="hard",
                    custom_tracks={"baby-t-park":
                                   copy.deepcopy(BABY_T_PARK_CURRENT)})
        self.assertTrue(_reach(_state(mw), "Custom Track 1: Held 1st"))
