import logging
import os
import json
from BaseClasses import ItemClassification
from typing import List, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld


class ItemDict(TypedDict):
    name: str
    count: int
    classification: ItemClassification

valid_classes = {
    "progression": ItemClassification.progression,
    "filler": ItemClassification.filler,
    "useful": ItemClassification.useful,
    "progression_skip_balancing": ItemClassification.progression_skip_balancing
}

item_prefix = 35010000

def load_item_table() -> List[ItemDict]:
    """
    Loads item data from the CTR world's data/items.json file.
    Returns a list of item dictionaries with proper ItemClassification enums.
    """
    data_path = os.path.join(os.path.dirname(__file__), "data", "items.json")
    with open(data_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    valid_classes = {
        "progression": ItemClassification.progression,
        "filler": ItemClassification.filler,
        "useful": ItemClassification.useful,
        "progression_skip_balancing": ItemClassification.progression_skip_balancing
    }

    item_table: List[ItemDict] = []
    for entry in raw_items:
        cls_name = entry["classification"].lower()
        if cls_name not in valid_classes:
            raise ValueError(f"Unknown item classification: {cls_name}")

        item_table.append({
            "name": entry["name"],
            "count": entry["count"],
            "classification": valid_classes[cls_name],
        })

    return item_table