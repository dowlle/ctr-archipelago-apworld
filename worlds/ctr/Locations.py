# Look at init or Items.py for more information on imports
from typing import Mapping, TYPE_CHECKING
import logging

from .Types import LocData

if TYPE_CHECKING:
    from . import ctrAPWorld



def get_total_locations(world: "ctrAPWorld") -> int:
    total = 0
    for name in location_table:
            total += 1

    return total

def get_location_names() -> Mapping[str, int]:
    names = {name: data.ap_code for name, data in location_table.items()}

    return names

# --- N. Sanity Beach ---
nsan_table = {

    "Crash Cove: Trophy Race": LocData(35012000, "Crash Cove"),
    "Crash Cove: Sapphire Time Trial": LocData(35012001, "Crash Cove"),
    "Crash Cove: Gold Time Trial": LocData(35012002, "Crash Cove"),
    "Crash Cove: Platinum Time Trial": LocData(35012003, "Crash Cove"),
    "Crash Cove: CTR Token Challenge": LocData(35012004, "Crash Cove"),

    "Roo's Tubes: Trophy Race": LocData(35012005, "Roo's Tubes"),
    "Roo's Tubes: Sapphire Time Trial": LocData(35012006, "Roo's Tubes"),
    "Roo's Tubes: Gold Time Trial": LocData(35012007, "Roo's Tubes"),
    "Roo's Tubes: Platinum Time Trial": LocData(35012008, "Roo's Tubes"),
    "Roo's Tubes: CTR Token Challenge": LocData(35012009, "Roo's Tubes"),

    "Mystery Caves: Trophy Race": LocData(35012010, "Mystery Caves"),
    "Mystery Caves: Sapphire Time Trial": LocData(35012011, "Mystery Caves"),
    "Mystery Caves: Gold Time Trial": LocData(35012012, "Mystery Caves"),
    "Mystery Caves: Platinum Time Trial": LocData(35012013, "Mystery Caves"),
    "Mystery Caves: CTR Token Challenge": LocData(35012014, "Mystery Caves"),

    "Sewer Speedway: Trophy Race": LocData(35012015, "Sewer Speedway"),
    "Sewer Speedway: Sapphire Time Trial": LocData(35012016, "Sewer Speedway"),
    "Sewer Speedway: Gold Time Trial": LocData(35012017, "Sewer Speedway"),
    "Sewer Speedway: Platinum Time Trial": LocData(35012018, "Sewer Speedway"),
    "Sewer Speedway: CTR Token Challenge": LocData(35012019, "Sewer Speedway"),

    "Ripper Roo Garage: Boss Race": LocData(35012020, "Ripper Roo Garage"),

    "Skull Rock: Crystal Bonus Round": LocData(35012021, "Skull Rock"),

}

# --- Lost Ruins ---
lost_table = {

    "Coco Park: Trophy Race": LocData(35012022, "Coco Park"),
    "Coco Park: Sapphire Time Trial": LocData(35012023, "Coco Park"),
    "Coco Park: Gold Time Trial": LocData(35012024, "Coco Park"),
    "Coco Park: Platinum Time Trial": LocData(35012025, "Coco Park"),
    "Coco Park: CTR Token Challenge": LocData(35012026, "Coco Park"),

    "Tiger Temple: Trophy Race": LocData(35012027, "Tiger Temple"),
    "Tiger Temple: Sapphire Time Trial": LocData(35012028, "Tiger Temple"),
    "Tiger Temple: Gold Time Trial": LocData(35012029, "Tiger Temple"),
    "Tiger Temple: Platinum Time Trial": LocData(35012030, "Tiger Temple"),
    "Tiger Temple: CTR Token Challenge": LocData(35012031, "Tiger Temple"),

    "Papu's Pyramid: Trophy Race": LocData(35012032, "Papu's Pyramid"),
    "Papu's Pyramid: Sapphire Time Trial": LocData(35012033, "Papu's Pyramid"),
    "Papu's Pyramid: Gold Time Trial": LocData(35012034, "Papu's Pyramid"),
    "Papu's Pyramid: Platinum Time Trial": LocData(35012035, "Papu's Pyramid"),
    "Papu's Pyramid: CTR Token Challenge": LocData(35012036, "Papu's Pyramid"),

    "Dingo Canyon: Trophy Race": LocData(35012037, "Dingo Canyon"),
    "Dingo Canyon: Sapphire Time Trial": LocData(35012038, "Dingo Canyon"),
    "Dingo Canyon: Gold Time Trial": LocData(35012039, "Dingo Canyon"),
    "Dingo Canyon: Platinum Time Trial": LocData(35012040, "Dingo Canyon"),
    "Dingo Canyon: CTR Token Challenge": LocData(35012041, "Dingo Canyon"),

    "Papu Papu Garage: Boss Race": LocData(35012042, "Papu Papu Garage"),

    "Rampage Ruins: Crystal Bonus Round": LocData(35012043, "Rampage Ruins"),

}

