"""Seed-local display aliases; never change the registered AP namespace."""


def _escape_markup(text: str) -> str:
    # UT embeds aliases in Kivy markup. Creator titles are untrusted text.
    return text.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def location_aliases(world, *, escape_markup: bool = True) -> dict[int, str]:
    """UT's supported per-world hook, restricted to this seed's real locations.

    The plan's checks carry their display names. Keep Location.name, address
    and both global datapackage maps intact. Server datapackages request
    plain text; UT requires escaped Kivy markup.
    """
    plan = world.ctr_content_plan
    # A named block's check already carries its real name, so only
    # generic-slot checks get an alias.
    existing = {loc.address: loc.name for loc in world.multiworld.get_locations(world.player)}
    return {check["location"]: (_escape_markup(check["display_name"]) if escape_markup else check["display_name"])
            for check in plan["checks"]
            if check["location"] in existing and existing[check["location"]] != check["display_name"]}


def item_aliases(world) -> dict[int, str]:
    """Room titles for this seed's generic custom letter items (#306 B+).

    `Letter C (Custom Track 3)` becomes `Letter C (<room title>)`. Plain text:
    only the room datapackage copy uses it; Universal Tracker has no item alias
    hook. Named blocks need none, their item names are already real.
    """
    from .custom_check_namespace import LETTERS, custom_check_code
    # Content plans (#133 PR 3b): the generic-slot letter items the plan
    # pools take their track's room title.
    from .content_plan import plan_letter_items
    plan = world.ctr_content_plan
    pooled = plan_letter_items(plan)
    aliases = {}
    for track in plan["tracks"]:
        if track["origin"] != "custom" or "named_block" in track:
            continue
        for variant, letter in enumerate(LETTERS):
            code = custom_check_code("letter_item", track["custom_slot"], variant)
            if code in pooled:
                aliases[code] = f"Letter {letter} ({track.get('room_title', track['display_name'])})"
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

    UT also resolves the location of every received item through the world's
    `location_id_to_name` and then `get_location(name)`. The class map still
    gives the generic name, which no longer exists in this world, and UT
    v0.2.x then drops the item from its state, so an item found on a renamed
    check went missing from the tracker's logic. This world instance therefore
    gets its own copies of both maps with the renamed entries. The class maps
    and the datapackage are unchanged, and the generic names still resolve in
    `location_name_to_id`.
    """
    if not getattr(world.multiworld, "generation_is_fake", False):
        return 0
    aliases = dict(getattr(world, "location_id_to_alias", {}) or {})
    cache = world.multiworld.regions.location_cache[world.player]
    id_to_name = dict(world.location_id_to_name)
    name_to_id = dict(world.location_name_to_id)
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
        id_to_name[location.address] = title
        name_to_id[title] = location.address
        renamed += 1
    world.location_id_to_alias = {}
    if renamed:
        world.location_id_to_name = id_to_name
        world.location_name_to_id = name_to_id
    return renamed
