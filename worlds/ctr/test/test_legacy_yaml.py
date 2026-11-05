"""A 0.2.x YAML is refused once, with one readable message.

The tester's old YAML threw a generator error on a Baby T Park custom_tracks
mapping, and after removing it on cortex_vortex_track: true. Removed option
names never reached the world at all. See legacy_yaml.py.
"""
import unittest

from Generate import roll_settings
from Options import OptionError

from .. import legacy_yaml

GAME = "Crash Team Racing"


def _weights(section):
    return {"name": "T", "game": GAME, GAME: section}


def _roll(section):
    return roll_settings(_weights(section))


def _refusal(section):
    """The message of the refusal roll_settings raises for this section."""
    with unittest.TestCase().assertRaises(OptionError) as caught:
        _roll(section)
    cause = caught.exception.__cause__
    assert cause is not None
    return str(cause)


OLD_MAPPING = {"baby-t-park": {"package_uuid": "x", "replaces": "purple_gem_cup"}}


class LegacyYamlRefusalTests(unittest.TestCase):
    def test_tester_yaml_shape_gets_one_message_naming_everything(self):
        message = _refusal({
            "custom_tracks": OLD_MAPPING,
            "include_battle_arenas": {"false": 80, "true": 20},
            "include_gem_cups": {"false": 0, "true": 50},
            "slide_coliseum_races": {"off": 0, "trophy_race": 50},
            "cortex_vortex_track": {"false": 10, "true": 90},
            "death_link": {"off": 0, "any_hit": 0, "race_loss": 50},
        })
        self.assertIn("0.2.x", message)
        self.assertIn("0.3.0 release notes", message)
        self.assertIn("v0.2.4 client", message)
        for name in ("custom_tracks", "include_battle_arenas",
                     "include_gem_cups", "slide_coliseum_races",
                     "cortex_vortex_track: true"):
            self.assertIn(name, message)
        # any_hit has weight 0 in this YAML, so it is not an offender.
        self.assertNotIn("any_hit", message)

    def test_removed_names_alone_refuse(self):
        for name in legacy_yaml.REMOVED_OPTIONS:
            with self.subTest(name=name):
                self.assertIn(name, _refusal({name: {"false": 0, "true": 50}}))

    def test_values_refused_when_selected(self):
        self.assertIn("death_link: any_hit", _refusal({"death_link": "any_hit"}))
        self.assertIn("cortex_vortex_track: true",
                      _refusal({"cortex_vortex_track": True}))

    def test_current_yaml_still_rolls(self):
        rolled = _roll({"custom_tracks": [], "cortex_vortex_track": "off",
                        "death_link": "race_loss", "cup_count": 5})
        self.assertEqual(rolled.cup_count.value, 5)

    def test_empty_old_mapping_and_false_are_not_refused(self):
        rolled = _roll({"custom_tracks": {}, "cortex_vortex_track": False})
        self.assertEqual(rolled.cortex_vortex_track.value, 0)

    def test_message_text(self):
        self.assertEqual(
            legacy_yaml.refusal_message(["a (b)", "c"]),
            "CTR: this YAML is from 0.2.x and does not work in 0.3.0. "
            "Old options in it: a (b); c. Make a new YAML (the YAML Builder "
            "has 0.3.0) or edit this one: see the 0.3.0 release notes for "
            "the YAML upgrade guide. Rooms made on 0.2.x need the v0.2.4 "
            "client.")

    def test_helper_ignores_other_callers(self):
        legacy_yaml.check_caller()  # not under handle_option: no effect
