"""The two-stage probe must mirror companion pre_fill (Bethany/Dex, 2026-08-21).

CTR's pre_fill dry-runs the room on a parallel mirror to predict whether the
two-stage pad gates would FillError, and collapses them only then. The mirror
used to skip the pre_fill step entirely, so a companion whose pre_fill locks
items into dedicated locations (KH2 places Donald, Goofy and keyblade
abilities into 66 of its own locations) presented the mirror's main fill with
66 phantom open locations. The mirror dead-ended, and CTR collapsed every
stage-2 gate on a room the real generator fills fine: measured 6 of 6 false
collapses on Dex's CTR plus KH2 pair, all 28 wire stage2 entries type 0.

These tests pin the fix from both directions:

* a REAL companion with a pre-fill lifecycle (KH2 itself, the reported game)
  must no longer collapse stage 2;
* a GENERIC minimal companion whose only interesting property is "more
  locations than pool items, difference placed in pre_fill" must not either,
  so the fix cannot silently regress into a KH2-only special case (the fix
  keys on CTR's own world class, never on a companion's name).
"""
import unittest

from test.general import setup_multiworld
from worlds.AutoWorld import AutoWorldRegister, World
from BaseClasses import Item, ItemClassification, Location, Region

from .. import ctrAPWorld

STEPS = ("generate_early", "create_regions", "create_items", "set_rules",
         "connect_entrances", "generate_basic", "pre_fill")
CTR_OPTIONS = {"warppad_unlock_requirements": 1, "two_stage_density": "full"}


def _assert_two_stage_survived(test, mw, ctr_player=1):
    ctr = mw.worlds[ctr_player]
    test.assertIsInstance(ctr, ctrAPWorld)
    test.assertFalse(
        getattr(ctr, "_ctr_force_collapse_stage2", False),
        "the probe collapsed stage 2 for a room the real generator fills")
    test.assertTrue(getattr(ctr, "_ctr_two_stage_active", False))
    test.assertTrue(
        getattr(ctr, "warp_pad_unlock_stage2_concrete", {}),
        "no concrete stage-2 requirements survived")


class TestKH2RoomKeepsStageTwo(unittest.TestCase):
    """The reported room shape: CTR plus a default-options KH2 slot. KH2's
    pre_fill always locks Donald, Goofy and keyblade abilities into dedicated
    locations, so any default KH2 slot reproduces the census mismatch that
    used to false-collapse the probe."""

    def test_ctr_plus_kh2_keeps_stage_two(self):
        from worlds.kh2 import KH2World
        mw = setup_multiworld([ctrAPWorld, KH2World], STEPS, seed=6062,
                              options=[CTR_OPTIONS, {}])
        _assert_two_stage_survived(self, mw)


class _PreFillCompanionItem(Item):
    game = "CTR Test PreFill Companion"


class _PreFillCompanion(World):
    """Minimal companion with the KH2 pre-fill SHAPE: 12 locations, 8 pool
    items, and pre_fill locks 4 dedicated items into the last 4 locations."""
    game = "CTR Test PreFill Companion"
    item_name_to_id = {f"Companion Item {i}": 990000 + i for i in range(12)}
    location_name_to_id = {f"Companion Spot {i}": 991000 + i for i in range(12)}
    hidden = True

    DEDICATED = 4

    def create_item(self, name):
        return _PreFillCompanionItem(
            name, ItemClassification.progression,
            self.item_name_to_id[name], self.player)

    def create_regions(self):
        menu = Region("Menu", self.player, self.multiworld)
        for name, code in self.location_name_to_id.items():
            menu.locations.append(Location(self.player, name, code, menu))
        self.multiworld.regions.append(menu)

    def create_items(self):
        for i in range(12 - self.DEDICATED):
            self.multiworld.itempool.append(
                self.create_item(f"Companion Item {i}"))

    def set_rules(self):
        self.multiworld.completion_condition[self.player] = (
            lambda state: state.has("Companion Item 0", self.player))

    def pre_fill(self):
        for i in range(12 - self.DEDICATED, 12):
            self.multiworld.get_location(
                f"Companion Spot {i}", self.player).place_locked_item(
                    self.create_item(f"Companion Item {i}"))


class TestGenericCompanionPreFill(unittest.TestCase):
    """The same census-mismatch shape with no real game involved, so the fix
    provably does not key on any specific companion."""

    @classmethod
    def tearDownClass(cls):
        AutoWorldRegister.world_types.pop(_PreFillCompanion.game, None)
        super().tearDownClass()

    def test_ctr_plus_prefill_companion_keeps_stage_two(self):
        mw = setup_multiworld([ctrAPWorld, _PreFillCompanion], STEPS,
                              seed=6062, options=[CTR_OPTIONS, {}])
        _assert_two_stage_survived(self, mw)

    def test_companion_shape_is_the_mismatch_shape(self):
        # The premise the regression rests on: before pre_fill runs, the
        # companion contributes more locations than pool items -- the exact
        # census the broken mirror used to dead-end on.
        mw = setup_multiworld(
            [ctrAPWorld, _PreFillCompanion],
            ("generate_early", "create_regions", "create_items", "set_rules",
             "connect_entrances", "generate_basic"),
            seed=6062, options=[CTR_OPTIONS, {}])
        comp_locs = [loc for loc in mw.get_locations(2)]
        comp_items = [it for it in mw.itempool if it.player == 2]
        self.assertEqual(len(comp_locs) - len(comp_items),
                         _PreFillCompanion.DEDICATED)


if __name__ == "__main__":
    unittest.main()
