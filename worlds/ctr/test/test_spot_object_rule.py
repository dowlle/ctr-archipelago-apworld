"""TV2: an AP box spot carries a crate's ruling through `rule_of`.

The fixture file (test/fixtures/box_spots/custom/tv-world.json) is never
shipped: the tests put it in place of the shipped table for their own duration.
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import box_spot_catalog, box_spots, content_plan, object_rulings
from ..Locations import CTR_LOCATION_IDS
from .test_box_spots import entry, spot_files, spot_set
from .test_content_item_boxes import boxes
from .test_content_plan import make_world
from .test_object_rulings import PIN, TV, options

PACKAGE = options()["content_pool"]["tracks"]["custom"][0]
TRACK = dict(origin="custom", named_block=78, id=TV)
RULED = (1, 2)
ORDINARY = (3, 4)


def build(difficulty, blue, boost, count=15, seed=3):
    opts = options(difficulty, blue, boost, wumpa="off")
    opts["item_box_count"] = count
    return make_world(opts, seed=seed, stop_before="pre_fill")


def expected(difficulty, blue, boost, stats=False):
    """(spots present, rank of the ruled ones) by the crate rule."""
    # Both packs off (the helper options turn stats off) leaves the plan with no
    # capability record, hence no Logic Difficulty: the spots are dropped.
    removed = boost == "off" and not stats or difficulty != "hard" and not (blue and boost != "off")
    rank = 0 if boost == "off" else 2 if difficulty == "hard" else 3
    return ([] if removed else list(RULED)) + list(ORDINARY), rank


class TestSpotCarriesCrateRule(unittest.TestCase):
    def test_fixture_is_a_valid_file_and_names_ruled_crates(self):
        with spot_files(custom=("tv-world",)):
            doc = box_spots.CUSTOM_FILES["tv-world"]["doc"]
        self.assertEqual([s.get("rule_of") for s in doc["spots"]], ["wumpa_crate:3", "wumpa_crate:6", None, None])
        for text, parsed in (("wumpa_crate:3", ("wumpa_crate", 3)), ("weapon_crate:19", ("weapon_crate", 19))):
            self.assertEqual(object_rulings.parse_rule(text), parsed)
        for bad in ("wumpa_crate", "wumpa_crate:", "wumpa_crate:03", "wumpa_crate:x", "box:3", "", None, 3):
            self.assertIsNone(object_rulings.parse_rule(bad))

    def test_file_checks_refuse_a_rule_that_could_under_gate(self):
        doc = copy.deepcopy(entry("box_spots/custom/tv-world.json")["doc"])
        box_spot_catalog.check_draft_file(doc)
        for label, change in {
            "needs below the strictest bound": lambda s: s.__setitem__("needs", "usf"),
            "needs absent": lambda s: s.pop("needs"),
            "a crate with no ruling": lambda s: s.__setitem__("rule_of", "wumpa_crate:2"),
            "another kind": lambda s: s.__setitem__("rule_of", "weapon_crate:3"),
            "malformed": lambda s: s.__setitem__("rule_of", "wumpa_crate:3:4"),
        }.items():
            bad = copy.deepcopy(doc)
            change(bad["spots"][0])
            with self.subTest(label), self.assertRaises(box_spots.SpotFileError):
                box_spot_catalog.check_draft_file(bad)
        other = copy.deepcopy(doc)
        other["track"]["track_key"] = "ancient-lake"
        with self.assertRaises(box_spots.SpotFileError):
            box_spot_catalog.check_draft_file(other)
        retail = copy.deepcopy(box_spots.RETAIL_FILES[0]["doc"])
        retail["spots"][0].update(needs="blue_fire", rule_of="wumpa_crate:3")
        with self.assertRaises(box_spots.SpotFileError):
            box_spot_catalog.check_draft_file(retail)

    def test_eligibility_follows_the_crate_ruling_and_fails_closed(self):
        with spot_files(custom=("tv-world",)):
            file = box_spots.CUSTOM_FILES["tv-world"]
            for difficulty, level in (("easy", 0), ("medium", 1), ("hard", 2)):
                for blue in (False, True):
                    present, _ = expected(difficulty, blue, "shared_global")
                    self.assertEqual(box_spots.eligible(file, 2, blue, level, TRACK, PACKAGE), present,
                                     (difficulty, blue))
            # No capability record (both packs off): no Logic Difficulty, the ruled spots go.
            self.assertEqual(box_spots.eligible(file, 2, False, None, TRACK, PACKAGE), [3, 4])
            # A package no ruling covers takes the spot's own blue_fire bound, never less.
            other = dict(PACKAGE, content_id="other-tv-world")
            self.assertEqual(box_spots.eligible(file, 2, False, 2, TRACK, other), [3, 4])
            self.assertEqual(box_spots.eligible(file, 2, True, 2, TRACK, other), [1, 2, 3, 4])
            self.assertEqual(box_spots.spot_rank(box_spots.spots_by_number(file)[1], TRACK, other, True, 2), 3)

    def test_rank_is_the_crate_rank(self):
        with spot_files(custom=("tv-world",)):
            file = box_spots.CUSTOM_FILES["tv-world"]
            spots = box_spots.spots_by_number(file)
            for level in range(3):
                for blue in (False, True):
                    cap = dict(logic_difficulty=level, boost_blue_fire=blue)
                    for n, ordinal in ((1, 3), (2, 6)):
                        want = object_rulings.rank(TRACK, PACKAGE, "wumpa_crate", ordinal, cap)
                        if want is None:
                            continue
                        self.assertEqual(box_spots.spot_rank(spots[n], TRACK, PACKAGE, blue, level), want)
            self.assertEqual(box_spots.spot_rank(spots[3], TRACK, PACKAGE, False, 0), 0)
            self.assertEqual(box_spots.spot_rank(spots[4], TRACK, PACKAGE, False, 0), 2)

    def test_every_setting_in_a_generated_room(self):
        for difficulty in ("easy", "medium", "hard"):
            for blue in (False, True):
                for boost in ("off", "shared_global", "per_character"):
                    with self.subTest(difficulty=difficulty, blue=blue, boost=boost), spot_files(custom=("tv-world",)):
                        world = build(difficulty, blue, boost)
                        wire = json.loads(json.dumps(world.fill_slot_data()))
                        plan = wire["content_plan"]
                        self.assertTrue(content_plan.validate(plan))
                        present, rank = expected(difficulty, blue, boost)
                        record = spot_set(plan, TV)
                        self.assertEqual((record["pool"], record["picked"]), (len(present), sorted(present)))
                        checks = {c["spot"]["number"]: c for c in boxes(plan, TV)}
                        self.assertEqual(sorted(checks), sorted(present))
                        for n, check in checks.items():
                            self.assertEqual(check.get("boost", 0), rank if n in RULED else
                                             (0 if n == 3 else 0 if boost == "off" else 2), (n, check))
                        # The seed restores to the same plan, and a forged lower rank is refused.
                        restored = make_world({}, passthrough=wire, stop_before="pre_fill")
                        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data()))["content_plan"], plan)
                        if rank > 1 and present[0] in RULED:
                            forged = copy.deepcopy(plan)
                            next(c for c in boxes(forged, TV) if c["spot"]["number"] == 1)["boost"] = rank - 1
                            with self.assertRaises(OptionError):
                                content_plan.validate(forged)

    def test_removed_spots_keep_their_registered_ids(self):
        for n in (1, 2, 3, 4):
            self.assertIn(f"TV World: Item Box {n}", CTR_LOCATION_IDS)
        with spot_files(custom=("tv-world",)):
            plan = build("easy", False, "shared_global").ctr_content_plan
        self.assertEqual(spot_set(plan, TV)["picked"], [3, 4])
        names = {c["display_name"] for c in plan["checks"]}
        self.assertFalse({"TV World: Item Box 1", "TV World: Item Box 2"} & names)

    def test_reachability_by_held_boosts(self):
        for difficulty in ("easy", "hard"):
            with spot_files(custom=("tv-world",)):
                world = build(difficulty, True, "shared_global")
                present, rank = expected(difficulty, True, "shared_global")
                state = CollectionState(world.multiworld)
                for item in world.multiworld.itempool:
                    if not item.name.startswith("Progressive Boost"):
                        state.collect(item, True)
                boosts = [i.name for i in world.multiworld.itempool if i.name.startswith("Progressive Boost")]
                by_name = {l.name: l for l in world.multiworld.get_locations(1)}
                for held in range(4):
                    for n in present:
                        want = {1: rank, 2: rank, 3: 0, 4: 2}[n]
                        got = by_name[f"TV World: Item Box {n}"].can_reach(state)
                        self.assertEqual(got, held >= want, (difficulty, held, n))
                    for name in boosts[:1]:
                        state.collect(world.create_item(name), True)

    def test_no_other_track_changes_and_count_zero_is_untouched(self):
        # Another track's pool, and a Count 0 room, read the same with and without the file.
        for count in (0, 15):
            with self.subTest(count=count):
                base = build("hard", True, "shared_global", count=count).fill_slot_data()["content_plan"]
                with spot_files(custom=("tv-world",)):
                    withfile = build("hard", True, "shared_global", count=count).fill_slot_data()["content_plan"]
                if count == 0:
                    self.assertEqual(withfile, base)
                else:
                    others = lambda p: [c for c in p["checks"] if c["owner"] != TV]
                    self.assertEqual(others(withfile), others(base))
