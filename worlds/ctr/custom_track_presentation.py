"""Seed-local display aliases; never change the registered AP namespace."""

from .custom_track_locations import slot_region
from .custom_tracks import TRACK_DISPLAY_NAMES, resolved_custom_tracks
from .wumpa_checks import CUSTOM_DESTINATION_ROLES, custom_location_name


def _escape_markup(text: str) -> str:
    # UT embeds aliases in Kivy markup. Creator titles are untrusted text.
    return text.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def location_aliases(world, *, escape_markup: bool = True) -> dict[int, str]:
    """UT's supported per-world hook, restricted to this seed's real locations.

    Prefixes are derived from resolved slot/role identities, not a catalogue's
    order. Keep Location.name, address and both global datapackage maps intact.
    Pinned package titles take precedence over the legacy compiled title table.
    Server datapackages request plain text; UT requires escaped Kivy markup.
    """
    plan = getattr(world, "ctr_content_plan", None)
    if plan is not None:
        # A named block's check already carries its real name, so only
        # generic-slot checks get an alias.
        existing = {loc.address: loc.name for loc in world.multiworld.get_locations(world.player)}
        return {check["location"]: (_escape_markup(check["display_name"]) if escape_markup else check["display_name"])
                for check in plan["checks"]
                if check["location"] in existing and existing[check["location"]] != check["display_name"]}
    prefixes = {}
    roles = {role: label for role, label, _region in CUSTOM_DESTINATION_ROLES}
    titles = getattr(world, "custom_track_titles", None)
    for track_id, entry in resolved_custom_tracks(world).items():
        if titles is not None:
            title = titles.get(int(entry["slot"]))
            if title is None:
                continue
        else:
            title = entry.get("title", TRACK_DISPLAY_NAMES.get(track_id, track_id))
        prefixes[f"{slot_region(entry['slot'])}: "] = title
        if entry["replaces"] in roles:
            role_name = custom_location_name(roles[entry["replaces"]])
            prefixes[role_name.removesuffix("Reach 10 Wumpa")] = title
    aliases = {}
    for location in world.multiworld.get_locations(world.player):
        if location.address is None:
            continue
        for prefix, title in prefixes.items():
            if location.name.startswith(prefix):
                text = f"{title}: {location.name[len(prefix):]}"
                aliases[location.address] = _escape_markup(text) if escape_markup else text
                break
    return aliases


def item_aliases(world) -> dict[int, str]:
    """Room titles for this seed's generic custom letter items (#306 B+).

    `Letter C (Custom Track 3)` becomes `Letter C (<room title>)`. Plain text:
    only the room datapackage copy uses it; Universal Tracker has no item alias
    hook. Named blocks need none, their item names are already real.
    """
    from .custom_check_namespace import LETTERS, custom_check_code
    titles = getattr(world, "custom_track_titles", None) or {}
    aliases = {}
    for slot, title in titles.items():
        for variant, letter in enumerate(LETTERS):
            aliases[custom_check_code("letter_item", slot, variant)] = f"Letter {letter} ({title})"
    return aliases


def apply_ut_room_names(world) -> int:
    """Universal Tracker only: rename aliased locations to their room title.

    UT builds Tracker Page lines from `Location.name` plus a bracketed alias,
    so the alias alone shows `Custom Track 1: Trophy Race (Baby T Park: Trophy
    Race)`. Inside UT's regenerated world (generation_is_fake) this renames
    each aliased location to its Kivy-escaped room title, keeps its address,
    and clears the alias map. CTR rules hold Location objects, not names
    (logic_terms.Ref), so they keep working after the rename. Returns the
    number of renamed locations. Never runs in a real generation.
    """
    if not getattr(world.multiworld, "generation_is_fake", False):
        return 0
    aliases = dict(getattr(world, "location_id_to_alias", {}) or {})
    cache = world.multiworld.regions.location_cache[world.player]
    renamed = 0
    for location in list(world.multiworld.get_locations(world.player)):
        title = aliases.get(location.address)
        if title is None or title == location.name or title in cache:
            continue
        region = location.parent_region
        region.locations.remove(location)
        cache.pop(location.name, None)
        location.name = title
        region.locations.append(location)
        renamed += 1
    world.location_id_to_alias = {}
    return renamed
