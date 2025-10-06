import logging

from BaseClasses import Item, ItemClassification

from .Types import ItemData, ctrAPItem
from .Locations import get_total_locations
from .Options import Trophysanity, Relicsanity, RelicDifficulty, Tokensanity, Gemsanity, Goal
from typing import List, Dict, TYPE_CHECKING


if TYPE_CHECKING:
    from . import ctrAPWorld

def create_itempool(world: "ctrAPWorld") -> List[Item]:
    itempool: List[Item] = []    

    itempool += create_junk_items(world, get_total_locations(world) - len(itempool) - 1)

    return itempool

def create_item(world: "ctrAPWorld", name: str) -> Item:
    data = item_table[name]
    return ctrAPItem(name, data.classification, data.ap_code, world.player)


def create_junk_items(world: "ctrAPWorld", count: int) -> List[Item]:
    trap_chance = world.options.TrapChance.value
    junk_pool: List[Item] = []
    junk_list: Dict[str, int] = {}
    trap_list: Dict[str, int] = {}

    for name in item_table.keys():

        ic = item_table[name].classification
        if ic == ItemClassification.filler:
            junk_list[name] = junk_weights.get(name)

    for i in range(count):
        if trap_chance > 0 and world.random.randint(1, 100) <= trap_chance:
            junk_pool.append(world.create_item(
                world.random.choices(list(trap_list.keys()), weights=list(trap_list.values()), k=1)[0]))
        else:
            junk_pool.append(world.create_item(
                world.random.choices(list(junk_list.keys()), weights=list(junk_list.values()), k=1)[0]))

    return junk_pool

ap_ctr_items = {
    # Progression items
    "Trophy": ItemData(35010001, ItemClassification.progression, 16),
    "Sapphire Relic": ItemData(35010002, ItemClassification.progression, 18),
    "Gold Relic": ItemData(35010003, ItemClassification.progression, 18),
    "Platinum Relic": ItemData(35010004, ItemClassification.progression, 18),
    "Red CTR Token": ItemData(35010005, ItemClassification.progression, 4),
    "Green CTR Token": ItemData(35010006, ItemClassification.progression, 4),
    "Blue CTR Token": ItemData(35010007, ItemClassification.progression, 4),
    "Yellow CTR Token": ItemData(35010008, ItemClassification.progression, 4),
    "Purple CTR Token": ItemData(35010009, ItemClassification.progression, 4),
    "Red Gem": ItemData(35010010, ItemClassification.progression, 1),
    "Green Gem": ItemData(35010011, ItemClassification.progression, 1),
    "Blue Gem": ItemData(35010012, ItemClassification.progression, 1),
    "Yellow Gem": ItemData(35010013, ItemClassification.progression, 1),
    "Purple Gem": ItemData(35010014, ItemClassification.progression, 1),
    "Key": ItemData(35010015, ItemClassification.progression, 4),
    "Progressive Door": ItemData(35010016, ItemClassification.progression, 4),

    # Character Unlocks (for character swap mod)
    "Ripper Roo": ItemData(35019900, ItemClassification.useful, 1),
    "Papu Papu": ItemData(35019901, ItemClassification.useful, 1),
    "Komodo Joe": ItemData(35019902, ItemClassification.useful, 1),
    "Pinstripe": ItemData(35019903, ItemClassification.useful, 1),
    "Fake Crash": ItemData(35019904, ItemClassification.useful, 1),
    "N. Tropy": ItemData(35019905, ItemClassification.useful, 1),
    "Penta Penguin": ItemData(3501905, ItemClassification.useful, 1),
    "Nitros Oxide": ItemData(35019906, ItemClassification.useful, 1),
}

junk_items = {
    # Junk
    "Wumpa Fruit": ItemData(35011053, ItemClassification.filler, 0)

}

junk_weights = {
    "Wumpa Fruit": 40
}

item_table = {
    **ap_ctr_items,
    **junk_items
}