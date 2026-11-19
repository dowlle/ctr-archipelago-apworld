"""Reviewed physical pickup ranks for the exact Country Speedway 1.3.0 LEV.

Weapon ordinals name native instance-table seats, never AP box numbers.
"""

LEV_SHA256 = "9fa73436daaf91434ede1d6fb036a8e6dff225c55533cc0be5723d229b5e53bd"
BOX_RULES_KEY = "pickup_rules"


def matches(package):
    from .box_spots import lev_pin
    return lev_pin(package) == LEV_SHA256


def rank(kind, ordinal):
    return 2 if (kind, ordinal) in (("weapon_crate", 1), ("wumpa_crate", 2)) else 0
