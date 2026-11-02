"""Generation and wire gates for Lettersanity (#148)."""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import lettersanity
from ..lettersanity import (LETTERSANITY_CLASS, ITEM_NAMES, LETTER_TRACKS,
                            LETTERS, item_name)
from ..item_boxes import TIGER_TEMPLE_DOOR_OPENERS

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=148, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _wrapper_chain(rule):
    """The rule objects a composed access rule wraps, outermost first.

    Every layer in `Rules.py` keeps its inner rule as the first default
    argument (`previous=` / `base=`), so following `__defaults__[0]` walks the
    composition. Used to assert reuse BY REFERENCE without hard-coding how many
    layers a given seed installs."""
    chain = []
    while callable(rule):
        chain.append(rule)
        defaults = getattr(rule, "__defaults__", None) or ()
        if not defaults or not callable(defaults[0]):
            break
        rule = defaults[0]
    return chain


def _chain_index(chain, target):
    for index, rule in enumerate(chain):
        if rule is target:
            return index
    return None


def _letter_pairs(mw, world):
    """All created letter locations with their own item, as (loc_name, item_name).

    Built from the seed's resolved per-track selection, the single source that
    location creation, item creation and rules all share."""
    pairs = []
    for track in LETTER_TRACKS:
        for letter in world.options._lettersanity_selected.get(track, ()):
            loc = LETTERSANITY_CLASS.location_name(track, letter)
            if loc in mw.regions.location_cache[1]:
                pairs.append((loc, item_name(track, letter)))
    return pairs


def _collect_all(mw, exclude=None):
    """A CollectionState holding every item in the itempool, optionally minus
    one excluded item name or a collection of names. Used to build a full-
    collection state for rule-composition tests without running a real fill."""
    excluded = ({exclude} if isinstance(exclude, str)
                else set(exclude or ()))
    st = CollectionState(mw)
    for item in mw.itempool:
        if item.name in excluded:
            continue
        st.add_item(item.name, 1, 1)
    return st


class TestLettersanityShapes(unittest.TestCase):
    def _counts(self, mode, count=3):
        mw = _build(lettersanity=mode, letters_per_track=count)
        world = mw.worlds[1]
        locations = [name for name in LETTERSANITY_CLASS.names()
                     if name in mw.regions.location_cache[1]]
        items = [item.name for item in mw.itempool if item.name in ITEM_NAMES]
        return world, locations, items

    def test_off(self):
        world, locations, items = self._counts("off")
        self.assertEqual((locations, items), ([], []))
        self.assertNotIn("lettersanity_checks", world.fill_slot_data())



    def test_items_only_uses_all_letters(self):
        _world, locations, items = self._counts("items_only", 1)
        self.assertEqual(locations, [])
        self.assertEqual(set(items), set(ITEM_NAMES))





class TestTigerTempleLetterRDoorRule(unittest.TestCase):
    """Issue #323: Tiger Temple R shares Item Box 5's shortcut door."""

    @staticmethod
    def _rule(mw, letter):
        name = LETTERSANITY_CLASS.location_name("Tiger Temple", letter)
        return mw.get_location(name, 1).access_rule

    @staticmethod
    def _without_openers(mw, *also_excluded):
        return _collect_all(
            mw, exclude=set(TIGER_TEMPLE_DOOR_OPENERS) | set(also_excluded))

    def test_itemsanity_requires_any_one_door_opener(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    itemsanity=True)
        rule = self._rule(mw, "R")
        self.assertFalse(rule(self._without_openers(mw)))

        for opener in TIGER_TEMPLE_DOOR_OPENERS:
            with self.subTest(opener=opener):
                state = self._without_openers(mw)
                state.add_item(opener, 1, 1)
                self.assertTrue(rule(state))

    def test_c_and_t_are_not_door_gated(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    itemsanity=True)
        state = self._without_openers(mw)
        self.assertTrue(self._rule(mw, "C")(state))
        self.assertTrue(self._rule(mw, "T")(state))
        self.assertFalse(self._rule(mw, "R")(state))

    def test_itemsanity_off_keeps_existing_reachability(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    itemsanity=False)
        self.assertTrue(self._rule(mw, "R")(_collect_all(mw)))

    def test_mode_2_composes_own_letter_and_door_opener(self):
        mw = _build(lettersanity="locations_and_items", letters_per_track=3,
                    itemsanity=True)
        rule = self._rule(mw, "R")
        own = item_name("Tiger Temple", "R")

        state = self._without_openers(mw)
        self.assertFalse(rule(state))
        state.add_item(TIGER_TEMPLE_DOOR_OPENERS[0], 1, 1)
        self.assertTrue(rule(state))

        missing_own = self._without_openers(mw, own)
        missing_own.add_item(TIGER_TEMPLE_DOOR_OPENERS[0], 1, 1)
        self.assertFalse(rule(missing_own))

    def test_universal_tracker_regeneration_has_the_same_gate(self):
        source = _build(lettersanity="locations_only", letters_per_track=3,
                        itemsanity=True)
        wire = source.worlds[1].fill_slot_data()

        from worlds.AutoWorld import call_all
        tracker = setup_multiworld(ctrAPWorld, steps=(), seed=20260903)
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in STEPS:
            call_all(tracker, step)

        for label, mw in (("source", source), ("tracker", tracker)):
            with self.subTest(world=label):
                rule = self._rule(mw, "R")
                state = self._without_openers(mw)
                self.assertFalse(rule(state))
                state.add_item(TIGER_TEMPLE_DOOR_OPENERS[0], 1, 1)
                self.assertTrue(rule(state))


