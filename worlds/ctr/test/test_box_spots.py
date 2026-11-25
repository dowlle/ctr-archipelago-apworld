"""Hand-placed AP box spots (alpha3 row A3-14).

Retail's 241 boxes are 18 built-in spot files that rebuild the frozen tables
exactly; a track with more than 15 eligible spots gets 15 picked on a generator
of its own; a named custom track with a spot file stands its boxes there
instead of on its weapon crates, numbered from 1; a generic slot never uses a
file. The test spot files (test/fixtures/box_spots) are never shipped: the
tests put them in place of the shipped table for their own duration.
"""
import contextlib
import copy
import hashlib
import json
import pkgutil
import random
import unittest
from unittest import mock

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError

from .. import box_spot_catalog, box_spots, content_item_boxes, content_plan, crate_exclusions, destinations, item_boxes, named_tracks
from ..Locations import CTR_LOCATION_IDS
from .test_content_item_boxes import BTP_ID, LOOP_ID, before_cp1, box_options, boxes, btp, builtin_only, first_world, refused
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN

FIXTURES = "test/fixtures/"
CRASH_COVE = 3
#: The reviewed community files (A3-45): track key -> (named block, LEV pin of
#: the package revision in the shared YAMLs, spots that need more than none).
COMMUNITY = {
    "ancient-lake": (1, "21e1ffe395f1d5d0a2c4538050d18912577a4dd783026fa9caea8b09ad8d3aee", {2: "boost"}),
    "dk-pass": (25, "cf29d61f8e7b9a5d210a060ffbc4da22b04483d25d85c6a01bff855f312c09ef", {}),
    # A4-62b: Country Speedway 1.3.1 (spot 6 of the submission dropped: it sits
    # on a wall top) and Gossamer's Castle 1.0.0 (block 89).
    "country-speedway": (17, "504946fdd87d040cce6dfadcf158759b53962d2a08b41002ad97949051b3d996",
                         {2: "boost", 3: "boost", 4: "boost", 11: "boost", 14: "boost"}),
    "gossamer-s-castle": (89, "82a6d81942050ad29370033ccabc111b1731f24cf42e103afab12fd42a79f14c", {6: "boost"}),
}
#: Spot numbers per file; every other file holds 1 to 15.
COMMUNITY_NUMBERS = {"country-speedway": [n for n in range(1, 16) if n != 6]}
ARABIAN_DAY = "arabian-heights-day"
#: A7-1: the source of dowlle's retail spots and how many ship per LevelID.
DOWLLE_2026_11_24 = "dowlle, Box Author Mode, 2026-11-24"
DOWLLE_2026_11_24_COUNTS = {0: 34, 1: 35, 2: 34, 3: 30, 4: 22, 5: 35, 6: 18, 7: 35, 8: 0, 9: 34, 10: 35, 11: 33, 12: 34, 13: 35, 14: 27, 15: 35, 16: 35, 17: 35}
ARABIAN_DAY_LEV = "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900"

#: CP1: dowlle's Box Author Mode spots on named custom tracks (2026-11-24).
#: track key -> (named block, LEV pin, first new number, spots shipped, numbers
#: that need boost from his stream calls). Numbers follow the track's existing
#: spots (main or the BX3 copies) in placement order; airborne spots, spots
#: without ground and spots past number 50 are held, without a number.
DOWLLE_CUSTOM = {
    "ancient-lake": (1, "21e1ffe395f1d5d0a2c4538050d18912577a4dd783026fa9caea8b09ad8d3aee", 16, 19, []),
    "arctic-alleyway": (6, "a31f66f5ac7d0fcf1a99cfa4af0d956e655f51a3fbc27b3511e24e23f139dda9", 17, 34, [36]),
    "baby-t-park": (8, "be161e0b11aa03505c501b7db012d830405e69e171f84633c2e24ffe9cc3cbf8", 1, 29, []),
    "big-forest": (9, "9553863255f8b9a72cf2b8fbe0e3f1f3195e0e502c604ccf0c3f06ff0c3ea535", 13, 38, [50]),
    "bowser-castle-1": (10, "0b59b54ac3d902d43ee7b798d45dd4979aa5859520460282d22fb6bc85dcbcd9", 1, 10, []),
    "chasqui-rally": (12, "9201064be9731919a0b86590af2801f902c0c8704520521900e84faf17ecc06d", 9, 27, []),
    "choco-island-2": (13, "4d5a7397feaa242083a59279c28d8e96118ec7074de5f03eeab329207c4472d4", 1, 18, []),
    "coco-park-2025": (15, "bbebd28a0c61723b632a1535d26a5f90d061f6c918403a851680f64e487f9a1c", 1, 43, [10, 11, 12, 13, 14, 15, 16, 17]),
    "country-speedway": (17, "504946fdd87d040cce6dfadcf158759b53962d2a08b41002ad97949051b3d996", 16, 35, []),
    "crystal-caves": (18, "eddcd303e316e8eb41f885e8ec959a2c2d3db06e21727dfc50c61ab8a8048139", 13, 24, []),
    "dark-ruins": (21, "ced2df2e83aef4759e0bb132fbd36f44c51d818b623d7950faec2407b8229589", 13, 15, [27]),
    "diwali": (23, "5d4c5da687c67af1d7baa42f1246b4c4d43e708667f2c5921ce4ec0ebcd5f305", 13, 15, []),
    "draculas-castle": (26, "8c343aa6723ee2dec99d54f815e77e9e20798f657d6f4464f312529ffe4698f4", 12, 39, []),
    "dreamy-heights": (27, "9f85b2d5dbc2fe543ce024751fc6e08f77d7ba649f8ddfec936f016804a9bbf3", 17, 33, []),
    "garden-speedway": (32, "a04e15057ee83c80d98f0e88eb513eb51286e123b11e82155203b7ef9a43b23e", 1, 15, []),
    "gossamer-s-castle": (89, "82a6d81942050ad29370033ccabc111b1731f24cf42e103afab12fd42a79f14c", 16, 23, []),
    "green-hill-raceway": (35, "50250966e9b31d13b140aaafa9433ffce19269898a0850edd0a1e8cf1207c760", 1, 27, []),
    "haven-stadium": (38, "37f2daddfe7fd988b091b914536737f77a3ac07384e120a25b7e3d69386e3188", 1, 21, []),
    "inferno-island": (41, "d8863cf0274fc29ac8e2118e666604ddc80ebbe49d5c747dd91acec6a07dfd32", 1, 25, [20, 21, 22]),
    "neon-paradise": (51, "639434d84fe6de4ba88a31a1dd5a11291d640617ab25af9c7bfbd5d383b53d5d", 19, 20, []),
    "neonstadion": (52, "8c1fde3e60405eb8737e75aa4cfe5cb205cd9d21961eccf4c5d7827ecf484880", 17, 24, []),
}


