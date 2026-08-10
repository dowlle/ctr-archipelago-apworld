"""Itemsanity -- use-time weapon checks, plain and juiced (#145, subsuming #180).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Firing each of the 11
Adventure-reachable weapons. Every fire sends that weapon's plain check; a fire
made while holding 10 or more wumpa additionally sends its juiced check. The
signal is use-time, not pickup-time: the hook is `VehPickupItem_ShootNow`, and
the juiced condition is the `d->numWumpas >= 10` read the fire branches already
do. Triples are NOT folded -- Bomb x3 and Missile x3 are their own weapons and
their own checks.

WHO OWNS THE SEMANTICS. The apworld owns the names, the 11 weapon items, the
per-item access rules and the wire block; native owns the fire hook and the
receive-gating of the crate roll. Neither half is built here.

The 11 weapons are the Adventure-only enumeration: held IDs 0-4 and 6-11,
excluding ID 5 (Spring, rewritten to Turbo before it can ever be held) and IDs 12
and 13 (Invisibility, Super Engine -- battle-mode-only, never reachable in
Adventure). Never mint those three.

DATAPACKAGE STABILITY. This class claims the additive block 35016000, stride 2
per weapon in WEAPONS order (plain then juiced), and registers all 22 names
UNCONDITIONALLY. 35016xxx was recorded as free by #177's own issue body and
claimed for itemsanity by the #145 spec across three independent reads.

The 11 weapon ITEMS are ordinary `data/items.json` entries at indexes 95-105
(`35010095`-`35010105`), in WEAPONS order -- the first block of the 0.2.0 append,
per the ruled freeze order (Stef, 08-10 11:38: itemsanity block first, H-dossier
families after it). They are items, not locations, so they are not this class's
to register -- `ITEM_NAMES` below exists so the two orders provably cannot drift,
and the tests assert it against the live item table.

Unlike podium, #109 boxes or lettersanity, itemsanity has no per-seed elastic
subset: all 22 are created whenever the toggle is on, none are held back. That is
a property of the ruled shape, not of this freeze.

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

NAMES LAND INERT. `created_location_names` returns nothing, unconditionally, and
every weapon item carries `count: 0`, because no option creates either yet -- the
0.2.0 freeze mints names, not features.
"""
from .location_class import LocationClass

# Additive block for the 22 itemsanity checks, stride 2 per weapon.
ITEMSANITY_CODE_BASE = 35016000

#: The 11 Adventure-reachable weapons, in held-ID order. FROZEN: this order is
#: both the location stride order within the 35016000 block AND the append order
#: of the 11 weapon items in data/items.json, so the two cannot be reordered
#: independently.
WEAPONS = (
    "Turbo",           # held ID 0
    "Bomb",            # held ID 1
    "Missile",         # held ID 2
    "TNT",             # held ID 3
    "Beaker",          # held ID 4
    "Shield Bubble",   # held ID 6
    "Mask",            # held ID 7
    "N. Tropy Clock",  # held ID 8
    "Warpball",        # held ID 9
    "Bomb x3",         # held ID 10 (0xA)
    "Missile x3",      # held ID 11 (0xB)
)

#: The 11 weapon item names, frozen order. Mirrors data/items.json indexes
#: 95-105; asserted against the live item table by test_itemsanity.
ITEM_NAMES = WEAPONS


class ItemsanityLocationClass(LocationClass):
    """The 22 use-time weapon checks as a `LocationClass` (#176).

    Global, not per-track: the class has no stable partition key, so its wire
    block is the ordered-array variant of the Contract section 7 shared
    location-class shape rather than podium's per-partition map.
    """

    key = "itemsanity"
    display_name = "Itemsanity"
    code_blocks = (ITEMSANITY_CODE_BASE,)

    #: The AP region every itemsanity check parents to. Itemsanity is global --
    #: a weapon is fired wherever you are -- so it hangs off the world's root
    #: region rather than any track's.
    REGION = "Menu"

    def all_locations(self):
        out = []
        for wi, weapon in enumerate(WEAPONS):
            out.append((self.location_name(weapon, False),
                        ITEMSANITY_CODE_BASE + wi * 2, self.REGION))
            out.append((self.location_name(weapon, True),
                        ITEMSANITY_CODE_BASE + wi * 2 + 1, self.REGION))
        return out

    def location_name(self, weapon: str, juiced: bool = False) -> str:
        """AP location name for a weapon's check, e.g. 'Itemsanity: Turbo' or
        'Itemsanity: Turbo (Juiced)'."""
        return f"Itemsanity: {weapon}" + (" (Juiced)" if juiced else "")

    def created_location_names(self, options):
        """Nothing, until #145's toggle exists. See the module docstring."""
        return []


#: The registered itemsanity class. `Locations.py` registers this instance.
ITEMSANITY_CLASS = ItemsanityLocationClass()
