"""Frozen generic Archipelago identities for custom-track race checks.

Custom package titles are mutable community metadata, while Archipelago
location names are permanent datapackage identities.  The ruled model therefore
registers 32 role-agnostic slots (one per destination surface) and lets slot
data map each created slot to its package and display title.

This Alpha6 slice creates the geometry-independent race family only: one
Trophy Race check plus the same five creatable podium rungs used by retail
trophy races.  All 32 x 6 names are registered unconditionally; a seed creates
only the slots occupied by selected packages and only the podium rungs enabled
by that seed's normal podium options.
"""
from typing import List, Mapping

from .location_class import LocationClass
from .podium import SLOT_ORDER, created_rung_keys_from_options


CUSTOM_TRACK_SLOT_COUNT = 32
CUSTOM_TROPHY_CODE_BASE = 35016300
CUSTOM_PODIUM_CODE_BASE = 35016400

_RUNG_SUFFIX = {
    "held_1st": "Held 1st",
    "held_3rd": "Held 3rd",
    "held_5th": "Held 5th",
    "finish_podium": "Finish on Podium",
    "finish_any": "Finish (Any Position)",
}


def slot_region(slot: int) -> str:
    return f"Custom Track {slot}"


def slot_for_track_id(tracks: Mapping[str, Mapping], track_id: str) -> int:
    """Stable 1-based generic slot for one selected package.

    Mapping order is deliberately irrelevant: sorting ids means two equivalent
    YAML mappings cannot change datapackage identities merely by reordering
    their keys.  Package placement RNG, when added, remains a separate decision.
    """
    return sorted(tracks).index(track_id) + 1


class CustomTrackLocationClass(LocationClass):
    key = "custom_track_race"
    display_name = "Custom Track Race Checks"
    # Podium codes span 35016400..35016559, hence both hundred blocks.
    code_blocks = (CUSTOM_TROPHY_CODE_BASE,
                   CUSTOM_PODIUM_CODE_BASE,
                   CUSTOM_PODIUM_CODE_BASE + 100)

    def trophy_name(self, slot: int) -> str:
        return f"{slot_region(slot)}: Trophy Race"

    def location_name(self, slot: int, rung_key: str = "trophy") -> str:
        if rung_key == "trophy":
            return self.trophy_name(slot)
        return f"{slot_region(slot)}: {_RUNG_SUFFIX[rung_key]}"

    def all_locations(self):
        out = []
        for slot in range(1, CUSTOM_TRACK_SLOT_COUNT + 1):
            region = slot_region(slot)
            out.append((self.trophy_name(slot),
                        CUSTOM_TROPHY_CODE_BASE + slot - 1,
                        region))
            for rung_index, rung_key in enumerate(SLOT_ORDER):
                out.append((self.location_name(slot, rung_key),
                            CUSTOM_PODIUM_CODE_BASE + (slot - 1) * len(SLOT_ORDER)
                            + rung_index,
                            region))
        return out

    def created_location_names(self, options) -> List[str]:
        if options is None:
            return []
        raw = getattr(getattr(options, "custom_tracks", None), "value", {}) or {}
        if not isinstance(raw, Mapping):
            return []
        rungs = created_rung_keys_from_options(options)
        out = []
        for slot, _track_id in enumerate(sorted(raw), start=1):
            if slot > CUSTOM_TRACK_SLOT_COUNT:
                break
            out.append(self.trophy_name(slot))
            out.extend(self.location_name(slot, rung) for rung in rungs)
        return out

    def slot_codes(self, slot: int, created_keys) -> list:
        created = set(created_keys)
        return [self.code_for(slot, key) if key in created else -1
                for key in SLOT_ORDER]


CUSTOM_TRACK_LOCATION_CLASS = CustomTrackLocationClass()
