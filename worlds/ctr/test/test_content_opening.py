"""The opening of a content plan (one generator row 8b): the search, the plan's
reach model against the real rules, the redraw, and the seating."""
import unittest
from unittest import mock

from BaseClasses import CollectionState
from worlds.AutoWorld import call_all
from Fill import distribute_items_restrictive

from .. import content_opening, content_plan, sphere0_guard
from .test_content_plan import make_world

VANILLA = dict(warppad_unlock_requirements="vanilla")
TIGHT = dict(VANILLA, shuffle_keys=False, podium_rungs=[], progressive_boost="shared_global")
LETTERS = dict(TIGHT, adventure_structure="ctr_first", lettersanity="locations_and_items", shuffle_gems=False)


def spots(start, gates):
    """`room` of a start of `start` spots and gates of ({name: count}, spots)."""
    def room(held):
        return start + sum(gain for need, gain in gates if all(held.count(n) >= c for n, c in need.items()))
    return room


class TestSearch(unittest.TestCase):
    def test_a_wide_start_needs_nothing(self):
        self.assertEqual(content_opening.search(dict(Key=4), spots(5, []), 5), ([], 5))

    def test_a_gate_of_several_items_is_taken_whole(self):
        names, room = content_opening.search(dict(Trophy=4, Boost=1), spots(2, [(dict(Trophy=1, Boost=1), 8)]), 5)
        self.assertEqual(sorted(names), ["Boost", "Trophy"])
        self.assertEqual(room, 8)

    def test_a_gate_that_needs_more_than_the_start_is_no_step(self):
        self.assertEqual(content_opening.search(dict(Trophy=4), spots(2, [(dict(Trophy=3), 8)]), 5), ([], 2))

    def test_each_step_pays_for_the_next(self):
        gates = [(dict(Trophy=1), 2), (dict(Trophy=2, Key=1), 8)]
        names, room = content_opening.search(dict(Trophy=4, Key=1), spots(1, gates), 5)
        self.assertEqual(sorted(names), ["Key", "Trophy", "Trophy"])
        self.assertEqual(room, 8)

    def test_a_gate_of_three_different_items_is_a_group(self):
        names, room = content_opening.search(dict(Red=1, Blue=1, Green=1), spots(3, [(dict(Red=1, Blue=1, Green=1), 8)]), 5)
        self.assertEqual(sorted(names), ["Blue", "Green", "Red"])
        self.assertEqual(room, 8)

    def test_a_gate_of_a_mixed_group_opens(self):
        gate = dict(Trophy=2, Racer=1, Boost=1)
        names, room = content_opening.search(dict(Trophy=4, Racer=1, Boost=1), spots(4, [(gate, 9)]), 5)
        self.assertEqual(sorted(names), ["Boost", "Racer", "Trophy", "Trophy"])
        self.assertEqual(room, 9)

    def test_the_probe_budget_bounds_the_groups(self):
        calls = []

        def room(held):
            calls.append(held)
            return 7

        content_opening.search({f"Item {n}": 3 for n in range(14)}, room, 9, probes=300)
        self.assertLess(len(set(calls)), 340)

    def test_the_search_stops_at_its_target(self):
        names, room = content_opening.search(dict(Key=4), spots(1, [(dict(Key=1), 6), (dict(Key=2), 90)]), 5)
        self.assertEqual((names, room), (["Key"], 6))

    def test_a_useless_item_is_not_seated(self):
        self.assertEqual(content_opening.search(dict(Relic=9), spots(3, []), 5), ([], 3))


class TestPlanReach(unittest.TestCase):
    def assert_matches(self, options, seeds):
        for seed in seeds:
            world = make_world(dict(options), seed=seed, stop_before="pre_fill")
            mw = world.multiworld
            plan = world.ctr_content_plan
            boost = sphere0_guard.starting_boost_item(world) if plan.get("capability", {}).get("boost_mode") else None
            reach = content_opening.PlanReach(plan, world.ctr_content_items.rows, set(), boost)
            state = sphere0_guard._base_state(world)
            pool = {}
            for item in mw.itempool:
                if item.advancement:
                    pool.setdefault(item.name, []).append(item)
            orders = [(), ("Trophy",), ("Trophy",) * 2, ("Trophy",) * 4, ("Key",), ("Trophy",) * 4 + ("Key",)]
            for held in orders:
                if boost in pool:
                    held += (boost,)
                if all(name in pool for name in held):
                    items = [pool[name][held[:i].count(name)] for i, name in enumerate(held)]
                    with self.subTest(seed=seed, held=held):
                        self.assertEqual(reach.room(tuple(sorted(held))),
                                         len(sphere0_guard._room(world, sphere0_guard._collect(world, state, items))))

    def test_it_reads_the_default(self):
        self.assert_matches({}, range(3))

    def test_it_reads_vanilla_requirements(self):
        self.assert_matches(VANILLA, range(3))

    def test_a_locked_pad_counts_its_own_racers_boost(self):
        world = make_world(dict(progressive_boost="per_character", character_unlocks=True, racer_locked_pads=8),
                           seed=1, stop_before="pre_fill")
        plan = world.ctr_content_plan
        start = sphere0_guard.starting_boost_item(world)
        reach = content_opening.PlanReach(plan, world.ctr_content_items.rows, set(), start)
        locked = [pad["id"] for pad in plan["pads"] if pad["racer_lock"] is not None]
        self.assertTrue(locked)
        for _code, _spot, _floor, routes in reach.checks:
            for _own, _later, route, _need, boost in routes or ():
                if route["own_pad_id"] in locked:
                    self.assertNotEqual(boost, reach.code[start])

    def test_it_reads_a_fixed_first_key(self):
        self.assert_matches(TIGHT, range(3))

    def test_a_ctr_first_token_waits_for_its_letters_and_the_win(self):
        self.assert_matches(LETTERS, range(3))


