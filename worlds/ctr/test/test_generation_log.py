"""The generation log says each CTR notice once per slot.

A room with N CTR slots once printed every option warning (N+1) x N times.
Notices are latched per slot on the option object (`notices.say_once`).
"""
import logging
import unittest

from test.general import setup_multiworld

from .. import ctrAPWorld

OPTIONS = {
    "warppad_unlock_requirements": "randomized",
    "lettersanity": "off",
    "letters_per_track": 2,
}


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _generate_logging(players, seed=5, options=OPTIONS):
    handler = _Capture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        mw = setup_multiworld([ctrAPWorld] * players, seed=seed, options=options)
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    return mw, handler.lines


class TestNoticesOncePerSlot(unittest.TestCase):
    def test_three_ctr_room_says_each_notice_once_per_slot(self):
        mw, lines = _generate_logging(3)
        for p in mw.player_ids:
            name = mw.player_name[p]
            mine = [line for line in lines
                    if "Letters Per Track" in line and name in line]
            with self.subTest(player=name):
                self.assertEqual(mine, [f"CTR ({name}): ignored options: "
                                        "Letters Per Track (Lettersanity off)"])


if __name__ == "__main__":
    unittest.main()