def community_numbers(key):
    return COMMUNITY_NUMBERS.get(key, list(range(1, 16)))


def fixture(path):
    return json.loads(pkgutil.get_data(box_spots.__package__, FIXTURES + path).decode("utf-8"))


def entry(path):
    raw = pkgutil.get_data(box_spots.__package__, FIXTURES + path)
    return dict(doc=box_spot_catalog._check_file_shape(json.loads(raw.decode("utf-8")), path), path=path,
                sha256=hashlib.sha256(raw).hexdigest())


@contextlib.contextmanager
def spot_files(retail=(), custom=()):
    """Put test spot files in place of the shipped ones for the block."""
    r = {e["doc"]["track"]["level_id"]: e for e in (entry(f"box_spots/retail/{n}.json") for n in retail)}
    c = {e["doc"]["track"]["track_key"]: e for e in (entry(f"box_spots/custom/{n}.json") for n in custom)}
    with mock.patch.dict(box_spots.RETAIL_FILES, r), mock.patch.dict(box_spots.CUSTOM_FILES, c):
        yield


def spot_set(plan, track_id):
    return content_item_boxes.spot_sets(plan["item_boxes"]).get(track_id)


class TestConversion(unittest.TestCase):
    def test_files_rebuild_the_frozen_tables(self):
        frozen = fixture("retail_box_tables.json")
        self.assertEqual(item_boxes.PLACED_COUNTS, frozen["placed_counts"])
        # A7-1 adds one ruled spot past the built-ins: Papu's Pyramid box 50
        # (BX5 candidate C), with built-in spot 10's rule (boost, hard tier).
        papu = ("Papu's Pyramid", next(s["number"] for s in box_spots.RETAIL_FILES[5]["doc"]["spots"]
                                       if s["pos"] == [102, 663, -4736]))
        self.assertEqual(item_boxes.SK_REQUIRED_TIER,
                         {(t, n): v for t, n, v in frozen["sk_required_tier"]} | {papu: 2})
        self.assertEqual(item_boxes.BOX_RULES,
                         {(t, n): (b, s) for t, n, b, s in frozen["box_rules"]} | {papu: (1, True)})
        self.assertEqual(item_boxes.EXPLICIT_NO_GATE, frozenset((t, n) for t, n in frozen["explicit_no_gate"]))
        self.assertEqual(list(item_boxes.TIGER_TEMPLE_DOOR_BOXES), [tuple(k) for k in frozen["tiger_temple_door"]])

    def test_files_match_the_shared_coordinate_fixture(self):
        rows = sorted([doc["track"]["level_id"], s["number"], *s["pos"], s["rot_y"]]
                      for doc in (e["doc"] for e in box_spots.RETAIL_FILES.values())
                      for s in doc["spots"] if s.get("source") == "builtin")
        self.assertEqual(rows, fixture("box_spots_builtin_rows.json")["rows"])
        self.assertEqual(len(rows), 241)

    def test_catalog_covers_the_18_retail_tracks_and_the_named_custom_files(self):
        self.assertEqual(sorted(box_spots.RETAIL_FILES), list(range(18)))
        self.assertEqual(set(box_spots.CUSTOM_FILES), {*COMMUNITY, *DOWLLE_CUSTOM, ARABIAN_DAY, "sunset-vista"})
        for e in box_spots.RETAIL_FILES.values():
            self.assertTrue(all(s.get("source") in ("builtin", DOWLLE_2026_11_24) for s in e["doc"]["spots"]), e["path"])
            self.assertEqual(e["doc"]["retired"], [], e["path"])

    def test_dowlle_retail_spots_of_2026_11_24(self):
        """A7-1: dowlle's Box Author Mode spots on the retail tracks, numbered from
        16 after the built-ins. dowlle ruled his placements boost 0 (A7-1b), so
        they ship with needs none, except Papu's Pyramid box 50 (BX5 candidate
        C) with built-in spot 10's rule. Spots flagged on 2026-11-08, airborne
        spots and spots without ground under them stay held, without a number."""
        for lid, e in box_spots.RETAIL_FILES.items():
            new = [s for s in e["doc"]["spots"] if s.get("source") != "builtin"]
            self.assertEqual(len(new), DOWLLE_2026_11_24_COUNTS[lid], e["path"])
            self.assertEqual([s["number"] for s in new], list(range(16, 16 + len(new))), e["path"])
            for spot in new:
                self.assertEqual(spot["source"], DOWLLE_2026_11_24)
                if lid == 5 and spot["pos"] == [102, 663, -4736]:
                    self.assertEqual((spot["rot_y"], spot["needs"], spot["shortcut"]), (2488, "boost", "hard"))
                    self.assertEqual(box_spots.RETAIL_RULES[("Papu's Pyramid", spot["number"])], (1, True))
                else:
                    self.assertEqual(spot["needs"], "none", (e["path"], spot["number"]))
                    self.assertNotIn("shortcut", spot)
        self.assertEqual(sum(DOWLLE_2026_11_24_COUNTS.values()), 546)

    def test_sunset_vista_file_is_the_approved_no_boost_file(self):
        """The in-game review of 2026-11-20: all 24 spots stay where they
        are, need no boost, and a lap finishes without boost (finish rank 0)."""
        from .. import content_capability
        doc = box_spots.CUSTOM_FILES["sunset-vista"]["doc"]
        lev = doc["track"]["lev_sha256"][0]
        self.assertEqual([s["number"] for s in doc["spots"]], list(range(1, 25)))
        for spot in doc["spots"]:
            self.assertEqual(spot["needs"], "none", spot["number"])
            self.assertIn("2026-11-20", spot["source"])
            self.assertEqual(box_spots.needs_rank(spot), 0)
        package = dict(content_id="sunset-vista", revision="1.2.0", capabilities={},
                       files=[dict(role="lev", sha256=lev)])
        self.assertEqual(content_capability.ruled_finish(package), 0)
        self.assertIsNone(content_capability.ruled_finish(dict(package, revision="1.1.0",
                                                               files=[dict(role="lev", sha256="01" * 32)])))

    def test_number_lock(self):
        """Append only: a locked number stays a spot or is retired, never both,
        and every spot number is locked."""
        lock = fixture("box_spot_numbers_lock.json")["tracks"]
        files = {f"retail:{lid}": e["doc"] for lid, e in box_spots.RETAIL_FILES.items()}
        files.update({f"custom:{key}": e["doc"] for key, e in box_spots.CUSTOM_FILES.items()})
        self.assertLessEqual(set(lock), set(files) | set(lock))
        for track, row in lock.items():
            doc = files.get(track)
            self.assertIsNotNone(doc, f"{track} lost its spot file")
            numbers = {s["number"] for s in doc["spots"]}
            self.assertLessEqual(set(row["numbers"]), numbers | set(doc["retired"]), track)
            self.assertLessEqual(set(row["retired"]), set(doc["retired"]), track)
            self.assertFalse(numbers & set(row["retired"]), f"{track} reuses a retired number")
        for track, doc in files.items():
            self.assertIn(track, lock, f"{track} is not in the number lock")
            self.assertLessEqual({s["number"] for s in doc["spots"]}, set(lock[track]["numbers"]), track)

    def test_spot_codes(self):
        for track_index, track in enumerate(item_boxes.BOX_TRACKS):
            for n in range(1, 16):
                self.assertEqual(item_boxes.ITEM_BOX_CLASS.slot_code(track, n), 35014000 + 15 * track_index + n - 1)
            for n in range(16, 51):
                self.assertEqual(item_boxes.ITEM_BOX_CLASS.slot_code(track, n), 35014300 + 35 * track_index + n - 16)
                self.assertEqual(CTR_LOCATION_IDS[f"{track}: Item Box {n}"],
                                 item_boxes.ITEM_BOX_CLASS.slot_code(track, n))
        for n in range(1, 51):
            self.assertEqual(named_tracks.location_code(8, f"item_box_{n}"), 35200000 + 200 * 8 + 19 + n)


