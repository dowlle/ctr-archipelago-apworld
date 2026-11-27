"""IM1: dowlle's reviewed Box Author Mode placements for the Sunday tracks.

One spot file per track, pinned to the exact Sunday LEV. Item Box n is the
track's n-th row of the reviewed export in file order (Arabian Heights Day from
28, after its 27 retired weapon crate rows). Rows that failed the pickup reach
or clearance check are held: their number stays free. Every spot is Boost 0
except Royal Raceway 38 (plain Boost 2) and Snowy Valley 30 (Boost 1).
"""
import copy
import hashlib
import json
import pkgutil
import unittest
from unittest import mock

from .. import box_spots, content_item_boxes, destinations, named_tracks
from ..Locations import CTR_LOCATION_IDS
from .test_box_spots import spot_set
from .test_content_item_boxes import box_options, boxes, btp, first_world
from .test_content_plan import make_world

SOURCE_SHA256 = "3770cfdf6b77d9d39a23f203cc932dfc4b5fbd095536be46c83a3f52a382b90e"
#: track key -> (named block, Sunday LEV, file rows, first number, held numbers, non-zero ranks)
IM1 = {
    "royal-raceway": (59, "fca9e96a57c850e68e0226382645b4d6df5b4e7ebeb61459269ec2427ffab96b", 42, 1, {33}, {38: "usf"}),
    "tv-world": (None, "e3d765e824a2de96d06d1f34951b6d2ab51c027fb3353c62d8e7086b8ce1e33a", 34, 1, set(), {}),
    "super-snocross-2": (None, "db6f51a7857983771eba923883daafd696eaf0224a2d833528361f187a6d7115", 42, 1, {27, 41}, {}),
    "arabian-heights-night": (None, "8093b663855d3fd0096fd2980a85bc6efe334c0aff250e8a33eea11909e5c21c", 23, 1, set(), {}),
    "arabian-heights-day": (3, "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900", 23, 28, set(), {}),
    "yoshi-circuit": (None, "5728e57919f873d84c84e8372db4b44bc104c9d7472e89be127def6012293ecf", 30, 1, set(), {}),
    "snowy-valley": (None, "add8c2b43aaaadbac84d05d8eb819bbda81670d02baef2a04a4d82157f87cfc4", 34, 1, {29}, {30: "boost"}),
    "sid-house": (61, "985663bf855f45fd8b71fe23ada322effb738c5fcf55cbd6c2710f95c631b112", 20, 1, set(), {}),
    "redrock-ravine": (None, "860d5d340207cdf3ab564cddb8fdad5cc5d171db382b0a74ae15761d9687a3d3", 20, 1, set(), {}),
    "sunken-sprint": (None, "286d6574d87e158d78cc89986f16b8b51e5b94f1b153574ea9358582e32c6ba1", 25, 1, set(), {}),
}
RULED = {("royal-raceway", 38): [-2564, -23, -2166], ("snowy-valley", 30): [-11227, 368, -5156]}


def package_for(key, digest=None, crates=17):
    package = btp(crates)
    old = package["files"][0]["sha256"]
    name = box_spots.CUSTOM_FILES[key]["doc"]["track"]["name"]
    block = destinations.named_track(key).block_index
    package.update(content_id=key, display_name=name, id=f"package/{key}/1.0.0", revision="1.0.0",
                   uuid=f"11111111-2222-4333-8444-{block:012d}")
    package["files"][0]["sha256"] = digest or IM1[key][1]
    for evidence in package.get("evidence", []):
        evidence["file_hashes"] = [package["files"][0]["sha256"] if h == old else h for h in evidence["file_hashes"]]
    return package


