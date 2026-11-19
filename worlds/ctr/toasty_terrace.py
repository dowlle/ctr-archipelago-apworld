"""Boost 0 pickup ruling from the driven Toasty Terrace 1.3.0 revision.

Only the exact measured LEV is reviewed. Older room records keep their rules.
"""

LEV_SHA256 = "2b18c6305d3cfe591e979eabe42e7815fe475479d49f59d5b7b50b06f701ac5d"
RULES_VERSION = 4


def matches(package):
    from .box_spots import lev_pin
    return lev_pin(package) == LEV_SHA256
