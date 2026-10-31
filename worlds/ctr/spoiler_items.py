"""Spoiler Items: reward previews held back behind two items (issue #459).

WHAT IT IS. With `spoiler_items` on, native hides two presentations until the
slot receives the item that restores it:

  * `Warp Pad Preview` (35010204): the floating reward previews above warp
    pads. Created once whenever the option is on.
  * `AP Box Colours` (35010205): the scouted-item colours of AP item boxes.
    Created once only when the seed has coloured AP boxes, that is
    `box_locations` and `color_boxes_by_item` are both on. A seed with no
    coloured boxes has no box colour to find (design answer 3, option A,
    2026-10-13).

Both are `useful` and gate presentation only. No location, pad, race, box or
goal rule reads either item, so they change no reachability and Universal
Tracker's logic graph is the same with or without them.

SUPPLY. Like Tizi Helper and Turbo Grant they add no location, so each copy
spends one slot that would otherwise hold filler. The legacy item creator puts
them in the pool before overflow shedding, so a tight seed sheds filler or the
comfort pack for them first, and refuses with a message naming them when they
still do not fit (the design forbids silently omitting an enabled reveal item).
The content plan budgets them as `item_packs` ledger rows.

WIRE. `ctr_options.spoiler_items` is always emitted (schema 18, Contract running
section). Native reads it: absent means off, so an older seed shows previews as
before. The reveal state itself comes from ReceivedItems, rebuilt on every
connect.

OFF IS GENERATION-NEUTRAL. With the option off this module creates nothing and
takes no random draw; the only wire difference from a pre-#459 seed is the
always-emitted `false`.
"""
#: The two reveal items, minted in minted_items_030 (frozen names and codes).
WARP_PAD_PREVIEW_ITEM = "Warp Pad Preview"
WARP_PAD_PREVIEW_CODE = 35010204
AP_BOX_COLOURS_ITEM = "AP Box Colours"
AP_BOX_COLOURS_CODE = 35010205

ITEM_CODES = {WARP_PAD_PREVIEW_ITEM: WARP_PAD_PREVIEW_CODE,
              AP_BOX_COLOURS_ITEM: AP_BOX_COLOURS_CODE}


def box_colours_item_wanted(options) -> bool:
    """Whether the seed has coloured AP boxes for AP Box Colours to reveal."""
    return bool(options.box_locations.value) and bool(options.color_boxes_by_item.value)
