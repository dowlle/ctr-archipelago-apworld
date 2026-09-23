"""Guards for the AP item box colour option (ruling R11, 2026-07-23).

R11 asked for colouring AP item boxes by the class of the item inside them as
a YAML toggle, `color_boxes_by_item`, because a box's colour tells the player
which checks matter. A 2026-09-23 ruling made it default to on; a seed
can turn it off for everyone, and each player can turn it off (never on) in
the client. Native (ap/ap_box_colour_logic.h) draws every box pink when the
key is off or absent.

What the apworld owns and these tests prove:

- the option exists, is on by default, and the wire value matches it;
- off reaches slot_data as false under the wire name `color_boxes_by_item`;
- it is ADDITIVE: schema_version does not move, so an older client (which
  never reads the key) keeps drawing pink boxes;
- it is generation-neutral: same seed, only this option varied, and the
  location set, the item pool and the rest of slot_data are identical;
- Universal Tracker does not restore it (it steers no logic).
"""

from test.general import setup_multiworld

from .. import ctrAPWorld
from . import CTRTestBase

WIRE_KEY = "color_boxes_by_item"
FIXED_SEED = 5949


class TestColorBoxesByItemDefault(CTRTestBase):
    """The default is on (2026-09-23 ruling)."""

    run_default_tests = False
    options = {}

    def test_default_is_on(self):
        self.assertTrue(self.world.options.color_boxes_by_item.value)

    def test_wire_value_matches_the_option(self):
        slot_data = self.world.fill_slot_data()
        self.assertIs(slot_data["ctr_options"][WIRE_KEY], True)

    def test_ut_does_not_restore_it(self):
        world = self.world
        world.options.color_boxes_by_item.value = True
        world._ut_restore_options({"ctr_options": {WIRE_KEY: False},
                                   "warp_pad_unlock": {}, "podium_checks": {}})
        self.assertTrue(world.options.color_boxes_by_item.value)

    def test_help_text_documents_the_colours_and_the_client_override(self):
        from ..Options import ColorBoxesByItem
        doc = ColorBoxesByItem.__doc__
        for phrase in ("purple: progression", "blue: useful", "cyan: filler",
                       "salmon: trap", "On (default)", "Item Box Colours",
                       "OFF (SEED)"):
            self.assertIn(phrase, doc)


class TestColorBoxesByItemOff(CTRTestBase):
    """off reaches the wire as false and needs no schema bump."""

    options = {"color_boxes_by_item": False, "box_locations": True}

    def test_wire_value_is_false(self):
        slot_data = self.world.fill_slot_data()
        self.assertIs(slot_data["ctr_options"][WIRE_KEY], False)

    def test_schema_version_is_not_bumped(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 16)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 16)


class TestColorBoxesByItemIsGenerationNeutral(CTRTestBase):
    """Same seed, only this option varied: nothing but the key itself moves."""

    run_default_tests = False
    options = {}

    def _generate(self, value):
        mw = setup_multiworld(ctrAPWorld, seed=FIXED_SEED,
                              options={"color_boxes_by_item": value,
                                       "box_locations": True})
        return mw, mw.worlds[1]

    def test_locations_items_and_slot_data_are_identical(self):
        mw_a, world_a = self._generate(True)
        mw_b, world_b = self._generate(False)

        names_a = sorted(loc.name for loc in mw_a.get_locations(1))
        names_b = sorted(loc.name for loc in mw_b.get_locations(1))
        self.assertEqual(names_a, names_b)

        pool_a = sorted(item.name for item in mw_a.itempool)
        pool_b = sorted(item.name for item in mw_b.itempool)
        self.assertEqual(pool_a, pool_b)

        sd_a = world_a.fill_slot_data()
        sd_b = world_b.fill_slot_data()
        self.assertTrue(sd_a["ctr_options"][WIRE_KEY])
        self.assertFalse(sd_b["ctr_options"][WIRE_KEY])
        del sd_a["ctr_options"][WIRE_KEY]
        del sd_b["ctr_options"][WIRE_KEY]
        self.assertEqual(sd_a, sd_b,
                         "a display option moved something on the wire")
