"""One generator row 2: plan content behind content_pool. The original Gem Cups,
`cups.tracks`, the five surface items, Platinum 0 and relic checks that follow
the item counts (ruled 2026-10-30)."""
import copy
import json
import unittest

from Options import OptionError

from .. import content_bosses, content_cups, content_item_pool, content_plan, cup_checks, gem_cup_legs
from .test_content_plan import make_world, profile_options
from .test_track_modes import mode_pool

GEM_NAMES = ("Red Gem Cup", "Green Gem Cup", "Blue Gem Cup", "Yellow Gem Cup", "Purple Gem Cup")
RELIC_CODE = {name: content_plan.CTR_LOCATION_IDS[f"Crash Cove: {name} Time Trial"]
              for name in ("Sapphire", "Gold", "Platinum")}
TRIAL_IDS = ("retail:16", "retail:17")


def plan_options(cups=None, modes=("trophy",), **extra):
    options = profile_options()
    options["content_pool"]["tracks"]["modes"] = list(modes)
    options["content_pool"]["cups"] = dict(count=5) if cups is None else cups
    options.update(extra)
    return options


def relic_options(relics, extra=None, retail="all"):
    options = plan_options(dict(count=0), modes=("trophy", "ctr", "relic"))
    options["content_pool"]["tracks"]["retail"] = retail
    options["item_pool"] = mode_pool()
    options["item_pool"]["base"]["relics"] = relics
    if extra:
        options["item_pool"]["extra"] = dict(relics=extra)
    return options


def cups_of(plan):
    return [e for e in plan["entries"] if e["kind"] == "cup"]


def gems_of(plan):
    return sorted((c for c in cups_of(plan) if content_cups.gem_colour(c["id"]) is not None),
                  key=lambda c: c["id"])


def pool_cups(plan):
    return [c for c in cups_of(plan) if content_cups.gem_colour(c["id"]) is None]


def relic_checks(plan, tier):
    return [c for c in plan["checks"] if c["kind"] == "relic" and c["routes"][0]["award"] == tier]


def tracker(world):
    wire = json.loads(json.dumps(world.fill_slot_data()))
    return make_world({}, passthrough=wire)


