# Look at init or Items.py for more information on imports
from typing import Dict, TYPE_CHECKING
import logging

from .Types import LocData

if TYPE_CHECKING:
    from . import ctrAPWorld



def get_total_locations(world: "ctrAPWorld") -> int:
    total = 0
    for name in location_table:
            total += 1

    return total

def get_location_names() -> Dict[str, int]:
    names = {name: data.ap_code for name, data in location_table.items()}

    return names


# --- N. Sanity Beach ---
nsan_table = {

    "Crash Cove Reward 1": LocData(35012000, "Crash Cove", "Trophy Race"),
    "Crash Cove Reward 2": LocData(35012001, "Crash Cove", "Sapphire Time Trial"),
    "Crash Cove Reward 3": LocData(35012002, "Crash Cove", "Gold Time Trial"),
    "Crash Cove Reward 4": LocData(35012003, "Crash Cove", "Platinum Time Trial"),
    "Crash Cove Reward 5": LocData(35012004, "Crash Cove", "CTR Token Challenge"),
    "Roo's Tubes Reward 1": LocData(35012005, "Roo's Tubes", "Trophy Race"),
    "Roo's Tubes Reward 2": LocData(35012006, "Roo's Tubes", "Sapphire Time Trial"),
    "Roo's Tubes Reward 3": LocData(35012007, "Roo's Tubes", "Gold Time Trial"),
    "Roo's Tubes Reward 4": LocData(35012008, "Roo's Tubes", "Platinum Time Trial"),
    "Roo's Tubes Reward 5": LocData(35012009, "Roo's Tubes", "CTR Token Challenge"),
    "Mystery Caves Reward 1": LocData(35012010, "Mystery Caves", "Trophy Race"),
    "Mystery Caves Reward 2": LocData(35012011, "Mystery Caves", "Sapphire Time Trial"),
    "Mystery Caves Reward 3": LocData(35012012, "Mystery Caves", "Gold Time Trial"),
    "Mystery Caves Reward 4": LocData(35012013, "Mystery Caves", "Platinum Time Trial"),
    "Mystery Caves Reward 5": LocData(35012014, "Mystery Caves", "CTR Token Challenge"),
    "Sewer Speedway Reward 1": LocData(35012015, "Sewer Speedway", "Trophy Race"),
    "Sewer Speedway Reward 2": LocData(35012016, "Sewer Speedway", "Sapphire Time Trial"),
    "Sewer Speedway Reward 3": LocData(35012017, "Sewer Speedway", "Gold Time Trial"),
    "Sewer Speedway Reward 4": LocData(35012018, "Sewer Speedway", "Platinum Time Trial"),
    "Sewer Speedway Reward 5": LocData(35012019, "Sewer Speedway", "CTR Token Challenge"),
    "Ripper Roo Garage Reward 1": LocData(35012020, "Ripper Roo Garage"),
    "Skull Rock Reward 1": LocData(35012021, "Skull Rock", "Crystal Bonus Round"),
}




# --- Lost Ruins ---
lost_table = {

    "Coco Park Reward 1": LocData(35012022, "Coco Park", "Trophy Race"),
    "Coco Park Reward 2": LocData(35012023, "Coco Park", "Sapphire Time Trial"),
    "Coco Park Reward 3": LocData(35012024, "Coco Park", "Gold Time Trial"),
    "Coco Park Reward 4": LocData(35012025, "Coco Park", "Platinum Time Trial"),
    "Coco Park Reward 5": LocData(35012026, "Coco Park", "CTR Token Challenge"),
    "Tiger Temple Reward 1": LocData(35012027, "Tiger Temple", "Trophy Race"),
    "Tiger Temple Reward 2": LocData(35012028, "Tiger Temple", "Sapphire Time Trial"),
    "Tiger Temple Reward 3": LocData(35012029, "Tiger Temple", "Gold Time Trial"),
    "Tiger Temple Reward 4": LocData(35012030, "Tiger Temple", "Platinum Time Trial"),
    "Tiger Temple Reward 5": LocData(35012031, "Tiger Temple", "CTR Token Challenge"),
    "Papu's Pyramid Reward 1": LocData(35012032, "Papu's Pyramid", "Trophy Race"),
    "Papu's Pyramid Reward 2": LocData(35012033, "Papu's Pyramid", "Sapphire Time Trial"),
    "Papu's Pyramid Reward 3": LocData(35012034, "Papu's Pyramid", "Gold Time Trial"),
    "Papu's Pyramid Reward 4": LocData(35012035, "Papu's Pyramid", "Platinum Time Trial"),
    "Papu's Pyramid Reward 5": LocData(35012036, "Papu's Pyramid", "CTR Token Challenge"),
    "Dingo Canyon Reward 1": LocData(35012037, "Dingo Canyon", "Trophy Race"),
    "Dingo Canyon Reward 2": LocData(35012038, "Dingo Canyon", "Sapphire Time Trial"),
    "Dingo Canyon Reward 3": LocData(35012039, "Dingo Canyon", "Gold Time Trial"),
    "Dingo Canyon Reward 4": LocData(35012040, "Dingo Canyon", "Platinum Time Trial"),
    "Dingo Canyon Reward 5": LocData(35012041, "Dingo Canyon", "CTR Token Challenge"),
    "Papu Papu Garage Reward 1": LocData(35012042, "Papu Papu Garage", "Boss Race"),
    "Rampage Ruins Reward 1": LocData(35012043, "Rampage Ruins", "Crystal Bonus Round"),
}