class TestFileChecks(unittest.TestCase):
    BASE = {"format": "ctr-ap-box-spots", "version": 1,
            "track": {"kind": "retail", "level_id": 4, "name": "Tiger Temple"},
            "spots": [{"number": 1, "pos": [0, 0, 0], "rot_y": 0, "needs": "none"}], "retired": []}

    def refuses(self, change):
        doc = copy.deepcopy(self.BASE)
        change(doc)
        with self.assertRaises(box_spots.SpotFileError):
            box_spot_catalog._check_file_shape(doc, "<test>")

    def test_good_file(self):
        self.assertEqual(box_spot_catalog._check_file_shape(copy.deepcopy(self.BASE), "<test>")["version"], 1)

    def test_bad_files(self):
        spot = lambda d: d["spots"][0]
        cases = [
            lambda d: d.__setitem__("format", "ctr-ap-box-placements"),
            lambda d: d.__setitem__("version", 2),
            lambda d: d.pop("retired"),
            lambda d: d["spots"].append(dict(spot(d))),
            lambda d: spot(d).__setitem__("number", 51),
            lambda d: spot(d).__setitem__("number", 0),
            lambda d: d.__setitem__("retired", [1]),
            lambda d: spot(d).__setitem__("pos", [0, 0]),
            lambda d: spot(d).__setitem__("pos", [0, 40000, 0]),
            lambda d: spot(d).__setitem__("needs", "blue_fire"),
            lambda d: spot(d).__setitem__("shortcut", "easy"),
            lambda d: spot(d).__setitem__("height", 3),
            lambda d: spot(d).__setitem__("no_gate", False),
            lambda d: (spot(d).__setitem__("needs", "boost"), spot(d).__setitem__("no_gate", True)),
            lambda d: (d["track"].__setitem__("level_id", 3), spot(d).__setitem__("door", "tiger_temple")),
            lambda d: d.__setitem__("track", {"kind": "custom", "track_key": "baby-t-park", "name": "Baby T Park",
                                              "lev_sha256": []}),
            lambda d: d.__setitem__("track", {"kind": "custom", "track_key": "baby-t-park", "name": "Baby T Park",
                                              "lev_sha256": ["AB" * 32]}),
        ]
        for i, change in enumerate(cases):
            with self.subTest(i):
                self.refuses(change)

    def test_absent_needs_means_usf(self):
        self.assertEqual(box_spots.needs_rank({"number": 1, "pos": [0, 0, 0], "rot_y": 0}), 2)


