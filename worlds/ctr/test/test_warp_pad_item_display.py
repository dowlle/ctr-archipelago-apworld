"""Guards for the warp-pad item display option (issue #59).

Players reported that a pad crams every unclaimed item on its destination -- race,
CTR challenge, relics, podium rungs -- into one rotation, so a floating sapphire
could be the CTR check or the relic check and there is no way to tell. #59 asks
for Icebound's shape as an option: one slot per reward type, rotating within the
type, alongside the current display rather than replacing it.

The apworld owns the OPTION and its slot_data mirror; the pad render is native's
half (its glow pass already enumerates a destination's unchecked reward bits and
cycles a 3-wide window over them, which is the one_pile behaviour). So what these
tests can prove is exactly what the apworld is responsible for:

- the option exists, defaults to one_pile, and the wire value matches it;
- by_reward_type reaches slot_data as 1 under the key native will read;
- it is ADDITIVE: schema_version does not move, so an older client (which will
  not find the key and defaults it to 0) keeps today's behaviour;
- it is generation-neutral: same seed, same options bar this one, and the
  location set, the item pool and the whole rest of slot_data are identical. A
  display setting must never move a check, an item or a gate.
- Universal Tracker does NOT restore it (it steers no logic, so the tracking
  player's own preference is the right one to keep).
"""

from test.general import setup_multiworld

from .. import ctrAPWorld
from . import CTRTestBase

WIRE_KEY = "warp_pad_item_display"
FIXED_SEED = 5949


class TestWarpPadItemDisplayDefault(CTRTestBase):
    """The default is the shipped behaviour."""

    run_default_tests = False
    options = {}

    def test_default_is_one_pile(self):
        opt = self.world.options.warp_pad_item_display
        self.assertEqual(opt.value, 0)
        self.assertEqual(opt.current_key, "one_pile")

    def test_wire_value_matches_the_option(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ctr_options"][WIRE_KEY], 0)

    def test_ut_does_not_restore_it(self):
        # Display only: a tracking player keeps their own preference, so the
        # restore pass must leave it alone even when the seed says otherwise.
        world = self.world
        world.options.warp_pad_item_display.value = 1
        world._ut_restore_options({"ctr_options": {WIRE_KEY: 0},
                                   "warp_pad_unlock": {}, "podium_checks": {}})
        self.assertEqual(world.options.warp_pad_item_display.value, 1)


class TestWarpPadItemDisplayByRewardType(CTRTestBase):
    """by_reward_type reaches the wire and changes nothing else."""

    options = {"warp_pad_item_display": "by_reward_type"}

    def test_wire_value_is_one(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ctr_options"][WIRE_KEY], 1)

    def test_schema_version_is_not_bumped(self):
        # Additive key (the one_lap_cups / death_link precedent): an older client
        # never sees it and defaults to 0 == one pile == what it already does.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 6)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 6)


class TestWarpPadItemDisplayIsGenerationNeutral(CTRTestBase):
    """Same seed, only this option varied: nothing but the key itself moves."""

    run_default_tests = False
    options = {}

    def _generate(self, value):
        # The option is set BEFORE the generation steps run, so this really does
        # compare two generations and not one generation read twice.
        mw = setup_multiworld(ctrAPWorld, seed=FIXED_SEED,
                              options={"warp_pad_item_display": value})
        return mw, mw.worlds[1]

    def test_locations_items_and_slot_data_are_identical(self):
        mw_a, world_a = self._generate(0)
        mw_b, world_b = self._generate(1)

        names_a = sorted(loc.name for loc in mw_a.get_locations(1))
        names_b = sorted(loc.name for loc in mw_b.get_locations(1))
        self.assertEqual(names_a, names_b)

        pool_a = sorted(item.name for item in mw_a.itempool)
        pool_b = sorted(item.name for item in mw_b.itempool)
        self.assertEqual(pool_a, pool_b)

        sd_a = world_a.fill_slot_data()
        sd_b = world_b.fill_slot_data()
        self.assertEqual(sd_a["ctr_options"][WIRE_KEY], 0)
        self.assertEqual(sd_b["ctr_options"][WIRE_KEY], 1)
        del sd_a["ctr_options"][WIRE_KEY]
        del sd_b["ctr_options"][WIRE_KEY]
        self.assertEqual(sd_a, sd_b,
                         "a display option moved something on the wire")
