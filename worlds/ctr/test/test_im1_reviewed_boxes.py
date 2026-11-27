"""IM1: dowlle's reviewed Box Author Mode placements for the Sunday tracks.

One spot file per track, pinned to the exact Sunday LEV. Item Box n is the
track's n-th row of the reviewed export in file order (Arabian Heights Day from
28, after its 27 retired weapon crate rows). Rows that failed the pickup reach
or clearance check are held: their number stays free. Every spot is Boost 0
except Royal Raceway 38 (plain Boost 2) and Snowy Valley 29 and 30 (Boost 1).
IM1b (dowlle's answers of 2026-11-27) added Royal Raceway 33, Super Snocross 2
41 and Snowy Valley 29, near Relic Race time crates, and TV World 35 and 36 on
the upper ledge (their own source, the Wumpa crate ruling; test_im1b_answers.py).
"""
import copy
import gzip
import json
import pkgutil
import unittest
from unittest import mock

from Options import OptionError
from .. import box_spots, content_plan, destinations, named_tracks, track_rulings
from ..Locations import CTR_LOCATION_IDS
from .test_box_spots import spot_set
from .test_content_item_boxes import box_options, boxes, btp, country_speedway_before_im1b, first_world
from .test_content_plan import make_world

SOURCE_SHA256 = "3770cfdf6b77d9d39a23f203cc932dfc4b5fbd095536be46c83a3f52a382b90e"
#: track key -> (named block, Sunday LEV, file rows, first number, held numbers, non-zero ranks)
IM1 = {
    "royal-raceway": (59, "fca9e96a57c850e68e0226382645b4d6df5b4e7ebeb61459269ec2427ffab96b", 42, 1, set(), {38: "usf"}),
    "tv-world": (None, "e3d765e824a2de96d06d1f34951b6d2ab51c027fb3353c62d8e7086b8ce1e33a", 34, 1, set(),
                 {35: "blue_fire", 36: "blue_fire"}),
    "super-snocross-2": (None, "db6f51a7857983771eba923883daafd696eaf0224a2d833528361f187a6d7115", 42, 1, {27}, {}),
    "arabian-heights-night": (None, "8093b663855d3fd0096fd2980a85bc6efe334c0aff250e8a33eea11909e5c21c", 23, 1, set(), {}),
    "arabian-heights-day": (3, "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900", 23, 28, set(), {}),
    "yoshi-circuit": (None, "5728e57919f873d84c84e8372db4b44bc104c9d7472e89be127def6012293ecf", 30, 1, set(), {}),
    "snowy-valley": (None, "add8c2b43aaaadbac84d05d8eb819bbda81670d02baef2a04a4d82157f87cfc4", 34, 1, set(),
                     {29: "boost", 30: "boost"}),
    "sid-house": (61, "985663bf855f45fd8b71fe23ada322effb738c5fcf55cbd6c2710f95c631b112", 20, 1, set(), {}),
    "redrock-ravine": (None, "860d5d340207cdf3ab564cddb8fdad5cc5d171db382b0a74ae15761d9687a3d3", 20, 1, set(), {}),
    "sunken-sprint": (None, "286d6574d87e158d78cc89986f16b8b51e5b94f1b153574ea9358582e32c6ba1", 25, 1, set(), {}),
}
RULED = {("royal-raceway", 38): [-2564, -23, -2166], ("snowy-valley", 30): [-11227, 368, -5156],
         ("snowy-valley", 29): [-10977, 410, -7379]}
