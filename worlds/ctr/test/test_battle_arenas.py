"""include_battle_arenas off removes the four arena checks and nothing else (#364).

The Purple CTR Token items stay in the pool and can be found anywhere. The
Purple Gem Cup keeps its token requirement.
"""

from Fill import distribute_items_restrictive
from test.general import gen_steps
from . import setup_multiworld
from worlds.AutoWorld import call_all

from . import CTRTestBase
from .. import ctrAPWorld
from ..destinations import ARENA_TRACKS


ARENA_LOCATIONS = {f"{track}: Crystal Challenge" for track in ARENA_TRACKS}


def _purple_count(multiworld, player):
    # The start bootstrap may have seated a Token on a check in pre_fill.
    return sum(item.name == "Purple CTR Token" for item in multiworld.itempool if item.player == player) + sum(
        location.item is not None and location.item.name == "Purple CTR Token"
        for location in multiworld.get_locations(player))


class ArenaChecksMixin:
    def test_pool_balanced(self):
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(pool), len(self.multiworld.get_unfilled_locations(self.player)))


class TestBattleArenasOff(ArenaChecksMixin, CTRTestBase):
    run_default_tests = False
    options = {"include_battle_arenas": False, "accessibility": "full"}

    def test_no_arena_locations_but_purple_items_remain(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertFalse(ARENA_LOCATIONS & names)
        self.assertEqual(_purple_count(self.multiworld, self.player), 4)



class TestBattleArenasOffVanilla(ArenaChecksMixin, CTRTestBase):
    run_default_tests = False
    options = {"include_battle_arenas": False,
               "warppad_unlock_requirements": "vanilla", "accessibility": "full"}

    def test_purple_items_remain(self):
        self.assertEqual(_purple_count(self.multiworld, self.player), 4)


class TestBattleArenasOn(ArenaChecksMixin, CTRTestBase):
    run_default_tests = False
    options = {"include_battle_arenas": True, "accessibility": "full",
               "crystal_arenas": ["Rocky Road", "Rampage Ruins", "Skull Rock", "Nitro Court"]}

    def test_four_arena_locations_and_tokens(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertTrue(ARENA_LOCATIONS <= names)
        self.assertEqual(_purple_count(self.multiworld, self.player), 4)
        self.assertIs(self.world.fill_slot_data()["ctr_options"]["include_battle_arenas"], True)



