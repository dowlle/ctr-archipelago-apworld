"""Universal Tracker and the `win_logic` block (Contract 7m).

UT re-generates the world from the connected seed's slot_data
(`interpret_slot_data` returns it verbatim). The new block rides along in that
passthrough and must be ignored by the restore path. And because the block is
serialised from the installed rule terms, a tracker re-generation must
serialise the SAME block from its own rules: the game and the tracker then
agree on every win check by construction, which is the point of option A.
"""
import random
import unittest

from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..win_logic import wire_block
from .test_win_logic_parity import STEPS, PLAYER, _random_options


def _tracker(seed, options, wire):
    tracker = setup_multiworld(ctrAPWorld, steps=(), seed=seed, options=options)
    tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
    tracker.generation_is_fake = True
    for step in STEPS:
        call_all(tracker, step)
    return tracker


class TestTrackerRebuildsTheSameBlock(unittest.TestCase):
    def _check(self, seed, options, tracker_options=None):
        """Generate `options`, re-generate as the tracker from its slot_data
        and compare blocks. `tracker_options=None` hands the tracker the
        source's RESOLVED option values (a YAML that matches the seed);
        `{}` is the no-YAML tracker. Returns False when the source refuses."""
        try:
            source = setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)
        except OptionError:
            return False
        world = source.worlds[PLAYER]
        wire = world.fill_slot_data()
        self.assertIn("win_logic", wire)
        if tracker_options is None:
            tracker_options = options
        tracker = _tracker(seed, tracker_options, wire)
        self.assertEqual(wire_block(tracker.worlds[PLAYER]), wire["win_logic"])
        return True

    def test_named_options(self):
        cases = (
            {},
            {"progressive_boost": "per_character", "character_unlocks": True,
             "racer_locked_pads": 6, "itemsanity": True, "box_locations": True,
             "include_battle_arenas": False, "logic_difficulty": "easy"},
            {"warppad_unlock_requirements": "vanilla", "oxide_goal": "101_percent",
             "bosses_required_goal": 3, "gems_required_goal": 2},
        )
        for options in cases:
            with self.subTest(options=options, tracker="same YAML"):
                self.assertTrue(self._check(5, options, options))

    def test_random_options(self):
        rng = random.Random(29)
        done = attempts = 0
        while done < 12:
            attempts += 1
            self.assertLess(attempts, 120)
            seed = rng.randrange(1 << 30)
            options = _random_options(rng)
            with self.subTest(seed=seed):
                if self._check(seed, options):
                    done += 1
                    # The no-YAML tracker (ut_can_gen_without_yaml).
                    self._check(seed, options, {})


if __name__ == "__main__":
    unittest.main()