class TestGemCups(unittest.TestCase):
    def test_counts_keep_the_first_cups_red_first(self):
        for count in (1, 3, 5, 7):
            with self.subTest(count=count):
                plan = make_world(plan_options(dict(count=count))).ctr_content_plan
                gems = gems_of(plan)
                self.assertEqual([c["display_name"] for c in gems], list(GEM_NAMES[:min(count, 5)]))
                self.assertEqual(len(pool_cups(plan)), max(0, count - 5))
                self.assertIn(content_cups.GEM_FEATURE, plan["required_features"])
                for cup in pool_cups(plan):
                    self.assertIn(cup["display_name"], cup_checks.CUP_NAMES)

    def test_no_cups_declare_no_gem_feature(self):
        plan = make_world(plan_options(dict(count=0))).ctr_content_plan
        self.assertNotIn(content_cups.GEM_FEATURE, plan["required_features"])

    def test_frozen_gem_and_sweep_ids(self):
        plan = make_world(plan_options(dict(count=7), cup_sweep_checks=True)).ctr_content_plan
        checks = {c["location"]: c for c in plan["checks"]}
        for colour, name in enumerate(GEM_NAMES):
            win, sweep = checks[35011200 + colour], checks[35028300 + colour]
            self.assertEqual((win["display_name"], win["kind"], win["owner"]),
                             (f"{name}: Gem", "cup", f"gem_cup:{colour}"))
            self.assertEqual((sweep["display_name"], sweep["kind"], sweep["owner"]),
                             (f"{name}: Win All Legs", "cup_sweep", f"gem_cup:{colour}"))
            self.assertEqual(win["routes"][0]["entry_id"], f"entry/gem_cup:{colour}")
            self.assertEqual(win["routes"][0]["award"], "win")
        for cup in pool_cups(plan):
            index = int(cup["id"].split(":")[1])
            self.assertIn(35027000 + index, checks)
            self.assertIn(35027200 + index, checks)

    def test_gems_stay_shuffled_items(self):
        world = make_world(plan_options(), stop_before="pre_fill")
        names = [item.name for item in world.multiworld.itempool]
        self.assertTrue(all(names.count(f"{colour} Gem") == 1 for colour in ("Red", "Green", "Blue", "Yellow", "Purple")))
        self.assertTrue(all(location.item is None for location in world.multiworld.get_locations(1)
                            if location.name.endswith(": Gem")))

    def test_hit_character_uses_the_retail_cup_orders(self):
        options = plan_options(dict(count=6), hit_character=True)
        plan_world = make_world(options)
        wire = json.loads(json.dumps(plan_world.fill_slot_data()))
        block = wire["hit_character_encounters"]
        self.assertEqual(list(block["content_cups"]), [cup["id"].split(":")[1] for cup in pool_cups(wire["content_plan"])])
        self.assertTrue({"100", "101", "102", "103", "104"} <= set(block["cups"]))
        self.assertEqual(tracker(plan_world).ctr_content_plan, plan_world.ctr_content_plan)

    def test_validator_refuses_a_forged_lineup(self):
        plan = make_world(plan_options(dict(count=6))).ctr_content_plan
        missing_red = copy.deepcopy(plan)
        cup = next(e for e in missing_red["entries"] if e["id"] == "entry/gem_cup:0")
        cup["id"] = "entry/gem_cup:4x"
        with self.assertRaises(OptionError):
            content_plan.validate(missing_red)
        with self.assertRaisesRegex(OptionError, "first five cups"):
            content_cups.check_lineup([dict(id="entry/gem_cup:1", kind="cup")])
        with self.assertRaisesRegex(OptionError, "first five cups"):
            content_cups.check_lineup([dict(id="entry/gem_cup:0", kind="cup"), dict(id="entry/cup:3", kind="cup")])
        self.assertIsNone(content_cups.gem_colour("entry/gem_cup:5"))
        self.assertIsNone(content_cups.gem_colour("entry/gem_cup:01"))

    def test_tracker_restores_the_plan(self):
        world = make_world(plan_options(dict(count=7), cup_sweep_checks=True))
        restored = tracker(world)
        self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual({loc.name for loc in restored.multiworld.get_locations(1)},
                         {loc.name for loc in world.multiworld.get_locations(1)})


class TestCupTracks(unittest.TestCase):
    def legs(self, plan, cup):
        names = {t["id"]: t["display_name"] for t in plan["tracks"]}
        return [names[leg["track_id"]] for leg in cup["legs"]]

    def test_off_races_the_original_tracks_and_a_sixth_cup_draws(self):
        table = gem_cup_legs.load_vanilla_cup_legs()
        for seed in range(6):
            plan = make_world(plan_options(dict(count=7, tracks="off")), seed=seed).ctr_content_plan
            for cup in gems_of(plan):
                self.assertEqual(self.legs(plan, cup), table[cup["display_name"]])
            for cup in pool_cups(plan):
                self.assertEqual(len(set(self.legs(plan, cup))), 4)

    def test_a_yaml_off_reads_as_false(self):
        self.assertEqual(content_cups.settings(dict(count=1, tracks=False))["tracks"], "off")

    def test_random_no_repeats_is_the_default(self):
        spec = content_cups.settings(dict(count=1))
        self.assertEqual((spec["tracks"], spec["repeats"]["within_cup"]), ("random_no_repeats", False))

    def test_random_allows_repeats_inside_a_cup(self):
        seen = False
        for seed in range(20):
            plan = make_world(plan_options(dict(count=5, tracks="random")), seed=seed).ctr_content_plan
            seen |= any(len(set(self.legs(plan, cup))) < 4 for cup in cups_of(plan))
        self.assertTrue(seen)

    def test_trial_tracks_are_never_cup_races(self):
        for value in content_cups.CUP_TRACKS:
            for seed in range(8):
                plan = make_world(plan_options(dict(count=7, tracks=value)), seed=seed).ctr_content_plan
                legs = {leg["track_id"] for cup in cups_of(plan) for leg in cup["legs"]}
                self.assertFalse(legs & set(TRIAL_IDS), value)

    def test_tracks_wins_over_the_older_repeats_key(self):
        spec = content_cups.settings(dict(count=1, tracks="random_no_repeats",
                                          composition=dict(repeats=dict(within_cup=True))))
        self.assertFalse(spec["repeats"]["within_cup"])
        spec = content_cups.settings(dict(count=1, tracks="random",
                                          composition=dict(repeats=dict(within_cup=False))))
        self.assertTrue(spec["repeats"]["within_cup"])
        spec = content_cups.settings(dict(count=1, tracks="off", composition=dict(repeats=dict(within_cup=True))))
        self.assertFalse(spec["repeats"]["within_cup"])

    def test_the_older_repeats_key_still_works_alone(self):
        spec = content_cups.settings(dict(count=1, composition=dict(repeats=dict(within_cup=True))))
        self.assertEqual(spec["tracks"], "random")
        spec = content_cups.settings(dict(count=1, composition=dict(repeats=dict(within_cup=False))))
        self.assertEqual(spec["tracks"], "random_no_repeats")

    def test_unknown_value_refuses(self):
        for value in ("shuffled", None, True, 0):
            with self.assertRaisesRegex(OptionError, "cups.tracks must be"):
                content_cups.settings(dict(count=1, tracks=value))

    def test_off_needs_the_original_tracks_of_the_seeds_cups(self):
        options = plan_options(dict(count=5, tracks="off"))
        # Red, Green, Blue and Yellow Gem Cups, without Crash Cove (0) in the selection.
        options["content_pool"]["tracks"]["retail"] = [i for i in range(18) if i != 0]
        options["content_pool"]["required_entries"] = []
        with self.assertRaisesRegex(OptionError, "cups.tracks off"):
            make_world(options)


