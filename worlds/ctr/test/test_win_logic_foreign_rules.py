"""A rule another world wraps after CTR's `set_rules` cannot be exported.

SlotLock 0.11.3 locks a slot in `stage_pre_fill` by replacing every exit of
its origin region with `has("Unlock <slot>") and old_rule(state)`. That rule
has no term, so the `win_logic` exporter raised and the whole generation
failed (Discord report, 2026-10-25). `fill_slot_data` now omits the block for
that slot (native: 0.2.3 race-loss behaviour). A plain lambda CTR itself
installs during `set_rules` still raises, so the parity guard is unchanged.
"""
import unittest

from test.general import setup_multiworld

from .. import ctrAPWorld
from ..logic_terms import term_of
from ..win_logic import ForeignRuleError, WinLogicExportError, snapshot_rules, wire_block

PLAYER = 1
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _slotlock_wrap(world):
    """SlotLock's `stage_pre_fill` loop, with a foreign unlock item."""
    origin = world.get_region(world.origin_region_name)
    for exit_ in origin.get_exits():
        old_rule = exit_.access_rule
        exit_.access_rule = (lambda state, old_rule=old_rule:
                             state.has("Unlock Someone", 2) and old_rule(state))


class TestForeignRuleWrap(unittest.TestCase):

    def setUp(self):
        self.mw = setup_multiworld(ctrAPWorld, STEPS, seed=3)
        self.world = self.mw.worlds[PLAYER]

    def test_unwrapped_seed_emits_block(self):
        self.assertIn("win_logic", self.world.fill_slot_data())

    def test_slotlock_wrap_omits_block(self):
        _slotlock_wrap(self.world)
        with self.assertRaises(ForeignRuleError):
            wire_block(self.world)
        with self.assertLogs("worlds.ctr.slot_data", level="WARNING"):
            slot_data = self.world.fill_slot_data()
        self.assertNotIn("win_logic", slot_data)

    def test_own_plain_lambda_still_raises(self):
        """A rule that had no term when `set_rules` finished is CTR's own
        unexportable rule, not a foreign wrap: generation must still fail."""
        origin = self.world.get_region(self.world.origin_region_name)
        exit_ = origin.get_exits()[0]
        self.assertIsNotNone(term_of(exit_))
        exit_.access_rule = lambda state: True
        snapshot_rules(self.world)  # as if set_rules had installed it
        with self.assertRaises(WinLogicExportError) as caught:
            self.world.fill_slot_data()
        self.assertNotIsInstance(caught.exception, ForeignRuleError)


if __name__ == "__main__":
    unittest.main()
