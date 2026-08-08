"""Regression guard for the stage-2 collapse generation warning (issue #75).

A stage-2 collapse is sanctioned: the design rule is that a pad's tier 2 MAY
collapse if a seed needs it for generation. What was NOT sanctioned is that it
happened silently. A YAML could ask for layered warp-pad gating, not get it, and
give nobody any way to notice. Measured on the 0.1.5 apworld this is not a corner
case: 0 in 10,000 seeds at shipped defaults, but 15.8% with
`podium_placement_checks: false` and 43.3% at the tightest measured config.

So both silent collapse paths now log exactly one warning naming the collapse and
its cause:
  geography -- no free starting-pad subset opens sphere 0 wide enough
  fill      -- the pre_fill dry run predicts this room would FillError

Deliberately NOT warned: `two_stage_density: off`. That collapse is what the YAML
asked for, so a warning would be noise, and it would fire on every such seed.

The wording is part of the contract with anyone reading a generation log, so the
stable prefix is asserted here rather than left to drift.
"""

import logging
import types
import unittest
from unittest import mock

from .. import warp_pad_logic as wpl

# The greppable part of the line. If you change this, change it deliberately:
# it is what a player is told to search their generation log for.
STABLE_PREFIX = "two-stage warp-pad gating was collapsed"


def _fake_world(name="Tester", player=1):
    return types.SimpleNamespace(
        player=player,
        multiworld=types.SimpleNamespace(player_name={player: name}),
        _ctr_two_stage_active=True,
    )


class WarningWording(unittest.TestCase):

    def test_names_the_player_the_collapse_and_the_reason(self):
        world = _fake_world("Stef")
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "geography", "best breadth was 3")
        self.assertEqual(len(cm.output), 1, "exactly one line per collapse")
        line = cm.output[0]
        self.assertIn("[CTR]", line)
        self.assertIn("Stef", line)
        self.assertIn(STABLE_PREFIX, line)
        self.assertIn("best breadth was 3", line)

    def test_each_reason_has_its_own_explanation(self):
        world = _fake_world()
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "geography", "detail-g")
        self.assertIn("sphere 0", cm.output[0])
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "fill", "detail-f")
        self.assertIn("item fill would fail", cm.output[0])

    def test_says_the_seed_is_still_playable(self):
        """The warning must not read as an error. A collapsed seed is beatable;
        it just has less layered gating than requested."""
        world = _fake_world()
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "fill", "2 slots in the room")
        line = cm.output[0]
        self.assertIn("playable", line)
        self.assertIn("two_stage_density", line)

    def test_unknown_reason_still_warns(self):
        """Never swallow a collapse because someone added a cause and forgot the
        table entry."""
        world = _fake_world()
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "brand-new-reason", "something")
        self.assertIn(STABLE_PREFIX, cm.output[0])

    def test_survives_a_world_with_no_resolvable_name(self):
        """Reporting must not be able to break generation."""
        world = types.SimpleNamespace(player=7, multiworld=None)
        with self.assertLogs(level=logging.WARNING) as cm:
            wpl.warn_stage2_collapsed(world, "geography", "d")
        self.assertIn("player 7", cm.output[0])


class GeographyCollapseWarns(unittest.TestCase):
    """The last-resort branch of run_sphere_search (warp_pad_logic), driven with
    the roll + breadth measurement stubbed so the test does not depend on any
    particular seed's geography."""

    def _run(self, breadths, collapse_stage2=False):
        seq = list(breadths)

        def fake_once(world, mode, reward_track_for=None,
                      collapse_stage2=False, include_gem_cups=False):
            return {t: {1: None, 2: 0} for t in wpl.HUB_STATIC}

        def fake_breadth(world, out, reward_track_for, include_gem_cups):
            return seq.pop(0) if seq else 0

        world = _fake_world()
        with mock.patch.object(wpl, "_run_sphere_search_once", fake_once), \
                mock.patch.object(wpl, "_sphere0_breadth", fake_breadth):
            wpl.run_sphere_search(world, 1, None, collapse_stage2, False)
        return world

    def test_capped_seed_warns_once_with_the_measured_breadth(self):
        with self.assertLogs(level=logging.WARNING) as cm:
            world = self._run([3] * wpl._SPHERE0_REPAIR_TRIES)
        self.assertFalse(world._ctr_two_stage_active, "sanity: collapse fired")
        lines = [l for l in cm.output if STABLE_PREFIX in l]
        self.assertEqual(len(lines), 1)
        # The best breadth it actually reached, and the bar it had to clear.
        self.assertIn("was 3", lines[0])
        self.assertIn(str(wpl._SPHERE0_MIN_BREADTH), lines[0])

    def test_a_seed_that_clears_the_threshold_is_silent(self):
        """No collapse, no warning. This is the overwhelmingly common path at
        shipped defaults (0 collapses in 10,000 seeds), so a spurious warning here
        would be noise on essentially every generation."""
        with mock.patch.object(wpl.logging, "warning") as warn:
            self._run([wpl._SPHERE0_MIN_BREADTH])
        warn.assert_not_called()

    def test_requested_collapse_is_silent(self):
        """two_stage_density: off asked for this. Not a surprise, not a warning."""
        with mock.patch.object(wpl.logging, "warning") as warn:
            self._run([0] * wpl._SPHERE0_REPAIR_TRIES, collapse_stage2=True)
        warn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
