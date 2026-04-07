from typing import NamedTuple, Optional
from BaseClasses import Location, Item, ItemClassification


class ctrAPLocation(Location):
    game = "Crash Team Racing"


class ctrAPItem(Item):
    game = "Crash Team Racing"


class LocData(NamedTuple):
    ap_code: Optional[int]
    region: Optional[str]
