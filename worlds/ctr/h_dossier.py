"""The H-dossier item families, activated (traps, useful grants, wumpa).

WHAT "ACTIVATED" MEANS HERE. The 0.2.0 name freeze (#177) already minted every
name in this module into `data/items.json` at count 0: eleven traps at indexes
106-116, three useful grants at 117-119, and three wumpa entries at 120-122. A
frozen name is a reserved id and nothing else -- no option creates it, no pool
draws it, no native effect answers it. This module is the half that makes them
real: it owns how many copies of each name a seed's options create, and it is
the single place the counts are decided so the pool loop, the supply
accounting, the slot_data mirror and the tests all read one answer.

THE RULING THIS IMPLEMENTS. Stef, 2026-08-10 16:28/16:30, walked family by
family against the R-H dossier:

  * ELEVEN traps, all in. Seven of Kitkat's original list (wumpa reset, flatten,
    inventory reroll, inventory auto-use, empty crates, weakened kart, boost
    suppression -- the dossier's items 6 and 7 merged into one name), plus the
    wireframe render trap Stef added at 16:28, plus Nitro / Reverse Controls /
    Red Potion ruled in at 16:30 ("honestly fun"). Respawn/mask-grab was
    REJECTED outright, not parked, and is not here.
  * THREE useful grants: Passive Shield, Invincibility Mask, and Invisibility --
    the last "ALL MODES", not battle-only, overruling the dossier's recommended
    scoping. The player-agency power-up grant was DEFERRED past 0.2.0 because
    itemsanity owns the weapons-as-items space, so it is not here either.
  * THREE wumpa names: Small and Big Wumpa Bundle as filler, plus ONE
    "Progressive Starting Wumpa" name received up to ten times, per the #12/#13
    progressive convention. The dossier's separate "+5 / +10 wumpa useful items"
    were folded into that ladder rather than minted as their own names.
  * ONE location, global: the 10-wumpa check, which `wumpa_checks.py` owns.

THE ONE AMENDMENT BEYOND THE FREEZE. `Turbo Grant` (#224), the missing sibling
of the already-frozen `Invincibility Mask`, appended at 35010189 immediately
after Tizi's 35010188. The 2026-08-11 ruling is explicit that the ruled Mask
filler IS `Invincibility Mask` and that no duplicate Mask-grant name may be
minted, so the amendment is exactly one name wide and nothing in the manifest
moves. See `TURBO_GRANT_ITEM` below.

WHY THE TRAPS ARE NOT LISTED HERE. Their names live in `__init__.py`'s
`FROZEN_TRAP_ITEM_NAMES`, whose ORDER is pinned to native's `AP_TrapEffect`
enum, and this build moves that whole list into the buildable `TRAP_ITEM_NAMES`
now that every effect exists natively. Restating the eleven names here would
give the order two homes and one of them would eventually drift (Lessons
Learned #5). This module imports nothing from that list and decides no trap
counts: traps are drawn by `trap_fill_percentage` out of the filler budget, not
created per-option, so their "how many" is a fill decision, not an item-family
one.

THE SUPPLY SHAPE, stated once. Every name this module creates adds an item and
NO location, so each is a straight subtraction from the seed's spare capacity,
exactly like the Tizi Helper and the character unlocks. The two wumpa bundles
are the sole exception: they are FILLER SUBSTITUTES, drawn out of the filler
budget the pool already sizes, so they cost nothing. That is why they are a
separate function from `created_item_counts` -- mixing them in would double-
count them against the supply check.
"""
from typing import Dict, List

from Options import OptionError

#: The three ruled useful grants, frozen order (data/items.json indexes 117-119).
#: Order is not load-bearing on the wire -- native dispatches these by item id,
#: not by position in a block -- but it is the order the freeze minted and the
#: order the tests assert, so it stays the order here.
USEFUL_GRANT_ITEMS: List[str] = [
    "Passive Shield",
    "Invincibility Mask",
    "Invisibility",
]

#: The #224 amendment. Appended at 35010189, one past Tizi's 35010188, and the
#: only name in this build that is not already in the #177 freeze. It is grouped
#: with the useful grants everywhere below because it behaves exactly like
#: `Invincibility Mask` -- same queue, same itemsanity gate shape, same option.
TURBO_GRANT_ITEM = "Turbo Grant"

#: The amendment's frozen code. Pinned here as well as in data/items.json on the
#: same reasoning `tizi_helper.TIZI_HELPER_CODE` gives: a test can assert the two
#: agree without re-reading the JSON through the loader. It is Tizi's code plus
#: one, and the freeze's last entry (Gas Pedal, 35010187) plus two.
TURBO_GRANT_CODE = 35010189

#: The full set the `useful_item_grants` toggle creates: the three ruled grants
#: plus the ruled amendment. One copy of each, per the ruling's "one name"
#: reading of every entry in the useful family.
GRANT_ITEMS: List[str] = USEFUL_GRANT_ITEMS + [TURBO_GRANT_ITEM]

