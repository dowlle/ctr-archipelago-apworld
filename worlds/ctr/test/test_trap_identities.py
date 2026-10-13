"""Trap identities on the wire (issue #307, slot_data schema 18).

Every seed carries a `trap_identities` block mapping each trap item id to the
trap's stable key, and native applies a received trap only when that key is
the one it has for the item. test/fixtures/trap_identities.json is the shared
fixture: a byte-identical copy lives in native as
tools/fixtures/trap_identities.json, and native's test-trap-identities harness
checks its enum, key table, item table and effect names against the same rows.
Reordering, renaming or re-pointing a trap on either side without changing the
fixture fails that side's test.
"""
import json
import pkgutil
import unittest

from .. import ctrAPWorld
from ..slot_data import SLOT_DATA_SCHEMA
from ..traps import (TRAP_IDENTITIES_VERSION, TRAP_REGISTRY,
                     trap_identities_block)
from . import CTRTestBase

FIXTURE = json.loads(pkgutil.get_data(__package__, "fixtures/trap_identities.json"))


class TestFixture(unittest.TestCase):

    def test_registry_matches_the_fixture_row_for_row(self):
        rows = [(r["key"], r["name"]) for r in FIXTURE["traps"]]
        self.assertEqual([(e.key, e.name) for e in TRAP_REGISTRY], rows)

    def test_item_ids_match_the_fixture(self):
        for row in FIXTURE["traps"]:
            self.assertEqual(ctrAPWorld.item_name_to_id[row["name"]], row["item_id"], row["name"])

    def test_keys_and_ids_are_unique(self):
        self.assertEqual(len({r["key"] for r in FIXTURE["traps"]}), len(FIXTURE["traps"]))
        self.assertEqual(len({r["item_id"] for r in FIXTURE["traps"]}), len(FIXTURE["traps"]))

    def test_block_is_exactly_the_fixture(self):
        block = trap_identities_block(ctrAPWorld.item_name_to_id)
        self.assertEqual(block["version"], FIXTURE["version"])
        self.assertEqual(TRAP_IDENTITIES_VERSION, 1)
        # Ordered comparison: the emitted map follows the fixture's row order.
        self.assertEqual(list(block["items"].items()),
                         [(str(r["item_id"]), r["key"]) for r in FIXTURE["traps"]])


class TestEmitted(CTRTestBase):
    run_default_tests = False
    options = {"trap_fill_percentage": 50}

    def test_every_seed_carries_the_block_at_schema_18(self):
        sd = self.world.fill_slot_data()
        self.assertEqual(SLOT_DATA_SCHEMA, 18)
        self.assertEqual(sd["schema_version"], 18)
        self.assertEqual(sd["ctr_options"]["schema_version"], 18)
        self.assertEqual(sd["trap_identities"], trap_identities_block(ctrAPWorld.item_name_to_id))

    def test_every_drawn_trap_has_an_identity(self):
        items = self.world.fill_slot_data()["trap_identities"]["items"]
        trap_names = {e.name for e in TRAP_REGISTRY}
        drawn = [i for i in self.multiworld.itempool
                 if i.player == self.player and i.name in trap_names]
        self.assertTrue(drawn, "trap_fill_percentage 50 drew no traps")
        by_name = {e.name: e.key for e in TRAP_REGISTRY}
        for item in drawn:
            self.assertEqual(items[str(item.code)], by_name[item.name])

    def test_the_block_survives_a_json_round_trip(self):
        sd = self.world.fill_slot_data()
        self.assertEqual(json.loads(json.dumps(sd))["trap_identities"], sd["trap_identities"])


class TestNoTraps(CTRTestBase):
    run_default_tests = False
    options = {"trap_fill_percentage": 0}

    def test_the_block_does_not_depend_on_trap_fill(self):
        self.assertEqual(self.world.fill_slot_data()["trap_identities"],
                         trap_identities_block(ctrAPWorld.item_name_to_id))
