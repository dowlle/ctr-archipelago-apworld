"""include_battle_arenas off removes the four arena checks and nothing else (#364).

The Purple CTR Token items stay in the pool and can be found anywhere. The
Purple Gem Cup keeps its token requirement.
"""

from Fill import distribute_items_restrictive
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from . import CTRTestBase
from .. import ctrAPWorld
from ..destinations import ARENA_TRACKS


ARENA_LOCATIONS = {f"{track}: Crystal Challenge" for track in ARENA_TRACKS}


def _purple_count(multiworld, player):
    return sum(item.name == "Purple CTR Token" for item in multiworld.itempool
               if item.player == player)


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

    def test_wire_carries_the_option(self):
        wire = self.world.fill_slot_data()
        self.assertEqual(wire["schema_version"], 18)
        self.assertIs(wire["ctr_options"]["include_battle_arenas"], False)


class TestBattleArenasOffVanilla(ArenaChecksMixin, CTRTestBase):
    run_default_tests = False
    options = {"include_battle_arenas": False,
               "warppad_unlock_requirements": "vanilla", "accessibility": "full"}

    def test_purple_items_remain(self):
        self.assertEqual(_purple_count(self.multiworld, self.player), 4)


class TestBattleArenasOn(ArenaChecksMixin, CTRTestBase):
    run_default_tests = False
    options = {"include_battle_arenas": True, "accessibility": "full"}

    def test_four_arena_locations_and_tokens(self):
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertTrue(ARENA_LOCATIONS <= names)
        self.assertEqual(_purple_count(self.multiworld, self.player), 4)
        self.assertIs(self.world.fill_slot_data()["ctr_options"]["include_battle_arenas"], True)


def test_arena_off_seed_sweep():
    variants = (
        {},
        {"warppad_unlock_requirements": "vanilla"},
        {"warppad_unlock_requirements": "random_without_4_keys",
         "bosses_required_goal": 2},
        {"gems_required_goal": 2, "include_gem_cups": False,
         "shuffle_gems": True},
    )
    for variant in variants:
        for seed in range(1, 5):
            options = {"include_battle_arenas": False, "accessibility": "full",
                       **variant}
            mw = setup_multiworld(ctrAPWorld, gen_steps, seed=seed, options=options)
            distribute_items_restrictive(mw)
            call_all(mw, "post_fill")
            world = mw.worlds[1]
            assert not ARENA_LOCATIONS & {loc.name for loc in mw.get_locations(1)}
            assert _purple_count(mw, 1) == 4
            assert world.fill_slot_data()["ctr_options"]["include_battle_arenas"] is False


def test_arena_toggle_removes_exactly_four_locations():
    options = {"accessibility": "full"}
    on = setup_multiworld(ctrAPWorld, gen_steps, seed=31,
                          options={**options, "include_battle_arenas": True})
    off = setup_multiworld(ctrAPWorld, gen_steps, seed=31,
                           options={**options, "include_battle_arenas": False})
    assert len(on.get_locations(1)) - len(off.get_locations(1)) == 4
