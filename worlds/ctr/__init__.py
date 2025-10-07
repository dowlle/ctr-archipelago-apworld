import logging
from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, CollectionState, WebWorld
from typing import Dict
from .Locations import get_location_names, get_total_locations
from .Items import item_table, item_prefix
from .Options import ctrAPOptions
from .Regions import create_regions
from .Rules import set_rules
from .Types import ctrAPItem

class ctrAPWeb(WebWorld):
    theme = "Party"
    
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up (the game you are randomizing) for Archipelago. "
        "This guide covers single-player, multiworld, and related software.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Taor"]
    )]


class ctrAPWorld(World):
    """
    This is where you describe your game. Pretend you are marketing the game and that people have no clue what it is.
    Or make it silly. Whatever you wish I have no control over you.
    """

    game = "Crash Team Racing"
    item_name_to_id = {item["name"]: (item_prefix + index) for index, item in enumerate(item_table)}
    location_name_to_id = get_location_names()
    options_dataclass = ctrAPOptions
    options = ctrAPOptions
    web = ctrAPWeb()


    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)





    def create_regions(self):
        create_regions(self)

    def set_rules(self):
        set_rules(self)
    
    
    def create_item(self, name: str) -> "ctrAPItem":
        item_id: int = self.item_name_to_id[name]
        id = item_id - item_prefix

        return ctrAPItem(name, item_table[id]["classification"], item_id, player=self.player)
    
    def create_event(self, event: str):
        return ctrAPItem(event, ItemClassification.progression_skip_balancing, None, self.player)


    def create_items(self):

        pool = []

        for item in item_table:
            count = item["count"]
            
            if count <= 0:
                continue
            else:
                for _ in range(count):
                    pool.append(self.create_item(item["name"]))

        self.multiworld.itempool += pool


#todo: add options to slot data
    def fill_slot_data(self) -> Dict[str, object]:
        slot_data: Dict[str, object] = {
            "options": {
            "Goal":                 self.options.Goal.value,
            },
            "Seed": self.multiworld.seed_name,  # to verify the server's multiworld
            "Slot": self.multiworld.player_name[self.player],  # to connect to server
            "TotalLocations": get_total_locations(self)
        }

        return slot_data
    

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)
    
    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)