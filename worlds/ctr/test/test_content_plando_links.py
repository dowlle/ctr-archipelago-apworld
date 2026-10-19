"""Plando and item links on content plans (#133 PR 4f).

The rooms below run the framework phases in Main.py's order: links formed
before generate_early, blocks parsed before generate_basic, then link_items,
plando, pre_fill, the fill and post_fill. The wire ledger stays the creation
plan; plando and links move copies the world created and never add or drop a
selected one.
"""
import copy
import json
import unittest
from argparse import Namespace
from collections import Counter

from BaseClasses import CollectionState, MultiWorld, PlandoOptions
from Fill import (distribute_items_restrictive, distribute_planned_blocks, parse_planned_blocks,
                  resolve_early_locations_for_planned)
from Options import ItemLinks, OptionError, PlandoItems
from worlds.AutoWorld import call_all

from .. import ctrAPWorld, content_item_pool
from .test_content_plan import make_world, profile_options

STEPS = ("generate_early", "create_regions", "create_items", "set_rules", "connect_entrances")
TROPHY = ["Crash Cove: Trophy Race", "Roo's Tubes: Trophy Race", "Mystery Caves: Trophy Race",
          "Sewer Speedway: Trophy Race", "Tiger Temple: Trophy Race", "Coco Park: Trophy Race",
          "Blizzard Bluff: Trophy Race"]


def room(players=1, plando=None, links=None, seed=7, options=None, stop=None):
    """A room of content-plan slots in Main.py's phase order. `plando` and
    `links` map a player to its option value. `stop` names the phase to stop
    before ("pre_fill", "fill" or "post_fill")."""
    ids = range(1, players + 1)
    mw = MultiWorld(players)
    mw.game = {p: ctrAPWorld.game for p in ids}
    mw.player_name = {p: f"Slot{p}" for p in ids}
    mw.set_seed(seed)
    mw.seed_name = str(seed)
    mw.plando_options = PlandoOptions.items
    opts = options or profile_options()
    args = Namespace()
    for name, cls in ctrAPWorld.options_dataclass.type_hints.items():
        setattr(args, name, {p: cls.from_any(copy.deepcopy(opts.get(name, cls.default))) for p in ids})
    args.plando_items = {p: PlandoItems.from_any(copy.deepcopy((plando or {}).get(p, []))) for p in ids}
    args.item_links = {p: ItemLinks.from_any(copy.deepcopy((links or {}).get(p, []))) for p in ids}
    mw.set_options(args)
    mw.set_item_links()
    mw.state = CollectionState(mw)
    for step in STEPS:
        call_all(mw, step)
    mw.plando_item_blocks = parse_planned_blocks(mw)
    call_all(mw, "generate_basic")
    mw.link_items()
    mw._all_state = None
    resolve_early_locations_for_planned(mw)
    distribute_planned_blocks(mw, [b for p in mw.plando_item_blocks for b in mw.plando_item_blocks[p]])
    if stop == "pre_fill":
        return mw
    call_all(mw, "pre_fill")
    if stop == "fill":
        return mw
    distribute_items_restrictive(mw)
    if stop == "post_fill":
        return mw
    call_all(mw, "post_fill")
    return mw


def block(item, locations, from_pool=True, world=False, count=None):
    value = dict(items=item if isinstance(item, (list, dict)) else [item], locations=locations,
                 from_pool=from_pool, world=world, force=True)
    if count is not None:
        value["count"] = count
    return value


def holder(mw, name, player=1):
    return [loc for loc in mw.get_filled_locations() if loc.item.name == name and loc.item.player == player]


LINK = [{"name": "Shared", "item_pool": ["Key", "Trophy"], "replacement_item": None, "link_replacement": None}]


class TestPlandoFromPool(unittest.TestCase):
    def test_takes_the_created_copy_and_keeps_the_wire(self):
        plain = room()
        mw = room(plando={1: [block("Red Gem", ["Crash Cove: Trophy Race"])]})
        world = mw.worlds[1]
        location = mw.get_location("Crash Cove: Trophy Race", 1)
        self.assertEqual(location.item.name, "Red Gem")
        self.assertTrue(location.locked)
        self.assertIn(id(location.item), {id(i) for i in world.ctr_created_items})
        self.assertEqual(len(holder(mw, "Red Gem")), 1)
        # The wire is the creation ledger: plando changes no row.
        wire = json.loads(json.dumps(world.fill_slot_data()))
        self.assertEqual(wire["content_plan"], json.loads(json.dumps(plain.worlds[1].fill_slot_data()))["content_plan"])
        self.assertEqual(world.ctr_framework_accounting["from_pool"], Counter({"Red Gem": 1}))
        self.assertTrue(all(loc.item for loc in mw.get_locations(1)))

    def test_more_copies_than_created_is_refused(self):
        with self.assertRaisesRegex(OptionError, "may take 2 'Red Gem' from the pool, but this content plan creates 1"):
            room(plando={1: [block(["Red Gem", "Red Gem"], TROPHY[:2])]})

    def test_blocks_add_up(self):
        with self.assertRaisesRegex(OptionError, "may take 2 'Red Gem'"):
            room(plando={1: [block("Red Gem", TROPHY[:1]), block("Red Gem", TROPHY[1:2])]})

    def test_an_unselected_item_is_refused(self):
        with self.assertRaisesRegex(OptionError, "'Purple CTR Token' from the pool, but this content plan creates 0"):
            room(plando={1: [block("Purple CTR Token", TROPHY[:1])]})

    def test_a_linked_item_is_refused(self):
        with self.assertRaisesRegex(OptionError, "an item link\\s+of this player shares that item"):
            room(players=2, links={1: LINK, 2: LINK}, plando={1: [block("Key", TROPHY[:1])]})

    def test_a_synthesized_copy_is_refused(self):
        mw = room(stop="pre_fill")
        world = mw.worlds[1]
        location = next(loc for loc in mw.get_unfilled_locations(1))
        location.place_locked_item(world.create_item("Key"))
        with self.assertRaisesRegex(OptionError, "placed a new copy of Key"):
            call_all(mw, "pre_fill")


