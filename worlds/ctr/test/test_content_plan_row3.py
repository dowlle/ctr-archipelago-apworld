"""One generator row 3: pad placement and requirements behind content_pool."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError
from worlds.AutoWorld import call_all

from .. import content_bosses, content_plan, content_requirements as cr, warp_pad_logic
from .test_content_plan import make_world, profile_pool

SHAPE = dict(preset="mixed", tracks=dict(retail="all", modes=["trophy", "ctr", "relic"], custom=[]),
             cups=dict(count=5), crystals=dict(count=4), bosses=dict(enabled=True))
KEY = 35010014


def options(placement="shuffle", **overrides):
    return {"content_pool": copy.deepcopy(SHAPE), "item_pool": {}, "accessibility": "full",
            "pad_layout": dict(placement=placement, stages="two", mode_order="fixed", merge_trophy_ctr=False),
            **overrides}


def records(plan, prefix):
    return {int(r["id"].split(":")[1]): r["predicate"] for r in plan["requirements"] if r["id"].startswith(prefix)}


def occupied(plan):
    entries = {e["id"]: e for e in plan["entries"]}
    return {int(p["id"].split(":")[1]): entries[p["entry_id"]] for p in plan["pads"]
            if p["kind"] == "normal" and p["entry_id"] is not None}


def filled(world):
    call_all(world.multiworld, "pre_fill")
    distribute_items_restrictive(world.multiworld)
    return world.multiworld


class TestPlacement(unittest.TestCase):
    def test_vanilla_keeps_original_content_home(self):
        plan = make_world(options("vanilla")).ctr_content_plan
        tracks = {t["id"]: t for t in plan["tracks"]}
        for physical, entry in occupied(plan).items():
            if entry["kind"] == "track":
                self.assertEqual(tracks[entry["track_id"]]["retail_id"], physical)
            elif entry["kind"] == "crystal":
                self.assertEqual(entry["arena_id"], physical)
            else:
                self.assertEqual(100 + int(entry["id"].rsplit(":", 1)[1]), physical)

    def test_within_kind_keeps_each_kind_on_its_pads(self):
        for seed in range(6):
            plan = make_world(options("shuffle_within_kind"), seed=seed).ctr_content_plan
            kind = dict(track="track", cup="cup", crystal="arena")
            for physical, entry in occupied(plan).items():
                self.assertEqual(cr.PHYSICAL_KIND[physical], kind[entry["kind"]])

    def test_overflow_takes_any_free_pad_without_a_refusal(self):
        # Seven arenas fit four arena pads; ten cups fit five cup pads.
        o = options("shuffle_within_kind", include_arcade_arenas=True)
        o["content_pool"]["crystals"] = dict(count=7)
        o["content_pool"]["cups"] = dict(count=10)
        plan = make_world(o).ctr_content_plan
        seats = occupied(plan)
        self.assertEqual(sum(e["kind"] == "crystal" for e in seats.values()), 7)
        self.assertEqual(sum(e["kind"] == "cup" for e in seats.values()), 10)
        self.assertTrue(any(cr.PHYSICAL_KIND[p] == "track" and e["kind"] != "track" for p, e in seats.items()))

    def test_custom_content_on_vanilla_takes_a_free_pad(self):
        o = options("vanilla")
        o["content_pool"]["tracks"]["retail"] = [i for i in range(18) if i != 3]
        o["content_pool"]["tracks"]["cortex_vortex"] = True
        plan = make_world(o).ctr_content_plan
        seats = occupied(plan)
        self.assertEqual(seats[3]["track_id"], "cortex_vortex")

    def test_a_spare_pad_is_closed_and_asks_for_nothing(self):
        o = options()
        o["content_pool"]["tracks"]["retail"] = [3, 6, 9, 8, 14, 4]
        o["content_pool"]["cups"] = dict(count=0)
        o["content_pool"]["crystals"] = dict(count=0)
        o["item_pool"] = profile_pool()
        o["oxide_goal"], o["gems_required_goal"] = "disabled", 5
        plan = make_world(o, stop_before="pre_fill").ctr_content_plan
        ids = {r["id"] for r in plan["requirements"]}
        for pad in plan["pads"]:
            if pad["kind"] == "normal" and pad["entry_id"] is None:
                self.assertEqual(pad["mode_gates"], [])
                physical = pad["id"].split(":")[1]
                self.assertFalse({f"stage1:{physical}", f"stage2:{physical}"} & ids)

    def test_all_on_own_content_is_drawn_again(self):
        chosen = [dict(retail_id=3), dict(retail_id=6)]
        self.assertTrue(cr.own_content(dict(zip((3, 6), chosen))))
        self.assertFalse(cr.own_content({3: chosen[1], 6: chosen[0]}))

    def test_too_many_cups_on_early_pads_fail_the_floor(self):
        seats = [(i, 26, 0) for i in (3, 6, 9, 8, 21)] + [(14, 27, 1)]
        cups = {p: dict(cup_index=None, gem_cup=n) for n, p in enumerate((3, 6, 9, 8))}
        cups[21] = dict(arena_id=21)
        self.assertFalse(cr.capacity_met(cups, seats, 0))
        tracks = {p: dict(retail_id=p) for p in (3, 6, 9, 8)}
        self.assertFalse(cr.capacity_met(tracks, seats, 0))  # 4 at 0 Keys, but only 4 at 1 Key of 8
        wide = {seat[0]: dict(retail_id=seat[0]) for seat in seats}
        self.assertTrue(cr.capacity_met(wide, seats, 3))


class TestRandomRequirements(unittest.TestCase):
    def test_free_pads_are_three_to_five_beach_pads(self):
        for seed in range(12):
            plan = make_world(options(), seed=seed).ctr_content_plan
            free = [p for p in plan["pads"] if p["entry_id"] and p["kind"] == "normal"
                    and p["entrance_req"] == "free" and p["mode_gates"][0]["requirement_id"] == "free"]
            self.assertTrue(3 <= len(free) <= 5, seed)

    def test_every_other_pad_has_a_requirement_within_the_ceilings(self):
        plan = make_world(options(), seed=2).ctr_content_plan
        rows = {r["item"]: r for r in plan["items"]["rows"]}
        for predicate in records(plan, "stage1:").values():
            self.assertLessEqual(predicate["count"], 8 if predicate.get("item") != KEY else 4)
        for predicate in records(plan, "stage2:").values():
            self.assertLessEqual(predicate["count"], 4)
            for item in predicate.get("items", [predicate.get("item")]):
                self.assertGreater(rows[item]["requirement_ceiling"], 0)

    def test_a_tier_the_seed_lacks_is_never_asked(self):
        for seed in range(12):
            plan = make_world(options(), seed=seed).ctr_content_plan  # Platinum defaults to 0
            for table in (records(plan, "stage1:"), records(plan, "stage2:")):
                for predicate in table.values():
                    self.assertNotIn(35010003, predicate.get("items", [predicate.get("item")]))

    def test_weights_are_the_one_table(self):
        weights = dict(warp_pad_logic.DEFAULT_REQUIREMENT_WEIGHTS)
        weights.update({k: 0 for k in weights if k != "Trophy"})
        plan = make_world(options(requirement_weights=weights), seed=1).ctr_content_plan
        for table in (records(plan, "stage1:"), records(plan, "stage2:")):
            for predicate in table.values():
                self.assertEqual(predicate.get("item"), 35010000)

    def test_any_of_counts_of_the_table_are_drawn(self):
        seen = set()
        for seed in range(12):
            plan = make_world(options(), seed=seed).ctr_content_plan
            seen |= {tuple(p["items"]) for p in records(plan, "stage1:").values() if p["op"] == "sum"}
        self.assertGreaterEqual(len(seen), 2)

    def test_zero_trophy_weight_is_refused(self):
        weights = dict(warp_pad_logic.DEFAULT_REQUIREMENT_WEIGHTS, Trophy=0)
        with self.assertRaisesRegex(OptionError, "Trophy must stay above 0"):
            make_world(options(requirement_weights=weights))

    def test_no_4_keys_at_either_stage(self):
        for seed in range(30):
            plan = make_world(options(warppad_unlock_requirements="random_without_4_keys"), seed=seed).ctr_content_plan
            for table in (records(plan, "stage1:"), records(plan, "stage2:")):
                self.assertFalse(any(p.get("item") == KEY and p["count"] >= 4 for p in table.values()))

    def test_forged_four_keys_is_refused(self):
        plan = make_world(options(warppad_unlock_requirements="random_without_4_keys"), seed=1).ctr_content_plan
        forged = copy.deepcopy(plan)
        row = next(r for r in forged["requirements"] if r["id"].startswith("stage2:"))
        row["predicate"] = dict(op="count", item=KEY, count=4)
        with self.assertRaisesRegex(OptionError, "4 Keys"):
            content_plan.validate(forged)

    def test_forged_counts_are_refused(self):
        plan = make_world(options(), seed=1).ctr_content_plan
        forged = copy.deepcopy(plan)
        row = next(r for r in forged["requirements"] if r["id"].startswith("stage2:"))
        row["predicate"] = dict(op="count", item=35010000, count=5)
        with self.assertRaisesRegex(OptionError, "above its count ceiling"):
            content_plan.validate(forged)
        forged = copy.deepcopy(plan)
        row = next(r for r in forged["requirements"] if r["id"].startswith("stage1:"))
        row["predicate"] = dict(op="count", item=35010000, count=9)
        with self.assertRaisesRegex(OptionError, "above its count ceiling"):
            content_plan.validate(forged)

    def test_a_stage_2_met_by_its_stage_1_is_refused(self):
        plan = make_world(options(), seed=1).ctr_content_plan
        physical = sorted(set(records(plan, "stage1:")) & set(records(plan, "stage2:")))[0]
        forged = copy.deepcopy(plan)
        row = next(r for r in forged["requirements"] if r["id"] == f"stage2:{physical}")
        row["predicate"] = copy.deepcopy(records(plan, "stage1:")[physical])
        row["predicate"]["count"] = 1
        with self.assertRaises(OptionError):
            content_plan.validate(forged)

    def test_a_relic_race_with_no_tier_check_is_never_first(self):
        o = options(relic_perfect_checks=True)
        o["item_pool"] = {"base": {"relics": {"sapphire": 2, "gold": 1}}}
        o["pad_layout"]["mode_order"] = "per_pad"
        o["oxide_final_challenge_unlock"] = "any_relic_type"
        o["oxide_final_challenge_relic_count"] = 1
        for seed in range(12):
            plan = make_world(copy.deepcopy(o), seed=seed, stop_before="pre_fill").ctr_content_plan
            tiers = {c["routes"][0]["own_pad_id"] for c in plan["checks"] if c["kind"] == "relic"}
            for pad in plan["pads"]:
                if len(pad["mode_gates"]) > 1 and pad["id"] not in tiers:
                    self.assertNotEqual(pad["mode_gates"][0]["mode"], "relic")

    def test_the_stand_ins_keep_the_simulation_walking(self):
        """Stage 1 reaches the deep counts of a walked seed, not the fallback's."""
        counts = []
        for seed in range(8):
            plan = make_world(options(), seed=seed).ctr_content_plan
            counts.append(max(p["count"] for p in records(plan, "stage1:").values()))
        self.assertGreater(sum(counts) / len(counts), 4)

    def test_stage2_follows_two_stage_density(self):
        expect = dict(off=0, light=4, standard=6, deep=10)
        for density, most in expect.items():
            for seed in range(6):
                plan = make_world(options(two_stage_density=density), seed=seed).ctr_content_plan
                self.assertLessEqual(len(records(plan, "stage2:")), most, density)
        plan = make_world(options(), seed=1).ctr_content_plan
        self.assertEqual(len(records(plan, "stage2:")), 18)  # `full`, the trial tracks too

    def test_stages_single_is_density_off(self):
        o = options()
        o["pad_layout"]["stages"] = "single"
        self.assertFalse(records(make_world(o).ctr_content_plan, "stage2:"))

    def test_stage2_asks_more_than_stage1(self):
        for seed in range(12):
            plan = make_world(options(), seed=seed).ctr_content_plan
            first, second = records(plan, "stage1:"), records(plan, "stage2:")
            for physical, predicate in second.items():
                if physical in first and first[physical].get("item") == predicate.get("item") \
                        and first[physical].get("items") == predicate.get("items"):
                    self.assertGreater(predicate["count"], first[physical]["count"])