class TestOxideStationLetterBoostRule(unittest.TestCase):
    """The hard-knowledge finish shortcut does not reach physical T or R."""

    def test_token_and_created_letters_keep_distinct_route_requirements(self):
        for mode in ("off", "locations_only", "locations_and_items", "items_only"):
            with self.subTest(mode=mode):
                mw = _build(seed=335, lettersanity=mode, letters_per_track=3,
                            shortcut_knowledge="hard",
                            progressive_boost="shared_global", box_locations=True)
                token = mw.get_location("Oxide Station: CTR Token Challenge", 1)
                trophy = mw.get_location("Oxide Station: Trophy Race", 1)
                letters = [mw.get_location(
                    LETTERSANITY_CLASS.location_name("Oxide Station", letter), 1)
                    for letter in ("C", "T", "R") if mode in
                    ("locations_only", "locations_and_items")]
                no_boost = _collect_all(mw, exclude="Progressive Boost")
                self.assertTrue(trophy.access_rule(no_boost))
                self.assertFalse(token.access_rule(no_boost))
                for loc in letters:
                    self.assertEqual(loc.access_rule(no_boost), loc.name.endswith("Letter C"))
                no_boost.add_item("Progressive Boost", 1, 1)
                self.assertFalse(token.access_rule(no_boost))
                for loc in letters:
                    self.assertEqual(loc.access_rule(no_boost), loc.name.endswith("Letter C"))
                no_boost.add_item("Progressive Boost", 1, 1)
                self.assertTrue(token.access_rule(no_boost))
                self.assertTrue(all(loc.access_rule(no_boost) for loc in letters))

    def test_unrandomized_boost_keeps_vanilla_routes(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    shortcut_knowledge="hard", progressive_boost="off")
        state = _collect_all(mw)
        self.assertTrue(mw.get_location(
            "Oxide Station: CTR Token Challenge", 1).access_rule(state))
        for letter in ("C", "T", "R"):
            self.assertTrue(mw.get_location(
                LETTERSANITY_CLASS.location_name("Oxide Station", letter),
                1).access_rule(state))


    def test_universal_tracker_rebuilds_the_same_t_and_r_gates(self):
        source = _build(seed=335, lettersanity="locations_and_items",
                        letters_per_track=3, shortcut_knowledge="hard",
                        progressive_boost="shared_global", box_locations=True)
        tracker = setup_multiworld(ctrAPWorld, steps=(), seed=999)
        tracker.re_gen_passthrough = {ctrAPWorld.game: source.worlds[1].fill_slot_data()}
        from worlds.AutoWorld import call_all
        for step in STEPS:
            call_all(tracker, step)
        for label, mw in (("source", source), ("tracker", tracker)):
            with self.subTest(world=label):
                for name in ("Oxide Station: CTR Token Challenge",
                             LETTERSANITY_CLASS.location_name("Oxide Station", "T"),
                             LETTERSANITY_CLASS.location_name("Oxide Station", "R")):
                    state = _collect_all(mw, exclude="Progressive Boost")
                    loc = mw.get_location(name, 1)
                    self.assertFalse(loc.access_rule(state))
                    state.add_item("Progressive Boost", 1, 1)
                    self.assertFalse(loc.access_rule(state))
                    state.add_item("Progressive Boost", 1, 1)
                    self.assertTrue(loc.access_rule(state))


