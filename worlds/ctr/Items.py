import logging

from BaseClasses import ItemClassification
from typing import List, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld


class ItemDict(TypedDict):
    name: str
    count: int
    classification: ItemClassification

Progression = ItemClassification.progression
Junk = ItemClassification.filler
Character = ItemClassification.useful

item_prefix = 35010000

item_table: List[ItemDict] = [
    {'name': "Trophy",
     'count': 16,
     'classification': Progression},
    {'name': "Sapphire Relic",
     'count': 18,
     'classification': Progression},
    {'name': "Gold Relic",
     'count': 18,
     'classification': Progression},
    {'name': "Platinum Relic",
     'count': 18,
     'classification': Progression},
    {'name': "Red CTR Token",
     'count': 4,
     'classification': Progression},
    {'name': "Green CTR Token",
     'count': 4,
     'classification': Progression},
    {'name': "Blue CTR Token",
     'count': 4,
     'classification': Progression},
    {'name': "Yellow CTR Token",
     'count': 4,
     'classification': Progression},
    {'name': "Purple CTR Token",
     'count': 4,
     'classification': Progression},
    {'name': "Red Gem",
     'count': 1,
     'classification': Progression},
    {'name': "Green Gem",
     'count': 1,
     'classification': Progression},
    {'name': "Blue Gem",
     'count': 1,
     'classification': Progression},
    {'name': "Yellow Gem",
     'count': 1,
     'classification': Progression},
    {'name': "Purple Gem",
     'count': 1,
     'classification': Progression},
    {'name': "Key",
     'count': 4,
     'classification': Progression},
    {'name': "Wumpa Fruit",
     'count': 3,
     'classification': Junk},
    # {'name': "Progressive Door",
    #  'count': 4,
    #  'classification': Progression},
    # {'name': "Ripper Roo",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Papu Papu",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Komodo Joe",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Pinstripe",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Fake Crash",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "N. Tropy",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Penta Penguin",
    #  'count': 1,
    #  'classification': Character},
    # {'name': "Nitros Oxide",
    #  'count': 1,
    #  'classification': Character},
]