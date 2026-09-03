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

    def test_locations_only_counts(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                world, locations, items = self._counts("locations_only", count)
                self.assertEqual(len(locations), 16 * count)
                self.assertEqual(items, [])
                self.assertTrue(all(len(v) == count for v in world.options._lettersanity_selected.values()))

    def test_locations_and_items_counts(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                _world, locations, items = self._counts("locations_and_items", count)
                self.assertEqual(len(locations), 16 * count)
                self.assertEqual(len(items), 16 * count)

    def test_items_only_uses_all_letters(self):
        _world, locations, items = self._counts("items_only", 1)
        self.assertEqual(locations, [])
        self.assertEqual(set(items), set(ITEM_NAMES))

    def test_wire_uses_fixed_three_slot_arrays(self):
        world, _locations, _items = self._counts("locations_only", 2)
        block = world.fill_slot_data()["lettersanity_checks"]
        self.assertEqual(block["mode"], 1)
        self.assertEqual(block["letters_per_track"], 2)
        self.assertEqual(len(block["locations"]), len(LETTER_TRACKS))
        self.assertTrue(all(len(codes) == len(LETTERS) and codes.count(-1) == 1
                            for codes in block["locations"].values()))


class TestLettersanityUTRestoreParity(unittest.TestCase):
    """Universal Tracker regeneration (issue #29): the wire's mode,
    letters_per_track and per-track selection must round-trip through
    `_ut_restore_options` so a tracking client rebuilds the SAME world
    (independent review verified modes 0, 2 and 3)."""

    def _restored(self, wire_block, **build_options):
        from BaseClasses import CollectionState
        mw = _build(**build_options)
        world = mw.worlds[1]
        passthrough = {"ctr_options": {"lettersanity": wire_block.get("mode", 0)},
                       "lettersanity_checks": wire_block,
                       "warp_pad_unlock": {}, "podium_checks": {}}
        world._ut_restore_options(passthrough)
        return world.options.lettersanity.value, \
            world.options.letters_per_track.value, \
            dict(world.options._lettersanity_selected)

    def test_mode_0_round_trips(self):
        mode, count, selected = self._restored(
            {"mode": 0, "letters_per_track": 3,
             "locations": {str(lid): [-1, -1, -1]
                           for lid in lettersanity.TRACK_LEVEL_IDS.values()}})
        self.assertEqual(mode, 0)
        self.assertEqual(count, 3)
        # No live codes on the wire, so every track rebuilds an empty selection.
        self.assertEqual(set(selected), set(lettersanity.LETTER_TRACKS))
        self.assertTrue(all(sel == () for sel in selected.values()))

    def test_mode_2_selection_round_trips(self):
        mw = _build(lettersanity="locations_and_items", letters_per_track=2)
        world = mw.worlds[1]
        block = world.fill_slot_data()["lettersanity_checks"]
        mode, count, selected = self._restored(block, seed=7)
        self.assertEqual(mode, 2)
        self.assertEqual(count, 2)
        self.assertEqual(
            {track: set(letters) for track, letters in selected.items()},
            {track: set(letters)
             for track, letters in world.options._lettersanity_selected.items()})

    def test_mode_3_round_trips(self):
        mw = _build(lettersanity="items_only", letters_per_track=1)
        world = mw.worlds[1]
        block = world.fill_slot_data()["lettersanity_checks"]
        mode, count, selected = self._restored(block, seed=7)
        self.assertEqual(mode, 3)
        self.assertEqual(count, 1)
        # items_only emits all -1 location codes, so the rebuilt per-track
        # selection is all-empty (the restore mirrors exactly what the wire
        # carried, which for mode 3 carries no locations).
        self.assertTrue(all(sel == () for sel in selected.values()))


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


class TestLettersanityMode2SelfItemRules(unittest.TestCase):
    """The frozen mode-2 self-item access rule (dossier amendment, ruled
    2026-08-10), now ANDed onto the tier-2 term (parity audit family 2, ruled
    2026-08-12): each created letter location requires its own letter item AND
    the same reachability as its track's CTR Token Challenge (trophy race plus
    stage-2), so fill can never seat a letter at its own location and logic
    matches native pickup (letters only collide inside the token challenge)."""

    def _rules(self, count, seed=148):
        mw = _build(lettersanity="locations_and_items", letters_per_track=count,
                    seed=seed)
        world = mw.worlds[1]
        state = CollectionState(mw)
        return mw, world, state, _letter_pairs(mw, world)

    def test_rule_is_own_item_AND_token_challenge_reachability(self):
        """Mode 2 composition (parity audit family 2, ruling 2026-08-12): a
        letter location's rule must be `token-challenge tier-2 term AND own
        letter`, implemented BY REFERENCE so both the letter and the token
        challenge wrap the SAME tier-2 rule object.

        Verified three ways here: (a) the shared `previous` object identity, (b)
        the tier-2 term being live (a full collection satisfies it), and (c) the
        self-item term being live (dropping the own letter blocks it while
        dropping a DIFFERENT selected letter does not)."""
        for count in (1, 2, 3):
            with self.subTest(count=count):
                mw, world, _state, pairs = self._rules(count)
                own_by_loc = dict(pairs)
                for track in LETTER_TRACKS:
                    tc = mw.get_location(f"{track}: CTR Token Challenge", 1)
                    # The token challenge rule wraps the tier-2 term as its
                    # `previous` (defaults[0]); the letter rules must wrap that
                    # SAME object, never a re-written stage-2 term.
                    tier2_term = tc.access_rule.__defaults__[0]
                    for letter in world.options._lettersanity_selected[track]:
                        loc_name = LETTERSANITY_CLASS.location_name(track, letter)
                        own = own_by_loc[loc_name]
                        with self.subTest(loc=loc_name, count=count):
                            loc = mw.get_location(loc_name, 1)
                            self.assertIs(
                                loc.access_rule.__defaults__[0], tier2_term,
                                f"{loc_name} must reuse the token challenge's "
                                f"tier-2 rule object by reference")
                            # Full collection: tier-2 met, own held.
                            self.assertTrue(loc.access_rule(_collect_all(mw)))
                            # Dropping the own letter: self-item term blocks.
                            self.assertFalse(
                                loc.access_rule(_collect_all(mw, exclude=own)))
                            # Empty: tier-2 term blocks (nothing reachable).
                            self.assertFalse(
                                loc.access_rule(CollectionState(mw)))
                            # A different selected letter on the SAME track is
                            # NOT needed: the letter rule is `tier-2 AND own`,
                            # not the token challenge's letter-received term
                            # (pickup vs win).
                            others = [l for l in world.options._lettersanity_selected[track]
                                      if l != letter]
                            if others:
                                other = item_name(track, others[0])
                                self.assertTrue(
                                    loc.access_rule(_collect_all(mw, exclude=other)),
                                    f"{loc_name} must not require the token "
                                    f"challenge's other selected letter {other}")

    def test_no_cross_letter_item_satisfies_a_location_rule(self):
        mw, _world, state, pairs = self._rules(2)
        own_by_loc = dict(pairs)
        for loc_name, own in pairs:
            with self.subTest(loc=loc_name):
                for other, _other_own in pairs:
                    if other == loc_name:
                        continue
                    other_item = own_by_loc[other]
                    if other_item == own:
                        continue
                    st = CollectionState(mw)
                    st.add_item(other_item, 1, 1)
                    self.assertFalse(
                        mw.get_location(loc_name, 1).access_rule(st),
                        f"{loc_name} must not be satisfied by {other_item}")

    def test_inactive_locations_have_no_rule_and_do_not_enter_the_seed(self):
        mw, world, _state, pairs = self._rules(1)
        created = {name for name, _own in pairs}
        for track in LETTER_TRACKS:
            for letter in LETTERS:
                loc_name = LETTERSANITY_CLASS.location_name(track, letter)
                if loc_name in created:
                    continue
                self.assertNotIn(loc_name, mw.regions.location_cache[1])

    def test_modes_0_1_3_retain_structural_behavior(self):
        # Mode 0: nothing minted, no slot_data block.
        mw = _build(lettersanity="off")
        self.assertEqual([n for n in LETTERSANITY_CLASS.names()
                          if n in mw.regions.location_cache[1]], [])
        self.assertEqual([i.name for i in mw.itempool
                          if i.name in ITEM_NAMES], [])
        # Mode 1: locations but no items; letter locations carry the SAME rule
        # object as their track's CTR Token Challenge (no self-item term exists).
        mw1 = _build(lettersanity="locations_only", letters_per_track=2)
        world1 = mw1.worlds[1]
        self.assertEqual(len([n for n in LETTERSANITY_CLASS.names()
                              if n in mw1.regions.location_cache[1]]), 32)
        self.assertEqual([i.name for i in mw1.itempool
                          if i.name in ITEM_NAMES], [])
        for name, _own in _letter_pairs(mw1, world1):
            track = name.split(":")[0].strip()
            tc_rule = mw1.get_location(f"{track}: CTR Token Challenge", 1).access_rule
            with self.subTest(loc=name):
                # Identity (parity audit family 2, ruling 2026-08-12): a mode-1
                # letter location carries the EXACT SAME rule object as its
                # track's CTR Token Challenge -- the tier-2 term installed by
                # add_time_trial_and_ctr_requirements, never a re-written
                # stage-2 term. There is no self-item term in mode 1 (no items
                # exist), so identity is the whole story.
                self.assertIs(mw1.get_location(name, 1).access_rule, tc_rule)
        # Mode 3: items but no locations.
        mw3 = _build(lettersanity="items_only", letters_per_track=1)
        self.assertEqual([n for n in LETTERSANITY_CLASS.names()
                          if n in mw3.regions.location_cache[1]], [])
        self.assertEqual({i.name for i in mw3.itempool
                          if i.name in ITEM_NAMES}, set(ITEM_NAMES))


class TestLettersanityMode2NoSelfSeats(unittest.TestCase):
    """Direct fill regression: with the self-item rule written, a real
    `distribute_items_restrictive` never seats a letter item at its own letter
    location, across a deterministic seed sweep. This is the exact defect the
    independent review probed (13/60 seeds at count 2, 6/40 at count 3 before
    the fix)."""

    def _run_fill(self, count, seeds):
        from Fill import distribute_items_restrictive
        from test.general import gen_steps
        self_seats = []
        fills_ok = 0
        for seed in seeds:
            mw = setup_multiworld(ctrAPWorld, gen_steps, seed=seed,
                                  options={"lettersanity": "locations_and_items",
                                           "letters_per_track": count})
            distribute_items_restrictive(mw)
            fills_ok += 1
            world = mw.worlds[1]
            for loc_name, own in _letter_pairs(mw, world):
                item = mw.get_location(loc_name, 1).item
                if item is not None and item.name == own:
                    self_seats.append((seed, loc_name))
        return self_seats, fills_ok

    def test_no_self_seat_count_1(self):
        self_seats, ok = self._run_fill(1, range(3_000_000, 3_000_030))
        self.assertEqual(ok, 30)
        self.assertEqual(self_seats, [], "letter seated at its own location")

    def test_no_self_seat_count_2(self):
        # The review measured 13 self-seats across 60 seeds at count 2 pre-fix.
        self_seats, ok = self._run_fill(2, range(3_000_000, 3_000_060))
        self.assertEqual(ok, 60)
        self.assertEqual(self_seats, [], "letter seated at its own location")

    def test_no_self_seat_count_3(self):
        # The review measured 6 self-seats across 40 seeds at count 3 pre-fix.
        self_seats, ok = self._run_fill(3, range(3_000_000, 3_000_040))
        self.assertEqual(ok, 40)
        self.assertEqual(self_seats, [], "letter seated at its own location")


class TestLettersanityTier2NoStrandedFill(unittest.TestCase):
    """Parity audit family 2, fill-level probe: with the tier-2 term on the
    letter locations, accessibility:full generation must never seat a
    progression item at a letter location that is UNREACHABLE without that very
    item. Before the tier-2 fix a letter location was reachable at stage-1, so
    fill could seat a progression item there and strand it until the pad's
    stage-2 (native letters only collide inside the token challenge, whose entry
    the stage-2 lock forbids). After the fix the letter rule matches native, so
    a stranded seat would break its own reachability: removing the seated item
    must leave the location reachable.

    Probed across both location-bearing modes (1 and 2) and a deterministic
    seed sweep, with `accessibility: full` (the default). The 130-seed self-seat
    sweep above shares the same generation path; this adds the reachability
    assertion that the tier-2 term is actually live at fill time."""

    def _run_fill(self, mode, count, seeds):
        from Fill import distribute_items_restrictive
        from test.general import gen_steps
        stranded = []
        fills_ok = 0
        for seed in seeds:
            mw = setup_multiworld(ctrAPWorld, gen_steps, seed=seed,
                                  options={"lettersanity": mode,
                                           "letters_per_track": count})
            distribute_items_restrictive(mw)
            fills_ok += 1
            world = mw.worlds[1]
            for track in LETTER_TRACKS:
                for letter in world.options._lettersanity_selected.get(track, ()):
                    loc_name = LETTERSANITY_CLASS.location_name(track, letter)
                    if loc_name not in mw.regions.location_cache[1]:
                        continue
                    loc = mw.get_location(loc_name, 1)
                    seated = loc.item
                    if seated is None or not seated.advancement:
                        continue
                    # Reachable without the item seated here?
                    reachable_without = CollectionState(mw)
                    for other_loc in mw.get_locations(1):
                        other = other_loc.item
                        if other is None or other_loc.name == loc_name:
                            continue
                        reachable_without.add_item(other.name, 1, 1)
                    if not loc.can_reach(reachable_without):
                        stranded.append((seed, loc_name, seated.name))
        return stranded, fills_ok

    def test_mode2_no_stranded_progression_seat(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                stranded, ok = self._run_fill(2, count,
                                              range(4_000_000, 4_000_020))
                self.assertEqual(ok, 20)
                self.assertEqual(
                    stranded, [],
                    "progression item seated at a letter location that is "
                    "unreachable without that item")

    def test_mode1_no_stranded_progression_seat(self):
        stranded, ok = self._run_fill(1, 2, range(4_000_000, 4_000_020))
        self.assertEqual(ok, 20)
        self.assertEqual(
            stranded, [],
            "progression item seated at a mode-1 letter location that is "
            "unreachable without that item")
