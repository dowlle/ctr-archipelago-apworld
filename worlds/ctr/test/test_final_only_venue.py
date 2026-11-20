"""A6-48 (rulings of 2026-11-20).

1. `oxide_goal: none` with `boss_garages` off is the `disabled` seed
   ("Treat as disabled when garages off").
2. A venue whose only allowed route is the Final Challenge gets no lap, Reach
   10 Wumpa or pickup checks of its own ("Build for alpha6"). The final's win
   and the venue's package stay; a check with another route keeps its Final
   Challenge route. Rooms made before the feature keep their checks.
"""
import copy
import json
from pathlib import Path
import unittest

from BaseClasses import ItemClassification
from Fill import distribute_items_restrictive
from Options import OptionError
from .. import content_bosses, content_plan as cp, content_pickups as pickups
from .test_content_item_pool import small_pool
from .test_content_plan import make_world, profile_options

VORTEX = "cortex_vortex"
OXIDE = "retail:13"
FIXTURE = Path(__file__).parent / "fixtures" / "final_only_legacy.json"


def options(**extra):
    return dict(dict(retail_tracks=["Dingo Canyon", "Tiny Arena", "Hot Air Skyway"], custom_tracks=[],
                     cortex_vortex_track="off", cup_count=0, crystal_challenge_count=0, boss_garages=True,
                     oxide_goal="101_percent", oxide_final_track="cortex_vortex", bosses_required_goal=0,
                     gems_required_goal=0, progressive_boost="off", progressive_stats="off",
                     character_unlocks=False, lap_completion_checks=True, itemboxsanity=2, wumpasanity="both",
                     wumpa_check="per_track", item_box_count=0, wumpa_shop_slots=0, podium_rungs=[],
                     accessibility="full"), **extra)


def pool():
    """A pool small enough for the rooms without pickup checks."""
    p = small_pool()
    p["base"]["gems"] = []
    return p


def owned(plan, track_id):
    return [c for c in plan["checks"] if c["owner"] == track_id]


def wire_digest(world):
    return json.dumps(world.fill_slot_data(), sort_keys=True, default=repr)


class TestGaragesOffNone(unittest.TestCase):
    def test_none_is_the_disabled_seed(self):
        for seed in (1, 420):
            with self.subTest(seed=seed):
                none = make_world(profile_options() | dict(oxide_goal="none"), seed=seed)
                disabled = make_world(profile_options(), seed=seed)
                self.assertEqual(none.options.oxide_goal.value, content_bosses.GOAL_DISABLED)
                self.assertEqual(none.ctr_content_plan, disabled.ctr_content_plan)
                self.assertEqual(wire_digest(none), wire_digest(disabled))
                self.assertEqual([i.name for i in none.multiworld.itempool],
                                 [i.name for i in disabled.multiworld.itempool])
                self.assertEqual(none.ctr_content_plan.get("bosses"), None)

    def test_none_without_another_goal_is_still_refused(self):
        with self.assertRaisesRegex(OptionError, "with boss_garages off"):
            make_world(profile_options() | dict(oxide_goal="none", gems_required_goal=0))

    def test_garages_on_none_is_unchanged(self):
        world = make_world(options(oxide_goal="none", gems_required_goal=3))
        self.assertEqual(world.options.oxide_goal.value, content_bosses.GOAL_NONE)
        self.assertEqual(world.ctr_content_plan["bosses"]["oxide_goal"], content_bosses.GOAL_NONE)
        codes = {c["location"] for c in world.ctr_content_plan["checks"]}
        self.assertLessEqual({content_bosses.OXIDE_FIRST, content_bosses.OXIDE_FINAL}, codes)


