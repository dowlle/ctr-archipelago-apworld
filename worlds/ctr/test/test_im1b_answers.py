"""IM1b: dowlle's answers of 2026-11-27 on the reviewed AP box import.

1. Royal Raceway 33, Super Snocross 2 41 and Snowy Valley 29 (Boost 1) go in
   at their reserved numbers, though each sits 132 to 204 units from a Relic
   Race time crate. Super Snocross 2 27 stays held, its number free.
3. TV World 35 and 36 on the upper ledge carry Wumpa crate 3's ruling (TV2).
4. Jungle Boogie N-Gage gets its first file: only dowlle's own November 24
   stream rows (the CP1 baseline), floating rows 7 and 10 held.
5. Country Speedway is one track over the merged 1.3.1 Relic file and 1.3.0
   race file: one file pinned to both. Spot 11 floats out of reach and is
   retired. Spots 3 and 4 overlap a 1.3.0 pickup, so they exist only on 1.3.1.
   A merged package selects its spots by its 1.3.0 race LEV, so its Relic Race
   shows the 1.3.0 set too: 3 and 4 never show there.
"""
import copy
import json
import unittest
from unittest import mock

from Options import OptionError
from .. import box_spot_catalog, box_spots, content_item_boxes, content_plan, named_tracks, destinations
from ..Locations import CTR_LOCATION_IDS
from . import test_object_rulings as rulings
from .test_box_spots import spot_set
from .test_content_item_boxes import box_options, boxes, country_speedway_before_im1b, first_world
from .test_content_plan import make_world
from .test_im1_reviewed_boxes import IM1, package_for

CS131 = "504946fdd87d040cce6dfadcf158759b53962d2a08b41002ad97949051b3d996"
CS130 = "9fa73436daaf91434ede1d6fb036a8e6dff225c55533cc0be5723d229b5e53bd"
JB = "jungle-boogie-n-gage"
JB_PIN = "ac968f6ce814ecbe67a7efd6e926f4fa7c59803c56e8f05a194156962ec0f906"
JB_NUMBERS = [n for n in range(1, 31) if n not in (7, 10)]
#: (track, number) -> (position, needs, export row)
ADDED = {("royal-raceway", 33): ([-4675, -103, -16186], "none"),
         ("super-snocross-2", 41): ([14943, 5844, -3810], "none"),
         ("snowy-valley", 29): ([-10977, 410, -7379], "boost")}
LEDGE = {35: ([11500, 1774, -1836], 3072), 36: ([10870, 1774, -1180], 2048)}
COUNTRY_ALL = [n for n in range(1, 51) if n not in (6, 11)]
COUNTRY_130 = [n for n in COUNTRY_ALL if n not in (3, 4)]


def package(key, digest, crates=17):
    """A catalogue package of `key` on the LEV `digest`."""
    if key in IM1:
        return package_for(key, digest, crates)
    with mock.patch.dict(IM1, {key: (None, digest, 0, 1, set(), {})}):
        return package_for(key, digest, crates)


def main_catalog():
    """The custom files as on main before IM1 and IM1b."""
    day = next(v for v in box_spots.LEGACY_FILES.values() if v["path"].endswith("/arabian-heights-day-a6-16.json"))
    files = {k: v for k, v in box_spots.CUSTOM_FILES.items() if k not in IM1 and k != JB}
    files.update({"arabian-heights-day": day, "country-speedway": country_speedway_before_im1b()})
    return mock.patch.dict(box_spots.CUSTOM_FILES, files, clear=True)


def wire(world):
    return json.loads(json.dumps(world.fill_slot_data()))


