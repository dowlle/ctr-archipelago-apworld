"""Adventure structure and race type menu (#208).

Pins the option defaults and wire scalars, the `ctr_first` stage-1 rule (CTR
Challenge and Trophy Race share one term, no stage 2, letters on the stage-1
entry), the unchanged stage-2 rule of the relic checks, the `race_structure`
award pairs, the refusals for destinations that cannot serve `ctr_first`, and
the Universal Tracker restore.
"""
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from . import CTRTestBase
from .. import race_structure
from ..logic_terms import term_of

TRACK = "Crash Cove"


def _loc(world, name):
    return world.multiworld.get_location(name, world.player)


class TestDefaults(CTRTestBase):
    def test_classic_and_always(self):
        o = self.world.options
        self.assertEqual(int(o.adventure_structure.value), race_structure.CLASSIC)
        self.assertEqual(int(o.race_type_selector.value), 1)
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["adventure_structure"], "classic")
        self.assertEqual(co["race_type_selector"], "always")
        self.assertNotIn("race_structure", self.world.fill_slot_data())

    def test_classic_ctr_needs_the_trophy(self):
        ctr = _loc(self.world, f"{TRACK}: CTR Token Challenge")
        trophy = _loc(self.world, f"{TRACK}: Trophy Race")
        self.assertIsNot(term_of(ctr), term_of(trophy))


class TestProductiveSelector(CTRTestBase):
    options = {"race_type_selector": "productive"}

    def test_wire(self):
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["race_type_selector"], "productive")


class TestCtrFirst(CTRTestBase):
    options = {"adventure_structure": "ctr_first", "lettersanity": "locations_only"}

    def test_trophy_and_ctr_share_one_term(self):
        for trophy_name, ctr_name in race_structure.stage1_pairs(self.world):
            trophy, ctr = _loc(self.world, trophy_name), _loc(self.world, ctr_name)
            self.assertIs(term_of(trophy), term_of(ctr), trophy_name)
        self.assertEqual(len(race_structure.stage1_pairs(self.world)), 16)

    def test_ctr_has_no_stage2_and_no_trophy_ref(self):
        stage2 = self.world.warp_pad_unlock_stage2_concrete
        self.assertTrue(stage2, "the default density gives pads a stage 2")
        enc_refs = []

        class Enc:
            def ref(self, location):
                enc_refs.append(location)
                return {"ref": 0}

            def __getattr__(self, name):
                return lambda *a, **k: {}

        for trophy_name, ctr_name in race_structure.stage1_pairs(self.world):
            term_of(_loc(self.world, ctr_name)).wire(Enc())
        self.assertEqual(enc_refs, [])

    def test_ctr_reachable_with_stage1_only(self):
        """Destinations whose physical pad has a plain-item stage 2: with
        every progression item except that one, the CTR Challenge, its
        letters and the Trophy Race are in logic, its relic checks are not."""
        stage2 = self.world.warp_pad_unlock_stage2_concrete
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        tested = 0
        for track, (item, _count) in sorted(stage2.items()):
            if item not in self.world.item_name_to_id or f"{track}: CTR Token Challenge" not in names:
                continue
            state = CollectionState(self.multiworld)
            for it in self.multiworld.itempool:
                if it.player == self.player and it.advancement and it.name != item:
                    state.collect(it, True)
            state.sweep_for_advancements()
            if not _loc(self.world, f"{track}: Trophy Race").parent_region.can_reach(state):
                continue  # this pad's stage 1 also needs the item
            self.assertTrue(_loc(self.world, f"{track}: CTR Token Challenge").can_reach(state), track)
            self.assertTrue(_loc(self.world, f"{track}: Trophy Race").can_reach(state), track)
            for loc in self.multiworld.get_locations(self.player):
                if loc.name.startswith(f"{track}: Letter "):
                    self.assertTrue(loc.can_reach(state), loc.name)
                if loc.name.startswith(f"{track}: ") and loc.name.endswith(" Time Trial"):
                    self.assertFalse(loc.can_reach(state), loc.name)
            tested += 1
        self.assertGreater(tested, 0, "no destination with a plain-item stage 2 to test")

    def test_relics_still_reference_the_trophy(self):
        refs = []

        class Enc:
            def ref(self, location):
                refs.append(location.name if hasattr(location, "name") else location)
                return {"ref": 0}

            def __getattr__(self, name):
                return lambda *a, **k: {}

        trial = next(loc for loc in self.multiworld.get_locations(self.player)
                     if loc.name.startswith(f"{TRACK}: ") and loc.name.endswith(" Time Trial"))
        term_of(trial).wire(Enc())
        self.assertEqual(refs, [f"{TRACK}: Trophy Race"])

    def test_wire(self):
        data = self.world.fill_slot_data()
        self.assertEqual(data["ctr_options"]["adventure_structure"], "ctr_first")
        block = data["race_structure"]
        self.assertEqual(block["version"], race_structure.RACE_STRUCTURE_VERSION)
        ids = self.world.location_name_to_id
        self.assertIn([ids[f"{TRACK}: CTR Token Challenge"], ids[f"{TRACK}: Trophy Race"]],
                      block["stage1_awards"])
        self.assertEqual(len(block["stage1_awards"]), 16)

    def test_win_logic_entries_match(self):
        from ..win_logic import wire_block
        block = wire_block(self.world)
        ids = self.world.location_name_to_id
        checks = block["checks"]
        trophy = checks.get(str(ids[f"{TRACK}: Trophy Race"]))
        ctr = checks.get(str(ids[f"{TRACK}: CTR Token Challenge"]))
        self.assertIsNotNone(trophy)
        self.assertIsNotNone(ctr)
        self.assertEqual((trophy["kind"], ctr["kind"]), ("trophy", "ctr"))
        self.assertEqual({k: v for k, v in trophy.items() if k != "kind"},
                         {k: v for k, v in ctr.items() if k != "kind"})