class TestFirstKeyCapacity(unittest.TestCase):
    def test_a_token_behind_letters_does_not_skip_the_path(self):
        """A raw count of the first races reaches nine on these seeds: every Token
        counted. The checks that can hold a Trophy do not, so the path is seated."""
        paths = 0
        for seed in range(6):
            world = make_world(dict(LETTERS), seed=seed, stop_before="pre_fill")
            near = sum(c["kind"] == "ctr" for c in world.ctr_content_plan["checks"]) >= 9
            paths += near and bool(world.ctr_first_key_path)
        self.assertGreater(paths, 0)

    def test_the_tight_opening_fits(self):
        for seed in range(6):
            world = make_world(dict(LETTERS), seed=seed, stop_before="pre_fill")
            room, need = content_opening.fit(world, world.ctr_content_plan)
            self.assertGreaterEqual(room, need)


class TestRedraw(unittest.TestCase):
    def test_a_plan_that_fits_takes_no_further_draw(self):
        calls = []
        real = content_plan.draw_plan

        def counted(world, *estimate):
            calls.append(1)
            return real(world, *estimate)

        with mock.patch.object(content_plan, "draw_plan", counted):
            make_world({}, seed=1, stop_before="pre_fill")
        self.assertEqual(len(calls), 1)

    def test_a_short_opening_draws_again_until_it_fits(self):
        answers = iter([(0, 5), (2, 5), (5, 5)])
        with mock.patch.object(content_opening, "fit", lambda _world, _plan: next(answers)):
            make_world({}, seed=1, stop_before="pre_fill")
        self.assertIsNone(next(answers, None))

    def test_the_best_draw_stands(self):
        draws = []
        real = content_plan.draw_plan

        def traced(world, *estimate):
            state = world.random.getstate()
            plan = real(world, *estimate)
            draws.append((state, plan))
            return plan

        rooms = iter([1, 3] + [2] * content_plan.OPENING_REDRAWS)
        with mock.patch.object(content_plan, "draw_plan", traced), \
                mock.patch.object(content_opening, "fit", lambda _world, _plan: (next(rooms), 5)):
            world = make_world({}, seed=1, stop_before="pre_fill")
        self.assertEqual(draws[-1][0], draws[1][0])
        self.assertEqual(world.ctr_content_plan["pads"], draws[1][1]["pads"])

    def test_the_tight_mix_fits(self):
        for seed in range(12):
            world = make_world(dict(TIGHT), seed=seed, stop_before="pre_fill")
            room, need = content_opening.fit(world, world.ctr_content_plan)
            self.assertGreaterEqual(room, need)


class TestSeating(unittest.TestCase):
    def test_a_reservation_locks_nothing(self):
        world = make_world(dict(TIGHT), seed=2, stop_before="pre_fill")
        mw = world.multiworld
        pool = [item for item in mw.itempool if item.name == "Trophy"][:2]
        before = sum(loc.item is not None for loc in mw.get_locations(1))
        chosen = sphere0_guard._reserve(world, sphere0_guard._base_state(world), pool)
        self.assertEqual(len(chosen), 2)
        self.assertNotEqual(chosen[0][1], chosen[1][1])
        self.assertEqual(sum(loc.item is not None for loc in mw.get_locations(1)), before)

    def test_a_path_that_does_not_fit_seats_nothing(self):
        world = make_world(dict(TIGHT), seed=2, stop_before="pre_fill")
        mw = world.multiworld
        state = sphere0_guard._base_state(world)
        with mock.patch.object(sphere0_guard, "_reserve", lambda *_args: None), \
                mock.patch.object(sphere0_guard, "_first_key_tight", lambda *_args: True):
            sphere0_guard._seat_first_key(world, state)
        self.assertEqual(sum(loc.item is not None and loc.item.name == "Trophy" and loc.address is not None
                             for loc in mw.get_locations(1)), 0)

    def test_a_wide_first_key_is_left_to_the_fill(self):
        world = make_world(dict(TIGHT), seed=2, stop_before="pre_fill")
        with mock.patch.object(sphere0_guard, "_first_key_tight", lambda *_args: False):
            state = sphere0_guard._base_state(world)
            self.assertIs(sphere0_guard._seat_first_key(world, state), state)

    def test_an_opening_that_falls_short_is_taken_back(self):
        world = make_world(dict(TIGHT), seed=2, stop_before="pre_fill")
        mw = world.multiworld
        pool = list(mw.itempool)
        trophy = next(item for item in pool if item.name == "Trophy")
        spot = sphere0_guard._open_empty(world, sphere0_guard._base_state(world))[0]
        spot.place_locked_item(trophy)
        mw.itempool.remove(trophy)
        sphere0_guard._unlock(world, [("Trophy", spot.name)])
        self.assertIsNone(spot.item)
        self.assertFalse(spot.locked)
        self.assertIsNone(trophy.location)

    def assert_fills(self, options, seeds):
        for seed in seeds:
            with self.subTest(seed=seed):
                world = make_world(dict(options), seed=seed, stop_before="fill")
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game())

    def test_the_failing_shapes_fill(self):
        self.assert_fills(TIGHT, range(8))
        self.assert_fills(LETTERS, range(8))
