"""Named custom-track id blocks (#306, path C): id math, freeze, collisions.

The shipped data file has no tracks in phase 1. The fixture rows under
test/fixtures/named_tracks_fixture.json are TEST DATA ONLY: they exercise the
mechanism and are never shipped names.
"""
import copy
import json
import os
import pkgutil
import subprocess
import unittest
from unittest.mock import patch

from .. import ctrAPWorld, destinations, named_tracks as nt
from ..cortex_vortex_track import CORTEX_VORTEX, letter_item_name, letter_location_name, relic_name
from ..destinations import NamedTrack, parse_named_tracks
from ..Locations import CTR_LOCATION_CLASSES
from ..podium import PODIUM_CLASS, SLOT_ORDER


def fixture_document():
    return nt.load_fixture_document()


def fixture_tracks():
    return parse_named_tracks(fixture_document())


def lock_document():
    return json.loads(pkgutil.get_data("worlds.ctr", "test/fixtures/named_tracks_lock.json"))


def parse_lock_tracks(document):
    return [NamedTrack(row["track_key"], row["block_index"], row["ap_name"])
            for row in document["tracks"]]


def published_baseline():
    """The last published lock, independent of this branch's own lock file.

    CI writes the PR base's copy to CTR_NAMED_LOCK_BASELINE. Locally the same
    file is read from the first of the base refs git knows. None when neither
    exists (the PR that introduces the lock has nothing older to compare to).
    """
    path = os.environ.get("CTR_NAMED_LOCK_BASELINE")
    if path:
        if not os.path.exists(path) or not os.path.getsize(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    for ref in ("origin/dev/custom-pad-0.3.0", "origin/main"):
        shown = subprocess.run(
            ["git", "-C", root, "show", f"{ref}:worlds/ctr/test/fixtures/named_tracks_lock.json"],
            capture_output=True, text=True)
        if shown.returncode == 0 and shown.stdout.strip():
            return json.loads(shown.stdout)
    return None


def live_ids():
    named_locations = set(nt.NAMED_TRACK_CLASS.names())
    named_items = {row["name"] for row in nt.NAMED_TRACK_ITEM_DATA}
    return ({n: c for n, c in ctrAPWorld.location_name_to_id.items() if n not in named_locations},
            {n: c for n, c in ctrAPWorld.item_name_to_id.items() if n not in named_items})


class TestIdMath(unittest.TestCase):
    def test_bases_budgets_and_ranges(self):
        self.assertEqual((nt.NAMED_LOCATION_BASE, nt.LOCATION_BUDGET), (35200000, 200))
        self.assertEqual((nt.NAMED_ITEM_BASE, nt.ITEM_BUDGET), (35100000, 5))
        self.assertEqual(nt.NAMED_LOCATION_RANGE, (35200000, 37199999))
        self.assertEqual(nt.NAMED_ITEM_RANGE, (35100000, 35149999))

    def test_codes(self):
        self.assertEqual(nt.location_code(0, "trophy"), 35200000)
        self.assertEqual(nt.location_code(0, "wumpa"), 35200014)
        self.assertEqual(nt.location_code(1, "trophy"), 35200200)
        self.assertEqual(nt.location_code(9999, "trophy"), 37199800)
        self.assertEqual(nt.item_code(0, "letter_c"), 35100000)
        self.assertEqual(nt.item_code(2, "letter_r"), 35100012)
        self.assertEqual(nt.item_code(9999, "letter_r"), 35149997)
        self.assertEqual(nt.block_of_location(35200413), (2, 13))
        self.assertIsNone(nt.block_of_location(35026000))

    def test_invalid_block_cannot_alias(self):
        for bad in (-1, 10000, True, 1.0, "1", None):
            with self.subTest(block=bad), self.assertRaises(ValueError):
                nt.location_code(bad, "trophy")
            with self.subTest(block=bad), self.assertRaises(ValueError):
                nt.item_code(bad, "letter_c")
        with self.assertRaises(KeyError):
            nt.location_code(0, "unknown")

    def test_spellings_match_cortex_vortex_and_podium(self):
        stem = "Track"
        cv = {
            "trophy": f"{CORTEX_VORTEX}: Trophy Race",
            "ctr_token": f"{CORTEX_VORTEX}: CTR Token Challenge",
            "relic_sapphire": relic_name("Sapphire"), "relic_gold": relic_name("Gold"),
            "relic_platinum": relic_name("Platinum"),
            "letter_c": letter_location_name("C"), "letter_t": letter_location_name("T"),
            "letter_r": letter_location_name("R"),
        }
        for key, name in cv.items():
            self.assertEqual(nt.location_name(CORTEX_VORTEX, key), name)
        for rung in SLOT_ORDER:
            self.assertEqual(nt.location_name(stem, rung), PODIUM_CLASS.location_name(stem, rung))
        for key, letter in (("letter_c", "C"), ("letter_t", "T"), ("letter_r", "R")):
            self.assertEqual(nt.item_name(CORTEX_VORTEX, key), letter_item_name(letter))


class TestFreeze(unittest.TestCase):
    def test_layout_is_append_only(self):
        self.assertEqual(nt.layout_violations(lock_document()["layout"]), [])
        moved = copy.deepcopy(lock_document()["layout"])
        moved["locations"][0][2] = "Trophy"
        self.assertTrue(nt.layout_violations(moved))
        shorter = copy.deepcopy(lock_document()["layout"])
        shorter["items"] = shorter["items"][:2]
        self.assertEqual(nt.layout_violations(shorter), [], "a lock may predate an append")

    def test_shipped_rows_match_the_committed_lock(self):
        lock = lock_document()
        self.assertEqual(nt.freeze_violations(lock["tracks"], destinations.NAMED_TRACKS), [])
        self.assertEqual(lock, json.loads(nt.lock_document_text(destinations.NAMED_TRACKS)),
                         "regenerate test/fixtures/named_tracks_lock.json with "
                         "`python -m worlds.ctr.named_tracks --print-lock` and review it")

    def test_shipped_rows_match_the_published_baseline(self):
        """The lock above lives in this branch, so regenerating it hides a
        change. The baseline is the lock as last published (the PR base or the
        previous commit), fetched by CI into CTR_NAMED_LOCK_BASELINE or read
        from git locally. A shipped name, id or layout row can never change."""
        baseline = published_baseline()
        if baseline is None:
            self.skipTest("no published baseline lock available (first introduction or no git ref)")
        self.assertEqual(nt.freeze_violations(baseline["tracks"], destinations.NAMED_TRACKS), [])
        self.assertEqual(nt.layout_violations(baseline["layout"]), [])
        in_lock = parse_lock_tracks(lock_document())
        self.assertEqual(nt.freeze_violations(baseline["tracks"], in_lock), [],
                         "the committed lock rewrote a published row")

    def test_regenerated_lock_cannot_hide_a_rename(self):
        published = list(fixture_tracks())
        baseline = nt.lock_rows(published)
        renamed = [NamedTrack(t.track_key, t.block_index, t.ap_name + " X")
                   if t.block_index == 0 else t for t in published]
        regenerated = json.loads(nt.lock_document_text(renamed))
        self.assertEqual(nt.freeze_violations(regenerated["tracks"], renamed), [],
                         "the in-branch lock check alone is satisfied")
        self.assertTrue(nt.freeze_violations(baseline, parse_lock_tracks(regenerated)),
                        "the published baseline catches it")

    def test_append_passes_and_every_change_fails(self):
        tracks = list(fixture_tracks())
        frozen = nt.lock_rows(tracks)
        self.assertEqual(nt.freeze_violations(frozen, tracks), [])
        appended = tracks + [NamedTrack("fixture-new", 3, "Fixture New Track")]
        self.assertEqual(nt.freeze_violations(frozen, appended), [])
        cases = {
            "renamed": [NamedTrack(t.track_key, t.block_index, t.ap_name + " X")
                        if t.block_index == 0 else t for t in tracks],
            "moved": [NamedTrack(t.track_key, 7, t.ap_name) if t.block_index == 0 else t
                      for t in tracks],
            "removed": tracks[1:],
            "swapped": [NamedTrack(tracks[1].track_key, 0, tracks[0].ap_name),
                        NamedTrack(tracks[0].track_key, 1, tracks[1].ap_name), tracks[2]],
        }
        for label, current in cases.items():
            with self.subTest(case=label):
                self.assertTrue(nt.freeze_violations(frozen, current), label)
        # A new block may not fill a gap below the highest frozen block.
        gap = nt.lock_rows([tracks[0], tracks[2]])
        self.assertTrue(nt.freeze_violations(
            gap, [tracks[0], tracks[2], NamedTrack("fixture-low", 1, "Fixture Low")]))

    def test_a_layout_append_keeps_shipped_codes(self):
        frozen = nt.lock_rows(fixture_tracks())
        grown = nt.LOCATION_OFFSETS + (("ap_box_1", 31, "AP Box 1"),)
        with patch.object(nt, "LOCATION_OFFSETS", grown), \
                patch.dict(nt._LOCATION_OFFSET, {"ap_box_1": (31, "AP Box 1")}):
            self.assertEqual(nt.freeze_violations(frozen, fixture_tracks()), [])


class TestRegistryRows(unittest.TestCase):
    def test_fixture_is_marked_test_data_and_not_shipped(self):
        self.assertIn("TEST DATA ONLY", fixture_document()["test_data"])
        shipped = json.loads(pkgutil.get_data("worlds.ctr", destinations.NAMED_TRACKS_FILE))
        self.assertNotIn("test_data", shipped)
        self.assertEqual(shipped["tracks"], [], "phase 1 mints no named block")
        self.assertEqual(destinations.NAMED_TRACKS, ())
        self.assertEqual(nt.NAMED_TRACK_CLASS.all_locations(), [])
        self.assertEqual(nt.NAMED_TRACK_ITEM_DATA, ())

    def test_fixture_family_is_complete_and_collision_free(self):
        tracks = fixture_tracks()
        locations, items = live_ids()
        nt.validate_tracks(tracks, locations, items)
        cls = nt.NamedTrackLocationClass(tracks)
        rows = cls.all_locations()
        self.assertEqual(len(rows), len(tracks) * len(nt.LOCATION_OFFSETS))
        self.assertIn(("Fixture Speedway: Trophy Race", 35200000, "Fixture Speedway"), rows)
        self.assertIn(("Crash Cove (Custom): Letter R", 35200213, "Crash Cove (Custom)"), rows)
        self.assertEqual(cls.code_blocks, (35200000,))
        self.assertEqual(nt.item_data(tracks)[0]["name"], "Letter C (Fixture Speedway)")
        for _name, code, _region in rows:
            for first, last, label in nt.RESERVED_ID_RANGES:
                self.assertFalse(first <= code <= last, label)

    def test_fixture_registers_beside_every_live_class(self):
        # The full registry with the fixture class appended must accept it:
        # no name or code is shared with any registered class.
        from ..location_class import LocationClassRegistry
        registry = LocationClassRegistry()
        for location_class in CTR_LOCATION_CLASSES:
            if location_class.key != "named_track":
                registry.register(location_class)
        registry.register(nt.NamedTrackLocationClass(fixture_tracks()))

    def test_named_ranges_clear_every_reservation(self):
        for first, last, label in nt.RESERVED_ID_RANGES:
            for lo, hi in (nt.NAMED_LOCATION_RANGE, nt.NAMED_ITEM_RANGE):
                self.assertTrue(last < lo or first > hi, label)
        # Named ids belong to their own ranges; every other live id must sit in
        # the reservation table. Pinning the registry export mints named ids,
        # so the two sets are checked separately.
        named_locations = set(nt.NAMED_TRACK_CLASS.names())
        named_items = {row["name"] for row in nt.NAMED_TRACK_ITEM_DATA}
        for name, code in ctrAPWorld.location_name_to_id.items():
            if name in named_locations:
                self.assertTrue(nt.NAMED_LOCATION_RANGE[0] <= code <= nt.NAMED_LOCATION_RANGE[1],
                                f"named location {name!r} has {code} outside its range")
        for name, code in ctrAPWorld.item_name_to_id.items():
            if name in named_items:
                self.assertTrue(nt.NAMED_ITEM_RANGE[0] <= code <= nt.NAMED_ITEM_RANGE[1],
                                f"named item {name!r} has {code} outside its range")
        other_locations, other_items = live_ids()
        for code in list(other_locations.values()) + list(other_items.values()):
            self.assertTrue(any(first <= code <= last for first, last, _ in nt.RESERVED_ID_RANGES),
                            f"live code {code} is outside the reservation table; add its range")

    def test_collisions_are_refused(self):
        locations, items = live_ids()
        base = fixture_tracks()
        with self.assertRaises(ValueError):  # a retail stem without "(Custom)"
            nt.validate_tracks([NamedTrack("x", 5, "Wumpa")], locations, items)
        with self.assertRaises(ValueError):  # not a sanitized title
            nt.validate_tracks([NamedTrack("x", 5, "Bad [Name]")], locations, items)
        with self.assertRaises(ValueError):  # a live name inside the family
            nt.validate_tracks(base, {**locations, "Fixture Speedway: Trophy Race": 1}, items)
        with self.assertRaises(ValueError):  # a live code inside a named block
            nt.validate_tracks(base, {**locations, "Stray": 35200001}, items)
        with self.assertRaises(ValueError):
            nt.validate_tracks(base, locations, {**items, "Stray": 35100003})

    def test_malformed_rows_are_refused(self):
        good = fixture_document()
        mutations = {
            "format": lambda d: d.update(format=2),
            "unknown top": lambda d: d.update(extra=1),
            "unknown row": lambda d: d["tracks"][0].update(extra=1),
            "duplicate block": lambda d: d["tracks"][1].update(block_index=0),
            "duplicate key": lambda d: d["tracks"][1].update(track_key="baby-t-park"),
            "duplicate name": lambda d: d["tracks"][1].update(ap_name="fixture speedway"),
            "block range": lambda d: d["tracks"][0].update(block_index=10000),
            "bool block": lambda d: d["tracks"][0].update(block_index=True),
            "key chars": lambda d: d["tracks"][0].update(track_key="Baby T"),
            "retail name": lambda d: d["tracks"][1].update(ap_name="Crash Cove"),
            "padded name": lambda d: d["tracks"][0].update(ap_name=" Fixture"),
        }
        for label, mutate in mutations.items():
            document = copy.deepcopy(good)
            mutate(document)
            with self.subTest(case=label), self.assertRaises(ValueError):
                parse_named_tracks(document)