#: IM1b: the TV World ledge boxes after the 34 export rows (TV2 source).
LEDGE = {"tv-world": [35, 36]}


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
                numbers = [n for n in range(first, first + rows) if n not in held] + LEDGE.get(key, [])
                self.assertEqual([s["number"] for s in doc["spots"]], numbers)
                self.assertEqual({s["number"]: s["needs"] for s in doc["spots"] if s["needs"] != "none"}, ranks)
                self.assertTrue(all(s["source_family"] == "ap_box" and s["provenance"][0]
                                    == ("tv2-tv-world-ledge" if s["number"] in LEDGE.get(key, ()) else f"im1-{key}")
                                    for s in doc["spots"]))
                self.assertEqual(doc["retired"], list(range(1, 28)) if key == "arabian-heights-day" else [])
                source = box_spots.SOURCE_RECORDS[f"im1-{key}"]
                self.assertEqual((source["sha256"], source["pins"], source["kind"]),
                                 (SOURCE_SHA256, [pin], "box_author_export"))
                # The export rows of one track are consecutive in file order.
                ordinals = [s["provenance"][1] for s in doc["spots"] if s["number"] not in LEDGE.get(key, ())]
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

    def test_country_speedway_covers_the_merged_pair(self):
        """IM1b: one file for the 1.3.1 Relic file and the 1.3.0 race file."""
        doc = box_spots.CUSTOM_FILES["country-speedway"]["doc"]
        self.assertEqual(doc["track"]["lev_sha256"],
                         ["504946fdd87d040cce6dfadcf158759b53962d2a08b41002ad97949051b3d996",
                          "9fa73436daaf91434ede1d6fb036a8e6dff225c55533cc0be5723d229b5e53bd"])
        self.assertEqual((len(doc["spots"]), doc["retired"]), (48, [11]))

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
        for key, ranks in (("royal-raceway", {38: 2}), ("snowy-valley", {29: 1, 30: 1})):
            tid = f"custom/{key}/1.0.0"
            own = boxes(plan, tid)
            self.assertEqual(spot_set(plan, tid)["picked"], [s["number"] for s in box_spots.CUSTOM_FILES[key]["doc"]["spots"]])
            self.assertEqual({c["spot"]["number"]: c["boost"] for c in own if c.get("boost")}, ranks)
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

    def old_catalog(self):
        """The catalog as it was before IM1: no new files, Day's alpha6 rows,
        Country Speedway's 1.3.1 file (IM1b) and no Jungle Boogie file."""
        legacy = next(v for v in box_spots.LEGACY_FILES.values() if v["path"].endswith("/arabian-heights-day-a6-16.json"))
        files = {k: v for k, v in box_spots.CUSTOM_FILES.items() if k not in IM1 and k != "jungle-boogie-n-gage"}
        files["arabian-heights-day"] = legacy
        files["country-speedway"] = country_speedway_before_im1b()
        return legacy, mock.patch.dict(box_spots.CUSTOM_FILES, files, clear=True)

    def test_room_from_before_the_files_restores(self):
        """A room generated before IM1 keeps its crate seats (Arabian Heights
        Day: its old weapon crate rows, here with their Boost 2 terms under the
        ruling version of that time) and restores unchanged, with and without
        the room_compatibility stamp (main produced unstamped Day rooms between
        2026-11-19 and 2026-11-20)."""
        legacy, old = self.old_catalog()
        packages = [package_for(key, crates=0 if key == "arabian-heights-day" else 17) for key in IM1]
        for package in packages:
            package["capabilities"]["super_turbo_pads"] = True
        options = box_options(custom=packages, item_box_count=20, progressive_boost="shared_global",
                              logic_difficulty="hard")
        with old, mock.patch.object(track_rulings, "RULING_VERSION", 4):
            wire = json.loads(json.dumps(first_world(options).fill_slot_data()))
        sets = {s["track_id"]: s for s in wire["content_plan"]["item_boxes"]["spot_sets"]}
        day = sets["custom/arabian-heights-day/1.0.0"]
        self.assertEqual((day["file_sha256"], day["pool"], len(day["picked"])), (legacy["sha256"], 27, 20))
        self.assertLessEqual(set(day["picked"]), set(range(1, 28)))
        self.assertTrue(any(c.get("boost") == 2 for c in boxes(wire["content_plan"], "custom/arabian-heights-day/1.0.0")))
        self.assertFalse(set(sets) & {f"custom/{k}/1.0.0" for k in IM1 if k != "arabian-heights-day"})
        unstamped = copy.deepcopy(wire)
        del unstamped["content_plan"]["room_compatibility"]
        for room in (wire, unstamped):
            restored = make_world({}, seed=999, passthrough=copy.deepcopy(room))
            self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), room)

    def test_unstamped_day_room_from_main_of_2026_11_20_restores(self):
        """A Day room generated at apworld main adb2ea01d (2026-11-20): no
        room_compatibility stamp, spot set naming the file's first digest,
        Boost 2 on its boxes. It restores unchanged."""
        raw = pkgutil.get_data("worlds.ctr", "test/fixtures/im1_day_room_adb2ea01d.json.gz")
        wire = json.loads(gzip.decompress(raw))
        self.assertNotIn("room_compatibility", wire["content_plan"])
        (day,) = [s for s in wire["content_plan"]["item_boxes"]["spot_sets"]
                  if s["track_id"] == "custom/arabian-heights-day/1.0.0"]
        self.assertEqual(day["file_sha256"][:8], "51f6d6d1")
        self.assertTrue(any(c.get("boost") == 2 for c in boxes(wire["content_plan"], day["track_id"])))
        restored = make_world({}, seed=999, passthrough=copy.deepcopy(wire))
        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data(), sort_keys=True)), wire)

    def test_restore_only_file_never_serves_a_new_room(self):
        legacy, old = self.old_catalog()
        package = package_for("arabian-heights-day", crates=0)
        world = first_world(box_options(custom=[package], item_box_count=20))
        current = box_spots.CUSTOM_FILES["arabian-heights-day"]
        self.assertEqual(spot_set(world.ctr_content_plan, "custom/arabian-heights-day/1.0.0")["file_sha256"],
                         current["sha256"])
        with old:
            stale = first_world(box_options(custom=[package], item_box_count=20)).ctr_content_plan
        with self.assertRaises(OptionError):
            content_plan.validate(stale)
        # Only an older file of the same track and pin is ever used.
        record = spot_set(stale, "custom/arabian-heights-day/1.0.0")
        track = next(t for t in stale["tracks"] if t["id"] == "custom/arabian-heights-day/1.0.0")
        self.assertIs(box_spots.file_for(track, package, record["file_sha256"]), legacy)
        self.assertIs(box_spots.file_for(track, package), current)
        self.assertIsNone(box_spots.file_for(track, package_for("arabian-heights-day", "01" * 32, 0),
                                             record["file_sha256"]))

if __name__ == "__main__":
    unittest.main()