class TestCtrFirstBoost(TestCtrFirst):
    """Progressive Boost on: the CTR boost floor and the Trophy's finish terms
    both land on the shared term."""
    options = {"adventure_structure": "ctr_first", "lettersanity": "locations_only",
               "progressive_boost": "shared_global"}


class TestCtrFirstLettersanityItems(CTRTestBase):
    """Lettersanity mode 3: the CTR win needs the letter items, so the Trophy
    Race check does too."""
    options = {"adventure_structure": "ctr_first", "lettersanity": "items_only"}

    def test_trophy_needs_letter_items(self):
        from .. import lettersanity
        letters = tuple(lettersanity.item_name(TRACK, letter) for letter in lettersanity.LETTERS)
        state = CollectionState(self.multiworld)
        for it in self.multiworld.itempool:
            if it.player == self.player and it.advancement and it.name not in letters:
                state.collect(it, True)
        state.sweep_for_advancements()
        self.assertFalse(_loc(self.world, f"{TRACK}: Trophy Race").can_reach(state))
        for name in letters:
            state.collect(self.world.create_item(name), True)
        self.assertTrue(_loc(self.world, f"{TRACK}: Trophy Race").can_reach(state))


class TestCtrFirstUsfFinishRungs(CTRTestBase):
    """The CTR Challenge's finishing place earns the rungs, letters or not
    (decision 14), so a USF track's finish rungs need the USF finish, not
    the CTR win's letter items."""
    options = {"adventure_structure": "ctr_first", "lettersanity": "items_only",
               "progressive_boost": "shared_global"}

    def test_finish_rung_does_not_wait_for_letters(self):
        from .. import lettersanity
        from ..podium import FINISH_RUNG_KEYS, location_name
        from ..usf_finish import USF_FINISH_TRACKS
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        tried = 0
        for track in sorted(USF_FINISH_TRACKS):
            rungs = [location_name(track, k) for k in sorted(FINISH_RUNG_KEYS)
                     if location_name(track, k) in names]
            if not rungs or f"{track}: Trophy Race" not in names:
                continue
            letters = {lettersanity.item_name(track, letter) for letter in lettersanity.LETTERS}
            state = CollectionState(self.multiworld)
            for it in self.multiworld.itempool:
                if it.player == self.player and it.advancement and it.name not in letters:
                    state.collect(it, True)
            state.sweep_for_advancements()
            self.assertFalse(_loc(self.world, f"{track}: Trophy Race").can_reach(state), track)
            for rung in rungs:
                self.assertTrue(_loc(self.world, rung).can_reach(state), rung)
            tried += 1
        self.assertGreater(tried, 0)


