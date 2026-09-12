"""Direct predicate tests for the generalized Hit Character routes (tickets 07/08).

Ticket 06 proved one route; tickets 07 and 08 generalize it to every target.
This file tests the reusable predicate helpers directly, not only a green
accessibility seed:

  * the precomputed appearance-player sets for default racers (conservative
    guest-seat reservation) and for pinned guests;
  * the any-of trigger capture and proof;
  * route resolution through the shuffled destination -> physical pad map;
  * ordinary, boss and hit-method predicates;
  * player-character conflicts and alternative-character routes;
  * the structural `OptionError`s for impossible targets.

All-sixteen generation/reachability proofs live in test_hit_character_all16.py.
"""
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import characters, ctrAPWorld
from ..hit_character import (
    HIT_CHARACTER_CLASS,
    HIT_METHOD_ITEMS,
    ORDINARY_FIELD_SIZE,
    PIN_GUESTS,
    POLICY_SELF_CHARACTER,
    PURPLE_CUP_FIELD_SIZE,
    _default_appearance_players,
    _guest_appearance_players,
    install_rules,
    retail_route,
    trigger_proofs,
    trigger_rule,
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

#: A flat base list for the pure appearance-player tests.
BASE = tuple(range(8))
RACER_NAMES = tuple(characters.CHARACTER_ID_TO_NAME[b] for b in BASE)


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


def _proof_for(world, target_id, region_name):
    for region, rule in trigger_proofs(world, PLAYER, target_id):
        if region.name == region_name:
            return region, rule
    raise AssertionError(f"no trigger proof for {region_name!r}")


class TestAppearancePlayers(unittest.TestCase):
    """The conservative guest-seat reservation and pin appearance sets."""

    def test_default_in_guaranteed_prefix_accepts_any_other_player(self):
        players = _default_appearance_players(0, BASE, ORDINARY_FIELD_SIZE, None)
        self.assertEqual(set(players),
                         set(characters.ROSTER_CHARACTER_ID)
                         - {characters.CHARACTER_ID_TO_NAME[0]})

    def test_default_in_shift_in_seat_needs_a_prefix_player(self):
        # Target 6 is base[6] (the seat after the guaranteed six): only a
        # player drawn from the guaranteed prefix shifts it in.
        players = _default_appearance_players(6, BASE, ORDINARY_FIELD_SIZE, None)
        self.assertEqual(set(players), set(RACER_NAMES[:6]))
        self.assertNotIn(characters.CHARACTER_ID_TO_NAME[7], players)

    def test_default_last_base_seat_is_never_guaranteed(self):
        self.assertEqual(
            _default_appearance_players(7, BASE, ORDINARY_FIELD_SIZE, None), ())

    def test_default_locked_to_the_target_is_impossible(self):
        self.assertEqual(
            _default_appearance_players(
                0, BASE, ORDINARY_FIELD_SIZE,
                characters.CHARACTER_ID_TO_NAME[0]), ())

    def test_default_locked_to_another_racer_is_that_racer_only(self):
        cortex = characters.CHARACTER_ID_TO_NAME[1]
        self.assertEqual(
            _default_appearance_players(0, BASE, ORDINARY_FIELD_SIZE, cortex),
            (cortex,))
        # Target 7 can never be shifted in by a single removal.
        self.assertEqual(
            _default_appearance_players(7, BASE, ORDINARY_FIELD_SIZE, cortex),
            ())

    def test_guest_no_lock_accepts_any_other_player(self):
        target = characters.CHARACTER_ID_TO_NAME[14]
        players = _guest_appearance_players(target, None)
        self.assertEqual(set(players),
                         set(characters.ROSTER_CHARACTER_ID) - {target})

    def test_guest_locked_to_the_target_is_impossible(self):
        target = characters.CHARACTER_ID_TO_NAME[14]
        self.assertEqual(_guest_appearance_players(target, target), ())

    def test_guest_locked_to_another_racer_is_that_racer_only(self):
        target = characters.CHARACTER_ID_TO_NAME[14]
        penta = characters.CHARACTER_ID_TO_NAME[13]
        self.assertEqual(_guest_appearance_players(target, penta), (penta,))

    def test_purple_cup_field_size_is_the_contract_value(self):
        self.assertEqual(ORDINARY_FIELD_SIZE, 7)
        self.assertEqual(PURPLE_CUP_FIELD_SIZE, 4)


class TestTriggerProofs(unittest.TestCase):
    """Any-of trigger capture, from the frozen wire block."""

    def test_guest_captures_every_authoritative_trigger(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        names = {region.name for region, _ in trigger_proofs(world, PLAYER, 14)}
        self.assertEqual(names, {"Crash Cove", "Sewer Speedway"})
        names = {region.name for region, _ in trigger_proofs(world, PLAYER, 13)}
        self.assertEqual(names, {"Blizzard Bluff", "Polar Pass"})
        names = {region.name for region, _ in trigger_proofs(world, PLAYER, 12)}
        self.assertEqual(names, {"Slide Coliseum", "Turbo Track"})

    def test_boss_kind_guest_trigger_is_its_boss_race(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        proofs = trigger_proofs(world, PLAYER, 8)
        self.assertEqual({region.name for region, _ in proofs},
                         {"Pinstripe Garage"})

    def test_default_racers_have_no_invented_trigger(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        for cid in range(8):
            with self.subTest(engine_id=cid):
                self.assertEqual(trigger_proofs(world, PLAYER, cid), [])

    def test_trigger_rule_is_any_of(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        proofs = trigger_proofs(world, PLAYER, 14)
        rule = trigger_rule(proofs)
        state = _all_items_state(mw)
        self.assertTrue(rule(state))
        # Drop the first proof: the second alone still satisfies any-of.
        self.assertTrue(trigger_rule(proofs[1:])(state))
        self.assertFalse(trigger_rule(())(state))


class TestRouteResolution(unittest.TestCase):
    """Destination -> physical pad resolution and custom-displacement refusal."""

    def test_retail_route_resolves_the_shuffled_physical_pad(self):
        mw = _build(seed=21, hit_character=True, **TRACKS_SHUFFLE)
        world = mw.worlds[PLAYER]
        # With tracks shuffled, the pad that loads Crash Cove is not its own.
        self.assertNotEqual(world.ctr_pad_by_destination.get("Crash Cove"),
                            "Crash Cove Warp Pad")
        route = retail_route(world, PLAYER, "Crash Cove")
        self.assertIsNotNone(route)
        pad_name, hub, _rule = route
        self.assertEqual(pad_name, world.ctr_pad_by_destination["Crash Cove"])
        self.assertEqual(hub.name, mw.get_entrance(pad_name, PLAYER).parent_region.name)

    def test_retail_route_refuses_a_displaced_destination(self):
        mw = _build(seed=23, hit_character=True, **NO_SHUFFLE)
        world = mw.worlds[PLAYER]
        route = retail_route(world, PLAYER, "Crash Cove")
        entrance = mw.get_entrance(route[0], PLAYER)
        entrance.connected_region = mw.get_region("Menu", PLAYER)
        self.assertIsNone(retail_route(world, PLAYER, "Crash Cove"))

    def test_retail_route_refuses_a_missing_pad(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        world.ctr_pad_by_destination["Crash Cove"] = "Nonexistent Warp Pad"
        self.assertIsNone(retail_route(world, PLAYER, "Crash Cove"))


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

    def test_boss_route_is_reachable_before_the_clear(self):
        mw = _build(seed=1, steps=ITEMS_STEPS, hit_character=True)
        world = mw.worlds[PLAYER]
        # Lock the ordinary Pinstripe pin pad to Pinstripe itself, so only the
        # boss encounter can prove Hit Pinstripe.
        pad = world.ctr_pad_by_destination.get("Hot Air Skyway",
                                               "Hot Air Skyway Warp Pad")
        world.ctr_racer_locks = {pad: "Pinstripe"}
        call_all(mw, "set_rules")
        state = _state_without_racer_unlocks(mw)
        _grant(state, world, *(["Trophy"] * 16))
        self.assertTrue(_hit_rule(mw, 8)(state))

    def test_boss_hit_check_is_not_gated_by_its_own_clear(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        # A boss route predicate reads the boss race location, not the checked
        # state of that same location, so no trigger/clear term appears.
        from ..hit_character import _boss_predicate, _build_boss_routes
        block = world.ctr_hit_character_encounters
        routes = _build_boss_routes(world, PLAYER, 8, block)
        self.assertTrue(routes)
        state = _all_items_state(mw)
        self.assertTrue(any(_boss_predicate(r)(state) for r in routes))

    def test_boss_identity_substitution_moves_the_route(self):
        """The boss route reads the emitted `bosses` table, not a retyped map."""
        from ..hit_character import _build_boss_routes
        mw = _build(seed=1, steps=ITEMS_STEPS, hit_character=True)
        world = mw.worlds[PLAYER]
        block = dict(world.ctr_hit_character_encounters)
        block["bosses"] = dict(block["bosses"])
        block["bosses"]["35011103"] = 11  # Pinstripe's code now resolves to Joe
        joe = _build_boss_routes(world, PLAYER, 11, block)
        pinstripe = _build_boss_routes(world, PLAYER, 8, block)
        self.assertTrue(any(r.boss_region.name == "Pinstripe Garage"
                            for r in joe))
        self.assertFalse(any(r.boss_region.name == "Pinstripe Garage"
                             for r in pinstripe))

    def test_target_is_never_in_its_own_appearance_players(self):
        """Owning the target's playable unlock is never an appearance proof."""
        from ..hit_character import _build_ordinary_routes
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        block = world.ctr_hit_character_encounters
        for cid in range(16):
            target_name = characters.CHARACTER_ID_TO_NAME[cid]
            for route in _build_ordinary_routes(world, PLAYER, cid, block):
                with self.subTest(engine_id=cid, track=route.track):
                    self.assertNotIn(target_name, route.appearance_players)

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


class TestBossAccessRules(unittest.TestCase):
    """A boss route keeps BOTH the garage region and the race's access rule.

    Dropping either term must flip a Hit rule: the region is the garage
    requirement, and the location rule carries the encounter-specific terms
    (Oxide's Key/companion/relic gates).
    """

    def test_oxide_boss_route_requires_its_location_rule(self):
        mw = _build(seed=1, hit_character=True, oxide_goal="any_percent",
                    bosses_required_goal=4)
        world = mw.worlds[PLAYER]
        # Four Keys open the garage region, but the any-percent companion
        # terms gate the Oxide challenge itself.
        state = CollectionState(mw)
        _grant(state, world, *(["Key"] * 4))
        state.update_reachable_regions(PLAYER)
        self.assertTrue(
            mw.get_location("N. Oxide Garage: N. Oxide's Challenge",
                            PLAYER).parent_region.can_reach(state))
        self.assertFalse(_hit_rule(mw, 15)(state))
        # Satisfying the companions (all-state) restores the route.
        self.assertTrue(_hit_rule(mw, 15)(mw.get_all_state(False)))

    def test_lesser_boss_route_requires_its_garage_region(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        keys_only = CollectionState(mw)
        _grant(keys_only, world, *(["Key"] * 4))
        keys_only.update_reachable_regions(PLAYER)
        self.assertFalse(_hit_rule(mw, 8)(keys_only))
        with_trophies = CollectionState(mw)
        _grant(with_trophies, world, *(["Key"] * 4), *(["Trophy"] * 16))
        with_trophies.update_reachable_regions(PLAYER)
        self.assertTrue(_hit_rule(mw, 8)(with_trophies))


class TestStructuralErrors(unittest.TestCase):
    """Impossible targets refuse generation with a clear OptionError."""

    def _items_world(self, **overrides):
        return _build(seed=1, steps=ITEMS_STEPS, hit_character=True, **overrides)

    def test_missing_selected_location_raises(self):
        mw = self._items_world()
        mw.regions.location_cache[PLAYER].pop("Hit Nitros Oxide")
        with self.assertRaises(OptionError) as ctx:
            call_all(mw, "set_rules")
        self.assertIn("Nitros Oxide", str(ctx.exception))

    def test_no_created_trigger_raises(self):
        mw = self._items_world()
        cache = mw.regions.location_cache[PLAYER]
        cache.pop("Crash Cove: Trophy Race", None)
        cache.pop("Sewer Speedway: Trophy Race", None)
        with self.assertRaises(OptionError) as ctx:
            call_all(mw, "set_rules")
        self.assertIn("Fake Crash", str(ctx.exception))

    def test_all_pins_locked_to_the_target_raises(self):
        mw = self._items_world()
        world = mw.worlds[PLAYER]
        locks = {}
        for track in ("Crash Cove", "Sewer Speedway"):
            pad = world.ctr_pad_by_destination.get(track, f"{track} Warp Pad")
            locks[pad] = "Fake Crash"
        world.ctr_racer_locks = locks
        with self.assertRaises(OptionError) as ctx:
            call_all(mw, "set_rules")
        self.assertIn("Fake Crash", str(ctx.exception))

    def test_disabled_boss_route_with_no_alternative_raises(self):
        with self.assertRaises(OptionError) as ctx:
            _build(seed=1, hit_character=True, oxide_goal="disabled",
                   bosses_required_goal=4)
        self.assertIn("Nitros Oxide", str(ctx.exception))

    def test_displaced_route_leaves_the_other_pin_as_the_route(self):
        """A single displaced pin is not fatal: the other pin still proves it."""
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        pad = world.ctr_pad_by_destination.get("Crash Cove",
                                               "Crash Cove Warp Pad")
        entrance = mw.get_entrance(pad, PLAYER)
        entrance.connected_region = mw.get_region("Menu", PLAYER)
        install_rules(world, PLAYER)
        state = _all_items_state(mw)
        self.assertTrue(_hit_rule(mw, 14)(state))

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
    """STATIC contract only: the frozen pin table and the policy string.

    This does NOT verify the production selector, its growing eligible set, or
    the seating order under `never_seat_player` -- that is native's selector and
    the native worker owns the all-sixteen P1 verification. What is checked here
    is the immutable wire contract the native consumer reads.
    """

    def test_static_pin_and_policy_contract(self):
        from ..hit_character import build_encounters
        self.assertEqual(POLICY_SELF_CHARACTER, "never_seat_player")
        for seed in (0, 1, 0xDEADBEEF, 0xFFFFFFFF):
            block = build_encounters(seed)
            with self.subTest(seed=seed):
                self.assertEqual(block["tracks"]["3"]["pinned"], [14])
                self.assertNotIn(14, block["tracks"]["3"]["base"])
                self.assertEqual(block["policy"]["self_character"],
                                 POLICY_SELF_CHARACTER)
        self.assertEqual({cid: levels for cid, (levels, _c, _k)
                          in PIN_GUESTS.items()},
                         {8: (7,), 9: (5,), 10: (6,), 11: (1,),
                          12: (16, 17), 13: (2, 12), 14: (3, 8), 15: (13,)})


class TestBuildIdentity(unittest.TestCase):
    """The internal ticket-06 staging badge, without moving the pair identity."""

    def test_internal_slice_build_badge_and_numeric_versions(self):
        from ..version import BUILD_VERSION
        self.assertEqual(BUILD_VERSION, "0.2.1-hit-slice1")
        mw = _build(seed=1, hit_character=True)
        wire = mw.worlds[PLAYER].fill_slot_data()
        co = wire["ctr_options"]
        self.assertEqual(co["build_version"], "0.2.1-hit-slice1")
        self.assertEqual(co["world_version"], "0.2.1")
        self.assertEqual(co["schema_version"], 16)
        self.assertEqual(wire["schema_version"], 16)


if __name__ == "__main__":
    unittest.main()
