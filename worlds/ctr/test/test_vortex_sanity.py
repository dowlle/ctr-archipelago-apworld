"""Shipped Vortex ordinal partition, persisted rooms and Tracker capability boundaries."""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from .. import content_plan, sanity
from .test_content_plan import make_world, profile_options


def vortex_options(**extra):
    options = dict(profile_options(), itemboxsanity=50, wumpasanity="both",
                   item_box_count=50, progressive_stats="off", shortcut_knowledge=1, **extra)
    options["content_pool"]["tracks"]["cortex_vortex"] = True
    return options


class TestVortexSanity(unittest.TestCase):
    def test_exact_partition_and_revision(self):
        track = dict(id="cortex_vortex", origin="cortex_vortex", display_name="Cortex Vortex")
        inv = sanity.inventory(track)
        self.assertEqual(inv["lev_sha256"], sanity.CORTEX_LEV_SHA256)
        self.assertEqual(inv["counts"], [69, 7, 0])
        self.assertEqual(set(map(int, inv["needs"]["weapon_crate"])), set(range(1, 62)))
        self.assertEqual(set(map(int, inv["needs"]["wumpa_crate"])), set(range(2, 8)))
        for kind, needs in inv["needs"].items():
            for ordinal in needs:
                # Named packages using these exact bytes also retain their
                # original terms in a Sewer-only version-1 room.
                self.assertEqual(sanity.object_needs(inv, kind, int(ordinal), {"rules_version": 1}), {})
        row = dict(track_id=track["id"], lev_sha256=inv["lev_sha256"], weapon_crate=list(range(1, 70)),
                   wumpa_crate=list(range(1, 8)), wumpa_fruit=[])
        entries = [dict(id="entry/vortex", kind="track", track_id=track["id"], modes=["trophy"])]
        pads = [dict(id="pad:0", entry_id=entries[0]["id"])]
        for mode in range(3):
            for tier in range(3):
                record = dict(rules_version=2, shortcut_knowledge=tier, tracks=[row])
                self.assertEqual(sanity.eligible(track, 0, record, None, None), list(range(1, 70)))
                checks = sanity.checks(record, [track], entries, pads, [], dict(boost_mode=mode, stats_mode=0))
                for c in checks:
                    n = int(c["display_name"].rsplit(" ", 1)[1])
                    exception = n >= 62 if c["kind"] == "weapon_crate" else n == 1
                    self.assertEqual(c.get("boost", 0), 2 if mode and not exception else 0)
        self.assertNotEqual(sanity.inventory(track, record={})["lev_sha256"], inv["lev_sha256"])

    def test_generated_tracker_boost_boundary_and_digest_refusal(self):
        for mode in ("off", "shared_global", "per_character"):
            for blue in (False, True):
                world = make_world(vortex_options(progressive_boost=mode, progressive_boost_blue_fire=blue),
                                   seed=3, stop_before="pre_fill")
                wire = json.loads(json.dumps(world.fill_slot_data()))
                plan = wire["content_plan"]
                self.assertTrue(content_plan.validate(plan))
                row = next(r for r in plan["sanity"]["tracks"] if r["track_id"] == "cortex_vortex")
                self.assertEqual(row["lev_sha256"], sanity.CORTEX_LEV_SHA256)
                self.assertEqual(plan["sanity"]["rules_version"], 2)
                self.assertFalse(any(c["owner"] == "cortex_vortex" and c["kind"] == "box" for c in plan["checks"]))
                tracker = make_world({}, passthrough=wire, stop_before="pre_fill")
                self.assertEqual(plan, tracker.ctr_content_plan)
                for rank in range(4):
                    for w in (world, tracker):
                        state = CollectionState(w.multiworld)
                        for name, count in w.multiworld.get_all_state().prog_items[1].items():
                            for _ in range(min(count, rank) if name.startswith("Progressive Boost") else count):
                                state.collect(w.create_item(name), True)
                        for c in plan["checks"]:
                            if c["owner"] != "cortex_vortex" or c["kind"] not in sanity.KINDS:
                                continue
                            n = int(c["display_name"].rsplit(" ", 1)[1])
                            exception = n >= 62 if c["kind"] == "weapon_crate" else n == 1
                            with self.subTest(mode=mode, blue=blue, rank=rank, crate=c["display_name"]):
                                self.assertEqual(w.multiworld.get_location(c["display_name"], 1).can_reach(state),
                                                 exception or mode == "off" or rank >= 2)
                for digest in ("0" * 64, sanity.CATALOG["cortex_vortex"]["lev_sha256"]):
                    bad = copy.deepcopy(plan)
                    next(r for r in bad["sanity"]["tracks"] if r["track_id"] == "cortex_vortex")["lev_sha256"] = digest
                    with self.assertRaises(OptionError):
                        content_plan.validate(bad)

    def legacy_room(self, version):
        world = make_world(vortex_options(progressive_boost="shared_global"), seed=3, stop_before="pre_fill")
        wire = json.loads(json.dumps(world.fill_slot_data()))
        plan = wire["content_plan"]
        if version is None:
            del plan["sanity"]["rules_version"]
        else:
            plan["sanity"]["rules_version"] = version
        next(r for r in plan["sanity"]["tracks"] if r["track_id"] == "cortex_vortex")["lev_sha256"] = sanity.CATALOG["cortex_vortex"]["lev_sha256"]
        # Use Medium so the inherited Sewer correction changes no picks.
        plan["checks"] = [c for c in plan["checks"] if c["kind"] not in sanity.KINDS]
        plan["checks"].extend(sanity.checks(plan["sanity"], plan["tracks"], plan["entries"], plan["pads"],
                                           plan["encounters"], plan.get("capability"),
                                           {p["id"]: p for p in plan["packages"]}))
        self.assertTrue(content_plan.validate(plan))
        self.assertEqual(make_world({}, passthrough=wire, stop_before="pre_fill").ctr_content_plan, plan)
        self.assertTrue(all("boost" not in c for c in plan["checks"]
                            if c["owner"] == "cortex_vortex" and c["kind"] in sanity.KINDS))

    def test_unversioned_room_keeps_original_pin_picks_and_terms(self):
        self.legacy_room(None)

    def test_sewer_version_one_room_keeps_original_vortex_terms(self):
        self.legacy_room(1)
