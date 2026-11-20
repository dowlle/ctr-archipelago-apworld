import copy
import unittest
from unittest.mock import patch

from Options import OptionError

from .. import content_item_boxes, content_plan, crate_exclusions, notices, track_rulings
from .test_content_item_boxes import box_options, btp, first_world
from .test_content_plan import make_world
from .test_country_speedway import country_options
from .test_crate_exclusions import lockbox_track_4, matsuri
from .test_green_hill_raceway import PACKAGE as GREEN_HILL, green_options
from .test_royal_raceway import PACKAGE as ROYAL, royal_options
from .test_toasty_terrace import toasty_options


def later_revision(options, pin):
    package = options["content_pool"]["tracks"]["custom"][0]
    key = package["content_id"]
    package.update(id=f"package/{key}/9.0.0", revision="9.0.0")
    old_pin = package["files"][0]["sha256"]
    package["files"][0]["sha256"] = pin
    for evidence in package.get("evidence", ()):
        evidence["file_hashes"] = [pin if digest == old_pin else digest
                                   for digest in evidence["file_hashes"]]
    track = f"custom/{key}/9.0.0"
    options["content_pool"]["required_entries"] = [track]
    return track, package


def sunset_mixed_options(revision="1.2.0", pin=None):
    options = royal_options(item_box_count=0, itemboxsanity=0, wumpasanity="off")
    later_revision(options, "ab" * 32)
    sunset = btp(25)
    sunset.update(id=f"package/sunset-vista/{revision}", revision=revision, content_id="sunset-vista",
                  display_name="Sunset Vista", uuid="11111111-2222-4333-8444-555555555588")
    old_pin = sunset["files"][0]["sha256"]
    new_pin = pin or track_rulings.REVIEWS["sunset-vista"][0][0]
    sunset["files"][0]["sha256"] = new_pin
    for evidence in sunset.get("evidence", ()):
        evidence["file_hashes"] = [new_pin if digest == old_pin else digest
                                   for digest in evidence["file_hashes"]]
    sunset["capabilities"]["super_turbo_pads"] = True
    options["content_pool"]["tracks"]["custom"].append(sunset)
    options["content_pool"]["required_entries"].append(f"custom/sunset-vista/{revision}")
    return options


