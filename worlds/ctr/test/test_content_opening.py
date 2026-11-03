"""The opening of a content plan (one generator row 8b): the search, the plan's
reach model against the real rules, the redraw, and the seating."""
import unittest
from pathlib import Path
from unittest import mock
import yaml

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
    def test_garage_demand_pays_for_its_support_items(self):
        room = spots(5, [(dict(Boost=2), 8)])
        held, free = content_opening.search(dict(Boost=2, Relic=3), room, 12,
                                            reached=lambda items: items.count("Relic") >= 3,
                                            goals=[("Relic",) * 3])
        self.assertEqual(sorted(held), ["Boost", "Boost", "Relic", "Relic", "Relic"])
        self.assertEqual(free, 8)  # 13 reachable slots minus all five items.

    def test_a_garage_demand_larger_than_the_opening_is_not_seated(self):
        held, free = content_opening.search(dict(Relic=4), spots(3, []), 12,
                                            reached=lambda items: items.count("Relic") >= 4,
                                            goals=[("Relic",) * 4])
        self.assertEqual((held, free), ([], 3))

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

    def test_copies_of_one_kind_come_before_pairs_of_many_kinds(self):
        # Row 13: a boost per racer gives some thirty kinds the pool cannot do
        # without; their pairs spent the probes before three of one kind.
        pool = {f"Boost {n}": 2 for n in range(30)}
        pool["Token"] = 4
        gates = [(dict(Token=3), 12)] + [({f"Boost {n}": 2}, 1) for n in range(30)]
        names, room = content_opening.search(pool, spots(5, gates), 6)
        self.assertEqual(names, ["Token"] * 3)
        self.assertEqual(room, 14)

    def test_a_bundle_is_taken_whole(self):
        # Row 13: one track's letters open its letter checks and Token together.
        gates = [(dict(LetterC=1), 1), (dict(LetterT=1), 1), (dict(LetterC=1, LetterT=1), 1)]
        pool = dict(Trophy=4, LetterC=1, LetterT=1)
        self.assertEqual(content_opening.search(pool, spots(2, gates), 5, bundles=[("LetterC", "LetterT")]),
                         (["LetterC", "LetterT"], 3))

    def test_bundle_names_are_no_step_of_their_own(self):
        gates = [(dict(LetterC=1, LetterT=1), 6)]
        self.assertEqual(content_opening.search(dict(LetterC=1, LetterT=1), spots(2, gates), 5,
                                                bundles=[("LetterC", "LetterT", "LetterR")]), ([], 2))

    def test_bundle_can_seat_each_letter_in_the_check_the_previous_letter_opens(self):
        bundle = ("LetterC", "LetterT", "LetterR")
        gates = [({name: 1}, 1) for name in bundle] + [(dict.fromkeys(bundle, 1), 1)]
        held, free = content_opening.search(dict.fromkeys(bundle, 1), spots(1, gates), 2,
                                            bundles=[bundle])
        self.assertEqual(tuple(held), bundle)
        self.assertEqual(free, 2)  # Five checks, all three copies paid.

    def test_bundle_cannot_spend_a_later_check_before_it_opens(self):
        bundle = ("LetterC", "LetterT", "LetterR")
        gates = [(dict.fromkeys(bundle, 1), 5)]
        self.assertEqual(content_opening.search(dict.fromkeys(bundle, 1), spots(1, gates), 2,
                                                bundles=[bundle]), ([], 1))

    def test_bundle_prefixes_obey_the_existing_probe_budget(self):
        bundle = ("LetterC", "LetterT", "LetterR")
        gates = [({name: 1}, 1) for name in bundle] + [(dict.fromkeys(bundle, 1), 1)]
        self.assertEqual(content_opening.search(dict.fromkeys(bundle, 1), spots(1, gates), 2,
                                                probes=1, bundles=[bundle]), ([], 1))

    def test_the_search_stops_at_its_target(self):
        names, room = content_opening.search(dict(Key=4), spots(1, [(dict(Key=1), 6), (dict(Key=2), 90)]), 5)
        self.assertEqual((names, room), (["Key"], 6))

    def test_a_useless_item_is_not_seated(self):
        self.assertEqual(content_opening.search(dict(Relic=9), spots(3, []), 5), ([], 3))


