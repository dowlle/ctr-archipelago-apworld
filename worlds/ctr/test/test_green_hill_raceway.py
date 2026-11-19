"""Green Hill Raceway 2.0.0: laps, finishes and every ordinary crate at Boost 0 (Stef, 2026-11-18)."""
import copy
import json
from pathlib import Path
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from .. import characters, content_capability, content_item_boxes as boxes, content_plan, green_hill_raceway, sanity
from .test_content_plan import make_world, profile_options

PACKAGE = json.loads((Path(__file__).parent / "fixtures/green_hill_raceway_200.json").read_text())
TRACK = "custom/green-hill-raceway/2.0.0"
PICKUPS = (*sanity.KINDS, "box")


def green_options(**extra):
    options = profile_options()
    options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(PACKAGE)]
    options["content_pool"]["required_entries"] = [TRACK]
    options.update(itemboxsanity=50, wumpasanity="crates", progressive_stats="off",
                   progressive_boost="shared_global", shortcut_knowledge=1, item_box_count=15,
                   lap_completion_checks=True, podium_placement_checks=True, podium_held_fifth_rung=True,
                   logic_difficulty="hard")
    options.update(extra)
    return options


def state_at(world, rank, omit=None):
    state = CollectionState(world.multiworld)
    for name, num in world.multiworld.get_all_state().prog_items[1].items():
        if name == omit:
            continue
        if name.startswith("Progressive Boost"):
            num = min(num, rank)
        for _ in range(num):
            state.collect(world.create_item(name), True)
    return state


def own(p, kinds=None):
    return [c for c in p["checks"] if c["owner"] == TRACK and (kinds is None or c["kind"] in kinds)]


