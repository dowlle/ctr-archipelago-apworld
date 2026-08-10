"""The wumpa family's own check -- reaching 10 wumpa in a race (R-H dossier 3.4).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Crossing 10 wumpa in a
race. `RB_Player_ModifyWumpa` already has an exact, named transition for it --
`if (numWumpaOriginal < 10 && driver->numWumpas == 10)` -- which today plays the
"juiced up" jingle and starts `BattleHUD.juicedUpCooldown`. A check-emit call
slots into that existing branch with no new engine state and no new hook. It is
the cleanest signal in the whole R-H dossier.

WHO OWNS THE SEMANTICS. The apworld owns the name, the option and the rule;
native owns the emit call. Neither half is built here.

GLOBAL, ONE LOCATION PER SEED (Stef, 2026-08-10 16:28 ruling). Not per-track. The
dossier recommended global by analogy to the ruled itemsanity precedent and
flagged the analogy as inference; the ruling settled it directly, "by the same
anti-per-track reasoning as the juiced-checks ruling". So this class is one name,
not sixteen or eighteen.

RELATIONSHIP TO ITEMSANITY. Both this check and itemsanity's juiced checks read
the same `numWumpas >= 10` signal, but they are different events -- this one
fires on REACHING 10, itemsanity's fire on FIRING a weapon while at 10 -- so they
coexist without double-counting. Informational #178 row, not a conflict.

DATAPACKAGE STABILITY. This class claims the additive block 35016100 (one code)
and registers its single name UNCONDITIONALLY. It sits in the 35016xxx family
alongside itemsanity's 35016000-021, deliberately spaced a full hundred clear so
neither can grow into the other.

FROZEN-NAME WARNING. This name rides the single 0.2.0 datapackage bump (#177).
After that bump it is permanent, and its id can never move.

NAMES LAND INERT. `created_location_names` returns nothing, unconditionally,
because no option creates this location yet -- the 0.2.0 freeze mints names, not
features. The three wumpa ITEMS the same ruling adopted (Small Wumpa Bundle, Big
Wumpa Bundle, Progressive Starting Wumpa) are ordinary data/items.json entries at
indexes 120-122 and are not this class's to register.
"""
from .location_class import LocationClass

# Additive single-code block for the 10-wumpa check.
WUMPA_CODE_BASE = 35016100

#: The one location name. Spelled out rather than clever: a player reading it in
#: a tracker with itemsanity switched off has no "(Juiced)" vocabulary to lean
#: on, so the name says what to do.
WUMPA_TEN_LOCATION = "Wumpa: Reach 10 Wumpa"


class WumpaLocationClass(LocationClass):
    """The single 10-wumpa check as a `LocationClass` (#176)."""

    key = "wumpa"
    display_name = "Wumpa Checks"
    code_blocks = (WUMPA_CODE_BASE,)

    #: Global, like itemsanity: wumpa are collected wherever you race, so the
    #: check hangs off the world's root region rather than any track's.
    REGION = "Menu"

    def all_locations(self):
        return [(WUMPA_TEN_LOCATION, WUMPA_CODE_BASE, self.REGION)]

    def location_name(self) -> str:
        return WUMPA_TEN_LOCATION

    def created_location_names(self, options):
        """Nothing, until the wumpa-check toggle exists. See the module docstring."""
        return []


#: The registered wumpa class. `Locations.py` registers this instance.
WUMPA_CLASS = WumpaLocationClass()
