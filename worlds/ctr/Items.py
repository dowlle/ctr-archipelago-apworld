import json
import pkgutil
from BaseClasses import ItemClassification
from typing import List, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld


class ItemDict(TypedDict):
    name: str
    count: int
    classification: ItemClassification


item_prefix = 35010000


def load_item_table() -> List[ItemDict]:
    """
    Loads item data from the CTR world's data/items.json file.
    Returns a list of item dictionaries with proper ItemClassification enums.
    """
    data_bytes = pkgutil.get_data(__package__, "data/items.json")
    raw_items = json.loads(data_bytes.decode("utf-8"))

    classes = {
        "progression": ItemClassification.progression,
        "filler": ItemClassification.filler,
        "useful": ItemClassification.useful,
        "progression_skip_balancing": ItemClassification.progression_skip_balancing,
        "progression_deprioritized": ItemClassification.progression_deprioritized,
        "progression_deprioritized_skip_balancing": ItemClassification.progression_deprioritized_skip_balancing,
    }

    item_table: List[ItemDict] = []
    for entry in raw_items:
        cls_name = entry["classification"].lower()

        item_table.append({
            "name": entry["name"],
            "count": entry["count"],
            "classification": classes[cls_name],
        })

    return item_table