# --- Glacier Park ---
glac_table = {

    "Blizzard Bluff Reward 1": LocData(35012044, "Blizzard Bluff", "Trophy Race"),
    "Blizzard Bluff Reward 2": LocData(35012045, "Blizzard Bluff", "Sapphire Time Trial"),
    "Blizzard Bluff Reward 3": LocData(35012046, "Blizzard Bluff", "Gold Time Trial"),
    "Blizzard Bluff Reward 4": LocData(35012047, "Blizzard Bluff", "Platinum Time Trial"),
    "Blizzard Bluff Reward 5": LocData(35012048, "Blizzard Bluff", "CTR Token Challenge"),
    "Dragon Mines Reward 1": LocData(35012049, "Dragon Mines", "Trophy Race"),
    "Dragon Mines Reward 2": LocData(35012050, "Dragon Mines", "Sapphire Time Trial"),
    "Dragon Mines Reward 3": LocData(35012051, "Dragon Mines", "Gold Time Trial"),
    "Dragon Mines Reward 4": LocData(35012052, "Dragon Mines", "Platinum Time Trial"),
    "Dragon Mines Reward 5": LocData(35012053, "Dragon Mines", "CTR Token Challenge"),
    "Polar Pass Reward 1": LocData(35012054, "Polar Pass", "Trophy Race"),
    "Polar Pass Reward 2": LocData(35012055, "Polar Pass", "Sapphire Time Trial"),
    "Polar Pass Reward 3": LocData(35012056, "Polar Pass", "Gold Time Trial"),
    "Polar Pass Reward 4": LocData(35012057, "Polar Pass", "Platinum Time Trial"),
    "Polar Pass Reward 5": LocData(35012058, "Polar Pass", "CTR Token Challenge"),
    "Tiny Arena Reward 1": LocData(35012059, "Tiny Arena", "Trophy Race"),
    "Tiny Arena Reward 2": LocData(35012060, "Tiny Arena", "Sapphire Time Trial"),
    "Tiny Arena Reward 3": LocData(35012061, "Tiny Arena", "Gold Time Trial"),
    "Tiny Arena Reward 4": LocData(35012062, "Tiny Arena", "Platinum Time Trial"),
    "Tiny Arena Reward 5": LocData(35012063, "Tiny Arena", "CTR Token Challenge"),
    "Komodo Joe Garage Reward 1": LocData(35012064, "Komodo Joe Garage", "Boss Race"),
    "Rocky Road Reward 1": LocData(35012065, "Rocky Road", "Crystal Bonus Round"),
}




