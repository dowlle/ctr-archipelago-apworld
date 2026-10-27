"""One identity per legacy custom track (#133, ruled 2026-10-15).

A legacy `custom_tracks` entry whose track id has a named block (#306, path C)
uses that block for every check and item it creates: Trophy Race, the podium
rungs, the CTR Token Challenge, the letters and Reach 10 Wumpa. Its region and
its location names use the block's frozen `ap_name` (`Baby T Park: Trophy
Race`), so the room, Universal Tracker, hints and the spoiler show the real
name without a room rewrite. An entry without a block keeps the generic slot
ids (`Custom Track N`, path B+) and its room title.

Every caller asks this module for a name or a code instead of computing one
from the slot, so the two paths cannot drift. `normalize_custom_tracks` sets
`named_block` and `ap_name` on a named entry; nothing else does.
"""
from typing import Dict, List, Mapping, Optional

from . import destinations, named_tracks
from .custom_check_namespace import LETTERS, custom_check_code, custom_check_name
from .custom_track_locations import CUSTOM_TRACK_LOCATION_CLASS
from .podium import SLOT_ORDER

_LETTER_KEYS = ("letter_c", "letter_t", "letter_r")


def named_block(entry: Mapping) -> Optional[int]:
    """The entry's named block index, or None on the generic path."""
    return entry.get("named_block")


def track_label(entry: Mapping) -> str:
    """Region name and location-name stem: the frozen `ap_name` of a named
    block, else `Custom Track N`."""
    if named_block(entry) is not None:
        return entry["ap_name"]
    return destinations.custom_slot_region(int(entry["slot"]))


def location_name(entry: Mapping, key: str) -> str:
    """`key` is `trophy` or a podium rung key from `podium.SLOT_ORDER`."""
    if named_block(entry) is not None:
        return named_tracks.location_name(entry["ap_name"], key)
    return CUSTOM_TRACK_LOCATION_CLASS.location_name(int(entry["slot"]), key)


def location_code(entry: Mapping, key: str) -> int:
    if named_block(entry) is not None:
        return named_tracks.location_code(entry["named_block"], key)
    return CUSTOM_TRACK_LOCATION_CLASS.code_for(int(entry["slot"]), key)


def podium_codes(entry: Mapping, created_keys) -> List[int]:
    """The five rung codes in `SLOT_ORDER`, -1 for a rung this seed lacks."""
    created = set(created_keys)
    return [location_code(entry, key) if key in created else -1 for key in SLOT_ORDER]


def ctr_name(entry: Mapping) -> str:
    if named_block(entry) is not None:
        return named_tracks.location_name(entry["ap_name"], "ctr_token")
    return custom_check_name("ctr_location", int(entry["slot"]))


def ctr_code(entry: Mapping) -> int:
    if named_block(entry) is not None:
        return named_tracks.location_code(entry["named_block"], "ctr_token")
    return custom_check_code("ctr_location", int(entry["slot"]))


def letter_location_name(entry: Mapping, letter_index: int) -> str:
    if named_block(entry) is not None:
        return named_tracks.location_name(entry["ap_name"], _LETTER_KEYS[letter_index])
    return custom_check_name("letter_location", int(entry["slot"]), letter_index)


def letter_location_code(entry: Mapping, letter_index: int) -> int:
    if named_block(entry) is not None:
        return named_tracks.location_code(entry["named_block"], _LETTER_KEYS[letter_index])
    return custom_check_code("letter_location", int(entry["slot"]), letter_index)


def letter_item_name(entry: Mapping, letter_index: int) -> str:
    if named_block(entry) is not None:
        return named_tracks.item_name(entry["ap_name"], _LETTER_KEYS[letter_index])
    return custom_check_name("letter_item", int(entry["slot"]), letter_index)


def letter_item_code(entry: Mapping, letter_index: int) -> int:
    if named_block(entry) is not None:
        return named_tracks.item_code(entry["named_block"], _LETTER_KEYS[letter_index])
    return custom_check_code("letter_item", int(entry["slot"]), letter_index)


