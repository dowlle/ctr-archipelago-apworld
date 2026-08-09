import json
import pkgutil
from BaseClasses import ItemClassification
from typing import List, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld


class ItemDict(TypedDict):
    name: str
    code: int
    count: int
    classification: ItemClassification

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
        "trap": ItemClassification.trap,
        "progression_skip_balancing": ItemClassification.progression_skip_balancing,
        "progression_deprioritized": ItemClassification.progression_deprioritized,
        "progression_deprioritized_skip_balancing": ItemClassification.progression_deprioritized_skip_balancing,
    }

    item_table: List[ItemDict] = []
    seen_names = set()
    seen_codes = set()
    for entry in raw_items:
        cls_name = entry["classification"].lower()
        name = entry["name"]
        code = entry["code"]

        if not isinstance(name, str) or not name:
            raise ValueError(f"Invalid CTR item name: {name!r}")
        if type(code) is not int or code < 0:
            raise ValueError(f"Invalid CTR item code for {name!r}: {code!r}")
        if name in seen_names:
            raise ValueError(f"Duplicate CTR item name: {name!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate CTR item code: {code}")
        seen_names.add(name)
        seen_codes.add(code)

        item_table.append({
            "name": name,
            "code": code,
            "count": entry["count"],
            "classification": classes[cls_name],
        })

    return item_table
