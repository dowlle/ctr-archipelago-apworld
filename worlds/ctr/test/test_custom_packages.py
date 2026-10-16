"""Open package admission for content-plan custom tracks (#133 PR 2).

Descriptors are untrusted player input: every field is bounded and a malformed
descriptor is refused with a message naming the field. The paired native parser
applies the same rules (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from Options import OptionError

from .. import content_plan, custom_packages, named_tracks
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
        with self.assertRaisesRegex(custom_packages.PackageError, "at most 32"):
            custom_packages.admit_all([UNKNOWN] * 33)
        with self.assertRaisesRegex(custom_packages.PackageError, "at most 32"):
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

    def test_track_without_arcade_is_refused_not_dropped(self):
        descriptor = copy.deepcopy(UNKNOWN)
        descriptor["capabilities"]["arcade"] = False
        with self.assertRaisesRegex(OptionError, "arcade: false"):
            make_world(options_with([descriptor]))

    def test_malformed_descriptor_names_the_field(self):
        descriptor = copy.deepcopy(UNKNOWN)
        descriptor["laps"] = 9
        with self.assertRaisesRegex(OptionError, r"tracks\.custom\[0\]\.laps: 9 is outside 1 to 7"):
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
        path = os.path.join(os.path.dirname(__file__), "..", "docs", "experimental-content-plan.yaml")
        with open(path, encoding="utf-8") as handle:
            options = yaml.safe_load(handle)["Crash Team Racing"]
        world = make_world(options)
        self.assertEqual(world.ctr_content_plan["packages"], [content_plan.PACKAGES[1]])
