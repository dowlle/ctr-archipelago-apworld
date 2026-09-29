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

    def test_gold_and_platinum_need_their_tier_rank(self):
        for difficulty, blue_fire in self.CASES:
            mw = _build(seed=3, progressive_boost="shared_global",
                        logic_difficulty=difficulty,
                        progressive_boost_blue_fire=blue_fire, **NO_TROPHY)
            options = mw.worlds[PLAYER].options
            names = {loc.name for loc in mw.get_locations(PLAYER)}
            for track in TRIALS:
                self.assertNotIn(f"{track}: Trophy Race", names)
                for tier in ("Gold", "Platinum"):
                    need = relic_tier_boost_min(track, tier, options)
                    name = f"{track}: {tier} Time Trial"
                    with self.subTest(difficulty=difficulty,
                                      blue_fire=blue_fire, location=name):
                        self.assertGreater(need, 0)
                        self.assertFalse(_reach(mw, _state(mw, 0), name))
                        self.assertFalse(_reach(mw, _state(mw, need - 1),
                                                name))
                        self.assertTrue(_reach(mw, _state(mw, need), name))

    def test_same_rank_as_with_a_trophy_race(self):
        """Gold and Platinum open at the same boost count either way. Sapphire
        is left out: with a Trophy Race it inherits that race's own
        difficulty gate, which is not a relic tier term."""
        for difficulty in ("easy", "medium", "hard"):
            without = _build(seed=3, progressive_boost="shared_global",
                             logic_difficulty=difficulty, **NO_TROPHY)
            with_trophy = _build(seed=3, progressive_boost="shared_global",
                                 logic_difficulty=difficulty, **WITH_TROPHY)
            for track in TRIALS:
                for tier in ("Gold", "Platinum"):
                    name = f"{track}: {tier} Time Trial"
                    for boost in range(4):
                        with self.subTest(difficulty=difficulty,
                                          location=name, boost=boost):
                            self.assertEqual(
                                _reach(without, _state(without, boost), name),
                                _reach(with_trophy,
                                       _state(with_trophy, boost), name))

    def test_sapphire_stays_free(self):
        mw = _build(seed=3, progressive_boost="shared_global",
                    logic_difficulty="easy", **NO_TROPHY)
        for track in TRIALS:
            self.assertTrue(_reach(mw, _state(mw, 0),
                                   f"{track}: Sapphire Time Trial"))

    def test_vacuous_with_boost_off(self):
        for difficulty in ("easy", "medium", "hard"):
            mw = _build(seed=3, progressive_boost="off",
                        logic_difficulty=difficulty, **NO_TROPHY)
            for track in TRIALS:
                for tier in ("Sapphire", "Gold", "Platinum"):
                    name = f"{track}: {tier} Time Trial"
                    with self.subTest(difficulty=difficulty, location=name):
                        self.assertTrue(_reach(mw, _state(mw, 0), name))

    def test_a_locked_trial_pad_binds_its_racer(self):
        from ..progressive_capability import track_required_character
        mw = track = required = None
        for seed in range(1, 65):
            candidate = _build(seed=seed, progressive_boost="per_character",
                               logic_difficulty="hard",
                               racer_locked_pads=True, **NO_TROPHY)
            world = candidate.worlds[PLAYER]
            hits = [(t, track_required_character(world, t)) for t in TRIALS]
            hits = [(t, r) for t, r in hits if r]
            if hits:
                mw, (track, required) = candidate, hits[0]
                break
        if mw is None:
            self.skipTest("fixture seeds produced no locked trial pad")
        wrong = next(racer for racer in ROSTER if racer != required)
        name = f"{track}: Gold Time Trial"
        self.assertFalse(_reach(mw, _state(
            mw, character_boosts=((wrong, 3),)), name))
        self.assertTrue(_reach(mw, _state(
            mw, character_boosts=((required, 3),)), name))
