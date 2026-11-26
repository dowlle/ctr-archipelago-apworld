"""Origin catalogue, pinned from the public track registry."""

import json
import pkgutil
from copy import copy
from functools import cache
from typing import NamedTuple

from worlds.AutoWorld import data_package_checksum

from . import destinations, named_tracks

FEATURE = "origin_letters_v1"
PLACEMENT_FEATURE = "placed_track_letters_v1"
DEFAULT = "CTR"

# Pinned together with named_tracks.json by tools/build_named_tracks.py.
_CATALOGUE = json.loads(pkgutil.get_data(__package__, "data/origins.json"))


def _origin(package):
    row = _CATALOGUE["tracks"].get(destinations.canonical_track_key(package["content_id"]))
    if not row or row["review"] != "verified" or row["relation"] not in ("port", "remake"):
        return {}, DEFAULT
    game = _CATALOGUE["games"][row["origin_game"]]
    code = game["code"]
    if not game["racing_game"] or not set(code) <= set(DEFAULT + named_tracks.MINTED_ORIGIN_GLYPHS):
        return {}, DEFAULT
    return row, code


def has_letter_placements(package):
    if not package or not package["capabilities"]["arcade"]:
        return False
    row, code = _origin(package)
    files = {record["role"]: record["sha256"] for record in package["files"]}
    placement = row.get("letter_placements", {}).get(files["lev"])
    return code == "CNK" and placement is not None and placement["vrm_sha256"] == files["vrm"]


def letters_for_package(package, placed=False):
    row, code = _origin(package)
    lev = package["files"][0]["sha256"]
    if placed or row.get("own_letter_models", {}).get(lev) == code:
        return code
    return DEFAULT


def _origin_item(code):
    first, last = named_tracks.ORIGIN_ITEM_RANGE
    return first <= code <= last


def is_origin_location(code):
    row = named_tracks.block_of_location(code)
    return row is not None and 141 <= row[1] <= 176


class _OptionWorld(NamedTuple):
    game: str
    item_names: frozenset
    location_names: frozenset
    item_name_groups: dict
    location_name_groups: dict


@cache
def legacy_option_world(world):
    """The old alphabet of registered names for options rolled before the plan."""
    from .item_groups import letter_item_names

    from .character_looks import GROUP as LOOK_GROUP, LOOKS

    # Character looks (JL2) are left out the same way: a random name roll or a
    # group draw (Filler, Everything) keeps the alphabet it had before them.
    # The Character Looks group itself stays for YAMLs that name it.
    item_ids = {name: code for name, code in world.item_name_to_id.items()
                if not _origin_item(code) and name not in LOOKS}
    item_names = frozenset(item_ids)
    locations = frozenset(name for name, code in world.location_name_to_id.items() if not is_origin_location(code))
    named_items = [row for row in named_tracks.NAMED_TRACK_ITEM_DATA if not _origin_item(row["code"])]
    item_groups = {group: (members if group == LOOK_GROUP else frozenset(members) - set(LOOKS))
                   for group, members in world.item_name_groups.items()}
    item_groups["Everything"] = item_names
    item_groups["CTR Letters"] = frozenset(letter_item_names(named_items))
    return _OptionWorld(world.game, item_names, locations, item_groups, world.location_name_groups)


def _set_slot_option(options, name, value):
    """The generator may share the rolled option object across multiple slots."""
    option = getattr(options, name)
    if value != option.value:
        option = copy(option)
        option.value = value
        setattr(options, name, option)


def prune_unused_option_names(world):
    """Group expansion may include the reserved letter names for other rooms."""
    plan = world.ctr_content_plan
    locations = {row["location"] for row in plan["checks"]}
    items = {row["item"] for row in plan["items"]["rows"]}
    for field in ("exclude_locations", "priority_locations", "start_location_hints"):
        names = {name for name in getattr(world.options, field).value
                 if not is_origin_location(world.location_name_to_id.get(name))
                 or world.location_name_to_id[name] in locations}
        _set_slot_option(world.options, field, names)
    for field in ("start_hints", "local_items", "non_local_items"):
        names = {name for name in getattr(world.options, field).value
                 if not _origin_item(world.item_name_to_id.get(name, 0))
                 or world.item_name_to_id[name] in items}
        _set_slot_option(world.options, field, names)
    links = world.options.item_links
    if FEATURE not in plan["required_features"] and hasattr(links, "legacy_value"):
        _set_slot_option(world.options, "item_links", links.legacy_value)
    elif hasattr(links, "legacy_value"):
        links.verify_origin_locality(type(world), {world.item_id_to_name[code] for code in items if _origin_item(code)})


def restore_legacy_link_pools(multiworld, world_type):
    """Restore the old registered pool order for links between legacy slots."""
    for group in multiworld.groups.values():
        if group["game"] != world_type.game:
            continue
        worlds = [multiworld.worlds[s] for s in sorted(group["players"])]
        if any(FEATURE in w.ctr_content_plan["required_features"] for w in worlds):
            continue
        links = [link for w in worlds for link in w.options.item_links.value if link["name"] == group["name"]]
        if not links or not any(hasattr(w.options.item_links, "legacy_value") for w in worlds):
            continue
        shared = set(links[0]["item_pool"])
        excluded = set(links[0].get("exclude", ()))
        for link in links[1:]:
            shared &= set(link["item_pool"])
            excluded |= set(link.get("exclude", ()))
        groups = legacy_option_world(world_type).item_name_groups
        # Character looks (JL2): looks the framework already put in this
        # link's pool stay when a member slot allows them.
        from .character_looks import LOOKS, allowed_looks
        enabled = {look for w in worlds for look in allowed_looks(w)}
        pool = set(group["item_pool"]) & set(LOOKS) & enabled
        for name in shared:
            pool |= groups.get(name, {name})
        # The legacy groups leave looks out, so a group name (Filler,
        # Everything) adds the looks a member slot allows.
        for name in shared:
            pool |= set(world_type.item_name_groups.get(name, ())) & set(LOOKS) & enabled
        for name in excluded:
            pool -= groups.get(name, {name})
            pool -= set(world_type.item_name_groups.get(name, ())) & set(LOOKS)
        group["item_pool"] = pool
        group["local_items"] &= pool
        group["non_local_items"] &= pool


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
