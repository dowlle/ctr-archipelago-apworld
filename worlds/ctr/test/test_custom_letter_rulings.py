"""A4-30: two project-owned letter floors, independent of difficulty."""
import copy
import json
import unittest
from unittest import mock

from BaseClasses import CollectionState

from .. import content_capability as cap, content_plan
from .test_capability_packs import RECORD, first_world, refused
from .test_custom_packages import named_fixture
from .test_track_checks import check_options


def packages():
    tv = named_fixture()
    tv["capabilities"].update(ctr_tokens=True, super_turbo_pads=False)
    nina = copy.deepcopy(tv)
    nina.update(id="package/nina-s-nightmare/1.1.0", content_id="nina-s-nightmare",
                display_name="Nina's Nightmare", uuid="2a22c2c3-118e-5635-8012-4d508cf7bc20")
    nina["files"][0]["sha256"] = "e5" * 32
    nina["files"][1]["sha256"] = "f6" * 32
    # Deliberately no finish floor: prove the letter ruling works independently.
    return [tv, nina]


class TestCustomLetterRulings(unittest.TestCase):
    def test_exact_scope_and_all_settings(self):
        self.assertEqual(cap.LETTER_BOOST_RULINGS,
                         {("tv-world", "letter_r"): 2, ("nina-s-nightmare", "letter_t"): 2})
        for package, target in zip(packages(), ("letter_r", "letter_t")):
            for difficulty in range(3):
                for knowledge in range(3):
                    for blue in (False, True):
                        for mode in (0, 1, 2):
                            record = dict(RECORD, boost_mode=mode, logic_difficulty=difficulty,
                                          shortcut_knowledge=knowledge, boost_blue_fire=blue)
                            track = dict(origin="custom", display_name=package["display_name"])
                            for letter in content_plan.LETTER_KEYS:
                                with self.subTest(package=package["content_id"], record=record, letter=letter):
                                    self.assertEqual(cap.check_boost(track, "letter", letter, record, package),
                                                     2 if mode and letter == target else 0)
                            for picked in (set(), {target}, set(content_plan.LETTER_KEYS) - {target}, None):
                                want = 0 if not mode else 2 if picked is None or target in picked else 1
                                self.assertEqual(cap.check_boost(track, "ctr", "win_letters", record,
                                                                 package, picked), want)
                            # A similar content id must not inherit the ruling.
                            other = dict(package, content_id=package["content_id"] + "-other")
                            self.assertEqual(cap.check_boost(track, "letter", target, record, other), 0)
                            # Existing finish requirements are never lowered.
                            if mode:
                                ruled_finish = dict(other, capabilities=dict(super_turbo_pads=True))
                                self.assertEqual(cap.check_boost(track, "letter", target, record, ruled_finish), 2)

    def test_generated_wire_reachability_and_validation(self):
        for difficulty in ("easy", "medium", "hard"):
            options = check_options(custom=packages(), letters=1, stages="single", order="fixed")
            options.update(progressive_boost="shared_global", logic_difficulty=difficulty)
            world = first_world(options, seed=30)
            plan, mw = world.ctr_content_plan, world.multiworld
            for content, award in (("tv-world", "letter_r"), ("nina-s-nightmare", "letter_t")):
                check = next(c for c in plan["checks"] if c["owner"] == f"custom/{content}/1.1.0"
                             and c["kind"] == "letter" and c["routes"][0]["award"] == award)
                self.assertEqual(check["boost"], 2)
                loc = next(loc for loc in mw.get_locations(1) if loc.address == check["location"])
                state = CollectionState(mw)
                for item in mw.itempool:
                    if item.name != "Progressive Boost":
                        state.collect(item, True)
                self.assertFalse(loc.can_reach(state))
                state.collect(world.create_item("Progressive Boost"), True)
                self.assertFalse(loc.can_reach(state))
                state.collect(world.create_item("Progressive Boost"), True)
                self.assertTrue(loc.can_reach(state))
                forged = copy.deepcopy(plan)
                next(c for c in forged["checks"] if c["location"] == check["location"])["boost"] = 1
                self.assertTrue(refused(forged))
            self.assertTrue(content_plan.validate(plan))

    def test_boost_off_plan_is_identical_without_the_rulings(self):
        options = check_options(custom=packages(), letters=1)
        options.update(progressive_boost="off", progressive_stats="shared_global")
        on = first_world(options, seed=30).fill_slot_data()
        with mock.patch.dict(cap.LETTER_BOOST_RULINGS, {}, clear=True):
            off = first_world(options, seed=30).fill_slot_data()
        self.assertEqual(json.dumps(on, sort_keys=True), json.dumps(off, sort_keys=True))

    def test_loader_rejects_duplicate_and_invalid_rows(self):
        good = dict(content_id="tv-world", letter="letter_r", rank=2, ruling="Project ruling 2026-11-10")
        def load(rows):
            with mock.patch.object(cap.pkgutil, "get_data", return_value=json.dumps(
                    dict(version=1, rulings=rows)).encode()):
                return cap._load_letter_rulings()
        self.assertEqual(load([good]), {("tv-world", "letter_r"): 2})
        for bad in (dict(good, letter="T"), dict(good, rank=True), dict(good, rank=3),
                    dict(good, content_id=""), dict(good, ruling="undated"), dict(good, extra=1)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load([bad])
        with self.assertRaises(ValueError):
            load([good, good])