class TestSourceChecks(unittest.TestCase):
    def test_catalog_has_all_reviewed_ap_source_kinds(self):
        docs = [e["doc"] for e in (*box_spots.RETAIL_FILES.values(), *box_spots.CUSTOM_FILES.values())]
        sources = set()
        for doc in docs:
            box_spots.check_file(doc)
            for spot in doc["spots"]:
                if spot["source_family"] == "ap_box":
                    sources.add(box_spots.SOURCE_RECORDS[spot["provenance"][0]]["kind"])
        self.assertEqual(sources, box_spot_catalog.AP_SOURCE_KINDS)

    def test_refuses_non_ap_and_unknown_families(self):
        doc = box_spots.RETAIL_FILES[4]["doc"]
        for family in ("weapon_crate", "wumpa_crate", "loose_fruit", "time_crate", "ctr_letter", "other"):
            with self.subTest(family=family), self.assertRaises(box_spots.SpotFileError):
                box_spots.check_file(dict(doc, spots=[dict(doc["spots"][0], source_family=family)]))

    def test_refuses_missing_or_mismatched_source(self):
        doc = box_spots.RETAIL_FILES[4]["doc"]
        original = doc["spots"][0]
        for field in ("source_family", "provenance"):
            spot = dict(original)
            del spot[field]
            with self.subTest(field=field), self.assertRaises(box_spots.SpotFileError):
                box_spots.check_file(dict(doc, spots=[spot]))
        for changes in ({"pos": [0, 0, 0]}, {"number": 50}, {"rot_y": original["rot_y"] + 1},
                        {"provenance": ["invented-source", 1]}):
            with self.subTest(changes=changes), self.assertRaises(box_spots.SpotFileError):
                box_spots.check_file(dict(doc, spots=[dict(original, **changes)]))

    def test_published_day_rows_are_the_only_donor_exception(self):
        doc = box_spots.CUSTOM_FILES[ARABIAN_DAY]["doc"]
        self.assertEqual([s["number"] for s in doc["spots"]], list(range(1, 28)))
        self.assertEqual({s["source_family"] for s in doc["spots"]}, {"weapon_crate"})
        box_spots.check_file(doc)
        with self.assertRaisesRegex(box_spots.SpotFileError, "LEV donor models"):
            box_spots.check_file(dict(doc, spots=[dict(doc["spots"][0], source_family="ap_box")]))

    def test_bx3_model_8_refused_even_if_labelled_ap(self):
        doc = box_spots.CUSTOM_FILES["chasqui-rally"]["doc"]
        # BX3 Chasqui row 1, from the LRG2Pancho model-8 extract.
        spot = dict(number=1, pos=[-4403, -15, 16274], rot_y=289, provenance=["bx3", 1])
        source = dict(kind="lev_model_extract", track="custom:chasqui-rally",
                      pins=doc["track"]["lev_sha256"], rows={1: [spot["number"], *spot["pos"], spot["rot_y"]]},
                      model_id=8, donor_lev_sha256="9bba2b38" + "0" * 56)
        for family in ("ap_box", "weapon_crate"):
            with self.subTest(family=family), self.assertRaisesRegex(box_spots.SpotFileError, "LEV donor models"):
                box_spot_catalog.check_file(dict(doc, spots=[dict(spot, source_family=family)]), {"bx3": source})

    def test_cp1_pins_cannot_be_broadened_by_a_spot_file(self):
        for key in ("chasqui-rally", "dark-ruins", "dreamy-heights", "neon-paradise"):
            doc = box_spots.CUSTOM_FILES[key]["doc"]
            pin = DOWLLE_CUSTOM[key][1]
            self.assertEqual(doc["track"]["lev_sha256"], [pin])
            track = dict(doc["track"], lev_sha256=[pin, "01" * 32])
            with self.subTest(track=key), self.assertRaisesRegex(box_spots.SpotFileError, "LEV pins"):
                box_spots.check_file(dict(doc, track=track))
            package = dowlle_package(key)
            named = dict(origin="custom", named_block=DOWLLE_CUSTOM[key][0])
            self.assertIsNotNone(box_spots.file_for(named, package))
            package["files"][0]["sha256"] = "01" * 32
            self.assertIsNone(box_spots.file_for(named, package))


class TestPick(unittest.TestCase):
    def test_fifteen_or_fewer_draw_nothing(self):
        with mock.patch.object(box_spots.random, "Random", side_effect=AssertionError("drew")):
            self.assertEqual(box_spots.pick([3, 1, 2], 7, 1, "retail:3"), [1, 2, 3])
            self.assertEqual(box_spots.pick(range(1, 16), 7, 1, "retail:3"), list(range(1, 16)))

    def test_more_than_fifteen_pick_fifteen_on_their_own_stream(self):
        pool = list(range(1, 24))
        state = random.getstate()
        first = box_spots.pick(pool, 7, 1, "retail:3")
        self.assertEqual(random.getstate(), state)
        self.assertEqual(len(first), 15)
        self.assertEqual(first, sorted(set(first)))
        self.assertLessEqual(set(first), set(pool))
        self.assertEqual(box_spots.pick(pool, 7, 1, "retail:3"), first)
        self.assertGreater(len({tuple(box_spots.pick(pool, s, 1, "retail:3")) for s in range(20)}), 1)
        self.assertNotEqual({tuple(box_spots.pick(pool, 7, p, "retail:3")) for p in (1, 2)}, {tuple(first)})