class TestCtrFirstNarrowStartHint(TestCtrFirstLettersanityItems):
    """The narrow-start guard names ctr_first with letter items as the cause.
    A real seed with no free check is refused earlier by the item supply
    check; this pins the message the guard gives when it is the one to stop."""

    def test_message(self):
        from unittest import mock
        from .. import sphere0_guard
        with mock.patch.object(sphere0_guard, "sphere0_breadth", return_value=0):
            with self.assertRaisesRegex(OptionError, "ctr_first"):
                sphere0_guard.raise_if_narrow(self.world)


class TestCtrFirstTrialTracks(CTRTestBase):
    options = {"adventure_structure": "ctr_first",
               "slide_coliseum_races": "trophy_and_ctr_challenge",
               "turbo_track_races": "trophy_and_ctr_challenge"}

    def test_trial_pairs_included(self):
        self.assertEqual(len(race_structure.stage1_pairs(self.world)), 18)


class TestCtrFirstCortexVortex(CTRTestBase):
    options = {"adventure_structure": "ctr_first", "cortex_vortex_track": True}

    def test_cortex_pair_included(self):
        names = [t for t, _c in race_structure.stage1_pairs(self.world)]
        self.assertIn("Cortex Vortex: Trophy Race", names)


class TestCtrFirstTrialFallback(CTRTestBase):
    """Decision 4: a trial track on trophy_race in a ctr_first seed is a
    classic track. Its Trophy Race keeps its own rule, it is in no award
    pair, and the retail tracks still pair."""
    options = {"adventure_structure": "ctr_first",
               "slide_coliseum_races": "trophy_race",
               "turbo_track_races": "trophy_and_ctr_challenge"}

    def test_fallback_and_pairs(self):
        self.assertEqual(race_structure.classic_fallbacks(self.world), ["Slide Coliseum"])
        pairs = race_structure.stage1_pairs(self.world)
        self.assertEqual(len(pairs), 17)
        self.assertNotIn("Slide Coliseum: Trophy Race", [t for t, _c in pairs])
        block = race_structure.race_structure_block(self.world)
        sc = _loc(self.world, "Slide Coliseum: Trophy Race").address
        self.assertNotIn(sc, [t for _c, t in block["stage1_awards"]])

    def test_fallback_trophy_needs_no_ctr_terms(self):
        """The classic Trophy is reachable with the items that reach any
        retail Trophy; nothing ties it to a CTR win."""
        state = CollectionState(self.multiworld)
        for it in self.multiworld.itempool:
            if it.player == self.player and it.advancement:
                state.collect(it, True)
        state.sweep_for_advancements()
        self.assertTrue(_loc(self.world, "Slide Coliseum: Trophy Race").can_reach(state))


class TestRestoredBlockFallback(TestCtrFirstTrialFallback):
    """Universal Tracker on a seed with a classic fallback track: the room's
    block must leave that track out, as the rebuilt one does."""

    def _passthrough(self, saved):
        self.multiworld.re_gen_passthrough = {self.world.game: {"race_structure": saved}}
        try:
            race_structure.check_tracker_block(self.world)
        finally:
            del self.multiworld.re_gen_passthrough

    def test_matching_block_passes(self):
        self._passthrough(race_structure.race_structure_block(self.world))

    def test_block_pairing_the_fallback_track_refused(self):
        """A room generated with Slide Coliseum on trophy_and_ctr_challenge
        pairs it; tracking it with a trophy_race YAML must refuse."""
        block = race_structure.race_structure_block(self.world)
        sc = _loc(self.world, "Slide Coliseum: Trophy Race").address
        saved = dict(block, stage1_awards=block["stage1_awards"] + [[sc + 100000, sc]])
        with self.assertRaises(OptionError):
            self._passthrough(saved)


