"""Item links and the start bootstrap: a linked item leaves the slot's pool before
pre_fill, and the group's copy is what the fill places. The opening counts those
items, so the bootstrap has to be able to seat them."""
import copy
import unittest
from argparse import Namespace

from BaseClasses import CollectionState, MultiWorld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld, sphere0_guard

NARROW = dict(warppad_unlock_requirements="vanilla", progressive_boost="shared_global", podium_rungs=["held_1st"],
              cup_count=12, crystal_challenge_count=2, accessibility="full", wumpa_shop_slots=14)
LINK = [dict(name="Shared", item_pool=["Everything"], replacement_item=None, link_replacement=None)]


def linked_room(seed):
    mw = MultiWorld(2)
    mw.set_seed(seed)
    mw.seed_name = str(seed)
    args = Namespace()
    mw.player_name = {1: "P1", 2: "P2"}
    for player in (1, 2):
        mw.game[player] = ctrAPWorld.game
    options = dict(NARROW, item_links=LINK)
    for name, cls in ctrAPWorld.options_dataclass.type_hints.items():
        value = {player: cls.from_any(copy.deepcopy(options.get(name, cls.default))) for player in (1, 2)}
        setattr(args, name, value)
    mw.set_options(args)
    mw.set_item_links()
    mw.state = CollectionState(mw)
    for step in ("generate_early", "create_regions", "create_items", "set_rules", "connect_entrances", "generate_basic"):
        call_all(mw, step)
    mw.link_items()
    mw._all_state = None
    return mw


class TestLinkedOpening(unittest.TestCase):
    def test_the_bootstrap_sees_and_seats_group_copies(self):
        seated = 0
        for seed in range(1, 9):
            mw = linked_room(seed)
            world = mw.worlds[1]
            group = next(iter(mw.groups))
            own = [item for item in mw.itempool if sphere0_guard._own_item(world, item) and item.advancement]
            self.assertTrue(own)
            self.assertTrue(all(item.player == group for item in own), "Everything is linked")
            call_all(mw, "pre_fill")
            seats = [loc for loc in mw.get_filled_locations(1) if loc.address is not None and loc.locked
                     and loc.item.player == group]
            seated += len(seats)
        self.assertGreater(seated, 0)

    def test_a_group_copy_opens_the_receipt_in_the_sweep(self):
        mw = linked_room(1)
        world = mw.worlds[1]
        group = next(iter(mw.groups))
        copy_ = next(item for item in mw.itempool if item.player == group and item.name == "Trophy")
        state = sphere0_guard._collect(world, CollectionState(mw), [copy_])
        self.assertTrue(state.has("Trophy", 1), "the slot holds the linked Trophy")
