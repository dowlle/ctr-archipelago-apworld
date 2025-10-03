# Look at init or Items.py for more information on imports
from typing import Dict, TYPE_CHECKING
import logging

from .Types import LocData

if TYPE_CHECKING:
    from . import ctrAPWorld

# This is technique in programming to make things more readable for booleans
# A boolean is true or false
def did_include_extra_locations(world: "ctrAPWorld") -> bool:
    return bool(world.options.ExtraLocations)

# This is used by ap and in Items.py
# Theres a multitude of reasons to need to grab how many locations there are
def get_total_locations(world: "ctrAPWorld") -> int:
    # This is the total that we'll keep updating as we count how many locations there are
    total = 0
    for name in location_table:
        # If we did not turn on extra locations (see how readable it is with that thing from the top)
        # AND the name of it is found in our extra locations table, then that means we dont want to count it
        # So continue moves onto the next name in the table
        if not did_include_extra_locations(world) and name in extra_locations:
            continue

        # If the location is valid though, count it
        if is_valid_location(world, name):
            total += 1

    return total

def get_location_names() -> Dict[str, int]:
    # This is just a fancy way of getting all the names and data in the location table and making a dictionary thats {name, code}
    # If you have dynamic locations then you want to add them to the dictionary as well
    names = {name: data.ap_code for name, data in location_table.items()}

    return names

# The check to make sure the location is valid
# I know it looks like the same as when we counted it but thats because this is an example
# Things get complicated fast so having a back up is nice
def is_valid_location(world: "ctrAPWorld", name) -> bool:
    if not did_include_extra_locations(world) and name in extra_locations:
        return False
    
    return True
# You might need more functions as well so be liberal with them
# My advice, if you are about to type the same thing in a second time, turn it into a function
# Even if you only do it once you can turn it into a function too for organization

# Heres where you do the next fun part of listing out all those locations
# Its a lot
# My advice, zone out for half an hour listening to music and hope you wake up to a completed list

# --- N. Sanity Beach ---
nsan_table = {

    "Crash Cove Reward 1": LocData(35012000, "Crash Cove"),
    "Crash Cove Reward 2": LocData(35012001, "Crash Cove"),
    "Crash Cove Reward 3": LocData(35012002, "Crash Cove"),
    "Roo's Tubes Reward 1": LocData(35012003, "Roo's Tubes"),
    "Roo's Tubes Reward 2": LocData(35012004, "Roo's Tubes"),
    "Roo's Tubes Reward 3": LocData(35012005, "Roo's Tubes"),
    "Mystery Caves Reward 1": LocData(35012006, "Mystery Caves"),
    "Mystery Caves Reward 2": LocData(35012007, "Mystery Caves"),
    "Mystery Caves Reward 3": LocData(35012008, "Mystery Caves"),
    "Sewer Speedway Reward 1": LocData(35012009, "Sewer Speedway"),
    "Sewer Speedway Reward 2": LocData(35012010, "Sewer Speedway"),
    "Sewer Speedway Reward 3": LocData(35012011, "Sewer Speedway"),
    "Ripper Roo Garage Reward 1": LocData(35012012, "Ripper Roo Garage"),
    "Skull Rock Reward 1": LocData(35012013, "Skull Rock"),
}




# --- Lost Ruins ---
lost_table = {

    "Coco Park Reward 1": LocData(35012014, "Coco Park"),
    "Coco Park Reward 2": LocData(35012015, "Coco Park"),
    "Coco Park Reward 3": LocData(35012016, "Coco Park"),
    "Tiger Temple Reward 1": LocData(35012017, "Tiger Temple"),
    "Tiger Temple Reward 2": LocData(35012018, "Tiger Temple"),
    "Tiger Temple Reward 3": LocData(35012019, "Tiger Temple"),
    "Papu's Pyramid Reward 1": LocData(35012020, "Papu's Pyramid"),
    "Papu's Pyramid Reward 2": LocData(35012021, "Papu's Pyramid"),
    "Papu's Pyramid Reward 3": LocData(35012022, "Papu's Pyramid"),
    "Dingo Canyon Reward 1": LocData(35012023, "Dingo Canyon"),
    "Dingo Canyon Reward 2": LocData(35012024, "Dingo Canyon"),
    "Dingo Canyon Reward 3": LocData(35012025, "Dingo Canyon"),
    "Papu Papu Garage Reward 1": LocData(35012026, "Papu Papu Garage"),
    "Rampage Ruins Reward 1": LocData(35012027, "Rampage Ruins"),
}