class TestAnswerOneAddedBoxes(unittest.TestCase):
    def test_added_at_their_numbers_and_exact_positions(self):
        for (key, n), (pos, needs) in ADDED.items():
            with self.subTest(key=key, n=n):
                spot = box_spots.spots_by_number(box_spots.CUSTOM_FILES[key])[n]
                self.assertEqual((spot["pos"], spot["needs"], spot["provenance"][0]), (pos, needs, f"im1-{key}"))
                self.assertIn("time crate", spot["review"])
                source = box_spots.SOURCE_RECORDS[f"im1-{key}"]
                self.assertEqual(source["rows"][spot["provenance"][1]], [n, *pos, spot["rot_y"]])
        ss2 = box_spots.CUSTOM_FILES["super-snocross-2"]["doc"]
        self.assertNotIn(27, {s["number"] for s in ss2["spots"]} | set(ss2["retired"]))

    def test_ranks_on_the_wire(self):
        keys = ("royal-raceway", "super-snocross-2", "snowy-valley")
        packages = [package_for(k) for k in keys]
        plan = first_world(box_options(custom=packages, item_box_count=50, progressive_boost="shared_global",
                                       logic_difficulty="hard")).ctr_content_plan
        for (key, n), (_, needs) in ADDED.items():
            check = next(c for c in boxes(plan, f"custom/{key}/1.0.0") if c["spot"]["number"] == n)
            self.assertEqual(check.get("boost", 0), box_spots.NEEDS[needs], (key, n))
        self.assertTrue(content_plan.validate(plan))


class TestAnswerThreeLedgeBoxes(unittest.TestCase):
    def build(self, difficulty, blue, boost="shared_global"):
        opts = rulings.options(difficulty, blue, boost, wumpa="crates")
        opts["item_box_count"] = 50
        return make_world(opts, seed=7, stop_before="pre_fill")

    def test_rows_are_the_tv2_rows(self):
        spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES["tv-world"])
        for n, (pos, yaw) in LEDGE.items():
            self.assertEqual((spots[n]["pos"], spots[n]["rot_y"], spots[n]["rule_of"], spots[n]["needs"]),
                             (pos, yaw, "wumpa_crate:3", "blue_fire"))
            self.assertEqual(CTR_LOCATION_IDS[f"TV World: Item Box {n}"],
                             named_tracks.location_code(destinations.named_track("tv-world").block_index, f"item_box_{n}"))
        self.assertLessEqual(max(LEDGE), box_spots.MAX_NUMBER)
        box_spots.check_rules()

    def test_same_rule_as_the_crates_in_hard_and_easy_with_and_without_blue_fire(self):
        for difficulty in ("easy", "hard"):
            for blue in (False, True):
                with self.subTest(difficulty=difficulty, blue=blue):
                    room = wire(self.build(difficulty, blue))
                    plan = room["content_plan"]
                    self.assertTrue(content_plan.validate(plan))
                    present = difficulty == "hard" or blue
                    record = spot_set(plan, rulings.TV)
                    self.assertEqual(record["pool"], 34 + 2 * present)
                    checks = {c["spot"]["number"]: c for c in boxes(plan, rulings.TV)}
                    crate = next((c for c in plan["checks"] if c["owner"] == rulings.TV
                                  and c["display_name"] == "TV World: Wumpa Crate 3"), None)
                    self.assertEqual(crate is not None, present)
                    if present:
                        rank = 2 if difficulty == "hard" else 3
                        self.assertEqual({checks[n]["boost"] for n in LEDGE}, {rank})
                        self.assertEqual(crate["boost"], rank)
                    else:
                        self.assertFalse(set(LEDGE) & set(checks))
                    restored = make_world({}, passthrough=copy.deepcopy(room), stop_before="pre_fill")
                    self.assertEqual(wire(restored)["content_plan"], plan)


