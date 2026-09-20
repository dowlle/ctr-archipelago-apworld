"""The CTR Token Challenge boost gate (ruling 2026-09-20, 0.2.1-alpha3).

Before the ruling a CTR Token Challenge carried no capability term of its own:
`can_reach(<track>: Trophy Race)` plus any stage-2 warp-pad requirement, and
nothing else. The alpha2 stream report is that the challenge is harder than
the race it hangs off, so it now ANDs the first boost rank while the boost pack
is on, at every logic difficulty.

What these tests pin, in the order the ruling names them:

  * the term binds on a retail track at every difficulty, including hard,
    where no other race term exists;
  * it is a FLOOR, not a ceiling -- a track whose Trophy Race needs USF still
    needs USF for its token challenge, inherited through `can_reach`;
  * it is vacuous with Progressive Boost off (the #145 FillError class);
  * shared_global and per_character both read it through `gate_satisfied`, and
    a racer-locked pad binds its racer;
  * the trial tracks (Slide Coliseum, Turbo Track) and custom-track slots go
    through the same install site and get the same term.
"""
import copy
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..custom_tracks import BABY_T_PARK_EXAMPLE
from ..progressive_capability import ROSTER, boost_item_name
from ..usf_finish import CTR_CHALLENGE_BOOST_COUNT, USF_BOOST_COUNT
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
#: A plain retail track: no USF finish gate, no relic-tier interaction.
PLAIN = "Crash Cove"
#: A USF finish track, to prove the inherited requirement is not lowered.
USF_TRACK = "Hot Air Skyway"


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _state(mw, boost=0, character_boosts=(), without=()):
    """Everything in the seed except the boost chain, plus `boost` copies."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if (item != BOOST and not item.startswith(f"{BOOST} (")
                and item not in without):
            state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    for character, count in character_boosts:
        state.add_item(boost_item_name(character), PLAYER, count)
    return state


def _reachable(mw, state, name):
    return state.can_reach(name, "Location", PLAYER)


class TestChallengeBoostFloor(unittest.TestCase):
    def test_the_floor_is_the_first_boost_rank(self):
        self.assertEqual(CTR_CHALLENGE_BOOST_COUNT, 1)

    def test_every_difficulty_gates_the_challenge(self):
        """Unlike the weapon-family rule, this term has no difficulty escape:
        hard has no race requirement at all, so without this the challenge
        would be free there."""
        for difficulty in ("easy", "medium", "hard"):
            mw = _build(progressive_boost="shared_global",
                        logic_difficulty=difficulty)
            name = f"{PLAIN}: CTR Token Challenge"
            with self.subTest(difficulty=difficulty, boost=0):
                self.assertFalse(_reachable(mw, _state(mw, boost=0), name))
            with self.subTest(difficulty=difficulty, boost=1):
                self.assertTrue(_reachable(
                    mw, _state(mw, boost=CTR_CHALLENGE_BOOST_COUNT), name))

    def test_every_retail_challenge_carries_it(self):
        """Every token challenge in the seed is shut at zero boost. The three
        USF finish tracks open at two rather than one, which is the inherited
        race requirement doing its job, so they are asserted at their own
        rank instead of being skipped."""
        from ..usf_finish import ALL_USF_FINISH_TRACKS
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard")
        blocked = _state(mw, boost=0)
        one, two = _state(mw, boost=1), _state(mw, boost=USF_BOOST_COUNT)
        names = [loc.name for loc in mw.get_locations(PLAYER)
                 if loc.name.endswith("CTR Token Challenge")]
        self.assertGreaterEqual(len(names), 16)
        for name in sorted(names):
            track = name.split(":")[0].strip()
            with self.subTest(location=name):
                self.assertFalse(_reachable(mw, blocked, name))
                if track in ALL_USF_FINISH_TRACKS:
                    self.assertFalse(_reachable(mw, one, name))
                    self.assertTrue(_reachable(mw, two, name))
                else:
                    self.assertTrue(_reachable(mw, one, name))

    def test_a_higher_race_requirement_is_still_inherited(self):
        """Hot Air Skyway's finish needs USF. The token challenge gates on
        `can_reach` of that race, so one boost must NOT be enough for it while
        it is enough on a plain track in the same seed."""
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard")
        one = _state(mw, boost=CTR_CHALLENGE_BOOST_COUNT)
        usf = _state(mw, boost=USF_BOOST_COUNT)
        name = f"{USF_TRACK}: CTR Token Challenge"
        self.assertFalse(_reachable(mw, one, name))
        self.assertTrue(_reachable(mw, usf, name))
        self.assertTrue(_reachable(mw, one, f"{PLAIN}: CTR Token Challenge"))

    def test_oxide_hard_shortcut_escape_does_not_lower_its_token(self):
        """At hard shortcut knowledge Oxide Station's FINISH gate goes vacuous,
        so the race is free at zero boost. Its token challenge is not: the
        2026-09-20 floor shuts it at zero, and the earlier #87 physical-letter
        ruling keeps it at USF above that. The floor is a floor, never a
        ceiling, and it did not relax anything already installed."""
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard",
                    shortcut_knowledge="hard")
        name = "Oxide Station: CTR Token Challenge"
        self.assertTrue(_reachable(mw, _state(mw, boost=0),
                                   "Oxide Station: Trophy Race"))
        self.assertFalse(_reachable(mw, _state(mw, boost=0), name))
        self.assertFalse(_reachable(
            mw, _state(mw, boost=CTR_CHALLENGE_BOOST_COUNT), name))
        self.assertTrue(_reachable(mw, _state(mw, boost=USF_BOOST_COUNT), name))

    def test_the_term_is_vacuous_with_the_boost_pack_off(self):
        """Seating spec 2.2: with Progressive Boost off no boost item exists,
        so the term must resolve True rather than to a requirement nothing can
        satisfy."""
        mw = _build(progressive_boost="off", logic_difficulty="hard")
        self.assertTrue(_reachable(mw, _state(mw, boost=0),
                                   f"{PLAIN}: CTR Token Challenge"))

    def test_sapphire_time_trial_is_untouched(self):
        """Ruling 3 of the same session: Sapphire stays free. The token term
        must not leak onto the relic branch."""
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard")
        name = f"{PLAIN}: Sapphire Time Trial"
        live = {loc.name for loc in mw.get_locations(PLAYER)}
        self.assertIn(name, live)
        self.assertTrue(_reachable(mw, _state(mw, boost=0), name))


class TestChallengeBoostRacerAware(unittest.TestCase):
    def test_per_character_mode_accepts_a_driveable_racer(self):
        mw = _build(progressive_boost="per_character", logic_difficulty="hard",
                    character_unlocks=False)
        racer = mw.worlds[PLAYER].ctr_starting_character
        name = f"{PLAIN}: CTR Token Challenge"
        self.assertFalse(_reachable(mw, _state(mw), name))
        self.assertTrue(_reachable(
            mw, _state(mw, character_boosts=((racer, 1),)), name))

    def test_a_locked_pad_binds_its_racer(self):
        from ..progressive_capability import track_required_character
        mw = track = required = None
        for seed in range(1, 33):
            candidate = _build(seed=seed, progressive_boost="per_character",
                               logic_difficulty="hard", racer_locked_pads=True)
            world = candidate.worlds[PLAYER]
            hits = [(loc.name.split(":")[0].strip(),
                     track_required_character(world,
                                              loc.name.split(":")[0].strip()))
                    for loc in candidate.get_locations(PLAYER)
                    if loc.name.endswith("CTR Token Challenge")]
            hits = [(t, r) for t, r in hits if r]
            if hits:
                mw, (track, required) = candidate, hits[0]
                break
        self.assertIsNotNone(mw, "fixture seeds produced no locked token track")
        wrong = next(racer for racer in ROSTER if racer != required)
        name = f"{track}: CTR Token Challenge"
        self.assertFalse(_reachable(
            mw, _state(mw, character_boosts=((wrong, 3),)), name))
        self.assertTrue(_reachable(
            mw, _state(mw, character_boosts=((required, 3),)), name))


class TestChallengeBoostTrialTracks(unittest.TestCase):
    """Slide Coliseum and Turbo Track host their races since #203. They reach
    `add_time_trial_and_ctr_requirements` by name like every other track, so
    they take the same term rather than an exemption."""

    OPTIONS = {"slide_coliseum_races": "trophy_and_ctr_challenge",
               "turbo_track_races": "trophy_and_ctr_challenge"}

    def test_both_trial_challenges_need_the_first_boost(self):
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard",
                    **self.OPTIONS)
        blocked, cleared = _state(mw, boost=0), _state(mw, boost=1)
        live = {loc.name for loc in mw.get_locations(PLAYER)}
        for track in ("Slide Coliseum", "Turbo Track"):
            name = f"{track}: CTR Token Challenge"
            if name not in live:
                continue
            with self.subTest(track=track):
                self.assertFalse(_reachable(mw, blocked, name))
                self.assertTrue(_reachable(mw, cleared, name))
                # The trial TROPHY race itself keeps no boost term: only the
                # challenge was ruled.
                self.assertTrue(_reachable(mw, blocked, f"{track}: Trophy Race"))


class TestChallengeBoostCustomTracks(CTRTestBase):
    """A custom-track slot's CTR Token Challenge takes the term from the same
    loop, and `add_custom_ctr_challenge_rules` ANDs its letters on top without
    dropping it."""

    run_default_tests = False
    auto_construct = False
    options = {"progressive_boost": "shared_global", "logic_difficulty": "hard",
               "lettersanity": 0,
               "custom_tracks": {"baby-t-park": {
                   **copy.deepcopy(BABY_T_PARK_EXAMPLE),
                   "modes": {"ctr_challenge": True}}}}

    def setUp(self):
        self.world_setup(seed=7)

    def test_custom_challenge_needs_the_first_boost(self):
        name = "Custom Track 1: CTR Token Challenge"
        loc = self.multiworld.get_location(name, self.player)
        blocked = _state(self.multiworld, boost=0)
        cleared = _state(self.multiworld, boost=1)
        self.assertFalse(loc.can_reach(blocked))
        self.assertTrue(loc.can_reach(cleared))


class TestChallengeBoostStopsAtTheToken(unittest.TestCase):
    """The floor is on COMPLETING the challenge, so it lands on the token
    location only. Letter locations keep the entry rule they already shared
    plus their own ruled routes (Papu's Turbo/Mask arms, Oxide's free C,
    Tiger Temple's door opener) -- floor-sharing them would have overridden
    three earlier rulings the 2026-09-20 session did not revisit."""

    def test_letters_share_the_entry_rule_the_token_wraps(self):
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard",
                    lettersanity=1)
        token = mw.get_location(f"{PLAIN}: CTR Token Challenge", PLAYER)
        letters = [loc for loc in mw.get_locations(PLAYER)
                   if loc.name.startswith(f"{PLAIN}: Letter ")]
        self.assertTrue(letters)
        entry = token.access_rule.__defaults__[0]
        blocked = _state(mw, boost=0)
        for loc in letters:
            with self.subTest(location=loc.name):
                self.assertIs(loc.access_rule, entry)
                self.assertTrue(loc.can_reach(blocked))
        self.assertFalse(token.can_reach(blocked))

    def test_papu_route_arms_survive_the_floor(self):
        """Papu's C and T rule only exists while boost is randomized, which is
        exactly when the floor binds. Sharing the floor with the letters would
        have made the Turbo and Mask arms dead code."""
        from ..lettersanity import LETTERSANITY_CLASS
        mw = _build(progressive_boost="shared_global", logic_difficulty="hard",
                    lettersanity=1, letters_per_track=3, itemsanity=True)
        for letter in ("C", "T"):
            name = LETTERSANITY_CLASS.location_name("Papu's Pyramid", letter)
            loc = mw.get_location(name, PLAYER)
            with self.subTest(letter=letter, route="none"):
                self.assertFalse(loc.can_reach(
                    _state(mw, boost=0, without=("Turbo", "Mask"))))
            for route in ("Turbo", "Mask"):
                with self.subTest(letter=letter, route=route):
                    state = _state(mw, boost=0, without=("Turbo", "Mask"))
                    state.add_item(route, PLAYER, 1)
                    self.assertTrue(loc.can_reach(state))


if __name__ == "__main__":
    unittest.main()
