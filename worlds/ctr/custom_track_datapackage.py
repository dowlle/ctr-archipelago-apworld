"""Room-local custom track labels for an unmodified Archipelago server.

Locations take the track's room title, and since #306 B+ so do the generic
custom letter items (`Letter C (Custom Track 1)` -> `Letter C (Baby T Park)`).

Datapackages are per game, not per player. Conflicting aliases therefore name
every owner explicitly. Never pick one player's track for everybody, move an
address, or mutate the registered package shared by concurrent generations.
"""
from collections import Counter, defaultdict
from copy import deepcopy

from worlds.AutoWorld import data_package_checksum

from .custom_track_presentation import item_aliases, location_aliases


def _relabel(canonical, owners, changed, player_name, kind="location"):
    """{code: label} with conflicting per-player labels combined and every
    label unique, so the reverse name->ID map stays bijective."""
    labels = dict(canonical)
    for code in sorted(changed):
        entries = owners[code]
        if len({label for _, label in entries}) == 1:
            labels[code] = entries[0][1]
        else:
            # Player number also disambiguates identical display names.
            labels[code] = " / ".join(
                f"{label} ({player_name[player]}, P{player})"
                for player, label in entries)

    # A title can equal another title or even a registered retail name. Keep
    # the reverse name->ID map bijective, including deliberately crafted text.
    counts = Counter(labels.values())
    reserved = set(labels.values()) | set(canonical.values())
    for code in sorted(changed):
        label = labels[code]
        if counts[label] > 1:
            candidate = f"{label} [{kind} {code}]"
            while candidate in reserved:
                candidate += "*"
            labels[code] = candidate
            reserved.add(candidate)
    return labels


def _owned_item_codes(multiworld, player):
    """Item codes this player's items carry anywhere in the room."""
    codes = set()
    for location in multiworld.get_locations():
        item = location.item
        if item is not None and item.player == player and item.code is not None:
            codes.add(item.code)
    for item in multiworld.precollected_items.get(player, ()):
        if item.code is not None:
            codes.add(item.code)
    return codes


def embed_track_names(multiworld, multidata, game: str) -> None:
    package = multidata["datapackage"][game]
    canonical = {code: name for name, code in package["location_name_to_id"].items()}
    canonical_items = {code: name for name, code in package.get("item_name_to_id", {}).items()}
    owners = defaultdict(list)
    item_owners = defaultdict(list)
    changed = set()
    changed_items = set()
    for player in sorted(multiworld.player_ids):
        world = multiworld.worlds[player]
        if world.game != game:
            continue
        aliases = location_aliases(world, escape_markup=False)
        # Include actual users without an alias too (e.g. legacy role checks).
        for location in multiworld.get_locations(player):
            code = location.address
            if code not in canonical:
                continue
            label = aliases.get(code, canonical[code])
            owners[code].append((player, label))
            if label != canonical[code]:
                changed.add(code)
        # #306 B+: generic custom letter items take the room title too.
        renamed_items = item_aliases(world)
        if renamed_items:
            for code in sorted(_owned_item_codes(multiworld, player)):
                if code in renamed_items and code in canonical_items:
                    item_owners[code].append((player, renamed_items[code]))
                    if renamed_items[code] != canonical_items[code]:
                        changed_items.add(code)
    if not changed and not changed_items:
        return

    result = deepcopy(package)
    if changed:
        labels = _relabel(canonical, owners, changed, multiworld.player_name)
        result["location_name_to_id"] = dict(sorted((name, code) for code, name in labels.items()))
        renames = {canonical[code]: labels[code] for code in changed}
        result["location_name_groups"] = {
            group: sorted(renames.get(name, name) for name in names)
            for group, names in sorted(result.get("location_name_groups", {}).items())
        }
    if changed_items:
        labels = _relabel(canonical_items, item_owners, changed_items, multiworld.player_name, "item")
        result["item_name_to_id"] = dict(sorted((name, code) for code, name in labels.items()))
        renames = {canonical_items[code]: labels[code] for code in changed_items}
        result["item_name_groups"] = {
            group: sorted(renames.get(name, name) for name in names)
            for group, names in sorted(result.get("item_name_groups", {}).items())
        }
    result.pop("checksum", None)
    result = dict(sorted(result.items()))
    result["checksum"] = data_package_checksum(result)
    multidata["datapackage"][game] = result
