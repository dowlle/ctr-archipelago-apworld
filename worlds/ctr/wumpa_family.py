"""The wumpa item family, activated: two bundle fillers and the starting ladder.

WHAT "ACTIVATED" MEANS. The 0.2.0 name freeze (#177) minted `Small Wumpa
Bundle`, `Big Wumpa Bundle` and `Progressive Starting Wumpa` into
`data/items.json` at indexes 120-122, count 0, and `wumpa_checks.py` minted the
global 10-wumpa location name the same way. A frozen name is a reserved id and
nothing else: no option created any of them, no pool drew them, and the native
half sat waiting. This module is the half that makes them real.

THE RULING THIS IMPLEMENTS. Stef, 2026-08-10 16:28/16:30, walking the R-H
dossier family by family: two bundles as FILLER, one `Progressive Starting
Wumpa` name received up to ten times per the #12/#13 progressive convention
(the dossier's separate "+5 / +10 wumpa useful items" folded into that ladder
rather than minted as their own names), and ONE global location, the 10-wumpa
check.

PROVENANCE. The design, the weights and the reasoning below are lifted from the
recovered `h_dossier.py` on `feat/020-h-dossier-families`, which implemented
this family alongside eleven traps and four useful grants. Only the wumpa half
is taken here, on purpose: that branch carries its own `Turbo Grant`
implementation, which would collide with the separately reviewed #224 pair. The
traps and the grants remain that branch's to land.

THE SUPPLY SHAPE, stated once, because it is the whole reason the two halves of
this family are handled differently:

  * The BUNDLES cost NOTHING. They are filler substitutes -- they change WHICH
    filler name lands in a slot the pool was already going to fill, so they
    never enter the pool as extra demand. They are also `filler`-classified, so
    the overflow shedder treats them exactly like `Wumpa Fruit`, with no rule
    of its own (see item_supply.shed_overflow).
  * The LADDER costs supply. Every `Progressive Starting Wumpa` copy is one
    more item with no location of its own, exactly like the character unlocks
    and the Tizi Helper, so it must be mirrored into the rung sizer's demand
    predictor or the sizer will fail to expand a seed that needed the room.
"""
from typing import Dict, List

#: The two bundle FILLER names. Never created per-option: they substitute into
#: the filler budget alongside `Wumpa Fruit`. See `filler_weights`.
WUMPA_BUNDLE_ITEMS: List[str] = [
    "Small Wumpa Bundle",
    "Big Wumpa Bundle",
]

#: The ruled progressive: ONE name, up to ten received copies (Stef, 16:30).
PROGRESSIVE_WUMPA_ITEM = "Progressive Starting Wumpa"

#: The hard ceiling on that ladder. Ten is not an arbitrary option bound: a kart
#: can hold exactly ten fruit (`RB_Player_ModifyWumpa` clamps there, and native's
#: `ap_wumpa.c` clamps its own bank to the same number for the same reason), so
#: an eleventh copy could never be felt. The option's `range_end` reads this.
PROGRESSIVE_WUMPA_MAX = 10

#: How many fruit each bundle hands over, mirroring native's receive handler
#: (`AP_WumpaReceive(3)` for small, a full kart for big). Recorded here so a
#: reader of the apworld does not have to open the client to know what the item
#: does; native owns the actual delivery and clamps to the engine's own cap.
BUNDLE_WUMPA_COUNT: Dict[str, int] = {
    "Small Wumpa Bundle": 3,
    "Big Wumpa Bundle": 10,
}

#: Relative draw weight of each filler name once the bundles are enabled.
#: Deliberately weighted toward plain `Wumpa Fruit` so enabling bundles enriches
#: the filler pool rather than replacing it -- a seed whose every filler slot
#: became a ten-fruit bundle would make the 10-wumpa check and itemsanity's
#: juiced checks trivial, which is a balance change the ruling did not make.
FILLER_WEIGHTS: Dict[str, int] = {
    "Wumpa Fruit": 6,
    "Small Wumpa Bundle": 3,
    "Big Wumpa Bundle": 1,
}


