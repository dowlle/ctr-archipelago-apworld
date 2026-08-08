import json
import pkgutil
from BaseClasses import Location
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld


from .location_class import LocationClassRegistry
from .podium import PODIUM_CLASS

# The registered optional location classes (#176), in registration order.
#
# REGISTRATION IS APPEND-ONLY. Registration order is the order every class's
# locations enter CTR_LOCATION_IDS, so a new class (relic perfects #49, item
# boxes #109, itemsanity #145, lettersanity #148) goes at the END of this list.
# Codes are explicit per class so a reorder would not renumber anything, but
# keeping the order stable keeps location_name_to_id byte-stable, which is what
# makes a datapackage manifest diff (#177) readable.
CTR_LOCATION_CLASSES = LocationClassRegistry()
CTR_LOCATION_CLASSES.register(PODIUM_CLASS)

_LOCATION_DATA = json.loads(
    pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
)


CTR_LOCATION_IDS = {loc["name"]: loc["code"] for loc in _LOCATION_DATA}
CTR_LOCATION_TO_REGION = {loc["name"]: loc["region"] for loc in _LOCATION_DATA}

# Optional location classes are part of the game's global datapackage
# (name<->id must be stable for servers/trackers), so every class's FULL frozen
# superset is registered here unconditionally -- for podium that is all 112 rungs
# (16 tracks x 7 entries: 3 shipped names at the 35015000 block plus 4 new rungs
# at the 35015100 block). Whether a given SEED creates them is decided per-option
# in Regions.create_regions; get_total_locations counts only the locations a seed
# actually creates, so the datapackage size never inflates a seed's reported
# location count.
#
# The disjointness check runs BEFORE the merge: a class block colliding with the
# static table would otherwise silently overwrite a shipped id.
CTR_LOCATION_CLASSES.assert_disjoint_from(CTR_LOCATION_IDS, "data/locations.json")
for _cls_name, _cls_code, _cls_region in CTR_LOCATION_CLASSES.all_locations():
    CTR_LOCATION_IDS[_cls_name] = _cls_code
    CTR_LOCATION_TO_REGION[_cls_name] = _cls_region


def get_location_id(name: str):
    """Return the numeric ID for a given location name."""
    return CTR_LOCATION_IDS.get(name)


def get_region_for_location(name: str):
    """Return the region name associated with a given location."""
    return CTR_LOCATION_TO_REGION.get(name)


def get_location_names() -> dict:
    """
    Return a dictionary of all locations and their numeric IDs.
    """
    return CTR_LOCATION_IDS.copy()


def get_total_locations(world) -> int:
    """
    Return the number of locations THIS seed actually created (incl. events, to
    preserve the historical value for non-podium seeds). Counting created
    locations -- rather than len(CTR_LOCATION_IDS), the full static datapackage --
    keeps TotalLocations accurate now that the datapackage always carries the 112
    podium rungs while a seed may create 0-80 of them per option (up to 5 rungs
    across 16 tracks).
    """
    return len(world.multiworld.get_locations(world.player))


def create_location(player: int, name: str, region):
    """
    Factory to create Location objects linked to CTR location codes.
    """
    addr = get_location_id(name)
    return Location(player, name, addr, region)
