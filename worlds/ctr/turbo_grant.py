"""Turbo Grant: the in-race Turbo hand-out (issue #224).

WHAT IT IS. One received AP item. Receiving it rolls a normal Turbo straight
into the player's weapon slot and plays the usual item-pickup ping, as if a
weapon box had just paid out a Turbo. It is fired on demand through the ordinary
held-item path -- circle press, same as any Turbo -- so it adds no inventory
interface and no second firing path.

THE RULED GATE (ruled 2026-08-11, "Mask and Turbo filler interactions",
restated in the #224 body):

  * itemsanity OFF -> a received grant is deliverable with no weapon-item gate.
  * itemsanity ON  -> a grant is deliverable only once the slot has also
    received the separate progression `Turbo` weapon item (the itemsanity item
    at 35010095). Until then the grant queues; it is never discarded.

WHY THE SIBLING MASK GRANT IS NOT HERE. The ruling names the already-frozen
`Invincibility Mask` (35010118) as the Mask half of the same family and forbids
minting a duplicate Mask-grant name. #224 appends the missing Turbo sibling and
nothing else.

DELIVERY, QUEUEING AND FIRING ARE ALL NATIVE'S. This side owns the name, the
code, the option and one diagnostic wire scalar. Native owns every runtime rule:
the race window, the empty-weapon-slot precondition, the itemsanity ownership
check, the per-slot queue that survives reconnects and race restarts, and the
progressive-boost behaviour at fire time. Native reads "is itemsanity on for
this seed" off server location membership (the 35016000 block), exactly as #223
does, so this side emits no wire key for the gate.

WHY IT MINTS NO LOCATION. The grant hands you a weapon; it adds no check of its
own. The 270 authored item-box checks (#109) and the 22 itemsanity use-checks
(#145) are separate families on their own code blocks and are untouched by it.

WHY `useful` AND NOT `progression`. No rule reads it, and no seed can require
it: the only weapon-gated logic in this world is the Tiger Temple door box's
opener set (item_boxes.TIGER_TEMPLE_DOOR_OPENERS), which a one-shot Turbo does
not open. `useful` also matches the three already-frozen sibling grants --
`Passive Shield` (35010117), `Invincibility Mask` (35010118) and `Invisibility`
(35010119) -- which is the shape the H-dossier ruling gives this family. The
#224 title calls it a filler item in the sense #223 uses for `Tizi Helper`: one
useful item spending one otherwise-filler slot, not ItemClassification.filler
and not a draw from `create_filler()`.

THE ID. `Turbo Grant` is code 35010189, appended one past `Tizi Helper`
(35010188), which was itself the first ruled reopening of the #177 name freeze.
This is the SECOND and, as ruled, last such amendment: it renumbers nothing,
renames nothing, moves no location code and rides 0.2.0's single datapackage
bump rather than buying a second one. The slot_data Contract's #223 datapackage
note reserved exactly this code for exactly this name.

THE OPTION SHAPE. A dedicated toggle creating exactly one copy, mirroring
`tizi_helper`. The H-dossier plan eventually folds all four grants under one
`useful_item_grants` umbrella toggle that creates one of each; that umbrella
does not exist on this branch and activating the other three needs their native
effects, which do not exist either. When it lands it can subsume this toggle
without touching a single item code or name.
"""

#: The item name. Player-visible, so it is the display string too.
TURBO_GRANT_ITEM = "Turbo Grant"

#: The frozen code. Pinned here as well as in data/items.json so a test can
#: assert the two agree without re-reading the JSON through the loader.
TURBO_GRANT_CODE = 35010189

#: The itemsanity weapon whose receipt the ruled gate additionally requires when
#: itemsanity is on. Named rather than coded so a rename is caught by the
#: itemsanity family tests instead of drifting silently.
TURBO_ITEMSANITY_COMPANION = "Turbo"

#: The Mask half of the same ruled family. Named here only so a reader (or a
#: test) can see that #224 deliberately reuses the frozen name instead of
#: minting a second Mask grant.
RULED_MASK_SIBLING = "Invincibility Mask"


def created_item_count(world) -> int:
    """How many `Turbo Grant` items this seed's options create: 1 or 0.

    A single copy, and only when the option is on. Kept as a function so the
    pool loop, the tests and any future supply accounting all read one answer.
    """
    return 1 if world.options.turbo_grant.value else 0