def created_item_counts(world) -> Dict[str, int]:
    """Name -> copies this seed creates, for the half that SPENDS SUPPLY.

    That is the ladder and only the ladder. The bundles are excluded on purpose:
    counting them here would double-count them against the supply check, since
    they are drawn from the filler budget rather than added to the pool.

    Returns only positive entries, so an all-off seed returns an empty dict and
    every caller's loop is a no-op rather than a run of zeros.
    """
    counts: Dict[str, int] = {}
    ladder = int(world.options.progressive_starting_wumpa.value)
    if ladder > 0:
        counts[PROGRESSIVE_WUMPA_ITEM] = min(ladder, PROGRESSIVE_WUMPA_MAX)
    return counts


def created_item_total(world) -> int:
    """Total supply this family spends on this seed. One number so the capacity
    check does not have to re-sum the dict at its own call site."""
    return sum(created_item_counts(world).values())


def filler_weights(world) -> Dict[str, int]:
    """The weighted filler name pool for this seed.

    With `wumpa_bundles` off this is `{"Wumpa Fruit": 1}` -- a single name with a
    single weight, which every caller resolves to the same fixed `Wumpa Fruit`
    the pre-this-build code returned, taking no RNG draw. That is what keeps a
    bundles-off seed byte-identical to a pre-activation seed, the same
    generation-neutrality property `trap_fill_percentage = 0` has.
    """
    if not world.options.wumpa_bundles.value:
        return {"Wumpa Fruit": 1}
    return dict(FILLER_WEIGHTS)


def draw_filler_name(world) -> str:
    """One filler name for one filler slot, drawn against `filler_weights`.

    NO RNG IS CONSUMED when bundles are off: the single-name case returns
    directly rather than asking `random.choices` for a one-element draw, so the
    default seed's RNG stream is untouched. This matters beyond tidiness -- the
    vanilla fill backstop replays a simulated fill move for move and asserts the
    simulation and the real fill draw identically, so a stray draw here would
    break replay fidelity on every default seed.
    """
    weights = filler_weights(world)
    if len(weights) == 1:
        return next(iter(weights))
    names = list(weights)
    return world.random.choices(names, weights=[weights[n] for n in names])[0]


def fill_slot_data(world) -> Dict[str, object]:
    """The wire scalars for this family.

    BOTH ARE ALWAYS EMITTED, on the same convention as `itemsanity` and
    `tizi_helper`: a tracker (and a Universal Tracker restore) should be able to
    read the seed's real configuration without inferring it from an item that
    may not have arrived yet, and an absent key correctly restores to off on
    every pre-activation seed.

    NATIVE READS NEITHER. Every runtime decision on the native side is driven by
    RECEIVED ITEMS -- a bundle hands over fruit when its item arrives, and the
    starting ladder is simply the count of copies received, rebuilt from
    ReceivedItems on every fresh connection. So these keys are diagnostic and
    tracker metadata, and a pre-0.2.0 client is unaffected by their presence.
    """
    o = world.options
    return {
        "wumpa_bundles": bool(o.wumpa_bundles.value),
        "progressive_starting_wumpa": int(o.progressive_starting_wumpa.value),
    }


def restore_slot_data(options, ctr_options) -> None:
    """Universal Tracker restore for the two scalars above.

    An absent key is a pre-activation seed and restores to off / zero, which is
    the honest answer: such a seed created none of these items.
    """
    options.wumpa_bundles.value = int(bool(ctr_options.get("wumpa_bundles", 0)))
    options.progressive_starting_wumpa.value = min(
        PROGRESSIVE_WUMPA_MAX,
        max(0, int(ctr_options.get("progressive_starting_wumpa", 0) or 0)))
