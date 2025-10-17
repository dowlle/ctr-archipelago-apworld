import json
import os
from BaseClasses import Location
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld




data_path = os.path.join(os.path.dirname(__file__), "data", "locations.json")

with open(data_path, "r", encoding="utf-8") as f:
    _LOCATION_DATA = json.load(f)


CTR_LOCATION_IDS = {loc["name"]: loc["code"] for loc in _LOCATION_DATA}
CTR_LOCATION_TO_REGION = {loc["name"]: loc["region"] for loc in _LOCATION_DATA}



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
    Return total number of locations for this world instance.
    """
    return len(CTR_LOCATION_IDS)


def create_location(player: int, name: str, region):
    """
    Factory to create Location objects linked to CTR location codes.
    """
    addr = get_location_id(name)
    return Location(player, name, addr, region)