class TestRefusals(unittest.TestCase):
    def _gen(self, **options):
        from worlds import AutoWorld
        from test.general import setup_solo_multiworld
        from .. import ctrAPWorld
        from Options import PerGameCommonOptions  # noqa: F401
        from argparse import Namespace
        from BaseClasses import MultiWorld
        from Generate import get_seed_name  # noqa: F401
        mw = MultiWorld(1)
        mw.game[1] = ctrAPWorld.game
        mw.player_name = {1: "Tester"}
        mw.set_seed(1)
        args = Namespace()
        for name, option in AutoWorld.AutoWorldRegister.world_types[ctrAPWorld.game].options_dataclass.type_hints.items():
            setattr(args, name, {1: option.from_any(options.get(name, option.default))})
        mw.set_options(args)
        mw.state = CollectionState(mw)
        from worlds.AutoWorld import call_all
        for step in ("generate_early", "create_regions", "create_items", "set_rules"):
            call_all(mw, step)
        return mw

    def test_trial_trophy_only_falls_back(self):
        """Decision 4 (2026-10-28): a track without a CTR Challenge keeps
        the classic order inside a ctr_first seed instead of refusing."""
        mw = self._gen(adventure_structure="ctr_first", slide_coliseum_races="trophy_race")
        world = mw.worlds[1]
        self.assertIn("Slide Coliseum", race_structure.classic_fallbacks(world))

    def test_content_plans_take_ctr_first(self):
        """Job J11: content plans carry ctr_first in the plan
        (test_content_ctr_first); the old refusal is gone."""
        self.assertFalse(hasattr(race_structure, "raise_if_content_plan"))

    def test_classic_trial_trophy_only_allowed(self):
        self._gen(slide_coliseum_races="trophy_race")


class TestRestoredBlock(TestCtrFirst):
    """Universal Tracker compares the room's block with the rebuilt one."""

    def test_matching_block_passes(self):
        block = race_structure.race_structure_block(self.world)
        race_structure.raise_if_restored_block_differs(self.world, {"race_structure": block})

    def test_tuple_block_passes(self):
        """The Tracker hands JSON arrays back as tuples."""
        block = race_structure.race_structure_block(self.world)
        saved = dict(block, stage1_awards=tuple(tuple(p) for p in block["stage1_awards"]))
        race_structure.raise_if_restored_block_differs(self.world, {"race_structure": saved})

    def test_missing_or_mismatched_block_refused(self):
        block = race_structure.race_structure_block(self.world)
        with self.assertRaises(OptionError):
            race_structure.raise_if_restored_block_differs(self.world, {})
        with self.assertRaises(OptionError):
            race_structure.raise_if_restored_block_differs(
                self.world, {"race_structure": dict(block, version=2)})
        with self.assertRaises(OptionError):
            race_structure.raise_if_restored_block_differs(
                self.world, {"race_structure": dict(block, version=True)})
        with self.assertRaises(OptionError):
            race_structure.raise_if_restored_block_differs(
                self.world, {"race_structure": dict(block, stage1_awards=block["stage1_awards"][1:])})


class TestRestore(unittest.TestCase):
    def _options(self):
        class V:
            value = None

        class O:
            adventure_structure = V()
            race_type_selector = type("W", (), {"value": None})()
        return O

    def test_absent_is_classic_always(self):
        o = self._options()
        race_structure.restore_slot_data(o, {})
        self.assertEqual(o.adventure_structure.value, race_structure.CLASSIC)
        self.assertEqual(o.race_type_selector.value, 1)

    def test_present(self):
        o = self._options()
        race_structure.restore_slot_data(
            o, {"adventure_structure": "ctr_first", "race_type_selector": "productive"})
        self.assertEqual(o.adventure_structure.value, race_structure.CTR_FIRST)
        self.assertEqual(o.race_type_selector.value, 0)
