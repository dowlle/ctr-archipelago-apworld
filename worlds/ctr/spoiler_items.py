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
from typing import List

#: The two reveal items, minted in minted_items_030 (frozen names and codes).
WARP_PAD_PREVIEW_ITEM = "Warp Pad Preview"
WARP_PAD_PREVIEW_CODE = 35010204
AP_BOX_COLOURS_ITEM = "AP Box Colours"
AP_BOX_COLOURS_CODE = 35010205

ITEM_CODES = {WARP_PAD_PREVIEW_ITEM: WARP_PAD_PREVIEW_CODE,
              AP_BOX_COLOURS_ITEM: AP_BOX_COLOURS_CODE}


def enabled(world) -> bool:
    """The seed's value, read from the connected room on a Tracker restore.

    The content-plan restore bypasses the ordinary option restorer, so this
    resolves the option the same way `wumpa_family.reserve_top_up_enabled`
    does, for both the item creator and the wire emitter.
    """
    passthrough = getattr(getattr(world, "multiworld", None), "re_gen_passthrough", {}).get(
        getattr(world, "game", ""))
    if passthrough:
        world.options.spoiler_items.value = int(bool(
            passthrough.get("ctr_options", {}).get("spoiler_items", False)))
    return bool(world.options.spoiler_items.value)


def box_colours_item_wanted(options) -> bool:
    """Whether the seed has coloured AP boxes for AP Box Colours to reveal."""
    return bool(options.box_locations.value) and bool(options.color_boxes_by_item.value)


def created_item_names(world) -> List[str]:
    """The reveal items this seed creates: none, one or two, in code order."""
    if not enabled(world):
        return []
    names = [WARP_PAD_PREVIEW_ITEM]
    if box_colours_item_wanted(world.options):
        names.append(AP_BOX_COLOURS_ITEM)
    return names


def raise_if_items_do_not_fit(pool_size: int, unfilled: int, names) -> None:
    """Refuse a seed whose enabled reveal items are what overflows its pool.

    Fires only when the pool without the reveal items fits and the pool with
    them does not, so the message blames the right family. Any other overflow
    is left to the character-unlock and general capacity checks after it.
    """
    from Options import OptionError
    count = len(names)
    if not count or pool_size <= unfilled or pool_size - count > unfilled:
        return
    missing = pool_size - unfilled
    raise OptionError(
        f"CTR: Spoiler Items needs {missing} more location(s) for "
        f"{' and '.join(names[-missing:])}, which add no location of their own "
        f"({pool_size} items, {unfilled} locations). Enable more checks (item "
        "boxes, itemsanity, podium rungs or lettersanity locations) or turn "
        "off Spoiler Items.")


def fill_slot_data(world) -> dict:
    """The always-emitted wire scalar."""
    return {"spoiler_items": enabled(world)}


def restore_slot_data(options, ctr_options) -> None:
    """Universal Tracker restore: an absent key is a pre-#459 seed, off.

    AP Box Colours depends on `color_boxes_by_item` too, which the ordinary
    restore deliberately leaves alone (display only, pinned by
    test_color_boxes_by_item). On a Spoiler Items room it decides the pool, so
    restore it there from the always-emitted key; otherwise the Tracker's
    default (on) would add an AP Box Colours the seed never created."""
    options.spoiler_items.value = int(bool(ctr_options.get("spoiler_items", 0)))
    if options.spoiler_items.value and "color_boxes_by_item" in ctr_options:
        options.color_boxes_by_item.value = int(bool(ctr_options["color_boxes_by_item"]))
