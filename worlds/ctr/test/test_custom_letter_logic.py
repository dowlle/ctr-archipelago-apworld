"""Custom-track letters take the retail letter rule layers (ruling 2026-09-27).

A custom slot's letters sit inside that slot's CTR Token Challenge, so they
share the challenge's entry rule (Trophy Race reachable, stage 2 where the pad
has one, the pad's racer lock through the Trophy Race) and then get the
Lettersanity layers on top: the mode-2 own-letter guard, and letter item
receipts on the token. No per-letter physical gate is invented for them.
"""
import copy
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..custom_check_namespace import LETTERS, custom_check_name
from ..custom_tracks import BABY_T_PARK_CURRENT
from ..itemsanity import ITEM_NAMES
from ..lettersanity import LETTERSANITY_CLASS
from ..progressive_capability import track_required_character
from .test_lettersanity import _chain_index, _wrapper_chain

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
CUSTOM = "Custom Track 1"
RETAIL = "Dingo Canyon"  # same ruled capability group, no per-letter gate


def _custom_tracks():
    entry = copy.deepcopy(BABY_T_PARK_CURRENT)
    entry["modes"] = {"ctr_challenge": True}
    return {"baby-t-park": entry}


def _options(**overrides):
    options = {"progressive_boost": "shared_global", "itemsanity": True,
               "logic_difficulty": "medium", "lettersanity": "locations_only",
               "letters_per_track": 3, "include_gem_cups": True,
               "custom_tracks": _custom_tracks()}
    options.update(overrides)
    return options


def _build(seed=1, **overrides):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed,
                            options=_options(**overrides))


def _state(mw, boost=0, exclude=()):
    """Every item except boost and weapons (and `exclude`), plus `boost`."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if (item == BOOST or item.startswith(f"{BOOST} (")
                or item in ITEM_NAMES or item in exclude):
            continue
        state.add_item(item, PLAYER, 99)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item.endswith(f"({CUSTOM})") and item not in exclude:
            state.add_item(item, PLAYER, 1)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


def _custom_letters(mw):
    return sorted(loc.name for loc in mw.get_locations(PLAYER)
                  if loc.name.startswith(f"{CUSTOM}: Letter "))


def _reach(state, name):
    return state.can_reach(name, "Location", PLAYER)


class TestCustomLettersFollowTheirTrophyRace(unittest.TestCase):
    def test_unreachable_before_the_trophy_race_like_a_retail_letter(self):
        for seed in (1, 2, 3):
            mw = _build(seed=seed)
            letters = _custom_letters(mw)
            self.assertEqual(len(letters), 3)
            retail = [LETTERSANITY_CLASS.location_name(RETAIL, letter)
                      for letter in LETTERS]
            bare, usf = _state(mw), _state(mw, boost=2)
            trophy = f"{CUSTOM}: Trophy Race"
            self.assertFalse(_reach(bare, trophy))
            self.assertTrue(_reach(usf, trophy))
            for name in letters + retail:
                with self.subTest(seed=seed, location=name):
                    self.assertFalse(_reach(bare, name))
                    self.assertTrue(_reach(usf, name))

    def test_racer_lock_of_the_displaced_pad_reaches_the_letters(self):
        checked = 0
        for seed in range(1, 40):
            mw = _build(seed=seed, racer_locked_pads=True)
            racer = track_required_character(mw.worlds[PLAYER], CUSTOM)
            if racer is None:
                continue
            checked += 1
            without = _state(mw, boost=2, exclude=(racer,))
            for name in _custom_letters(mw):
                with self.subTest(seed=seed, location=name):
                    self.assertFalse(_reach(without, name))
                    self.assertTrue(_reach(_state(mw, boost=2), name))
            if checked == 2:
                break
        self.assertGreater(checked, 0, "no seed locked the displaced pad")

    def test_mode_2_keeps_the_own_letter_guard_on_the_entry_rule(self):
        mw = _build(lettersanity="locations_and_items")
        for name in _custom_letters(mw):
            own = custom_check_name("letter_item", 1,
                                    LETTERS.index(name[-1]))
            with self.subTest(location=name):
                self.assertFalse(_reach(_state(mw), name))
                self.assertFalse(_reach(_state(mw, boost=2, exclude=(own,)),
                                        name))
                self.assertTrue(_reach(_state(mw, boost=2), name))


class TestEveryCreatedLetterSharesItsChallengeEntry(unittest.TestCase):
    def test_parity_over_every_created_letter(self):
        """Every created letter location (retail, Cortex Vortex, custom)
        reuses, by reference, a rule object from its own CTR Token
        Challenge's wrapper chain."""
        for mode in ("locations_only", "locations_and_items"):
            mw = _build(lettersanity=mode, cortex_vortex_track=True)
            letters = [loc for loc in mw.get_locations(PLAYER)
                       if ": Letter " in loc.name]
            kinds = {loc.name.split(":")[0] for loc in letters}
            self.assertIn(CUSTOM, kinds)
            self.assertIn("Cortex Vortex", kinds)
            for loc in letters:
                track = loc.name.split(":")[0]
                token = mw.get_location(f"{track}: CTR Token Challenge", PLAYER)
                token_chain = _wrapper_chain(token.access_rule)
                shared = [rule for rule in _wrapper_chain(loc.access_rule)
                          if _chain_index(token_chain, rule) is not None]
                with self.subTest(mode=mode, location=loc.name):
                    self.assertTrue(shared, f"{loc.name} has no shared entry rule")


class TestUniversalTrackerBuildsTheSameCustomLetterRules(unittest.TestCase):
    def test_regeneration_matches(self):
        source = _build(seed=7, lettersanity="locations_and_items")
        wire = source.worlds[PLAYER].fill_slot_data()
        tracker = setup_multiworld(ctrAPWorld, steps=(), seed=7,
                                   options=_options(
                                       lettersanity="locations_and_items"))
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        tracker.generation_is_fake = True
        for step in STEPS:
            call_all(tracker, step)
        self.assertEqual(_custom_letters(tracker), _custom_letters(source))
        for label, mw in (("source", source), ("tracker", tracker)):
            for name in _custom_letters(mw):
                own = custom_check_name("letter_item", 1,
                                        LETTERS.index(name[-1]))
                with self.subTest(world=label, location=name):
                    self.assertFalse(_reach(_state(mw), name))
                    self.assertFalse(_reach(
                        _state(mw, boost=2, exclude=(own,)), name))
                    self.assertTrue(_reach(_state(mw, boost=2), name))


if __name__ == "__main__":
    unittest.main()
