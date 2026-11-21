"""A4-52: TV World's upper-room crates, with stable identities."""
import copy
import json
import unittest
from unittest import mock

from BaseClasses import CollectionState
from Options import OptionError
from .. import content_capability, content_plan, object_rulings, sanity, track_rulings
from .test_content_plan import make_world
from .test_custom_packages import named_fixture
from .test_track_checks import check_options

TV = "custom/tv-world/1.1.0"
PIN = "e3d765e824a2de96d06d1f34951b6d2ab51c027fb3353c62d8e7086b8ce1e33a"


def options(difficulty="easy", blue=False, boost="shared_global", wumpa="crates"):
    package = named_fixture()
    package["files"][0]["sha256"] = PIN
    package["files"][1]["sha256"] = "b78491bf70e067e5149814c32a658e8e7ec99932d6c97ed0d5820f6403f456cc"
    package["capabilities"].update(weapon_crates=19, fruit_crates=9, loose_fruit=0, super_turbo_pads=True)
    opts = check_options(custom=[package], modes=("trophy",), stages="single", order="fixed", rungs=False)
    opts.update(wumpasanity=wumpa, itemboxsanity=50, item_box_count=0, progressive_boost=boost,
                progressive_boost_blue_fire=blue, logic_difficulty=difficulty,
                progressive_stats="off", character_unlocks=False, wumpa_shop_slots=0)
    return opts


