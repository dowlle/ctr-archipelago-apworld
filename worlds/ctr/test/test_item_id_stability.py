"""Explicit-code stability guard for item ids (issue #168).

Each entry in data/items.json carries an explicit code, so its ID is stable
regardless of array order. This fixture additionally pins every item ID shipped
in v0.1.5 and catches an accidental code edit or removal.

This test pins the id every item held as of the v0.1.5 release
(fixtures/item_id_stability_v0_1_5.json) and fails if any of those names now
resolve to a different id. It reads the mapping straight off the registered
world class rather than re-reading the JSON, so it covers the actual mapping
published in the datapackage.

New entries are not covered by this v0.1.5 fixture and are meant to pass
silently. When 0.2.0's frozen name manifest (issue #177) lands, extend this
fixture with the new names and their explicit IDs without editing existing
entries.
"""
import json
import pathlib
import unittest

from worlds.AutoWorld import AutoWorldRegister
from worlds.ctr.Items import load_item_table

FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "item_id_stability_v0_1_5.json"
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key in item id stability fixture: {key!r}")
        result[key] = value
    return result


class TestItemIdStability(unittest.TestCase):
    def test_registered_ids_come_from_explicit_item_codes(self) -> None:
        table = load_item_table()
        explicit = {item["name"]: item["code"] for item in table}
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]

        self.assertEqual(len(explicit), len(table), "CTR item names must be unique")
        self.assertEqual(
            len(set(explicit.values())), len(table),
            "CTR item codes must be unique",
        )
        self.assertEqual(world_type.item_name_to_id, explicit)

    def test_existing_items_keep_their_frozen_id(self) -> None:
        frozen: dict = json.loads(
            FIXTURE_PATH.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        current = world_type.item_name_to_id

        for name, frozen_id in frozen.items():
            with self.subTest(item=name):
                self.assertIn(
                    name, current,
                    f"{name!r} is gone from data/items.json. If it was "
                    "genuinely retired, its explicit id must stay reserved.",
                )
                self.assertEqual(
                    current[name], frozen_id,
                    f"{name!r} moved from id {frozen_id} to {current[name]}. "
                    "Item ids are explicit codes in data/items.json, so this "
                    "means an existing code changed. If this "
                    "move is genuinely intentional (a frozen manifest sign-off "
                    "that deliberately renumbers), update this fixture in the "
                    "same commit and say so in the PR description.",
                )
