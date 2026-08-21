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
import collections
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..capability_contract import (CONFIRMED_FINISH_BY_TRACK,
                                   held_first_gated_tracks)
from ..gem_cup_legs import load_vanilla_cup_legs
from ..podium import (FINISH_RUNG_KEYS, HELD_RUNG_KEYS, TROPHY_TRACKS,
                      location_name)
from ..progressive_capability import boost_item_name
from ..usf_finish import (ALL_USF_FINISH_TRACKS, FIRST_BOOST_COUNT,
                          USF_BOOST_COUNT, USF_FINISH_TRACKS,
                          USF_OR_HARD_SK_FINISH_TRACKS, cup_finish_term,
                          usf_finish_cups)
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
HAS = "Hot Air Skyway"
OXIDE = "Oxide Station"
#: Vanilla cups containing any track with a confirmed finish gate.
VANILLA_GATED_CUPS = ("Green Gem Cup", "Yellow Gem Cup", "Purple Gem Cup")
#: The one vanilla cup that legs BOTH gated tracks, so its composed term keeps
#: a Hot Air Skyway half after the Oxide half goes vacuous at hard knowledge.
OXIDE_AND_HAS_CUP = "Yellow Gem Cup"


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

    def __init__(self, reachable=(), boost=0, regions=()):
        self.reachable = set(reachable)
        self.boost = boost
        # A rung's own-track branch is now the Trophy Race's captured pre-gate
        # rule, which asks the REGION object directly rather than resolving a
        # location name through the state. Same "exactly what is named is
        # reachable" contract, expressed the way `Region.can_reach` reads it.
        self.stale = collections.defaultdict(bool)
        self.reachable_regions = collections.defaultdict(set, {PLAYER: set(regions)})

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
        one_boost = _state(mw, boost=FIRST_BOOST_COUNT)
        checked = 0
        for suffix in self.SUFFIXES:
            if f"{HAS}: {suffix}" not in live:
                continue
            checked += 1
            with self.subTest(suffix=suffix):
                self.assertFalse(_reachable(mw, blocked, f"{HAS}: {suffix}"))
                self.assertTrue(_reachable(mw, cleared, f"{HAS}: {suffix}"))
                # Control: the same check on a non-USF track. Gold and
                # Platinum carry the 2026-08-21 first-boost floor everywhere,
                # so their control opens at one boost rather than bare;
                # Sapphire and the token challenge stay free.
                control = f"Crash Cove: {suffix}"
                if suffix in ("Gold Time Trial", "Platinum Time Trial"):
                    self.assertFalse(_reachable(mw, blocked, control))
                    self.assertTrue(_reachable(mw, one_boost, control))
                else:
                    self.assertTrue(_reachable(mw, blocked, control))
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
            boost=0, regions=[mw.get_region("Papu's Pyramid", PLAYER)])))

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