def wumpa_name(entry: Mapping) -> Optional[str]:
    """The named block's Reach 10 Wumpa name; None on the generic path, where
    the check stays on its destination-role identity (wumpa_checks)."""
    if named_block(entry) is None:
        return None
    return named_tracks.location_name(entry["ap_name"], "wumpa")


def wumpa_code(entry: Mapping) -> Optional[int]:
    if named_block(entry) is None:
        return None
    return named_tracks.location_code(entry["named_block"], "wumpa")


def entries_by_slot(options) -> Dict[int, Mapping]:
    """{slot: normalized entry} for this seed's legacy descriptor, or {}.

    Read from the option value through the option validator, the same way
    `wumpa_checks` reads it, so location classes that only see options agree
    with `world.custom_tracks`. Universal Tracker restores the option value
    from the wire before any of them run."""
    raw = getattr(getattr(options, "custom_tracks", None), "value", None)
    if not raw or not isinstance(raw, Mapping):
        return {}
    from .custom_tracks import normalize_custom_tracks
    return {int(entry["slot"]): entry for entry in normalize_custom_tracks(raw).values()}


def named_slots(options) -> Dict[int, Mapping]:
    """{slot: entry} for the entries on a named block."""
    return {slot: entry for slot, entry in entries_by_slot(options).items()
            if named_block(entry) is not None}


def is_custom_label(world, track: str) -> bool:
    """Whether `track` is the region name of one of this seed's custom tracks."""
    return any(track_label(entry) == track
               for entry in (getattr(world, "custom_tracks", None) or {}).values())


def created_letter_location_names(options) -> List[str]:
    """Every custom letter location this seed creates, generic and named."""
    selected = getattr(options, "_custom_lettersanity_selected", {}) or {}
    if options is None or int(options.lettersanity.value) not in (1, 2) or not selected:
        return []
    entries = entries_by_slot(options)
    return [letter_location_name(entries[slot], LETTERS.index(letter))
            for slot, chosen in sorted(selected.items()) for letter in chosen]


def created_named_location_names(options) -> List[str]:
    """The named-block locations the legacy path creates this seed."""
    entries = named_slots(options)
    if not entries:
        return []
    from .podium import created_rung_keys_from_options
    from .wumpa_checks import WUMPA_PER_TRACK, _mode as _wumpa_mode, eligible_custom_roles
    rungs = created_rung_keys_from_options(options)
    admitted = set(getattr(options, "_custom_ctr_admitted_slots", ()) or ())
    selected = getattr(options, "_custom_lettersanity_selected", {}) or {}
    letters_created = int(options.lettersanity.value) in (1, 2)
    out = []
    for slot, entry in sorted(entries.items()):
        out.append(location_name(entry, "trophy"))
        out.extend(location_name(entry, rung) for rung in rungs)
        if letters_created:
            out.extend(letter_location_name(entry, LETTERS.index(letter))
                       for letter in selected.get(slot, ()))
        if slot in admitted:
            out.append(ctr_name(entry))
    if _wumpa_mode(options) == WUMPA_PER_TRACK:
        out.extend(wumpa_name(entry) for _role, _label, _region, entry
                   in eligible_custom_roles(options) if named_block(entry) is not None)
    # #344: a named track's Complete One Lap, once create_regions made it.
    from .lap_checks import named_location_names
    out.extend(named_location_names(options))
    return out


def created_named_item_names(options) -> List[str]:
    """The named-block letter items the legacy path pools this seed."""
    entries = named_slots(options)
    if not entries or int(options.lettersanity.value) not in (2, 3):
        return []
    selected = getattr(options, "_custom_lettersanity_selected", {}) or {}
    return [letter_item_name(entries[slot], LETTERS.index(letter))
            for slot, chosen in sorted(selected.items()) if slot in entries
            for letter in chosen]
