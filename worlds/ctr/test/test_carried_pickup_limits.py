import copy
import unittest
from unittest.mock import patch

from Options import OptionError

from .. import content_item_boxes, content_plan, notices, track_rulings
from .test_content_plan import make_world
from .test_country_speedway import country_options
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

    def test_rooms_without_pickup_limits_keep_their_previous_pool(self):
        options = royal_options()
        track_id, package = later_revision(options, "ab" * 32)
        package["capabilities"].update(weapon_crates=40, fruit_crates=10)
        with patch.object(track_rulings, "pickup_limits_enabled", return_value=False):
            legacy = make_world(options, seed=3, stop_before="pre_fill").fill_slot_data()
        row = next(row for row in legacy["content_plan"]["sanity"]["tracks"] if row["track_id"] == track_id)
        self.assertEqual(row["wumpa_crate"][-1], 10)
        self.assertEqual(make_world({}, passthrough=legacy, stop_before="pre_fill").fill_slot_data(), legacy)
