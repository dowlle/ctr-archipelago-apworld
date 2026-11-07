"""Logic for every pad location on every seed (A3-37b, ruling of 2026-11-07 12:35 CET,
"Yes, export all").

Native shows a pad's open look only while an open check behind it is in logic
(native #616). Before this row the `win_logic` block carried a row for an item
box, Wumpa check, CTR letter or podium rung only with `pad_approach_hints` on,
and a check without a row counts as in logic, so such a pad stayed green. Now
every seed carries the complete graph (block version 2, kind `hint` for the
non-wins), the block Pad Approach Hints already sent. The win rows are the
ones the win-only graph gives, so race-loss stakes do not move.
"""
import json
import random
import unittest

from .. import content_plan
from ..logic_terms import term_of
from ..win_logic import ForeignRuleError, snapshot_rules, wire_block
from .test_content_plan import make_world
from .test_item_packs import pack_options


def _resolved(block):
    """{code: (kind, region term, rule)}: the rows with their region index
    replaced by the term, so blocks with different region tables compare."""
    return {code: (row["kind"], json.dumps(block["regions"][row["region"]]), json.dumps(row["rule"]))
            for code, row in block["checks"].items()}


def _nodes(block):
    """Term nodes over every region and rule: an upper bound of native's
    node table, which shares nothing between terms."""
    def count(term):
        if isinstance(term, list) and term[0] in ("all", "any"):
            return 1 + sum(count(child) for child in term[1:])
        return 1
    return (sum(count(region) for region in block["regions"])
            + sum(count(row["rule"]) for row in block["checks"].values()))


def _option_sets():
    yield "default", pack_options()
    yield "families", pack_options(podium_rungs=["held_1st", "finish_any"], podium_placement_checks=True,
                                   lettersanity="locations_and_items", box_locations=True,
                                   lap_completion_checks=True, wumpa_check="per_track")
    yield "capability", pack_options(box_locations=True, progressive_boost="per_character",
                                     progressive_stats="per_character", character_unlocks=True,
                                     racer_locked_pads=3, lettersanity="locations_and_items")


class TestWinLogicEveryLocation(unittest.TestCase):
    def test_every_addressed_location_has_a_row_without_the_option(self):
        for label, options in _option_sets():
            for seed in (3, 17):
                with self.subTest(options=label, seed=seed):
                    world = make_world(options, seed=seed)
                    data = world.fill_slot_data()
                    self.assertNotIn("pad_approach_hints", data["ctr_options"])
                    block = data["win_logic"]
                    self.assertEqual(block["version"], 2)
                    expected = {str(location.address) for location in world.multiworld.get_locations(world.player)
                                if location.address is not None}
                    self.assertEqual(set(block["checks"]), expected)
                    wins = content_plan.win_kinds(world.ctr_content_plan)
                    for code, row in block["checks"].items():
                        self.assertEqual(row["kind"], wins.get(int(code), "hint"))

    def test_pad_families_get_rows(self):
        world = make_world(dict(_option_sets())["families"], seed=3)
        block = world.fill_slot_data()["win_logic"]
        kinds = {check["location"]: check["kind"] for check in world.ctr_content_plan["checks"]}
        for family in ("box", "letter", "podium", "wumpa"):
            codes = [code for code, kind in kinds.items() if kind == family]
            with self.subTest(family=family):
                self.assertTrue(codes)
                for code in codes:
                    self.assertEqual(block["checks"][str(code)]["kind"], "hint")

    def test_win_rows_unchanged(self):
        """The win rows, regions resolved, are exactly the win-only graph's,
        the block every seed carried before A3-37b. `families` and `start`
        are unchanged too; only `version`, hint rows and their regions are new."""
        for label, options in _option_sets():
            with self.subTest(options=label):
                world = make_world(options, seed=5)
                full = world.fill_slot_data()["win_logic"]
                wins_only = wire_block(world, include_hints=False)
                self.assertEqual(wins_only["version"], 1)
                resolved = _resolved(full)
                self.assertEqual({code: resolved[code] for code in wins_only["checks"]}, _resolved(wins_only))
                self.assertTrue(all(full["checks"][code]["kind"] == "hint"
                                    for code in set(full["checks"]) - set(wins_only["checks"])))
                self.assertEqual(full["families"], wins_only["families"])
                self.assertEqual(full["start"], wins_only["start"])

    def test_placement_does_not_depend_on_the_option(self):
        """The rules are the same callables with the option on or off, so
        the placement and every other slot_data key match."""
        from Fill import distribute_items_restrictive
        for seed in (3, 29):
            off = make_world(pack_options(box_locations=True), seed=seed)
            on = make_world(pack_options(box_locations=True, pad_approach_hints=True), seed=seed)
            for world in (off, on):
                distribute_items_restrictive(world.multiworld)
            placed = [{loc.name: (loc.item.name, loc.item.player) for loc in w.multiworld.get_locations()
                       if loc.item is not None} for w in (off, on)]
            with self.subTest(seed=seed):
                self.assertEqual(placed[0], placed[1])
                wire_on = on.fill_slot_data()
                wire_on["ctr_options"].pop("pad_approach_hints")
                self.assertEqual(json.dumps(wire_on, sort_keys=True),
                                 json.dumps(off.fill_slot_data(), sort_keys=True))

    def test_foreign_wrap_on_a_non_win_keeps_the_win_only_block(self):
        world = make_world(pack_options(box_locations=True), seed=3)
        snapshot_rules(world)
        wins = content_plan.win_kinds(world.ctr_content_plan)
        box = next(location for location in world.multiworld.get_locations(world.player)
                   if location.address is not None and location.address not in wins
                   and term_of(location) is not None)
        previous = box.access_rule
        box.access_rule = lambda state: state.has("Foreign Unlock", 2) and previous(state)
        with self.assertRaises(ForeignRuleError):
            wire_block(world)
        with self.assertLogs("worlds.ctr.slot_data", level="WARNING"):
            block = world.fill_slot_data()["win_logic"]
        self.assertEqual(block, wire_block(world, include_hints=False))
        self.assertEqual(block["version"], 1)
        self.assertNotIn(str(box.address), block["checks"])

    def test_foreign_wrap_on_a_reached_proof_falls_back(self):
        """A win or shared rule that reads another check through `Reached`
        sees a wrapped target as a foreign rule, so the fallback still runs."""
        from ..logic_terms import Reached
        world = make_world(pack_options(box_locations=True), seed=3)
        snapshot_rules(world)
        target = next(location for location in world.multiworld.get_locations(world.player)
                      if location.address is not None and term_of(location) is not None)
        previous = target.access_rule
        target.access_rule = lambda state: state.has("Foreign Unlock", 2) and previous(state)
        from ..win_logic import _Encoder
        with self.assertRaises(ForeignRuleError):
            Reached({target.address: target}, target.address, "pad").wire(_Encoder(world))

    def test_block_fits_native_tables(self):
        """Native refuses a block over its tables (ap_win_logic.h): 4,096
        checks, 1,024 regions, 16,384 nodes."""
        rng = random.Random(7)
        for label, options in _option_sets():
            world = make_world(options, seed=rng.randrange(1000))
            block = world.fill_slot_data()["win_logic"]
            with self.subTest(options=label):
                self.assertLessEqual(len(block["checks"]), 4096)
                self.assertLessEqual(len(block["regions"]), 1024)
                self.assertLessEqual(_nodes(block), 16384)


if __name__ == "__main__":
    unittest.main()
