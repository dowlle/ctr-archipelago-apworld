"""Permanent checks for the approved append-only custom namespace."""
import unittest

from ..custom_check_namespace import (
    CUSTOM_FAMILIES, CUSTOM_SLOT_COUNT, custom_check_code, custom_check_name,
)
from .. import ctrAPWorld


class TestCustomCheckNamespace(unittest.TestCase):
    def test_exact_ranges_and_no_registered_collisions(self):
        expected = {
            "letter_location": (35020000, 35020395),
            "letter_item": (35021000, 35021395),
            "relic_location": (35022000, 35022395),
            "ctr_location": (35023000, 35023131),
            "perfect_location": (35024000, 35024131),
        }
        seen = set()
        registered = set(ctrAPWorld.location_name_to_id.values())
        registered.update(ctrAPWorld.item_name_to_id.values())
        for family, (_base, stride) in CUSTOM_FAMILIES.items():
            with self.subTest(family=family):
                codes = [custom_check_code(family, slot, variant)
                         for slot in range(1, CUSTOM_SLOT_COUNT + 1)
                         for variant in range(stride)]
                self.assertEqual((codes[0], codes[-1]), expected[family])
                self.assertEqual(len(set(codes)), CUSTOM_SLOT_COUNT * stride)
                self.assertFalse(seen.intersection(codes))
                for slot in range(1, CUSTOM_SLOT_COUNT + 1):
                    for variant in range(stride):
                        code = custom_check_code(family, slot, variant)
                        if code in registered:
                            # relic and perfect were minted by the 0.3.0 id step.
                            self.assertIn(family, ("letter_location", "letter_item", "ctr_location",
                                                   "relic_location", "perfect_location"))
                            mapping = (ctrAPWorld.item_name_to_id if family ==
                                       "letter_item" else ctrAPWorld.location_name_to_id)
                            self.assertEqual(mapping[
                                custom_check_name(family, slot, variant)], code)
                seen.update(codes)
        self.assertEqual(len(seen), 1452)

    def test_exact_names_and_unique_spelling(self):
        expected = {
            "letter_location": "Custom Track 132: Letter R",
            "letter_item": "Letter R (Custom Track 132)",
            "relic_location": "Custom Track 132: Platinum Time Trial",
            "ctr_location": "Custom Track 132: CTR Token Challenge",
            "perfect_location": "Custom Track 132: Relic Race Perfect",
        }
        for family, (_base, stride) in CUSTOM_FAMILIES.items():
            self.assertEqual(custom_check_name(family, 132, stride - 1),
                             expected[family])
            names = {custom_check_name(family, slot, variant)
                     for slot in range(1, 133) for variant in range(stride)}
            self.assertEqual(len(names), 132 * stride)

    def test_invalid_identity_cannot_alias(self):
        for family, (_base, stride) in CUSTOM_FAMILIES.items():
            for slot in (0, 133, -1, True, False, 1.0, "1", None):
                with self.subTest(family=family, slot=slot):
                    with self.assertRaises(ValueError):
                        custom_check_code(family, slot)
            for variant in (-1, stride, True, False, 0.0, "0", None):
                with self.subTest(family=family, variant=variant):
                    with self.assertRaises(ValueError):
                        custom_check_name(family, 1, variant)
        with self.assertRaises(KeyError):
            custom_check_code("unknown_family", 1)
