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
from . import track_rulings

KEY = "crate_exclusions"
FEATURE = "crate_exclusions_v1"
EXCLUSIONS = json.loads(pkgutil.get_data(__package__, "data/crate_exclusions.json"))


WEAPON = "weapon_crate"


def ordinals(lev_sha256, kind=WEAPON, package=None):
    """Excluded one-based ordinals of one model family."""
    if package:
        lev_sha256 = track_rulings.source(package, EXCLUSIONS)
    return {c["ordinal"] for c in EXCLUSIONS.get(lev_sha256, ()) if c.get("family", WEAPON) == kind}


def entries(package):
    """Weapon-crate entries only: the wire and the fallback seating never see other families."""
    pin = track_rulings.source(package, EXCLUSIONS)
    crates = [c for c in EXCLUSIONS.get(pin, ()) if c.get("family", WEAPON) == WEAPON]
    if pin == lev_pin(package):
        return copy.deepcopy(crates)
    count = (package or {}).get("capabilities", {}).get("weapon_crates", 0)
    return [{"ordinal": c["ordinal"], "pos": None} for c in crates if c["ordinal"] <= count]


def count(package, excluded=()):
    """Raw package count minus this seed's carried entries, never a live lookup.

    A seed without the feature keeps its old seating, including in Tracker.
    Only new generation looks up the current catalog through records().
    """
    raw = (package or {}).get("capabilities", {}).get("weapon_crates")
    return None if raw is None else raw - len(excluded)


def records(tracks, packages, spots):
    """Only pad tracks using fallback seating, never hand-placed spots."""
    out = []
    for track in tracks:
        if track.get("origin") != "custom" or track["id"] in spots:
            continue
        package = packages.get(track.get("package_id"))
        if not (package or {}).get("capabilities", {}).get("weapon_crates"):
            continue
        crates = entries(package)
        if crates:
            out.append(dict(track_id=track["id"], lev_sha256=lev_pin(package), crates=crates))
    return out