# --- Glacier Park ---
glac_table = {

    "Blizzard Bluff Reward 1": LocData(35012028, "Blizzard Bluff"),
    "Blizzard Bluff Reward 2": LocData(35012029, "Blizzard Bluff"),
    "Blizzard Bluff Reward 3": LocData(35012030, "Blizzard Bluff"),
    "Dragon Mines Reward 1": LocData(35012031, "Dragon Mines"),
    "Dragon Mines Reward 2": LocData(35012032, "Dragon Mines"),
    "Dragon Mines Reward 3": LocData(35012033, "Dragon Mines"),
    "Polar Pass Reward 1": LocData(35012034, "Polar Pass"),
    "Polar Pass Reward 2": LocData(35012035, "Polar Pass"),
    "Polar Pass Reward 3": LocData(35012036, "Polar Pass"),
    "Tiny Arena Reward 1": LocData(35012037, "Tiny Arena"),
    "Tiny Arena Reward 2": LocData(35012038, "Tiny Arena"),
    "Tiny Arena Reward 3": LocData(35012039, "Tiny Arena"),
    "Komodo Joe Garage Reward 1": LocData(35012040, "Komodo Joe Garage"),
    "Rocky Road Reward 1": LocData(35012041, "Rocky Road"),
}




# --- Citadel City ---
city_table = {

    "Hot Air Skyway Reward 1": LocData(35012042, "Hot Air Skyway"),
    "Hot Air Skyway Reward 2": LocData(35012043, "Hot Air Skyway"),
    "Hot Air Skyway Reward 3": LocData(35012044, "Hot Air Skyway"),
    "Cortex Castle Reward 1": LocData(35012045, "Cortex Castle"),
    "Cortex Castle Reward 2": LocData(35012046, "Cortex Castle"),
    "Cortex Castle Reward 3": LocData(35012047, "Cortex Castle"),
    "N. Gin Labs Reward 1": LocData(35012048, "N. Gin Labs"),
    "N. Gin Labs Reward 2": LocData(35012049, "N. Gin Labs"),
    "N. Gin Labs Reward 3": LocData(35012050, "N. Gin Labs"),
    "Oxide Station Reward 1": LocData(35012051, "Oxide Station"),
    "Oxide Station Reward 2": LocData(35012052, "Oxide Station"),
    "Oxide Station Reward 3": LocData(35012053, "Oxide Station"),
    "Pinstripe Garage Reward 1": LocData(35012054, "Pinstripe Garage"),
    "Nitro Court Reward 1": LocData(35012055, "Nitro Court"),
}




# --- Gem Stone Valley - Central ---
gemcent_table = {

    "Slide Coliseum Reward 1": LocData(35012056, "Slide Coliseum"),
    "Turbo Track Reward 1": LocData(35012057, "Turbo Track"),
    "N. Oxide Garage Reward 1": LocData(35012058, "N. Oxide Garage"),
    "N. Oxide Garage Reward 2": LocData(35012059, "N. Oxide Garage"),
}




# --- Gem Stone Valley - Cup Room ---
gemcups_table = {

    "Red Cup Reward 1": LocData(35012060, "Red Cup"),
    "Red Cup Reward 2": LocData(35012061, "Red Cup"),
    "Green Cup Reward 1": LocData(35012062, "Green Cup"),
    "Green Cup Reward 2": LocData(35012063, "Green Cup"),
    "Blue Cup Reward 1": LocData(35012064, "Blue Cup"),
    "Blue Cup Reward 2": LocData(35012065, "Blue Cup"),
    "Yellow Cup Reward 1": LocData(35012066, "Yellow Cup"),
    "Yellow Cup Reward 2": LocData(35012067, "Yellow Cup"),
    "Purple Cup Reward 1": LocData(35012068, "Purple Cup"),
    "Purple Cup Reward 2": LocData(35012069, "Purple Cup"),
}

extra_locations = {
    "Penta Penguin Cheat Code": LocData(35019000, "Penta Penguin")
}

# Also like in Items.py, this collects all the dictionaries together
# Its important to note that locations MUST be bigger than progressive item count and should be bigger than total item count
# Its not here because this is an example and im not funny enough to think of more locations
# But important to note
location_table = {
    **nsan_table,
    **lost_table,
    **glac_table,
    **city_table,
    **gemcent_table,
    **gemcups_table,
    **extra_locations
}