class TestVanillaRequirements(unittest.TestCase):
    V = dict(warppad_unlock_requirements="vanilla")

    def test_each_pad_keeps_its_requirement_with_any_placement(self):
        for placement in cr.PLACEMENTS:
            plan = make_world(options(placement, **self.V)).ctr_content_plan
            first = records(plan, "stage1:")
            self.assertNotIn(3, first)  # Crash Cove, 0 Trophies
            self.assertNotIn(6, first)
            self.assertEqual(first[9], dict(op="count", item=35010000, count=1))
            self.assertEqual(first[13], dict(op="count", item=35010000, count=15))
            self.assertEqual(first[21], dict(op="count", item=KEY, count=1))
            self.assertEqual(first[18], dict(op="count", item=KEY, count=4))
            self.assertEqual(first[16], dict(op="count", item=35010001, count=10))
            self.assertEqual(first[17], dict(op="sum", items=list(range(35010009, 35010014)), count=5))
            self.assertEqual(first[100], dict(op="count", item=35010004, count=4))

    def test_key_stage2_counts_from_the_physical_hub(self):
        plan = make_world(options("shuffle", **self.V)).ctr_content_plan
        second = records(plan, "stage2:")
        seats = occupied(plan)
        want = {physical: cr.vanilla_stage2_keys(physical) for physical, e in seats.items() if e["kind"] == "track"}
        self.assertEqual({p: r["count"] for p, r in second.items()}, want)
        self.assertEqual((cr.vanilla_stage2_keys(3), cr.vanilla_stage2_keys(14), cr.vanilla_stage2_keys(2),
                          cr.vanilla_stage2_keys(7), cr.vanilla_stage2_keys(16), cr.vanilla_stage2_keys(100)),
                         (1, 2, 3, 4, 2, 3))

    def test_density_off_has_no_key_stage(self):
        self.assertFalse(records(make_world(options(two_stage_density="off", **self.V)).ctr_content_plan, "stage2:"))

    def test_fewer_items_clamp_and_none_opens_free(self):
        o = options("vanilla", **self.V)
        o["item_pool"] = {"base": {"relics": {"sapphire": 0}}}
        o["oxide_final_challenge_unlock"] = "gold_relics"
        plan = make_world(o, stop_before="pre_fill").ctr_content_plan
        self.assertNotIn(16, records(plan, "stage1:"))

    def test_garages_ask_the_trophy_table(self):
        plan = make_world(options(**self.V)).ctr_content_plan
        req = {r["id"]: r["predicate"] for r in plan["requirements"]}
        for g, count in enumerate((4, 8, 12, 16)):
            self.assertEqual(req[f"boss:{g}"], dict(op="count", item=35010000, count=count))
        self.assertEqual(next(p for p in plan["pads"] if p["id"] == "garage:4")["entrance_req"], "keys:4")

    def test_forged_vanilla_records_are_refused(self):
        plan = make_world(options(**self.V)).ctr_content_plan
        forged = copy.deepcopy(plan)
        next(r for r in forged["requirements"] if r["id"] == "stage1:13")["predicate"]["count"] = 2
        with self.assertRaisesRegex(OptionError, "vanilla stage 1"):
            content_plan.validate(forged)
        forged = copy.deepcopy(plan)
        next(r for r in forged["requirements"] if r["id"].startswith("stage2:"))["predicate"]["count"] = 1
        forged["requirements"] = [r for r in forged["requirements"] if r["id"] != "stage2:7"]
        with self.assertRaises(OptionError):
            content_plan.validate(forged)

    def test_vanilla_locks_no_pad(self):
        plan = make_world(options(racer_locked_pads=6, character_unlocks=True, **self.V), stop_before="pre_fill").ctr_content_plan
        self.assertFalse(any(p["racer_lock"] is not None for p in plan["pads"]))

    def test_manual_rules_with_vanilla_stay_refused(self):
        with self.assertRaisesRegex(OptionError, "warp_pad_rules needs"):
            make_world(options(warp_pad_rules={"Crash Cove": dict(item="Trophy", count=1)}, **self.V))

    def test_every_placement_fills_and_is_beatable(self):
        for placement in cr.PLACEMENTS:
            for seed in range(4):
                mw = filled(make_world(options(placement, **self.V), seed=seed, stop_before="pre_fill"))
                self.assertTrue(mw.can_beat_game(), (placement, seed))


