import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from ..Rules import make_rule


PLAYER = 1


class TestRulesParser(unittest.TestCase):
    def test_valid_single_rule(self):
        state = Mock()
        state.has.return_value = True

        self.assertTrue(make_rule("has('Key', 2)", PLAYER)(state))
        state.has.assert_called_once_with("Key", PLAYER, 2)

    def test_valid_conjunction(self):
        state = Mock()
        state.has.return_value = True

        rule = make_rule("has('Key', 4) and has('Sapphire Relic', 10)", PLAYER)

        self.assertTrue(rule(state))
        self.assertEqual(
            state.has.call_args_list,
            [unittest.mock.call("Key", PLAYER, 4),
             unittest.mock.call("Sapphire Relic", PLAYER, 10)],
        )

    def test_item_name_containing_and_is_not_split(self):
        state = Mock()
        state.has.return_value = True

        self.assertTrue(make_rule("has('Sand and Snow')", PLAYER)(state))
        state.has.assert_called_once_with("Sand and Snow", PLAYER, 1)

    def test_always_and_true_are_unconditional(self):
        state = Mock()
        for expression in ("always", "true"):
            with self.subTest(expression=expression):
                self.assertTrue(make_rule(expression, PLAYER)(state))
        state.has.assert_not_called()

    def assert_rejected(self, expression, segment):
        with self.assertRaises(ValueError) as raised:
            make_rule(expression, PLAYER)
        message = str(raised.exception)
        self.assertIn(repr(expression), message)
        self.assertIn(repr(segment), message)

    def test_rejects_unsupported_segment(self):
        self.assert_rejected("has('Key') or has('Trophy')", "has('Key') or has('Trophy')")

    def test_rejects_missing_item(self):
        for expression in ("has()", "has('', 1)"):
            with self.subTest(expression=expression):
                self.assert_rejected(expression, expression)

    def test_rejects_non_integer_count(self):
        self.assert_rejected("has('Key', many)", "has('Key', many)")

    def test_rejects_negative_count(self):
        self.assert_rejected("has('Key', -1)", "has('Key', -1)")

    def test_rejects_unbalanced_parentheses(self):
        self.assert_rejected("has('Key', 1", "has('Key', 1")

    def test_every_world_json_rule_parses(self):
        world_path = Path(__file__).parents[1] / "data" / "world.json"
        world_data = json.loads(world_path.read_text(encoding="utf-8"))
        rules = []

        def collect(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ("access_rule", "requires") and isinstance(child, str):
                        rules.append(child)
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(world_data)
        self.assertTrue(rules)
        for expression in rules:
            with self.subTest(expression=expression):
                make_rule(expression, PLAYER)
