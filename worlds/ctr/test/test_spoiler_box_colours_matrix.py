"""AP Box Colours across every display option (A2-6, alpha1 room refusal).

An alpha1 room with `spoiler_items` and `box_locations` on and
`color_boxes_by_item` off was refused by the client: native wanted AP Box
Colours whenever the plan had item boxes, while the apworld (Rulebook, Pad and
box display, Spoiler Items rule 1 and rule 7) creates it only for coloured
boxes. This pins the apworld side over the whole matrix of
`color_boxes_by_item`, `spoiler_items`, `ap_item_type_colors` and
`box_locations`: the item exists exactly with Spoiler Items, AP boxes and box
colours, and the room passes the envelope check the tracker runs on restore.
The native parser is pinned on the same rule in
tools/test-spoiler-items-production.py and, through both validators, in
tools/test-content-plan-parity.py.
"""
import itertools
import unittest

from Options import OptionError

from .. import content_plan
from .test_content_plan_row5 import fill, options
from .test_content_plan import make_world

MATRIX = list(itertools.product((False, True), (False, True), (False, True), (False, True)))


class TestSpoilerBoxColoursMatrix(unittest.TestCase):
    def test_ap_box_colours_follows_coloured_boxes(self):
        for colours, spoiler, type_colours, boxes in MATRIX:
            with self.subTest(color_boxes_by_item=colours, spoiler_items=spoiler,
                              ap_item_type_colors=type_colours, box_locations=boxes):
                world = make_world(options(color_boxes_by_item=colours, spoiler_items=spoiler,
                                           ap_item_type_colors=type_colours, box_locations=boxes), seed=1)
                wire = fill(world)
                plan, co = wire["content_plan"], wire["ctr_options"]
                packs = plan.get("item_packs", {})
                wanted = spoiler and boxes and colours
                self.assertEqual("ap_box_colours" in packs, wanted)
                self.assertEqual("warp_pad_preview" in packs, spoiler)
                self.assertEqual("item_boxes" in plan, boxes)
                names = [item.name for item in world.multiworld.itempool]
                self.assertEqual(names.count("AP Box Colours"), int(wanted))
                if boxes:
                    self.assertIs(co["color_boxes_by_item"], colours)
                content_plan.check_spoiler_envelope(plan, co)

    def test_the_alpha1_report_shape(self):
        # The reported YAML: Spoiler Items and boxes on, both colour options off.
        wire = fill(make_world(options(color_boxes_by_item=False, spoiler_items=True,
                                       ap_item_type_colors=False, box_locations=True), seed=1))
        self.assertEqual(wire["ctr_options"]["spoiler_items"], True)
        self.assertIs(wire["ctr_options"]["color_boxes_by_item"], False)
        self.assertIn("warp_pad_preview", wire["content_plan"]["item_packs"])
        self.assertNotIn("ap_box_colours", wire["content_plan"]["item_packs"])
        bad = dict(wire["content_plan"], item_packs={**wire["content_plan"]["item_packs"], "ap_box_colours": True})
        with self.assertRaises(OptionError):
            content_plan.check_spoiler_envelope(bad, wire["ctr_options"])


if __name__ == "__main__":
    unittest.main()
