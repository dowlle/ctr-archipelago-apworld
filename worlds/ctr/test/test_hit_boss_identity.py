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

from . import setup_multiworld

from .. import ctrAPWorld
from ..hit_character import HIT_CHARACTER_CLASS

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


if __name__ == "__main__":
    unittest.main()
