"""The generation log says each CTR notice once per slot.

The two-stage fill probe builds a mirror of the room whose slots share the
real option objects and reruns every generation step on it. Before the probe
was muted and the notices were latched per slot, a room with N CTR slots
printed every option warning (N+1) x N times.
"""
import logging
import unittest
from unittest import mock

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
        calls = []
        original = ctrAPWorld._probe_two_stage_fillable

        def counting(self_):
            calls.append(self_.player)
            return original(self_)

        with mock.patch.object(ctrAPWorld, "_probe_two_stage_fillable", counting):
            mw, lines = _generate_logging(3)
        self.assertEqual(len(calls), 1, "the probe must have run")
        for p in mw.player_ids:
            name = mw.player_name[p]
            mine = [line for line in lines
                    if "Letters Per Track" in line and name in line]
            with self.subTest(player=name):
                self.assertEqual(mine, [f"CTR ({name}): ignored options: "
                                        "Letters Per Track (Lettersanity off)"])

    def test_nothing_ctr_is_logged_while_the_mirror_runs(self):
        from .. import _quiet_ctr_logs
        handler = _Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with _quiet_ctr_logs():
                logging.getLogger("worlds.ctr.forced_options").warning("CTR: hidden")
                logging.warning("[CTR] hidden too")
                logging.getLogger("worlds.other").warning("other game line")
            logging.getLogger("worlds.ctr.forced_options").warning("CTR: shown")
        finally:
            root.removeHandler(handler)
        self.assertEqual(handler.lines, ["other game line", "CTR: shown"])


if __name__ == "__main__":
    unittest.main()