class TestGreenHillRaceway(unittest.TestCase):
    def test_all_ordinals_reachable_at_ranks_zero_one_two(self):
        for count in (0, 1, 5, 15, 50):
            for mode in ("shared_global", "per_character"):
                for wumpa in ("off", "crates"):
                    w = make_world(green_options(item_box_count=count, progressive_boost=mode, wumpasanity=wumpa,
                                                 character_unlocks=True), seed=3, stop_before="pre_fill")
                    wire = json.loads(json.dumps(w.fill_slot_data()))
                    p = wire["content_plan"]
                    self.assertTrue(content_plan.validate(p))
                    self.assertEqual(p["sanity"]["rules_version"], 6)
                    self.assertEqual(p["capability"]["finish_free"], [TRACK])
                    if count:
                        self.assertEqual(p["item_boxes"]["pickup_rules"], [TRACK])
                    else:
                        self.assertNotIn("pickup_rules", p.get("item_boxes", {}))
                    row = next(r for r in p["sanity"]["tracks"] if r["track_id"] == TRACK)
                    self.assertEqual(row["counts"], [20, 9, 0])
                    seats = [i * 20 // min(count, 15) + 1 for i in range(min(count, 15))]
                    self.assertEqual(row["weapon_crate"], sorted(set(range(1, 21)) - set(seats)))
                    self.assertEqual(row["wumpa_crate"], list(range(1, 10)) if wumpa == "crates" else [])
                    pickups = own(p, PICKUPS)
                    self.assertEqual(sum(c["kind"] == "box" for c in pickups), len(seats))
                    self.assertEqual(len(pickups), 20 + (9 if wumpa == "crates" else 0))
                    laps = own(p, ("lap",))
                    finishes = own(p, ("trophy", "podium"))
                    self.assertEqual(len(laps), 1)
                    self.assertEqual(sum(c["kind"] == "podium" for c in finishes), 5)
                    for c in pickups + laps + finishes:
                        self.assertEqual(c.get("boost", 0), 0, c)
                    self.assertEqual(len(w.multiworld.itempool), len(w.multiworld.get_unfilled_locations(1)))
                    restored = make_world({}, passthrough=wire, stop_before="pre_fill")
                    self.assertEqual(restored.ctr_content_plan, p)
                    for world in (w, restored):
                        for rank in (0, 1, 2):
                            state = state_at(world, rank)
                            for c in pickups + laps + finishes:
                                with self.subTest(count=count, mode=mode, wumpa=wumpa, rank=rank, check=c["display_name"]):
                                    self.assertTrue(world.multiworld.get_location(c["display_name"], 1).can_reach(state))

    def test_easy_difficulty_floors_stay_independent(self):
        # Reward requirements are retained: the difficulty option still raises win-type checks.
        p = make_world(green_options(logic_difficulty="easy"), seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p, (*PICKUPS, "lap"))))
        by_name = {c["display_name"].split(": ", 1)[1]: c.get("boost", 0) for c in own(p, ("trophy", "podium"))}
        self.assertEqual(by_name["Finish (Any Position)"], 0)
        self.assertGreaterEqual(by_name["Held 1st"], 1)

    def test_finish_kinds_at_hard(self):
        p = make_world(green_options(), seed=3, stop_before="pre_fill").ctr_content_plan
        track = next(t for t in p["tracks"] if t["id"] == TRACK)
        for stated in (None, False, True):
            pkg = copy.deepcopy(next(x for x in p["packages"] if x["id"] == PACKAGE["id"]))
            if stated is None:
                pkg["capabilities"].pop("super_turbo_pads", None)
            else:
                pkg["capabilities"]["super_turbo_pads"] = stated
            for kind, awards in (("trophy", ("win",)), ("podium", ("held_1st", "held_3rd", "held_5th", "finish_podium", "finish_any"))):
                for award in awards:
                    with self.subTest(stated=stated, kind=kind, award=award):
                        self.assertEqual(content_capability.check_boost(track, kind, award, p["capability"], pkg), 0)
            self.assertEqual(content_capability.finish_boost(track, p["capability"], pkg), 0)

    def test_off_mode_has_no_ranks(self):
        p = make_world(green_options(progressive_boost="off"), seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertNotIn("finish_free", p.get("capability", {}))
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p)))

    def test_exact_pin_only_and_older_versions(self):
        w = make_world(green_options(), seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        track = next(t for t in p["tracks"] if t["id"] == TRACK)
        for version in (0, 1, 2, 3, 4, 5):
            record = copy.deepcopy(p["sanity"])
            if version:
                record["rules_version"] = version
            else:
                record.pop("rules_version")
            checks = sanity.checks(record, p["tracks"], p["entries"], p["pads"], p["encounters"],
                                   p["capability"], {PACKAGE["id"]: PACKAGE})
            self.assertTrue(all(c.get("boost") == 2 for c in checks if c["owner"] == TRACK), version)
        other = copy.deepcopy(PACKAGE)
        other["files"][0]["sha256"] = "0" * 64
        self.assertFalse(green_hill_raceway.matches(other))
        inv = sanity.inventory(track, other, dict(rules_version=6))
        self.assertEqual(inv["needs"]["weapon_crate"]["1"]["needs"], "usf")
        # An old room (no marker) keeps its recorded ranks: USF for lap and finishes, even with a False descriptor.
        legacy = {k: v for k, v in p["capability"].items() if k != "finish_free"}
        self.assertEqual(content_capability.finish_boost(track, legacy, PACKAGE), 2)
        self.assertEqual(content_capability.check_boost(track, "podium", "finish_any", legacy, PACKAGE), 2)
        self.assertEqual(content_capability.finish_boost(track, p["capability"], PACKAGE), 0)
        for bad in ([], [TRACK, TRACK], ["retail:0"], [TRACK, "a"]):
            shaped = copy.deepcopy(p)
            shaped["capability"]["finish_free"] = bad
            with self.assertRaises(OptionError):
                content_plan.validate(shaped)
        stripped = copy.deepcopy(p)
        stripped["capability"].pop("finish_free")
        with self.assertRaises(OptionError):
            content_plan.validate(stripped)  # new-rule ranks no longer match a record without the marker
        bad = copy.deepcopy(p)
        next(pkg for pkg in bad["packages"] if pkg["id"] == PACKAGE["id"])["files"][0]["sha256"] = "0" * 64
        with self.assertRaises(OptionError):
            content_plan.validate(bad)
        self.assertEqual(boxes.box_terms(track, 1, legacy, PACKAGE, dict(shortcut_knowledge=1))[0], 2)
        self.assertEqual(boxes.box_terms(track, 1, p["capability"], PACKAGE, dict(shortcut_knowledge=1, pickup_rules=[TRACK]))[0], 0)

    def test_unrecognised_revision_keeps_generic_terms(self):
        options = green_options()
        options["content_pool"]["tracks"]["custom"][0]["files"][0]["sha256"] = "ab" * 32
        w = make_world(options, seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        self.assertLess(p["sanity"].get("rules_version", 0), 6)
        self.assertNotIn("pickup_rules", p.get("item_boxes", {}))
        self.assertNotIn("finish_free", p["capability"])
        self.assertTrue(all(c.get("boost", 0) == 2 for c in own(p, PICKUPS)))
        # The lap rank rides the pad route: out of logic until two ranks, as before the ruling.
        lap = own(p, ("lap",))[0]["display_name"]
        for rank, reach in ((0, False), (1, False), (2, True)):
            self.assertEqual(w.multiworld.get_location(lap, 1).can_reach(state_at(w, rank)), reach, rank)

    def test_free_pad_room_and_gated_pad_control(self):
        # Free pad: no racer lock on the Green Hill pad.
        for seed in range(12):
            w = make_world(green_options(character_unlocks=False, progressive_boost="shared_global"), seed=seed,
                           stop_before="pre_fill")
            p = w.ctr_content_plan
            entry = next(e for e in p["entries"] if e["kind"] == "track" and e["track_id"] == TRACK)
            pad = next(pad for pad in p["pads"] if pad["entry_id"] == entry["id"])
            self.assertIsNone(pad["racer_lock"])
            checks = own(p, (*PICKUPS, "lap", "trophy", "podium"))
            state = state_at(w, 0)
            self.assertTrue(all(w.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))
        # Gated pad control: omitting the racer or Key keeps every check unreachable at any rank.
        for seed in range(12):
            w = make_world(green_options(character_unlocks=True, racer_locked_pads=20,
                                         progressive_boost="per_character"), seed=seed, stop_before="pre_fill")
            p = w.ctr_content_plan
            entry = next(e for e in p["entries"] if e["kind"] == "track" and e["track_id"] == TRACK)
            pad = next(pad for pad in p["pads"] if pad["entry_id"] == entry["id"])
            if pad["racer_lock"] is not None:
                break
        else:
            self.fail("fixture did not produce a locked Green Hill pad")
        racer = characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
        checks = own(p, (*PICKUPS, "lap"))
        for omit in (racer, "Key"):
            state = state_at(w, 2, omit)
            self.assertTrue(all(not w.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))

    def test_mixed_room_preserves_other_candidates(self):
        from .test_country_speedway import PACKAGE as country_package
        from .test_royal_raceway import PACKAGE as royal_package
        from .test_toasty_terrace import PACKAGE as toasty_package
        options = green_options()
        options["content_pool"]["tracks"]["custom"] += [copy.deepcopy(x) for x in (country_package, toasty_package, royal_package)]
        options["content_pool"]["required_entries"] += ["custom/country-speedway/1.3.0", "custom/toasty-terrace/1.3.0",
                                                         "custom/royal-raceway/1.0.0"]
        p = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertEqual(p["sanity"]["rules_version"], 6)
        self.assertTrue(content_plan.validate(p))
        self.assertEqual(p["capability"]["finish_free"], [TRACK])
        self.assertEqual(p["capability"]["finish_floors"], ["custom/royal-raceway/1.0.0"])
        country = [c for c in p["checks"] if c["owner"] == "custom/country-speedway/1.3.0"]
        self.assertEqual(next(c for c in country if c["display_name"].endswith("Item Box 1"))["boost"], 2)
        royal = [c for c in p["checks"] if c["owner"] == "custom/royal-raceway/1.0.0"]
        self.assertTrue(all(c.get("boost", 0) == 2 for c in royal if c["kind"] in ("trophy", "podium")))
        self.assertTrue(all(c.get("boost", 0) == 0 for c in royal if c["kind"] in (*sanity.KINDS, "box")))
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p, (*PICKUPS, "lap"))))
