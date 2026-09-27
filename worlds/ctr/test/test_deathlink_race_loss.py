"""Guards for the DeathLink race_loss value (issue #286).

Native reads ``ctr_options.death_link`` as a plain integer and gives 3 its own
receive effect: a received death ends the current adventure race as a
last-place loss instead of forcing a mask reset. The apworld owns the option
and its wire mirror, so these tests pin exactly that half:

- the pre-existing values keep their integers and off stays the default;
- race_loss reaches slot_data as 3 under the key native reads;
- it is additive: schema_version does not move (older natives fall back to the
  mask reset for an unknown nonzero value);
- Universal Tracker does not restore it (it steers no logic), and a seed
  carrying 3 still passes through interpret_slot_data and the restore pass.
"""

from .. import ctrAPWorld
from ..Options import DeathLink
from . import CTRTestBase

WIRE_KEY = "death_link"


class TestDeathLinkValues(CTRTestBase):
    """The integer values are the wire contract with native."""

    run_default_tests = False
    options = {}

    def test_values_are_stable(self):
        self.assertEqual(DeathLink.option_off, 0)
        self.assertEqual(DeathLink.option_mask_reset, 1)
        self.assertEqual(DeathLink.option_any_hit, 2)
        self.assertEqual(DeathLink.option_race_loss, 3)

    def test_default_is_off(self):
        opt = self.world.options.death_link
        self.assertEqual(opt.value, 0)
        self.assertEqual(opt.current_key, "off")
        self.assertEqual(self.world.fill_slot_data()["ctr_options"][WIRE_KEY], 0)


class TestDeathLinkRaceLoss(CTRTestBase):
    """race_loss reaches the wire as 3."""

    options = {"death_link": "race_loss"}

    def test_wire_value_is_three(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ctr_options"][WIRE_KEY], 3)

    def test_schema_version_is_not_bumped(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 16)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 16)

    def test_ut_passthrough_and_restore(self):
        # interpret_slot_data hands the seed's slot_data back verbatim, so the
        # value survives into re_gen_passthrough unchanged.
        slot_data = self.world.fill_slot_data()
        passthrough = ctrAPWorld.interpret_slot_data(slot_data)
        self.assertEqual(passthrough["ctr_options"][WIRE_KEY], 3)

        # The restore pass accepts a seed carrying 3 and leaves the tracking
        # player's own DeathLink setting alone: it steers no logic.
        world = self.world
        world.options.death_link.value = DeathLink.option_mask_reset
        world._ut_restore_options(passthrough)
        self.assertEqual(world.options.death_link.value,
                         DeathLink.option_mask_reset)