class TestSurfaceItems(unittest.TestCase):
    def names(self, world):
        return [item.name for item in world.multiworld.itempool]

    def test_a_plan_creates_the_five(self):
        world = make_world(plan_options(dict(count=0)))
        names = self.names(world)
        for name in content_item_pool.SURFACE_NAMES:
            self.assertEqual(names.count(name), 1)
        self.assertIn(content_plan.SURFACE_FEATURE, world.ctr_content_plan["required_features"])
        rows = {r["item"]: r for r in world.ctr_content_plan["items"]["rows"]}
        self.assertTrue(all((rows[c]["base"], rows[c]["extra"]) == (1, 0) for c in content_plan.SURFACE_CODES))
        self.assertEqual({name: world.create_item(name).useful for name in content_item_pool.SURFACE_NAMES},
                         dict.fromkeys(content_item_pool.SURFACE_NAMES, True))

    def test_they_go_together_when_the_items_do_not_fit(self):
        options = plan_options(dict(count=0))
        options["item_pool"]["base"]["trophies"] = 2  # 19 checks, 11 counted items, one reserve short at 15
        fits = make_world(options)
        self.assertIn("Ignore Ice", self.names(fits))
        options["item_pool"]["base"]["trophies"] = 8  # 17 counted, 2 slots left
        world = make_world(options)
        self.assertFalse(set(self.names(world)) & set(content_item_pool.SURFACE_NAMES))
        self.assertNotIn(content_plan.SURFACE_FEATURE, world.ctr_content_plan["required_features"])
        self.assertEqual(world.ctr_content_plan["items"]["filler_count"], 2)

    def test_the_refusal_comes_after_the_drop(self):
        options = plan_options(dict(count=0))
        options["item_pool"]["base"]["trophies"] = 12  # 21 counted items on 19 checks
        with self.assertRaisesRegex(OptionError, "21 selected copies for 19 free checks.*Short by 2 checks"):
            make_world(options)

    def test_excluded_checks_keep_their_filler(self):
        plan = content_item_pool.resolve(dict(base=dict(trophies=0, relics=dict(sapphire=0, gold=0, platinum=0),
                                                        tokens=dict.fromkeys(content_item_pool.COLOURS, 0))), 16,
                                         surface=content_item_pool.SURFACE_NAMES, filler_reserve=2)
        self.assertEqual(plan.filler_count, 2)
        self.assertTrue(any(row.name == "Ignore Ice" for row in plan.rows))
        plan = content_item_pool.resolve(dict(base=dict(trophies=0, relics=dict(sapphire=0, gold=0, platinum=0),
                                                        tokens=dict.fromkeys(content_item_pool.COLOURS, 0))), 16,
                                         surface=content_item_pool.SURFACE_NAMES, filler_reserve=3)
        self.assertEqual(plan.filler_count, 7)
        self.assertFalse(any(row.name == "Ignore Ice" for row in plan.rows))

    def test_more_excluded_checks_than_filler_refuses(self):
        options = plan_options(dict(count=0))
        options["item_pool"]["base"]["trophies"] = 9  # 18 counted items on 19 checks, one filler slot
        options["exclude_locations"] = ["Crash Cove: Trophy Race", "Roo's Tubes: Trophy Race"]
        with self.assertRaisesRegex(OptionError, "An excluded check holds only filler"):
            make_world(options)
        options["exclude_locations"] = ["Crash Cove: Trophy Race"]
        self.assertEqual(make_world(options).ctr_content_plan["items"]["filler_count"], 1)

    def test_the_goal_check_counts_once(self):
        from .test_content_bosses import boss_options
        options = boss_options()
        options["item_pool"]["extra"] = dict(trophies=18)  # one filler slot, for the goal check
        name = content_plan.LOCATION_BY_CODE[content_bosses.OXIDE_FIRST]
        options["exclude_locations"] = [name]
        self.assertEqual(make_world(options).ctr_content_plan["items"]["filler_count"], 1)

    def test_a_name_outside_the_seed_is_not_counted(self):
        options = plan_options(dict(count=0))
        options["item_pool"]["base"]["trophies"] = 9
        options["exclude_locations"] = ["Crash Cove: Trophy Race", "Sewer Speedway: Sapphire Time Trial"]
        self.assertEqual(make_world(options).ctr_content_plan["items"]["filler_count"], 1)

    def test_a_start_of_a_dropped_item_refuses_with_a_reason(self):
        raw = dict(base=dict(trophies=7, relics=dict(sapphire=0, gold=0, platinum=0),
                             tokens=dict.fromkeys(content_item_pool.COLOURS, 0)))
        with self.assertRaisesRegex(OptionError, "surface items do not fit"):
            content_item_pool.resolve(raw, 17, starts={"Ignore Ice": 1},
                                      surface=content_item_pool.SURFACE_NAMES, filler_reserve=1)

    def test_validator_refuses_part_of_the_pack(self):
        plan = copy.deepcopy(make_world(plan_options(dict(count=0))).ctr_content_plan)
        row = next(r for r in plan["items"]["rows"] if r["item"] in content_plan.SURFACE_CODES)
        plan["items"]["rows"].remove(row)
        plan["items"]["filler_count"] += 1
        with self.assertRaisesRegex(OptionError, "surface items"):
            content_plan.validate(plan)


