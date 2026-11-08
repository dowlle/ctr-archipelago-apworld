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

from .. import box_spots, content_item_boxes, content_plan, crate_exclusions, destinations, item_boxes, named_tracks
from ..Locations import CTR_LOCATION_IDS
from .test_content_item_boxes import BTP_ID, LOOP_ID, box_options, boxes, btp, first_world, refused
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN

FIXTURES = "test/fixtures/"
CRASH_COVE = 3
#: The reviewed community files (A3-45): track key -> (named block, LEV pin of
#: the package revision in the shared YAMLs, spots that need more than none).
COMMUNITY = {
    "ancient-lake": (1, "21e1ffe395f1d5d0a2c4538050d18912577a4dd783026fa9caea8b09ad8d3aee", {2: "boost"}),
    "dk-pass": (25, "cf29d61f8e7b9a5d210a060ffbc4da22b04483d25d85c6a01bff855f312c09ef", {}),
}


def fixture(path):
    return json.loads(pkgutil.get_data(box_spots.__package__, FIXTURES + path).decode("utf-8"))


def entry(path):
    raw = pkgutil.get_data(box_spots.__package__, FIXTURES + path)
    return dict(doc=box_spots.check_file(json.loads(raw.decode("utf-8")), path), path=path,
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
        self.assertEqual(item_boxes.SK_REQUIRED_TIER, {(t, n): v for t, n, v in frozen["sk_required_tier"]})
        self.assertEqual(item_boxes.BOX_RULES, {(t, n): (b, s) for t, n, b, s in frozen["box_rules"]})
        self.assertEqual(item_boxes.EXPLICIT_NO_GATE, frozenset((t, n) for t, n in frozen["explicit_no_gate"]))
        self.assertEqual(list(item_boxes.TIGER_TEMPLE_DOOR_BOXES), [tuple(k) for k in frozen["tiger_temple_door"]])

    def test_files_match_the_shared_coordinate_fixture(self):
        rows = sorted([doc["track"]["level_id"], s["number"], *s["pos"], s["rot_y"]]
                      for doc in (e["doc"] for e in box_spots.RETAIL_FILES.values())
                      for s in doc["spots"] if s.get("source") == "builtin")
        self.assertEqual(rows, fixture("box_spots_builtin_rows.json")["rows"])
        self.assertEqual(len(rows), 241)

    def test_shipped_files_are_the_18_retail_tracks_and_the_reviewed_custom_files(self):
        self.assertEqual(sorted(box_spots.RETAIL_FILES), list(range(18)))
        self.assertEqual(sorted(box_spots.CUSTOM_FILES), sorted(COMMUNITY))
        for e in box_spots.RETAIL_FILES.values():
            self.assertTrue(all(s.get("source") == "builtin" for s in e["doc"]["spots"]), e["path"])
            self.assertEqual(e["doc"]["retired"], [], e["path"])

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
            box_spots.check_file(doc)

    def test_good_file(self):
        self.assertIs(box_spots.check_file(copy.deepcopy(self.BASE))["version"], 1)

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
            with patch:
                world = first_world(options, seed=11)
                distribute_items_restrictive(world.multiworld)
            placements.append(sorted((loc.name, loc.item.name) for loc in world.multiworld.get_locations()
                                     if loc.item is not None))
            if legacy:
                self.assertNotIn("spot_sets", world.ctr_content_plan["item_boxes"])
        self.assertEqual(placements[0], placements[1])

    def test_a_record_without_spot_sets_still_validates(self):
        """An alpha2-era plan (no spot sets, no spot fields) is still read."""
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
    """The first reviewed community files: DK Pass and Ancient Lake (A3-45)."""

    def test_files_are_reviewed_named_track_files(self):
        for key, (block, pin, needs) in COMMUNITY.items():
            doc = box_spots.CUSTOM_FILES[key]["doc"]
            self.assertEqual(destinations.named_track(key).block_index, block)
            self.assertEqual(doc["track"]["lev_sha256"], [pin])
            self.assertEqual([s["number"] for s in doc["spots"]], list(range(1, 16)))
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
            self.assertEqual((record["pool"], record["picked"]), (15, list(range(1, 16))))
            spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES[key])
            own = boxes(plan, track_id)
            self.assertEqual([c["spot"]["number"] for c in own], list(range(1, 16)))
            for check in own:
                n = check["spot"]["number"]
                self.assertEqual(check["spot"], box_spots.wire_spot(spots[n]))
                self.assertEqual(check["location"], named_tracks.location_code(block, f"item_box_{n}"))
                self.assertEqual(check.get("boost", 0), box_spots.NEEDS[needs.get(n, "none")])
        self.assertFalse(refused(plan))

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
