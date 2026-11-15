"""A5-5: one generator message per slot.

The generator prints at most one message for a slot, a summary of every option
it adjusted. A YAML that needs no adjustment prints nothing."""
import logging
import unittest
from types import SimpleNamespace

from .. import notices
from ..notices import adjusted, emit_summary, note_ignored, summary_lines
from .test_content_plan import make_world, profile_options
from .test_pad_budget import FOUR


class _Records(logging.Handler):
    """Every record the CTR world logs at INFO or above, from any CTR module."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def build(options, seed=3):
    handler = _Records()
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        world = make_world(options, seed=seed)
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    ours = [r for r in handler.records if r.name == "CTR" or r.name.startswith("worlds.ctr")]
    return world, ours


def heavy_options():
    """A YAML the generator has to adjust three ways: a one-tier relic count
    above 18, a Crystal Challenge count above the arenas listed, and the Alpha 6
    `true` spelling of Racer-Locked Warp Pads."""
    return dict(oxide_final_challenge_unlock="sapphire_relics", oxide_final_challenge_relic_count=30,
                crystal_challenge_count=7, crystal_arenas=FOUR, racer_locked_pads=True,
                character_unlocks=True, accessibility="full")


class TestSummary(unittest.TestCase):
    def test_a_yaml_that_needs_no_adjustment_prints_nothing(self):
        world, records = build(profile_options())
        self.assertEqual(records, [])
        self.assertEqual(summary_lines(world), [])

    def test_ignored_options_print_nothing_above_debug(self):
        world, records = build(profile_options())
        note_ignored(world, "Boss Track Allowlist (Boss Track Shuffle off)")
        self.assertFalse(emit_summary(world))
        self.assertEqual(records, [])

    def test_one_message_lists_every_adjustment(self):
        world, records = build(heavy_options())
        self.assertEqual(len(records), 1, [r.getMessage() for r in records])
        record = records[0]
        self.assertEqual(record.levelno, logging.WARNING)
        message = record.getMessage()
        self.assertIn("(ContentPlan)", message)
        self.assertIn("changed 3 settings", message)
        self.assertIn("Oxide's Final Challenge Relic Count: lowered from 30 to 18, because a one-tier mode allows at most 18", message)
        self.assertIn("Crystal Challenge Count: lowered from 7 to 4", message)
        self.assertIn("Racer-Locked Warp Pads: 'true' is read the Alpha 6 way", message)
        self.assertEqual(len(summary_lines(world)), 3)
        self.assertEqual(sum(line.startswith("  - ") for line in message.splitlines()), 3)

    def test_a_second_generate_early_adds_nothing(self):
        handler = _Records()
        world, _ = build(heavy_options())
        logging.getLogger().addHandler(handler)
        try:
            world.generate_early()
            self.assertFalse(emit_summary(world))
        finally:
            logging.getLogger().removeHandler(handler)
        self.assertEqual([r for r in handler.records if r.name == "CTR"], [])
        self.assertEqual(len(summary_lines(world)), 3)

    def test_the_pad_budget_is_one_line_in_the_summary(self):
        world, records = build(dict(cup_count=27, cortex_vortex_track="own_pad", accessibility="full"))
        self.assertEqual(len(records), 1)
        self.assertIn("Cup Count and Crystal Challenge Count: asked for 27 cups", records[0].getMessage())

    def test_the_library_part_of_the_message(self):
        fake = SimpleNamespace(options=SimpleNamespace(), player=2,
                               multiworld=SimpleNamespace(player_name={2: "Two"}))
        adjusted(fake, "a", "One: changed.")
        adjusted(fake, "a", "One: changed again.")
        adjusted(fake, "b", "Two: changed.")
        self.assertEqual(summary_lines(fake), ["One: changed again.", "Two: changed."])
        with self.assertLogs("CTR", "WARNING") as logs:
            self.assertTrue(emit_summary(fake))
            self.assertFalse(emit_summary(fake))
        self.assertEqual(len(logs.records), 1)
        self.assertIn("CTR (Two): the generator changed 2 settings for this slot:", logs.records[0].getMessage())

    def test_the_universal_tracker_rebuild_prints_nothing(self):
        fake = SimpleNamespace(options=SimpleNamespace(), player=1,
                               multiworld=SimpleNamespace(player_name={1: "P"}, generation_is_fake=True))
        adjusted(fake, "a", "One: changed.")
        self.assertFalse(emit_summary(fake))

    def test_no_module_logs_on_its_own(self):
        """The inventory of A5-5: no generation code calls the logger directly
        for an option notice any more; it goes through notices.adjusted."""
        import re
        from pathlib import Path
        root = Path(notices.__file__).parent
        pattern = re.compile(r"\b(?:logging|log|logger)\.(?:warning|info|error)\(|\bsay_once\b|\b_warn\(")
        found = []
        for path in sorted(root.glob("*.py")):
            if path.name in ("notices.py", "launcher_component.py"):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    found.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(found, [])
