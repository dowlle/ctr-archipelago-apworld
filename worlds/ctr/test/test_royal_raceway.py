"""Royal Raceway 1.0.0: crates at Boost 0, every finished race at Boost 2."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from BaseClasses import CollectionState
from Options import OptionError
from .. import box_spots, characters, content_capability, content_item_boxes as boxes, content_plan, royal_raceway, sanity
from .test_content_plan import make_world, profile_options

PACKAGE = json.loads((Path(__file__).parent / "fixtures/royal_raceway_100.json").read_text())
TRACK = "custom/royal-raceway/1.0.0"
RACE = ("trophy", "podium", "lap", "ctr", "letter", "relic", "perfect")


def royal_options(**extra):
    options = profile_options()
    options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(PACKAGE)]
    options["content_pool"]["required_entries"] = [TRACK]
    options.update(itemboxsanity=50, wumpasanity="crates", progressive_stats="off",
                   progressive_boost="shared_global", shortcut_knowledge=1, item_box_count=15,
                   lap_completion_checks=True, podium_placement_checks=True, podium_held_fifth_rung=True)
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


def without_spot_file():
    """The catalog before IM1's Royal Raceway spot file: the crate seats that
    rooms generated before it keep."""
    return mock.patch.dict(box_spots.CUSTOM_FILES, {k: v for k, v in box_spots.CUSTOM_FILES.items()
                                                    if k != "royal-raceway"}, clear=True)


class TestRoyalRaceway(unittest.TestCase):
    @without_spot_file()
    def test_pickups_boost_zero_and_finishes_boost_two(self):
        for count in (0, 1, 5, 15, 50):
            for mode in ("shared_global", "per_character"):
                for wumpa in ("off", "crates"):
                    w = make_world(royal_options(item_box_count=count, progressive_boost=mode,
                                                 wumpasanity=wumpa, character_unlocks=True),
                                   seed=3, stop_before="pre_fill")
                    wire = json.loads(json.dumps(w.fill_slot_data()))
                    p = wire["content_plan"]
                    self.assertTrue(content_plan.validate(p))
                    self.assertEqual(p["sanity"]["rules_version"], 5)
                    if count:
                        self.assertEqual(p["item_boxes"]["pickup_rules"], [TRACK])
                    else:
                        self.assertNotIn("pickup_rules", p.get("item_boxes", {}))
                    self.assertEqual(p["capability"]["finish_floors"], [TRACK])
                    row = next(r for r in p["sanity"]["tracks"] if r["track_id"] == TRACK)
                    self.assertEqual(row["counts"], [28, 6, 0])
                    seats = [i * 28 // min(count, 15) + 1 for i in range(min(count, 15))]
                    self.assertEqual(row["weapon_crate"], sorted(set(range(1, 29)) - set(seats)))
                    self.assertEqual(row["wumpa_crate"], list(range(1, 7)) if wumpa == "crates" else [])
                    pickups = own(p, (*sanity.KINDS, "box"))
                    self.assertEqual(sum(c["kind"] == "box" for c in pickups), len(seats))
                    self.assertEqual(len(pickups), 28 + (6 if wumpa == "crates" else 0))
                    self.assertTrue(all(c.get("boost", 0) == 0 for c in pickups))
                    finishes = own(p, ("trophy", "podium", "lap"))
                    self.assertTrue(finishes)
                    self.assertEqual(sum(c["kind"] == "podium" for c in finishes), 5)
                    self.assertTrue(all(c.get("boost", 0) >= 2 for c in finishes if c["kind"] != "lap"), finishes)
                    self.assertEqual(len(w.multiworld.itempool), len(w.multiworld.get_unfilled_locations(1)))
                    restored = make_world({}, passthrough=wire, stop_before="pre_fill")
                    self.assertEqual(restored.ctr_content_plan, p)
                    for world in (w, restored):
                        for rank in (0, 1, 2):
                            state = state_at(world, rank)
                            for c in pickups + finishes:
                                with self.subTest(count=count, mode=mode, wumpa=wumpa, rank=rank, check=c["display_name"]):
                                    reach = world.multiworld.get_location(c["display_name"], 1).can_reach(state)
                                    self.assertEqual(reach, rank >= 2 if c in finishes else True)

    def test_every_race_kind_and_award_is_at_least_two(self):
        w = make_world(royal_options(),
                       seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        track = next(t for t in p["tracks"] if t["id"] == TRACK)
        pkg = next(x for x in p["packages"] if x["id"] == PACKAGE["id"])
        for difficulty in (0, 1, 2):
            record = dict(p["capability"], logic_difficulty=difficulty)
            for kind, awards in (("trophy", ("win",)), ("podium", ("held_1st", "held_3rd", "held_5th", "finish_podium", "finish_any")),
                                 ("ctr", ("win",)), ("relic", ("sapphire", "gold", "platinum")), ("perfect", ("perfect",))):
                for award in awards:
                    with self.subTest(difficulty=difficulty, kind=kind, award=award):
                        self.assertGreaterEqual(content_capability.check_boost(track, kind, award, record, pkg), 2)
        off = dict(p["capability"], boost_mode=0)
        self.assertEqual(content_capability.check_boost(track, "podium", "held_3rd", off, pkg), 0)

    def test_off_mode_has_no_ranks(self):
        w = make_world(royal_options(progressive_boost="off"), seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p)))

    def test_exact_pin_only_and_older_versions(self):
        w = make_world(royal_options(), seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        track = next(t for t in p["tracks"] if t["id"] == TRACK)
        for version in (0, 1, 2, 3, 4):
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
        self.assertFalse(royal_raceway.matches(other))
        inv = sanity.inventory(track, other, dict(rules_version=5))
        self.assertEqual(inv["needs"]["weapon_crate"]["1"]["needs"], "usf")
        legacy = {k: v for k, v in p["capability"].items() if k != "finish_floors"}
        self.assertEqual(content_capability.check_boost(track, "podium", "held_3rd", legacy, PACKAGE), 0)
        self.assertEqual(content_capability.check_boost(track, "podium", "held_1st", legacy, PACKAGE), 1)
        self.assertEqual(content_capability.check_boost(track, "podium", "held_3rd", p["capability"], PACKAGE), 2)
        # A descriptor stating no turbo pad cannot lower a floor the record names.
        quiet = copy.deepcopy(PACKAGE)
        quiet["capabilities"]["super_turbo_pads"] = False
        self.assertEqual(content_capability.finish_boost(track, p["capability"], quiet), 2)
        self.assertEqual(content_capability.finish_boost(track, legacy, quiet), 0)
        for bad in ([], [TRACK, TRACK], ["retail:0"], [TRACK, "a"]):
            shaped = copy.deepcopy(p)
            shaped["capability"]["finish_floors"] = bad
            with self.assertRaises(OptionError):
                content_plan.validate(shaped)
        stripped = copy.deepcopy(p)
        stripped["capability"].pop("finish_floors")
        with self.assertRaises(OptionError):
            content_plan.validate(stripped)  # new-rule ranks no longer match a record without the marker
        bad = copy.deepcopy(p)
        next(pkg for pkg in bad["packages"] if pkg["id"] == PACKAGE["id"])["files"][0]["sha256"] = "0" * 64
        with self.assertRaises(OptionError):
            content_plan.validate(bad)
        old = copy.deepcopy(PACKAGE)
        self.assertEqual(boxes.box_terms(track, 1, p["capability"], old, dict(shortcut_knowledge=1))[0], 2)

    def test_unrecognised_revision_inherits_pickup_and_finish_rules(self):
        options = royal_options()
        pkg = options["content_pool"]["tracks"]["custom"][0]
        pkg["files"][0]["sha256"] = "ab" * 32
        p = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertEqual(p["sanity"]["rules_version"], 5)
        self.assertIn(TRACK, p["item_boxes"]["pickup_rules"])
        self.assertEqual(p["capability"]["finish_floors"], [TRACK])
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p, (*sanity.KINDS, "box"))))

    def test_independent_pad_and_racer_gates(self):
        for seed in range(12):
            w = make_world(royal_options(character_unlocks=True, racer_locked_pads=20,
                                         progressive_boost="per_character"), seed=seed, stop_before="pre_fill")
            p = w.ctr_content_plan
            entry = next(e for e in p["entries"] if e["kind"] == "track" and e["track_id"] == TRACK)
            pad = next(pad for pad in p["pads"] if pad["entry_id"] == entry["id"])
            if pad["racer_lock"] is not None:
                break
        else:
            self.fail("fixture did not produce a locked Royal pad")
        racer = characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
        checks = own(p, (*sanity.KINDS, "box"))
        for omit in (racer, "Key"):
            state = state_at(w, 2, omit)
            self.assertTrue(all(not w.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))

    def test_mixed_room_preserves_other_candidates(self):
        from .test_country_speedway import PACKAGE as country_package
        from .test_toasty_terrace import PACKAGE as toasty_package
        options = royal_options()
        options["content_pool"]["tracks"]["custom"] += [copy.deepcopy(country_package), copy.deepcopy(toasty_package)]
        options["content_pool"]["required_entries"] += ["custom/country-speedway/1.3.0", "custom/toasty-terrace/1.3.0"]
        p = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertEqual(p["sanity"]["rules_version"], 5)
        self.assertTrue(content_plan.validate(p))
        country = [c for c in p["checks"] if c["owner"] == "custom/country-speedway/1.3.0"]
        self.assertEqual(next(c for c in country if c["display_name"].endswith("Item Box 1"))["boost"], 2)
        self.assertEqual(next(c for c in country if c["display_name"].endswith("Wumpa Crate 2"))["boost"], 2)
        toasty = [c for c in p["checks"] if c["owner"] == "custom/toasty-terrace/1.3.0"
                  and c["kind"] in (*sanity.KINDS, "box", "lap")]
        self.assertTrue(all(c.get("boost", 0) == 0 for c in toasty))
        self.assertTrue(all(c.get("boost", 0) == 0 for c in own(p, (*sanity.KINDS, "box"))))


class TestRoyalCupPrefix(unittest.TestCase):
    """A Royal leg's pickups wait for the earlier legs' finishes, never for Royal's own."""

    def test_prefix_rank_unit(self):
        from .. import content_cups
        record = dict(boost_mode=1, boost_blue_fire=False, stats_mode=0, logic_difficulty=2, shortcut_knowledge=0)
        royal = dict(id=TRACK, origin="custom", package_id=PACKAGE["id"], display_name="Royal Raceway", laps=3)
        retail = {f"retail:{i}": dict(id=f"retail:{i}", origin="retail", retail_id=i,
                                      display_name=content_plan.RETAIL[i], laps=3) for i in (0, 7)}
        tracks = dict(retail, **{TRACK: royal})
        packages = {PACKAGE["id"]: dict(PACKAGE, capabilities=dict(PACKAGE["capabilities"], super_turbo_pads=True))}
        cup = lambda *ids: dict(id="entry/cup:0", legs=[dict(id=f"entry/cup:0/leg:{i}", track_id=t) for i, t in enumerate(ids)])
        leg = lambda i: f"entry/cup:0/leg:{i}"
        # Royal first: its own pickups need nothing from the cup, the next leg needs Royal's finish.
        c = cup(TRACK, "retail:0")
        self.assertEqual(content_cups.prefix_boost(c, leg(0), tracks, record, packages), 0)
        self.assertEqual(content_cups.prefix_boost(c, leg(1), tracks, record, packages), 2)
        # An unrated earlier leg keeps the Royal leg reachable at rank zero.
        c = cup("retail:0", TRACK, "retail:0")
        self.assertEqual(content_cups.prefix_boost(c, leg(1), tracks, record, packages), 0)
        self.assertEqual(content_cups.prefix_boost(c, leg(2), tracks, record, packages), 2)
        # A Boost 2 finish on an earlier leg gates the Royal leg.
        c = cup("retail:7", TRACK)
        self.assertEqual(content_cups.prefix_boost(c, leg(1), tracks, record, packages), 2)
        self.assertEqual(content_cups.prefix_boost(c, leg(1), tracks, dict(record, boost_mode=0), packages), 0)

    def test_generated_cup_routes(self):
        from .. import content_cups
        for seed in range(1, 12):
            o = royal_options(item_box_count=5)
            o["content_pool"]["cups"] = {"count": 3, "composition": {"custom_legs": {"max": 4}}}
            p = make_world(o, seed=seed, stop_before="pre_fill").ctr_content_plan
            pickups = own(p, (*sanity.KINDS, "box"))
            tracks = {t["id"]: t for t in p["tracks"]}
            packages = {x["id"]: x for x in p["packages"]}
            entries = {e["id"]: e for e in p["entries"]}
            cups = [r for c in pickups if c["kind"] != "box" for r in c["routes"] if r["leg_id"] is not None]
            for cup_route in cups:
                entry = entries[cup_route["entry_id"]]
                index = next(i for i, l in enumerate(entry["legs"]) if l["id"] == cup_route["leg_id"])
                earlier = max([0] + [content_capability.finish_boost(tracks[l["track_id"]], p["capability"],
                                                                      packages.get(tracks[l["track_id"]].get("package_id")))
                                     for l in entry["legs"][:index]])
                prefix = content_cups.prefix_boost(entry, cup_route["leg_id"], tracks, p["capability"], packages)
                self.assertEqual(prefix, earlier)
                self.assertTrue(entry["legs"][index]["track_id"] == TRACK)
            if cups:
                return
        self.fail("no generated cup raced Royal Raceway")
