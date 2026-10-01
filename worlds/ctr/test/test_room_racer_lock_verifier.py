"""Room-level racer-lock verifier (`characters.verify_room_no_self_lock`).

The verifier runs once per room from `stage_post_fill` and shares one
all-items state across every CTR slot. These pin three things: it accepts
and rejects exactly what the per-world check did on unlinked rooms, it sees
racer unlocks shared through AP item links (the 2026-10-01 generation deep
dive's injected linked self-lock was accepted before), and the placement rule
refuses a link group's copy on the same forbidden checks as a personal one.
"""
import unittest
from argparse import Namespace

from BaseClasses import CollectionState, MultiWorld
from Fill import distribute_items_restrictive
from Options import ItemLinks, OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..characters import (
    racer_link_groups,
    racer_lock_forbidden_locations,
    unlock_item_name,
    verify_no_self_lock,
    verify_room_no_self_lock,
)
from ..progressive_capability import ROSTER

LOCKED = {"racer_locked_pads": 6, "starting_character": "crash_bandicoot",
          "accessibility": "full"}
SHARED_RACERS = [r for r in ROSTER if r != "Crash Bandicoot"]
GEN_STEPS = ("generate_early", "create_regions", "create_items", "set_rules",
             "connect_entrances", "generate_basic")


def _linked_room(seed):
    """Two CTR slots sharing every non-starting racer through one item link,
    filled the way Main.py does it (links resolved before pre_fill)."""
    mw = MultiWorld(2)
    mw.game = {1: ctrAPWorld.game, 2: ctrAPWorld.game}
    mw.player_name = {1: "Linked1", 2: "Linked2"}
    mw.set_seed(seed)
    link = [{"name": "SharedRacers", "item_pool": SHARED_RACERS,
             "replacement_item": "Wumpa Fruit", "link_replacement": None}]
    args = Namespace()
    for name, option in ctrAPWorld.options_dataclass.type_hints.items():
        setattr(args, name, {p: option.from_any(LOCKED.get(name, option.default))
                             for p in (1, 2)})
    args.item_links = {p: ItemLinks.from_any(link) for p in (1, 2)}
    mw.set_options(args)
    mw.set_item_links()
    mw.state = CollectionState(mw)
    for step in GEN_STEPS:
        call_all(mw, step)
    mw.link_items()
    mw._all_state = None
    call_all(mw, "pre_fill")
    distribute_items_restrictive(mw)
    return mw


def _group_unlock(mw):
    """(member world, racer, group-owned location holding its unlock) for a
    racer that member's own pads require."""
    for player in mw.player_ids:
        world = mw.worlds[player]
        for racer in sorted(set(world.ctr_racer_locks.values())):
            name = unlock_item_name(racer)
            groups = racer_link_groups(mw, player, name)
            for loc in mw.get_filled_locations():
                if loc.item.name == name and loc.item.player in groups \
                        and loc.player not in mw.groups:
                    return world, racer, loc
    return None


def _swap(a, b):
    a.item, b.item = b.item, a.item
    a.item.location, b.item.location = a, b


class TestLinkedRacerUnlocks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mw = _linked_room(777)

    def test_a_valid_linked_room_passes(self):
        self.assertTrue(self.mw.groups)
        self.assertIsNotNone(_group_unlock(self.mw), "no linked racer unlock was placed")
        call_all(self.mw, "post_fill")  # stage_post_fill runs the room verifier

    def test_a_linked_unlock_on_its_own_destination_is_rejected(self):
        """The deep dive's injected fault: move the group's copy onto a check
        of a destination whose pad requires that racer."""
        world, racer, holder = _group_unlock(self.mw)
        forbidden = racer_lock_forbidden_locations(world)[racer]
        target = next(loc for loc in forbidden if loc.item is not None and loc is not holder)
        _swap(holder, target)
        try:
            with self.assertRaises(OptionError) as ctx:
                verify_room_no_self_lock(self.mw)
            self.assertIn(racer, str(ctx.exception))
        finally:
            _swap(holder, target)
        verify_room_no_self_lock(self.mw)

    def test_a_linked_unlock_behind_its_own_racer_is_rejected(self):
        """The reachability half: the group's copy sits somewhere that needs
        the racer it unlocks. Stripping only the personal count used to leave
        the group copy in state, so the racer was received again through the
        link and the check passed."""
        world, racer, holder = _group_unlock(self.mw)
        name = unlock_item_name(racer)
        rule = holder.access_rule
        holder.access_rule = lambda state, n=name, p=world.player: state.has(n, p)
        try:
            with self.assertRaises(OptionError) as ctx:
                verify_room_no_self_lock(self.mw)
            self.assertIn(name, str(ctx.exception))
        finally:
            holder.access_rule = rule
        verify_room_no_self_lock(self.mw)

    def test_the_placement_rule_refuses_the_group_copy_only(self):
        world, racer, holder = _group_unlock(self.mw)
        group_copy = holder.item
        other = next(p for p in self.mw.player_ids if p != world.player)
        personal_other = self.mw.worlds[other].create_item(unlock_item_name(racer))
        for loc in racer_lock_forbidden_locations(world)[racer]:
            self.assertFalse(loc.item_rule(group_copy), loc.name)
            self.assertTrue(loc.item_rule(personal_other) or loc in
                            racer_lock_forbidden_locations(self.mw.worlds[other]).get(racer, ()),
                            loc.name)


class TestRoomVerifierMatchesPerWorld(unittest.TestCase):

    def test_two_slot_room_accepts_and_rejects_like_the_world_check(self):
        mw = setup_multiworld([ctrAPWorld, ctrAPWorld], seed=3, options=LOCKED)
        distribute_items_restrictive(mw)
        verify_room_no_self_lock(mw)
        for player in mw.player_ids:
            verify_no_self_lock(mw.worlds[player])

        world = mw.worlds[2]
        racer = sorted(set(world.ctr_racer_locks.values()))[0]
        name = unlock_item_name(racer)
        holder = next(loc for loc in mw.get_filled_locations()
                      if loc.item.player == 2 and loc.item.name == name)
        rule = holder.access_rule
        holder.access_rule = lambda state, n=name: state.has(n, 2)
        try:
            with self.assertRaises(OptionError):
                verify_room_no_self_lock(mw)
            with self.assertRaises(OptionError):
                verify_no_self_lock(world)
            verify_no_self_lock(mw.worlds[1])  # the other slot is untouched
        finally:
            holder.access_rule = rule
        verify_room_no_self_lock(mw)

    def test_the_shared_state_is_restored_between_checks(self):
        """A failed check for one racer must not leak into the next: the
        same room verifies clean before and after a rejected fault."""
        mw = setup_multiworld([ctrAPWorld, ctrAPWorld], seed=17, options=LOCKED)
        distribute_items_restrictive(mw)
        before = mw.get_all_state()
        verify_room_no_self_lock(mw)
        after = mw.get_all_state()
        self.assertEqual({p: dict(c) for p, c in before.prog_items.items()},
                         {p: dict(c) for p, c in after.prog_items.items()})


if __name__ == "__main__":
    unittest.main()
