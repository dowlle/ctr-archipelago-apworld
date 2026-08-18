"""The wumpa family's own check -- reaching 10 wumpa in a race (R-H dossier 3.4).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Crossing 10 wumpa in a
race. `RB_Player_ModifyWumpa` already has an exact, named transition for it --
`if (numWumpaOriginal < 10 && driver->numWumpas == 10)` -- which today plays the
"juiced up" jingle and starts `BattleHUD.juicedUpCooldown`. A check-emit call
slots into that existing branch with no new engine state and no new hook. It is
the cleanest signal in the whole R-H dossier.

WHO OWNS THE SEMANTICS. The apworld owns the name, the option and the rule;
native owns the emit call. Neither half is built here.

GLOBAL, ONE LOCATION PER SEED (ruled 2026-08-10 16:28). Not per-track. The
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

ACTIVATED BY `wumpa_check`. The name landed inert with the freeze --
`created_location_names` returned nothing unconditionally, because the freeze
mints names, not features. It now creates the single location when the
`wumpa_check` toggle is on and nothing when it is off, which is the same
all-or-none shape itemsanity has and for the same reason: one name has no
per-seed subset to elastically size. The three wumpa ITEMS the same ruling
adopted (Small Wumpa Bundle, Big Wumpa Bundle, Progressive Starting Wumpa) are
ordinary data/items.json entries at indexes 120-122, owned by
`wumpa_family.py`, and are not this class's to register.
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
        """The one check when `wumpa_check` is on, otherwise none.

        Read defensively through `getattr` on the same convention itemsanity
        uses: `LocationClass` instances are also driven by the location-class
        infrastructure tests with stand-in option objects carrying only the
        options under test, and an absent toggle must answer "off" rather than
        raise.
        """
        toggle = getattr(options, "wumpa_check", None)
        if toggle is None or not bool(toggle.value):
            return []
        return [WUMPA_TEN_LOCATION]


#: The registered wumpa class. `Locations.py` registers this instance.
WUMPA_CLASS = WumpaLocationClass()