class TestRetailSeeds(unittest.TestCase):
    def test_every_retail_track_uses_its_built_in_spots(self):
        with builtin_only():
            self._every_retail_track_uses_its_built_in_spots()

    def _every_retail_track_uses_its_built_in_spots(self):
        for tier, value in (("easy", 0), ("medium", 1), ("hard", 2)):
            world = make_world(box_options(tier=tier), seed=2)
            plan = world.ctr_content_plan
            self.assertIn(box_spots.FEATURE, plan["required_features"])
            retail = [t for t in plan["tracks"] if t["origin"] == "retail"
                      and any(e.get("track_id") == t["id"] for e in plan["entries"])]
            self.assertEqual(sorted(s["track_id"] for s in plan["item_boxes"]["spot_sets"]),
                             sorted(t["id"] for t in retail))
            for track in retail:
                record = spot_set(plan, track["id"])
                name = track["display_name"]
                self.assertEqual(record["picked"], content_item_boxes.retail_slots(name, value))
                self.assertEqual(record["pool"], len(record["picked"]))
                for check in boxes(plan, track["id"]):
                    n = check["spot"]["number"]
                    self.assertEqual(check["display_name"], f"{name}: Item Box {n}")
                    row = box_spots.spots_by_number(box_spots.RETAIL_FILES[track["retail_id"]])[n]
                    self.assertEqual((check["spot"]["pos"], check["spot"]["rot_y"]), (row["pos"], row["rot_y"]))

    def test_spots_leave_the_fill_unchanged(self):
        """A retail seed fills exactly as without spot sets (the legacy record):
        same seed, same items on the same locations."""
        options = box_options(tier="hard", progressive_boost="shared_global")
        placements = []
        for legacy in (False, True):
            patch = (mock.patch.object(content_item_boxes, "add_spot_sets", lambda record, *a: record)
                     if legacy else contextlib.nullcontext())
            with patch, builtin_only():
                world = first_world(options, seed=11)
                distribute_items_restrictive(world.multiworld)
            placements.append(sorted((loc.name, loc.item.name) for loc in world.multiworld.get_locations()
                                     if loc.item is not None))
            if legacy:
                self.assertNotIn("spot_sets", world.ctr_content_plan["item_boxes"])
        self.assertEqual(placements[0], placements[1])

    def test_a_record_without_spot_sets_still_validates(self):
        """An alpha2-era plan (no spot sets, no spot fields) is still read."""
        with builtin_only():
            plan = copy.deepcopy(make_world(box_options(tier="hard"), seed=2).ctr_content_plan)
        plan["item_boxes"].pop("spot_sets")
        plan["required_features"].remove(box_spots.FEATURE)
        for check in plan["checks"]:
            check.pop("spot", None)
        self.assertFalse(refused(plan))


class TestCommunitySpotsOnRetail(unittest.TestCase):
    """Crash Cove with its 10 built-in spots and 8 test spots 16 to 23."""

    def test_more_than_fifteen_picks_fifteen(self):
        with spot_files(retail=["CRASH_COVE"]):
            picks = set()
            for seed in range(6):
                plan = make_world(box_options(tier="hard", progressive_boost="shared_global"), seed=seed).ctr_content_plan
                record = spot_set(plan, "retail:3")
                self.assertEqual((record["pool"], len(record["picked"])), (18, 15))
                picks.add(tuple(record["picked"]))
                checks = boxes(plan, "retail:3")
                self.assertEqual([c["spot"]["number"] for c in checks], record["picked"])
                spots = box_spots.spots_by_number(box_spots.RETAIL_FILES[CRASH_COVE])
                for check in checks:
                    n = check["spot"]["number"]
                    self.assertEqual(check["location"], CTR_LOCATION_IDS[f"Crash Cove: Item Box {n}"])
                    self.assertEqual(check.get("boost", 0), box_spots.needs_rank(spots[n]))
                    self.assertEqual(check["spot"]["pos"], spots[n]["pos"])
                self.assertFalse(refused(plan))
            self.assertGreater(len(picks), 1)

    def test_filled_seed_is_beatable_with_every_location_reachable(self):
        with spot_files(retail=["CRASH_COVE"], custom=["baby-t-park"]):
            for seed, extra in enumerate(({}, dict(progressive_boost="per_character", tier="hard"))):
                world = first_world(box_options(custom=[btp()], **extra), seed=seed * 5)
                distribute_items_restrictive(world.multiworld)
                state = CollectionState(world.multiworld)
                state.sweep_for_advancements()
                self.assertTrue(world.multiworld.can_beat_game(state), extra)
                self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations()), extra)

    def test_forged_spot_sets_refuse(self):
        with spot_files(retail=["CRASH_COVE"]):
            plan = make_world(box_options(tier="hard"), seed=3).ctr_content_plan
            self.assertFalse(refused(plan))

            def change(edit):
                forged = copy.deepcopy(plan)
                edit(forged, next(s for s in forged["item_boxes"]["spot_sets"] if s["track_id"] == "retail:3"))
                return refused(forged)

            other = sorted(set(range(1, 11)) | set(range(16, 24)))
            self.assertTrue(change(lambda p, s: s.__setitem__("picked", s["picked"][:14])))
            self.assertTrue(change(lambda p, s: s.__setitem__("picked", other[:15][::-1])))
            self.assertTrue(change(lambda p, s: s.__setitem__("pool", 17)))
            self.assertTrue(change(lambda p, s: s.__setitem__("file_sha256", "0" * 64)))
            self.assertTrue(change(lambda p, s: p["item_boxes"]["spot_sets"].remove(s)))
            unpicked = next(n for n in other if n not in spot_set(plan, "retail:3")["picked"])
            self.assertTrue(change(lambda p, s: s.__setitem__("picked", sorted(s["picked"][1:] + [unpicked]))))
            box = next(c for c in boxes(plan, "retail:3"))
            for edit in (lambda c: c["spot"]["pos"].__setitem__(0, c["spot"]["pos"][0] + 1),
                         lambda c: c.pop("spot"), lambda c: c["spot"].__setitem__("number", 24)):
                forged = copy.deepcopy(plan)
                edit(next(c for c in forged["checks"] if c["location"] == box["location"]))
                self.assertTrue(refused(forged))