class TestFinalOnlyVenue(unittest.TestCase):
    def test_vortex_final_only_has_no_checks_of_its_own(self):
        for chaos in ("cortex_vortex", "vortex_chaos"):
            with self.subTest(final=chaos):
                world = make_world(options(oxide_final_track=chaos), seed=3)
                plan = world.ctr_content_plan
                self.assertTrue(pickups.final_enabled(plan))
                self.assertFalse(owned(plan, VORTEX))
                self.assertNotIn(VORTEX, {r["track_id"] for r in plan["sanity"]["tracks"]})
                # The venue's track record and package stay, and so does the final's win.
                self.assertIn(VORTEX, {t["id"] for t in plan["tracks"]})
                self.assertIn(content_bosses.OXIDE_FINAL, {c["location"] for c in plan["checks"]})
                self.assertTrue(any(e["id"] == pickups.FINAL for e in plan["encounters"]))
                # The First Challenge venue keeps its lap (A6-16c).
                self.assertTrue(any(c["kind"] == "lap" for c in owned(plan, OXIDE)))
                self.assertTrue(cp.validate(plan))
                self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))

    def test_oxide_station_final_keeps_lap_and_drops_pickups(self):
        world = make_world(options(oxide_final_track="oxide_station"), seed=3)
        plan = world.ctr_content_plan
        self.assertTrue(pickups.final_enabled(plan))
        checks = owned(plan, OXIDE)
        self.assertEqual([c["kind"] for c in checks], ["lap"])
        self.assertEqual({r["encounter_id"] for r in checks[0]["routes"]}, {pickups.FIRST, pickups.FINAL})
        self.assertTrue(cp.validate(plan))

    def test_a_check_with_another_route_stays_and_keeps_its_final_route(self):
        for final, track, extra in (("cortex_vortex", VORTEX, dict(cortex_vortex_track="own_pad")),
                                    ("oxide_station", OXIDE,
                                     dict(retail_tracks=options()["retail_tracks"] + ["Oxide Station"]))):
            with self.subTest(final=final):
                world = make_world(options(oxide_final_track=final, **extra), seed=3)
                plan = world.ctr_content_plan
                self.assertFalse(pickups.final_enabled(plan))
                checks = [c for c in owned(plan, track) if c["kind"] in pickups.KINDS + ("lap",)]
                self.assertTrue(checks)
                self.assertTrue(all(any(r["encounter_id"] == pickups.FINAL for r in c["routes"]) for c in checks))
                self.assertTrue(cp.validate(plan))

    def test_relic_only_pad_does_not_keep_pickups(self):
        # A Relic Race pad is a lap route but no pickup route (A6-16c).
        world = make_world(options(cortex_vortex_track="own_pad", item_pool=pool(), oxide_final_challenge_relic_count=0,
                                   track_modes={"default": ["trophy"], "Cortex Vortex": ["relic"]}), seed=3)
        plan = world.ctr_content_plan
        if not any(e.get("track_id") == VORTEX and e["modes"] == ["relic"] for e in plan["entries"]):
            self.skipTest("Cortex Vortex drew no relic-only pad")
        self.assertTrue(pickups.final_enabled(plan))
        kinds = {c["kind"] for c in owned(plan, VORTEX)}
        self.assertIn("lap", kinds)
        self.assertFalse(kinds & set(pickups.KINDS))
        self.assertTrue(cp.validate(plan))

    def test_laps_only_room_carries_the_feature(self):
        world = make_world(options(itemboxsanity=0, wumpasanity="off", wumpa_check="off", item_pool=pool(), oxide_final_challenge_relic_count=0),
                           seed=3)
        plan = world.ctr_content_plan
        self.assertTrue(pickups.final_enabled(plan))
        self.assertFalse(pickups.enabled(plan))
        self.assertFalse(owned(plan, VORTEX))
        self.assertTrue(cp.validate(plan))

    def test_nothing_to_leave_out_keeps_the_wire(self):
        plans = [make_world(options(lap_completion_checks=False, itemboxsanity=0, wumpasanity="off",
                                    wumpa_check="off", item_pool=pool(), oxide_final_challenge_relic_count=0), seed=3).ctr_content_plan,
                 make_world(profile_options() | dict(lap_completion_checks=True), seed=3).ctr_content_plan]
        for plan in plans:
            with self.subTest(features=plan["required_features"]):
                self.assertNotIn(pickups.FINAL_FEATURE, plan["required_features"])

    def test_excluded_omitted_checks_reserve_no_filler(self):
        opts = options(item_pool={"base": {"trophies": 15}})
        base = make_world(opts, seed=1).ctr_content_plan
        excluded = make_world(dict(opts, exclude_locations={"Cortex Vortex: Reach 10 Wumpa",
                                                            "Cortex Vortex: Complete One Lap"}), seed=1).ctr_content_plan
        self.assertFalse(owned(excluded, VORTEX))
        self.assertEqual(base["items"], excluded["items"])

    def test_full_accessibility_fill_and_tracker_restore(self):
        for final in ("cortex_vortex", "vortex_chaos", "oxide_station"):
            with self.subTest(final=final):
                world = make_world(options(oxide_final_track=final), seed=5)
                distribute_items_restrictive(world.multiworld)
                state = world.multiworld.get_all_state(False)
                self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations(1)))
                wire = world.fill_slot_data()
                restored = make_world(options(), seed=5, passthrough=wire)
                self.assertEqual(restored.ctr_content_plan, world.ctr_content_plan)
                self.assertEqual({l.address for l in restored.multiworld.get_locations(1)},
                                 {l.address for l in world.multiworld.get_locations(1)})

    def test_feature_without_oxide_races_is_refused(self):
        plan = copy.deepcopy(make_world(profile_options() | dict(lap_completion_checks=True), seed=3).ctr_content_plan)
        plan["required_features"].append(pickups.FINAL_FEATURE)
        with self.assertRaises(OptionError):
            cp.validate(plan)

    def test_removing_the_feature_is_refused(self):
        plan = copy.deepcopy(make_world(options(), seed=3).ctr_content_plan)
        plan["required_features"].remove(pickups.FINAL_FEATURE)
        with self.assertRaises(OptionError):
            cp.validate(plan)

    def test_pre_feature_room_keeps_its_final_only_checks(self):
        # Generated on main before A6-48 with options(), seed 3: Cortex Vortex
        # carries lap, Reach 10 Wumpa and pickup checks from the final alone.
        wire = json.loads(FIXTURE.read_text())
        world = make_world(options(), seed=3, passthrough=wire)
        plan = world.ctr_content_plan
        self.assertFalse(pickups.final_enabled(plan))
        checks = owned(plan, VORTEX)
        self.assertTrue(checks)
        self.assertTrue(all(r["encounter_id"] == pickups.FINAL for c in checks for r in c["routes"]))
        self.assertTrue({"lap", "wumpa"} <= {c["kind"] for c in checks})
        self.assertTrue(cp.validate(plan))
        self.assertEqual({l.address for l in world.multiworld.get_locations(1) if l.address},
                         {c["location"] for c in plan["checks"]})


if __name__ == "__main__":
    unittest.main()