class TestGarages(unittest.TestCase):
    def test_trophy_draws_grow_with_depth(self):
        seen = {g: set() for g in range(4)}
        for seed in range(80):
            plan = make_world(options(), seed=seed, stop_before="pre_fill").ctr_content_plan
            for g in range(4):
                predicate = next(r["predicate"] for r in plan["requirements"] if r["id"] == f"boss:{g}")
                if predicate.get("item") == 35010000:
                    seen[g].add(predicate["count"])
        self.assertTrue(all(seen.values()))
        self.assertGreater(max(seen[3]), min(seen[0]))
        self.assertGreater(len(seen[3]), 1)

    def test_level_defaults_to_high(self):
        self.assertEqual(content_bosses.DEFAULT_LEVEL, "high")

    def test_oxide_stays_four_keys(self):
        plan = make_world(options()).ctr_content_plan
        self.assertEqual(next(p for p in plan["pads"] if p["id"] == "garage:4")["entrance_req"], "keys:4")


class TestFirstRaceWon(unittest.TestCase):
    def test_a_single_stage_pad_also_waits_for_the_first_race(self):
        o = options(two_stage_density="off")
        world = make_world(o, stop_before="pre_fill")
        plan, mw = world.ctr_content_plan, world.multiworld
        names = content_plan.LOCATION_BY_CODE
        pad = next(p for p in plan["pads"] if len(p["mode_gates"]) == 3)
        checks = [c for c in plan["checks"] if c["routes"][0]["own_pad_id"] == pad["id"] and len(c["routes"]) == 1]
        win = next(c for c in checks if c["kind"] == pad["mode_gates"][0]["mode"])
        later = next(c for c in checks if c["kind"] == pad["mode_gates"][1]["mode"])
        all_items = mw.get_all_state(False)
        for item in mw.itempool:
            all_items.collect(item, True)
        self.assertTrue(mw.get_location(names[later["location"]], 1).can_reach(all_items))
        mw.get_location(names[win["location"]], 1).access_rule = lambda state: False
        self.assertFalse(mw.get_location(names[later["location"]], 1).can_reach(all_items))

    def test_the_first_race_follows_the_pad_order(self):
        o = options()
        o["pad_layout"]["mode_order"] = "per_pad"
        plan = make_world(o, seed=4).ctr_content_plan
        firsts = {p["mode_gates"][0]["mode"] for p in plan["pads"] if len(p["mode_gates"]) > 1}
        self.assertGreater(len(firsts), 1)


