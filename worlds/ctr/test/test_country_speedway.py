"""Physical Country 1.3.0 seats, room compatibility and Tracker boundaries."""
import copy
import json
from pathlib import Path
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from .. import characters, content_item_boxes as boxes, content_plan, country_speedway as country, sanity
from .test_content_plan import make_world, profile_options

PACKAGE = json.loads((Path(__file__).parent / "fixtures/country_speedway_130.json").read_text())


def country_options(**extra):
    options = profile_options()
    options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(PACKAGE)]
    options["content_pool"]["required_entries"] = ["custom/country-speedway/1.3.0"]
    options.update(itemboxsanity=50, wumpasanity="crates", progressive_stats="off",
                   progressive_boost="shared_global", shortcut_knowledge=1, item_box_count=15)
    options.update(extra)
    return options


class TestCountrySpeedway(unittest.TestCase):
    def test_reused_older_lev_uses_the_latest_pickup_rules_and_current_counts(self):
        from .. import track_rulings
        old_pin = next(pin for pin, revision in track_rulings.REVIEWS["country-speedway"] if revision == "1.2.1")
        options = country_options(item_box_count=0)
        package = options["content_pool"]["tracks"]["custom"][0]
        package.update(id="package/country-speedway/9.0.0", revision="9.0.0")
        package["files"][0]["sha256"] = old_pin
        options["content_pool"]["required_entries"] = ["custom/country-speedway/9.0.0"]
        plan = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        row = next(r for r in plan["sanity"]["tracks"] if r["track_id"] == "custom/country-speedway/9.0.0")
        self.assertEqual(row["counts"], [25, 5, 0])
        self.assertEqual((len(row["weapon_crate"]), len(row["wumpa_crate"])), (25, 5))
        self.assertEqual(plan["sanity"]["rules_version"], 3)

    def test_a_new_revision_keeps_the_finish_ruling_and_its_own_pad_measurement(self):
        for pin in ("ab" * 32, country.LEV_SHA256):
            options = country_options(logic_difficulty="hard")
            package = options["content_pool"]["tracks"]["custom"][0]
            package.update(id="package/country-speedway/9.0.0", revision="9.0.0")
            package["files"][0]["sha256"] = pin
            package["capabilities"]["super_turbo_pads"] = True
            track = "custom/country-speedway/9.0.0"
            options["content_pool"]["required_entries"] = [track]
            world = make_world(options, seed=3, stop_before="pre_fill")
            plan = world.ctr_content_plan
            self.assertTrue(plan["packages"][0]["capabilities"]["super_turbo_pads"])
            trophy = next(c for c in plan["checks"] if c["kind"] == "trophy" and c["owner"] == track)
            self.assertEqual(trophy.get("boost", 0), 0)

    def test_country_version_is_separate_from_older_corrections(self):
        for version in (1, 2):
            w = make_world(country_options(), seed=3, stop_before="pre_fill")
            wire = json.loads(json.dumps(w.fill_slot_data()))
            p = wire["content_plan"]
            self.assertEqual(p["sanity"]["rules_version"], 3)
            p["sanity"]["rules_version"] = version
            p["item_boxes"].pop("pickup_rules")
            p["checks"] = [c for c in p["checks"] if c["kind"] not in sanity.KINDS]
            p["checks"].extend(sanity.checks(p["sanity"], p["tracks"], p["entries"], p["pads"],
                                              p["encounters"], p.get("capability"), {PACKAGE["id"]: PACKAGE}))
            for c in p["checks"]:
                if c["owner"] == "custom/country-speedway/1.3.0":
                    if c["kind"] == "box":
                        c.pop("boost", None)
                    elif c["kind"] in sanity.KINDS:
                        self.assertEqual(c.get("boost"), 2)
            self.assertTrue(content_plan.validate(p))
            self.assertEqual(make_world({}, passthrough=wire, stop_before="pre_fill").ctr_content_plan, p)

    def test_exact_pin_overrides_missing_or_wrong_turbo_metadata_only_in_new_rooms(self):
        from ..content_capability import finish_boost
        for stated in (None, True, False):
            options = country_options()
            package = options["content_pool"]["tracks"]["custom"][0]
            if stated is None:
                package["capabilities"].pop("super_turbo_pads")
            else:
                package["capabilities"]["super_turbo_pads"] = stated
            w = make_world(options, seed=3, stop_before="pre_fill")
            p = w.ctr_content_plan
            t = next(t for t in p["tracks"] if t.get("package_id") == PACKAGE["id"])
            checks = [c for c in p["checks"] if c["owner"] == t["id"] and c["kind"] == "box"]
            self.assertEqual([c.get("boost", 0) for c in checks], [2] + [0] * 14)
            normalized = next(pkg for pkg in p["packages"] if pkg["id"] == PACKAGE["id"])
            self.assertFalse(normalized["capabilities"]["super_turbo_pads"])
            self.assertEqual(finish_boost(t, p["capability"], normalized), 0)
            self.assertTrue(content_plan.validate(p))
        old = copy.deepcopy(PACKAGE)
        old["capabilities"].pop("super_turbo_pads")
        self.assertEqual(finish_boost(t, p["capability"], old), 2)
        self.assertEqual(boxes.box_terms(t, 2, p["capability"], old, dict(shortcut_knowledge=1))[0], 2)

    def test_authored_131_spots_keep_their_own_ranks(self):
        from .test_box_spots import community_package
        package = community_package("country-speedway", crates=25)
        track = dict(id="country131", origin="custom", package_id=package["id"], named_block=17,
                     display_name="Country Speedway", custom_slot=1)
        record = dict(shortcut_knowledge=1)
        boxes.add_spot_sets(record, [track], {package["id"]: package}, 3, 1)
        self.assertNotIn("pickup_rules", record)
        checks = boxes.track_boxes(track, record, package)
        self.assertEqual(len(checks), 14)
        for n, _, _ in checks:
            self.assertEqual(boxes.box_terms(track, n, dict(boost_mode=1), package, record)[0],
                             int(n in (2, 3, 4, 11, 14)))

    def test_route_and_locked_racer_are_independent(self):
        for seed in range(12):
            w = make_world(country_options(character_unlocks=True, racer_locked_pads=20,
                                           progressive_boost="per_character"), seed=seed, stop_before="pre_fill")
            p = w.ctr_content_plan
            tid = next(t["id"] for t in p["tracks"] if t.get("package_id") == PACKAGE["id"])
            eid = next(e["id"] for e in p["entries"] if e["kind"] == "track" and e["track_id"] == tid)
            pad = next(pad for pad in p["pads"] if pad["entry_id"] == eid)
            if pad["racer_lock"] is not None:
                break
        else:
            self.fail("fixture did not produce a locked Country pad")
        racer = characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
        checks = [c for c in p["checks"] if c["owner"] == tid and c["kind"] in (*sanity.KINDS, "box")]
        def state_without(predicate):
            state = CollectionState(w.multiworld)
            for name, num in w.multiworld.get_all_state().prog_items[1].items():
                if not predicate(name):
                    for _ in range(num):
                        state.collect(w.create_item(name), True)
            return state
        for missing in (lambda name: name == racer, lambda name: name == "Key"):
            state = state_without(missing)
            self.assertTrue(all(not w.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))
        # All other racer chains are full, but the pad's racer has no Boost.
        state = state_without(lambda name: name.startswith("Progressive Boost") and racer in name)
        platform = next(c for c in checks if c["kind"] == "box" and c["display_name"].endswith(" 1"))
        ground = next(c for c in checks if c["kind"] == "box" and c["display_name"].endswith(" 2"))
        self.assertFalse(w.multiworld.get_location(platform["display_name"], 1).can_reach(state))
        self.assertTrue(w.multiworld.get_location(ground["display_name"], 1).can_reach(state))

    def test_generated_seats_and_tracker(self):
        for count in (0, 1, 5, 15, 50):
            for mode in ("off", "shared_global", "per_character"):
                for wumpa in ("off", "crates"):
                    world = make_world(country_options(item_box_count=count, progressive_boost=mode,
                                                      wumpasanity=wumpa), seed=3, stop_before="pre_fill")
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    p = wire["content_plan"]
                    self.assertTrue(content_plan.validate(p))
                    t = next(t for t in p["tracks"] if t.get("package_id") == PACKAGE["id"])
                    checks = [c for c in p["checks"] if c["owner"] == t["id"]]
                    seat_count = min(count, 15)
                    seats = [i * 25 // seat_count + 1 for i in range(seat_count)]
                    weapon = [c for c in checks if c["kind"] == "weapon_crate"]
                    self.assertEqual({int(c["display_name"].rsplit(" ", 1)[1]) for c in weapon},
                                     set(range(1, 26)) - set(seats))
                    self.assertEqual(sum(c["kind"] == "wumpa_crate" for c in checks), 5 if wumpa == "crates" else 0)
                    for c in checks:
                        if c["kind"] not in (*sanity.KINDS, "box", "lap"):
                            continue
                        if c["kind"] == "lap":
                            rank = 0
                        else:
                            n = int(c["display_name"].rsplit(" ", 1)[1])
                            rank = country.rank("weapon_crate" if c["kind"] == "box" else c["kind"],
                                                seats[n - 1] if c["kind"] == "box" else n)
                        self.assertEqual(c.get("boost", 0), rank if mode != "off" else 0)
                    restored = make_world({}, passthrough=wire, stop_before="pre_fill")
                    self.assertEqual(restored.ctr_content_plan, p)
                    for rank in range(3):
                        for w in (world, restored):
                            state = CollectionState(w.multiworld)
                            for name, num in w.multiworld.get_all_state().prog_items[1].items():
                                for _ in range(min(num, rank) if name.startswith("Progressive Boost") else num):
                                    state.collect(w.create_item(name), True)
                            for c in checks:
                                if c["kind"] in (*sanity.KINDS, "box", "lap"):
                                    with self.subTest(count=count, mode=mode, wumpa=wumpa, rank=rank, check=c["display_name"]):
                                        self.assertEqual(w.multiworld.get_location(c["display_name"], 1).can_reach(state),
                                                         c.get("boost", 0) <= rank)

    def test_exclusions_resolve_native_ordinals(self):
        track = dict(id="country", origin="custom")
        record = dict(shortcut_knowledge=1, box_count=5, pickup_rules=["country"],
                      crate_exclusions=[dict(track_id="country", crates=[dict(ordinal=1), dict(ordinal=3)])])
        # The platform was excluded: AP box 1 now occupies physical weapon 2.
        self.assertEqual([boxes.physical_seat(track, record, PACKAGE, n) for n in range(1, 6)],
                         [2, 7, 12, 16, 21])
        self.assertTrue(all(boxes.box_terms(track, n, dict(boost_mode=1), PACKAGE, record)[0] == 0
                            for n in range(1, 6)))

    def test_legacy_sanity_and_box_terms_and_unaffected_pin(self):
        world = make_world(country_options(), seed=3, stop_before="pre_fill")
        wire = json.loads(json.dumps(world.fill_slot_data()))
        p = wire["content_plan"]
        t = next(t for t in p["tracks"] if t.get("package_id") == PACKAGE["id"])
        p["sanity"].pop("rules_version", None)
        p["item_boxes"].pop("pickup_rules")
        p["checks"] = [c for c in p["checks"] if c["kind"] not in sanity.KINDS]
        p["checks"].extend(sanity.checks(p["sanity"], p["tracks"], p["entries"], p["pads"],
                                          p["encounters"], p.get("capability"), {PACKAGE["id"]: PACKAGE}))
        for c in p["checks"]:
            if c["owner"] == t["id"] and c["kind"] == "box":
                c.pop("boost", None)
        # This is the actual pre-correction combination: sanity fallback USF,
        # crate-seated AP boxes and lap at zero.
        self.assertTrue(all(c.get("boost") == 2 for c in p["checks"]
                            if c["owner"] == t["id"] and c["kind"] in sanity.KINDS))
        self.assertTrue(content_plan.validate(p))
        self.assertEqual(make_world({}, passthrough=wire, stop_before="pre_fill").ctr_content_plan, p)
        other = copy.deepcopy(PACKAGE)
        other["files"][0]["sha256"] = "0" * 64
        inv = sanity.inventory(t, other, dict(rules_version=1))
        self.assertEqual(inv["needs"]["weapon_crate"]["2"]["needs"], "usf")
        bad = copy.deepcopy(world.ctr_content_plan)
        bad["item_boxes"]["pickup_rules"] = ["retail:0"]
        with self.assertRaises(OptionError):
            content_plan.validate(bad)