class TestNamedCustomSpots(unittest.TestCase):
    """Baby T Park (named block 8) with a test file of 18 spots from 1."""

    def test_spots_replace_crate_seating(self):
        with spot_files(custom=["baby-t-park"]):
            for tier, pool in (("easy", 17), ("medium", 18)):
                plan = make_world(box_options(custom=[btp(8)], tier=tier, progressive_boost="shared_global"),
                                  seed=4).ctr_content_plan
                record = spot_set(plan, BTP_ID)
                self.assertEqual((record["pool"], len(record["picked"])), (pool, 15))
                self.assertEqual(record["lev_sha256"], box_spots.lev_pin(btp()))
                spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES["baby-t-park"])
                own = boxes(plan, BTP_ID)
                self.assertEqual([c["spot"]["number"] for c in own], record["picked"])
                for check in own:
                    n = check["spot"]["number"]
                    self.assertEqual(check["location"], named_tracks.location_code(8, f"item_box_{n}"))
                    self.assertEqual(check["display_name"], f"Baby T Park: Item Box {n}")
                    # The spot's own field replaces the finish term.
                    self.assertEqual(check.get("boost", 0), box_spots.needs_rank(spots[n]))
                self.assertFalse(refused(plan))

    def test_another_lev_keeps_crate_seating(self):
        with spot_files(custom=["baby-t-park"]):
            plan = make_world(box_options(custom=[content_plan.PACKAGES[0] | {"capabilities": dict(
                content_plan.PACKAGES[0]["capabilities"], weapon_crates=8)}]), seed=4).ctr_content_plan
            track_id = next(t["id"] for t in plan["tracks"] if t.get("named_block") == 8)
            self.assertIsNone(spot_set(plan, track_id))
            self.assertEqual(len(boxes(plan, track_id)), 8)
            self.assertNotIn("spot", boxes(plan, track_id)[0])

    def test_generic_slot_never_uses_a_file(self):
        loop = copy.deepcopy(UNKNOWN)
        loop["capabilities"]["weapon_crates"] = 12
        doc = fixture("box_spots/custom/baby-t-park.json")
        doc["track"].update(track_key=loop["content_id"], lev_sha256=[box_spots.lev_pin(loop)])
        raw = json.dumps(doc).encode()
        fake = {loop["content_id"]: dict(doc=doc, path="<generic>", sha256=hashlib.sha256(raw).hexdigest())}
        with mock.patch.dict(box_spots.CUSTOM_FILES, fake):
            plan = make_world(box_options(custom=[btp(), loop]), seed=6).ctr_content_plan
        self.assertIsNone(spot_set(plan, LOOP_ID))
        self.assertEqual(len(boxes(plan, LOOP_ID)), 12)

    def test_tracker_round_trip_with_spots(self):
        with spot_files(retail=["CRASH_COVE"], custom=["baby-t-park"]):
            options = box_options(custom=[btp()], tier="hard")
            wire = json.loads(json.dumps(make_world(options, seed=2).fill_slot_data()))
            self.assertIn(box_spots.FEATURE, wire["content_plan"]["required_features"])
            restored = make_world(box_options(custom=[btp()], box_locations=False), seed=9, passthrough=wire)
            self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
            forged = copy.deepcopy(wire)
            forged["content_plan"]["item_boxes"]["spot_sets"][0]["picked"].reverse()
            with self.assertRaises(OptionError):
                make_world(options, seed=2, passthrough=forged)


def community_package(key, crates=17, digest=None):
    """A catalogue package of a community-file track on the given LEV."""
    package = btp(crates)
    old = package["files"][0]["sha256"]
    name = box_spots.CUSTOM_FILES[key]["doc"]["track"]["name"]
    package.update(content_id=key, display_name=name, id=f"package/{key}/1.0.0", revision="1.0.0",
                   uuid=f"11111111-2222-4333-8444-{COMMUNITY[key][0]:012d}")
    package["files"][0]["sha256"] = digest or COMMUNITY[key][1]
    for evidence in package.get("evidence", []):
        evidence["file_hashes"] = [package["files"][0]["sha256"] if h == old else h for h in evidence["file_hashes"]]
    return package


