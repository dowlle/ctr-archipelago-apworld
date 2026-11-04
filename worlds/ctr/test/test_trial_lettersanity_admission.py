"""Admission invariant for the upcoming trial lettersanity extension."""
import unittest
from types import SimpleNamespace

from ..lettersanity import LETTER_TRACKS, eligible_letter_tracks
from ..lettersanity import LETTERSANITY_CLASS, ALL_ITEM_NAMES
from .test_lettersanity import _build, _collect_all


class TestTrialLettersanityAdmission(unittest.TestCase):




    def test_trial_location_append_codes(self):
        for ti, track in enumerate(("Slide Coliseum", "Turbo Track")):
            for li, letter in enumerate(("C", "T", "R")):
                self.assertEqual(LETTERSANITY_CLASS.code_for(track, letter),
                                 35012548 + ti * 3 + li)


    def test_independent_trial_options_and_frozen_prefix(self):
        for slide in range(3):
            for turbo in range(3):
                with self.subTest(slide=slide, turbo=turbo):
                    options = SimpleNamespace(
                        slide_coliseum_races=SimpleNamespace(value=slide),
                        turbo_track_races=SimpleNamespace(value=turbo))
                    expected = tuple(LETTER_TRACKS)
                    if slide == 2:
                        expected += ("Slide Coliseum",)
                    if turbo == 2:
                        expected += ("Turbo Track",)
                    admitted = eligible_letter_tracks(options)
                    self.assertEqual(admitted, expected)
                    self.assertEqual(admitted[:16], tuple(LETTER_TRACKS))

    def test_old_options_do_not_admit_trials(self):
        self.assertEqual(eligible_letter_tracks(None), tuple(LETTER_TRACKS))
        self.assertEqual(eligible_letter_tracks(SimpleNamespace()),
                         tuple(LETTER_TRACKS))
