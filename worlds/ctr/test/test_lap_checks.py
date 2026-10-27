"""#344 lap completion checks: option, normal-room routes and rules, wire,
Universal Tracker, and the content-plan path."""
import copy
import unittest

from BaseClasses import CollectionState
from NetUtils import convert_to_base_types
from Options import OptionError

from .test_content_plan import make_world, profile_options
from .. import content_laps, content_plan
from ..item_boxes import BOX_TRACKS, TRACK_LEVEL_IDS
from ..lap_checks import (LAP_COMPLETION_CLASS, LAP_CORTEX_VORTEX_CODE, LAP_CUSTOM_CODE_BASE, LAP_RETAIL_CODE_BASE,
                          lap_name, region_name)
from ..progressive_capability import boost_item_name


def lap_locations(world):
    return {loc.name: loc for loc in world.multiworld.get_locations(1) if loc.name.endswith(": Complete One Lap")}


class TestNormalRoom(unittest.TestCase):
    def test_default_off_creates_nothing(self):
        world = make_world({})
        wire = world.fill_slot_data()
        self.assertFalse(lap_locations(world))
        self.assertNotIn("lap_checks", wire)
        self.assertNotIn("lap_completion_checks", wire["ctr_options"])
        self.assertEqual(LAP_COMPLETION_CLASS.created_location_names(world.options), [])

    def test_on_creates_every_raced_track_with_frozen_codes(self):
        off, on = make_world({}), make_world({"lap_completion_checks": True})
        laps = lap_locations(on)
        self.assertEqual(len(laps), 18)
        self.assertEqual(len(on.multiworld.get_locations(1)), len(off.multiworld.get_locations(1)) + 18)
        for i, track in enumerate(BOX_TRACKS):
            loc = laps[lap_name(track)]
            self.assertEqual(loc.address, LAP_RETAIL_CODE_BASE + i)
            self.assertEqual(loc.parent_region.name, region_name(track))
            # The track's own pad is a route; nothing else of the track is in the region.
            self.assertEqual(list(loc.parent_region.locations), [loc])
            self.assertIn(track, {e.parent_region.name for e in loc.parent_region.entrances})
        wire = on.fill_slot_data()
        self.assertIs(wire["ctr_options"]["lap_completion_checks"], True)
        self.assertEqual(wire["lap_checks"], dict(
            version=1, custom_slots={},
            tracks={str(TRACK_LEVEL_IDS[t]): LAP_RETAIL_CODE_BASE + i
                    for i, t in sorted(enumerate(BOX_TRACKS), key=lambda p: TRACK_LEVEL_IDS[p[1]])}))
        self.assertEqual(sorted(LAP_COMPLETION_CLASS.created_location_names(on.options)), sorted(laps))
        self.assertEqual(len(on.multiworld.itempool), len(on.multiworld.get_unfilled_locations(1)))

    def test_cup_legs_are_routes_with_their_ordered_prefix(self):
        world = make_world({"lap_completion_checks": True, "randomize_gem_cup_tracks": True}, seed=19)
        for track in BOX_TRACKS[:16]:
            region = world.multiworld.get_region(region_name(track), 1)
            cups = {e.parent_region.name for e in region.entrances} - {track}
            want = {cup for cup, legs in world.gem_cup_legs.items() if track in legs}
            self.assertEqual(cups, want, track)
        prefixes = {(e.parent_region.name, stem): prefix for e, stem, _src, prefix in world._ctr_lap_routes}
        for cup, legs in world.gem_cup_legs.items():
            for track in set(legs):
                self.assertEqual(prefixes[(cup, track)], legs[:legs.index(track) + 1])

    def test_finish_term_on_pad_and_cup_routes(self):
        world = make_world({"lap_completion_checks": True, "progressive_boost": "shared_global",
                            "character_unlocks": False})
        hot_air = world.multiworld.get_entrance("Hot Air Skyway -> Hot Air Skyway: Lap", 1)
        crash_cove = world.multiworld.get_entrance("Crash Cove -> Crash Cove: Lap", 1)
        state = CollectionState(world.multiworld)
        self.assertFalse(hot_air.access_rule(state))  # USF crosses the climb
        self.assertTrue(crash_cove.access_rule(state))  # no finish term, no win term
        cup_routes = [(e, prefix) for e, stem, src, prefix in world._ctr_lap_routes if prefix is not None]
        from ..usf_finish import ALL_USF_FINISH_TRACKS
        gated = [e for e, prefix in cup_routes if "Hot Air Skyway" in prefix]
        free = [e for e, prefix in cup_routes if not ALL_USF_FINISH_TRACKS.intersection(prefix)]
        self.assertTrue(gated and free)
        self.assertFalse(any(e.access_rule(state) for e in gated))
        self.assertTrue(all(e.access_rule(state) for e in free))
        for _ in range(2):
            state.collect(world.create_item(boost_item_name()), True)
        self.assertTrue(hot_air.access_rule(state))
        self.assertTrue(all(e.access_rule(state) for e in gated))

    def test_cortex_vortex_pad_track_and_dropped_destination(self):
        from .test_cortex_vortex_track import _build
        from ..cortex_vortex_track import dropped_region
        mw = _build(dropped=2, lap_completion_checks=True)  # Blizzard Bluff has no pad
        world = mw.worlds[1]
        lost = dropped_region(world.options)
        self.assertEqual(lost, "Blizzard Bluff")
        names = {loc.name for loc in mw.get_locations(1)}
        self.assertIn(lap_name("Cortex Vortex"), names)
        self.assertEqual(mw.get_location(lap_name("Cortex Vortex"), 1).address, LAP_CORTEX_VORTEX_CODE)
        wire = world.fill_slot_data()
        self.assertEqual(wire["lap_checks"]["tracks"]["110"], LAP_CORTEX_VORTEX_CODE)
        # The vanilla legs still race Blizzard Bluff in a Gem Cup: only those
        # Cups reach its lap check, never its own (padless) region.
        dropped = mw.get_region(region_name(lost), 1)
        sources = {e.parent_region.name for e in dropped.entrances}
        self.assertNotIn(lost, sources)
        self.assertEqual(sources, {cup for cup, legs in world.gem_cup_legs.items() if lost in legs})
        self.assertTrue(sources)
        self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations(1)))

    def test_legacy_custom_track_uses_its_named_block(self):
        from .test_custom_tracks import BABY_T_PARK, NAMED
        from ..named_tracks import location_code
        world = make_world({"lap_completion_checks": True, "custom_tracks": BABY_T_PARK})
        laps = lap_locations(world)
        entry = next(iter(world.custom_tracks.values()))
        code = location_code(entry["named_block"], "lap")
        self.assertEqual(laps[lap_name(NAMED)].address, code)
        self.assertEqual(world.fill_slot_data()["lap_checks"]["custom_slots"], {str(entry["slot"]): code})
        self.assertNotIn(lap_name(NAMED), LAP_COMPLETION_CLASS.created_location_names(world.options))
        from ..custom_track_ids import created_named_location_names
        self.assertIn(lap_name(NAMED), created_named_location_names(world.options))
        self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))

    def test_generic_custom_slot_code(self):
        from ..lap_checks import custom_code
        self.assertEqual(custom_code({"slot": 1}), LAP_CUSTOM_CODE_BASE)
        self.assertEqual(custom_code({"slot": 132, "named_block": None}), LAP_CUSTOM_CODE_BASE + 131)

    def test_tracker_roundtrip_and_old_seed(self):
        world = make_world({"lap_completion_checks": True, "randomize_gem_cup_tracks": True}, seed=19)
        wire = convert_to_base_types(world.fill_slot_data())
        tracker = make_world({}, seed=987, passthrough=wire)
        self.assertEqual(tracker.fill_slot_data()["lap_checks"], wire["lap_checks"])
        self.assertEqual({l.address for l in tracker.multiworld.get_locations(1)},
                         {l.address for l in world.multiworld.get_locations(1)})
        old = make_world({}).fill_slot_data()
        tracker = make_world({"lap_completion_checks": True}, passthrough=old)
        self.assertFalse(tracker.options.lap_completion_checks.value)
        self.assertFalse(lap_locations(tracker))

    def test_saved_block_refuses_forgery(self):
        wire = make_world({"lap_completion_checks": True}).fill_slot_data()
        for mutation in range(5):
            bad = copy.deepcopy(wire)
            if mutation == 0: bad["lap_checks"]["tracks"]["0"] += 1
            if mutation == 1: bad["lap_checks"]["tracks"].pop("0")
            if mutation == 2: bad["ctr_options"]["lap_completion_checks"] = 1
            if mutation == 3: del bad["lap_checks"]
            if mutation == 4: bad["lap_checks"]["version"] = 2
            with self.subTest(mutation=mutation), self.assertRaises(OptionError):
                make_world({}, passthrough=bad)
        bad = copy.deepcopy(make_world({}).fill_slot_data())
        bad["lap_checks"] = wire["lap_checks"]
        with self.assertRaises(OptionError):
            make_world({}, passthrough=bad)

    def test_win_logic_export_unchanged_by_dead_end_routes(self):
        import random
        from .test_win_logic_parity import check_seed
        for boost in ("off", "per_character"):
            world = make_world({"lap_completion_checks": True, "progressive_boost": boost,
                                "randomize_gem_cup_tracks": True, "racer_locked_pads": True}, seed=19)
            wire = world.fill_slot_data()
            self.assertFalse(any(str(c) in wire["win_logic"]["checks"]
                                 for c in range(LAP_RETAIL_CODE_BASE, LAP_RETAIL_CODE_BASE + 18)))
            self.assertEqual(check_seed(world.multiworld, random.Random(42), states_per_seed=20), [])