class TestPapuPyramidLetterCapabilityRules(unittest.TestCase):
    """Papu's Pyramid C and T need boost, Turbo, or Mask."""

    @staticmethod
    def _rule(mw, letter):
        name = LETTERSANITY_CLASS.location_name("Papu's Pyramid", letter)
        return mw.get_location(name, 1).access_rule

    @staticmethod
    def _without_routes(mw, *also_excluded):
        return _collect_all(
            mw, exclude={"Progressive Boost", "Turbo", "Mask",
                         *also_excluded})

    @staticmethod
    def _world(**options):
        defaults = {
            "lettersanity": "locations_only",
            "letters_per_track": 3,
            "logic_difficulty": "hard",
            "progressive_boost": "shared_global",
            "itemsanity": True,
        }
        defaults.update(options)
        return _build(**defaults)

    def test_c_and_t_each_accept_boost_turbo_or_mask(self):
        for difficulty in ("easy", "medium", "hard"):
            mw = self._world(logic_difficulty=difficulty)
            for letter in ("C", "T"):
                rule = self._rule(mw, letter)
                self.assertFalse(rule(self._without_routes(mw)))
                for route in ("Progressive Boost", "Turbo", "Mask"):
                    with self.subTest(difficulty=difficulty, letter=letter,
                                      route=route):
                        state = self._without_routes(mw)
                        state.add_item(route, 1, 1)
                        self.assertTrue(rule(state))

    def test_r_is_not_given_the_c_and_t_gate(self):
        mw = self._world()
        self.assertTrue(self._rule(mw, "R")(self._without_routes(mw)))

    def test_itemsanity_off_leaves_only_randomized_boost_arm(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    logic_difficulty="hard",
                    progressive_boost="shared_global", itemsanity=False)
        for letter in ("C", "T"):
            rule = self._rule(mw, letter)
            state = _collect_all(mw, exclude="Progressive Boost")
            self.assertFalse(rule(state))
            state.add_item("Progressive Boost", 1, 1)
            self.assertTrue(rule(state))

    def test_progressive_boost_off_uses_vanilla_boost(self):
        mw = _build(lettersanity="locations_only", letters_per_track=3,
                    logic_difficulty="hard",
                    progressive_boost="off", itemsanity=True)
        state = _collect_all(mw, exclude={"Turbo", "Mask"})
        self.assertTrue(self._rule(mw, "C")(state))
        self.assertTrue(self._rule(mw, "T")(state))

    def test_mode_2_composes_own_letter_and_route(self):
        mw = _build(lettersanity="locations_and_items", letters_per_track=3,
                    logic_difficulty="hard",
                    progressive_boost="shared_global", itemsanity=True)
        for letter in ("C", "T"):
            own = item_name("Papu's Pyramid", letter)
            rule = self._rule(mw, letter)

            route_without_own = self._without_routes(mw, own)
            route_without_own.add_item("Mask", 1, 1)
            self.assertFalse(rule(route_without_own))

            route_with_own = self._without_routes(mw)
            route_with_own.add_item("Mask", 1, 1)
            self.assertTrue(rule(route_with_own))

    def test_universal_tracker_regeneration_has_the_same_gates(self):
        source = self._world()
        wire = source.worlds[1].fill_slot_data()

        from worlds.AutoWorld import call_all
        tracker = setup_multiworld(ctrAPWorld, steps=(), seed=20260903)
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in STEPS:
            call_all(tracker, step)

        for label, mw in (("source", source), ("tracker", tracker)):
            for letter in ("C", "T"):
                with self.subTest(world=label, letter=letter):
                    rule = self._rule(mw, letter)
                    state = self._without_routes(mw)
                    self.assertFalse(rule(state))
                    state.add_item("Turbo", 1, 1)
                    self.assertTrue(rule(state))






