"""Regression tests for issue #355 (venusyprime, 0.2.1-alpha1) and the
2026-09-12 legacy-YAML `oxide_final_challenge_relic_count: all` failure.

1. OxideFinalTrack was missing from ap_ctr_option_groups, so it fell into
   the unlabelled bucket at the bottom of the web page instead of sitting
   with the other Goal/Oxide options.
2. SlideColiseumRaces and TurboTrackRaces subclass TrialTrackRaces but did
   not carry their own docstring, so the generated YAML template showed no
   description for either option (Python does not fall back to a parent
   class's __doc__).
3. OxideFinalTrack's docstring quoted the exact AP location id, which is
   more detail than a player needs; that detail now lives in a code
   comment instead.
4. special_range_names = {"all": 18} was attached to OxideFinalTrack (a
   0/1 Choice) instead of FinalOxideRelicCount (the NamedRange the 0.2.0
   template's `all` value was meant for), so `oxide_final_challenge_relic_count:
   all` raised an AttributeError during NamedRange.from_text() instead of
   resolving to 18, a full single tier, as in 0.2.0.
"""
from test.general import setup_multiworld

from . import CTRTestBase
from .. import ctrAPWorld
from ..Options import (
    ap_ctr_option_groups,
    FinalOxideRelicCount,
    OxideFinalTrack,
    SlideColiseumRaces,
    TurboTrackRaces,
    TrialTrackRaces,
)


class TestOxideFinalTrackOptionGroup(CTRTestBase):
    def test_is_sorted_into_the_goal_group(self):
        self.assertIn(OxideFinalTrack, ap_ctr_option_groups["Goal"])

    def test_is_not_in_any_other_group(self):
        for group_name, options in ap_ctr_option_groups.items():
            if group_name == "Goal":
                continue
            self.assertNotIn(OxideFinalTrack, options)

    def test_every_option_appears_in_exactly_one_group(self):
        seen = []
        for options in ap_ctr_option_groups.values():
            seen.extend(options)
        self.assertEqual(seen.count(OxideFinalTrack), 1)

    def test_description_no_longer_names_the_exact_location_id(self):
        # The location id is still available -- just as a code comment, not
        # player-facing text (issue #355).
        self.assertNotIn("35011105", OxideFinalTrack.__doc__ or "")


class TestTrialTrackRaceDescriptions(CTRTestBase):
    def test_slide_coliseum_has_its_own_nonempty_docstring(self):
        self.assertTrue(SlideColiseumRaces.__doc__)
        self.assertIn("Slide Coliseum", SlideColiseumRaces.__doc__)

    def test_turbo_track_has_its_own_nonempty_docstring(self):
        self.assertTrue(TurboTrackRaces.__doc__)
        self.assertIn("Turbo Track", TurboTrackRaces.__doc__)

    def test_descriptions_are_distinct_from_each_other(self):
        self.assertNotEqual(SlideColiseumRaces.__doc__, TurboTrackRaces.__doc__)

    def test_descriptions_are_distinct_from_bare_inheritance(self):
        # Before the fix, __doc__ on both subclasses was None: Python does
        # not inherit a parent class's docstring onto a child class that
        # defines no docstring of its own.
        self.assertIsNotNone(SlideColiseumRaces.__doc__)
        self.assertIsNotNone(TurboTrackRaces.__doc__)
        self.assertNotEqual(SlideColiseumRaces.__doc__, TrialTrackRaces.__doc__)
        self.assertNotEqual(TurboTrackRaces.__doc__, TrialTrackRaces.__doc__)


class TestFinalOxideRelicCountSpecialRangeNames(CTRTestBase):
    def test_special_range_names_live_on_the_relic_count_option(self):
        self.assertEqual(FinalOxideRelicCount.special_range_names, {"all": 18})

    def test_oxide_final_track_no_longer_carries_it(self):
        self.assertEqual(getattr(OxideFinalTrack, "special_range_names", {}), {})

    def test_all_resolves_to_a_full_single_tier(self):
        option = FinalOxideRelicCount.from_text("all")
        self.assertEqual(option.value, 18)

    def test_legacy_all_yaml_generates(self):
        # This is the exact shape of the 0.2.0 template value that used to
        # raise an AttributeError inside NamedRange.from_text() (cls._RANDOM_OPTS
        # does not exist on Range; that's only reached once "all" fails to
        # match special_range_names, so fixing the class it lives on avoids
        # tripping that codepath entirely).
        options = {
            "oxide_final_challenge_unlock": "total_relics",
            "oxide_final_challenge_relic_count": "all",
            "bosses_required_goal": 1,
            "sapphire_relic_count": 1,
            "gold_relic_count": 1,
            "platinum_relic_count": 1,
            "accessibility": "minimal",
        }
        mw = setup_multiworld(ctrAPWorld, seed=355, options=options)
        self.assertEqual(
            mw.worlds[1].options.oxide_final_challenge_relic_count.value, 18)
