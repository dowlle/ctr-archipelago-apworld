"""Spoiler Items (#459): two useful reveal items that gate presentation only.

Pins the frozen names and codes, the zero, one or two copies per seed, the
supply refusal, the content-plan ledger rows and envelope, the Universal Tracker
restore from on, off and absent wire data, and that no rule needs either item.
"""
import copy
import json
import unittest

from BaseClasses import CollectionState, ItemClassification
from Options import OptionError

from . import CTRTestBase
from .. import content_plan, rung_sizer, spoiler_items
from .test_content_item_boxes import box_options, first_world
from .test_content_plan import make_world, profile_options

PREVIEW, BOXES = spoiler_items.WARP_PAD_PREVIEW_ITEM, spoiler_items.AP_BOX_COLOURS_ITEM


def reveal_items(world):
    return sorted(i.name for i in world.multiworld.itempool if i.name in (PREVIEW, BOXES))


class TestFrozenIdentities(unittest.TestCase):
    def test_names_codes_and_classification(self):
        from .. import ctrAPWorld
        self.assertEqual(ctrAPWorld.item_name_to_id[PREVIEW], 35010204)
        self.assertEqual(ctrAPWorld.item_name_to_id[BOXES], 35010205)
        self.assertEqual(spoiler_items.ITEM_CODES, {PREVIEW: 35010204, BOXES: 35010205})
        from ..minted_items_030 import MINTED_ITEMS_030
        rows = {name: cls for name, _code, cls in MINTED_ITEMS_030}
        self.assertEqual(rows[PREVIEW], ItemClassification.useful)
        self.assertEqual(rows[BOXES], ItemClassification.useful)


class TestOff(CTRTestBase):
    options = {"box_locations": True}

    def test_default_creates_nothing(self):
        self.assertFalse(self.world.options.spoiler_items.value)
        self.assertEqual(reveal_items(self.world), [])
        self.assertIs(self.world.fill_slot_data()["ctr_options"]["spoiler_items"], False)


class TestOnWithoutBoxes(CTRTestBase):
    options = {"spoiler_items": True}

    def test_one_preview(self):
        self.assertEqual(reveal_items(self.world), [PREVIEW])
        self.assertIs(self.world.fill_slot_data()["ctr_options"]["spoiler_items"], True)
        self.assertEqual(len(self.multiworld.itempool), len(self.multiworld.get_unfilled_locations(self.player)))


class TestOnWithColouredBoxes(CTRTestBase):
    options = {"spoiler_items": True, "box_locations": True, "color_boxes_by_item": True}

    def test_two_items_useful(self):
        self.assertEqual(reveal_items(self.world), [BOXES, PREVIEW])
        self.assertEqual({i.classification for i in self.multiworld.itempool if i.name in (PREVIEW, BOXES)},
                         {ItemClassification.useful})

    def test_no_rule_needs_either_item(self):
        state = CollectionState(self.multiworld)
        for item in self.multiworld.itempool:
            if item.name not in (PREVIEW, BOXES) and item.advancement:
                state.collect(item, True)
        state.sweep_for_advancements()
        for location in self.multiworld.get_locations(self.player):
            self.assertTrue(location.can_reach(state), location.name)


class TestOnWithPinkBoxes(CTRTestBase):
    options = {"spoiler_items": True, "box_locations": True, "color_boxes_by_item": False}

    def test_no_box_colour_item_without_colours(self):
        self.assertEqual(reveal_items(self.world), [PREVIEW])


class TestSupply(unittest.TestCase):
    def test_refusal_names_the_missing_items(self):
        names = [PREVIEW, BOXES]
        spoiler_items.raise_if_items_do_not_fit(10, 10, names)
        spoiler_items.raise_if_items_do_not_fit(9, 10, names)
        spoiler_items.raise_if_items_do_not_fit(13, 10, names)  # someone else overflows
        spoiler_items.raise_if_items_do_not_fit(12, 10, [])
        with self.assertRaisesRegex(OptionError, r"needs 1 more location\(s\) for AP Box Colours,"):
            spoiler_items.raise_if_items_do_not_fit(11, 10, names)
        with self.assertRaisesRegex(OptionError, r"needs 2 more location\(s\) for Warp Pad Preview and AP Box"):
            spoiler_items.raise_if_items_do_not_fit(12, 10, names)
        with self.assertRaisesRegex(OptionError, r"needs 1 more location\(s\) for Warp Pad Preview,"):
            spoiler_items.raise_if_items_do_not_fit(11, 10, [PREVIEW])

    def test_rung_sizer_counts_the_reveal_items(self):
        off = make_world({"box_locations": True}, seed=459)
        on = make_world({"box_locations": True, "spoiler_items": True}, seed=459)
        self.assertEqual(rung_sizer.predicted_mandatory_pool(on), rung_sizer.predicted_mandatory_pool(off) + 2)


