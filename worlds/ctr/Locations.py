import json
import pkgutil
from BaseClasses import Location
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld


from .podium import all_podium_locations

_LOCATION_DATA = json.loads(
    pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
)


CTR_LOCATION_IDS = {loc["name"]: loc["code"] for loc in _LOCATION_DATA}
CTR_LOCATION_TO_REGION = {loc["name"]: loc["region"] for loc in _LOCATION_DATA}

# Podium placement checks (feat/podium-checks) are part of the game's global
# datapackage (name<->id must be stable for servers/trackers), so ALL 48 rungs
# are registered here unconditionally. Whether a given SEED creates them is
# decided per-option in Regions.create_regions; get_total_locations counts only
# the locations a seed actually creates, so the datapackage size never inflates
# a seed's reported location count.
for _pod_name, _pod_code, _pod_region in all_podium_locations():
    CTR_LOCATION_IDS[_pod_name] = _pod_code
    CTR_LOCATION_TO_REGION[_pod_name] = _pod_region


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
    keeps TotalLocations accurate now that the datapackage always carries the 48
    podium rungs while a seed may create 0/32/48 of them per option.
    """
    return len(world.multiworld.get_locations(world.player))


def create_location(player: int, name: str, region):
    """
    Factory to create Location objects linked to CTR location codes.
    """
    addr = get_location_id(name)
    return Location(player, name, addr, region)
