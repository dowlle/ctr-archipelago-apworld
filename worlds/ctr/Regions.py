from BaseClasses import Region
from enum import IntEnum
from .Types import ctrAPLocation
from .Locations import location_table
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld

class ctrWarpPads(IntEnum):
    DINGO_CANYON = 0
    DRAGON_MINES = 1
    BLIZZARD_BLUFF = 2
    CRASH_COVE = 3
    TIGER_TEMPLE = 4
    PAPU_PYRAMID = 5
    ROO_TUBES = 6
    HOT_AIR_SKYWAY = 7
    SEWER_SPEEDWAY = 8
    MYSTERY_CAVES = 9
    CORTEX_CASTLE = 10
    N_GIN_LABS = 11
    POLAR_PASS = 12
    OXIDE_STATION = 13
    COCO_PARK = 14
    TINY_ARENA = 15
    SLIDE_COLISEUM = 16
    TURBO_TRACK = 17
    NITRO_COURT = 18
    RAMPAGE_RUINS = 19
    SKULL_ROCK = 21
    RED_CUP = 100
    GREEN_CUP = 101
    BLUE_CUP = 102
    YELLOW_CUP = 103
    PURPLE_CUP = 104

def create_regions(world: "ctrAPWorld"):

    menu = create_region(world, "Menu"),


    nsan_hub = create_region_and_connect(world, "N. Sanity Beach", "Menu -> N. Sanity Beach", menu),
    crash_cove = create_region_and_connect(world, "Crash Cove", "Crash Cove Warp Pad", nsan_hub),
    roo_toob = create_region_and_connect(world, "Roo's Tubes", "Roo's Tubes Warp Pad", nsan_hub),
    myst_cave = create_region_and_connect(world, "Mystery Caves", "Mystery Caves Warp Pad", nsan_hub),
    sew_speed = create_region_and_connect(world, "Sewer Speedway", "Sewer Speedway Warp Pad", nsan_hub),
    roo_grage = create_region_and_connect(world, "Ripper Roo Garage", "Ripper Roo Garage Door", nsan_hub),
    skull_rock = create_region_and_connect(world, "Skull Rock", "Skull Rock Warp Pad", nsan_hub),

    gemcent_hub = create_region_and_connect(world, "Gem Stone Valley", "N. Sanity Beach -> Gem Stone Valley", nsan_hub),
    slide_col = create_region_and_connect(world, "Slide Coliseum", "Slide Coliseum Warp Pad", gemcent_hub),
    turbo_track = create_region_and_connect(world, "Turbo Track", "Turbo Track Warp Pad", gemcent_hub),
    oxide_grage = create_region_and_connect(world, "N. Oxide Garage", "N. Oxide Garage Door", gemcent_hub),

    gemcups_hub = create_region_and_connect(world, "Cups Room", "Gem Stone Valley -> Cups Room", gemcent_hub),
    red_cup = create_region_and_connect(world, "Red Cup", "Red Cup Warp Pad", gemcups_hub),
    green_cup = create_region_and_connect(world, "Green Cup", "Green Cup Warp Pad", gemcups_hub),
    blue_cup = create_region_and_connect(world, "Blue Cup", "Blue Cup Warp Pad", gemcups_hub),
    yellow_cup = create_region_and_connect(world, "Yellow Cup", "Yellow Cup Warp Pad", gemcups_hub),
    purple_cup = create_region_and_connect(world, "Purple Cup", "Purple Cup Warp Pad", gemcups_hub),

    lost_hub = create_region_and_connect(world, "Lost Ruins", "Gem Stone Valley -> Lost Ruins", gemcent_hub),
    coco_park = create_region_and_connect(world, "Coco Park", "Coco Park Warp Pad", lost_hub),
    tiger_temple = create_region_and_connect(world, "Tiger Temple", "Tiger Temple Warp Pad", lost_hub),
    papu_pmid = create_region_and_connect(world, "Papu's Pyramid", "Papu's Pyramid Warp Pad", lost_hub),
    dingo_cany = create_region_and_connect(world, "Dingo Canyon", "Dingo Canyon Warp Pad", lost_hub),
    papu_grage = create_region_and_connect(world, "Papu Papu Garage", "Papu Papu Garage Door", lost_hub),
    ramp_ruin = create_region_and_connect(world, "Rampage Ruins", "Rampage Ruins Warp Pad", lost_hub),


    glac_hub = create_region_and_connect(world, "Glacier Park", "Lost Ruins -> Glacier Park", lost_hub),
    nsan_hub.connect(glac_hub, "Glacier Park -> N. Sanity Beach"),
    blizz_bluff = create_region_and_connect(world, "Blizzard Bluff", "Blizzard Bluff Warp Pad", glac_hub),
    drag_mine = create_region_and_connect(world, "Dragon Mines", "Dragon Mines Warp Pad", glac_hub),
    polar_pass = create_region_and_connect(world, "Polar Pass", "Polar Pass Warp Pad", glac_hub),
    tiny_arena = create_region_and_connect(world, "Tiny Arena", "Tiny Arena Warp Pad", glac_hub),
    komo_grage = create_region_and_connect(world, "Komodo Joe Garage", "Komodo Joe Garage Door", glac_hub),
    rocky_road = create_region_and_connect(world, "Rocky Road", "Rocky Road Warp Pad", glac_hub),

    city_hub = create_region_and_connect(world, "Citadel City", "Glacier Park -> Citadel City Warp Pad", glac_hub),
    hot_air = create_region_and_connect(world, "Hot Air Skyway", "Hot Air Skyway Warp Pad", city_hub),
    cort_cast = create_region_and_connect(world, "Cortex Castle", "Cortex Castle Warp Pad", city_hub),
    ngin_labs = create_region_and_connect(world, "N. Gin Labs", "N. Gin Labs Warp Pad", city_hub),
    oxide_stat = create_region_and_connect(world, "Oxide Station", "Oxide Station Warp Pad", city_hub),
    pins_grage = create_region_and_connect(world, "Pinstripe Garage", "Pinstripe Garage Door", city_hub),
    nitro_court = create_region_and_connect(world, "Nitro Court", "Nitro Court Warp Pad", city_hub),

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