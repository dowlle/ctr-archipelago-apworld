"""Append-only guard for item ids (issue #168).

`item_name_to_id` is built as `item_prefix + enumerate(load_item_table())`
(__init__.py:71-74), so an item's id is its POSITION in data/items.json, not
anything pinned to the item itself. Reordering the file, or removing an entry
from the middle, silently renumbers every entry after it -- the same failure
mode a moved podium code would be, except nothing today catches it. Locations
already carry an explicit `code` field (data/locations.json) and are immune to
this; items are not.

This test pins the id every item held as of the v0.1.5 release
(fixtures/item_id_stability_v0_1_5.json) and fails if any of those names now
resolve to a different id. It reads the mapping straight off the registered
world class -- not by recomputing the formula here -- so it also catches a
changed `item_prefix` or a changed load order, not just a reshuffled JSON
array.

Appends are NOT covered by the fixture and are meant to pass silently: adding
a new entry at the END of items.json only mints a new id, it does not move
anyone else's. When 0.2.0's frozen name manifest (issue #177) lands and new
items are appended, extend this fixture with the new names' ids (append-only,
same as the file it is guarding) rather than editing the existing entries.
"""
import json
import pathlib
import unittest

from worlds.AutoWorld import AutoWorldRegister

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
                    "genuinely retired, its id must stay reserved (do not let "
                    "a later item shift into it) -- items are positional, "
                    "unlike locations, which carry an explicit code.",
                )
                self.assertEqual(
                    current[name], frozen_id,
                    f"{name!r} moved from id {frozen_id} to {current[name]}. "
                    "Item ids are item_prefix + array position in "
                    "data/items.json, so this means an existing entry was "
                    "reordered, removed, or item_prefix itself changed. New "
                    "items must be appended at the END of items.json; if this "
                    "move is genuinely intentional (a frozen manifest sign-off "
                    "that deliberately renumbers), update this fixture in the "
                    "same commit and say so in the PR description.",
                )