# --- Glacier Park ---
glac_table = {

    "Blizzard Bluff: Trophy Race": LocData(35012044, "Blizzard Bluff"),
    "Blizzard Bluff: Sapphire Time Trial": LocData(35012045, "Blizzard Bluff"),
    "Blizzard Bluff: Gold Time Trial": LocData(35012046, "Blizzard Bluff"),
    "Blizzard Bluff: Platinum Time Trial": LocData(35012047, "Blizzard Bluff"),
    "Blizzard Bluff: CTR Token Challenge": LocData(35012048, "Blizzard Bluff"),

    "Dragon Mines: Trophy Race": LocData(35012049, "Dragon Mines"),
    "Dragon Mines: Sapphire Time Trial": LocData(35012050, "Dragon Mines"),
    "Dragon Mines: Gold Time Trial": LocData(35012051, "Dragon Mines"),
    "Dragon Mines: Platinum Time Trial": LocData(35012052, "Dragon Mines"),
    "Dragon Mines: CTR Token Challenge": LocData(35012053, "Dragon Mines"),

    "Polar Pass: Trophy Race": LocData(35012054, "Polar Pass"),
    "Polar Pass: Sapphire Time Trial": LocData(35012055, "Polar Pass"),
    "Polar Pass: Gold Time Trial": LocData(35012056, "Polar Pass"),
    "Polar Pass: Platinum Time Trial": LocData(35012057, "Polar Pass"),
    "Polar Pass: CTR Token Challenge": LocData(35012058, "Polar Pass"),

    "Tiny Arena: Trophy Race": LocData(35012059, "Tiny Arena"),
    "Tiny Arena: Sapphire Time Trial": LocData(35012060, "Tiny Arena"),
    "Tiny Arena: Gold Time Trial": LocData(35012061, "Tiny Arena"),
    "Tiny Arena: Platinum Time Trial": LocData(35012062, "Tiny Arena"),
    "Tiny Arena: CTR Token Challenge": LocData(35012063, "Tiny Arena"),

    "Komodo Joe Garage: Boss Race": LocData(35012064, "Komodo Joe Garage"),

    "Rocky Road: Crystal Bonus Round": LocData(35012065, "Rocky Road"),

}

# --- Citadel City ---
city_table = {

    "Hot Air Skyway: Trophy Race": LocData(35012066, "Hot Air Skyway"),
    "Hot Air Skyway: Sapphire Time Trial": LocData(35012067, "Hot Air Skyway"),
    "Hot Air Skyway: Gold Time Trial": LocData(35012068, "Hot Air Skyway"),
    "Hot Air Skyway: Platinum Time Trial": LocData(35012069, "Hot Air Skyway"),
    "Hot Air Skyway: CTR Token Challenge": LocData(35012070, "Hot Air Skyway"),

    "Cortex Castle: Trophy Race": LocData(35012071, "Cortex Castle"),
    "Cortex Castle: Sapphire Time Trial": LocData(35012072, "Cortex Castle"),
    "Cortex Castle: Gold Time Trial": LocData(35012073, "Cortex Castle"),
    "Cortex Castle: Platinum Time Trial": LocData(35012074, "Cortex Castle"),
    "Cortex Castle: CTR Token Challenge": LocData(35012075, "Cortex Castle"),

    "N. Gin Labs: Trophy Race": LocData(35012076, "N. Gin Labs"),
    "N. Gin Labs: Sapphire Time Trial": LocData(35012077, "N. Gin Labs"),
    "N. Gin Labs: Gold Time Trial": LocData(35012078, "N. Gin Labs"),
    "N. Gin Labs: Platinum Time Trial": LocData(35012079, "N. Gin Labs"),
    "N. Gin Labs: CTR Token Challenge": LocData(35012080, "N. Gin Labs"),

    "Oxide Station: Trophy Race": LocData(35012081, "Oxide Station"),
    "Oxide Station: Sapphire Time Trial": LocData(35012082, "Oxide Station"),
    "Oxide Station: Gold Time Trial": LocData(35012083, "Oxide Station"),
    "Oxide Station: Platinum Time Trial": LocData(35012084, "Oxide Station"),
    "Oxide Station: CTR Token Challenge": LocData(35012085, "Oxide Station"),

    "Pinstripe Garage: Boss Race": LocData(35012086, "Pinstripe Garage"),

    "Nitro Court: Crystal Bonus Round": LocData(35012087, "Nitro Court"),

}

# --- Gemstone Valley - Central ---
gemcent_table = {

    "Slide Coliseum: Sapphire Time Trial": LocData(35012088, "Slide Coliseum"),
    "Slide Coliseum: Gold Time Trial": LocData(35012089, "Slide Coliseum"),
    "Slide Coliseum: Platinum Time Trial": LocData(35012090, "Slide Coliseum"),

    "Turbo Track: Sapphire Time Trial": LocData(35012091, "Turbo Track"),
    "Turbo Track: Gold Time Trial": LocData(35012092, "Turbo Track"),
    "Turbo Track: Platinum Time Trial": LocData(35012093, "Turbo Track"),

    "N. Oxide Garage: Beat Oxide Once": LocData(35012094, "N. Oxide Garage"),
    "N. Oxide Garage: Character Unlock": LocData(35012095, "N. Oxide Garage"),
    "N. Oxide Garage: Beat Oxide Twice": LocData(35012096, "N. Oxide Garage"),

}

# --- Gemstone Valley - Cup Room ---
gemcups_table = {

    "Red Cup: Gem Cup": LocData(35012097, "Red Cup"),
    "Red Cup: Character Unlock": LocData(35012098, "Red Cup"),

    "Green Cup: Gem Cup": LocData(35012099, "Green Cup"),
    "Green Cup: Character Unlock": LocData(35012100, "Green Cup"),

    "Blue Cup: Gem Cup": LocData(35012101, "Blue Cup"),
    "Blue Cup: Character Unlock": LocData(35012102, "Blue Cup"),

    "Yellow Cup: Gem Cup": LocData(35012103, "Yellow Cup"),
    "Yellow Cup: Character Unlock": LocData(35012104, "Yellow Cup"),

    "Purple Cup: Gem Cup": LocData(35012105, "Purple Cup"),
    "Purple Cup: Character Unlock": LocData(35012106, "Purple Cup"),
}


location_table = {
    **nsan_table,
    **lost_table,
    **glac_table,
    **city_table,
    **gemcent_table,
    **gemcups_table
}