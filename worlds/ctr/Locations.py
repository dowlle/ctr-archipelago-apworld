import json
import pkgutil
from BaseClasses import Location
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld


from .podium import all_podium_locations
from .relic_perfect import all_relic_perfect_locations

_LOCATION_DATA = json.loads(
    pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
)


CTR_LOCATION_IDS = {loc["name"]: loc["code"] for loc in _LOCATION_DATA}
CTR_LOCATION_TO_REGION = {loc["name"]: loc["region"] for loc in _LOCATION_DATA}

# Podium placement checks are part of the game's global datapackage (name<->id
# must be stable for servers/trackers), so the FULL rung superset is registered
# here unconditionally (podium.all_podium_locations -- 7 names per track across
# the frozen 35015000 and additive 35015100 blocks; the live v0.2.0 layout is the
# 5-rung one described in podium.py, not the v0.1.x 3-rung set). Whether a given
# SEED creates them is decided per-option in Regions.create_regions;
# get_total_locations counts only the locations a seed actually creates, so the
# datapackage size never inflates a seed's reported location count.
for _pod_name, _pod_code, _pod_region in all_podium_locations():
    CTR_LOCATION_IDS[_pod_name] = _pod_code
    CTR_LOCATION_TO_REGION[_pod_name] = _pod_region

# Relic-race perfect checks (#49): same datapackage rule as the rungs above --
# all 18 names registered unconditionally, creation decided per-option in
# Regions.create_regions.
for _rp_name, _rp_code, _rp_region in all_relic_perfect_locations():
    CTR_LOCATION_IDS[_rp_name] = _rp_code
    CTR_LOCATION_TO_REGION[_rp_name] = _rp_region


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
