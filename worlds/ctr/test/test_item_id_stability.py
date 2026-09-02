"""Explicit-code stability guard for item ids (issue #168).

Each entry in data/items.json carries an explicit code, so its ID is stable
regardless of array order. This fixture additionally pins every item ID shipped
in v0.1.5 and catches an accidental code edit or removal.

This test pins the id every item held as of the v0.1.5 release
(fixtures/item_id_stability_v0_1_5.json) and fails if any of those names now
resolve to a different id. It reads the mapping straight off the registered
world class rather than re-reading the JSON, so it covers the actual mapping
published in the datapackage.

The 0.2.0 name freeze (issue #177) added a SECOND fixture,
fixtures/item_id_stability_v0_2_0.json, pinning every item name registered during
the 0.2.0 cycle -- the spine-1 capability names plus the 93 the freeze itself
minted. It is a separate file rather than an extension of the v0.1.5 one so each
fixture keeps saying honestly which release froze the ids it holds; both are read
below. Ids are never edited in place; the one name-level exception is recorded next.

Entries added AFTER the 0.2.0 freeze are covered by neither fixture and are meant
to pass silently. Any release that spends a datapackage bump adds its own fixture
here the same way.

RENAME EXCEPTIONS. #280 (the 0.2.0 trap rework, ruled 2026-08-19) rewrote 16
trap keys in place. The approved 2026-09-02 datapackage unfreeze then rewrote
`Nitro` to `Nitro Drop` in the v0.2.0 fixture. These are the only in-place
fixture edits either file has taken, because the rework renamed those items while 0.2.0 is still
unpublished. Not one id moved, which is the property these fixtures exist to
protect; a fixture keyed on a name that no longer exists would fail on the rename
rather than on an id change and would stop guarding anything. The old-to-new name
maps are pinned in test_trap_rework.py, so each approved rename remains on the
record in code.
"""
import json
import pathlib
import unittest

from worlds.AutoWorld import AutoWorldRegister
from worlds.ctr.Items import load_item_table

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "item_id_stability_v0_1_5.json"
#: One entry per release that spent a datapackage bump. Append-only.
FIXTURE_PATHS = (
    FIXTURE_PATH,
    FIXTURE_DIR / "item_id_stability_v0_2_0.json",
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
        frozen: dict = {}
        for path in FIXTURE_PATHS:
            batch = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
            overlap = set(batch) & set(frozen)
            self.assertEqual(
                overlap, set(),
                f"{path.name} re-pins name(s) an earlier fixture already owns: "
                f"{sorted(overlap)[:5]}. Each fixture owns its own release's "
                "names; ids are never edited in place (names moved once, per the "
                "RENAME EXCEPTION above).",
            )
            frozen.update(batch)
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
