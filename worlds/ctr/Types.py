from typing import NamedTuple, Optional
from BaseClasses import Location, Item, ItemClassification

class ctrAPLocation(Location):
    game = "Crash Team Racing"

class ctrAPItem(Item):
    game = "Crash Team Racing"


class ItemData(NamedTuple):
    ap_code: Optional[int]
    classification: ItemClassification
    count: Optional[int] = 1


class LocData(NamedTuple):
    ap_code: Optional[int]
    region: Optional[str]