class TestCommunitySpotFiles(unittest.TestCase):
    """The original community submissions, isolated from later additions."""

    def setUp(self):
        self.enterContext(before_cp1())

    def test_files_are_reviewed_named_track_files(self):
        for key, (block, pin, needs) in COMMUNITY.items():
            doc = box_spots.CUSTOM_FILES[key]["doc"]
            self.assertEqual(destinations.named_track(key).block_index, block)
            self.assertEqual(doc["track"]["lev_sha256"], [pin])
            self.assertEqual([s["number"] for s in doc["spots"]], community_numbers(key))
            self.assertEqual(doc["retired"], [])
            for spot in doc["spots"]:
                self.assertEqual(spot["source"], "community")
                self.assertEqual(spot["needs"], needs.get(spot["number"], "none"), (key, spot["number"]))
                self.assertNotIn("shortcut", spot)

    def test_seed_stands_every_box_at_the_spots(self):
        packages = [community_package(key) for key in COMMUNITY]
        plan = first_world(box_options(custom=packages, progressive_boost="shared_global")).ctr_content_plan
        self.assertIn(box_spots.FEATURE, plan["required_features"])
        self.assertNotIn(crate_exclusions.KEY, plan["item_boxes"])
        for key, (block, pin, needs) in COMMUNITY.items():
            track_id = next(t["id"] for t in plan["tracks"] if t.get("named_block") == block)
            record = spot_set(plan, track_id)
            self.assertEqual(record["lev_sha256"], pin)
            numbers = community_numbers(key)
            self.assertEqual((record["pool"], record["picked"]), (len(numbers), numbers))
            spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES[key])
            own = boxes(plan, track_id)
            self.assertEqual([c["spot"]["number"] for c in own], numbers)
            for check in own:
                n = check["spot"]["number"]
                self.assertEqual(check["spot"], box_spots.wire_spot(spots[n]))
                self.assertEqual(check["location"], named_tracks.location_code(block, f"item_box_{n}"))
                self.assertEqual(check.get("boost", 0), box_spots.NEEDS[needs.get(n, "none")])
        self.assertFalse(refused(plan))

    def test_country_speedway_without_crates_stands_its_spots(self):
        """Country Speedway 1.3.1 has no weapon crates (catalogue capability
        weapon_crates 0), so crate seating gives it no boxes; its file gives 14."""
        plan = first_world(box_options(custom=[community_package("country-speedway", 0)],
                                       progressive_boost="shared_global")).ctr_content_plan
        track_id = next(t["id"] for t in plan["tracks"] if t.get("named_block") == 17)
        numbers = community_numbers("country-speedway")
        self.assertEqual(spot_set(plan, track_id)["picked"], numbers)
        own = boxes(plan, track_id)
        self.assertEqual([c["spot"]["number"] for c in own], numbers)
        self.assertEqual([c["spot"]["number"] for c in own if c.get("boost", 0)], [2, 3, 4, 11, 14])
        other = first_world(box_options(custom=[community_package("country-speedway", 0, "01" * 32)])).ctr_content_plan
        other_id = next(t["id"] for t in other["tracks"] if t.get("named_block") == 17)
        self.assertIsNone(spot_set(other, other_id))
        self.assertEqual(boxes(other, other_id), [])

    def test_arabian_day_stands_nights_layout_on_its_pinned_crateless_lev(self):
        package = btp(0)
        package.update(content_id=ARABIAN_DAY, display_name="Arabian Heights Day",
                       id=f"package/{ARABIAN_DAY}/1.0.0", revision="1.0.0", evidence=[])
        package["files"][0]["sha256"] = ARABIAN_DAY_LEV
        options = box_options(custom=[package], item_box_count=50, progressive_boost="shared_global",
                              accessibility="full")
        world = first_world(options)
        plan = world.ctr_content_plan
        track_id = f"custom/{ARABIAN_DAY}/1.0.0"
        own = boxes(plan, track_id)
        numbers = list(range(1, 28))
        record = spot_set(plan, track_id)
        self.assertEqual((record["lev_sha256"], record["pool"], record["picked"]),
                         (ARABIAN_DAY_LEV, 27, numbers))
        self.assertEqual([check["location"] for check in own],
                         [named_tracks.location_code(3, f"item_box_{n}") for n in numbers])
        self.assertEqual([check["display_name"] for check in own],
                         [f"Arabian Heights Day: Item Box {n}" for n in numbers])
        self.assertEqual([check["spot"]["number"] for check in own if check.get("boost") == 2],
                         list(range(2, 21)))
        distribute_items_restrictive(world.multiworld)
        self.assertTrue(world.multiworld.fulfills_accessibility(CollectionState(world.multiworld)))

        package["files"][0]["sha256"] = "01" * 32
        other = first_world(box_options(custom=[package])).ctr_content_plan
        self.assertIsNone(spot_set(other, track_id))
        self.assertEqual(boxes(other, track_id), [])

    def test_other_revisions_keep_crate_seating(self):
        # The xdelta-import Ancient Lake LEV keeps its reviewed crate exclusion.
        old = "256d1ed4597aacd081d2806130c28969681ce35df5a5ba53200545cbd1835eb8"
        for key, digest in (("ancient-lake", old), ("dk-pass", "01" * 32)):
            plan = first_world(box_options(custom=[community_package(key, 8, digest)])).ctr_content_plan
            track_id = next(t["id"] for t in plan["tracks"] if t["origin"] == "custom")
            self.assertIsNone(spot_set(plan, track_id))
            self.assertNotIn("spot", boxes(plan, track_id)[0])
            self.assertEqual(crate_exclusions.KEY in plan["item_boxes"], key == "ancient-lake")

    def test_room_from_before_the_files_restores(self):
        """A room generated before the files shipped keeps its crate seats."""
        packages = [community_package(key) for key in COMMUNITY]
        with mock.patch.dict(box_spots.CUSTOM_FILES, {}, clear=True):
            wire = json.loads(json.dumps(first_world(box_options(custom=packages)).fill_slot_data()))
        sets = {s["track_id"] for s in wire["content_plan"]["item_boxes"]["spot_sets"]}
        self.assertFalse(any(t.startswith("custom/") for t in sets))
        restored = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
        # A retail track without its set still refuses.
        forged = copy.deepcopy(wire)
        forged["content_plan"]["item_boxes"]["spot_sets"] = [
            s for s in forged["content_plan"]["item_boxes"]["spot_sets"] if not s["track_id"].startswith("retail:")]
        self.assertTrue(any(t.startswith("retail:") for t in sets))
        with self.assertRaises(OptionError):
            make_world({}, seed=999, passthrough=forged)

    def test_tracker_round_trip(self):
        packages = [community_package(key) for key in COMMUNITY]
        wire = json.loads(json.dumps(first_world(box_options(custom=packages, tier="hard")).fill_slot_data()))
        restored = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
        forged = copy.deepcopy(wire)
        record = next(s for s in forged["content_plan"]["item_boxes"]["spot_sets"] if s["track_id"].startswith("custom/"))
        record["lev_sha256"] = "01" * 32
        with self.assertRaises(OptionError):
            make_world({}, seed=999, passthrough=forged)


if __name__ == "__main__":
    unittest.main()


