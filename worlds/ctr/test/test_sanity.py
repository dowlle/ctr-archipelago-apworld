"""Sanity picks, route ownership, admission, permanent names and Tracker."""
import copy
import json
import unittest

from Options import ExcludeLocations, OptionError
from .. import content_item_pool, content_plan, ctrAPWorld, sanity
from ..Options import Itemboxsanity, Wumpasanity
from .test_content_plan import make_world, profile_options


class TestSanity(unittest.TestCase):
    def world(self, **options):
        return make_world(dict(profile_options(), **options), seed=3)

    def test_option_bounds(self):
        self.assertEqual(Itemboxsanity.default, 0)
        self.assertEqual(Wumpasanity.default, 0)
        for value in (-1, 51):
            with self.assertRaises(Exception):
                Itemboxsanity.from_any(value)

    def test_defaults_omit_record_and_features(self):
        a = self.world().fill_slot_data()
        b = self.world(itemboxsanity=0, wumpasanity="off").fill_slot_data()
        self.assertEqual(a, b)
        self.assertNotIn("sanity", a["content_plan"])
        self.assertFalse(set(sanity.FEATURES) & set(a["content_plan"]["required_features"]))

    def expanded_groups(self, *groups):
        # Exercise Archipelago's real option verification and group expansion.
        option = ExcludeLocations.from_any(list(groups))
        option.verify(ctrAPWorld, "ContentPlan", 0)
        return option.value

    def test_disabled_groups_do_not_change_the_item_ledger(self):
        baseline = self.world().fill_slot_data()
        for group in ("Weapon Crates", "Wumpa Crates", "Loose Wumpa Fruit"):
            with self.subTest(group=group):
                world = self.world(exclude_locations=self.expanded_groups(group))
                self.assertEqual(world.fill_slot_data(), baseline)

    def test_disabled_group_allows_a_surface_start_from_pool(self):
        start = {"Ignore Ice": 1}
        baseline = self.world(start_inventory_from_pool=start).fill_slot_data()
        world = self.world(start_inventory_from_pool=start,
                           exclude_locations=self.expanded_groups("Weapon Crates", "Wumpa Crates", "Loose Wumpa Fruit"))
        self.assertEqual(world.fill_slot_data(), baseline)

    def test_enabled_groups_reserve_only_the_selected_pickups(self):
        settings = dict(itemboxsanity=5, wumpasanity="both")
        baseline = self.world(**settings).ctr_content_items.wire()
        world = self.world(**settings,
                           exclude_locations=self.expanded_groups("Weapon Crates", "Wumpa Crates", "Loose Wumpa Fruit"))
        self.assertEqual(world.ctr_content_items.wire(), baseline)
        self.assertTrue(set(content_item_pool.SURFACE_NAMES) <= {row.name for row in world.ctr_content_items.rows})

    def test_selected_exclusions_still_keep_their_filler(self):
        options = profile_options()
        options["item_pool"]["base"]["trophies"] = 6
        options.update(itemboxsanity=5, wumpasanity="both",
                       exclude_locations=self.expanded_groups("Weapon Crates", "Wumpa Crates", "Loose Wumpa Fruit"))
        world = make_world(options, seed=3)
        plan = world.ctr_content_plan
        selected = sum(c["kind"] in sanity.KINDS for c in plan["checks"])
        self.assertGreater(selected, 0)
        self.assertGreaterEqual(world.ctr_content_items.filler_count, selected)
        self.assertFalse(set(content_item_pool.SURFACE_NAMES) & {row.name for row in world.ctr_content_items.rows})

    def test_counts_modes_and_tracker(self):
        for boxes, wumpa, ap_boxes in ((5, "off", 0), (50, "off", 50), (0, "both", 0), (50, "both", 50)):
            with self.subTest(boxes=boxes, wumpa=wumpa, ap_boxes=ap_boxes):
                world = self.world(itemboxsanity=boxes, wumpasanity=wumpa, item_box_count=ap_boxes)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                for row in plan["sanity"]["tracks"]:
                    if row["track_id"].startswith("retail:"):
                        # Maintainer ruling, 2026-11-10: Roo's Tubes Weapon Crate 9 is outside the track and never a check.
                        eligible = row["counts"][0] - (1 if row["track_id"] == "retail:6" else 0)
                        self.assertEqual(len(row["weapon_crate"]), min(boxes, eligible))
                        self.assertEqual(len(row["wumpa_crate"]), row["counts"][1] if wumpa == "both" else 0)
                        self.assertEqual(len(row["wumpa_fruit"]), row["counts"][2] if wumpa == "both" else 0)
                wire = json.loads(json.dumps(world.fill_slot_data()))
                tracker = make_world(profile_options(), passthrough=wire)
                self.assertEqual(tracker.ctr_content_plan, plan)
                self.assertEqual(tracker.options.itemboxsanity.value, boxes)
                self.assertEqual(tracker.options.wumpasanity.value, Wumpasanity.from_any(wumpa).value)

    def test_pick_is_stable_and_does_not_follow_ap_box_count(self):
        plans = [self.world(itemboxsanity=5, item_box_count=n).ctr_content_plan for n in (0, 5, 50)]
        retail = lambda p: [r for r in p["sanity"]["tracks"] if r["track_id"].startswith("retail:")]
        self.assertEqual(retail(plans[0]), retail(plans[1]))
        self.assertEqual(retail(plans[0]), retail(plans[2]))
        self.assertTrue(any(r["weapon_crate"] != list(range(1, 6)) for r in retail(plans[0])))

    def test_named_budget_and_identity_freeze(self):
        names = sanity.SANITY_CLASS.name_to_code()
        self.assertEqual(len(names), len(set(names.values())))
        for t in sanity.destinations.NAMED_TRACKS:
            for suffix, count in zip(sanity.SUFFIXES, sanity.BUDGETS):
                self.assertIn(f"{t.ap_name}: {suffix} {count}", names)
        self.assertFalse(any(n.startswith("Custom Track ") for n in names))

    def test_tampered_pick_counts_routes_and_feature_refused(self):
        original = self.world(itemboxsanity=5, wumpasanity="both").ctr_content_plan
        for mutation in ("ordinal", "counts", "hash", "route", "feature", "missing"):
            plan = copy.deepcopy(original)
            if mutation == "ordinal":
                plan["sanity"]["tracks"][0]["weapon_crate"][0] = 81
            elif mutation == "counts":
                plan["sanity"]["tracks"][0]["counts"][0] += 1
            elif mutation == "hash":
                plan["sanity"]["tracks"][0]["lev_sha256"] = "0" * 64
            elif mutation == "route":
                next(c for c in plan["checks"] if c["kind"] in sanity.KINDS)["routes"][0]["award"] = "box"
            elif mutation == "feature":
                plan["required_features"].remove(sanity.FEATURES[0])
            else:
                del plan["sanity"]
            with self.subTest(mutation=mutation), self.assertRaises(OptionError):
                content_plan.validate(plan)

    def test_geometry_rulings(self):
        needs = lambda key, kind, n: sanity.CATALOG[key]["needs"][kind][str(n)]
        # Hot Air Skyway Wumpa Crate 4 stays the unreviewed conservative USF default until the new pictures are reviewed.
        self.assertEqual(needs("retail:7", "wumpa_crate", 4), dict(needs="usf", reviewed=False))
        # Maintainer ruling, 2026-11-10: Cortex Castle Wumpa Crates 7 and 8 both need USF (a ruling, not a default).
        for n in (7, 8):
            self.assertEqual(needs("retail:10", "wumpa_crate", n), dict(needs="usf", reviewed=True))
        # Maintainer ruling, 2026-11-10: Tiger Temple Wumpa Crates 5 to 8 need a door opener only, no USF or boost.
        for n in (5, 6, 7, 8):
            self.assertEqual(needs("retail:4", "wumpa_crate", n), dict(needs="none", reviewed=True, door=True))
        # Maintainer ruling, 2026-11-10: Roo's Tubes Weapon Crate 9 is a dev-placed crate outside the track, so it is excluded.
        self.assertNotIn("weapon_crate", sanity.CATALOG["retail:6"]["needs"])
        self.assertEqual(sanity.CATALOG["retail:6"], sanity.CATALOG[sanity.CATALOG["retail:6"]["lev_sha256"]])
        roo = dict(origin="retail", retail_id=6, display_name="Roo's Tubes")
        record = dict(shortcut_knowledge=2)
        self.assertEqual(sanity.eligible(roo, 0, record, None, None), list(range(1, 9)) + list(range(10, 14)))
        self.assertEqual(sanity.eligible(roo, 1, record, None, None), [1, 2])

    def test_excluded_crates_are_never_picked(self):
        for seed in range(3):
            plan = make_world(dict(profile_options(), itemboxsanity=50), seed=seed).ctr_content_plan
            rows = {r["track_id"]: r for r in plan["sanity"]["tracks"]}
            self.assertEqual(rows["retail:6"]["weapon_crate"], list(range(1, 9)) + list(range(10, 14)))
            forged = copy.deepcopy(plan)
            next(r for r in forged["sanity"]["tracks"] if r["track_id"] == "retail:6")["weapon_crate"][8] = 9
            with self.assertRaises(OptionError):
                content_plan.validate(forged)

    def test_named_revision_exclusions_stay(self):
        # Maintainer ruling, 2026-11-10: North Pole and Ancient Lake Weapon Crate 1 stay excluded (both Ancient Lake revisions).
        from .test_crate_exclusions import ANCIENT_LAKE, NORTH_POLE
        for pin in (*ANCIENT_LAKE, NORTH_POLE):
            track = dict(origin="custom", named_block=0, id="custom/fixture")
            package = dict(files=[dict(role="lev", sha256=pin)], capabilities=dict(weapon_crates=5, fruit_crates=0, loose_fruit=0))
            self.assertNotIn(1, sanity.eligible(track, 0, dict(shortcut_knowledge=2), None, package), pin)

    def test_measured_new_named_revision_defaults_to_usf(self):
        t = dict(origin="custom", named_block=0, id="custom/acid-lake/fixture")
        package = dict(files=[dict(role="lev", sha256="f" * 64)],
                       capabilities=dict(weapon_crates=5, fruit_crates=2, loose_fruit=3))
        inv = sanity.inventory(t, package)
        self.assertEqual(inv["counts"], [5, 2, 3])
        self.assertTrue(all(rule["needs"] == "usf" for family in inv["needs"].values() for rule in family.values()))
        generic = {k: v for k, v in t.items() if k != "named_block"}
        self.assertIsNone(sanity.inventory(generic, package))

    def test_usf_rank_and_tiger_door_terms(self):
        from .test_capability_packs import first_world
        options = dict(profile_options(), itemboxsanity=50, wumpasanity="both", itemsanity=True,
                       progressive_boost="shared_global", progressive_boost_blue_fire=True)
        world = first_world(options, seed=3)
        checks = {c["display_name"]: c for c in world.ctr_content_plan["checks"]}
        self.assertEqual(checks["Hot Air Skyway: Wumpa Crate 4"]["boost"], 2)  # USF, not the optional Blue Fire rank.
        self.assertNotIn("Roo's Tubes: Weapon Crate 9", checks)
        for n in (7, 8):
            self.assertEqual(checks[f"Cortex Castle: Wumpa Crate {n}"]["boost"], 2)
        for n in (5, 6, 7, 8):
            name = f"Tiger Temple: Wumpa Crate {n}"
            self.assertTrue(sanity.CATALOG["retail:4"]["needs"]["wumpa_crate"][str(n)]["door"])
            self.assertNotIn("boost", checks[name])  # a door opener only, never boost

    def test_tiger_temple_door_needs_an_opener_and_no_boost(self):
        from .. import sphere0_guard
        from ..item_boxes import TIGER_TEMPLE_DOOR_OPENERS
        for itemsanity in (True, False):
            world = make_world(dict(profile_options(), itemboxsanity=50, wumpasanity="both", itemsanity=itemsanity,
                                    progressive_boost="shared_global", progressive_stats="off",
                                    character_unlocks=False, wumpa_shop_slots=0), seed=3, stop_before="pre_fill")
            plan = world.ctr_content_plan
            codes = {c["location"]: c for c in plan["checks"]
                     if c["owner"] == "retail:4" and c["display_name"].split(": ")[1].startswith("Wumpa Crate ")
                     and int(c["display_name"].rsplit(" ", 1)[1]) in (5, 6, 7, 8)}
            self.assertEqual(len(codes), 4)
            locations = {l.address: l for l in world.multiworld.get_locations(world.player) if l.address in codes}
            boost = sphere0_guard.starting_boost_item(world)
            items = [i for i in world.multiworld.itempool if i.advancement and i.name != boost
                     and i.name not in TIGER_TEMPLE_DOOR_OPENERS]
            base = sphere0_guard._base_state(world)
            held = lambda extra: sphere0_guard._collect(world, base, items + [world.create_item(n) for n in extra])
            without = held([])
            with_opener = held([TIGER_TEMPLE_DOOR_OPENERS[0]])
            for code, location in locations.items():
                with self.subTest(itemsanity=itemsanity, code=code):
                    # No boost is held in either state: boost never gates these pickups.
                    self.assertEqual(location.can_reach(without), not itemsanity)
                    self.assertTrue(location.can_reach(with_opener))

    def test_cup_and_boss_routes_precede_own_pad(self):
        from .test_27_cups import cups_options
        world = make_world(cups_options(itemboxsanity=5, wumpasanity="both"), seed=1)
        checks = [c for c in world.ctr_content_plan["checks"] if c["kind"] in sanity.KINDS]
        self.assertTrue(checks)
        self.assertTrue(any(any(r["mode"] == "boss_race" for r in c["routes"]) for c in checks))
        self.assertTrue(all(r["mode"] in ("cup", "boss_cup", "boss_race") for c in checks for r in c["routes"]))
        self.assertTrue(content_plan.validate(world.ctr_content_plan))

    def test_location_exclusion_groups(self):
        from .. import ctrAPWorld
        for group, suffix in (("Weapon Crates", "Weapon Crate "), ("Wumpa Crates", "Wumpa Crate "),
                              ("Loose Wumpa Fruit", "Wumpa Fruit ")):
            names = ctrAPWorld.location_name_groups[group]
            self.assertTrue(names)
            self.assertTrue(all(suffix in n for n in names))

    def test_opening_forecast_matches_pickup_rules(self):
        from .. import content_opening, sphere0_guard
        from ..item_boxes import TIGER_TEMPLE_DOOR_OPENERS
        from .test_27_cups import cups_options
        options = dict(itemboxsanity=50, wumpasanity="both", progressive_boost="shared_global",
                       progressive_stats="off", character_unlocks=False, wumpa_shop_slots=0)
        cases = (dict(profile_options(), **options, itemsanity=True),
                 cups_options(**options, boss_garages=False, oxide_goal="disabled", bosses_required_goal=0,
                              gems_required_goal=5, shuffle_keys=True))
        for index, settings in enumerate(cases):
            world = make_world(settings, seed=3, stop_before="pre_fill")
            plan = world.ctr_content_plan
            boost = sphere0_guard.starting_boost_item(world)
            reach = content_opening.PlanReach(plan, world.ctr_content_items.rows, set(), boost)
            codes = {c["location"] for c in plan["checks"] if c["kind"] in sanity.KINDS}
            locations = {location.address: location for location in world.multiworld.get_locations(world.player)
                         if location.address in codes}
            self.assertTrue(codes)
            items = [item for item in world.multiworld.itempool if item.advancement and item.name != boost
                     and item.name not in TIGER_TEMPLE_DOOR_OPENERS]
            base = sphere0_guard._base_state(world)
            for rank in (0, 1, 2):
                held_items = items + [world.create_item(boost) for _ in range(rank)]
                state = sphere0_guard._collect(world, base, held_items)
                held = tuple(sorted(item.name for item in held_items))
                predicted = reach._sweep(reach._held(held)) & codes
                actual = {code for code, location in locations.items() if location.can_reach(state)}
                with self.subTest(case=index, rank=rank):
                    self.assertEqual(predicted, actual)
                if index == 0:
                    self.assertTrue(sanity.door_codes(plan))
                    self.assertFalse(sanity.door_codes(plan) & actual)

    def test_opening_forecast_keeps_cup_prefix_boost(self):
        from .. import content_cups, content_opening, sphere0_guard
        from .test_27_cups import cups_options
        world = make_world(cups_options(itemboxsanity=50, wumpasanity="both", progressive_boost="shared_global"),
                           seed=3, stop_before="pre_fill")
        plan = world.ctr_content_plan
        reach = content_opening.PlanReach(plan, world.ctr_content_items.rows, set(),
                                          sphere0_guard.starting_boost_item(world))
        checks = {c["location"]: c for c in plan["checks"]}
        tracks = {t["id"]: t for t in plan["tracks"]}
        packages = {p["id"]: p for p in plan["packages"]}
        entries = {e["id"]: e for e in plan["entries"]}
        constrained = 0
        for code, _spot, _floor, routes in reach.checks:
            if checks[code]["kind"] not in sanity.KINDS:
                continue
            for _own, _later, route, need, _boost in routes or ():
                if route["leg_id"] is None:
                    continue
                prefix = content_cups.prefix_boost(entries[route["entry_id"]], route["leg_id"], tracks,
                                                    plan["capability"], packages)
                if prefix > checks[code].get("boost", 0):
                    constrained += 1
                    self.assertGreaterEqual(need, prefix)
        self.assertGreater(constrained, 0)