class TestObjectRulings(unittest.TestCase):
    def test_all_settings_wire_reachability_and_tracker(self):
        for difficulty in ("easy", "medium", "hard"):
            for blue in (False, True):
                for boost in ("off", "shared_global", "per_character"):
                    with self.subTest(difficulty=difficulty, blue=blue, boost=boost):
                        world = make_world(options(difficulty, blue, boost), seed=52, stop_before="pre_fill")
                        plan = world.ctr_content_plan
                        row = next(r for r in plan["sanity"]["tracks"] if r["track_id"] == TV)
                        removed = difficulty != "hard" and not (blue and boost != "off")
                        self.assertEqual(row["wumpa_crate"], [1, 2, 7, 8, 9] if removed else list(range(1, 10)))
                        self.assertEqual(row["weapon_crate"], list(range(1, 20)))
                        checks = [c for c in plan["checks"] if c["owner"] == TV and c["kind"] in sanity.KINDS]
                        targets = [c for c in checks if c["location"] in range(37210066, 37210070)]
                        self.assertEqual(len(targets), 0 if removed else 4)
                        rank = 0 if boost == "off" else 2 if difficulty == "hard" else 3
                        for c in targets:
                            self.assertEqual(c.get("boost", 0), rank)
                        for c in checks:
                            if c not in targets:
                                self.assertNotIn("boost", c)
                        self.assertTrue(content_plan.validate(plan))
                        tracker = make_world(options(), passthrough=json.loads(json.dumps(world.fill_slot_data())),
                                             stop_before="pre_fill")
                        self.assertEqual(tracker.ctr_content_plan, plan)
                        # Physical check availability is independent of received boosts.
                        state = CollectionState(world.multiworld)
                        for item in world.multiworld.itempool:
                            if not item.name.startswith("Progressive Boost"):
                                state.collect(item, True)
                        boost_names = {i.name for i in world.multiworld.itempool if i.name.startswith("Progressive Boost")}
                        locations = {l.address: l for l in world.multiworld.get_locations(1)}
                        for held in range(4):
                            for c in targets:
                                self.assertEqual(locations[c["location"]].can_reach(state), held >= rank)
                            for name in boost_names:
                                state.collect(world.create_item(name), True)
                        forged = copy.deepcopy(plan)
                        if removed:
                            next(r for r in forged["sanity"]["tracks"] if r["track_id"] == TV)["wumpa_crate"].insert(2, 3)
                        elif rank:
                            next(c for c in forged["checks"] if c["location"] == targets[0]["location"])["boost"] = rank - 1
                        else:
                            continue
                        with self.assertRaises(OptionError):
                            content_plan.validate(forged)

    def test_scope_and_shortcut_independence(self):
        package = options()["content_pool"]["tracks"]["custom"][0]
        track = dict(origin="custom", named_block=78, id=TV)
        self.assertEqual(sanity.CATALOG[PIN]["needs"], {})
        for difficulty in range(3):
            for blue in (False, True):
                cap = dict(boost_mode=1, logic_difficulty=difficulty, boost_blue_fire=blue)
                for tier in range(3):
                    row = dict(shortcut_knowledge=tier)
                    picked = sanity.eligible(track, 1, row, None, package, cap)
                    self.assertEqual(picked, list(range(1, 10)) if difficulty == 2 or blue else [1, 2, 7, 8, 9])
                other = dict(package, content_id="other-tv-world")
                self.assertEqual(object_rulings.rank(track, other, "wumpa_crate", 3, cap), 0)
                self.assertEqual(object_rulings.rank(track, package, "weapon_crate", 3, cap), 0)
        names = sanity.SANITY_CLASS.name_to_code()
        for n in range(3, 7):
            self.assertEqual(names[f"TV World: Wumpa Crate {n}"], 37210064 + n - 1)

    def test_off_parity(self):
        for opts in (options(wumpa="off"), options(wumpa="fruit")):
            baseline = make_world(opts, seed=52).fill_slot_data()
            with mock.patch.dict(object_rulings.RULINGS, {}, clear=True):
                self.assertEqual(make_world(opts, seed=52).fill_slot_data(), baseline)

    def test_without_review_history_ruling_uses_exact_lev_and_older_room_restores(self):
        opts = options()
        package = opts["content_pool"]["tracks"]["custom"][0]
        package["files"][0]["sha256"] = "ab" * 32
        # Give the changed revision measured counts without giving it the ruling.
        with (mock.patch.dict(sanity.CATALOG, {"ab" * 32: dict(sanity.CATALOG[PIN], lev_sha256="ab" * 32)}),
              mock.patch.dict(track_rulings.REVIEWS, {"tv-world": []})):
            current = make_world(opts, seed=52, stop_before="pre_fill").ctr_content_plan
            row = next(r for r in current["sanity"]["tracks"] if r["track_id"] == TV)
            self.assertEqual(row["wumpa_crate"], list(range(1, 10)))
            self.assertNotIn("logic_difficulty", current["sanity"])
            # Recreate the picks an older, raw-key lookup wrote for this pin.
            legacy = {key: dict(rule, lev_sha256="ab" * 32) for key, rule in object_rulings.RULINGS.items()}
            with mock.patch.dict(object_rulings.RULINGS, legacy):
                old = make_world(opts, seed=52, stop_before="pre_fill").fill_slot_data()
            old_row = next(r for r in old["content_plan"]["sanity"]["tracks"] if r["track_id"] == TV)
            self.assertEqual(old_row["wumpa_crate"], [1, 2, 7, 8, 9])
            restored = make_world({}, passthrough=old, stop_before="pre_fill")
            self.assertEqual(restored.fill_slot_data(), old)

    def test_loader_refuses_invalid_rows(self):
        good = next(iter(object_rulings.RULINGS.values()))
        self.assertEqual(len(object_rulings.RULINGS), 4)
        for rows in ([good, good], [dict(good, ordinal=True)], [dict(good, hard_rank=3)],
                     [dict(good, blue_fire_rank=2)], [dict(good, ruling="undated")], [dict(good, kind="letter")]):
            with mock.patch.object(object_rulings.pkgutil, "get_data", return_value=json.dumps(
                    dict(version=1, rulings=rows)).encode()), self.assertRaises(ValueError):
                object_rulings._load()

    def test_exact_review_can_clear_an_unscoped_ruling(self):
        good = next(iter(object_rulings.RULINGS.values()))
        reviewed = dict(good, revision="9.0.0", lev_sha256=PIN, hard_rank=0, blue_fire_rank=0, since=2)
        with mock.patch.object(object_rulings.pkgutil, "get_data", return_value=json.dumps(
                dict(version=1, rulings=[good, reviewed])).encode()):
            rulings = object_rulings._load()
        package = dict(named_fixture(), revision="9.0.0", files=[dict(role="lev", sha256=PIN)])
        with mock.patch.object(object_rulings, "RULINGS", rulings):
            args = ({"origin": "custom"}, package, good["kind"], good["ordinal"],
                    {"logic_difficulty": 0, "boost_blue_fire": False})
            self.assertIsNone(object_rulings.rank(*args))
            with mock.patch.object(track_rulings, "RULING_VERSION", 2):
                self.assertEqual(track_rulings.generation(object_rulings.rank)(*args), 0)

    def test_historical_key_carries_only_its_copy_review(self):
        st_patrick, anniversary = "release-st-patrick-adventure-slot-55", "crash-30anniversary-adventure-track-26"
        pin, other_pin, new_pin = "aa" * 32, "bb" * 32, "cc" * 32
        key = ("coco-park-2025", "wumpa_crate", 1, "1.0.0", pin, 2)
        row = dict(content_id=key[0], lev_sha256=pin, hard_rank=2, blue_fire_rank=3)
        reviews = {st_patrick: [[pin, "1.0.0"]], anniversary: [[other_pin, "1.0.0"]]}
        track = {"origin": "custom"}
        settings = {"logic_difficulty": 0, "boost_blue_fire": False}
        with (mock.patch.dict(track_rulings.REVIEWS, reviews),
              mock.patch.dict(object_rulings.RULINGS, {key: row})):
            for raw, expected in ((st_patrick, None), (anniversary, 0)):
                package = dict(id=f"package/{raw}/2.0.0", content_id=raw, revision="2.0.0",
                               files=[dict(role="lev", sha256=new_pin)])
                for version in (1, 2):
                    plan = dict(required_features=[track_rulings.FEATURE], track_ruling_sources=dict(
                        version=version, packages=[dict(package_id=package["id"], reviews=[
                            dict(revision=rev, lev_sha256=sha) for rev, sha in track_rulings.reviewed(package)])]))
                    with self.subTest(key=raw, version=version):
                        self.assertEqual(track_rulings.validation(
                            lambda _: object_rulings.rank(track, package, "wumpa_crate", 1, settings)
                        )(plan), expected if version == 2 else 0)
                self.assertEqual(track_rulings.generation(lambda _: object_rulings.carried_source(package))(None),
                                 ("1.0.0", pin) if raw == st_patrick else None)

    def test_rule_added_to_a_previous_source_does_not_change_saved_rooms(self):
        from .. import track_rulings

        next_version = track_rulings.RULING_VERSION + 1
        exact = options()
        carried = copy.deepcopy(exact)
        package = carried["content_pool"]["tracks"]["custom"][0]
        package.update(id="package/tv-world/9.0.0", revision="9.0.0")
        package["files"][0]["sha256"] = "ab" * 32
        carried["content_pool"]["required_entries"] = ["custom/tv-world/9.0.0"]
        for opts in (exact, carried):
            room = make_world(opts, seed=52, stop_before="pre_fill")
            wire = json.loads(json.dumps(room.fill_slot_data()))
            key = ("tv-world", "wumpa_crate", 3)
            rule = dict(object_rulings.RULINGS[key], hard_rank=0, blue_fire_rank=0)
            with (mock.patch.dict(object_rulings.RULINGS, {(*key, "1.1.0", PIN, next_version): rule}),
                  mock.patch.object(track_rulings, "RULING_VERSION", next_version)):
                restored = make_world({}, passthrough=wire, seed=99, stop_before="pre_fill")
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
                new_plan = make_world(opts, seed=52, stop_before="pre_fill").ctr_content_plan
                selected = next(r["wumpa_crate"] for r in new_plan["sanity"]["tracks"]
                                if r["track_id"].startswith("custom/tv-world/"))
                self.assertIn(3, selected)

    def test_finish_ruling_added_to_a_previous_source_preserves_saved_rooms(self):
        from .. import track_rulings

        next_version = track_rulings.RULING_VERSION + 1
        for revision, pin in (("1.1.0", PIN), ("9.0.0", "ab" * 32)):
            opts = options("hard")
            package = opts["content_pool"]["tracks"]["custom"][0]
            package.update(id=f"package/tv-world/{revision}", revision=revision)
            package["files"][0]["sha256"] = pin
            track = f"custom/tv-world/{revision}"
            opts["content_pool"]["required_entries"] = [track]
            world = make_world(opts, seed=52, stop_before="pre_fill")
            wire = json.loads(json.dumps(world.fill_slot_data()))
            new_rule = {("tv-world", "1.1.0", PIN, next_version): 2}
            with (mock.patch.dict(content_capability.USF_FINISH_RULINGS, new_rule),
                  mock.patch.object(track_rulings, "RULING_VERSION", next_version)):
                restored = make_world({}, passthrough=wire, seed=99, stop_before="pre_fill")
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
                new_plan = make_world(opts, seed=52, stop_before="pre_fill").ctr_content_plan
                trophy = next(c for c in new_plan["checks"] if c["kind"] == "trophy" and c["owner"] == track)
                self.assertEqual(trophy["boost"], 2)

    def test_selection_settings_are_paired_and_agree_with_capability(self):
        original = make_world(options(), seed=52, stop_before="pre_fill").ctr_content_plan
        for key, value in (("logic_difficulty", True), ("logic_difficulty", 2),
                           ("boost_blue_fire", 1), ("boost_blue_fire", True)):
            forged = copy.deepcopy(original)
            forged["sanity"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(OptionError):
                content_plan.validate(forged)
        for key in ("logic_difficulty", "boost_blue_fire"):
            forged = copy.deepcopy(original)
            del forged["sanity"][key]
            with self.subTest(missing=key), self.assertRaises(OptionError):
                content_plan.validate(forged)
