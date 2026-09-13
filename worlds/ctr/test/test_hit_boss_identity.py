"""Ticket 12: the apworld consumer of the shared boss resolved-identity fixture.

`fixtures/ctr_hit_boss_identity.json` is a byte-identical copy of native
`tools/fixtures/ctr_hit_boss_identity.json`. Native pins its dispatch against the
same file, so a later boss randomizer cannot move only one consumer: the emitted
`bosses` table must equal the retail table here, and a substituted identity must
move the apworld boss route exactly as it moves native dispatch.
"""

import json
import os
import unittest

from test.general import setup_multiworld

from .. import ctrAPWorld
from ..hit_character import HIT_CHARACTER_CLASS, _build_boss_routes

PLAYER = 1
ITEMS_STEPS = ("generate_early", "create_regions", "create_items")
OPTIONS = {"hit_character": True,
           "slide_coliseum_races": "trophy_race",
           "turbo_track_races": "trophy_race"}

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "ctr_hit_boss_identity.json")


def _load_fixture():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


def _world():
    mw = setup_multiworld(ctrAPWorld, ITEMS_STEPS, seed=1, options=OPTIONS)
    return mw.worlds[PLAYER]


def _boss_location(world, code):
    name = {int(c): n for n, c in world.location_name_to_id.items()}[int(code)]
    return world.multiworld.regions.location_cache[PLAYER][name]


class TestSharedBossIdentityFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture = _load_fixture()
        cls.world = _world()
        cls.block = cls.world.ctr_hit_character_encounters

    def test_emitted_bosses_table_is_the_retail_fixture(self):
        emitted = {str(k): int(v) for k, v in self.block["bosses"].items()}
        self.assertEqual(emitted, self.fixture["retail_bosses"])

    def test_locations_match_the_fixture(self):
        emitted = {str(k): int(v) for k, v in self.block["locations"].items()}
        self.assertEqual(emitted, self.fixture["locations"])
        for cid, code in self.fixture["locations"].items():
            self.assertEqual(
                self.world.location_name_to_id[
                    HIT_CHARACTER_CLASS.location_name(int(cid))],
                code)

    def test_each_boss_win_routes_to_its_expected_hit(self):
        """Every boss race location yields a boss route for the fixture's
        identity, and that identity's Hit code is the expected one."""
        for boss_code, engine_id in self.fixture["retail_bosses"].items():
            with self.subTest(boss_code=boss_code):
                expected_hit = self.fixture["expected_hit_codes"][boss_code]
                self.assertEqual(self.fixture["locations"][str(engine_id)],
                                 expected_hit)
                region = _boss_location(self.world, boss_code).parent_region
                routes = _build_boss_routes(self.world, PLAYER, engine_id,
                                            self.block)
                self.assertTrue(any(r.boss_region is region for r in routes))

    def test_substituted_identity_moves_the_route(self):
        case = self.fixture["substituted_case"]
        boss_code = str(case["boss_key"])
        retail_id = self.fixture["retail_bosses"][boss_code]
        new_id = case["engine_id"]
        self.assertEqual(self.fixture["locations"][str(new_id)], case["hit_code"])

        block = dict(self.block)
        block["bosses"] = dict(self.block["bosses"])
        block["bosses"][boss_code] = new_id
        region = _boss_location(self.world, boss_code).parent_region

        new_routes = _build_boss_routes(self.world, PLAYER, new_id, block)
        old_routes = _build_boss_routes(self.world, PLAYER, retail_id, block)
        self.assertTrue(any(r.boss_region is region for r in new_routes))
        self.assertFalse(any(r.boss_region is region for r in old_routes))


if __name__ == "__main__":
    unittest.main()