# --- Citadel City ---
city_table = {

    "Hot Air Skyway Reward 1": LocData(35012066, "Hot Air Skyway", "Trophy Race"),
    "Hot Air Skyway Reward 2": LocData(35012067, "Hot Air Skyway", "Sapphire Time Trial"),
    "Hot Air Skyway Reward 3": LocData(35012068, "Hot Air Skyway", "Gold Time Trial"),
    "Hot Air Skyway Reward 4": LocData(35012069, "Hot Air Skyway", "Platinum Time Trial"),
    "Hot Air Skyway Reward 5": LocData(35012070, "Hot Air Skyway", "CTR Token Challenge"),
    "Cortex Castle Reward 1": LocData(35012071, "Cortex Castle", "Trophy Race"),
    "Cortex Castle Reward 2": LocData(35012072, "Cortex Castle", "Sapphire Time Trial"),
    "Cortex Castle Reward 3": LocData(35012073, "Cortex Castle", "Gold Time Trial"),
    "Cortex Castle Reward 4": LocData(35012074, "Cortex Castle", "Platinum Time Trial"),
    "Cortex Castle Reward 5": LocData(35012075, "Cortex Castle", "CTR Token Challenge"),
    "N. Gin Labs Reward 1": LocData(35012076, "N. Gin Labs", "Trophy Race"),
    "N. Gin Labs Reward 2": LocData(35012077, "N. Gin Labs", "Sapphire Time Trial"),
    "N. Gin Labs Reward 3": LocData(35012078, "N. Gin Labs", "Gold Time Trial"),
    "N. Gin Labs Reward 4": LocData(35012079, "N. Gin Labs", "Platinum Time Trial"),
    "N. Gin Labs Reward 5": LocData(35012080, "N. Gin Labs", "CTR Token Challenge"),
    "Oxide Station Reward 1": LocData(35012081, "Oxide Station", "Trophy Race"),
    "Oxide Station Reward 2": LocData(35012082, "Oxide Station", "Sapphire Time Trial"),
    "Oxide Station Reward 3": LocData(35012083, "Oxide Station", "Gold Time Trial"),
    "Oxide Station Reward 4": LocData(35012084, "Oxide Station", "Platinum Time Trial"),
    "Oxide Station Reward 5": LocData(35012085, "Oxide Station", "CTR Token Challenge"),
    "Pinstripe Garage Reward 1": LocData(35012086, "Pinstripe Garage", "Boss Race"),
    "Nitro Court Reward 1": LocData(35012087, "Nitro Court", "Crystal Bonus Round"),
}




# --- Gemstone Valley - Central ---
gemcent_table = {

    "Slide Coliseum Reward 1": LocData(35012088, "Slide Coliseum", "Sapphire Time Trial"),
    "Slide Coliseum Reward 2": LocData(35012089, "Slide Coliseum", "Gold Time Trial"),
    "Slide Coliseum Reward 3": LocData(35012090, "Slide Coliseum", "Platinum Time Trial"),
    "Turbo Track Reward 1": LocData(35012091, "Turbo Track", "Sapphire Time Trial"),
    "Turbo Track Reward 2": LocData(35012092, "Turbo Track", "Gold Time Trial"),
    "Turbo Track Reward 3": LocData(35012093, "Turbo Track", "Platinum Time Trial"),
    "N. Oxide Garage Reward 1": LocData(35012094, "N. Oxide Garage", "Beat Oxide Once"),
    "N. Oxide Garage Reward 2": LocData(35012095, "N. Oxide Garage", "Character Unlock"),
    "N. Oxide Garage Reward 3": LocData(35012096, "N. Oxide Garage", "Beat Oxide Twice"),
}




# --- Gemstone Valley - Cup Room ---
gemcups_table = {

    "Red Cup Reward 1": LocData(35012097, "Red Cup", "Gem Cup"),
    "Red Cup Reward 2": LocData(35012098, "Red Cup", "Character Unlock"),
    "Green Cup Reward 1": LocData(35012099, "Green Cup", "Gem Cup"),
    "Green Cup Reward 2": LocData(35012100, "Green Cup", "Character Unlock"),
    "Blue Cup Reward 1": LocData(35012101, "Blue Cup", "Gem Cup"),
    "Blue Cup Reward 2": LocData(35012102, "Blue Cup", "Character Unlock"),
    "Yellow Cup Reward 1": LocData(35012103, "Yellow Cup", "Gem Cup"),
    "Yellow Cup Reward 2": LocData(35012104, "Yellow Cup", "Character Unlock"),
    "Purple Cup Reward 1": LocData(35012105, "Purple Cup", "Gem Cup"),
    "Purple Cup Reward 2": LocData(35012106, "Purple Cup", "Character Unlock"),
}


location_table = {
    **nsan_table,
    **lost_table,
    **glac_table,
    **city_table,
    **gemcent_table,
    **gemcups_table
}