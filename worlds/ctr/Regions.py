import json, os
from BaseClasses import Region, Entrance, EntranceType
from .Locations import create_location


def _world_path():
    return os.path.join(os.path.dirname(__file__), "data", "world.json")


def create_regions(world):
    """Build all regions, exits, and locations from JSON definitions."""
    with open(_world_path(), "r") as f:
        data = json.load(f)

    player, mw = world.player, world.multiworld
    regions = []


    for reg in data["regions"]:
        region = Region(reg["name"], player, mw)
        region.type = reg.get("type", "generic")
        region.is_start = reg.get("is_start", False)
        mw.regions.append(region)
        regions.append(region)

    region_lookup = {r.name: r for r in regions}


    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for loc_data in reg.get("locations", []):
            name = loc_data["name"]
            location = create_location(player, name, region)
            location.type = loc_data.get("type", "default")
            location.logic_text = loc_data.get("requires", "True")
            region.locations.append(location)
            mw.regions.location_cache[player][name] = location


    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for ex in reg.get("exits", []):
            ent = Entrance(
                player,
                ex["name"],
                region,
                randomization_group=ex.get("randomization_group", 0),
                randomization_type=EntranceType[ex.get("randomization_type", "ONE_WAY")]
            )
            ent.access_rule_text = ex.get("access_rule", "True")
            tgt = ex.get("target")
            if tgt in region_lookup:
                ent.connect(region_lookup[tgt])
            region.exits.append(ent)
            mw.regions.entrance_cache[player][ent.name] = ent

    world.start_region = next((r for r in regions if getattr(r, "is_start", False)), None)
    return regions
