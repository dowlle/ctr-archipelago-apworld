"""A start with no check that can hold progression (A4-82, apworld #229).

The nightly sanity YAML 316-0 rolls Item Box Count 0, shared Progressive Boost
and logic difficulty easy or medium, and excludes Weapon Crates, Wumpa Crates and
Loose Wumpa Fruit. Every race check then needs the first boost, and every check
open at the start is excluded, so AP's fill had nowhere to put that boost and
failed on every AP seed (A4-76: 39 of 250 nightly seeds). Ruling 2026-11-14:
such YAMLs must generate. The slot now starts with its first boost, taken from
its pool exactly as `start_inventory_from_pool` would (sphere0_guard.start_opener).
Without that grant the guard refuses the slot with a readable message instead
of a FillError, because excluded checks no longer count as starting checks.
"""
import copy
import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import yaml

from BaseClasses import CollectionState, MultiWorld
from Fill import distribute_items_restrictive
from Options import OptionError
from worlds.AutoWorld import call_all
from worlds.generic.Rules import exclusion_rules

from .. import ctrAPWorld, sphere0_guard
from .test_content_plan import make_world

FIXTURE = Path(__file__).parent / "fixtures" / "a4_82_no_start_progression_spot.yaml"
BOOST = "Progressive Boost"


def fixture(**overrides):
    options = yaml.safe_load(FIXTURE.read_text())[ctrAPWorld.game]
    options.update(overrides)
    return options


def generate(options, seed, until="post_fill"):
    """One slot through Main.py's steps: the start inventory is granted after
    generate_early and exclusions apply before generate_basic."""
    mw = MultiWorld(1)
    mw.game[1] = ctrAPWorld.game
    mw.player_name = {1: "Start"}
    mw.set_seed(seed)
    mw.seed_name = str(seed)
    args = Namespace()
    for name, cls in ctrAPWorld.options_dataclass.type_hints.items():
        setattr(args, name, {1: cls.from_any(copy.deepcopy(options.get(name, cls.default)))})
    mw.set_options(args)
    mw.state = CollectionState(mw)
    world = mw.worlds[1]
    # Generate.py expands location groups before generation.
    groups = ctrAPWorld.location_name_groups
    world.options.exclude_locations.value = {name for group in world.options.exclude_locations.value
                                             for name in groups.get(group, {group})}
    call_all(mw, "generate_early")
    for option in (world.options.start_inventory, world.options.start_inventory_from_pool):
        for name, count in option.value.items():
            for _ in range(count):
                mw.push_precollected(mw.create_item(name, 1))
    if until == "generate_early":
        return world
    for step in ("create_regions", "create_items", "set_rules"):
        call_all(mw, step)
    exclusion_rules(mw, 1, world.options.exclude_locations.value)
    for step in ("connect_entrances", "generate_basic"):
        call_all(mw, step)
    if until == "generate_basic":
        return world
    call_all(mw, "pre_fill")
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    return world


def placements(world):
    return sorted((loc.name, loc.item.name) for loc in world.multiworld.get_locations(1))


def start_row(world, name):
    return next(row for row in world.ctr_content_items.rows if row.name == name)


class TestNoStartProgressionSpot(unittest.TestCase):

    def test_failing_roll_starts_with_the_first_boost_and_fills(self):
        world = generate(fixture(), 1)
        self.assertEqual(world.ctr_start_opener, BOOST)
        self.assertEqual([item.name for item in world.multiworld.precollected_items[1]], [BOOST])
        self.assertEqual(start_row(world, BOOST).start_from_pool, 1)
        self.assertTrue(world.multiworld.fulfills_accessibility())

    def test_the_granted_start_has_room_for_progression(self):
        world = generate(fixture(), 1, until="generate_basic")
        self.assertGreaterEqual(sphere0_guard.sphere0_progression_spots(world),
                                sphere0_guard.MIN_STARTING_CHECKS)

    def test_same_seed_as_a_written_from_pool_start(self):
        # The grant is exactly the YAML start_inventory_from_pool: {Progressive Boost: 1}.
        granted = generate(fixture(), 2)
        written = generate(fixture(start_inventory_from_pool={BOOST: 1}), 2)
        self.assertFalse(hasattr(written, "ctr_start_opener"))
        self.assertEqual(granted.ctr_content_plan, written.ctr_content_plan)
        self.assertEqual(placements(granted), placements(written))

    def test_medium_and_blue_fire_rolls_get_it_too(self):
        for overrides in (dict(logic_difficulty="medium"), dict(progressive_boost_blue_fire=True)):
            with self.subTest(**overrides):
                world = generate(fixture(**overrides), 1, until="generate_early")
                self.assertEqual(world.ctr_start_opener, BOOST)
                self.assertEqual(world.options.start_inventory_from_pool.value, {BOOST: 1})
                self.assertEqual([item.name for item in world.multiworld.precollected_items[1]], [BOOST])

    def test_rolls_with_an_open_start_are_untouched(self):
        for overrides in (dict(logic_difficulty="hard"), dict(item_box_count=50), dict(progressive_boost="off"),
                          dict(exclude_locations=[])):
            with self.subTest(**overrides):
                world = generate(fixture(**overrides), 1, until="generate_early")
                self.assertFalse(hasattr(world, "ctr_start_opener"))
                self.assertEqual(world.multiworld.precollected_items[1], [])

    def test_guard_refuses_an_excluded_only_start_without_the_grant(self):
        with mock.patch.object(sphere0_guard, "start_opener", return_value=None):
            with self.assertRaises(OptionError) as raised:
                generate(fixture(), 1, until="generate_basic")
        self.assertIn("no check at the start that can hold progression", str(raised.exception))
        self.assertIn("exclude_locations", str(raised.exception))

    def test_start_opener_needs_no_manual_rules(self):
        # warp_pad_rules are never helped with a free item (Rulebook, manual
        # rules): the same empty start gets the boost without rules and none
        # with them. The guard then refuses it with the rules named.
        real = sphere0_guard.start_opener
        with mock.patch.object(sphere0_guard, "start_opener", return_value=None):
            world = generate(fixture(), 1, until="generate_early")
        self.assertEqual(real(world, world.ctr_content_plan), BOOST)
        world.options.warp_pad_rules.value = {"Crash Cove": {"item": "Trophy", "count": 1}}
        self.assertIsNone(real(world, world.ctr_content_plan))

    def test_shop_that_can_hold_progression_is_a_start(self):
        # Wumpa Shop slots that allow progression can take the first boost:
        # no grant and no refusal.
        world = generate(fixture(wumpa_shop_progression="allowed"), 1)
        self.assertFalse(hasattr(world, "ctr_start_opener"))
        self.assertEqual(world.multiworld.precollected_items[1], [])
        self.assertTrue(world.multiworld.fulfills_accessibility())

    def test_a_starting_weapon_opens_itemsanity_checks(self):
        # The plan model cannot see Itemsanity checks, so a slot that starts
        # with a weapon gets no grant: its weapon's checks are open.
        world = generate(fixture(start_inventory={"Bomb": 1}), 1)
        self.assertFalse(hasattr(world, "ctr_start_opener"))
        self.assertEqual([item.name for item in world.multiworld.precollected_items[1]], ["Bomb"])
        self.assertTrue(world.multiworld.fulfills_accessibility())

    def test_tracker_rebuilds_the_granted_start(self):
        world = generate(fixture(), 1, until="generate_basic")
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(start_row(other, BOOST).start_from_pool, 1)
        self.assertFalse(hasattr(other, "ctr_start_opener"))


if __name__ == "__main__":
    unittest.main()
