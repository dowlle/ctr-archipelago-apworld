"""Pad Approach Hints (native #124, ruling of 2026-07-20, built 2026-11-02).

The option is a client setting: off by default, display and hint only. It
rides the content-plan envelope as `pad_approach_hints: true` only when on,
so an option-off room's slot_data is unchanged. The draw never reads it. The
paired native reader is ap/ap_pad_hints_logic.h (tools/test-pad-approach-hints.cpp).
"""
import copy
import json
import random
import unittest

from Options import OptionError

from .. import content_plan
from ..Options import PadApproachHints, ap_ctr_option_groups
from .test_content_plan import make_world
from .test_item_packs import pack_options


class TestPadApproachHints(unittest.TestCase):
    def test_off_by_default_in_the_display_group(self):
        self.assertEqual(PadApproachHints.default, 0)
        self.assertIn(PadApproachHints, ap_ctr_option_groups["Display"])
        self.assertIn("cannot be undone", PadApproachHints.__doc__)

    def test_off_sends_no_key(self):
        co = make_world(pack_options(), seed=3).fill_slot_data()["ctr_options"]
        self.assertNotIn("pad_approach_hints", co)

    def test_on_sends_true_and_takes_no_draw(self):
        off = make_world(pack_options(), seed=3)
        on = make_world(pack_options(pad_approach_hints=True), seed=3)
        wire_off, wire_on = off.fill_slot_data(), on.fill_slot_data()
        self.assertIs(wire_on["ctr_options"].pop("pad_approach_hints"), True)
        wins = wire_off.pop("win_logic")
        complete = wire_on.pop("win_logic")
        self.assertEqual({code: check for code, check in complete["checks"].items()
                          if check["kind"] != "hint"}, wins["checks"])
        self.assertEqual(json.dumps(wire_on, sort_keys=True), json.dumps(wire_off, sort_keys=True))

    def test_on_exports_every_addressed_location_including_non_wins(self):
        world = make_world(pack_options(pad_approach_hints=True, podium_rungs=["held_1st", "finish_any"],
                                        podium_placement_checks=True, lettersanity="locations_and_items", box_locations=True,
                                        lap_completion_checks=True), seed=3)
        block = world.fill_slot_data()["win_logic"]
        self.assertTrue({"box", "letter", "lap", "podium"}.issubset(
            {check["kind"] for check in world.ctr_content_plan["checks"]}))
        expected = {str(location.address) for location in world.multiworld.get_locations(world.player)
                    if location.address is not None}
        self.assertEqual(set(block["checks"]), expected)
        self.assertTrue(any(check["kind"] == "hint" for check in block["checks"].values()))

    def test_all_family_wire_matches_live_reachability(self):
        from .test_content_bosses import boss_options
        from .test_win_logic_parity import WireEvaluator, _states, BOSS_FLAGS
        for mode in ("shared_global", "per_character"):
            options = boss_options(pad_approach_hints=True, itemsanity=True, hit_character=True,
                                   box_locations=True, lap_completion_checks=True,
                                   podium_placement_checks=True, podium_rungs=["held_1st", "finish_any"],
                                   lettersanity="locations_and_items", crystalsanity=True,
                                   progressive_boost=mode, progressive_stats=mode,
                                   character_unlocks=True, racer_locked_pads=3,
                                   wumpa_shop_slots=3, wumpa_shop_progression="allowed",
                                   cup_sweep_checks=True)
            options["content_pool"]["cups"]["count"] = 3
            options["content_pool"]["crystals"]["count"] = 3
            options["item_pool"]["base"]["trophies"] = 12
            world = make_world(options, seed=92, stop_before="generate_basic")
            kinds = {check["kind"] for check in world.ctr_content_plan["checks"]}
            self.assertTrue({"box", "letter", "lap", "podium", "itemsanity", "hit", "crystal_pickup",
                             "crystal", "wumpa_shop", "cup", "cup_sweep", "boss_race"}.issubset(kinds))
            data = world.fill_slot_data()
            for index, (state, received) in enumerate(_states(world.multiworld, random.Random(42), 12)):
                # Event-expanded wire represents actual earned event knowledge.
                for location in world.multiworld.get_locations(1):
                    if location.address is None and location.item is not None:
                        while state.has(location.item.name, 1):
                            state.remove(location.item)
                state.sweep_for_advancements()
                evaluator = WireEvaluator(data["win_logic"], data["ctr_options"], received,
                                          sum(state.has(name, 1) for name in BOSS_FLAGS), world.item_name_to_id)
                for location in world.multiworld.get_locations(1):
                    if location.address is not None:
                        with self.subTest(mode=mode, state=index, location=location.name):
                            self.assertEqual(evaluator.in_logic(location.address), location.can_reach(state))

    def test_tracker_restores_it(self):
        world = make_world(pack_options(pad_approach_hints=True), seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.options.pad_approach_hints.value, 1)
        self.assertEqual(other.fill_slot_data(), wire)

    def test_bad_value_refuses_on_restore(self):
        wire = json.loads(json.dumps(make_world(pack_options(pad_approach_hints=True), seed=3).fill_slot_data()))
        for value in (False, 1, "true"):
            forged = copy.deepcopy(wire)
            forged["ctr_options"]["pad_approach_hints"] = value
            with self.subTest(value=value), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)

    def test_listed_as_optional_envelope_key(self):
        self.assertIn("pad_approach_hints", content_plan.ENVELOPE_OPTIONAL)


if __name__ == "__main__":
    unittest.main()
