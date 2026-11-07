"""Reviewed fallback crate exclusions, keyed only by exact LEV SHA-256.

Ordinals are one-based weapon-crate ordinals in instance-table order. Positions
are signed LEV coordinates, checked again before native touches any crate.
The world ships the list and carries the applicable entries in the seed. The
geometry report tool never updates this list or changes generation.
"""
import copy
import json
import pkgutil

from .box_spots import lev_pin

KEY = "crate_exclusions"
FEATURE = "crate_exclusions_v1"
EXCLUSIONS = json.loads(pkgutil.get_data(__package__, "data/crate_exclusions.json"))


def entries(package):
    return copy.deepcopy(EXCLUSIONS.get(lev_pin(package), []))


def count(package):
    raw = (package or {}).get("capabilities", {}).get("weapon_crates")
    return None if raw is None else raw - len(entries(package))


def records(tracks, packages, spots):
    """Only pad tracks using fallback seating, never hand-placed spots."""
    return [dict(track_id=t["id"], lev_sha256=lev_pin(packages.get(t.get("package_id"))),
                 crates=entries(packages[t["package_id"]]))
            for t in tracks if t.get("origin") == "custom" and t["id"] not in spots
            and (packages.get(t.get("package_id")) or {}).get("capabilities", {}).get("weapon_crates")
            and entries(packages.get(t.get("package_id")))]
