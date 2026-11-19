"""Origin catalogue, pinned from the public track registry."""

import json
import pkgutil

from worlds.AutoWorld import data_package_checksum

from . import named_tracks

FEATURE = "origin_letters_v1"
DEFAULT = "CTR"

# Pinned together with named_tracks.json by tools/build_named_tracks.py.
_CATALOGUE = json.loads(pkgutil.get_data(__package__, "data/origins.json"))


def letters_for_package(package):
    """Stage 1 requires models in the exact LEV the seed pins."""
    row = _CATALOGUE["tracks"].get(package["content_id"])
    if not row or row["review"] != "verified" or row["relation"] not in ("port", "remake"):
        return DEFAULT
    game = _CATALOGUE["games"][row["origin_game"]]
    code = game["code"]
    lev = package["files"][0]["sha256"]
    if (game["racing_game"] and row.get("own_letter_models", {}).get(lev) == code
            and set(code) <= set(DEFAULT + named_tracks.MINTED_ORIGIN_GLYPHS)):
        return code
    return DEFAULT


def _origin_item(code):
    first, last = named_tracks.ORIGIN_ITEM_RANGE
    return first <= code <= last


def is_origin_location(code):
    row = named_tracks.block_of_location(code)
    return row is not None and 141 <= row[1] <= 176


def prune_unused_option_names(world):
    """Group expansion may include the reserved letter names for other rooms."""
    plan = world.ctr_content_plan
    locations = {row["location"] for row in plan["checks"]}
    items = {row["item"] for row in plan["items"]["rows"]}
    for option in (world.options.exclude_locations, world.options.priority_locations,
                   world.options.start_location_hints):
        option.value = {name for name in option.value
                        if not is_origin_location(world.location_name_to_id.get(name))
                        or world.location_name_to_id[name] in locations}
    for option in (world.options.start_hints, world.options.local_items, world.options.non_local_items):
        option.value = {name for name in option.value
                        if not _origin_item(world.item_name_to_id.get(name, 0))
                        or world.item_name_to_id[name] in items}


def preserve_legacy_package(multiworld, multidata, game):
    """Keep unused origin families out of a legacy room's embedded package."""
    ctr_slots = {slot for slot, world in multiworld.worlds.items() if world.game == game}
    if any(FEATURE in wire.get("content_plan", {}).get("required_features", ())
           for slot, wire in multidata["slot_data"].items() if slot in ctr_slots):
        return
    for slot, placements in multidata["locations"].items():
        if slot in ctr_slots and any(map(is_origin_location, placements)):
            return
        if any(owner in ctr_slots and _origin_item(code) for code, owner, _flags in placements.values()):
            return
    if any(_origin_item(code) for slot, items in multidata["precollected_items"].items()
           if slot in ctr_slots for code in items):
        return

    # Archipelago's global package is shared across generations. Copy the part
    # embedded in this room, as with the generic-track title aliases.
    package = multidata["datapackage"][game]
    result = package.copy()
    result.pop("checksum")
    for kind, is_origin in (("item", _origin_item), ("location", is_origin_location)):
        names, groups = f"{kind}_name_to_id", f"{kind}_name_groups"
        removed = {name for name, code in package[names].items() if is_origin(code)}
        result[groups] = {group: [name for name in members if name not in removed]
                          for group, members in package[groups].items()}
        result[names] = {name: code for name, code in package[names].items() if name not in removed}
    result["checksum"] = data_package_checksum(result)
    multidata["datapackage"][game] = result
