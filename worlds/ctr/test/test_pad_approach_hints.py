"""Pad Approach Hints (native #124, ruling of 2026-07-20, built 2026-11-02).

The option is a client setting: off by default, display and hint only. It
rides the content-plan envelope as `pad_approach_hints: true` only when on,
so an option-off room's slot_data is unchanged. The draw never reads it. The
paired native reader is ap/ap_pad_hints.h (tools/test-pad-approach-hints.cpp).
"""
import copy
import json
import unittest

from Options import OptionError

from .. import content_plan
from ..Options import PadApproachHints, ap_ctr_option_groups
from .test_content_plan import make_world
from .test_item_packs import pack_options


class TestPadApproachHints(unittest.TestCase):
    def test_off_by_default_in_the_display_group(self):
        self.assertEqual(PadApproachHints.default, 0)
        self.assertIn(PadApproachHints, ap_ctr_option_groups["Display"])
        self.assertIn("cannot be undone", PadApproachHints.__doc__)

    def test_off_sends_no_key(self):
        co = make_world(pack_options(), seed=3).fill_slot_data()["ctr_options"]
        self.assertNotIn("pad_approach_hints", co)

    def test_on_sends_true_and_takes_no_draw(self):
        off = make_world(pack_options(), seed=3)
        on = make_world(pack_options(pad_approach_hints=True), seed=3)
        wire_off, wire_on = off.fill_slot_data(), on.fill_slot_data()
        self.assertIs(wire_on["ctr_options"].pop("pad_approach_hints"), True)
        self.assertEqual(json.dumps(wire_on, sort_keys=True), json.dumps(wire_off, sort_keys=True))

    def test_tracker_restores_it(self):
        world = make_world(pack_options(pad_approach_hints=True), seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.options.pad_approach_hints.value, 1)
        self.assertEqual(other.fill_slot_data(), wire)

    def test_bad_value_refuses_on_restore(self):
        wire = json.loads(json.dumps(make_world(pack_options(pad_approach_hints=True), seed=3).fill_slot_data()))
        for value in (False, 1, "true"):
            forged = copy.deepcopy(wire)
            forged["ctr_options"]["pad_approach_hints"] = value
            with self.subTest(value=value), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)

    def test_listed_as_optional_envelope_key(self):
        self.assertIn("pad_approach_hints", content_plan.ENVELOPE_OPTIONAL)


if __name__ == "__main__":
    unittest.main()
