"""A4-52: TV World's upper-room crates, with stable identities."""
import copy
import json
import unittest
from unittest import mock

from BaseClasses import CollectionState
from Options import OptionError
from .. import content_plan, object_rulings, sanity
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

    def test_loader_refuses_invalid_rows(self):
        good = next(iter(object_rulings.RULINGS.values()))
        self.assertEqual(len(object_rulings.RULINGS), 4)
        for rows in ([good, good], [dict(good, ordinal=True)], [dict(good, hard_rank=3)],
                     [dict(good, blue_fire_rank=2)], [dict(good, ruling="undated")], [dict(good, kind="letter")]):
            with mock.patch.object(object_rulings.pkgutil, "get_data", return_value=json.dumps(
                    dict(version=1, rulings=rows)).encode()), self.assertRaises(ValueError):
                object_rulings._load()
