"""Item name groups (issue #167 first four, #536 the rest).

Every group is built from the registries that own the names (the roster, the
stat chains, the letter tables, the item data classifications) instead of being
typed out, so a roster, chain or table change moves the group with it.

Group names share the item-name namespace: AutoWorld builds
`all_item_and_group_names` from `item_names | set(item_name_groups)`, and a
YAML entry resolves against item names first. `build_item_name_groups` therefore
refuses a group named after an item. Groups add no id and no placement; they are
part of the checksummed datapackage payload.

NAMING (#536). The issue asks for "Stats (with their unique group for each stat
per character)". A per-character group cannot be named after the character:
"Crash Bandicoot" is that racer's unlock item. They are "<Character> Stats".
"Stats" holds the three stat chains (Top Speed, Acceleration, Turning) shared
and per character; Progressive Boost is a boost ladder, not a stat, and stays
out. "Filler" is the filler-classified items minus the Ignore pack: Ignore Sand
carries the filler classification in data/items.json but belongs to the
Ignore Ground Types group.
"""
from typing import Dict, Iterable, Mapping, Set

from BaseClasses import ItemClassification

from . import characters, lettersanity, progressive_capability as pc
from .cortex_vortex import LETTER_ITEM_DATA as CORTEX_VORTEX_LETTER_ITEM_DATA
from .custom_lettersanity import CUSTOM_LETTER_ITEM_DATA
from .named_tracks import NAMED_TRACK_ITEM_DATA

IGNORE_PREFIX = "Ignore "


def letter_item_names() -> Set[str]:
    return (set(lettersanity.ALL_ITEM_NAMES)
            | {row["name"] for row in CUSTOM_LETTER_ITEM_DATA}
            | {row["name"] for row in CORTEX_VORTEX_LETTER_ITEM_DATA}
            | {row["name"] for row in NAMED_TRACK_ITEM_DATA})


def build_item_name_groups(item_data_by_name: Mapping[str, Mapping]
                           ) -> Dict[str, Set[str]]:
    """The #536 groups, from the merged `{item name: item data}` table."""
    groups: Dict[str, Set[str]] = {
        "Characters": {characters.unlock_item_name(c) for c in pc.ROSTER},
        "Stats": set(pc.SHARED_STAT_NAME.values()),
        "CTR Letters": letter_item_names(),
        "Ignore Ground Types": {n for n in item_data_by_name
                                if n.startswith(IGNORE_PREFIX)},
    }
    groups["Filler"] = {
        n for n, row in item_data_by_name.items()
        if row["classification"] == ItemClassification.filler
        and n not in groups["Ignore Ground Types"]}
    for character in pc.ROSTER:
        stats = set(pc.STAT_NAME_BY_CHARACTER[character].values())
        groups[f"{character} Stats"] = stats
        groups["Stats"] |= stats
    for name, members in groups.items():
        if not members:
            raise ValueError(f"item group {name!r} is empty")
        missing = members - set(item_data_by_name)
        if missing:
            raise ValueError(f"item group {name!r} holds unregistered items "
                             f"{sorted(missing)[:5]}")
        if name in item_data_by_name:
            raise ValueError(f"item group {name!r} collides with an item name")
    return groups


def merge_item_groups(base: Mapping[str, Iterable[str]],
                      new: Mapping[str, Iterable[str]]) -> Dict[str, Set[str]]:
    """`base` then `new`; a repeated group name is an error, never a merge."""
    clash = set(base) & set(new)
    if clash:
        raise ValueError(f"item groups declared twice: {sorted(clash)}")
    return {**{k: set(v) for k, v in base.items()},
            **{k: set(v) for k, v in new.items()}}