class TestGarageDemands(unittest.TestCase):
    names = {1: "Sapphire", 2: "Gold", 3: "Red"}

    def test_summed_relics_keep_every_available_distribution(self):
        node = dict(op="sum", count=3, items=[1, 2])
        self.assertEqual(set(content_opening.garage_demands(node, dict(Sapphire=2, Gold=2), {}, self.names)),
                         {("Sapphire", "Gold", "Gold"), ("Sapphire", "Sapphire", "Gold")})

    def test_precollected_copies_need_no_slot(self):
        node = dict(op="count", count=3, item=1)
        self.assertEqual(content_opening.garage_demands(node, dict(Sapphire=2), {1: 1}, self.names),
                         [("Sapphire", "Sapphire")])

    def test_fixed_items_are_not_invented(self):
        self.assertEqual(content_opening.garage_demands(dict(op="count", count=1, item=3), {}, {}, self.names), [])

    def test_overlapping_all_terms_share_the_same_copies(self):
        node = dict(op="all", terms=[dict(op="count", count=2, item=1), dict(op="count", count=1, item=1)])
        self.assertEqual(content_opening.garage_demands(node, dict(Sapphire=2), {}, self.names),
                         [("Sapphire", "Sapphire")])

    def test_distinct_does_not_count_an_already_held_kind_twice(self):
        node = dict(op="distinct", count=2, items=[1, 2, 3])
        self.assertEqual(set(content_opening.garage_demands(node, dict(Sapphire=4, Gold=1, Red=1), {1: 1}, self.names)),
                         {("Gold",), ("Red",)})


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

    def test_each_tracks_letters_are_one_bundle(self):
        world = make_world(dict(LETTERS), seed=0, stop_before="pre_fill")
        plan = world.ctr_content_plan
        pool = {row.name: row.remaining for row in world.ctr_content_items.rows}
        bundles = content_opening.letter_bundles(plan, pool)
        tokens = {names for names in content_plan.letter_requirements(plan).values() if len(names) > 1}
        self.assertTrue(bundles)
        self.assertTrue(set(bundles) <= {names for names in content_plan.letter_requirements(plan).values()})
        self.assertTrue(tokens <= set(bundles))
        self.assertEqual(content_opening.letter_bundles(make_world(dict(TIGHT), seed=0, stop_before="pre_fill")
                                                        .ctr_content_plan, pool), [])

    def test_the_tight_opening_fits(self):
        for seed in range(6):
            world = make_world(dict(LETTERS), seed=seed, stop_before="pre_fill")
            room, need = content_opening.fit(world, world.ctr_content_plan)
            self.assertGreaterEqual(room, need)


class TestCostedFixedKeyCapacity(unittest.TestCase):
    def test_actual_vanilla_letter_prefix_failure_fills_and_reaches_all_checks(self):
        path = Path(__file__).parent / "fixtures" / "row13_vanilla_sequential_letters.yaml"
        options = yaml.safe_load(path.read_text())["Crash Team Racing"]
        world = make_world(options, seed=264, stop_before="fill")
        self.assertEqual(world.ctr_content_plan["pad_requirements"]["mode"], "vanilla")
        self.assertTrue(world.ctr_content_plan["fixed_items"]["keys"])
        distribute_items_restrictive(world.multiworld)
        state = CollectionState(world.multiworld)
        state.sweep_for_advancements(locations=world.multiworld.get_locations(world.player))
        self.assertTrue(world.multiworld.can_beat_game())
        self.assertTrue(all(location.can_reach(state) for location in world.multiworld.get_locations(world.player)
                            if location.address is not None))

    cases = (("letters", 169, 53), ("racers", 83, 48))

    def options(self, name):
        path = Path(__file__).parent / "fixtures" / f"row13_fixed_key_{name}.yaml"
        return yaml.safe_load(path.read_text())["Crash Team Racing"]

    def reach(self, world):
        boost = sphere0_guard.starting_boost_item(world)
        return content_opening.PlanReach(world.ctr_content_plan, world.ctr_content_items.rows, set(), boost)

    def test_actual_first_draws_do_not_get_their_support_items_for_free(self):
        for name, seed, advertised in self.cases:
            with self.subTest(name=name), mock.patch.object(content_opening.PlanReach, "key_slack", return_value=12):
                world = make_world(self.options(name), seed=seed, stop_before="pre_fill")
            reach = self.reach(world)
            key = reach.code["Key"]
            held = tuple(item for item, count in reach.pool.items() if item != "Key" for _ in range(count))
            counts = reach._held(held)
            counts[key] = 1
            fixed = {code: item for code, item in reach.pins.items() if item != key}
            opened = reach._sweep(counts, fixed)
            self.assertEqual(sum(spot and code in opened for code, spot, _floor, _routes in reach.checks), advertised)
            base, pins = reach.base, reach.pins
            self.assertLess(reach.key_slack(), content_opening.KEY_SLACK)
            self.assertIs(reach.base, base)
            self.assertIs(reach.pins, pins)
            # Nonlocal support cannot be budgeted as a local placement.
            self.assertLess(reach.key_slack(non_local=set(reach.pool)), content_opening.KEY_SLACK)

    def test_meeting_a_garage_demand_does_not_grant_its_boss_boost(self):
        world = make_world(self.options("letters"), seed=169, stop_before="pre_fill")
        reach = self.reach(world)
        checks = {check["location"]: check for check in world.ctr_content_plan["checks"]}
        encounter = next(encounter for encounter in reach.encounters.values()
                         if checks[encounter["completion_location"]].get("boost", 0))
        reach.base = dict(reach.base)
        reach.base[reach.code["Key"]] = 4
        all_items = tuple(name for name, count in reach.pool.items() for _ in range(count))
        no_boost = tuple(name for name in all_items if not name.startswith("Progressive Boost"))
        counts = reach._held(no_boost)
        reach._sweep(counts)
        self.assertTrue(reach._met(encounter["requirement_id"], counts))
        self.assertFalse(reach.encounter_reached(encounter, no_boost))
        self.assertTrue(reach.encounter_reached(encounter, all_items))

    def test_both_actual_failures_fill_and_reach_every_addressed_location(self):
        for name, seed, _advertised in self.cases:
            with self.subTest(name=name):
                world = make_world(self.options(name), seed=seed, stop_before="fill")
                mw = world.multiworld
                distribute_items_restrictive(mw)
                state = CollectionState(mw)
                state.sweep_for_advancements(locations=mw.get_locations(world.player))
                self.assertTrue(mw.can_beat_game())
                self.assertTrue(all(location.can_reach(state) for location in mw.get_locations(world.player)
                                    if location.address is not None))


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
