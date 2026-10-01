"""pre_fill builds no second multiworld.

CTR's pre_fill used to dry-run the whole room on a mirror MultiWorld to
predict whether two-stage warp-pad gating would FillError, and collapsed every
stage-2 gate when it predicted one. In 0.2.3 that probe never predicted a
collapse in 6,300+ probed seeds (2 to 25 slots) while costing about 30% of
generation time in a 1,000-slot room, so it was removed in favour of measured
fill success. This pins the removal: a two-stage multiworld goes through
pre_fill without constructing another MultiWorld, keeps its stage-2 gates, and
fills.
"""
import unittest
from unittest import mock

import BaseClasses
from Fill import distribute_items_restrictive
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld

BEFORE_PRE_FILL = ("generate_early", "create_regions", "create_items",
                   "set_rules", "connect_entrances", "generate_basic")
TWO_STAGE = {"warppad_unlock_requirements": "randomized",
             "two_stage_density": "full"}


class TestPreFillBuildsNoMirror(unittest.TestCase):
    def test_two_slot_two_stage_room(self):
        mw = setup_multiworld([ctrAPWorld, ctrAPWorld], BEFORE_PRE_FILL,
                              seed=20261001, options=TWO_STAGE)
        for p in mw.player_ids:
            self.assertTrue(mw.worlds[p]._ctr_two_stage_active,
                            "fixture slot is not two-stage")
        stage2 = {p: dict(mw.worlds[p].warp_pad_unlock_stage2_concrete)
                  for p in mw.player_ids}

        built = []
        original_init = BaseClasses.MultiWorld.__init__

        def counting_init(self_, *args, **kwargs):
            built.append(args)
            original_init(self_, *args, **kwargs)

        with mock.patch.object(BaseClasses.MultiWorld, "__init__", counting_init):
            call_all(mw, "pre_fill")
        self.assertEqual(built, [], "pre_fill constructed a MultiWorld")
        self.assertFalse(hasattr(mw, "_ctr_room_probe_verdict"))

        for p in mw.player_ids:
            with self.subTest(player=p):
                self.assertTrue(stage2[p], "no concrete stage-2 requirements")
                self.assertEqual(
                    dict(mw.worlds[p].warp_pad_unlock_stage2_concrete), stage2[p])
                wire = mw.worlds[p].fill_slot_data()["warp_pad_unlock"]
                self.assertTrue(
                    any(entry["stage2"]["type"] != 0 for entry in wire.values()),
                    "slot_data emitted no real stage-2 requirement")

        distribute_items_restrictive(mw)
        self.assertTrue(mw.can_beat_game())


if __name__ == "__main__":
    unittest.main()
