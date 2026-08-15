"""Guards for the AP-logo marker colour option (issue #212).

The native display revision (PR #213) shows non-original rewards as Archipelago
logos, coloured by item classification. #212 point 5 rules that colour scheme by
a `ctr_options.ap_item_type_colors` flag: enabled = classification colours,
disabled = one uniform greyish-white colour (0xd0, 0xd0, 0xc8). The native
default when the key is absent is colours enabled, so the shipped behaviour is
unchanged on seeds that never carried the key.

The apworld owns the OPTION and its slot_data mirror; the pad render is native's
half (already merged in #213). So what these tests can prove is exactly what the
apworld is responsible for:

- the option exists, is on by default, and the wire value matches it;
- off reaches slot_data as false under the locked wire name
  `ap_item_type_colors`;
- it is ADDITIVE: schema_version does not move, so an older client (which will
  not find the key and defaults it to colours enabled) keeps today's behaviour;
- it is generation-neutral: same seed, same options bar this one, and the
  location set, the item pool and the whole rest of slot_data are identical. A
  display setting must never move a check, an item or a gate.
- Universal Tracker does NOT restore it (it steers no logic, so the tracking
  player's own preference is the right one to keep).
"""

from test.general import setup_multiworld

from .. import ctrAPWorld
from . import CTRTestBase

WIRE_KEY = "ap_item_type_colors"
FIXED_SEED = 5949


class TestApItemTypeColorsDefault(CTRTestBase):
    """The default is colours on, matching the shipped native behaviour."""

    run_default_tests = False
    options = {}

    def test_default_is_on(self):
        opt = self.world.options.ap_item_type_colors
        self.assertTrue(opt.value)

    def test_wire_value_matches_the_option(self):
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["ctr_options"][WIRE_KEY])

    def test_ut_does_not_restore_it(self):
        # Display only: a tracking player keeps their own preference, so the
        # restore pass must leave it alone even when the seed says otherwise.
        world = self.world
        world.options.ap_item_type_colors.value = False
        world._ut_restore_options({"ctr_options": {WIRE_KEY: True},
                                   "warp_pad_unlock": {}, "podium_checks": {}})
        self.assertFalse(world.options.ap_item_type_colors.value)


class TestApItemTypeColorsOff(CTRTestBase):
    """off reaches the wire as false and changes nothing else."""

    options = {"ap_item_type_colors": False}

    def test_wire_value_is_false(self):
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["ctr_options"][WIRE_KEY])

    def test_schema_version_is_not_bumped(self):
        # Additive key (the one_lap_cups / death_link / warp_pad_item_display
        # precedent): an older client never sees it and defaults to colours
        # enabled, which is what it already does. Baseline is 7, the
        # unconditional #166 bump (Q28 ruling); this feature itself contributes
        # no further bump.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 7)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 7)


class TestApItemTypeColorsIsGenerationNeutral(CTRTestBase):
    """Same seed, only this option varied: nothing but the key itself moves."""

    run_default_tests = False
    options = {}

    def _generate(self, value):
        # The option is set BEFORE the generation steps run, so this really does
        # compare two generations and not one generation read twice.
        mw = setup_multiworld(ctrAPWorld, seed=FIXED_SEED,
                              options={"ap_item_type_colors": value})
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
