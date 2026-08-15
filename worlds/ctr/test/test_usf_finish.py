"""Confirmed USF finish gates and their propagation.

Finishing Hot Air Skyway at all needs USF (two received `Progressive Boost`).
The one-line version of that gate leaks, which is what these tests pin: the
Trophy Race rule is inherited by the time trials and the token challenge, but
the podium rungs reach the same finish through their Gem-Cup OR, and a cup that
runs Hot Air Skyway as a LEG cannot be completed without the same USF either.
Every path is exercised here, together with the two exemptions the session's own
data forced -- the live-position held rungs, and the whole gate collapsing to
vacuous when the boost chain is not randomized.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..gem_cup_legs import load_vanilla_cup_legs
from ..podium import (FINISH_RUNG_KEYS, HELD_RUNG_KEYS, TROPHY_TRACKS,
                      location_name)
from ..progressive_capability import boost_item_name
from ..usf_finish import (ALL_USF_FINISH_TRACKS, USF_BOOST_COUNT,
                          USF_FINISH_TRACKS, usf_finish_cups)
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
HAS = "Hot Air Skyway"
#: Vanilla cups containing any track with a confirmed finish gate.
VANILLA_GATED_CUPS = ("Green Gem Cup", "Yellow Gem Cup", "Purple Gem Cup")


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _state(mw, boost=0):
    """A state holding EVERY item in the seed except the boost chain, plus
    `boost` copies of it. Everything that is not the gate under test is
    satisfied, so a False verdict can only come from the gate."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item != BOOST and not item.startswith(f"{BOOST} ("):
            state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


def _reachable(mw, state, name):
    return state.can_reach(name, "Location", PLAYER)


class _FakeState:
    """A hand-built state for the branch tests: exactly the spots named are
    reachable, and the boost count is exactly what was asked for. Lets a rung's
    REAL installed rule be evaluated on a topology no option combination can
    produce (one cup reachable, the track's own pad shut)."""

    def __init__(self, reachable=(), boost=0):
        self.reachable = set(reachable)
        self.boost = boost

    def can_reach(self, spot, resolution_hint=None, player=None):
        return (spot, resolution_hint) in self.reachable

    def count(self, item, player):
        return self.boost if item == BOOST else 0

    def has(self, item, player, count=1):
        return True


class TestGatedCupSelection(unittest.TestCase):
    """Which cups the gate covers is a per-seed question about the leg map."""

    def test_vanilla_legs_gate_exactly_confirmed_cups(self):
        legs = load_vanilla_cup_legs()
        self.assertEqual(usf_finish_cups(legs), frozenset(VANILLA_GATED_CUPS))
        for cup in VANILLA_GATED_CUPS:
            self.assertTrue(ALL_USF_FINISH_TRACKS.intersection(legs[cup]))

    def test_a_synthetic_map_gates_by_membership_only(self):
        legs = {"Red Gem Cup": [HAS, HAS, HAS, HAS],
                "Green Gem Cup": ["Crash Cove", "Polar Pass", HAS, "Coco Park"],
                "Blue Gem Cup": ["Crash Cove"] * 4}
        self.assertEqual(usf_finish_cups(legs),
                         frozenset({"Red Gem Cup", "Green Gem Cup"}))

    def test_the_gated_tracks_are_real_trophy_tracks(self):
        self.assertTrue(USF_FINISH_TRACKS)
        for track in USF_FINISH_TRACKS:
            self.assertIn(track, TROPHY_TRACKS)


class TestTrophyRaceGate(unittest.TestCase):
    """The finish itself."""

    def test_vacuous_when_the_boost_chain_is_not_randomized(self):
        mw = _build()
        self.assertTrue(_reachable(mw, _state(mw), f"{HAS}: Trophy Race"))

    def test_needs_two_copies(self):
        mw = _build(progressive_boost="shared_global")
        name = f"{HAS}: Trophy Race"
        self.assertFalse(_reachable(mw, _state(mw, boost=0), name))
        self.assertFalse(_reachable(mw, _state(mw, boost=1), name))
        self.assertTrue(_reachable(mw, _state(mw, boost=USF_BOOST_COUNT), name))

    def test_per_character_usf_must_belong_to_one_driveable_racer(self):
        mw = _build(progressive_boost="per_character",
                    character_unlocks=False)
        name = f"{HAS}: Trophy Race"
        state = _state(mw)
        first = mw.worlds[PLAYER].ctr_starting_character
        second = "Coco Bandicoot" if first != "Coco Bandicoot" else "Polar"
        state.add_item(boost_item_name(first), PLAYER, 1)
        state.add_item(boost_item_name(second), PLAYER, 1)
        self.assertFalse(_reachable(mw, state, name))
        state.add_item(boost_item_name(first), PLAYER, 1)
        self.assertTrue(_reachable(mw, state, name))

    def test_no_other_track_is_gated(self):
        mw = _build(progressive_boost="shared_global")
        state = _state(mw, boost=0)
        for track in TROPHY_TRACKS:
            if track in ALL_USF_FINISH_TRACKS:
                continue
            with self.subTest(track=track):
                self.assertTrue(_reachable(mw, state, f"{track}: Trophy Race"))


class TestTimeTrialRipple(unittest.TestCase):
    """Relic time trials and the token challenge gate on `can_reach` of their
    track's Trophy Race LOCATION, so they inherit the term with no code of
    their own -- in both warp-pad modes, including on top of a stage-2 gate."""

    SUFFIXES = ("Sapphire Time Trial", "Gold Time Trial",
                "Platinum Time Trial", "CTR Token Challenge")

    def _check(self, **options):
        mw = _build(progressive_boost="shared_global", **options)
        blocked, cleared = _state(mw, boost=0), _state(mw, boost=USF_BOOST_COUNT)
        live = {loc.name for loc in mw.get_locations(PLAYER)}
        # The seed's relic-count sliders can remove whole tiers (#171), so the
        # suffix list is a superset; assert the surviving ones and that the
        # sweep was not empty.
        checked = 0
        for suffix in self.SUFFIXES:
            if f"{HAS}: {suffix}" not in live:
                continue
            checked += 1
            with self.subTest(suffix=suffix):
                self.assertFalse(_reachable(mw, blocked, f"{HAS}: {suffix}"))
                self.assertTrue(_reachable(mw, cleared, f"{HAS}: {suffix}"))
                # Control: the same check on an ungated track.
                self.assertTrue(
                    _reachable(mw, blocked, f"Crash Cove: {suffix}"))
        self.assertGreaterEqual(checked, 2)

    def test_vanilla_warp_pad_mode(self):
        self._check(warppad_unlock_requirements=0)

    def test_randomized_warp_pad_mode(self):
        self._check(warppad_unlock_requirements=1)


class TestPodiumRungs(unittest.TestCase):
    """The rungs are where the one-line fix leaks: their Gem-Cup OR reaches the
    finish without consulting the Trophy Race rule at all."""

    def test_finish_rungs_are_gated_despite_reachable_cups(self):
        mw = _build(progressive_boost="shared_global")
        blocked = _state(mw, boost=0)
        # The premise of the leak: both legging cups ARE reachable here.
        for cup in VANILLA_GATED_CUPS:
            self.assertTrue(blocked.can_reach(cup, "Region", PLAYER))
        cleared = _state(mw, boost=USF_BOOST_COUNT)
        for key in sorted(FINISH_RUNG_KEYS):
            with self.subTest(rung=key):
                name = location_name(HAS, key)
                self.assertFalse(_reachable(mw, blocked, name))
                self.assertTrue(_reachable(mw, cleared, name))

    def test_held_rungs_stay_free(self):
        """`Held 3rd` was checked on Hot Air Skyway without USF in the same
        session: the live-position listener fires before the finish line."""
        mw = _build(progressive_boost="shared_global")
        blocked = _state(mw, boost=0)
        for key in sorted(HELD_RUNG_KEYS & {"held_1st", "held_3rd"}):
            with self.subTest(rung=key):
                self.assertTrue(_reachable(mw, blocked, location_name(HAS, key)))

    def test_other_tracks_keep_every_rung(self):
        mw = _build(progressive_boost="shared_global")
        blocked = _state(mw, boost=0)
        for key in sorted(FINISH_RUNG_KEYS):
            with self.subTest(rung=key):
                self.assertTrue(
                    _reachable(mw, blocked, location_name("Crash Cove", key)))

    def test_cup_branch_of_a_leg_track_carries_the_term(self):
        """A different track's rung reached through a gated or plain cup.

        Papu's Pyramid is legged by Red (plain) and Purple (gated), so the two
        branches remain separable after Cortex Castle gates Green.
        """
        mw = _build(progressive_boost="shared_global")
        rule = mw.get_location(
            location_name("Papu's Pyramid", "finish_podium"), PLAYER).access_rule
        purple = [("Purple Gem Cup", "Region")]
        red = [("Red Gem Cup", "Region")]
        self.assertFalse(rule(_FakeState(purple, boost=0)))
        self.assertFalse(rule(_FakeState(purple, boost=1)))
        self.assertTrue(rule(_FakeState(purple, boost=USF_BOOST_COUNT)))
        # The ungated cup and the track's own trophy path stay boost-free.
        self.assertTrue(rule(_FakeState(red, boost=0)))
        self.assertTrue(rule(_FakeState(
            [("Papu's Pyramid: Trophy Race", "Location")], boost=0)))

    def test_cup_branches_are_ungated_when_the_pack_is_off(self):
        mw = _build()
        rule = mw.get_location(
            location_name("Roo's Tubes", "finish_podium"), PLAYER).access_rule
        self.assertTrue(rule(_FakeState([("Purple Gem Cup", "Region")])))


class TestGemCupCompletion(unittest.TestCase):
    """Completing a cup includes finishing every leg, so a cup that legs a
    USF track cannot pay out its Gem without USF."""

    def test_legging_cups_are_gated(self):
        mw = _build(progressive_boost="shared_global")
        blocked = _state(mw, boost=0)
        cleared = _state(mw, boost=USF_BOOST_COUNT)
        for cup, legs in load_vanilla_cup_legs().items():
            with self.subTest(cup=cup):
                name = f"{cup}: Gem"
                if ALL_USF_FINISH_TRACKS.intersection(legs):
                    self.assertFalse(_reachable(mw, blocked, name))
                    self.assertTrue(_reachable(mw, cleared, name))
                else:
                    self.assertTrue(_reachable(mw, blocked, name))

    def test_vacuous_when_the_boost_chain_is_not_randomized(self):
        mw = _build()
        state = _state(mw)
        for cup in VANILLA_GATED_CUPS:
            with self.subTest(cup=cup):
                self.assertTrue(_reachable(mw, state, f"{cup}: Gem"))

    def test_randomized_legs_gate_by_this_seed_s_map(self):
        """With `randomize_gem_cup_tracks` the gated set is per-seed, so the
        rules must follow the drawn map rather than the vanilla table."""
        for seed in (11, 12, 13):
            mw = _build(seed=seed, progressive_boost="shared_global",
                        randomize_gem_cup_tracks=True)
            legs = mw.worlds[PLAYER].gem_cup_legs
            blocked = _state(mw, boost=0)
            cleared = _state(mw, boost=USF_BOOST_COUNT)
            for cup, cup_legs in legs.items():
                with self.subTest(seed=seed, cup=cup):
                    name = f"{cup}: Gem"
                    self.assertEqual(
                        _reachable(mw, blocked, name),
                        not ALL_USF_FINISH_TRACKS.intersection(cup_legs))
                    self.assertTrue(_reachable(mw, cleared, name))


class TestBoostSeedGenerates(CTRTestBase):
    """A full fill on a randomized-boost seed: the gate now sits between the
    starting inventory and two Gem Cups, so the boost chain has to place
    reachably for the seed to complete at all."""

    options = {"progressive_boost": "shared_global", "accessibility": "full"}


class TestGatedCupGoalSeedGenerates(CTRTestBase):
    """The same, with the five-gem goal: both gated cups are then on the goal
    path, which is the tightest shape this gate creates."""

    options = {"progressive_boost": "shared_global", "accessibility": "full",
               "oxide_goal": "none", "gems_required_goal": 5}
