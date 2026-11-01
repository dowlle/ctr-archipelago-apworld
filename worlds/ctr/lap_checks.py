"""Lap completion check names (#344), minted in the 0.3.0 id step. Names only;
no seed creates them yet.

WHAT THIS CHECKS. `<Track>: Complete One Lap`: the first accepted lap in any
lap-based race mode on that track, Cup legs included; one check per track
across all its appearances (ruled 2026-10-13 21:37 CEST, #344 answer 1).

WHO OWNS THE SEMANTICS. The apworld owns names, codes and the per-seed subset
(option `lap_completion_checks`, not built yet); native owns the lap crossing
send in game/PlayLevel.c. This class returns an empty per-seed subset.

DATAPACKAGE STABILITY. Retail tracks `35028000 + i` in the canonical retail
order (BOX_TRACKS, the Reach 10 Wumpa order), Cortex Vortex at 35026009 (the
unused slot in its named block), generic custom slots `35028100 + N - 1` for
N in 1..132. Named custom tracks use offset 16 of their named block
(named_tracks.py). Every name registers unconditionally. Approved in the 0.3.0
minting register (ruled 2026-10-13 22:02 CEST).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
from typing import List

from . import destinations
from .custom_check_namespace import CUSTOM_SLOT_COUNT
from .item_boxes import BOX_TRACKS
from .location_class import LocationClass

LAP_RETAIL_CODE_BASE = 35028000
LAP_CORTEX_VORTEX_CODE = 35026009
LAP_CUSTOM_CODE_BASE = 35028100


def lap_name(track: str) -> str:
    return f"{track}: Complete One Lap"


class LapCompletionLocationClass(LocationClass):
    key = "lap_completion"
    display_name = "Lap Completion Checks"
    code_blocks = (LAP_RETAIL_CODE_BASE, 35026000)

    def all_locations(self):
        out = [(lap_name(track), LAP_RETAIL_CODE_BASE + i, track)
               for i, track in enumerate(BOX_TRACKS)]
        out.append((lap_name(destinations.CORTEX_VORTEX), LAP_CORTEX_VORTEX_CODE,
                    destinations.CORTEX_VORTEX))
        out += [(lap_name(destinations.custom_slot_region(slot)), LAP_CUSTOM_CODE_BASE + slot - 1,
                 destinations.custom_slot_region(slot))
                for slot in range(1, CUSTOM_SLOT_COUNT + 1)]
        return out

    def location_name(self, track: str) -> str:
        return lap_name(track)

    def created_location_names(self, options) -> List[str]:
        return []


LAP_COMPLETION_CLASS = LapCompletionLocationClass()