class TestAnswerFourJungleBoogie(unittest.TestCase):
    def test_file_holds_only_dowlles_stream_rows(self):
        doc = box_spots.CUSTOM_FILES[JB]["doc"]
        self.assertEqual(doc["track"]["lev_sha256"], [JB_PIN])
        self.assertEqual([s["number"] for s in doc["spots"]], JB_NUMBERS)
        self.assertEqual(len(doc["spots"]), 28)
        self.assertTrue(all(s["needs"] == "none" and s["provenance"][0] == f"cp1-{JB}" for s in doc["spots"]))
        source = box_spots.SOURCE_RECORDS[f"cp1-{JB}"]
        self.assertEqual(source["sha256"], box_spots.SOURCE_RECORDS["cp1-acropolis"]["sha256"])
        self.assertEqual(sorted(source["rows"]), [930 + n for n in JB_NUMBERS])
        for spot in doc["spots"]:
            self.assertEqual(CTR_LOCATION_IDS[f"Jungle Boogie N-Gage: Item Box {spot['number']}"],
                             named_tracks.location_code(destinations.named_track(JB).block_index,
                                                        f"item_box_{spot['number']}"))

    def test_seeds_on_the_pinned_lev_only(self):
        tid = f"custom/{JB}/1.0.0"
        for count, picked in ((15, 15), (50, 28)):
            plan = first_world(box_options(custom=[package(JB, JB_PIN, 0)], item_box_count=count)).ctr_content_plan
            record = spot_set(plan, tid)
            self.assertEqual((record["pool"], len(record["picked"]), record["lev_sha256"]), (28, picked, JB_PIN))
            self.assertLessEqual(set(record["picked"]), set(JB_NUMBERS))
            self.assertEqual(len(boxes(plan, tid)), picked)
        other = first_world(box_options(custom=[package(JB, "01" * 32, 0)])).ctr_content_plan
        self.assertIsNone(spot_set(other, tid))
        self.assertEqual(boxes(other, tid), [])


class TestAnswerFiveCountrySpeedway(unittest.TestCase):
    def plan(self, pin, count=50):
        return first_world(box_options(custom=[package("country-speedway", pin, 25 if pin == CS130 else 0)],
                                       item_box_count=count, progressive_boost="shared_global")).ctr_content_plan

    def test_one_file_for_both_levs(self):
        doc = box_spots.CUSTOM_FILES["country-speedway"]["doc"]
        self.assertEqual(doc["track"]["lev_sha256"], [CS131, CS130])
        self.assertEqual([s["number"] for s in doc["spots"]], COUNTRY_ALL)
        self.assertEqual(doc["retired"], [11])
        self.assertEqual({s["number"]: s["lev_sha256"] for s in doc["spots"] if "lev_sha256" in s},
                         {3: [CS131], 4: [CS131]})
        spot18 = box_spots.spots_by_number(box_spots.CUSTOM_FILES["country-speedway"])[18]
        self.assertNotIn("lev_sha256", spot18)

    def test_each_lev_seeds_its_set_and_spot_11_never(self):
        tid = "custom/country-speedway/1.0.0"
        for pin, numbers, ranked in ((CS130, COUNTRY_130, {14, 23, 24}), (CS131, COUNTRY_ALL, {3, 4, 14, 23, 24})):
            with self.subTest(pin=pin[:8]):
                plan = self.plan(pin)
                self.assertTrue(content_plan.validate(plan))
                record = spot_set(plan, tid)
                self.assertEqual((record["pool"], record["picked"], record["lev_sha256"]), (len(numbers), numbers, pin))
                own = boxes(plan, tid)
                self.assertEqual([c["spot"]["number"] for c in own], numbers)
                self.assertEqual({c["spot"]["number"] for c in own if c.get("boost")}, ranked)
                self.assertNotIn(content_item_boxes.country_speedway.BOX_RULES_KEY, plan["item_boxes"])
                self.assertNotIn("Country Speedway: Item Box 11", {c["display_name"] for c in plan["checks"]})

    def test_a_131_pick_is_not_a_valid_pick_on_the_race_file(self):
        """The 1.3.1 set (with 3 and 4) checked as if the package were 1.3.0 is
        refused, so no plan can carry spot 3 or 4 on the race LEV."""
        tid = "custom/country-speedway/1.0.0"
        record = {k: v for k, v in spot_set(self.plan(CS131), tid).items() if k != "track_id"}
        record["lev_sha256"] = CS130
        track = dict(origin="custom", named_block=17, id=tid)
        race = package("country-speedway", CS130, 25)
        with self.assertRaisesRegex(box_spots.SpotFileError, "not a valid pick"):
            box_spots.check_spot_set(track, race, 0, record, 50)
        ok = dict(record, pool=len(COUNTRY_130), picked=COUNTRY_130)
        self.assertIs(box_spots.check_spot_set(track, race, 0, ok, 50), box_spots.CUSTOM_FILES["country-speedway"])

    def test_file_check_refuses_a_bad_lev_subset(self):
        doc = copy.deepcopy(box_spots.CUSTOM_FILES["country-speedway"]["doc"])
        box_spot_catalog.check_draft_file(doc)
        for bad in ([], [CS131, CS130], [CS131, CS131], ["01" * 32], CS131):
            broken = copy.deepcopy(doc)
            broken["spots"][2]["lev_sha256"] = bad
            with self.subTest(bad=bad), self.assertRaises(box_spots.SpotFileError):
                box_spot_catalog.check_draft_file(broken)
        retail = copy.deepcopy(box_spots.RETAIL_FILES[0]["doc"])
        retail["spots"][0]["lev_sha256"] = [CS131]
        with self.assertRaises(box_spots.SpotFileError):
            box_spot_catalog.check_draft_file(retail)


