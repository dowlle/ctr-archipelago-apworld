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


def _relabel(canonical, owners, changed, player_name, kind, reserved_names):
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
    reserved = set(labels.values()) | reserved_names
    for code in sorted(changed):
        label = labels[code]
        if counts[label] > 1 or (label != canonical[code] and label in reserved_names):
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
    ctr_players = []
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
        ctr_players.append((player, item_aliases(world)))
    # Record every owner, canonical name when there is no alias, so a shared
    # generic code is never labelled for a player who has no title. Needed only
    # when some player renames items at all.
    if any(renamed for _player, renamed in ctr_players):
        for player, renamed_items in ctr_players:
            for code in sorted(_owned_item_codes(multiworld, player)):
                if code in canonical_items:
                    label = renamed_items.get(code, canonical_items[code])
                    item_owners[code].append((player, label))
                    if label != canonical_items[code]:
                        changed_items.add(code)
    if not changed and not changed_items:
        return

    result = deepcopy(package)
    # Old canonical labels must remain available as hint groups after relabeling.
    reserved_names = set(canonical.values()) | set(canonical_items.values())
    reserved_names.update(package.get("location_name_groups", {}))
    reserved_names.update(package.get("item_name_groups", {}))
    for kind, original, entries, renamed_codes in (
        ("location", canonical, owners, changed),
        ("item", canonical_items, item_owners, changed_items),
    ):
        if not renamed_codes:
            continue
        labels = _relabel(original, entries, renamed_codes, multiworld.player_name, kind, reserved_names)
        result[f"{kind}_name_to_id"] = dict(sorted((name, code) for code, name in labels.items()))
        renames = {original[code]: labels[code] for code in renamed_codes}
        groups_key = f"{kind}_name_groups"
        groups = {
            group: sorted(renames.get(name, name) for name in names)
            for group, names in result.get(groups_key, {}).items()
        }
        groups.update((old, [new]) for old, new in renames.items() if old != new)
        result[groups_key] = dict(sorted(groups.items()))
    result.pop("checksum", None)
    result = dict(sorted(result.items()))
    result["checksum"] = data_package_checksum(result)
    multidata["datapackage"][game] = result
