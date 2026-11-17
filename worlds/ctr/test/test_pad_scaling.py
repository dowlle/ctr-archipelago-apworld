"""Pool-scaled pad counts retain the default draw and enforce real gates."""
import copy
import random
import unittest
from unittest.mock import patch

from Options import OptionError

from .. import content_item_pool, content_plan, content_playthrough as cp, pad_scaling as ps
from .test_content_plan import make_world
from .test_content_plan_row3 import options, records, filled


def supply(multiplier=1):
    base, _ = content_item_pool.normalize({})
    return {name: count if name == "Key" else count * multiplier for name, count in base.items()}


def big_options():
    # Sanity and box checks provide capacity, not requirement supply.
    return options(item_pool={"base": {"trophies": 64, "tokens": dict.fromkeys(content_item_pool.COLOURS, 16),
                                      "relics": {"sapphire": 72, "gold": 72, "platinum": 0}}},
                   item_box_count=15, wumpasanity="both", lettersanity="locations_only",
                   requirement_weights={"Trophy": 1, **dict.fromkeys(cp.TOKEN_ITEMS + cp.RELIC_ITEMS, 1000)},
                   two_stage_density="full")


class TestPadScaling(unittest.TestCase):
    def test_shuffled_redraws_use_selected_inventory_and_caps(self):
        track = "Crash Cove"
        for total, cap in ((4, 2), (64, 32)):
            for path in ("frontier", "pinned", "critical"):
                with self.subTest(total=total, path=path):
                    # The same owned Trophy inventory backs all three relaxation
                    # paths. A static Key gate forces the two completeness paths.
                    exits = {"start": [(cp._pad_exit_name(track), track,
                                        [] if path == "frontier" else [("Key", 4)])]}
                    locations = {f"reward {i}": dict(region="start", gate=[],
                                 is_tt_or_token=False, reward="Trophy") for i in range(total)}
                    pads = {track: ("Key", 4)}
                    relaxed, _ = cp._revalidate_against_shuffle(
                        random.Random(0), exits, locations, pads, {}, {}, "start",
                        {"Trophy"}, {}, pinned_items={"Key"} if path == "pinned" else set(),
                        critical_regions={"unreached"} if path == "critical" else set(),
                        supply={"Trophy": total})
                    self.assertEqual(pads[track], ("Trophy", cap))
                    self.assertEqual(relaxed[track], (("Key", 4), pads[track]))

    def test_shuffled_singleton_redraw_collapses_implied_stage2(self):
        original = cp._revalidate_against_shuffle
        original_run = cp._run_sphere_search_once
        redraws = []

        def force_singleton_redraw(*args, **kwargs):
            result = original(*args, **kwargs)
            pads, second, hosts = args[3:6]
            dest = sorted(second)[0]
            # Reproduce the redraw outcome after the earlier stage-2 check:
            # AnyRelic and Sapphire are equivalent in this selected pool.
            pads[hosts[dest]] = ("AnyRelic", 2)
            second[dest] = ("Sapphire Relic", 1)
            redraws.append(hosts[dest])
            return result

        def run_shuffled(view, *args, **kwargs):
            # ReferenceWorld normally already uses physical-pad regions. Enter
            # the retained shuffled-graph pass explicitly to test its final check.
            view.warp_pad_map = {"Crash Cove Warp Pad": 6}
            out = original_run(view, *args, **kwargs)
            self.assertEqual(out[redraws[-1]][2], out[redraws[-1]][1])
            return out

        pool = {"base": {"trophies": 4, "tokens": dict.fromkeys(content_item_pool.COLOURS, 1),
                         "relics": {"sapphire": 9, "gold": 0, "platinum": 0}}}
        with patch.object(cp, "_revalidate_against_shuffle", side_effect=force_singleton_redraw), \
                patch.object(cp, "_run_sphere_search_once", side_effect=run_shuffled):
            world = make_world(options(item_pool=pool, item_box_count=15), seed=0)
        self.assertTrue(redraws)
        self.assertTrue(content_plan.validate(world.ctr_content_plan))

    def test_caps_default_large_small_and_display_limit(self):
        for item in ("Trophy", "AnyCtrToken", "AnyRelic", "AnyGem", "Gold Relic", "Red CTR Token"):
            for stage, old in ((1, 8), (2, 4)):
                self.assertEqual(ps.count_cap(item, old, supply()), old)
                self.assertEqual(ps.count_cap(item, old, supply(4)), old * 4)
                self.assertEqual(ps.count_cap(item, old, supply(100)), 99)
        small = supply()
        small.update({"Trophy": 4, **dict.fromkeys(cp.TOKEN_ITEMS, 1),
                      "Sapphire Relic": 9, "Gold Relic": 0})
        for item in ("Trophy", "AnyCtrToken", "AnyRelic"):
            self.assertEqual(ps.count_cap(item, 8, small), 2)
            self.assertEqual(ps.count_cap(item, 4, small), 1)
        for pool in (small, supply(), supply(100)):
            self.assertEqual(ps.count_cap("Key", 8, pool), 4)
            self.assertEqual(ps.count_cap("Key", 4, pool), 4)

    def test_missing_family_and_fractional_rounding(self):
        self.assertEqual(ps.count_cap("Platinum Relic", 8, {"Platinum Relic": 1}), 1)
        self.assertEqual(ps.count_cap("AnyRelic", 4, {}), 0)
        self.assertEqual(ps.count_cap("Trophy", 8, {"Trophy": 17}), 9)
        self.assertEqual(ps.count_cap("Trophy", 4, {"Trophy": 17}), 5)

    def test_inventory_collects_above_retail_and_does_not_leak_to_next_seed(self):
        inv = cp.Inv(supply(4))
        for _ in range(100):
            inv.add("Trophy")
            inv.add("Gold Relic")
            inv.add("Key")
        self.assertEqual((inv.count("Trophy"), inv.count("Gold Relic"), inv.count("Key")), (64, 72, 4))
        small = cp.Inv({"Trophy": 2})
        for _ in range(10):
            small.add("Trophy")
            small.add("Gold Relic")
        self.assertEqual((small.count("Trophy"), small.count("Gold Relic")), (2, 0))
        self.assertEqual(cp.Inv().caps["Trophy"], 16)

    def test_default_postpass_consumes_identical_rng(self):
        original = {"a": ("Trophy", 16), "b": ("AnyRelic", 27), "c": ("Key", 4),
                    "d": ("AnyCtrToken", 16), "e": None}
        for seed in range(30):
            for mode in (1, 2):
                for cap in (4, 8):
                    a, b = copy.deepcopy(original), copy.deepcopy(original)
                    r1, r2 = random.Random(seed), random.Random(seed)
                    cp._post_process(r1, a, mode, cap)
                    cp._post_process(r2, b, mode, cap, supply())
                    self.assertEqual(a, b)
                    self.assertEqual(r1.getstate(), r2.getstate())

    def test_large_pool_draws_high_counts_validates_fills_and_restores(self):
        seen = {1: 0, 2: 0}
        for seed in range(6):
            world = make_world(big_options(), seed=seed)
            plan = world.ctr_content_plan
            self.assertTrue(content_plan.validate(plan))
            for stage in (1, 2):
                for p in records(plan, f"stage{stage}:").values():
                    seen[stage] = max(seen[stage], p["count"])
                    rows = world.ctr_content_items.rows
                    self.assertLessEqual(p["count"], ps.predicate_cap(p, stage, rows))
            if seed == 0:
                mw = filled(world)
                state = mw.get_all_state(False)
                self.assertTrue(all(loc.can_reach(state) for loc in mw.get_locations(1)))
                restored = make_world(big_options(), seed=1000, passthrough=world.fill_slot_data())
                self.assertEqual(restored.ctr_content_plan, plan)
            bad = copy.deepcopy(plan)
            row = next(r for r in bad["requirements"] if r["id"].startswith("stage1:")
                       and r["predicate"].get("item") != content_item_pool.ITEMS["Key"])
            row["predicate"]["count"] = 100
            with self.assertRaises(ValueError):
                content_plan.validate(bad)
        self.assertGreater(seen[1], 8)
        self.assertGreater(seen[2], 4)

    def test_extras_and_additional_starts_do_not_increase_caps(self):
        ledger = content_item_pool.resolve({"extra": {"trophies": 100}}, 1000,
                                           additional={"Trophy": 100})
        rows = ledger.rows
        predicate = dict(op="count", item=content_item_pool.ITEMS["Trophy"], count=8)
        self.assertEqual(ps.predicate_cap(predicate, 1, rows), 8)
        self.assertEqual(ps.predicate_cap(predicate, 2, rows), 4)

    def test_restored_drawn_rules_refuse_unknown_or_non_counted_items(self):
        wire = make_world(options(), seed=1).fill_slot_data()
        token = content_item_pool.ITEMS["Red CTR Token"]
        malformed = [dict(op="count", item=999999, count=1),
                     dict(op="count", item=999999999, count=1),
                     dict(op="count", item=content_item_pool.ITEMS["Wumpa Fruit"], count=1),
                     dict(op="sum", items=[999999, token], count=1),
                     dict(op="sum", items=[token, 999999999], count=1),
                     dict(op="always")]
        for prefix in ("stage1:", "stage2:"):
            for predicate in malformed:
                forged = copy.deepcopy(wire)
                row = next(r for r in forged["content_plan"]["requirements"] if r["id"].startswith(prefix))
                row["predicate"] = predicate
                with self.subTest(stage=prefix, predicate=predicate):
                    with self.assertRaises(OptionError):
                        content_plan.validate(forged["content_plan"])
                    with self.assertRaises(OptionError):
                        make_world({}, passthrough=forged)

    def test_singleton_any_of_matches_the_native_predicate(self):
        for any_item, concrete in (("AnyRelic", "Sapphire Relic"), ("AnyCtrToken", "Red CTR Token"),
                                   ("AnyGem", "Red Gem")):
            one = {concrete: 9}
            self.assertTrue(cp.stage2_met_by_stage1((any_item, 2), (concrete, 1), one))
            self.assertTrue(cp.stage2_met_by_stage1((concrete, 2), (any_item, 1), one))
            self.assertFalse(cp.stage2_met_by_stage1((any_item, 1), (concrete, 2), one))
        self.assertFalse(cp.stage2_met_by_stage1(("AnyRelic", 2), ("Sapphire Relic", 1), supply()))

    def test_small_single_tier_pool_generates_real_distinct_second_stages(self):
        pool = {"base": {"trophies": 4, "tokens": dict.fromkeys(content_item_pool.COLOURS, 1),
                         "relics": {"sapphire": 9, "gold": 0, "platinum": 0}}}
        weights = {"Trophy": 1, **dict.fromkeys(cp.TOKEN_ITEMS + cp.RELIC_ITEMS, 1000)}
        for seed in (0, 1, 2, 6):
            world = make_world(options(item_pool=pool, item_box_count=15, requirement_weights=weights), seed=seed)
            plan = world.ctr_content_plan
            self.assertTrue(content_plan.validate(plan))
            first = records(plan, "stage1:")
            for pad, after in records(plan, "stage2:").items():
                before = first.get(pad)
                if before is not None:
                    a = set(before.get("items", [before.get("item")]))
                    b = set(after.get("items", [after.get("item")]))
                    self.assertFalse(a <= b and after["count"] <= before["count"])
            if seed == 0:
                mw = filled(world)
                state = mw.get_all_state(False)
                self.assertTrue(all(loc.can_reach(state) for loc in mw.get_locations(1)))
