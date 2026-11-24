"""Character looks (JL2): alternative driver models delivered as filler items.

The design rulings (2026-11-23 22:45 and 22:46 CET, design note "Joe looks filler
items"): every look is its own repeatable filler item, the newest look a player
receives becomes that racer's chosen look, an in-game OPTIONS row picks among
the received looks and the original, and the YAML option `character_looks`
lists the looks allowed in the item pool. The system is general (any racer, and
a first step towards custom characters); Komodo Moe for Komodo Joe is the first
look.

Generation only adds filler copies: a look never gates anything, so logic and
reachability are untouched. With the option empty (the default) the filler
draw and the wire are exactly what they were before this module.

Native reads nothing from slot_data for looks: received items drive the model
and the OPTIONS row. `ctr_options.character_looks` is emitted only when the list
is not empty, as tracker metadata and for a Universal Tracker restore; absent
means no looks.

Adding a look: one minted item (minted_items_030), one row here, its files and
table row in the native client (ap/ap_look_logic.h).
"""
from typing import Dict, List

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


def allowed_looks(world) -> List[str]:
    """The seed's allowed looks, sorted. On a Tracker restore the connected
    seed's wire decides (absent = none), like Reserve Top-Up."""
    passthrough = getattr(getattr(world, "multiworld", None), "re_gen_passthrough", {}).get(
        getattr(world, "game", ""))
    if passthrough:
        names = (passthrough.get("ctr_options") or {}).get(WIRE_KEY) or []
        if not isinstance(names, list):
            names = []
        if hasattr(world.options, "character_looks"):
            world.options.character_looks.value = {n for n in names if n in LOOKS}
    option = getattr(world.options, "character_looks", None)
    return sorted(n for n in (option.value if option is not None else ()) if n in LOOKS)


def envelope(world) -> Dict[str, List[str]]:
    """The optional ctr_options key: present only when a look is allowed."""
    looks = allowed_looks(world)
    return {WIRE_KEY: looks} if looks else {}
