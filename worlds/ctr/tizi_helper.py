"""Tizi Helper: the single-track Papu's Pyramid mask helper (issue #223).

WHAT IT IS. One received AP item. Once the slot holds it, the first row of four
weapon boxes immediately after the Papu's Pyramid start line yields a Mask
instead of a rolled weapon. Outside those four boxes, on every other track and
before the item arrives, weapon boxes behave exactly as vanilla. The name comes
from the community Tiziano skip; Icebound's standalone randomizer ships the same
idea as a `helper_tiziano` trick toggle, and #223 deliberately makes ours an AP
ITEM rather than a YAML trick or a client-setting toggle.

THE RULED ACTIVATION GATE (Stef, 2026-08-10, restated verbatim in the #223 body):

  * itemsanity OFF -> receiving `Tizi Helper` alone activates the helper.
  * itemsanity ON  -> the helper activates only after the slot has received BOTH
    `Tizi Helper` and the separate progression `Mask` weapon item (the
    itemsanity item at 35010101). Until both are in, the four boxes stay vanilla.

The gate is enforced NATIVELY, not here: native already knows which items the
slot received, and it reads "is itemsanity on for this seed" off server location
membership (the 35016000 block), so this side emits no wire key for it. See the
slot_data Contract's #223 note.

WHY IT MINTS NO LOCATION. The helper changes what a weapon box gives you; it
adds no check of its own. The 270 authored item-box checks (#109) are a separate
family on their own code block and are untouched by this item.

WHY `useful` AND NOT `progression`. No rule reads it. The only weapon-gated
logic in this world is the Tiger Temple door box's opener set
(item_boxes.TIGER_TEMPLE_DOOR_OPENERS), which is a different track, so no seed
can ever require the helper to reach a location. Classification therefore stays
`useful`; if a future speedrunner/trick-logic category puts the Tiziano skip IN
logic, that category re-rules this alongside its own options.

THE ID. `Tizi Helper` is code 35010188, appended one past the frozen 0.2.0 name
set's last entry (Gas Pedal, 35010187). #177 froze that set at 188 names and
0.2.0 spends exactly one datapackage bump; this is the ruled reopening of that
namespace for an append-only amendment, so it renumbers and renames nothing.
The second ruled amendment (`Turbo Grant`) takes the next free code after this
one when it is built.
"""

#: The item name. Player-visible, so it is the display string too.
TIZI_HELPER_ITEM = "Tizi Helper"

#: The frozen code. Pinned here as well as in data/items.json so a test can
#: assert the two agree without re-reading the JSON through the loader.
TIZI_HELPER_CODE = 35010188

#: The itemsanity weapon whose receipt the ruled gate additionally requires when
#: itemsanity is on. Named rather than coded so a rename is caught by the
#: itemsanity family tests instead of drifting silently.
TIZI_ITEMSANITY_COMPANION = "Mask"


def created_item_count(world) -> int:
    """How many `Tizi Helper` items this seed's options create: 1 or 0.

    A single copy, and only when the option is on. Kept as a function so the
    pool loop, the tests and any future supply accounting all read one answer.
    """
    return 1 if world.options.tizi_helper.value else 0
