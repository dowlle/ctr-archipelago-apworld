from BaseClasses import Region
from .Types import ctrAPLocation
from .Locations import location_table
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld


def create_regions(world: "ctrAPWorld"):

    menu = create_region(world, "Menu"),


    nsan_hub = create_region_and_connect(world, "N. Sanity Beach", "Menu -> N. Sanity Beach", menu),
    crash_cove = create_region_and_connect(world, "Crash Cove", "N. Sanity Beach -> Crash Cove", nsan_hub),
    roo_toob = create_region_and_connect(world, "Roo's Tubes", "N. Sanity Beach -> Roo's Tubes", nsan_hub),
    myst_cave = create_region_and_connect(world, "Mystery Caves", "N. Sanity Beach -> Mystery Caves", nsan_hub),
    sew_speed = create_region_and_connect(world, "Sewer Speedway", "N. Sanity Beach -> Sewer Speedway", nsan_hub),
    roo_grage = create_region_and_connect(world, "Ripper Roo Garage", "N. Sanity Beach -> Ripper Roo Garage", nsan_hub),
    skull_rock = create_region_and_connect(world, "Skull Rock", "N. Sanity Beach -> Skull Rock", nsan_hub),

    gemcent_hub = create_region_and_connect(world, "Gem Stone Valley", "N. Sanity Beach -> Gem Stone Valley", nsan_hub),
    slide_col = create_region_and_connect(world, "Slide Coliseum", "Gem Stone Valley -> Slide Coliseum", gemcent_hub),
    turbo_track = create_region_and_connect(world, "Turbo Track", "Gem Stone Valley -> Turbo Track", gemcent_hub),
    oxide_grage = create_region_and_connect(world, "N. Oxide Garage", "Gem Stone Valley -> N. Oxide Garage", gemcent_hub),

    gemcups_hub = create_region_and_connect(world, "Cups Room", "Gem Stone Valley -> Cups Room", gemcent_hub),
    red_cup = create_region_and_connect(world, "Red Cup", "Cups Room -> Red Cup", gemcups_hub),
    green_cup = create_region_and_connect(world, "Green Cup", "Cups Room -> Green Cup", gemcups_hub),
    blue_cup = create_region_and_connect(world, "Blue Cup", "Cups Room -> Blue Cup", gemcups_hub),
    yellow_cup = create_region_and_connect(world, "Yellow Cup", "Cups Room -> Yellow Cup", gemcups_hub),
    purple_cup = create_region_and_connect(world, "Purple Cup", "Cups Room -> Purple Cup", gemcups_hub),

    lost_hub = create_region_and_connect(world, "Lost Ruins", "Gem Stone Valley -> Lost Ruins", gemcent_hub),
    coco_park = create_region_and_connect(world, "Coco Park", " -> Coco Park", lost_hub),
    tiger_temple = create_region_and_connect(world, "Tiger Temple", " -> Tiger Temple", lost_hub),
    papu_pmid = create_region_and_connect(world, "Papu's Pyramid", " -> Papu's Pyramid", lost_hub),
    dingo_cany = create_region_and_connect(world, "Dingo Canyon", " -> Dingo Canyon", lost_hub),
    papu_grage = create_region_and_connect(world, "Papu Papu Garage", " -> Papu Papu Garage", lost_hub),
    ramp_ruin = create_region_and_connect(world, "Rampage Ruins", " -> Rampage Ruins", lost_hub),


    glac_hub = create_region_and_connect(world, "Glacier Park", "Lost Ruins -> Glacier Park", lost_hub),
    nsan_hub.connect(glac_hub, "Glacier Park -> N. Sanity Beach"),
    blizz_bluff = create_region_and_connect(world, "Blizzard Bluff", "Glacier Park -> Blizzard Bluff", glac_hub),
    drag_mine = create_region_and_connect(world, "Dragon Mines", "Glacier Park -> Dragon Mines", glac_hub),
    polar_pass = create_region_and_connect(world, "Polar Pass", "Glacier Park -> Polar Pass", glac_hub),
    tiny_arena = create_region_and_connect(world, "Tiny Arena", "Glacier Park -> Tiny Arena", glac_hub),
    komo_grage = create_region_and_connect(world, "Komodo Joe Garage", "Glacier Park -> Komodo Joe Garage", glac_hub),
    rocky_road = create_region_and_connect(world, "Rocky Road", "Glacier Park -> Rocky Road", glac_hub),

    city_hub = create_region_and_connect(world, "Citadel City", "Glacier Park -> Citadel City", glac_hub),
    hot_air = create_region_and_connect(world, "Hot Air Skyway", "Citadel City -> Hot Air Skyway", city_hub),
    cort_cast = create_region_and_connect(world, "Cortex Castle", "Citadel City -> Cortex Castle", city_hub),
    ngin_labs = create_region_and_connect(world, "N. Gin Labs", "Citadel City -> N. Gin Labs", city_hub),
    oxide_stat = create_region_and_connect(world, "Oxide Station", "Citadel City -> Oxide Station", city_hub),
    pins_grage = create_region_and_connect(world, "Pinstripe Garage", "Citadel City -> Pinstripe Garage", city_hub),
    nitro_court = create_region_and_connect(world, "Nitro Court", "Citadel City -> Nitro Court", city_hub),

def create_region(world: "ctrAPWorld", name: str) -> Region:
    reg = Region(name, world.player, world.multiworld)


    for (key, data) in location_table.items():
        if data.region == name:
            location = ctrAPLocation(world.player, key, data.ap_code, reg)
            reg.locations.append(location)
    
    world.multiworld.regions.append(reg)
    return reg

def create_region_and_connect(world: "ctrAPWorld",
                               name: str, entrancename: str, connected_region: Region) -> Region:
    reg: Region = create_region(world, name)
    connected_region.connect(reg, entrancename)
    return reg