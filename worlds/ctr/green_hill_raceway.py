"""Boost 0 ruling from the driven Green Hill Raceway 2.0.0 revision.

Stef, 2026-11-18: "fully completable without boost". A logged Boost 0 run in
Deck room AP_15759866362140677139 registered Complete One Lap, Finish on Podium,
Finish (Any Position) and pickups in all eight physical crate rows. Only the
exact measured LEV is reviewed. The pickup side uses sanity rules version 6 and
the `item_boxes.pickup_rules` marker. The lap and finish side uses the plan's
`capability.finish_free` list (content_capability), so a room from before the
ruling keeps its recorded ranks and an unrecognised revision keeps the generic
terms.
"""

LEV_SHA256 = "50250966e9b31d13b140aaafa9433ffce19269898a0850edd0a1e8cf1207c760"
RULES_VERSION = 6


def matches(package):
    from .box_spots import lev_pin
    return lev_pin(package) == LEV_SHA256
