"""Custom-track room titles (#306): sanitizing and the ruled clash suffixes."""
import unittest
from unittest.mock import patch

from .. import custom_track_titles as ct


class TestSanitize(unittest.TestCase):
    def test_cleaning(self):
        cases = {
            "Baby T Park": "Baby T Park",
            "  Baby \t T\nPark  ": "Baby T Park",
            "[Neon] {Rush}": "(Neon) (Rush)",
            "Bad\x00Name\x7f​": "BadName",
            ": Trailing :": "Trailing",
            "Café Circuit": "Café Circuit",
            "　 ": None,
            "": None,
            None: None,
            42: None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(ct.sanitize_title(raw), expected)

    def test_length_and_byte_limits(self):
        self.assertEqual(len(ct.sanitize_title("A" * 100)), ct.TITLE_MAX_CHARS)
        wide = ct.sanitize_title("漢" * 40)
        self.assertLessEqual(len(wide.encode("utf-8")), ct.TITLE_MAX_BYTES)
        self.assertEqual(ct.sanitize_title("Long Name " * 10), "Long Name Long Name Long Name Long Name")

    def test_room_titles_fit_every_location_label(self):
        worst = ct.room_title("漢" * 40, "漢" * 40, taken={"漢" * 20},
                              reserved=set())
        self.assertLessEqual(len((worst + ": Finish (Any Position)").encode("utf-8")), 128)
        self.assertTrue(ct.is_sanitized(worst))


class TestClashSuffixes(unittest.TestCase):
    def test_retail_clash_gets_custom(self):
        self.assertEqual(ct.room_title("Crash Cove"), "Crash Cove (Custom)")
        self.assertEqual(ct.room_title("crash cove"), "crash cove (Custom)")
        self.assertEqual(ct.room_title("Wumpa"), "Wumpa (Custom)")
        self.assertEqual(ct.room_title("Purple Gem Cup"), "Purple Gem Cup (Custom)")
        self.assertEqual(ct.room_title("Custom Track 3"), "Custom Track 3 (Custom)")
        self.assertEqual(ct.room_title("Baby T Park"), "Baby T Park")

    def test_custom_clash_gets_author(self):
        self.assertEqual(ct.room_title("Neon Rush", "Ana", taken={"neon rush"}),
                         "Neon Rush (Custom, Ana)")
        self.assertEqual(ct.room_title("Crash Cove", "Ana", taken={"Crash Cove (Custom)"}),
                         "Crash Cove (Custom, Ana)")
        self.assertEqual(ct.room_title("Neon Rush", None, fallback_author="neon-rush",
                                       taken={"Neon Rush"}), "Neon Rush (Custom, neon-rush)")
        self.assertEqual(ct.room_title("Neon Rush", "Ana",
                                       taken={"Neon Rush", "Neon Rush (Custom, Ana)"}),
                         "Neon Rush (Custom, Ana 2)")

    def test_seed_titles_keep_slot_order_and_named_stems(self):
        entries = [(2, "Neon Rush", "Bo", "b"), (1, "Neon Rush", "Ana", "a"),
                   (3, "Crash Cove", "Cy", "c"), (4, "", "Dee", "d")]
        self.assertEqual(ct.seed_titles(entries), {
            1: "Neon Rush", 2: "Neon Rush (Custom, Bo)", 3: "Crash Cove (Custom)"})
        with patch.object(ct, "named_stems", return_value={"neon rush"}):
            self.assertEqual(ct.seed_titles(entries)[1], "Neon Rush (Custom, Ana)")


# The legacy custom_track_titles wire reader/writer was deleted in row 12.
# Content-plan title validation and restoration are tested with the plan.