class TestIm1Files(unittest.TestCase):
    def test_counts_pins_numbers_and_ranks(self):
        for key, (block, pin, rows, first, held, ranks) in IM1.items():
            with self.subTest(key=key):
                entry = box_spots.CUSTOM_FILES[key]
                doc = entry["doc"]
                self.assertEqual(doc["track"]["lev_sha256"], [pin])
                if block is not None:
                    self.assertEqual(destinations.named_track(key).block_index, block)
                numbers = [n for n in range(first, first + rows) if n not in held]
                self.assertEqual([s["number"] for s in doc["spots"]], numbers)
                self.assertEqual({s["number"]: s["needs"] for s in doc["spots"] if s["needs"] != "none"}, ranks)
                self.assertTrue(all(s["source_family"] == "ap_box" and s["provenance"][0] == f"im1-{key}"
                                    for s in doc["spots"]))
                self.assertEqual(doc["retired"], list(range(1, 28)) if key == "arabian-heights-day" else [])
                source = box_spots.SOURCE_RECORDS[f"im1-{key}"]
                self.assertEqual((source["sha256"], source["pins"], source["kind"]),
                                 (SOURCE_SHA256, [pin], "box_author_export"))
                # The export rows of one track are consecutive in file order.
                ordinals = [s["provenance"][1] for s in doc["spots"]]
                self.assertEqual(ordinals, sorted(ordinals))
                name = doc["track"]["name"]
                for spot in doc["spots"]:
                    self.assertEqual(CTR_LOCATION_IDS[f"{name}: Item Box {spot['number']}"],
                                     named_tracks.location_code(destinations.named_track(key).block_index,
                                                                f"item_box_{spot['number']}"))

    def test_ruled_positions(self):
        for (key, number), pos in RULED.items():
            spot = box_spots.spots_by_number(box_spots.CUSTOM_FILES[key])[number]
            self.assertEqual(spot["pos"], pos)

    def test_country_speedway_stays_on_its_relic_pin(self):
        doc = box_spots.CUSTOM_FILES["country-speedway"]["doc"]
        self.assertEqual(doc["track"]["lev_sha256"],
                         ["504946fdd87d040cce6dfadcf158759b53962d2a08b41002ad97949051b3d996"])
        self.assertEqual(len(doc["spots"]), 49)

    def test_night_and_day_share_positions(self):
        night = box_spots.CUSTOM_FILES["arabian-heights-night"]["doc"]["spots"]
        day = box_spots.CUSTOM_FILES["arabian-heights-day"]["doc"]["spots"]
        self.assertEqual([(s["pos"], s["rot_y"]) for s in day], [(s["pos"], s["rot_y"]) for s in night])
        self.assertEqual([s["number"] - 27 for s in day], [s["number"] for s in night])


class TestIm1Generation(unittest.TestCase):
    def test_ranks_reach_the_wire_with_progressive_boost(self):
        packages = [package_for("royal-raceway"), package_for("snowy-valley")]
        plan = first_world(box_options(custom=packages, item_box_count=50, progressive_boost="shared_global",
                                       logic_difficulty="hard")).ctr_content_plan
        for key, number, rank in (("royal-raceway", 38, 2), ("snowy-valley", 30, 1)):
            tid = f"custom/{key}/1.0.0"
            own = boxes(plan, tid)
            self.assertEqual(spot_set(plan, tid)["picked"], [s["number"] for s in box_spots.CUSTOM_FILES[key]["doc"]["spots"]])
            self.assertEqual({c["spot"]["number"]: c["boost"] for c in own if c.get("boost")}, {number: rank})
        off = first_world(box_options(custom=packages, item_box_count=50)).ctr_content_plan
        self.assertFalse([c for k in ("royal-raceway", "snowy-valley") for c in boxes(off, f"custom/{k}/1.0.0")
                          if c.get("boost")])

    def test_other_revisions_keep_crate_seating(self):
        for key in IM1:
            with self.subTest(key=key):
                plan = first_world(box_options(custom=[package_for(key, "01" * 32)])).ctr_content_plan
                tid = f"custom/{key}/1.0.0"
                self.assertIsNone(spot_set(plan, tid))
                self.assertTrue(all("spot" not in c for c in boxes(plan, tid)))

    def test_room_from_before_the_files_restores(self):
        """A room generated before IM1 keeps its crate seats (Arabian Heights
        Day: its old weapon crate rows) and restores unchanged."""
        main_day = json.loads(pkgutil.get_data("worlds.ctr", "test/fixtures/im1_day_before.json"))
        packages = [package_for(key, crates=0 if key == "arabian-heights-day" else 17) for key in IM1]
        old_files = {k: v for k, v in box_spots.CUSTOM_FILES.items() if k not in IM1}
        raw = json.dumps(main_day, indent=2).encode()
        old_files["arabian-heights-day"] = dict(doc=main_day, path="data/box_spots/custom/arabian-heights-day.json",
                                                sha256=hashlib.sha256(raw).hexdigest())
        with mock.patch.dict(box_spots.CUSTOM_FILES, old_files, clear=True):
            wire = json.loads(json.dumps(first_world(box_options(custom=packages, item_box_count=20)).fill_slot_data()))
        sets = {s["track_id"]: s for s in wire["content_plan"]["item_boxes"]["spot_sets"]}
        day = sets["custom/arabian-heights-day/1.0.0"]
        self.assertEqual((day["pool"], len(day["picked"])), (27, 20))
        self.assertLessEqual(set(day["picked"]), set(range(1, 28)))
        self.assertFalse(set(sets) & {f"custom/{k}/1.0.0" for k in IM1 if k != "arabian-heights-day"})
        restored = make_world({}, seed=999, passthrough=copy.deepcopy(wire))
        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)


if __name__ == "__main__":
    unittest.main()
