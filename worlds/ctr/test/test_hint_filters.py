"""Hint filters (A2-23): wait for Warp Pad Preview, progression only for pad and shop hints.

All three are client settings: off by default, hint policy only. Each rides the
content-plan envelope as `<name>: true` only when on, so an option-off room's
slot_data is unchanged and the draw never reads them. The paired native reader
is ap/ap_hint_filters_logic.h (tools/test-hint-filters.cpp).
"""
import copy
import json
import unittest

from Options import OptionError

from .. import content_plan
from ..Options import (PadHintsProgressionOnly, PadHintsWaitForSpoiler, ShopHintsProgressionOnly,
                       ap_ctr_option_groups)
from .test_content_plan import make_world
from .test_item_packs import pack_options

KEYS = content_plan.HINT_FILTER_KEYS


class TestHintFilters(unittest.TestCase):
    def test_off_by_default_and_grouped(self):
        for cls in (PadHintsWaitForSpoiler, PadHintsProgressionOnly, ShopHintsProgressionOnly):
            self.assertEqual(cls.default, 0)
        self.assertIn(PadHintsWaitForSpoiler, ap_ctr_option_groups["Display"])
        self.assertIn(PadHintsProgressionOnly, ap_ctr_option_groups["Display"])
        self.assertIn(ShopHintsProgressionOnly, ap_ctr_option_groups["Wumpa Shop"])

    def test_off_sends_no_key(self):
        co = make_world(pack_options(), seed=3).fill_slot_data()["ctr_options"]
        for key in KEYS:
            self.assertNotIn(key, co)

    def test_each_on_sends_true_and_takes_no_draw(self):
        base = make_world(pack_options(), seed=3).fill_slot_data()
        for key in KEYS:
            with self.subTest(key=key):
                wire = make_world(pack_options(**{key: True}), seed=3).fill_slot_data()
                self.assertIs(wire["ctr_options"].pop(key), True)
                self.assertEqual(json.dumps(wire, sort_keys=True), json.dumps(base, sort_keys=True))

    def test_all_on_with_their_parents(self):
        world = make_world(pack_options(spoiler_items=True, pad_approach_hints=True,
                                        **{key: True for key in KEYS}), seed=5)
        co = world.fill_slot_data()["ctr_options"]
        for key in KEYS + ("pad_approach_hints", "spoiler_items"):
            self.assertIs(co[key], True)

    def test_tracker_restores_them(self):
        world = make_world(pack_options(**{key: True for key in KEYS}), seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        for key in KEYS:
            self.assertEqual(getattr(other.options, key).value, 1)
        self.assertEqual(other.fill_slot_data(), wire)

    def test_bad_value_refuses_on_restore(self):
        wire = json.loads(json.dumps(make_world(pack_options(**{key: True for key in KEYS}), seed=3).fill_slot_data()))
        for key in KEYS:
            for value in (False, 1, "true"):
                forged = copy.deepcopy(wire)
                forged["ctr_options"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(OptionError):
                    make_world({}, seed=999, passthrough=forged)

    def test_listed_as_optional_envelope_keys(self):
        for key in KEYS:
            self.assertIn(key, content_plan.ENVELOPE_OPTIONAL)


if __name__ == "__main__":
    unittest.main()
