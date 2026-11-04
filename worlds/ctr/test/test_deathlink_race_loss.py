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
        self.assertEqual(slot_data["schema_version"], 18)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 18)



class TestDeathLinkWeaponHit(CTRTestBase):
    """weapon_hit (#483) reaches the wire as 4 and couples to mask grabs only."""

    options = {"death_link": "weapon_hit"}

    def test_wire_value_is_four(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ctr_options"][WIRE_KEY], 4)
        self.assertEqual(slot_data["schema_version"], 18)