class TestContentPlan(unittest.TestCase):
    def test_ledger_rows_and_envelope(self):
        for boxes in (False, True):
            with self.subTest(boxes=boxes):
                options = dict(box_options() if boxes else profile_options(), spoiler_items=True)
                world = first_world(options) if boxes else make_world(options, seed=459)
                plan = world.ctr_content_plan
                want = {"warp_pad_preview": True, **({"ap_box_colours": True} if boxes else {})}
                self.assertEqual(plan["item_packs"], want)
                self.assertIn("item_packs_v1", plan["required_features"])
                rows = {r["item"]: r for r in plan["items"]["rows"]}
                for code in (35010204, 35010205) if boxes else (35010204,):
                    self.assertEqual((rows[code]["base"], rows[code]["extra"], rows[code]["remaining"]), (1, 0, 1))
                self.assertEqual(35010205 in rows, boxes)
                self.assertEqual(reveal_items(world), sorted([PREVIEW] + ([BOXES] if boxes else [])))
                self.assertEqual(len(world.multiworld.itempool), len(world.multiworld.get_unfilled_locations(1)))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                self.assertIs(wire["ctr_options"]["spoiler_items"], True)
                self.assertTrue(content_plan.validate(wire["content_plan"]))

    def test_off_plan_has_no_reveal_rows(self):
        world = make_world(profile_options(), seed=459)
        self.assertNotIn("warp_pad_preview", world.ctr_content_plan.get("item_packs", {}))
        self.assertIs(world.fill_slot_data()["ctr_options"]["spoiler_items"], False)

    def test_pack_record_and_envelope_checks(self):
        content_plan.check_pack_settings({"warp_pad_preview": True, "ap_box_colours": True})
        for bad in ({"warp_pad_preview": 1}, {"ap_box_colours": True}, {"warp_pad_preview": True, "other": True}):
            with self.subTest(bad=bad), self.assertRaises(OptionError):
                content_plan.check_pack_settings(bad)
        boxed = {"item_boxes": {}, "item_packs": {"warp_pad_preview": True, "ap_box_colours": True}}
        content_plan.check_spoiler_envelope(boxed, {"spoiler_items": True, "color_boxes_by_item": True})
        content_plan.check_spoiler_envelope({}, {})
        content_plan.check_spoiler_envelope({}, {"spoiler_items": False})
        for plan, co in ((boxed, {"spoiler_items": False, "color_boxes_by_item": True}),
                         (boxed, {"spoiler_items": True, "color_boxes_by_item": False}),
                         ({"item_boxes": {}, "item_packs": {"warp_pad_preview": True}},
                          {"spoiler_items": True, "color_boxes_by_item": True}),
                         ({}, {"spoiler_items": True}),
                         ({}, {"spoiler_items": 1})):
            with self.subTest(plan=plan, co=co), self.assertRaises(OptionError):
                content_plan.check_spoiler_envelope(plan, co)


class TestTrackerRestore(unittest.TestCase):
    def test_on_off_and_absent(self):
        for profile in ({"box_locations": True}, profile_options()):
            for enabled in (False, True):
                with self.subTest(content_plan="content_pool" in profile, enabled=enabled):
                    world = make_world(dict(profile, spoiler_items=enabled), seed=459)
                    wire = json.loads(json.dumps(world.fill_slot_data()))
                    restored = make_world(dict(profile, spoiler_items=not enabled), seed=999,
                                          passthrough=copy.deepcopy(wire))
                    self.assertEqual(bool(restored.options.spoiler_items.value), enabled)
                    self.assertEqual(reveal_items(restored), reveal_items(world))
                    self.assertEqual(restored.fill_slot_data()["ctr_options"]["spoiler_items"], enabled)
                    self.assertEqual(len(restored.multiworld.itempool), len(world.multiworld.itempool))
                    self.assertEqual(sorted(l.address for l in restored.multiworld.get_locations(1) if l.address),
                                     sorted(l.address for l in world.multiworld.get_locations(1) if l.address))
                    if "content_pool" not in profile:
                        wire["ctr_options"].pop("spoiler_items")
                        old = make_world(dict(profile, spoiler_items=True), seed=999, passthrough=wire)
                        self.assertFalse(old.options.spoiler_items.value)
                        self.assertEqual(reveal_items(old), [])
