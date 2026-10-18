"""Item Box Locations on content plans (#133 PR 4e).

Retail tracks keep their frozen box ids, Shortcut Knowledge seating and box
rules; a custom track on a named block uses its Item Box 1 to 15 offsets, one
per seat on its own weapon crates (min(weapon_crates, 15)); generic slots and
Cortex Vortex have none. The paired native parser reads the same records
(native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError

from .. import content_item_boxes, content_plan, custom_packages, named_tracks
from ..item_boxes import BOX_RULES, ITEM_BOX_CLASS
from ..Locations import CTR_LOCATION_IDS
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN, named_fixture
from .test_track_checks import check_options

BTP_ID = "custom/baby-t-park/1.0.2"
ACID_ID = "custom/acid-lake/1.0"
TIERS = {"easy": 0, "medium": 1, "hard": 2}


def btp(crates=8):
    package = copy.deepcopy(content_plan.PACKAGES[1])
    if crates is None:
        package["capabilities"].pop("weapon_crates", None)
    else:
        package["capabilities"]["weapon_crates"] = crates
    return package


def unruled(crates=20):
    """Test data on a named key with no USF ruling (Acid Lake, block 0) that
    states super turbo pads, so its finish term is USF."""
    d = named_fixture()
    d.update(id="package/acid-lake/1.0", content_id="acid-lake", revision="1.0", display_name="Acid Lake",
             uuid="11111111-2222-4333-8444-555555555555")
    d["capabilities"].update(super_turbo_pads=True, weapon_crates=crates)
    d["files"][0]["sha256"] = "e5" * 32
    d["files"][1]["sha256"] = "f6" * 32
    return d


def box_options(custom=None, tier="medium", **extra):
    options = check_options(rungs=False, custom=[btp()] if custom is None else custom)
    options["content_pool"]["required_entries"] = [f"custom/{d['content_id']}/{d['revision']}"
                                                   for d in options["content_pool"]["tracks"]["custom"]]
    options.update(box_locations=True, shortcut_knowledge=tier, character_unlocks=False)
    options.update(extra)
    return options


def first_world(options, seed=0):
    """The first seed from `seed` on that the starting-check guard accepts."""
    for attempt in range(seed, seed + 20):
        try:
            return make_world(options, seed=attempt)
        except OptionError as exc:
            if "at the start" not in str(exc):
                raise
    raise AssertionError("no seed in 20 passed the starting-check guard")


def boxes(plan, owner=None):
    return [c for c in plan["checks"] if c["kind"] == "box" and (owner is None or c["owner"] == owner)]


def refused(plan):
    try:
        content_plan.validate(plan)
    except OptionError:
        return True
    return False


def state_with(world, *names):
    state = CollectionState(world.multiworld)
    for name in names:
        state.collect(world.create_item(name), prevent_sweep=True)
    return state


class TestOffKeepsTheWire(unittest.TestCase):
    def test_off_means_no_record_feature_check_or_envelope_key(self):
        world = make_world(box_options(box_locations=False), seed=3)
        plan, wire = world.ctr_content_plan, world.fill_slot_data()
        self.assertNotIn("item_boxes", plan)
        self.assertNotIn(content_item_boxes.FEATURE, plan["required_features"])
        self.assertFalse(boxes(plan))
        self.assertNotIn("box_locations", wire["ctr_options"])
        self.assertNotIn("color_boxes_by_item", wire["ctr_options"])


class TestRetailBoxes(unittest.TestCase):
    def test_every_tier_matches_the_frozen_seating(self):
        for tier, value in TIERS.items():
            world = make_world(box_options(tier=tier), seed=2)
            plan = world.ctr_content_plan
            self.assertEqual(plan["item_boxes"], {"shortcut_knowledge": value})
            self.assertEqual(plan["required_features"][-1], content_item_boxes.FEATURE)
            got = {c["display_name"]: c["location"] for c in boxes(plan) if c["owner"].startswith("retail:")}
            want = {n: CTR_LOCATION_IDS[n] for n in ITEM_BOX_CLASS.created_location_names(world.options)}
            self.assertEqual(got, want)
            self.assertEqual(len(got), {0: 229, 1: 236, 2: 241}[value])

    def test_routes_follow_the_pad_mode_order(self):
        plan = make_world(box_options(), seed=5).ctr_content_plan
        entries = {e["id"]: e for e in plan["entries"]}
        pads = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
        for check in boxes(plan):
            entry = entries["entry/" + check["owner"]]
            self.assertEqual([(r["mode"], r["award"], r["own_pad_id"]) for r in check["routes"]],
                             [(m, "box", pads[entry["id"]]) for m in entry["modes"]])

    def test_box_rules_ride_as_boost_and_stats(self):
        plan = make_world(box_options(tier="hard", progressive_boost="shared_global",
                                      progressive_stats="shared_global"), seed=1).ctr_content_plan
        by_name = {c["display_name"]: c for c in boxes(plan)}
        seen = 0
        for (track, slot), (boost, stats) in BOX_RULES.items():
            check = by_name.get(f"{track}: Item Box {slot}")
            if check is None:
                continue
            seen += 1
            self.assertEqual(check.get("boost", 0), boost, check["display_name"])
            self.assertEqual(check.get("stats", False), stats, check["display_name"])
        self.assertEqual(seen, len(BOX_RULES))
        self.assertTrue(by_name["Oxide Station: Item Box 6"]["stats"])
        self.assertNotIn("boost", by_name["Oxide Station: Item Box 6"])

    def test_terms_need_their_packs(self):
        plan = make_world(box_options(tier="hard"), seed=1).ctr_content_plan
        self.assertFalse([c for c in boxes(plan) if "boost" in c or "stats" in c])
        plan = make_world(box_options(tier="hard", progressive_stats="shared_global"), seed=1).ctr_content_plan
        self.assertFalse([c for c in boxes(plan) if "boost" in c])
        self.assertEqual({c["display_name"] for c in boxes(plan) if c.get("stats")},
                         {f"{t}: Item Box {s}" for (t, s), (_b, st) in BOX_RULES.items() if st})


class TestCustomBoxes(unittest.TestCase):
    def test_named_track_takes_one_box_per_seat(self):
        for crates, count in ((8, 8), (15, 15), (40, 15), (1, 1)):
            plan = make_world(box_options(custom=[btp(crates)]), seed=4).ctr_content_plan
            own = boxes(plan, BTP_ID)
            self.assertEqual([c["location"] for c in own],
                             [named_tracks.location_code(8, f"item_box_{n}") for n in range(1, count + 1)])
            self.assertEqual([c["display_name"] for c in own],
                             [f"Baby T Park: Item Box {n}" for n in range(1, count + 1)])

    def test_no_stated_count_or_zero_crates_means_no_boxes(self):
        for crates in (None, 0):
            plan = make_world(box_options(custom=[btp(crates)]), seed=4).ctr_content_plan
            self.assertFalse(boxes(plan, BTP_ID))

    def test_generic_slot_and_cortex_vortex_have_none(self):
        loop = copy.deepcopy(UNKNOWN)
        loop["capabilities"]["weapon_crates"] = 12
        options = box_options(custom=[btp(), loop])
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        plan = make_world(options, seed=6).ctr_content_plan
        owners = {c["owner"] for c in boxes(plan)}
        self.assertNotIn("custom/fixture-loop/2.1", owners)
        self.assertNotIn(content_plan.CORTEX_TRACK_ID, owners)
        self.assertIn(BTP_ID, owners)

    def test_seats_spread_over_the_crate_table(self):
        self.assertEqual(content_item_boxes.seat_indices(8), list(range(8)))
        self.assertEqual(content_item_boxes.seat_indices(30), list(range(0, 30, 2)))
        self.assertEqual(content_item_boxes.seat_indices(69)[:3], [0, 4, 9])
        self.assertEqual(content_item_boxes.seat_indices(0), [])

    def test_custom_box_takes_the_finish_term(self):
        options = box_options(custom=[btp(), unruled()], progressive_boost="shared_global")
        plan = first_world(options, seed=3).ctr_content_plan
        self.assertEqual({c.get("boost") for c in boxes(plan, ACID_ID)}, {2})
        # Baby T Park is ruled generic terms only (2026-10-18): no box term.
        self.assertFalse([c for c in boxes(plan, BTP_ID) if "boost" in c])
        self.assertFalse([c for c in boxes(plan) if c["owner"].startswith("custom/") and "stats" in c])

    def test_weapon_crates_admission(self):
        for bad in (-1, 65537, True, "8", 1.0):
            d = btp()
            d["capabilities"]["weapon_crates"] = bad
            with self.assertRaises(custom_packages.PackageError):
                custom_packages.admit(d)
        self.assertEqual(custom_packages.admit(btp(65536))["capabilities"]["weapon_crates"], 65536)


class TestLogic(unittest.TestCase):
    def test_boost_and_stat_terms_gate_the_box(self):
        world = make_world(box_options(tier="hard", progressive_boost="shared_global",
                                       progressive_stats="shared_global"), seed=1)
        boost = world.multiworld.get_location("N. Gin Labs: Item Box 4", world.player)
        self.assertFalse(boost.access_rule(state_with(world, "Progressive Boost")))
        self.assertTrue(boost.access_rule(state_with(world, "Progressive Boost", "Progressive Boost")))
        stat = world.multiworld.get_location("Oxide Station: Item Box 6", world.player)
        chains = ("Progressive Top Speed", "Progressive Acceleration", "Progressive Turning")
        self.assertFalse(stat.access_rule(state_with(world, *chains[:2])))
        self.assertTrue(stat.access_rule(state_with(world, *chains)))

    def test_tiger_temple_door_box_needs_an_opener_with_itemsanity(self):
        world = make_world(box_options(itemsanity=True), seed=2)
        location = world.multiworld.get_location("Tiger Temple: Item Box 5", world.player)
        self.assertFalse(location.access_rule(state_with(world)))
        self.assertTrue(location.access_rule(state_with(world, "Bomb")))
        world = make_world(box_options(), seed=2)
        location = world.multiworld.get_location("Tiger Temple: Item Box 5", world.player)
        self.assertTrue(location.access_rule(state_with(world)))

    def test_filled_seeds_are_beatable_with_every_location_reachable(self):
        for seed, extra in enumerate(({}, dict(progressive_boost="per_character", tier="hard"),
                                      dict(progressive_stats="shared_global", itemsanity=True),
                                      dict(character_unlocks=True, racer_locked_pads=4, tier="easy"))):
            options = box_options(custom=[btp(), unruled(), copy.deepcopy(UNKNOWN)], **extra)
            world = first_world(options, seed=seed * 7)
            distribute_items_restrictive(world.multiworld)
            state = CollectionState(world.multiworld)
            state.sweep_for_advancements()
            self.assertTrue(world.multiworld.can_beat_game(state), extra)
            self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations()), extra)


class TestItemsanityRoutes(unittest.TestCase):
    def test_a_crateless_custom_track_is_no_itemsanity_or_hit_route(self):
        options = box_options(custom=[btp(0)], box_locations=False, itemsanity=True, hit_character=True)
        plan = make_world(options, seed=3).ctr_content_plan
        families = [c for c in plan["checks"] if c["kind"] in ("itemsanity", "hit")]
        self.assertTrue(families)
        for check in families:
            self.assertFalse([r for r in check["routes"] if r["entry_id"] == "entry/" + BTP_ID])
        options = box_options(custom=[btp(8)], box_locations=False, itemsanity=True)
        plan = make_world(options, seed=3).ctr_content_plan
        use = next(c for c in plan["checks"] if c["kind"] == "itemsanity")
        self.assertTrue([r for r in use["routes"] if r["entry_id"] == "entry/" + BTP_ID])

    def test_forging_a_crate_count_changes_the_routes(self):
        options = box_options(custom=[btp(8)], box_locations=False, itemsanity=True)
        plan = copy.deepcopy(make_world(options, seed=3).ctr_content_plan)
        plan["packages"][0]["capabilities"]["weapon_crates"] = 0
        self.assertTrue(refused(plan))


class TestForgeries(unittest.TestCase):
    OPTIONS = dict(custom=[btp(), unruled()], tier="hard", progressive_boost="shared_global",
                   progressive_stats="shared_global")

    @classmethod
    def setUpClass(cls):
        cls.world = first_world(box_options(**copy.deepcopy(cls.OPTIONS)), seed=2)
        cls.plan = cls.world.ctr_content_plan

    def forged(self, change):
        plan = copy.deepcopy(self.plan)
        change(plan)
        return refused(plan)

    def test_the_unchanged_plan_validates(self):
        self.assertFalse(self.forged(lambda p: None))

    def test_forged_records_checks_and_packages_refuse(self):
        def first_box(p):
            return boxes(p)[0]

        def drop_record(p):
            p.pop("item_boxes")
            p["required_features"].remove(content_item_boxes.FEATURE)

        def drop_box(p):
            p["checks"].remove(first_box(p))
            p["items"]["filler_count"] -= 1
            p["items"]["coded_checks"] -= 1

        def crates(p, n):
            next(d for d in p["packages"] if d["content_id"] == "baby-t-park")["capabilities"]["weapon_crates"] = n
        cases = {
            "record dropped": drop_record,
            "feature dropped": lambda p: p["required_features"].remove(content_item_boxes.FEATURE),
            "tier lowered": lambda p: p["item_boxes"].__setitem__("shortcut_knowledge", 1),
            "tier disagrees with capability": lambda p: p["capability"].__setitem__("shortcut_knowledge", 1),
            "unknown record field": lambda p: p["item_boxes"].__setitem__("color", True),
            "record not an object": lambda p: p.__setitem__("item_boxes", []),
            "box dropped": drop_box,
            "box code": lambda p: first_box(p).__setitem__("location", first_box(p)["location"] + 15),
            "box route dropped": lambda p: first_box(p)["routes"].pop(),
            "box award": lambda p: first_box(p)["routes"][0].__setitem__("award", "win"),
            "box name": lambda p: first_box(p).__setitem__("display_name", "Item Box 1"),
            "boost lowered": lambda p: next(c for c in boxes(p) if c.get("boost") == 2).__setitem__("boost", 1),
            "stats dropped": lambda p: next(c for c in boxes(p) if c.get("stats")).pop("stats"),
            "stats false": lambda p: next(c for c in boxes(p) if c.get("stats")).__setitem__("stats", False),
            "stats on a race check": lambda p: next(c for c in p["checks"] if c["kind"] == "trophy")
            .__setitem__("stats", True),
            "weapon crates raised": lambda p: crates(p, 30),
            "weapon crates lowered": lambda p: crates(p, 3),
        }
        for name, change in cases.items():
            self.assertTrue(self.forged(change), name)

    def test_envelope_and_tracker_round_trip(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertIs(wire["ctr_options"]["box_locations"], True)
        self.assertIs(wire["ctr_options"]["color_boxes_by_item"], True)
        # The tracker's own YAML does not matter: the room decides.
        options = box_options(**copy.deepcopy(self.OPTIONS), color_boxes_by_item=False)
        options.update(box_locations=False, shortcut_knowledge="easy")
        restored = make_world(options, seed=2, passthrough=wire)
        self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
        self.assertEqual(int(restored.options.box_locations.value), 1)
        self.assertEqual(int(restored.options.shortcut_knowledge.value), 2)
        self.assertEqual(int(restored.options.color_boxes_by_item.value), 1)
        for change in (lambda c: c["ctr_options"].pop("box_locations"),
                       lambda c: c["ctr_options"].pop("color_boxes_by_item"),
                       lambda c: c["ctr_options"].__setitem__("color_boxes_by_item", 1),
                       lambda c: c["ctr_options"].__setitem__("box_locations", False)):
            forged = copy.deepcopy(wire)
            change(forged)
            with self.assertRaises(OptionError):
                make_world(options, seed=2, passthrough=forged)
        plain_options = box_options(box_locations=False)
        plain = json.loads(json.dumps(make_world(plain_options, seed=2).fill_slot_data()))
        plain["ctr_options"]["box_locations"] = True
        with self.assertRaises(OptionError):
            make_world(plain_options, seed=2, passthrough=plain)


if __name__ == "__main__":
    unittest.main()
