"""The sphere-0 breadth measurement of the reference playthrough
(content_playthrough._sphere0_breadth) takes no random draw.

The repair loop that uses it lives in content_requirements on the plan. One
generator row 12 deleted the original generator's wrapper
(warp_pad_logic.run_sphere_search) with its control-flow and postcondition
tests.
"""

import types
import unittest
from unittest import mock

from .. import content_playthrough as wpl


class TestSphere0Breadth(unittest.TestCase):

    def test_breadth_helper_consumes_no_rng(self):
        """The measurement must not perturb generation determinism."""
        import random as _random
        rnd = _random.Random(12345)
        world = types.SimpleNamespace(random=rnd, start_region=None)
        before = rnd.getstate()
        with mock.patch.object(wpl, "build_graph",
                               lambda *a, **k: ({}, {}, None)):
            wpl._sphere0_breadth(world, {}, lambda t: t, False)
        self.assertEqual(rnd.getstate(), before,
                         "_sphere0_breadth consumed world.random")
