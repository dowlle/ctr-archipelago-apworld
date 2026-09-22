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
        existing = {loc.address for loc in world.multiworld.get_locations(world.player)}
        return {check["location"]: (_escape_markup(check["display_name"]) if escape_markup else check["display_name"])
                for check in plan["checks"] if check["location"] in existing}
    prefixes = {}
    roles = {role: label for role, label, _region in CUSTOM_DESTINATION_ROLES}
    for track_id, entry in resolved_custom_tracks(world).items():
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