class TestStartGuards(unittest.TestCase):
    def test_every_seed_starts_with_two_checks(self):
        for o in (options(), options("shuffle_within_kind"), options(warppad_unlock_requirements="vanilla"),
                  options(progressive_boost="shared_global")):
            for seed in range(10):
                world = make_world(copy.deepcopy(o), seed=seed, stop_before="pre_fill")
                mw = world.multiworld
                start = [loc for loc in mw.get_reachable_locations(CollectionState(mw), 1) if loc.address]
                self.assertGreaterEqual(len(start), 2)

    def test_vanilla_placement_swaps_in_an_open_pad(self):
        o = options(warppad_unlock_requirements="vanilla")
        o["content_pool"]["tracks"]["retail"] = [14, 4, 5, 0, 2, 1]
        o["content_pool"]["cups"] = dict(count=0)
        o["content_pool"]["crystals"] = dict(count=0)
        o["item_pool"] = profile_pool()
        o["item_pool"]["base"]["trophies"] = 5
        o["oxide_goal"], o["gems_required_goal"] = "disabled", 5
        plan = make_world(o, stop_before="pre_fill").ctr_content_plan
        seats = occupied(plan)
        self.assertTrue({3, 6} & set(seats))

    def test_the_early_weapon_gives_way_on_a_start_with_no_spare_check(self):
        from unittest import mock
        from .. import sphere0_guard
        world = make_world(options(itemsanity=True, hit_character=False), stop_before="pre_fill")
        mw = world.multiworld
        self.assertTrue(mw.early_items[1])
        spots = [object(), object()]
        with mock.patch.object(sphere0_guard, "_open_empty", lambda _world, _state: spots), \
                mock.patch.object(sphere0_guard, "bootstrap_target", lambda _world: 12), \
                mock.patch.object(sphere0_guard, "_next_openers", lambda *_args: []):
            sphere0_guard.bootstrap_start(world)
        self.assertFalse(mw.early_items[1])

    def test_a_start_with_room_keeps_the_early_weapon(self):
        from unittest import mock
        from .. import sphere0_guard
        world = make_world(options(itemsanity=True, hit_character=False), stop_before="pre_fill")
        mw = world.multiworld
        weapons = dict(mw.early_items[1])
        spots = [object()] * 3
        with mock.patch.object(sphere0_guard, "_open_empty", lambda _world, _state: spots), \
                mock.patch.object(sphere0_guard, "bootstrap_target", lambda _world: 12), \
                mock.patch.object(sphere0_guard, "_next_openers", lambda *_args: []):
            sphere0_guard.bootstrap_start(world)
        self.assertEqual(mw.early_items[1], weapons)

    def test_a_marked_item_that_opens_nothing_waits_for_an_opener(self):
        from .. import sphere0_guard
        for seed in range(30):
            world = make_world(options(warppad_unlock_requirements="vanilla", progressive_boost="shared_global",
                                       podium_placement_checks=False,
                                       item_pool={"base": {"trophies": 4}}),
                               seed=seed, stop_before="pre_fill")
            mw = world.multiworld
            if sphere0_guard.sphere0_breadth(world) > 3 or "Progressive Boost" not in mw.local_early_items[1]:
                continue
            call_all(mw, "pre_fill")
            distribute_items_restrictive(mw)
            self.assertTrue(mw.can_beat_game(), seed)

    def test_the_collapse_message_is_silent(self):
        with self.assertNoLogs(level="WARNING"):
            make_world(options(), seed=0, stop_before="pre_fill")

    def test_no_item_is_given_for_free(self):
        for seed in range(6):
            world = make_world(options(), seed=seed, stop_before="pre_fill")
            self.assertFalse(world.multiworld.precollected_items[1])


class TestTracker(unittest.TestCase):
    def test_restore_rebuilds_every_mode(self):
        for mode in ("vanilla", "randomized", "random_without_4_keys"):
            world = make_world(options(warppad_unlock_requirements=mode), stop_before="pre_fill")
            wire = json.loads(json.dumps(world.fill_slot_data()))
            restored = make_world({}, passthrough=wire)
            self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
            self.assertEqual(restored.ctr_content_plan["pad_requirements"]["mode"], mode)
            self.assertEqual(restored.options.warppad_unlock_requirements.value,
                             world.options.warppad_unlock_requirements.value)

    def test_the_feature_is_declared(self):
        plan = make_world(options()).ctr_content_plan
        self.assertIn(cr.FEATURE, plan["required_features"])