def lap_plan_options(**extra):
    options = profile_options()
    options["lap_completion_checks"] = True
    options.update(extra)
    return options


class TestContentPlan(unittest.TestCase):
    def test_off_keeps_the_plan(self):
        baseline = make_world(profile_options()).ctr_content_plan
        self.assertFalse(any(c["kind"] == content_laps.KIND for c in baseline["checks"]))
        self.assertNotIn(content_laps.FEATURE, baseline["required_features"])

    def test_every_standalone_track_has_one_lap_check_per_mode_route(self):
        options = lap_plan_options()
        options["content_pool"]["tracks"]["modes"] = ["trophy", "ctr", "relic"]
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        world = make_world(options)
        plan = world.ctr_content_plan
        self.assertEqual(plan["required_features"][-1], content_laps.FEATURE)
        laps = [c for c in plan["checks"] if c["kind"] == content_laps.KIND]
        tracks = {e["track_id"]: e for e in plan["entries"] if e["kind"] == "track"}
        self.assertEqual({c["owner"] for c in laps}, set(tracks))
        for check in laps:
            entry = tracks[check["owner"]]
            self.assertEqual([r["mode"] for r in check["routes"]], entry["modes"])
            self.assertTrue(all(r["award"] == "lap" and r["leg_id"] is None and r["entry_id"] == entry["id"]
                                for r in check["routes"]))
            track = next(t for t in plan["tracks"] if t["id"] == check["owner"])
            self.assertEqual(check["location"], content_plan.lap_location(track))
            self.assertEqual(check["display_name"], content_plan.room_title(track) + ": Complete One Lap")
        cortex = next(c for c in laps if c["owner"] == content_plan.CORTEX_TRACK_ID)
        self.assertEqual(cortex["location"], LAP_CORTEX_VORTEX_CODE)
        custom = next(c for c in laps if c["owner"].startswith("custom/"))
        self.assertEqual(custom["display_name"], "Baby T Park: Complete One Lap")
        self.assertTrue(content_plan.validate(plan))
        self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))

    def test_cup_legs_are_routes_in_entry_then_leg_order(self):
        from .test_content_cups import cup_options
        for seed in range(6):
            options = cup_options(seed)
            options["lap_completion_checks"] = True
            try:
                world = make_world(options, seed=seed)
            except OptionError:
                continue
            plan = world.ctr_content_plan
            laps = {c["owner"]: c for c in plan["checks"] if c["kind"] == content_laps.KIND}
            pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
            want = {}
            for entry in plan["entries"]:
                if entry["kind"] == "track":
                    want.setdefault(entry["track_id"], []).extend((entry["id"], m, None) for m in entry["modes"])
                elif entry["kind"] == "cup":
                    for leg in entry["legs"]:
                        want.setdefault(leg["track_id"], []).append((entry["id"], "cup", leg["id"]))
            self.assertEqual(set(laps), set(want), seed)
            for track, routes in want.items():
                self.assertEqual([(r["entry_id"], r["mode"], r["leg_id"]) for r in laps[track]["routes"]], routes)
                self.assertTrue(all(r["own_pad_id"] == pads[r["entry_id"]] for r in laps[track]["routes"]))
            self.assertTrue(content_plan.validate(plan))

    def test_validate_refuses_forged_lap_checks(self):
        plan = make_world(lap_plan_options()).ctr_content_plan
        lap = next(c for c in plan["checks"] if c["kind"] == content_laps.KIND)
        for name, change in [
                ("code", lambda p, c: c.__setitem__("location", c["location"] + 1)),
                ("award", lambda p, c: c["routes"][0].__setitem__("award", "win")),
                ("name", lambda p, c: c.__setitem__("display_name", "Lap")),
                ("feature", lambda p, c: p["required_features"].remove(content_laps.FEATURE)),
                ("dropped", lambda p, c: p["checks"].remove(c))]:
            forged = copy.deepcopy(plan)
            check = next(c for c in forged["checks"] if c["location"] == lap["location"])
            change(forged, check)
            with self.subTest(name), self.assertRaises(OptionError):
                content_plan.validate(forged)

    def test_tracker_restores_the_switch_from_the_plan(self):
        world = make_world(lap_plan_options())
        wire = convert_to_base_types(world.fill_slot_data())
        self.assertNotIn("lap_completion_checks", wire["ctr_options"])
        tracker = make_world({}, seed=5, passthrough=wire)
        self.assertTrue(tracker.options.lap_completion_checks.value)
        self.assertEqual({l.address for l in tracker.multiworld.get_locations(1)},
                         {l.address for l in world.multiworld.get_locations(1)})

    def test_lap_rule_needs_the_finish_rank_not_a_win(self):
        options = lap_plan_options(progressive_boost="shared_global")
        options["content_pool"]["required_entries"] = ["retail:10", "custom/baby-t-park/1.0.2"]
        world = make_world(options)
        plan = world.ctr_content_plan
        hot_air = next(c for c in plan["checks"] if c["kind"] == content_laps.KIND and c["owner"] == "retail:10")
        location = world.multiworld.get_location(content_plan.LOCATION_BY_CODE[hot_air["location"]], 1)
        state = CollectionState(world.multiworld)
        for item in world.multiworld.itempool:
            if not item.name.startswith("Progressive Boost"):
                state.collect(item, True)
        self.assertFalse(location.can_reach(state))
        for _ in range(2):
            state.collect(world.create_item(boost_item_name()), True)
        self.assertTrue(location.can_reach(state))


if __name__ == "__main__":
    unittest.main()