class TestCompatibility(unittest.TestCase):
    PACKAGES = (("royal-raceway", None, 17), ("super-snocross-2", None, 17), ("snowy-valley", None, 17),
                ("tv-world", None, 17), (JB, JB_PIN, 0), ("country-speedway", CS130, 25))

    def packages(self, country=CS130):
        out = [package(k, d or IM1[k][1], c) for k, d, c in self.PACKAGES if k != "country-speedway"]
        return out + [package("country-speedway", country, 25 if country == CS130 else 0)]

    def test_item_box_count_zero_is_identical_to_main(self):
        for country in (CS130, CS131):
            with self.subTest(country=country[:8]):
                options = box_options(custom=self.packages(country), item_box_count=0,
                                      progressive_boost="shared_global", logic_difficulty="hard")
                now = wire(first_world(options))
                with main_catalog():
                    before = wire(first_world(options))
                self.assertEqual(now, before)

    def test_rooms_from_before_restore_unchanged(self):
        """Rooms generated on main before IM1b: Country Speedway 1.3.1 with all
        49 spots (spot 11 among the picks), 1.3.0 with its crate seats and
        pickup rules, Jungle Boogie without boxes."""
        for country, count in ((CS131, 50), (CS130, 15), (CS131, 15)):
            with self.subTest(country=country[:8], count=count):
                options = box_options(custom=self.packages(country), item_box_count=count,
                                      progressive_boost="shared_global", logic_difficulty="hard")
                with main_catalog():
                    room = wire(first_world(options))
                plan = room["content_plan"]
                tid = "custom/country-speedway/1.0.0"
                sets = {s["track_id"]: s for s in plan["item_boxes"].get("spot_sets", [])}
                if country == CS131:
                    self.assertEqual(sets[tid]["file_sha256"], country_speedway_before_im1b()["sha256"])
                    if count == 50:
                        self.assertIn(11, sets[tid]["picked"])
                else:
                    self.assertNotIn(tid, sets)
                    self.assertIn(tid, plan["item_boxes"][content_item_boxes.country_speedway.BOX_RULES_KEY])
                self.assertNotIn(f"custom/{JB}/1.0.0", sets)
                restored = make_world({}, seed=999, passthrough=copy.deepcopy(room))
                self.assertEqual(wire(restored), room)

    def test_restore_only_country_file_never_serves_a_new_room(self):
        options = box_options(custom=[package("country-speedway", CS131, 0)], item_box_count=50)
        with main_catalog():
            stale = first_world(options).ctr_content_plan
        with self.assertRaises(OptionError):
            content_plan.validate(stale)


if __name__ == "__main__":
    unittest.main()
