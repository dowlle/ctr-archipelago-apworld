"""Exact driven revision, original weapon ordinals and persistent room rules."""
import copy
import json
from pathlib import Path
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from unittest import mock

from .. import box_spots, characters, content_item_boxes as boxes, content_plan, sanity, toasty_terrace
from .test_content_plan import make_world, profile_options

PACKAGE = json.loads((Path(__file__).parent / "fixtures/toasty_terrace_130.json").read_text())
TRACK = "custom/toasty-terrace/1.3.0"


def toasty_options(**extra):
    options = profile_options()
    options["content_pool"]["tracks"]["custom"] = [copy.deepcopy(PACKAGE)]
    options["content_pool"]["required_entries"] = [TRACK]
    options.update(itemboxsanity=50, wumpasanity="crates", progressive_stats="off",
                   progressive_boost="shared_global", shortcut_knowledge=1, item_box_count=15,
                   lap_completion_checks=True)
    options.update(extra)
    return options


class TestToastyTerrace(unittest.TestCase):
    def test_counts_ranks_tracker_and_physical_split(self):
        # Crate seating as in rooms generated before TT1 shipped the 1.3.0
        # spot file; test_box_spots.TestToastyDeckSpots covers the spots.
        previous = {k: e for k, e in box_spots.CUSTOM_FILES.items() if k != "toasty-terrace"}
        with mock.patch.dict(box_spots.CUSTOM_FILES, previous, clear=True):
            self._counts_ranks_tracker_and_physical_split()

    def _counts_ranks_tracker_and_physical_split(self):
        for count in (0, 1, 5, 15, 50):
            for mode in ("off", "shared_global", "per_character"):
                for wumpa in ("off", "crates"):
                    w = make_world(toasty_options(item_box_count=count, progressive_boost=mode,
                                                 wumpasanity=wumpa), seed=3, stop_before="pre_fill")
                    wire = json.loads(json.dumps(w.fill_slot_data()))
                    p = wire["content_plan"]
                    self.assertTrue(content_plan.validate(p))
                    self.assertEqual(p["sanity"]["rules_version"], 4)
                    row = next(r for r in p["sanity"]["tracks"] if r["track_id"] == TRACK)
                    self.assertEqual(row["counts"], [20, 4, 0])
                    seats = [i * 20 // min(count, 15) + 1 for i in range(min(count, 15))]
                    self.assertEqual(row["weapon_crate"], sorted(set(range(1, 21)) - set(seats)))
                    self.assertEqual(row["wumpa_crate"], list(range(1, 5)) if wumpa == "crates" else [])
                    self.assertEqual(row["wumpa_fruit"], [])
                    if count == 15:
                        self.assertEqual(row["weapon_crate"], [4, 8, 12, 16, 20])
                    checks = [c for c in p["checks"] if c["owner"] == TRACK
                              and c["kind"] in (*sanity.KINDS, "box", "lap")]
                    self.assertEqual(sum(c["kind"] == "box" for c in checks), len(seats))
                    self.assertEqual(len(checks), 20 + (4 if wumpa == "crates" else 0) + 1)
                    self.assertTrue(all(c.get("boost", 0) == 0 for c in checks))
                    self.assertEqual(len(w.multiworld.itempool), len(w.multiworld.get_unfilled_locations(1)))
                    restored = make_world({}, passthrough=wire, stop_before="pre_fill")
                    self.assertEqual(restored.ctr_content_plan, p)
                    for world in (w, restored):
                        state = CollectionState(world.multiworld)
                        for name, num in world.multiworld.get_all_state().prog_items[1].items():
                            if not name.startswith("Progressive Boost"):
                                for _ in range(num):
                                    state.collect(world.create_item(name), True)
                        for c in checks:
                            with self.subTest(count=count, mode=mode, wumpa=wumpa, check=c["display_name"]):
                                self.assertTrue(world.multiworld.get_location(c["display_name"], 1).can_reach(state))

    def test_exact_pin_only_and_older_versions(self):
        w = make_world(toasty_options(), seed=3, stop_before="pre_fill")
        p = w.ctr_content_plan
        track = next(t for t in p["tracks"] if t["id"] == TRACK)
        for version in (0, 1, 2, 3):
            record = copy.deepcopy(p["sanity"])
            if version:
                record["rules_version"] = version
            else:
                record.pop("rules_version")
            checks = sanity.checks(record, p["tracks"], p["entries"], p["pads"], p["encounters"],
                                   p["capability"], {PACKAGE["id"]: PACKAGE})
            self.assertTrue(all(c.get("boost") == 2 for c in checks if c["owner"] == TRACK))
        other = copy.deepcopy(PACKAGE)
        other["files"][0]["sha256"] = "0" * 64
        self.assertFalse(toasty_terrace.matches(other))
        inv = sanity.inventory(track, other, dict(rules_version=4))
        self.assertEqual(inv["needs"]["weapon_crate"]["1"]["needs"], "usf")
        bad = copy.deepcopy(p)
        next(pkg for pkg in bad["packages"] if pkg["id"] == PACKAGE["id"])["files"][0]["sha256"] = "0" * 64
        with self.assertRaises(OptionError):
            content_plan.validate(bad)
        old = copy.deepcopy(PACKAGE)
        old["capabilities"].pop("super_turbo_pads")
        self.assertEqual(boxes.box_terms(track, 1, p["capability"], old, dict(shortcut_knowledge=1))[0], 2)

    def test_measured_turbo_metadata_and_disabled_sanity(self):
        from ..content_capability import finish_boost
        for stated in (None, False, True):
            options = toasty_options(itemboxsanity=0, wumpasanity="off")
            pkg = options["content_pool"]["tracks"]["custom"][0]
            if stated is None:
                pkg["capabilities"].pop("super_turbo_pads")
            else:
                pkg["capabilities"]["super_turbo_pads"] = stated
            p = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
            self.assertNotIn("sanity", p)
            pkg = next(pkg for pkg in p["packages"] if pkg["id"] == PACKAGE["id"])
            self.assertFalse(pkg["capabilities"]["super_turbo_pads"])
            track = next(t for t in p["tracks"] if t["id"] == TRACK)
            self.assertEqual(finish_boost(track, p["capability"], pkg), 0)
            self.assertEqual([c.get("boost", 0) for c in p["checks"] if c["owner"] == TRACK and c["kind"] == "box"], [0] * 15)

    def test_independent_pad_and_racer_gates(self):
        for seed in range(12):
            w = make_world(toasty_options(character_unlocks=True, racer_locked_pads=20,
                                         progressive_boost="per_character"), seed=seed, stop_before="pre_fill")
            p = w.ctr_content_plan
            entry = next(e for e in p["entries"] if e["kind"] == "track" and e["track_id"] == TRACK)
            pad = next(pad for pad in p["pads"] if pad["entry_id"] == entry["id"])
            if pad["racer_lock"] is not None:
                break
        else:
            self.fail("fixture did not produce a locked Toasty pad")
        racer = characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
        checks = [c for c in p["checks"] if c["owner"] == TRACK and c["kind"] in (*sanity.KINDS, "box")]
        for omit in (racer, "Key"):
            state = CollectionState(w.multiworld)
            for name, num in w.multiworld.get_all_state().prog_items[1].items():
                if name != omit:
                    for _ in range(num):
                        state.collect(w.create_item(name), True)
            self.assertTrue(all(not w.multiworld.get_location(c["display_name"], 1).can_reach(state) for c in checks))

    def test_mixed_room_preserves_country_exceptions(self):
        from .test_content_item_boxes import before_im1b
        self.enterContext(before_im1b())  # Country Speedway 1.3.0 crate seats, as before IM1b
        from .test_country_speedway import PACKAGE as country_package
        options = toasty_options()
        options["content_pool"]["tracks"]["custom"].append(copy.deepcopy(country_package))
        options["content_pool"]["required_entries"].append("custom/country-speedway/1.3.0")
        p = make_world(options, seed=3, stop_before="pre_fill").ctr_content_plan
        self.assertEqual(p["sanity"]["rules_version"], 4)
        checks = [c for c in p["checks"] if c["owner"] == "custom/country-speedway/1.3.0"]
        self.assertEqual(next(c for c in checks if c["display_name"].endswith("Item Box 1"))["boost"], 2)
        self.assertEqual(next(c for c in checks if c["display_name"].endswith("Wumpa Crate 2"))["boost"], 2)
        self.assertTrue(all(c.get("boost", 0) == 0 for c in p["checks"] if c["owner"] == TRACK
                            and c["kind"] in (*sanity.KINDS, "box", "lap")))
        self.assertTrue(content_plan.validate(p))
