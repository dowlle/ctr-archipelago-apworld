"""Direct predicate tests for the generalized Hit Character routes (tickets 07/08).

Ticket 06 proved one route; tickets 07 and 08 generalize it to every target.
This file tests the reusable predicate helpers directly, not only a green
accessibility seed:

  * the appearance-player sets under the pool draw (any racer but the target,
    narrowed by a racer lock);
  * the any-of trigger capture and proof;
  * route resolution through the shuffled destination -> physical pad map;
  * ordinary, boss and hit-method predicates;
  * player-character conflicts and alternative-character routes;
  * the structural `OptionError`s for impossible targets.

All-sixteen generation/reachability proofs live in test_hit_character_all16.py.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import characters, ctrAPWorld
from ..hit_character import (
    HIT_CHARACTER_CLASS,
    HIT_METHOD_ITEMS,
    ORDINARY_FIELD_SIZE,
    POLICY_SELF_CHARACTER,
    PURPLE_CUP_FIELD_SIZE,
    UNLOCK_TRIGGERS,
)

PLAYER = 1
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
ITEMS_STEPS = ("generate_early", "create_regions", "create_items")

TRIAL = {"slide_coliseum_races": "trophy_race",
         "turbo_track_races": "trophy_race"}
NO_SHUFFLE = {"warppad_unlock_requirements": "vanilla",
              "warp_pad_shuffle_categories": []}
TRACKS_SHUFFLE = {"warppad_unlock_requirements": "vanilla",
                  "warp_pad_shuffle_categories": ["tracks"]}


def _build(seed=1, steps=STEPS, **overrides):
    options = dict(TRIAL)
    options.update(overrides)
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


def _grant(state, world, *names):
    for name in names:
        state.collect(world.create_item(name), prevent_sweep=True)


def _hit_rule(mw, cid):
    return mw.get_location(
        HIT_CHARACTER_CLASS.location_name(cid), PLAYER).access_rule


def _all_items_state(mw):
    world = mw.worlds[PLAYER]
    state = CollectionState(mw)
    for item in mw.itempool:
        if item.player == PLAYER:
            state.collect(world.create_item(item.name), prevent_sweep=True)
    for item in mw.precollected_items.get(PLAYER, ()):
        state.collect(item, prevent_sweep=True)
    state.update_reachable_regions(PLAYER)
    return state


def _state_without_racer_unlocks(mw, *extra_excludes):
    """Every non-racer item (optionally minus extras), so pads are open but
    only the start racer is selectable."""
    world = mw.worlds[PLAYER]
    excluded = set(characters.ROSTER_CHARACTER_ID) | set(extra_excludes)
    state = CollectionState(mw)
    for item in mw.itempool:
        if item.player == PLAYER and item.name not in excluded:
            state.collect(world.create_item(item.name), prevent_sweep=True)
    for item in mw.precollected_items.get(PLAYER, ()):
        if item.name not in excluded:
            state.collect(item, prevent_sweep=True)
    state.update_reachable_regions(PLAYER)
    return state


def _state_without(mw, *excluded):
    """Every item in the pool except the named ones, with regions swept."""
    world = mw.worlds[PLAYER]
    state = CollectionState(mw)
    for item in mw.itempool:
        if item.player == PLAYER and item.name not in excluded:
            state.collect(world.create_item(item.name), prevent_sweep=True)
    for item in mw.precollected_items.get(PLAYER, ()):
        if item.name not in excluded:
            state.collect(item, prevent_sweep=True)
    state.update_reachable_regions(PLAYER)
    return state


class TestAppearancePlayers(unittest.TestCase):
    """Pool-draw appearance sets: any racer but the target, or the lock."""


    def test_field_sizes_are_the_contract_values(self):
        self.assertEqual(ORDINARY_FIELD_SIZE, 7)
        self.assertEqual(PURPLE_CUP_FIELD_SIZE, 4)


class TestTriggerProofs(unittest.TestCase):
    """Any-of trigger capture, from the frozen wire block."""


class TestPlayerCharacterConflict(unittest.TestCase):
    """A target that is the only selectable racer has no appearance route."""

    def test_default_target_as_only_player_is_unreachable(self):
        mw = _build(seed=1, hit_character=True,
                    starting_character="crash_bandicoot")
        world = mw.worlds[PLAYER]
        state = _state_without_racer_unlocks(mw)
        self.assertEqual(world.ctr_starting_character, "Crash Bandicoot")
        self.assertFalse(_hit_rule(mw, 0)(state))
        _grant(state, world, "Coco Bandicoot")
        self.assertTrue(_hit_rule(mw, 0)(state))

    def test_guest_target_as_only_player_is_unreachable(self):
        mw = _build(seed=1, hit_character=True,
                    starting_character="fake_crash")
        world = mw.worlds[PLAYER]
        state = _state_without_racer_unlocks(mw)
        self.assertEqual(world.ctr_starting_character, "Fake Crash")
        self.assertFalse(_hit_rule(mw, 14)(state))
        _grant(state, world, "Crash Bandicoot")
        self.assertTrue(_hit_rule(mw, 14)(state))

    def test_alternative_racer_route_needs_a_second_racer(self):
        mw = _build(seed=1, hit_character=True,
                    starting_character="penta_penguin")
        world = mw.worlds[PLAYER]
        state = _state_without_racer_unlocks(mw)
        self.assertFalse(_hit_rule(mw, 13)(state))
        _grant(state, world, "N. Tropy")
        self.assertTrue(_hit_rule(mw, 13)(state))


class TestBossAndMethodPredicates(unittest.TestCase):
    """Boss routes are not gated by the clear; the hit method is per seed."""


    def test_itemsanity_off_needs_no_weapon_item(self):
        mw = _build(seed=1, hit_character=True, itemsanity=False)
        state = _all_items_state(mw)
        for cid in range(16):
            with self.subTest(engine_id=cid):
                self.assertTrue(_hit_rule(mw, cid)(state))

    def test_itemsanity_on_requires_a_selected_method(self):
        mw = _build(seed=1, hit_character=True, itemsanity=True)
        world = mw.worlds[PLAYER]
        state = _state_without_racer_unlocks(mw, *HIT_METHOD_ITEMS)
        # No selected method held: the method gate closes every target.
        self.assertFalse(any(_hit_rule(mw, cid)(state) for cid in range(16)))
        _grant(state, world, "Bomb")
        # The method is now held; default racers need no trigger.
        self.assertTrue(any(_hit_rule(mw, cid)(state) for cid in range(8)))
        for item in ("Turbo", "N. Tropy Clock"):
            with self.subTest(item=item):
                solo = _state_without_racer_unlocks(mw, *HIT_METHOD_ITEMS)
                _grant(solo, world, item)
                self.assertFalse(any(_hit_rule(mw, cid)(solo)
                                     for cid in range(16)))
        for item in HIT_METHOD_ITEMS:
            with self.subTest(item=item):
                solo = _state_without_racer_unlocks(mw, *HIT_METHOD_ITEMS)
                _grant(solo, world, item)
                self.assertTrue(any(_hit_rule(mw, cid)(solo)
                                    for cid in range(8)))


class TestKeyFallbackRule(unittest.TestCase):
    """A guest with no unlock win in the seed: `Key >= N` plus any ordinary
    route replaces the trigger term (2026-09-18 ruling).

    Each arm is built so the guest has NO boss route either, which is what
    makes the Key term load-bearing rather than shadowed by a boss race.
    """

    #: guest engine id -> (Key count, build options, locations to remove).
    ARMS = {
        14: (1, {}, ("Crash Cove: Trophy Race", "Sewer Speedway: Trophy Race")),
        13: (2, {}, ("Blizzard Bluff: Trophy Race", "Polar Pass: Trophy Race")),
        12: (3, {"slide_coliseum_races": 0, "turbo_track_races": 0}, ()),
        15: (4, {"oxide_goal": "disabled", "bosses_required_goal": 2}, ()),
    }

    def _fallback_world(self, guest, extra=None):
        keys, options, pops = self.ARMS[guest]
        options = dict(options)
        options.update(extra or {})
        mw = _build(seed=1, steps=ITEMS_STEPS, hit_character=True, **options)
        cache = mw.regions.location_cache[PLAYER]
        for name in pops:
            cache.pop(name, None)
        call_all(mw, "set_rules")
        self.assertEqual(mw.worlds[PLAYER].ctr_hit_character_fallback,
                         {guest: keys})
        return mw, keys


    def test_a_guest_with_its_unlock_win_is_not_key_gated(self):
        """The unchanged rule: with the win in the seed the rule is the trigger
        proof, which is what holds here, and no Key term is installed."""
        mw = _build(seed=1, hit_character=True)
        self.assertEqual(mw.worlds[PLAYER].ctr_hit_character_fallback, {})
        self.assertTrue(_hit_rule(mw, 14)(_all_items_state(mw)))

    def test_no_fallback_guest_keeps_the_wire_field_absent(self):
        mw = _build(seed=1, hit_character=True)
        block = mw.worlds[PLAYER].ctr_hit_character_encounters
        for guest in range(8, 16):
            self.assertNotIn("fallback_keys",
                             block["unlock_triggers"][str(guest)])


class TestStructuralErrors(unittest.TestCase):
    """Impossible targets refuse generation with a clear OptionError."""

    def _items_world(self, **overrides):
        return _build(seed=1, steps=ITEMS_STEPS, hit_character=True, **overrides)


    def test_disabled_boss_route_falls_back_to_keys(self):
        """`oxide_goal: disabled` removes both Oxide races. Oxide now joins the
        pool at 4 Keys through the ordinary routes instead of raising."""
        mw = _build(seed=1, hit_character=True, oxide_goal="disabled",
                    bosses_required_goal=2)
        world = mw.worlds[PLAYER]
        self.assertEqual(world.ctr_hit_character_fallback, {15: 4})
        self.assertTrue(_hit_rule(mw, 15)(_all_items_state(mw)))


    def test_no_hit_location_reachability_recursion(self):
        mw = _build(seed=1, hit_character=True)
        state = _all_items_state(mw)
        from unittest import mock
        seen = []
        original = CollectionState.can_reach

        def spy(self, *args, **kwargs):
            if args and isinstance(args[0], str):
                seen.append(args[0])
            return original(self, *args, **kwargs)

        with mock.patch.object(CollectionState, "can_reach", spy):
            for cid in range(16):
                _hit_rule(mw, cid)(state)
        self.assertFalse([name for name in seen if name.startswith("Hit ")])


class TestSelectorStaticContract(unittest.TestCase):
    """STATIC wire contract only: triggers, policy and one order per destination.

    The draw itself is pinned by test_hit_pool_draw.py against the shared
    native vector fixture.
    """

    def test_static_trigger_and_policy_contract(self):
        from ..hit_character import build_encounters
        self.assertEqual(POLICY_SELF_CHARACTER, "never_seat_player")
        for seed in (0, 1, 0xDEADBEEF, 0xFFFFFFFF):
            block = build_encounters(seed)
            with self.subTest(seed=seed):
                self.assertEqual(sorted(block["tracks"]["3"]["order"]),
                                 list(range(16)))
                self.assertEqual(block["policy"]["self_character"],
                                 POLICY_SELF_CHARACTER)
                for guest, (codes, kind) in UNLOCK_TRIGGERS.items():
                    self.assertEqual(block["unlock_triggers"][str(guest)],
                                     {"kind": kind, "any_of": list(codes)})


if __name__ == "__main__":
    unittest.main()
