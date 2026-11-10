"""Reviewed fallback crate exclusions, keyed only by exact LEV SHA-256.

Ordinals are one-based in instance-table order within a model family. An entry
without a "family" is a weapon crate; "wumpa_crate" names a Wumpa crate (A4-41).
Only weapon-crate entries ever reach the custom fallback seating or the seed's
crate_exclusions record. Wumpa-crate entries matter to Wumpasanity only. Positions
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


WEAPON = "weapon_crate"


def ordinals(lev_sha256, kind=WEAPON):
    """Excluded one-based ordinals of one model family for an exact LEV."""
    return {c["ordinal"] for c in EXCLUSIONS.get(lev_sha256, ()) if c.get("family", WEAPON) == kind}


def entries(package):
    """Weapon-crate entries only: the wire and the fallback seating never see other families."""
    return copy.deepcopy([c for c in EXCLUSIONS.get(lev_pin(package), []) if c.get("family", WEAPON) == WEAPON])


def count(package, excluded=()):
    """Raw package count minus this seed's carried entries, never a live lookup.

    A seed without the feature keeps its old seating, including in Tracker.
    Only new generation looks up the current catalog through records().
    """
    raw = (package or {}).get("capabilities", {}).get("weapon_crates")
    return None if raw is None else raw - len(excluded)


def records(tracks, packages, spots):
    """Only pad tracks using fallback seating, never hand-placed spots."""
    return [dict(track_id=t["id"], lev_sha256=lev_pin(packages.get(t.get("package_id"))),
                 crates=entries(packages[t["package_id"]]))
            for t in tracks if t.get("origin") == "custom" and t["id"] not in spots
            and (packages.get(t.get("package_id")) or {}).get("capabilities", {}).get("weapon_crates")
            and entries(packages.get(t.get("package_id")))]