class TestCarriedPickupLimits(unittest.TestCase):
    def test_added_pickups_have_no_check_or_seat_and_are_in_the_slot_summary(self):
        for options_factory in (country_options, toasty_options, royal_options, green_options):
            options = options_factory(item_box_count=5, wumpasanity="both")
            track_id, package = later_revision(options, "ab" * 32)
            caps = package["capabilities"]
            weapon, wumpa = caps["weapon_crates"], caps["fruit_crates"]
            caps.update(weapon_crates=weapon + 12, fruit_crates=wumpa + 3, loose_fruit=2)
            with self.subTest(track=track_id), self.assertLogs("CTR", "WARNING") as log:
                world = make_world(options, seed=3, stop_before="pre_fill")
                wire = world.fill_slot_data()
                plan = wire["content_plan"]
                self.assertIs(plan["track_ruling_sources"]["pickup_limits"], True)
                row = next(row for row in plan["sanity"]["tracks"] if row["track_id"] == track_id)
                self.assertEqual(row["counts"], [weapon + 12, wumpa + 3, 2])
                self.assertEqual(row["wumpa_crate"], list(range(1, wumpa + 1)))
                self.assertEqual(row["wumpa_fruit"], [])
                seats = [i + 1 for i in content_item_boxes.seat_indices(weapon, 5)]
                self.assertEqual(row["weapon_crate"], sorted(set(range(1, weapon + 1)) - set(seats)))
                self.assertTrue(content_plan.validate(plan))
                self.assertEqual(make_world({}, passthrough=wire, stop_before="pre_fill").ctr_content_plan, plan)
                summary = [line for line in notices.summary_lines(world) if "awaiting review" in line]
                self.assertEqual(len(summary), 1)
                for text in (f"Weapon Crate {weapon + 1}-{weapon + 12}", f"Wumpa Crate {wumpa + 1}-{wumpa + 3}",
                             "Wumpa Fruit 1-2"):
                    self.assertIn(text, summary[0])
                self.assertEqual(sum(summary[0] in line for line in log.output), 1)
                tampered = copy.deepcopy(plan)
                next(row for row in tampered["sanity"]["tracks"] if row["track_id"] == track_id
                     )["weapon_crate"][-1] = weapon + 1
                with self.assertRaises(OptionError):
                    content_plan.validate(tampered)

    def test_foreign_reviewed_lev_does_not_hide_royal_inheritance(self):
        pin = GREEN_HILL["files"][0]["sha256"]
        options = royal_options()
        track_id, package = later_revision(options, pin)
        package["capabilities"].update(weapon_crates=29, fruit_crates=7)
        world = make_world(options, seed=3, stop_before="pre_fill")
        plan = world.ctr_content_plan
        self.assertIn(track_id, plan["capability"]["finish_floors"])
        row = next(row for row in plan["sanity"]["tracks"] if row["track_id"] == track_id)
        self.assertEqual(row["lev_sha256"], pin)
        self.assertEqual(row["wumpa_crate"], list(range(1, 7)))
        self.assertIn((package["id"], "ordinary pickups", "1.0.0",
                       ROYAL["files"][0]["sha256"]),
                      track_rulings.spoiler_sources(plan))

    def test_disabled_pickup_options_still_report_added_ordinals_without_a_wire_marker(self):
        options = royal_options(item_box_count=0, itemboxsanity=0, wumpasanity="off", progressive_boost="off")
        _, package = later_revision(options, "ab" * 32)
        package["capabilities"].update(weapon_crates=29)
        with self.assertLogs("CTR", "WARNING") as log:
            plan = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertNotIn("track_ruling_sources", plan)
        self.assertEqual(sum("Weapon Crate 29" in line for line in log.output), 1)

    def test_a6_15_exclusions_and_counts_carry_to_new_revisions(self):
        for fixture, reviewed in ((matsuri, 27), (lockbox_track_4, 29)):
            options = box_options(custom=[fixture()], itemboxsanity=50, wumpasanity="both", item_box_count=5)
            tid, package = later_revision(options, "ab" * 32)
            package["capabilities"].update(weapon_crates=reviewed + 1, fruit_crates=3, loose_fruit=0)
            wire = first_world(options, seed=3).fill_slot_data()
            plan = wire["content_plan"]
            source = plan["track_ruling_sources"]
            self.assertEqual(source["version"], track_rulings.RULING_VERSION)
            self.assertIs(source["pickup_limits"], True)
            exclusion, = plan["item_boxes"][crate_exclusions.KEY]
            self.assertEqual(exclusion, dict(track_id=tid, lev_sha256="ab" * 32,
                                             crates=[dict(ordinal=1, pos=None)]))
            rows = [r for r in plan["sanity"]["tracks"] if r["track_id"] == tid]
            if fixture is matsuri:
                row, = rows
                self.assertNotIn(1, row["weapon_crate"])
                self.assertNotIn(reviewed + 1, row["weapon_crate"])
            else:
                self.assertFalse(rows)
            self.assertEqual(make_world({}, passthrough=wire).fill_slot_data(), wire)

    def test_foreign_pin_does_not_demand_its_exact_exclusion_in_a_version_two_room(self):
        nina = lockbox_track_4()
        nina.update(id="package/nina-s-nightmare/9.0.0", revision="9.0.0", content_id="nina-s-nightmare",
                    display_name="Nina's Nightmare")
        options = box_options(custom=[nina, matsuri()], itemboxsanity=50, progressive_boost="off")
        wire = first_world(options, seed=3).fill_slot_data()
        plan = wire["content_plan"]
        history = plan["track_ruling_sources"]
        self.assertEqual(history["version"], track_rulings.RULING_VERSION)
        self.assertNotIn("pickup_limits", history)
        self.assertEqual(plan["sanity"]["exclusion_version"], 2)
        self.assertEqual([r["track_id"] for r in plan["item_boxes"][crate_exclusions.KEY]],
                         ["custom/matsuri/1.0.0"])
        self.assertEqual(make_world({}, passthrough=wire).fill_slot_data(), wire)
        disabled = first_world(dict(options, box_locations=False, item_box_count=0, itemboxsanity=0),
                               seed=3).ctr_content_plan
        self.assertNotIn("track_ruling_sources", disabled)

    def test_sunset_vista_finish_ruling_survives_the_shared_history(self):
        for revision, pin in (("1.2.0", None), ("9.0.0", "cd" * 32)):
            options = sunset_mixed_options(revision, pin)
            wire = make_world(options, seed=3, stop_before="pre_fill").fill_slot_data()
            plan = wire["content_plan"]
            tid = f"custom/sunset-vista/{revision}"
            lap = next(c for c in plan["checks"] if c["owner"] == tid and c["kind"] == "lap")
            self.assertEqual(lap.get("boost", 0), 0)
            self.assertEqual(plan["track_ruling_sources"]["version"], track_rulings.RULING_VERSION)
            if pin:
                self.assertIn((f"package/sunset-vista/{revision}", "finish", "1.2.0",
                               track_rulings.REVIEWS["sunset-vista"][0][0]), track_rulings.spoiler_sources(plan))
            self.assertEqual(make_world({}, passthrough=wire, stop_before="pre_fill").fill_slot_data(), wire)

    def test_rooms_without_pickup_limits_keep_their_previous_pool(self):
        options = royal_options()
        track_id, package = later_revision(options, "ab" * 32)
        package["capabilities"].update(weapon_crates=40, fruit_crates=10)
        with patch.object(track_rulings, "pickup_limits_enabled", return_value=False):
            legacy = make_world(options, seed=3, stop_before="pre_fill").fill_slot_data()
        row = next(row for row in legacy["content_plan"]["sanity"]["tracks"] if row["track_id"] == track_id)
        self.assertEqual(row["wumpa_crate"][-1], 10)
        self.assertEqual(make_world({}, passthrough=legacy, stop_before="pre_fill").fill_slot_data(), legacy)
