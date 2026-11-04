"""Trial-track relic tier terms without a Trophy Race (ruling 2026-09-29).

Slide Coliseum and Turbo Track have no Trophy Race unless their race option
adds one. Before this ruling their Time Trials then skipped
`add_time_trial_and_ctr_requirements` entirely, so Gold and Platinum carried
no boost term. They now take the same racer-bound `relic_tier_boost_min`
term they would get with a Trophy Race (2026-08-21 tier ruling, including the
2026-09-17 easy/medium Platinum raise). Sapphire stays free, and the term is
vacuous with Progressive Boost off.
"""
import unittest

from .test_relic_perfect import PLAYER, _build, _state
from ..progressive_capability import ROSTER
from ..usf_finish import relic_tier_boost_min

TRIALS = ("Slide Coliseum", "Turbo Track")
#: Every relic tier is a check on every track, so no tier draw drops a trial.
ALL_TIERS = dict(sapphire_relic_count=18, gold_relic_count=18,
                 platinum_relic_count=18)
NO_TROPHY = dict(slide_coliseum_races="off", turbo_track_races="off",
                 **ALL_TIERS)
WITH_TROPHY = dict(slide_coliseum_races="trophy_race",
                   turbo_track_races="trophy_race", **ALL_TIERS)


def _reach(mw, state, name):
    return mw.get_location(name, PLAYER).can_reach(state)


class TestTrialRelicTierWithoutTrophyRace(unittest.TestCase):
    CASES = (("easy", False), ("easy", True), ("medium", False),
             ("hard", False))


