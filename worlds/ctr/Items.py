import logging

from BaseClasses import Item, ItemClassification
from .Types import ctrAPItem
from .Locations import get_total_locations
from typing import List, Dict, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld


class ItemDict(TypedDict):
    name: str
    count: int
    classification: ItemClassification

item_prefix = 35010000

item_table: List[ItemDict] = [
    {'name': "Trophy",
     'count': 16,
     'classification': ItemClassification.progression},
    {'name': "Sapphire Relic",
     'count': 18,
     'classification': ItemClassification.progression},
    {'name': "Gold Relic",
     'count': 18,
     'classification': ItemClassification.progression},
    {'name': "Platinum Relic",
     'count': 18,
     'classification': ItemClassification.progression},
    {'name': "Red CTR Token",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Green CTR Token",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Blue CTR Token",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Yellow CTR Token",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Purple CTR Token",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Red Gem",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Green Gem",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Blue Gem",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Yellow Gem",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Purple Gem",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Key",
     'count': 4,
     'classification': ItemClassification.progression},
    {'name': "Victory",
     'count': 1,
     'classification': ItemClassification.progression},
    {'name': "Wumpa Fruit",
     'count': 1,
     'classification': ItemClassification.filler},
    # {'name': "Progressive Door",
    #  'count': 4,
    #  'classification': ItemClassification.progression},
    # {'name': "Ripper Roo",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Papu Papu",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Komodo Joe",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Pinstripe",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Fake Crash",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "N. Tropy",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Penta Penguin",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
    # {'name': "Nitros Oxide",
    #  'count': 1,
    #  'classification': ItemClassification.useful},
]