class TestDowlleRetailSpots(unittest.TestCase):
    """A7-1: seeds on the shipped retail files with dowlle's 2026-11-24 spots."""

    def test_filled_seeds_reach_every_location_at_counts_15_and_50(self):
        for count, seed, extra in ((15, 0, {}), (50, 1, {}), (50, 4, dict(progressive_boost="per_character"))):
            with self.subTest(count=count, seed=seed):
                seen = set()
                world = first_world(box_options(custom=[], tier="hard", item_box_count=count, **extra), seed=seed)
                plan = world.ctr_content_plan
                for record in plan["item_boxes"]["spot_sets"]:
                    if not record["track_id"].startswith("retail:"):
                        continue
                    entry = box_spots.RETAIL_FILES[int(record["track_id"].split(":")[1])]
                    pool = len(box_spots.eligible(entry, 2))
                    self.assertEqual(record["pool"], pool, record["track_id"])
                    self.assertEqual(len(record["picked"]), min(count, pool), record["track_id"])
                    spots = box_spots.spots_by_number(entry)
                    checks = boxes(plan, record["track_id"])
                    self.assertEqual([c["spot"]["number"] for c in checks], record["picked"])
                    for check in checks:
                        row = spots[check["spot"]["number"]]
                        self.assertEqual((check["spot"]["pos"], check["spot"]["rot_y"]), (row["pos"], row["rot_y"]))
                    seen.update(n for n in record["picked"] if n >= 16)
                self.assertTrue(seen, "no 2026-11-24 spot was picked")
                self.assertFalse(refused(plan))
                distribute_items_restrictive(world.multiworld)
                state = CollectionState(world.multiworld)
                state.sweep_for_advancements()
                self.assertTrue(world.multiworld.can_beat_game(state))
                self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations()))

    def test_picked_boxes_carry_their_rules(self):
        options = box_options(custom=[], tier="hard", progressive_boost="shared_global",
                              progressive_stats="shared_global", item_box_count=50)
        for seed in (1, 2):
            plan = first_world(options, seed=seed).ctr_content_plan
            retail = [c for c in boxes(plan) if c["owner"].startswith("retail:")]
            self.assertEqual(len(retail), 787)
            for check in retail:
                track, _, slot = check["display_name"].rpartition(": Item Box ")
                boost, stats = item_boxes.BOX_RULES.get((track, int(slot)), (0, False))
                self.assertEqual(check.get("boost", 0), boost, check["display_name"])
                self.assertEqual(check.get("stats", False), stats, check["display_name"])


def dowlle_package(key):
    """A catalogue package of a CP1 track on the LEV its spots were placed on."""
    block, pin = DOWLLE_CUSTOM[key][:2]
    if key == "baby-t-park":
        return btp()
    package = btp()
    old = package["files"][0]["sha256"]
    package.update(content_id=key, display_name=box_spots.CUSTOM_FILES[key]["doc"]["track"]["name"],
                   id=f"package/{key}/1.0.0", revision="1.0.0", uuid=f"11111111-2222-4333-8444-{block:012d}")
    package["files"][0]["sha256"] = pin
    for evidence in package.get("evidence", []):
        evidence["file_hashes"] = [pin if h == old else h for h in evidence["file_hashes"]]
    return package


class TestDowlleCustomSpots(unittest.TestCase):
    """CP1: dowlle's 2026-11-24 placements on 21 named custom tracks. He ruled
    his placements boost 0 (2026-11-24); the spots his stream calls named need
    boost. Every spot is pinned to the LEV it was placed on."""

    def test_files_hold_the_spots_in_placement_order(self):
        total = 0
        for key, (block, pin, first, count, boost) in DOWLLE_CUSTOM.items():
            doc = box_spots.CUSTOM_FILES[key]["doc"]
            self.assertEqual(destinations.named_track(key).block_index, block, key)
            self.assertEqual(doc["track"]["lev_sha256"], [pin], key)
            new = [s for s in doc["spots"] if s.get("source") == DOWLLE_2026_11_24]
            self.assertEqual([s["number"] for s in new], list(range(first, first + count)), key)
            self.assertEqual(max(s["number"] for s in doc["spots"]), first + count - 1, key)
            self.assertLessEqual(first + count - 1, box_spots.MAX_NUMBER, key)
            older = [s for s in doc["spots"] if s.get("source") != DOWLLE_2026_11_24]
            self.assertTrue(all(s["number"] < first for s in older), key)
            for spot in new:
                self.assertEqual(spot["needs"], "boost" if spot["number"] in boost else "none", (key, spot["number"]))
                self.assertNotIn("shortcut", spot)
                self.assertTrue(spot["review"].startswith("CP1 ground map: "), (key, spot["number"]))
                self.assertEqual("note" in spot, spot["number"] in boost, (key, spot["number"]))
                if spot["number"] in boost:
                    self.assertTrue(spot["note"].startswith("dowlle's stream call at "), (key, spot["number"]))
            total += count
        self.assertEqual(total, 534)
        self.assertEqual(sum(len(v[4]) for v in DOWLLE_CUSTOM.values()), 14)

    def test_seeds_stand_the_boxes_and_stay_completable(self):
        """Every CP1 track in a filled seed at Item Box Count 15 and 50: the
        picked spots are the file's, boost spots carry boost, and every
        location is reachable."""
        keys = sorted(DOWLLE_CUSTOM)
        groups = [keys[i::3] for i in range(3)]
        for count in (15, 50):
            for group in groups:
                with self.subTest(count=count, group=group):
                    options = box_options(custom=[dowlle_package(k) for k in group], tier="hard",
                                          item_box_count=count, progressive_boost="shared_global",
                                          accessibility="full")
                    world = first_world(options, seed=count)
                    plan = world.ctr_content_plan
                    self.assertFalse(refused(plan))
                    for key in group:
                        block, pin, first, n, boost = DOWLLE_CUSTOM[key]
                        track_id = next(t["id"] for t in plan["tracks"] if t.get("named_block") == block)
                        record = spot_set(plan, track_id)
                        self.assertEqual(record["lev_sha256"], pin)
                        pool = len(box_spots.CUSTOM_FILES[key]["doc"]["spots"])
                        self.assertEqual((record["pool"], len(record["picked"])), (pool, min(count, pool)))
                        spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES[key])
                        for check in boxes(plan, track_id):
                            m = check["spot"]["number"]
                            self.assertEqual(check["spot"], box_spots.wire_spot(spots[m]))
                            self.assertEqual(check["location"], named_tracks.location_code(block, f"item_box_{m}"))
                            self.assertEqual(check.get("boost", 0), box_spots.needs_rank(spots[m]))
                    distribute_items_restrictive(world.multiworld)
                    self.assertTrue(world.multiworld.fulfills_accessibility(CollectionState(world.multiworld)))
