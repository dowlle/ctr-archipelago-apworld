"""`track_key` in a custom_tracks entry reaches every reader as `content_id`.

The two readers that ran admission on the raw option value (the bundled Cortex
Vortex swap and the Tizi Madness leave-out) once failed or kept the entry when
it was written with `track_key`. Legacy and modern YAML must generate the same
room on those paths.
"""
import copy
import unittest
from unittest import mock

from Options import OptionError

from .. import content_plan
from ..Options import CustomTracks
from . import test_content_plan
from .test_content_plan import make_world
from . import test_cortex_relic_perfect as cortex_tests
from .test_custom_packages import UNKNOWN
from .test_custom_packages import options_with
from .test_tizi_madness import SK, tizi_descriptor


def modern(descriptor):
    """The same entry with its key written as `track_key`."""
    out = {("track_key" if k == "content_id" else k): v for k, v in descriptor.items()}
    assert "content_id" not in out
    return out


def make_world_as_yaml(options, as_modern, **kwargs):
    """make_world, with the YAML custom_tracks entries written as track_key when
    `as_modern` (the test option builders only know the legacy name)."""
    real = test_content_plan.plan_options

    def convert(opts):
        out = real(opts)
        if as_modern:
            out["custom_tracks"] = [modern(d) for d in out["custom_tracks"]]
        return out
    with mock.patch.object(test_content_plan, "plan_options", convert):
        return make_world(options, **kwargs)


class TestOptionNormalisation(unittest.TestCase):
    def test_track_key_becomes_content_id_and_legacy_is_untouched(self):
        legacy = copy.deepcopy(UNKNOWN)
        self.assertEqual(CustomTracks.from_any([modern(legacy)]).value, [legacy])
        self.assertEqual(CustomTracks.from_any([legacy]).value, [legacy])
        both = dict(legacy, track_key=legacy["content_id"])
        self.assertEqual(CustomTracks.from_any([both]).value, [legacy])

    def test_disagreeing_names_still_fail_with_the_existing_message(self):
        entry = dict(modern(UNKNOWN), content_id="different")
        self.assertEqual(CustomTracks.from_any([entry]).value, [entry])
        with self.assertRaisesRegex(OptionError, "track_key and content_id must match"):
            content_plan.resolve_packages([entry])


class TestCortexSwap(unittest.TestCase):
    def custom(self):
        copy_ = cortex_tests.TestCortexVortexTrack.saphi_cortex_vortex()
        listed = [copy.deepcopy(content_plan.PACKAGES[1]), copy.deepcopy(UNKNOWN), cortex_tests.relic_named(), copy_]
        return listed

    def world(self, as_modern):
        options = cortex_tests.cv_options(cortex=False, custom=self.custom())
        options["content_pool"]["required_entries"].remove("custom/cortex-vortex/1.1.2")
        return make_world_as_yaml(options, as_modern, seed=3)

    def test_track_key_form_swaps_like_content_id(self):
        old, new = self.world(False), self.world(True)
        self.assertEqual(new.ctr_cortex_swap, ["package/cortex-vortex/1.1.2"])
        self.assertEqual(new.ctr_cortex_swap, old.ctr_cortex_swap)
        self.assertEqual(new.ctr_content_plan, old.ctr_content_plan)
        self.assertEqual(new.options.custom_tracks.value, old.options.custom_tracks.value)


class TestTiziLeaveOut(unittest.TestCase):
    def test_track_key_form_is_left_out_below_hard_like_content_id(self):
        legacy = tizi_descriptor()
        for sk in ("easy", "medium"):
            with self.subTest(shortcut_knowledge=sk):
                old = self.modern_world(legacy, sk, legacy_form=True)
                new = self.modern_world(legacy, sk)
                self.assertEqual(old.ctr_tizi_madness_left_out, [legacy["id"]])
                self.assertEqual(new.ctr_tizi_madness_left_out, old.ctr_tizi_madness_left_out)
                self.assertEqual(new.ctr_content_plan, old.ctr_content_plan)

    def test_track_key_form_stays_at_hard(self):
        legacy = tizi_descriptor()
        old, new = self.modern_world(legacy, "hard", legacy_form=True), self.modern_world(legacy, "hard")
        self.assertFalse(hasattr(new, "ctr_tizi_madness_left_out"))
        self.assertEqual(new.ctr_content_plan, old.ctr_content_plan)

    @staticmethod
    def modern_world(descriptor, sk, legacy_form=False):
        tid = f"custom/{descriptor['content_id']}/{descriptor['revision']}"
        options = options_with([descriptor], required=[tid])
        options.update(shortcut_knowledge=SK[sk], itemsanity=False)
        return make_world_as_yaml(options, not legacy_form, seed=7)


if __name__ == "__main__":
    unittest.main()