#: The two bundle FILLER names. Not created per-option: they substitute into the
#: filler budget alongside `Wumpa Fruit`. See `filler_weights`.
WUMPA_BUNDLE_ITEMS: List[str] = [
    "Small Wumpa Bundle",
    "Big Wumpa Bundle",
]

#: The ruled progressive: ONE name, up to ten received copies (Stef, 16:30).
PROGRESSIVE_WUMPA_ITEM = "Progressive Starting Wumpa"

#: The hard ceiling on that ladder. Ten is not an arbitrary option bound: a kart
#: can hold exactly ten fruit (`RB_Player_ModifyWumpa` clamps there, and
#: `ap_wumpa.c` clamps its own bank to the same number for the same reason), so
#: an eleventh copy could never be felt. The option's `range_end` reads this.
PROGRESSIVE_WUMPA_MAX = 10

#: How many fruit each bundle hands over. Small is a meaningful but partial
#: top-up, Big fills the kart from empty. Both are clamped natively by the
#: engine's own cap, so "Big" is never more than one full kart.
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
    """Name -> how many copies this seed's options create, for the families that
    SPEND SUPPLY (the four grants and the progressive wumpa ladder).

    Excludes the two bundle fillers on purpose: they cost no supply because they
    substitute into the filler budget. Excludes traps for the same reason.
    Returns only positive entries, so an all-off seed returns an empty dict and
    every caller's loop is a no-op rather than a run of zeros.
    """
    counts: Dict[str, int] = {}

    if world.options.useful_item_grants.value:
        for name in GRANT_ITEMS:
            counts[name] = 1

    ladder = int(world.options.progressive_starting_wumpa.value)
    if ladder > 0:
        counts[PROGRESSIVE_WUMPA_ITEM] = min(ladder, PROGRESSIVE_WUMPA_MAX)

    return counts


def created_item_total(world) -> int:
    """Total supply this module's families spend on this seed. One number so the
    capacity check does not have to re-sum the dict at its own call site."""
    return sum(created_item_counts(world).values())


def raise_if_families_exceed_location_supply(
        world, *, available_supply: int) -> None:
    """Reject a seed when its grants and starting-Wumpa ladder do not fit.

    These families add up to fourteen items and no locations. ``create_items``
    calls this after its optional comfort-pack trim, passing the live capacity
    left when the H-dossier items themselves are excluded. This mirrors the
    capability and character guards and prevents AP's panic fallback from
    silently moving the overflow into starting inventory.
    """
    counts = created_item_counts(world)
    needed = sum(counts.values())
    if needed <= 0 or available_supply >= needed:
        return
    detail = ", ".join(f"{count}x {name}"
                       for name, count in counts.items())
    raise OptionError(
        f"CTR: Useful Item Grants / Progressive Starting Wumpa would add "
        f"{needed} item(s) to the pool ({detail}), but this seed has only "
        f"{max(0, available_supply)} unfilled location(s) left for them. "
        f"Enable more location checks, turn off Useful Item Grants, or lower "
        f"Progressive Starting Wumpa.")


def filler_weights(world) -> Dict[str, int]:
    """The weighted filler name pool for this seed.

    With `wumpa_bundles` off this is `{"Wumpa Fruit": 1}` -- a single name with a
    single weight, which every caller resolves to the same fixed `Wumpa Fruit`
    the pre-this-build code returned, taking no RNG draw. That is what keeps a
    bundles-off seed byte-identical to a pre-#177 seed, the same
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
    """The wire scalars for these families.

    ALL THREE ARE ALWAYS EMITTED, on the same convention as `itemsanity` and
    `tizi_helper`: a tracker (and a Universal Tracker restore) should be able to
    read the seed's real configuration without inferring it from an item that
    may not have arrived yet, and an absent key correctly restores to off on
    every pre-this-build seed.

    NATIVE READS NONE OF THEM. Every runtime decision on the native side is
    driven by RECEIVED ITEMS -- a trap primes when its item arrives, a grant
    queues when its item arrives, the starting-wumpa ladder is the count of
    copies received -- and the one thing native needs that items cannot tell it,
    "is itemsanity on for this seed", it reads off server location membership
    (the 35016000 block), exactly as the Tizi gate does. So these keys are
    diagnostic and tracker metadata, and a pre-this-build client is unaffected
    by their presence.
    """
    o = world.options
    return {
        "useful_item_grants": bool(o.useful_item_grants.value),
        "wumpa_bundles": bool(o.wumpa_bundles.value),
        "progressive_starting_wumpa": int(o.progressive_starting_wumpa.value),
    }


def restore_slot_data(options, ctr_options) -> None:
    """Universal Tracker restore for the three scalars above.

    An absent key is a pre-this-build seed and restores to off / zero, which is
    the honest answer: such a seed created none of these items.
    """
    options.useful_item_grants.value = int(
        bool(ctr_options.get("useful_item_grants", 0)))
    options.wumpa_bundles.value = int(bool(ctr_options.get("wumpa_bundles", 0)))
    options.progressive_starting_wumpa.value = min(
        PROGRESSIVE_WUMPA_MAX,
        max(0, int(ctr_options.get("progressive_starting_wumpa", 0) or 0)))
