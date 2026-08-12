"""Generation and wire gates for Lettersanity (#148)."""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import lettersanity
from ..lettersanity import (LETTERSANITY_CLASS, ITEM_NAMES, LETTER_TRACKS,
                            LETTERS, item_name)

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


class TestLettersanityMode2SelfItemRules(unittest.TestCase):
    """The frozen mode-2 self-item access rule (dossier amendment, ruled
    2026-08-10): each created letter location requires its OWN letter item, so
    fill can never seat a letter at its own location (circular-unreachable
    under native pickup gating, the independent review's REJECT finding)."""

    def _rules(self, count, seed=148):
        mw = _build(lettersanity="locations_and_items", letters_per_track=count,
                    seed=seed)
        world = mw.worlds[1]
        state = CollectionState(mw)
        return mw, world, state, _letter_pairs(mw, world)

    def test_every_active_mode2_location_requires_its_own_item(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                mw, _world, state, pairs = self._rules(count)
                self.assertTrue(pairs, f"count {count} created no letter pairs")
                for loc_name, own in pairs:
                    loc = mw.get_location(loc_name, 1)
                    with self.subTest(loc=loc_name):
                        # Empty inventory: unreachable.
                        self.assertFalse(loc.access_rule(state))
                        # Its own item: reachable.
                        own_state = CollectionState(mw)
                        own_state.add_item(own, 1, 1)
                        self.assertTrue(loc.access_rule(own_state))

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
        # Mode 1: locations but no items; letter locations stay open (no
        # self-item rule can apply, no items exist).
        mw1 = _build(lettersanity="locations_only", letters_per_track=2)
        world1 = mw1.worlds[1]
        self.assertEqual(len([n for n in LETTERSANITY_CLASS.names()
                              if n in mw1.regions.location_cache[1]]), 32)
        self.assertEqual([i.name for i in mw1.itempool
                          if i.name in ITEM_NAMES], [])
        state1 = CollectionState(mw1)
        for name, _own in _letter_pairs(mw1, world1):
            self.assertTrue(
                mw1.get_location(name, 1).access_rule(state1),
                f"mode 1 {name} must stay open (no letter items exist)")
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
