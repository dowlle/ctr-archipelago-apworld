"""Accept legacy look settings and restore look metadata from older rooms."""
from copy import copy
from typing import Dict, List

from .notices import adjusted

#: Look item name -> (racer it dresses, look name). Item names are frozen once
#: released.
LOOKS: Dict[str, Dict[str, str]] = {
    "Joe Mama": {"racer": "Komodo Joe", "look": "Komodo Moe"},
}
#: The item group every look item joins.
GROUP = "Character Looks"
#: Filler weight of each allowed look, beside Wumpa Fruit at 6 and Reserve
#: Top-Up at 1 (JL1 plan: like Reserve Top-Up).
WEIGHT = 1
#: The slot_data key inside ctr_options.
WIRE_KEY = "character_looks"


def park(world) -> None:
    """Accept old YAMLs and record the adjustment before generating a new plan."""
    option = world.options.character_looks
    changed = bool(option.value)
    if changed:
        option = copy(option)
        option.value = set()
        world.options.character_looks = option

    # The registry still resolves reserved ids, but generation must not grant
    # them as starting items or use them as link replacements.
    for field in ("start_inventory", "start_inventory_from_pool"):
        inventory = getattr(world.options, field)
        if LOOKS.keys() & inventory.value.keys():
            inventory = copy(inventory)
            inventory.value = {name: count for name, count in inventory.value.items() if name not in LOOKS}
            setattr(world.options, field, inventory)
            changed = True
    for group in world.multiworld.groups.values():
        replacements = group.get("replacement_items", {})
        if replacements.get(world.player) in LOOKS:
            replacements[world.player] = None
            changed = True

    if changed:
        adjusted(world, WIRE_KEY,
                 "Character Looks: turned off until player-supplied model packs are supported.")


def allowed_looks(world) -> List[str]:
    """Restore the old room's looks for Universal Tracker."""
    passthrough = getattr(getattr(world, "multiworld", None), "re_gen_passthrough", {}).get(
        getattr(world, "game", ""))
    if not passthrough:
        return []
    names = (passthrough.get("ctr_options") or {}).get(WIRE_KEY) or []
    # Saved rooms turn slot-data lists into tuples.
    if not isinstance(names, (list, tuple)):
        return []
    return sorted({name for name in names if isinstance(name, str) and name in LOOKS})


def envelope(world) -> Dict[str, List[str]]:
    """Preserve legacy Tracker metadata. New rooms omit this field."""
    looks = allowed_looks(world)
    return {WIRE_KEY: looks} if looks else {}