class TestRelicChecks(unittest.TestCase):
    def test_platinum_defaults_to_zero_with_no_platinum_checks(self):
        options = relic_options(dict(sapphire=18, gold=18))
        plan = make_world(options).ctr_content_plan
        self.assertFalse(relic_checks(plan, "platinum"))
        row = next(r for r in plan["items"]["rows"] if r["item"] == content_item_pool.ITEMS["Platinum Relic"])
        self.assertEqual(row["base"], 0)

    def test_a_tier_exists_on_as_many_races_as_it_has_items(self):
        for seed in range(8):
            plan = make_world(relic_options(dict(sapphire=6, gold=4, platinum=0)), seed=seed).ctr_content_plan
            self.assertEqual((len(relic_checks(plan, "sapphire")), len(relic_checks(plan, "gold"))), (6, 4))
            self.assertIn(content_plan.RELIC_FEATURE, plan["required_features"])

    def test_the_draw_varies_by_seed(self):
        drawn = {tuple(sorted(c["owner"] for c in relic_checks(
            make_world(relic_options(dict(sapphire=6, gold=4, platinum=0)), seed=seed).ctr_content_plan, "gold")))
            for seed in range(6)}
        self.assertGreater(len(drawn), 1)

    def test_extras_count_as_items_of_the_tier(self):
        plan = make_world(relic_options(dict(sapphire=2, gold=0, platinum=0), dict(sapphire=3))).ctr_content_plan
        self.assertEqual(len(relic_checks(plan, "sapphire")), 5)

    def test_capped_by_the_relic_races_and_items_land_elsewhere(self):
        options = relic_options(dict(sapphire=8, gold=0, platinum=0), retail=list(range(6)))
        options["item_pool"]["base"]["trophies"] = 0
        options["item_pool"]["base"]["tokens"] = dict.fromkeys(content_item_pool.COLOURS, 0)
        world = make_world(options)
        plan = world.ctr_content_plan
        races = sum(e["kind"] == "track" and "relic" in e["modes"] for e in plan["entries"])
        self.assertEqual(races, 6)  # Baby T Park runs no Relic Race
        self.assertEqual(len(relic_checks(plan, "sapphire")), 6)
        self.assertEqual(sum(item.name == "Sapphire Relic" for item in world.multiworld.itempool), 8)

    def test_a_full_tier_takes_no_draw(self):
        class Fail:
            def sample(self, *_):
                raise AssertionError("no draw")
        world = make_world(relic_options(dict(sapphire=6, gold=4, platinum=0)))
        world.random, kept = Fail(), world.random
        self.assertEqual(content_plan.draw_relic_checks(world, ["a", "b"], dict(sapphire=2, gold=3, platinum=2))["a"],
                         {"sapphire", "gold", "platinum"})
        world.random = kept

    def test_all_three_tiers_declare_no_feature(self):
        options = relic_options(dict(sapphire=18, gold=18, platinum=18), retail=list(range(6)))
        options["item_pool"]["base"]["trophies"] = 0
        options["content_pool"]["required_entries"] = []
        options["content_pool"]["tracks"]["custom"] = []
        options["item_pool"]["base"]["relics"] = dict.fromkeys(("sapphire", "gold", "platinum"), 6)
        options["item_pool"]["base"]["tokens"] = dict.fromkeys(content_item_pool.COLOURS, 0)
        plan = make_world(options).ctr_content_plan
        self.assertNotIn(content_plan.RELIC_FEATURE, plan["required_features"])

    def test_a_relic_race_without_checks_is_never_first(self):
        for order in ("per_seed", "per_pad"):
            for seed in range(6):
                options = relic_options(dict(sapphire=2, gold=1, platinum=0))
                options["pad_layout"]["mode_order"] = order
                plan = make_world(options, seed=seed).ctr_content_plan
                with_checks = {c["owner"] for c in plan["checks"] if c["kind"] == "relic"}
                for entry in plan["entries"]:
                    if entry["kind"] == "track" and len(entry["modes"]) > 1 and entry["track_id"] not in with_checks:
                        self.assertNotEqual(entry["modes"][0], "relic")

    def test_validator_refuses_a_count_that_does_not_follow(self):
        plan = copy.deepcopy(make_world(relic_options(dict(sapphire=6, gold=4, platinum=0))).ctr_content_plan)
        check = relic_checks(plan, "gold")[0]
        plan["checks"].remove(check)
        plan["items"]["coded_checks"] -= 1
        plan["items"]["filler_count"] -= 1
        with self.assertRaises(OptionError):
            content_plan.validate(plan)

    def test_tracker_restores_the_drawn_tiers(self):
        world = make_world(relic_options(dict(sapphire=6, gold=4, platinum=0)))
        restored = tracker(world)
        self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual({loc.name for loc in restored.multiworld.get_locations(1)},
                         {loc.name for loc in world.multiworld.get_locations(1)})

    def test_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        for value in content_cups.CUP_TRACKS:
            for count in (3, 7):
                options = relic_options(dict(sapphire=8, gold=5, platinum=2))
                options["content_pool"]["cups"] = dict(count=count, tracks=value)
                for seed in range(3):
                    with self.subTest(value=value, count=count, seed=seed):
                        world = make_world(options, seed=seed)
                        distribute_items_restrictive(world.multiworld)
                        self.assertTrue(world.multiworld.can_beat_game())
                        self.assertFalse(world.multiworld.precollected_items[1])
                        self.assertTrue(all(loc.item for loc in world.multiworld.get_locations(1)))


if __name__ == "__main__":
    unittest.main()