class TestExplicitPlando(unittest.TestCase):
    def test_filler_pays_for_the_added_item(self):
        mw = room(plando={1: [block(["Wumpa Fruit"] * 2, TROPHY[:2], from_pool=False)]}, stop="fill")
        world = mw.worlds[1]
        self.assertEqual(len(world.ctr_plando_removed), 2)
        self.assertTrue(all(i.name in content_item_pool.filler_family(world)[0] for i in world.ctr_plando_removed))
        self.assertEqual(len(mw.itempool), len(mw.get_unfilled_locations()))
        distribute_items_restrictive(mw)
        call_all(mw, "post_fill")
        self.assertTrue(all(loc.item for loc in mw.get_locations(1)))
        # Every selected copy still goes out.
        for row in world.ctr_content_items.rows:
            self.assertEqual(len(holder(mw, row.name)), row.remaining, row.name)

    def test_a_ledger_item_is_refused(self):
        with self.assertRaisesRegex(OptionError, "adds Key with from_pool: false"):
            room(plando={1: [block("Key", TROPHY[:1], from_pool=False)]})

    def test_no_filler_left_is_refused(self):
        filler = room().worlds[1].ctr_content_items.filler_count
        self.assertLess(filler, len(TROPHY))
        with self.assertRaisesRegex(OptionError, "Removing a selected item instead is not allowed"):
            room(plando={1: [block({"Wumpa Fruit": len(TROPHY)}, TROPHY, from_pool=False)]})

    def test_a_trap_pays_when_no_plain_filler_is_left(self):
        options = profile_options()
        options["trap_fill_percentage"] = 100
        mw = room(options=options, plando={1: [block("Wumpa Fruit", TROPHY[:1], from_pool=False)]}, stop="fill")
        world = mw.worlds[1]
        self.assertEqual([i.name in world.item_name_groups["Traps"] for i in world.ctr_plando_removed], [True])


class TestItemLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mw = room(players=2, links={1: LINK, 2: LINK})

    def test_members_receive_their_whole_supply(self):
        mw = self.mw
        self.assertEqual(len(mw.groups), 1)
        group = next(iter(mw.groups))
        self.assertEqual(sorted(i.name for i in mw.itempool if i.player == group).count("Key"), 4)
        state = mw.get_all_state(False)
        for player in (1, 2):
            self.assertEqual(state.count("Key", player), 4)
            self.assertEqual(state.count("Trophy", player), 5)
            accounting = mw.worlds[player].ctr_framework_accounting
            self.assertEqual(accounting["linked"], Counter({"Key": 4, "Trophy": 5}))
        self.assertTrue(mw.can_beat_game())

    def test_wire_is_unchanged_by_the_link(self):
        plain = room(players=2)
        for player in (1, 2):
            self.assertEqual(json.loads(json.dumps(self.mw.worlds[player].fill_slot_data()))["content_plan"],
                             json.loads(json.dumps(plain.worlds[player].fill_slot_data()))["content_plan"])

    def test_tracker_restores_a_linked_slot(self):
        wire = json.loads(json.dumps(self.mw.worlds[1].fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, wire["content_plan"])

    def test_a_ledger_replacement_item_is_refused(self):
        link = [dict(LINK[0], replacement_item="Red Gem")]
        with self.assertRaisesRegex(OptionError, "names 'Red Gem' as its replacement_item"):
            room(players=2, links={1: link, 2: link})

    def test_cross_world_plando_and_links_fill(self):
        mw = room(players=2, links={1: LINK, 2: LINK},
                  plando={1: [block("Blue Gem", TROPHY[:3], world=True)],
                          2: [block("Wumpa Fruit", TROPHY[:1], from_pool=False)]})
        placed = holder(mw, "Blue Gem", 1)
        self.assertEqual([loc.player for loc in placed], [2])
        self.assertEqual(len(mw.worlds[2].ctr_plando_removed), 1)
        self.assertTrue(all(loc.item for loc in mw.get_locations() if loc.address is not None))


class TestBeforeOutput(unittest.TestCase):
    def test_a_dropped_copy_is_refused(self):
        mw = room(stop="post_fill")
        location = next(loc for loc in mw.get_filled_locations(1) if loc.item.name == "Key")
        location.item.location = None
        location.item = None
        with self.assertRaisesRegex(OptionError, "without a location \\(Key\\)"):
            call_all(mw, "post_fill")

    def test_an_extra_start_is_refused(self):
        mw = room(stop="post_fill")
        mw.push_precollected(mw.worlds[1].create_item("Key"))
        with self.assertRaisesRegex(OptionError, "start inventory of Slot1 differs"):
            call_all(mw, "post_fill")


if __name__ == "__main__":
    unittest.main()
