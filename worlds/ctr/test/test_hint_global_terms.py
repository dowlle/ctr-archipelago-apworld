"""The hint export preserves global-check runtime rules and income events."""
import random
import unittest

from .. import content_wumpa, logic_terms
from ..win_logic import ForeignRuleError
from .test_content_bosses import boss_options
from .test_content_plan import make_world
from .test_content_wumpa import shop_options
from .test_global_checks import global_options
from .test_win_logic_parity import _states


class TestHintGlobalTerms(unittest.TestCase):
    def test_export_compositions_match_existing_global_rules(self):
        cases = [global_options(),
                 global_options(progressive_boost="per_character", character_unlocks=True,
                                racer_locked_pads=4),
                 boss_options(itemsanity=True, hit_character=True, boss_opponent_shuffle=True,
                              progressive_boost="shared_global", cup_count=3),
                 boss_options(itemsanity=True, hit_character=True, boss_opponent_shuffle=True,
                              progressive_boost="per_character", character_unlocks=True,
                              racer_locked_pads=4, cup_count=3)]
        for seed, (options, hints) in enumerate([(c, h) for h in (True, False) for c in cases]):
            options = dict(options, pad_approach_hints=hints)
            if seed % len(cases) >= 2:
                # Leave room for the weapon, racer and capability copies.
                options["item_pool"]["base"]["trophies"] = 12
            world = make_world(options, seed=seed + 31, stop_before="generate_basic")
            globals_ = [(check, location) for check, location, _routes in world.ctr_global_routes]
            self.assertEqual(len(globals_), 38)
            for index, (state, _received) in enumerate(_states(world.multiworld, random.Random(seed), 24)):
                for check, location in globals_:
                    with self.subTest(seed=seed, state=index, kind=check["kind"], check=location.name):
                        term = logic_terms.term_of(location)
                        self.assertIsInstance(term, logic_terms.SerializedRule)
                        # The original callable is the runtime oracle. Evaluate
                        # the independently composed export predicate as well.
                        self.assertEqual(term.rule(state), term.term.compile()(state))

    def test_income_export_matches_live_route_rule(self):
        for seed, boost in enumerate(("off", "shared_global", "per_character")):
            options = shop_options(progression="allowed", pad_approach_hints=True, progressive_boost=boost)
            options["content_pool"]["tracks"]["modes"] = ["trophy", "ctr", "relic"]
            world = make_world(options, seed=seed + 71, stop_before="generate_basic")
            event = world.multiworld.get_location(content_wumpa.INCOME, world.player)
            term = content_wumpa.income_term(world)
            for index, (state, _received) in enumerate(_states(world.multiworld, random.Random(seed), 24)):
                with self.subTest(boost=boost, state=index):
                    self.assertEqual(event.access_rule(state), term.term.compile()(state))

    def test_foreign_income_wrapper_cannot_be_ignored_by_shop_export(self):
        world = make_world(shop_options(pad_approach_hints=True), seed=73,
                           stop_before="generate_basic")
        event = world.multiworld.get_location(content_wumpa.INCOME, world.player)
        previous = event.access_rule
        event.access_rule = lambda state: state.has("Foreign Unlock", 2) and previous(state)
        with self.assertRaises(ForeignRuleError):
            content_wumpa.income_term(world)

    def test_foreign_income_wrapper_refuses_shop_rows_without_hints(self):
        """A3-37b: shop slots have rows on every seed, so a wrapped income
        event must refuse their export with the option off too."""
        world = make_world(shop_options(), seed=73, stop_before="generate_basic")
        event = world.multiworld.get_location(content_wumpa.INCOME, world.player)
        previous = event.access_rule
        event.access_rule = lambda state: state.has("Foreign Unlock", 2) and previous(state)
        with self.assertRaises(ForeignRuleError):
            content_wumpa.income_term(world)

    def test_hints_off_annotates_global_rules_too(self):
        """A3-37b: the global checks are term-backed on every seed, and the
        runtime rule stays the original callable."""
        world = make_world(global_options(pad_approach_hints=False), seed=31,
                           stop_before="generate_basic")
        self.assertTrue(world.ctr_global_routes)
        for _check, location, _routes in world.ctr_global_routes:
            term = logic_terms.term_of(location)
            self.assertIsInstance(term, logic_terms.SerializedRule)
            self.assertIs(location.access_rule, term.rule)
