"""Regression tests for issue #355 (venusyprime, 0.2.1-alpha1) and the
2026-09-12 legacy-YAML `oxide_final_challenge_relic_count: all` failure.

1. OxideFinalTrack was missing from ap_ctr_option_groups, so it fell into
   the unlabelled bucket at the bottom of the web page instead of sitting
   with the other Goal/Oxide options.
2. SlideColiseumRaces and TurboTrackRaces subclass TrialTrackRaces but did
   not carry their own docstring, so the generated YAML template showed no
   description for either option (Python does not fall back to a parent
   class's __doc__). Both options were retired in one generator row 7 and
   deleted in row 12, with their test.
3. OxideFinalTrack's docstring quoted the exact AP location id, which is
   more detail than a player needs; that detail now lives in a code
   comment instead.
4. special_range_names = {"all": 18} was attached to OxideFinalTrack (a
   0/1 Choice) instead of FinalOxideRelicCount (the NamedRange the 0.2.0
   template's `all` value was meant for), so `oxide_final_challenge_relic_count:
   all` raised an AttributeError during NamedRange.from_text() instead of
   resolving to 18, a full single tier, as in 0.2.0.
"""

from . import CTRTestBase
from ..Options import (
    ap_ctr_option_groups,
    FinalOxideRelicCount,
    OxideFinalTrack,
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


class TestFinalOxideRelicCountSpecialRangeNames(CTRTestBase):
    def test_special_range_names_live_on_the_relic_count_option(self):
        self.assertEqual(FinalOxideRelicCount.special_range_names, {"all": 18})

    def test_oxide_final_track_no_longer_carries_it(self):
        self.assertEqual(getattr(OxideFinalTrack, "special_range_names", {}), {})

    def test_all_resolves_to_a_full_single_tier(self):
        option = FinalOxideRelicCount.from_text("all")
        self.assertEqual(option.value, 18)