class TestOxideStationGate(unittest.TestCase):
    """Oxide Station's finish gate and its `Held 1st` rung (issue #55).

    Ruled 2026-08-14 17:15 from the live pre1 test session: on an empty
    randomized boost chain Oxide Station is not realistically finishable at
    easy or medium shortcut knowledge, and holding 1st is not realistic
    either, but a player who declared HARD shortcut knowledge knows routes
    that make both work bare. So this track differs from Hot Air Skyway in
    exactly two ways -- the term is `USF OR shortcut_knowledge: hard` instead
    of USF strictly, and `Held 1st` carries the term too while `Held 3rd` and
    `Held 5th` stay free (holdable mid-race without finishing).

    The game-side half is `AP_CapabilityFireGrant`
    (ctr-native-ap `ap/ap_capability.c`): below `AP_CAP_BOOST_USF` a super
    turbo pad is demoted to a normal pad's cap and reserves, so the super pad
    cannot carry a bare kart across Oxide's finish -- while ordinary turbo
    pads still grant at every tier, which is what leaves the hard-knowledge
    route drivable with zero boost items. `AP_CAP_BOOST_USF` is the second
    rank of that enum, matching `USF_BOOST_COUNT`.

    The production rules landed with the confirmed-capability contract rather
    than as a standalone rule, and arrived without tests of their own. These
    pin the ruling so a later edit to `capability_contract` or to
    `track_finish_term` cannot silently un-gate the track.
    """

    FINISH_NAMES = ("Oxide Station: Trophy Race",
                    location_name(OXIDE, "finish_any"),
                    location_name(OXIDE, "finish_podium"),
                    location_name(OXIDE, "held_1st"))

    def test_finish_and_held_first_need_usf_at_easy_and_medium(self):
        for knowledge in ("easy", "medium"):
            mw = _build(progressive_boost="shared_global",
                        shortcut_knowledge=knowledge)
            live = {loc.name for loc in mw.get_locations(PLAYER)}
            for name in self.FINISH_NAMES:
                if name not in live:
                    continue
                with self.subTest(knowledge=knowledge, location=name):
                    self.assertFalse(_reachable(mw, _state(mw, boost=0), name))
                    self.assertFalse(_reachable(mw, _state(mw, boost=1), name))
                    self.assertTrue(_reachable(
                        mw, _state(mw, boost=USF_BOOST_COUNT), name))

    def test_held_third_and_fifth_stay_free_at_every_tier(self):
        """The live-position listener fires before the line, so these rungs
        never cross the gate -- the one asymmetry with `Held 1st`."""
        for knowledge in ("easy", "medium", "hard"):
            mw = _build(progressive_boost="shared_global",
                        shortcut_knowledge=knowledge,
                        podium_held_fifth_rung=True)
            live = {loc.name for loc in mw.get_locations(PLAYER)}
            blocked = _state(mw, boost=0)
            for key in ("held_3rd", "held_5th"):
                name = location_name(OXIDE, key)
                if name not in live:
                    continue
                with self.subTest(knowledge=knowledge, rung=key):
                    self.assertTrue(_reachable(mw, blocked, name))

    def test_hard_knowledge_escapes_the_whole_gate(self):
        """The escape is an OPTION, not a state term: at hard knowledge the
        track's term is vacuous and zero boost items are required."""
        mw = _build(progressive_boost="shared_global",
                    shortcut_knowledge="hard")
        live = {loc.name for loc in mw.get_locations(PLAYER)}
        blocked = _state(mw, boost=0)
        for name in self.FINISH_NAMES:
            if name not in live:
                continue
            with self.subTest(location=name):
                self.assertTrue(_reachable(mw, blocked, name))

    def test_hard_knowledge_does_not_escape_hot_air_skyway(self):
        """The escape is per TRACK, not per seed. Hot Air Skyway's record
        carries no escape, so its finish stays gated at hard knowledge -- and
        so does the Yellow Gem Cup, which legs both tracks."""
        mw = _build(progressive_boost="shared_global",
                    shortcut_knowledge="hard")
        blocked = _state(mw, boost=0)
        cleared = _state(mw, boost=USF_BOOST_COUNT)
        for name in (f"{HAS}: Trophy Race",
                     location_name(HAS, "finish_podium"),
                     f"{OXIDE_AND_HAS_CUP}: Gem"):
            with self.subTest(location=name):
                self.assertFalse(_reachable(mw, blocked, name))
                self.assertTrue(_reachable(mw, cleared, name))

    def test_a_cup_composes_its_gated_legs_one_term_each(self):
        """`cup_finish_term` ANDs one term per gated leg, so the hard-knowledge
        escape can collapse Oxide's half of a cup without touching the other
        half. Built from a synthetic leg list so the assertion does not depend
        on which cups a seed happens to draw."""
        for knowledge, both, oxide_only in (("easy", 2, 2), ("hard", 2, 0)):
            world = _build(progressive_boost="shared_global",
                           shortcut_knowledge=knowledge).worlds[PLAYER]
            with self.subTest(knowledge=knowledge):
                mixed = cup_finish_term([OXIDE, HAS, "Crash Cove"], world)
                only = cup_finish_term([OXIDE, "Crash Cove"], world)
                self.assertFalse(mixed(_FakeState(boost=both - 1), PLAYER))
                self.assertTrue(mixed(_FakeState(boost=both), PLAYER))
                self.assertTrue(only(_FakeState(boost=oxide_only), PLAYER))

    def test_another_track_s_cup_branch_carries_the_composed_term(self):
        """Dingo Canyon is a Yellow Gem Cup leg, and Yellow legs both gated
        tracks. Its rung reached through that cup therefore needs the boost at
        hard knowledge too -- the cup-branch leak this file exists to pin,
        checked on the shape where the two terms differ."""
        for knowledge in ("easy", "hard"):
            mw = _build(progressive_boost="shared_global",
                        shortcut_knowledge=knowledge)
            rule = mw.get_location(
                location_name("Dingo Canyon", "finish_podium"),
                PLAYER).access_rule
            cup = [(OXIDE_AND_HAS_CUP, "Region")]
            with self.subTest(knowledge=knowledge):
                self.assertFalse(rule(_FakeState(cup, boost=0)))
                self.assertTrue(rule(_FakeState(cup, boost=USF_BOOST_COUNT)))

    def test_vacuous_when_the_boost_chain_is_not_randomized(self):
        """Seating spec 2.2: with the pack off no Progressive Boost item
        exists and every kart already has USF, so the gate must resolve True
        rather than to a requirement nothing in the seed can satisfy."""
        mw = _build(shortcut_knowledge="easy")
        live = {loc.name for loc in mw.get_locations(PLAYER)}
        state = _state(mw)
        for name in self.FINISH_NAMES:
            if name not in live:
                continue
            with self.subTest(location=name):
                self.assertTrue(_reachable(mw, state, name))

    def test_per_character_usf_must_belong_to_one_driveable_racer(self):
        """Two racers holding one copy each is not USF for anybody -- the
        #252 single-racer ruling, on the escape-carrying track."""
        mw = _build(progressive_boost="per_character",
                    shortcut_knowledge="easy", character_unlocks=False)
        name = f"{OXIDE}: Trophy Race"
        state = _state(mw)
        first = mw.worlds[PLAYER].ctr_starting_character
        second = "Coco Bandicoot" if first != "Coco Bandicoot" else "Polar"
        state.add_item(boost_item_name(first), PLAYER, 1)
        state.add_item(boost_item_name(second), PLAYER, 1)
        self.assertFalse(_reachable(mw, state, name))
        state.add_item(boost_item_name(first), PLAYER, 1)
        self.assertTrue(_reachable(mw, state, name))

    def test_the_contract_row_is_what_production_reads(self):
        """Parity between the field ruling and the sets the rules consume, so
        the record cannot be edited without moving the gate with it."""
        record = CONFIRMED_FINISH_BY_TRACK[OXIDE]
        self.assertEqual(record.boost_count, USF_BOOST_COUNT)
        self.assertTrue(record.hard_shortcut_escape)
        self.assertTrue(record.gate_held_first)
        self.assertIn(OXIDE, USF_OR_HARD_SK_FINISH_TRACKS)
        self.assertIn(OXIDE, held_first_gated_tracks())
        self.assertNotIn(OXIDE, USF_FINISH_TRACKS)
        # Hot Air Skyway is the contrast the ruling is written against.
        self.assertNotIn(HAS, held_first_gated_tracks())
        self.assertIn(HAS, USF_FINISH_TRACKS)


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
