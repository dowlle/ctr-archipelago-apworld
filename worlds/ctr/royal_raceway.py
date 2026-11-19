"""Boost 0 pickup and Boost 2 finish rulings from the driven Royal Raceway 1.0.0 revision.

Only the exact measured LEV is reviewed (Deck driving, 2026-11-18). Ordinary
weapon and Wumpa crates are reachable at Boost 0 by reversing round the
course. Clearing the jump to finish a lap needs two Progressive Boost ranks,
so every reward that needs a finished race has a floor of two, carried in the
plan's `capability.finish_floors` (content_capability). Older room records keep
their rules: sanity rules version 5 and `item_boxes.pickup_rules` carry the
pickup side, and a record without `finish_floors` keeps its recorded ranks.
"""

LEV_SHA256 = "fca9e96a57c850e68e0226382645b4d6df5b4e7ebeb61459269ec2427ffab96b"
RULES_VERSION = 5


def matches(package):
    from .box_spots import lev_pin
    return lev_pin(package) == LEV_SHA256
