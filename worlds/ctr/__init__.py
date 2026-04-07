import logging
import json
import os
from typing import Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, CollectionState, WebWorld
from .Locations import get_location_names, get_total_locations
from .Items import load_item_table, item_prefix
from .Options import ctrAPOptions
from .Regions import create_regions
from .Rom import CrashTeamRacingProcedurePatch, write_tokens
from .Rules import set_rules
from .Types import ctrAPItem


class ctrAPWeb(WebWorld):
    theme = "Party"

    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Crash Team Racing for Archipelago, including "
            "single-player, multiworld, and required tools.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Taor", "Icebound777"]
        )
    ]


class ctrAPWorld(World):
    """
    Crash Team Racing (CTR) is a kart racing game developed by Naughty Dog and published by Sony
    Computer Entertainment for the PlayStation in 1999.
    It features characters from the Crash Bandicoot series and combines fast-paced racing with
    power-ups and weapons.
    """

    game = "Crash Team Racing"
    web = ctrAPWeb()
    topology_present = True
    options_dataclass = ctrAPOptions
    options: ctrAPOptions

    # Item + Location mapping
    item_name_to_id = {
        item["name"]: (item_prefix + index)
        for index, item in enumerate(load_item_table())
    }
    location_name_to_id = get_location_names()

    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)
        self.start_region = None

    def create_regions(self):
        create_regions(self)

    def set_rules(self):
        set_rules(self)

    # --- Item creation ---

    def create_item(self, name: str) -> "ctrAPItem":
        item_id: int = self.item_name_to_id[name]
        idx = item_id - item_prefix
        return ctrAPItem(
            name,
            load_item_table()[idx]["classification"],
            item_id,
            player=self.player
        )

    def create_event(self, event: str):
        return ctrAPItem(
            event,
            ItemClassification.progression_skip_balancing,
            None,
            self.player
        )

    def place_items_from_dict(self, option_dict: Dict[str, str]):
        for loc, item in option_dict.items():
            self.get_location(loc).place_locked_item(self.create_item(item))

    def create_filler(self, count: int) -> List[Item]:
        junk_pool: List[Item] = []
        for _ in range(count):
            junk_pool.append(self.create_item("Wumpa Fruit"))
        return junk_pool

    def create_items(self):
        player = self.player
        mw = self.multiworld
        pool = []

        if self.options.goal.value <= 2:
            victory = ctrAPItem(
                "Victory",
                ItemClassification.progression_skip_balancing,
                None,
                player
            )

            match self.options.goal.value:
                case 0:
                    mw.get_location(
                        "N. Oxide Garage: N. Oxide's Challenge",
                        player
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        "Victory", player
                    )
                case 1:
                    mw.get_location(
                        "N. Oxide Garage: N. Oxide's Final Challenge",
                        player
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        "Victory",
                        player
                    )
                case 2:
                    mw.get_location(
                        "N. Oxide Garage: N. Oxide's Final Challenge",
                        player
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = (
                        lambda state:
                            state.has("Victory", player)
                            and state.has("Gold Relic", player, 18)
                            and all(state.has(g, player, 1)
                                    for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
                                )
                    )

        elif self.options.goal.value >= 3:
            match self.options.goal.value:
                case 3:
                    mw.completion_condition[player] = lambda state: state.has(
                        "Trophy",
                        player,
                        16
                    )
                case 4:
                    self.gemgoal(player)

        # --- Create general item pool ---
        for item in load_item_table():
            count = item["count"]
            if count > 0:
                for _ in range(count):
                    pool.append(self.create_item(item["name"]))

        mw.itempool += pool
        mw.itempool += self.create_filler(
            (get_total_locations(self) - len(mw.itempool))
        )

    def gemgoal(self, player):
        """Locks gem rewards in the appropriate Gem Cup locations."""
        data_path = os.path.join(
            os.path.dirname(
                __file__
            ),
            "data",
            "vanilla_mapping.json"
        )
        with open(data_path, "r", encoding="utf-8") as f:
            _mapping = json.load(f)
        mw = self.multiworld
        for loc_name, gem_name in _mapping["ShuffleOptions"]["Gems"].items():
            loc = mw.get_location(loc_name, player)
            loc.place_locked_item(self.create_item(gem_name))

        mw.completion_condition[player] = lambda state: all(
            state.has(g, player, 1)
            for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        )

    def fill_slot_data(self) -> Dict[str, object]:
        slot_data: Dict[str, object] = {
            "options": {
                "Goal": self.options.goal.value,
                "Relic Difficulty": self.options.relicdifficulty.value,
                "Shuffle Warp Pads": self.options.shuffle_warp_pads.value,
            },
            "Seed": self.multiworld.seed_name,
            "Slot": self.multiworld.player_name[self.player],
            "TotalLocations": get_total_locations(self),
        }
        return slot_data

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)

    # --- Output generation ---

    def generate_output(self, output_directory: str) -> None:
        patch: CrashTeamRacingProcedurePatch = CrashTeamRacingProcedurePatch(
            player=self.player,
            player_name=self.player_name
        )
        patch.write_file(
            "base_patch.bsdiff4",
            pkgutil.get_data(
                __name__,
                "data/base_patch.bsdiff4"
            )
        )
        write_tokens(
            patch=patch,
            item_placement=self.multiworld.get_locations(self.player),
        )

        # Write output
        out_file_name: str = self.multiworld.get_out_file_name_base(
            self.player
        )
        patch.write(
            os.path.join(
                output_directory,
                f"{out_file_name}{patch.patch_file_ending}"
            )
        )
