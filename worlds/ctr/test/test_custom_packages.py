"""Open package admission for content-plan custom tracks (#133 PR 2).

Descriptors are untrusted player input: every field is bounded and a malformed
descriptor is refused with a message naming the field. The paired native parser
applies the same rules (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest
from unittest.mock import patch

from Options import OptionError

from .. import box_spots, content_plan, custom_packages, destinations, named_tracks
from .test_content_plan import make_world, profile_options

#: Test data only: a track key with no named block, so it takes path B+.
UNKNOWN = dict(id="package/fixture-loop/2.1", content_id="fixture-loop",
               uuid="0f0e0d0c-0b0a-4908-8706-050403020100", revision="2.1",
               display_name="Fixture Loop", author="Fixture Author", laps=3,
               capabilities=dict(time_trial=True, arcade=True, relic=True, ctr_tokens=False, wumpa=False),
               relic_targets=dict(sapphire=96000, gold=86400, platinum=76800),
               files=[dict(role="lev", sha256="a1" * 32, bytes=1234567, format="ctr-lev", format_version=1),
                      dict(role="vrm", sha256="b2" * 32, bytes=458808, format="ctr-vrm", format_version=1)],
               evidence=[])


def named_fixture():
    """Test data on a real named key (TV World, block 78) with made-up pins."""
    d = copy.deepcopy(UNKNOWN)
    d.update(id="package/tv-world/1.1.0", content_id="tv-world", revision="1.1.0",
             uuid="54532a25-e512-53a5-a74e-98a5d74a4c9f", display_name="TV World", laps=5)
    d["capabilities"].update(relic=False)
    del d["relic_targets"]
    d["files"][0]["sha256"] = "c3" * 32
    d["files"][1]["sha256"] = "d4" * 32
    return d


def options_with(custom, required=None):
    options = profile_options()
    options["content_pool"]["tracks"]["custom"] = custom
    options["content_pool"]["required_entries"] = (
        required if required is not None else [f"custom/{d['content_id']}/{d['revision']}" for d in custom])
    return options


class TestAdmission(unittest.TestCase):
    def test_alias_for_a_builtin_has_identity_without_a_custom_block(self):
        key = "lockbox-adventure-track-11"
        self.assertEqual(destinations.canonical_track_key(key), "cortex-vortex")
        self.assertIsNone(destinations.named_track(key))

    def test_historical_key_uses_the_canonical_block_for_new_rooms(self):
        alias, key = "n-gage-assembly-lane", "assembly-lane-n-gage"
        descriptor = copy.deepcopy(UNKNOWN)
        descriptor.update(content_id=alias, id=f"package/{alias}/{descriptor['revision']}",
                          display_name="N-Gage Assembly Lane")
        options = options_with([descriptor])
        block = destinations.named_track(key)
        self.assertIs(destinations.named_track(alias), block)
        world = make_world(options, seed=3)
        track = next(t for t in world.ctr_content_plan["tracks"] if t.get("package_id") == descriptor["id"])
        self.assertEqual((track["named_block"], track["room_title"]), (block.block_index, block.ap_name))
        self.assertEqual(world.ctr_content_plan["packages"][0]["content_id"], alias)
        tracker = make_world(options, passthrough=world.fill_slot_data())
        tracker.generate_basic()
        address = named_tracks.location_code(block.block_index, "trophy")
        self.assertEqual(tracker.location_id_to_name[address], block.ap_name + ": Trophy Race")

        options["content_pool"]["required_entries"] = [key]
        options["content_pool"]["tracks"]["overrides"] = {key: ["trophy"]}
        alias_world = make_world(options, seed=3)
        alias_track = next(t for t in alias_world.ctr_content_plan["tracks"] if t.get("package_id") == descriptor["id"])
        self.assertEqual(alias_track["modes"], ["trophy"])
        options = options_with([descriptor])

        with patch.dict(destinations.TRACK_KEY_ALIASES, {}, clear=True):
            old_world = make_world(options, seed=3)
            wire = old_world.fill_slot_data()
            track = next(t for t in wire["content_plan"]["tracks"] if t.get("package_id") == descriptor["id"])
            self.assertNotIn("named_block", track)
            saved = next(c for c in wire["content_plan"]["checks"] if c["owner"] == track["id"])
        restored = make_world(options, passthrough=wire)
        restored.generate_basic()
        self.assertEqual(restored.location_id_to_name[saved["location"]], saved["display_name"])

        canonical = copy.deepcopy(descriptor)
        canonical.update(content_id=key, id=f"package/{key}/{canonical['revision']}")
        with self.assertRaisesRegex(custom_packages.PackageError, "repeats the track key"):
            custom_packages.admit_all([descriptor, canonical])

    def test_alias_does_not_grant_box_spots_without_the_lev_pin(self):
        key = "gossamer-s-castle"
        track = {"origin": "custom", "named_block": destinations.named_track(key).block_index}
        package = copy.deepcopy(UNKNOWN)
        package["content_id"] = "boss-race-2"
        self.assertIsNone(box_spots.file_for(track, package))
        entry = box_spots.CUSTOM_FILES[key]
        package["files"][0]["sha256"] = entry["doc"]["track"]["lev_sha256"][0]
        self.assertIs(box_spots.file_for(track, package), entry)

    def test_yaml_keeps_first_copy_and_transfers_unshared_selectors(self):
        first = named_fixture()
        first.update(content_id="release-st-patrick-adventure-slot-55",
                     id="package/release-st-patrick-adventure-slot-55/1.1.0",
                     display_name="Old St. Patrick Title")
        second = named_fixture()
        second.update(content_id="coco-park-2025", id="package/coco-park-2025/1.1.0",
                      display_name="Old Anniversary Title")
        second["files"][0]["sha256"] = "ab" * 32
        for chosen, removed in ((first, second), (second, first)):
            options = options_with([chosen, removed], required=[removed["display_name"]])
            options["content_pool"]["tracks"]["overrides"] = {removed["display_name"]: ["trophy"]}
            world = make_world(options, seed=3)
            plan = world.ctr_content_plan
            self.assertEqual(plan["packages"], [chosen])
            track = next(t for t in plan["tracks"] if t.get("package_id") == chosen["id"])
            self.assertEqual((track["named_block"], track["room_title"], track["modes"]),
                             (15, "Coco Park 2025", ["trophy"]))
            self.assertEqual(world.ctr_duplicate_track_count, 1)

        options = options_with([first, second], required=[second["display_name"]])
        options["content_pool"]["tracks"]["overrides"] = {
            second["display_name"]: ["relic"],
            "coco-park-2025": ["trophy"],
        }
        plan = make_world(options, seed=3).ctr_content_plan
        track = next(t for t in plan["tracks"] if t.get("package_id") == first["id"])
        self.assertEqual(track["modes"], ["trophy"])

        third = copy.deepcopy(UNKNOWN)
        third["display_name"] = first["content_id"]
        first["capabilities"]["relic"] = True
        first["relic_targets"] = UNKNOWN["relic_targets"]
        options = options_with([first, second, third], required=[second["display_name"]])
        options["content_pool"]["tracks"]["overrides"] = {second["display_name"]: ["relic"]}
        world = make_world(options, seed=3)
        plan = world.ctr_content_plan
        self.assertEqual(content_plan.required_ids(world.options, plan["tracks"], [],
                                                   {p["id"]: p for p in plan["packages"]},
                                                   world.ctr_transferred_track_selectors.items()),
                         [content_plan.package_track_id(first)])
        modes = {t.get("package_id"): t["modes"] for t in plan["tracks"]}
        self.assertEqual(modes[first["id"]], ["relic"])
        self.assertEqual(modes[third["id"]], ["trophy"])

        fourth = dict(third, display_name=second["display_name"])
        options = options_with([first, second, third, fourth], required=[second["display_name"]])
        with self.assertRaisesRegex(OptionError, "not a track or arena.*Old Anniversary Title"):
            make_world(options, seed=3)

        first["capabilities"]["relic"] = False
        del first["relic_targets"]
        options = options_with([first, second], required=[second["display_name"]])
        options["content_pool"]["tracks"]["overrides"] = {second["display_name"]: ["relic"]}
        plan = make_world(options, seed=3).ctr_content_plan
        self.assertEqual(next(t["modes"] for t in plan["tracks"] if t.get("package_id") == first["id"]), ["trophy"])

        options["content_pool"]["tracks"]["overrides"][second["display_name"]] = ["bogus"]
        with self.assertRaisesRegex(OptionError, "nonempty list of distinct races"):
            make_world(options, seed=3)
        options["content_pool"]["tracks"]["overrides"] = {}
        options["content_pool"]["required_entries"] *= 2
        with self.assertRaisesRegex(OptionError, "listed more than once|lists these selectors more than once"):
            make_world(options, seed=3)

    def test_asteroid_legacy_alias_dedup_preserves_the_first_descriptor(self):
        first = copy.deepcopy(UNKNOWN)
        key = "release-st-patrick-adventure-track-1"
        first.update(content_id=key, id=f"package/{key}/2.1")
        second = copy.deepcopy(first)
        key = "lego-alien-rally-asteroid"
        second.update(content_id=key, id=f"package/{key}/2.1")
        plan = make_world(options_with([first, second]), seed=3).ctr_content_plan
        self.assertEqual(plan["packages"], [first])
        self.assertIsNone(destinations.named_track(key))

    def test_literal_selector_keeps_precedence_over_another_tracks_alias(self):
        alias, key = "n-gage-assembly-lane", "assembly-lane-n-gage"
        other = copy.deepcopy(UNKNOWN)
        other["display_name"] = alias
        canonical = named_fixture()
        canonical.update(content_id=key, id=f"package/{key}/{canonical['revision']}",
                         display_name="Assembly Lane N-Gage")
        options = options_with([other, canonical], required=[alias])
        options["content_pool"]["tracks"]["overrides"] = {alias: ["relic"]}
        world = make_world(options, seed=3)
        plan = world.ctr_content_plan
        self.assertEqual(content_plan.required_ids(world.options, plan["tracks"], [],
                                                   {p["id"]: p for p in plan["packages"]}), ["custom/fixture-loop/2.1"])
        modes = {track.get("package_id"): track["modes"] for track in plan["tracks"]}
        self.assertEqual(modes[other["id"]], ["relic"])
        self.assertEqual(modes[canonical["id"]], ["trophy"])

    def test_older_rooms_keep_two_raw_keys_that_now_share_an_identity(self):
        first, second = copy.deepcopy(UNKNOWN), copy.deepcopy(UNKNOWN)
        first.update(content_id="crash-30anniversary-adventure-track-2",
                     id="package/crash-30anniversary-adventure-track-2/2.1", display_name="Archived One")
        second.update(content_id="crash-30anniversary-adventure-track-12",
                      id="package/crash-30anniversary-adventure-track-12/2.1", display_name="Archived Two",
                      uuid="1f0e0d0c-0b0a-4908-8706-050403020100")
        second["files"][0]["sha256"] = "f2" * 32
        options = options_with([first, second])
        with patch.dict(destinations.TRACK_KEY_ALIASES, {}, clear=True):
            old = make_world(options, seed=3).fill_slot_data()
        restored = make_world(options, passthrough=old)
        self.assertEqual(restored.ctr_content_plan["packages"], old["content_plan"]["packages"])
        with self.assertRaisesRegex(custom_packages.PackageError, "repeats the track key"):
            custom_packages.admit_all([first, second])

    def test_yaml_track_key_alias_preserves_package_wire_shape(self):
        modern = dict(UNKNOWN, track_key=UNKNOWN["content_id"])
        del modern["content_id"]
        self.assertEqual(content_plan.resolve_packages([modern]), [UNKNOWN])
        self.assertEqual(content_plan.resolve_packages([dict(modern, content_id=UNKNOWN["content_id"])]), [UNKNOWN])
        with self.assertRaisesRegex(OptionError, "track_key and content_id must match"):
            content_plan.resolve_packages([dict(modern, content_id="different")])
        with self.assertRaises(OptionError):
            content_plan.resolve_packages([modern], "content_plan.packages")

    def test_known_profiles_and_unknown_descriptors_admit(self):
        for descriptor in (*content_plan.PACKAGES, UNKNOWN, named_fixture()):
            with self.subTest(descriptor=descriptor["id"]):
                self.assertEqual(custom_packages.admit(copy.deepcopy(descriptor)), descriptor)

    def refused(self, mutate, field):
        descriptor = copy.deepcopy(UNKNOWN)
        mutate(descriptor)
        with self.assertRaises(custom_packages.PackageError) as caught:
            custom_packages.admit(descriptor)
        self.assertIn(field, str(caught.exception))

    def test_every_field_is_closed_and_bounded(self):
        def set_(path, value):
            def change(d):
                target = d
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
            return change
        cases = [
            (set_(["id"], "package/other/2.1"), "package.id"),
            (set_(["content_id"], "Fixture-Loop"), "content_id"),
            (set_(["content_id"], "fixture_loop"), "content_id"),
            (set_(["content_id"], "-fixture"), "content_id"),
            (set_(["content_id"], "x" * 60), "too long"),
            (set_(["content_id"], 7), "content_id"),
            (set_(["revision"], 2.1), "revision"),
            (set_(["revision"], ".1"), "revision"),
            (set_(["uuid"], UNKNOWN["uuid"].upper()), "uuid"),
            (set_(["uuid"], "not-a-uuid"), "uuid"),
            (set_(["display_name"], "Fixture\nLoop"), "display_name"),
            (set_(["display_name"], ""), "display_name"),
            (set_(["display_name"], "é" * 65), "display_name"),
            (set_(["author"], "\x7f"), "author"),
            (set_(["author"], "Fixture \ud800"), "author"),
            (set_(["author"], None), "author"),
            (set_(["laps"], 0), "laps"),
            (set_(["laps"], 8), "laps"),
            (set_(["laps"], True), "laps"),
            (set_(["laps"], 3.0), "laps"),
            (set_(["laps"], "3"), "laps"),
            (set_(["capabilities", "arcade"], 1), "capabilities.arcade"),
            (set_(["capabilities", "boxes"], True), "capabilities"),
            (lambda d: d["capabilities"].pop("wumpa"), "capabilities"),
            (set_(["capabilities"], ["arcade"]), "capabilities"),
            (lambda d: d.pop("relic_targets"), "relic_targets"),
            (set_(["relic_targets", "gold"], 96000), "relic_targets"),
            (set_(["relic_targets", "platinum"], 0), "relic_targets.platinum"),
            (set_(["relic_targets", "sapphire"], 3456001), "relic_targets.sapphire"),
            (set_(["relic_targets", "extra"], 1), "relic_targets"),
            (set_(["files"], []), "files"),
            (lambda d: d["files"].reverse(), "files[0].role"),
            (lambda d: d["files"].append(copy.deepcopy(d["files"][1])), "files"),
            (set_(["files", 0, "sha256"], "A1" * 32), "files[0].sha256"),
            (set_(["files", 1, "sha256"], "b2" * 31), "files[1].sha256"),
            (set_(["files", 0, "bytes"], 0), "files[0].bytes"),
            (set_(["files", 0, "bytes"], 16 * 1024 * 1024 + 1), "files[0].bytes"),
            (set_(["files", 1, "bytes"], 4 * 1024 * 1024 + 1), "files[1].bytes"),
            (set_(["files", 1, "format"], "ctr-lev"), "files[1].format"),
            (set_(["files", 0, "format_version"], True), "files[0].format_version"),
            (set_(["files", 0, "path"], "x.lev"), "files[0]"),
            (set_(["evidence"], [dict(capability="arcade", file_hashes=["e5" * 32], verifier="v",
                                      revision=1, level="structural")]), "evidence[0].file_hashes"),
            (set_(["evidence"], [dict(capability="arcade", file_hashes=["a1" * 32], verifier="v",
                                      revision=1, level="measured")]), "evidence[0].level"),
            (set_(["evidence"], [dict(capability="arcade", file_hashes=["a1" * 32], verifier="v",
                                      revision=0, level="runtime")]), "evidence[0].revision"),
            (set_(["evidence"], [dict(capability="arcade", file_hashes=["a1" * 32], verifier="v",
                                      revision=1, level="runtime")] * 17), "evidence"),
            (set_(["evidence"], None), "evidence"),
            (set_(["source_url"], "https://example.invalid"), "unknown field source_url"),
            (lambda d: d.pop("laps"), "missing laps"),
        ]
        for mutate, field in cases:
            with self.subTest(field=field):
                self.refused(mutate, field)

    def test_lists_refuse_duplicates_and_oversize(self):
        twin = copy.deepcopy(UNKNOWN)
        twin.update(revision="2.2", id="package/fixture-loop/2.2")
        twin["files"][0]["sha256"] = "e5" * 32
        twin["uuid"] = "1f0e0d0c-0b0a-4908-8706-050403020100"
        with self.assertRaisesRegex(custom_packages.PackageError, "track key"):
            custom_packages.admit_all([UNKNOWN, twin])
        same_bytes = copy.deepcopy(named_fixture())
        same_bytes["files"] = copy.deepcopy(UNKNOWN["files"])
        with self.assertRaisesRegex(custom_packages.PackageError, "LEV and VRM pair"):
            custom_packages.admit_all([UNKNOWN, same_bytes])
        same_uuid = named_fixture()
        same_uuid["uuid"] = UNKNOWN["uuid"]
        with self.assertRaisesRegex(custom_packages.PackageError, "package uuid"):
            custom_packages.admit_all([UNKNOWN, same_uuid])
        with self.assertRaisesRegex(custom_packages.PackageError, "at most 132"):
            custom_packages.admit_all([UNKNOWN] * 133)
        with self.assertRaisesRegex(custom_packages.PackageError, "at most 132"):
            custom_packages.admit_all({"fixture-loop": UNKNOWN})


class TestOpenAdmissionGeneration(unittest.TestCase):
    def test_unknown_track_takes_path_b_plus_with_authored_laps(self):
        world = make_world(options_with([UNKNOWN]))
        plan = world.ctr_content_plan
        track = next(t for t in plan["tracks"] if t["origin"] == "custom")
        self.assertEqual(track["laps"], 3)
        self.assertNotIn("named_block", track)
        self.assertEqual(track["room_title"], "Fixture Loop")
        self.assertEqual(plan["packages"], [UNKNOWN])
        check = next(c for c in plan["checks"] if c["owner"] == track["id"])
        self.assertEqual(check["location"], 35016300)  # Custom Track 1: Trophy Race
        self.assertEqual(check["display_name"], "Fixture Loop: Trophy Race")
        names = {loc.address: loc.name for loc in world.multiworld.get_locations(1)}
        self.assertEqual(names[35016300], "Custom Track 1: Trophy Race")
        self.assertEqual(world.location_id_to_alias[35016300], "Fixture Loop: Trophy Race")
        self.assertTrue(content_plan.validate(plan))

    def test_named_key_uses_its_block_and_both_paths_coexist(self):
        world = make_world(options_with([named_fixture(), UNKNOWN]))
        plan = world.ctr_content_plan
        by_key = {t["package_id"]: t for t in plan["tracks"] if t["origin"] == "custom"}
        named = by_key["package/tv-world/1.1.0"]
        self.assertEqual((named["named_block"], named["room_title"], named["laps"]), (78, "TV World", 5))
        code = named_tracks.location_code(78, "trophy")
        self.assertIn(code, [c["location"] for c in plan["checks"]])
        names = {loc.address: loc.name for loc in world.multiworld.get_locations(1)}
        self.assertEqual(names[code], "TV World: Trophy Race")
        self.assertNotIn("named_block", by_key["package/fixture-loop/2.1"])
        # Slots follow the sorted package ids, so the B+ track is Custom Track 1.
        self.assertEqual(by_key["package/fixture-loop/2.1"]["custom_slot"], 1)

    def test_tracker_restores_open_packages_without_reroll(self):
        world = make_world(options_with([named_fixture(), UNKNOWN]), seed=7)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        tracker = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(tracker.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(tracker.fill_slot_data(), wire)

    def test_track_without_a_selected_mode_is_refused_not_dropped(self):
        descriptor = copy.deepcopy(UNKNOWN)
        descriptor["capabilities"]["arcade"] = False
        with self.assertRaisesRegex(OptionError, "can run none of the races"):
            make_world(options_with([descriptor]))

    def test_malformed_descriptor_names_the_field(self):
        descriptor = copy.deepcopy(UNKNOWN)
        descriptor["laps"] = 9
        with self.assertRaisesRegex(OptionError, r"custom_tracks\[0\]\.laps: 9 is outside 1 to 7"):
            make_world(options_with([descriptor]))

    def test_wire_forgery_is_refused(self):
        wire = make_world(options_with([named_fixture(), UNKNOWN]), seed=3).fill_slot_data()

        def custom_track(plan, key):
            return next(t for t in plan["tracks"] if t.get("package_id") == f"package/{key}")

        def laps_disagree(plan): custom_track(plan, "fixture-loop/2.1")["laps"] = 4
        def unsorted(plan): plan["packages"].reverse()
        def no_arcade(plan): plan["packages"][0]["capabilities"]["arcade"] = False
        def bad_pin(plan): plan["packages"][0]["files"][1]["bytes"] = 0
        def relic_without_targets(plan): plan["packages"][0].pop("relic_targets")
        def extra_field(plan): plan["packages"][1]["note"] = "x"
        def key_case(plan): plan["packages"][0]["content_id"] = "Fixture-loop"
        for mutate in (laps_disagree, unsorted, no_arcade, bad_pin, relic_without_targets, extra_field, key_case):
            forged = copy.deepcopy(wire)
            mutate(forged["content_plan"])
            with self.subTest(mutation=mutate.__name__), self.assertRaises(OptionError):
                make_world({}, passthrough=forged)


class TestTrackIdentityForgery(unittest.TestCase):
    """#133 PR 2 review: a forged plan cannot move a track between its named
    block and a generic slot, claim another track's block, or give a generic
    track a title that clashes in the room. Native refuses the same plans
    (native tools/test-content-plan-parity.py)."""

    @classmethod
    def setUpClass(cls):
        cls.plan = make_world(options_with([named_fixture(), UNKNOWN]), seed=3).ctr_content_plan

    def forged(self, change):
        plan = copy.deepcopy(self.plan)
        change(plan)
        plan["checks"].sort(key=lambda c: c["location"])
        return plan

    @staticmethod
    def track(plan, key):
        return next(t for t in plan["tracks"] if t.get("package_id", "").startswith(f"package/{key}/"))

    @staticmethod
    def check(plan, track):
        return next(c for c in plan["checks"] if c["owner"] == track["id"])

    def refuses(self, change, message):
        with self.assertRaisesRegex(OptionError, message):
            content_plan.validate(self.forged(change))

    def test_named_key_cannot_take_a_generic_slot(self):
        def change(plan):
            track = self.track(plan, "tv-world")
            del track["named_block"]
            self.check(plan, track)["location"] = 35016301  # Custom Track 2: Trophy Race
        self.refuses(change, "a track with a named block must use it")

    def test_unnamed_key_cannot_claim_another_block(self):
        north_pole = content_plan.destinations.named_track("north-pole")

        def change(plan):
            track = self.track(plan, "fixture-loop")
            track.update(named_block=north_pole.block_index, room_title=north_pole.ap_name)
            check = self.check(plan, track)
            check.update(location=named_tracks.location_code(north_pole.block_index, "trophy"),
                         display_name=north_pole.ap_name + ": Trophy Race")
        self.refuses(change, "named block does not match")

    def test_generic_room_title_cannot_clash(self):
        for title in ("Crash Cove", "TV World", "North Pole", "fixture loop", "Fixture Loop (Custom)"):
            def change(plan, title=title):
                track = self.track(plan, "fixture-loop")
                track["room_title"] = title
                self.check(plan, track)["display_name"] = title + ": Trophy Race"
            with self.subTest(title=title):
                self.refuses(change, "clash-suffixed title")

    def test_suffixed_titles_are_recomputed_per_seed(self):
        retail = copy.deepcopy(UNKNOWN)
        retail.update(display_name="Crash Cove")
        twin = copy.deepcopy(UNKNOWN)
        twin.update(id="package/fixture-twin/1", content_id="fixture-twin", revision="1",
                    uuid="1f0e0d0c-0b0a-4908-8706-050403020100", author="Other Author", display_name="Crash Cove")
        twin["files"][0]["sha256"] = "e5" * 32
        twin["files"][1]["sha256"] = "f6" * 32
        plan = make_world(options_with([retail, twin])).ctr_content_plan
        titles = {t["package_id"]: t["room_title"] for t in plan["tracks"] if t["origin"] == "custom"}
        self.assertEqual(titles, {"package/fixture-loop/2.1": "Crash Cove (Custom)",
                                  "package/fixture-twin/1": "Crash Cove (Custom, Other Author)"})
        self.assertTrue(content_plan.validate(plan))
        # A track the seed does not draw takes no name: alone, the second one
        # needs only the retail suffix.
        twin_track = next(t for t in plan["tracks"] if t.get("package_id") == "package/fixture-twin/1")
        self.assertEqual(content_plan.generic_room_titles([twin_track], {twin["id"]: twin}),
                         {twin_track["custom_slot"]: "Crash Cove (Custom)"})


class TestDocumentedFixture(unittest.TestCase):
    def test_documented_yaml_generates(self):
        import os
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "docs", "custom-track-example.yaml")
        with open(path, encoding="utf-8") as handle:
            options = yaml.safe_load(handle)["Crash Team Racing"]
        world = make_world(options)
        self.assertEqual(world.ctr_content_plan["packages"], [content_plan.PACKAGES[1]])
