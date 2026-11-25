"""CV1: the bundled Cortex Vortex as a merged mode build (Saphi 1.1.5 main pair,
1.1.6 relic pair), with the A6-15b crate rulings carried by position."""
import copy
import json
import unittest

from Options import OptionError
from .. import content_plan, cortex_vortex, sanity
from .test_content_plan import make_world
from .test_vortex_sanity import vortex_options

SAPHI_1_1_2_LEV = "d3189b6263c2a13c9f289e5ad7776bc78cca1cf64be5afa5085d7a727e6efd36"


def cortex_row(plan):
    return next(r for r in plan["sanity"]["tracks"] if r["track_id"] == "cortex_vortex")


class TestCortexVortexMerged(unittest.TestCase):
    def test_pins_are_distinct_digests(self):
        pins = (cortex_vortex.CORTEX_LEV_SHA256, cortex_vortex.CORTEX_VRM_SHA256,
                cortex_vortex.CORTEX_RELIC_LEV_SHA256, cortex_vortex.CORTEX_RELIC_VRM_SHA256,
                cortex_vortex.CORTEX_LEGACY_LEV_SHA256)
        self.assertEqual(len(set(pins)), 5)
        for pin in pins:
            self.assertRegex(pin, r"^[0-9a-f]{64}$")
        self.assertEqual(sanity.CORTEX_LEV_SHA256, cortex_vortex.CORTEX_LEV_SHA256)

    def test_rulings_carry_by_position(self):
        # 1.1.5's weapon and Wumpa crates are the ruled build's crates at the
        # same places in the same order, so the row is the ruled row re-keyed.
        new = sanity.CATALOG[cortex_vortex.CORTEX_LEV_SHA256]
        old = sanity.CATALOG[cortex_vortex.CORTEX_LEGACY_LEV_SHA256]
        self.assertEqual(new["lev_sha256"], cortex_vortex.CORTEX_LEV_SHA256)
        self.assertEqual(old["lev_sha256"], cortex_vortex.CORTEX_LEGACY_LEV_SHA256)
        self.assertEqual(new["counts"], [69, 7, 0])
        self.assertEqual(dict(new, lev_sha256=None), dict(old, lev_sha256=None))
        # The nine Boost 0 exceptions (weapon 62 to 69, Wumpa crate 1) stay
        # out of the needs table; everything else keeps the Boost 2 floor.
        self.assertEqual(set(map(int, new["needs"]["weapon_crate"])), set(range(1, 62)))
        self.assertEqual(set(map(int, new["needs"]["wumpa_crate"])), set(range(2, 8)))

    def test_inventory_follows_the_room(self):
        track = dict(id="cortex_vortex", origin="cortex_vortex", display_name="Cortex Vortex")
        self.assertEqual(sanity.inventory(track)["lev_sha256"], cortex_vortex.CORTEX_LEV_SHA256)
        legacy = dict(rules_version=4, tracks=[dict(track_id="cortex_vortex",
                                                    lev_sha256=cortex_vortex.CORTEX_LEGACY_LEV_SHA256)])
        self.assertEqual(sanity.inventory(track, record=legacy)["lev_sha256"], cortex_vortex.CORTEX_LEGACY_LEV_SHA256)
        other = dict(rules_version=4, tracks=[dict(track_id="cortex_vortex", lev_sha256=SAPHI_1_1_2_LEV)])
        self.assertEqual(sanity.inventory(track, record=other)["lev_sha256"], cortex_vortex.CORTEX_LEV_SHA256)
        self.assertEqual(sanity.inventory(track, record=dict(rules_version=1))["lev_sha256"],
                         sanity.CATALOG["cortex_vortex"]["lev_sha256"])

    def test_new_rooms_name_the_main_pair_and_older_rooms_still_admit(self):
        for mode in ("off", "shared_global", "per_character"):
            world = make_world(vortex_options(progressive_boost=mode), seed=3, stop_before="pre_fill")
            wire = json.loads(json.dumps(world.fill_slot_data()))
            plan = wire["content_plan"]
            self.assertEqual(cortex_row(plan)["lev_sha256"], cortex_vortex.CORTEX_LEV_SHA256)
            # A room generated before CV1 carries the all-in-one build's pin.
            older = copy.deepcopy(wire)
            cortex_row(older["content_plan"])["lev_sha256"] = cortex_vortex.CORTEX_LEGACY_LEV_SHA256
            with self.subTest(mode=mode, room="before CV1"):
                self.assertTrue(content_plan.validate(older["content_plan"]))
                tracker = make_world({}, passthrough=older, stop_before="pre_fill")
                self.assertEqual(older["content_plan"], tracker.ctr_content_plan)
            # Same checks, same terms: recomputed from the older row's catalog entry.
            p = older["content_plan"]
            recomputed = sanity.checks(p["sanity"], p["tracks"], p["entries"], p["pads"], p["encounters"],
                                       p.get("capability"), {pkg["id"]: pkg for pkg in p["packages"]})
            self.assertEqual(recomputed, [c for c in plan["checks"] if c["kind"] in sanity.KINDS])
            self.assertTrue(any(c["owner"] == "cortex_vortex" for c in recomputed))
            for digest in (SAPHI_1_1_2_LEV, cortex_vortex.CORTEX_RELIC_LEV_SHA256, "0" * 64):
                bad = copy.deepcopy(plan)
                cortex_row(bad)["lev_sha256"] = digest
                with self.subTest(mode=mode, digest=digest[:8]), self.assertRaises(OptionError):
                    content_plan.validate(bad)


class TestBundledCopy(unittest.TestCase):
    def package(self, relic=None):
        pin = lambda role, sha: {"role": role, "sha256": sha}
        p = {"content_id": "cortex-vortex", "files": [pin("lev", cortex_vortex.CORTEX_LEV_SHA256),
                                                     pin("vrm", cortex_vortex.CORTEX_VRM_SHA256)]}
        if relic:
            p["relic_files"] = [pin("lev", relic[0]), pin("vrm", relic[1])]
        return p

    def test_relic_pair_decides(self):
        self.assertTrue(cortex_vortex.bundled_copy(self.package()))
        self.assertTrue(cortex_vortex.bundled_copy(self.package(
            (cortex_vortex.CORTEX_RELIC_LEV_SHA256, cortex_vortex.CORTEX_RELIC_VRM_SHA256))))
        self.assertFalse(cortex_vortex.bundled_copy(self.package(("1" * 64, "2" * 64))))


class TestSoloSeesBothPairs(unittest.TestCase):
    def test_both_pairs_needed(self):
        import os, tempfile
        from ..tools.solo import ctr_solo
        with tempfile.TemporaryDirectory() as assets:
            folder = os.path.join(assets, "tracks", "cortex-vortex")
            os.makedirs(folder)
            for name in ("CVortex Arcade All.lev", "CVortex Arcade All.vrm", "CVortex Arcade All.sca"):
                open(os.path.join(folder, name), "wb").close()
            self.assertFalse(ctr_solo._cortex_installed(assets))
            for name in ("CVortex Relic.lev", "CVortex Relic.vrm"):
                open(os.path.join(folder, name), "wb").close()
            self.assertTrue(ctr_solo._cortex_installed(assets))


if __name__ == "__main__":
    unittest.main()
