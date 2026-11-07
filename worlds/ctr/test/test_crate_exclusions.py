"""Reviewed exclusions change fallback counts, never spot pools or logic."""
import copy
import json
import unittest
from unittest.mock import patch

from Options import OptionError
from .. import crate_exclusions, content_item_boxes, content_plan, box_spots
from .test_content_item_boxes import btp, box_options, first_world, boxes
from .test_content_plan import make_world


def ancient(crates=17, digest=None):
    p = btp(crates)
    old_hash = p["files"][0]["sha256"]
    p.update(content_id="ancient-lake", display_name="Ancient Lake", id="package/ancient-lake/1.1.0", revision="1.1.0")
    p["files"][0]["sha256"] = digest or next(iter(crate_exclusions.EXCLUSIONS))
    for evidence in p.get("evidence", []):
        evidence["file_hashes"] = [p["files"][0]["sha256"] if h == old_hash else h for h in evidence["file_hashes"]]
    return p


class TestCrateExclusions(unittest.TestCase):
    def test_exact_revision_counts_and_generation(self):
        for digest in crate_exclusions.EXCLUSIONS:
            p = ancient(digest=digest)
            self.assertEqual(content_item_boxes.crate_count(p), 17)
            world = first_world(box_options(custom=[p]))
            plan = world.ctr_content_plan
            self.assertIn(crate_exclusions.FEATURE, plan["required_features"])
            row, = plan["item_boxes"][crate_exclusions.KEY]
            self.assertEqual(content_item_boxes.crate_count(p, plan["item_boxes"], row["track_id"]), 16)
            self.assertEqual(row["lev_sha256"], digest)
            self.assertEqual(row["crates"], [{"ordinal": 1, "pos": [0, 0, 0]}])
            self.assertEqual(len(boxes(plan, row["track_id"])), 15)
            self.assertTrue(content_plan.validate(plan))
            # The count crosses the 15-seat ceiling only with a smaller fixture.
            small = first_world(box_options(custom=[ancient(3, digest)]))
            track_id = small.ctr_content_plan["item_boxes"][crate_exclusions.KEY][0]["track_id"]
            self.assertEqual(len(boxes(small.ctr_content_plan, track_id)), 2)

    def test_tracker_restores_legacy_and_current_seating(self):
        for digest in list(crate_exclusions.EXCLUSIONS):
            for count in (3, 17):
                p = ancient(count, digest)
                # Generate the historical wire with no catalog, rather than
                # merely stripping the field from a seed with fewer checks.
                with patch.dict(crate_exclusions.EXCLUSIONS, {}, clear=True):
                    legacy = first_world(box_options(custom=[p]))
                    wire = json.loads(json.dumps(legacy.fill_slot_data()))
                self.assertNotIn(crate_exclusions.KEY, wire["content_plan"]["item_boxes"])
                self.assertNotIn(crate_exclusions.FEATURE, wire["content_plan"]["required_features"])
                restored = make_world({}, seed=999, passthrough=wire)
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
                track_id = next(t["id"] for t in wire["content_plan"]["tracks"] if t["origin"] == "custom")
                self.assertEqual(len(boxes(restored.ctr_content_plan, track_id)), min(count, 15))
                current = first_world(box_options(custom=[p]))
                current_wire = json.loads(json.dumps(current.fill_slot_data()))
                current_restored = make_world({}, seed=999, passthrough=current_wire)
                self.assertEqual(json.loads(json.dumps(current_restored.fill_slot_data())), current_wire)
                self.assertEqual(len(boxes(current_restored.ctr_content_plan, track_id)), min(count - 1, 15))

    def test_unknown_revision_and_north_pole_are_unchanged(self):
        for digest in ("01" * 32, "17eafea488" + "0" * 54):
            p = ancient(3, digest)
            self.assertEqual(content_item_boxes.crate_count(p), 3)
            plan = first_world(box_options(custom=[p])).ctr_content_plan
            self.assertNotIn(crate_exclusions.KEY, plan["item_boxes"])
            self.assertNotIn(crate_exclusions.FEATURE, plan["required_features"])

    def test_forged_list_refused(self):
        plan = first_world(box_options(custom=[ancient()])).ctr_content_plan
        for field, value in (("ordinal", 2), ("pos", [1, 0, 0])):
            bad = copy.deepcopy(plan)
            bad["item_boxes"][crate_exclusions.KEY][0]["crates"][0][field] = value
            with self.assertRaises(OptionError):
                content_plan.validate(bad)

    def test_authored_spots_are_exempt(self):
        p = ancient()
        track = dict(id="track/ancient", origin="custom", named_block=1, package_id=p["id"])
        with patch.object(box_spots, "spot_set", return_value={"picked": [1], "pool": 1}):
            record = content_item_boxes.add_spot_sets(dict(shortcut_knowledge=2), [track], {p["id"]: p}, 1, 1)
        self.assertNotIn(crate_exclusions.KEY, record)

    def test_box_terms_unchanged(self):
        p = ancient()
        world = first_world(box_options(custom=[p], progressive_boost="shared_global", progressive_stats="shared_global"))
        plan = world.ctr_content_plan
        track_id = plan["item_boxes"][crate_exclusions.KEY][0]["track_id"]
        track = next(t for t in plan["tracks"] if t["id"] == track_id)
        other = copy.deepcopy(p)
        other["files"][0]["sha256"] = "01" * 32
        for n in range(1, 16):
            self.assertEqual(content_item_boxes.box_terms(track, n, plan["capability"], p),
                             content_item_boxes.box_terms(track, n, plan["capability"], other))
