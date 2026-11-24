"""Cortex Vortex as a pad track: its frozen names, ids and letter items, and the
option readers the location classes still share (design 2026-09-13, contract
frozen 10:12 CEST).

One generator row 12 deleted cortex_vortex_track.py with the original
generator: the dropped-destination draw, the letter draw, the wire block and
the Universal Tracker restore. The content plan places Cortex Vortex itself
(`cortex_vortex_track: off / in_pool / own_pad`). What stays here moved
verbatim.

DATAPACKAGE STABILITY. The location class claims the block 35026000 and
registers its eight names UNCONDITIONALLY: Trophy 35026000, Sapphire/Gold/
Platinum Time Trial 35026001-003, CTR Token Challenge 35026004 and Letter
C/T/R 35026006-008. 35026005 (`Cortex Vortex: Relic Race Perfect`) and
35026009 (`Cortex Vortex: Complete One Lap`) were minted by the 0.3.0 id step
in custom_fallback_families.py and lap_checks.py; this class does not own
them. The five podium rungs 35026010-014 ride the podium class. The three
letter ITEMS 35010200-202 live in `LETTER_ITEM_DATA` below, outside the
positional `data/items.json` table. The Wumpa check reuses 35016121.

FROZEN-NAME WARNING. These names were approved through the considered
datapackage unfreeze of 2026-09-13. They are permanent; their ids never move.
"""
import json
import pkgutil
from functools import lru_cache
from typing import Dict, Optional, Tuple

from BaseClasses import ItemClassification

from . import destinations
from .location_class import LocationClass

CORTEX_VORTEX = destinations.CORTEX_VORTEX
CORTEX_TRACK_KEY = "cortex-vortex"
#: The bundled Cortex Vortex is a merged mode build (CV1, 2026-11-24), like a
#: package with `relic_files`: Saphi 1.1.5 is the main pair (crates, CTR
#: letters, Arcade grid) and Saphi 1.1.6 the relic pair (the 100 time crates),
#: served by native only in a Relic Race. Native pins the same four digests
#: (include/platform/native_cortex_asset_pins.h).
CORTEX_LEV_SHA256 = "cabeba054ad1416a67ab2af2dcaad46e8ded71213319035750377b244fd9aa1a"
CORTEX_VRM_SHA256 = "a81cb4aa483d884b4d6b616bb12e0e8778439c1f4075d79b3807682a19dbe914"
CORTEX_RELIC_LEV_SHA256 = "08afeda329194b737014f29324d0930bafbd0b940d02e72b29b37b0e9cded911"
CORTEX_RELIC_VRM_SHA256 = "9e15a816e547b8a3b3d913a1767d58b1866e9b9d643f11cd3411381da6255500"
#: The all-in-one build bundled before CV1 (the A6-15b crate rulings were
#: made on it). Its weapon and Wumpa crates are 1.1.5's, at the same places in
#: the same instance order, so the rulings carry by position unchanged. Rooms
#: whose sanity rows name it keep restoring and admitting.
CORTEX_LEGACY_LEV_SHA256 = "4e3a2daf56c67be3ac645d3bb5375e516c828a0bca24c35ac69b3366c466fe13"
CORTEX_SANITY_PINS = (CORTEX_LEV_SHA256, CORTEX_LEGACY_LEV_SHA256)


def bundled_copy(package):
    """True for a registered Cortex Vortex key with the exact bundled pair."""
    return (destinations.canonical_track_key(package["content_id"]) == CORTEX_TRACK_KEY
            and package["files"][0]["sha256"] == CORTEX_LEV_SHA256
            and package["files"][1]["sha256"] == CORTEX_VRM_SHA256)


#: Virtual destination ID, outside {0..27, 100..104}.
DESTINATION_ID = destinations.CORTEX_VORTEX_LEVEL_ID


TROPHY_CODE = 35026000


RELIC_CODES = (35026001, 35026002, 35026003)


CTR_TOKEN_CODE = 35026004


#: `Cortex Vortex: Relic Race Perfect`, registered by
#: custom_fallback_families.CustomRelicLocationClass (0.3.0 id step).
RELIC_PERFECT_RESERVED_CODE = 35026005


LETTER_CODES = (35026006, 35026007, 35026008)


#: The five podium rungs, registered by the podium class in SLOT_ORDER.
PODIUM_CODE_BASE = 35026010


LETTER_ITEM_CODES = (35010200, 35010201, 35010202)


LETTERS = ("C", "T", "R")


RELIC_TIER_LABELS = ("Sapphire", "Gold", "Platinum")


TROPHY_NAME = f"{CORTEX_VORTEX}: Trophy Race"


CTR_TOKEN_NAME = f"{CORTEX_VORTEX}: CTR Token Challenge"


def relic_name(tier_label: str) -> str:
    return f"{CORTEX_VORTEX}: {tier_label} Time Trial"


def letter_location_name(letter: str) -> str:
    return f"{CORTEX_VORTEX}: Letter {letter}"


def letter_item_name(letter: str) -> str:
    """Same convention as `lettersanity.item_name`."""
    return f"Letter {letter} ({CORTEX_VORTEX})"


#: The three letter items, registered beside the positional item table.
LETTER_ITEM_DATA = tuple({
    "name": letter_item_name(letter),
    "code": code,
    "count": 0,
    "classification": ItemClassification.progression,
} for letter, code in zip(LETTERS, LETTER_ITEM_CODES))


@lru_cache(maxsize=1)
def destination_table() -> Dict[int, Tuple[str, str, str]]:
    """{destination LevelID: (pad exit name, destination region, kind)} for
    the 27 retail destinations, from data/warp_pad_ids.json and the pad-exit
    targets in data/world.json (never retyped: a cup pad's region is
    "<Colour> Gem Cup", not its pad name minus " Warp Pad")."""
    pads = json.loads(pkgutil.get_data(
        __package__, "data/warp_pad_ids.json").decode("utf-8"))["pads"]
    world = json.loads(pkgutil.get_data(
        __package__, "data/world.json").decode("utf-8"))
    targets = {ex["name"]: ex["target"]
               for region in world["regions"]
               for ex in region.get("exits", []) if ex["name"] in pads}
    return {meta["level_id"]: (pad, targets[pad], meta["kind"])
            for pad, meta in pads.items()}


def track_key(pad_name: str) -> str:
    """HUB_STATIC / warp_pad_logic track key of a pad exit ("Red Cup")."""
    return pad_name[: -len(" Warp Pad")]


def track_on(options) -> bool:
    toggle = getattr(options, "cortex_vortex_track", None)
    if toggle is None:
        return False
    try:
        return int(toggle.value) == 1
    except (AttributeError, TypeError, ValueError):
        return False


def dropped_level_id(options) -> Optional[int]:
    if not track_on(options):
        return None
    return getattr(options, "_cortex_vortex_dropped", None)


def dropped_region(options) -> Optional[str]:
    lid = dropped_level_id(options)
    return None if lid is None else destination_table()[lid][1]


def dropped_pad(options) -> Optional[str]:
    lid = dropped_level_id(options)
    return None if lid is None else destination_table()[lid][0]


def dropped_track(options) -> Optional[str]:
    """The dropped destination's track key, which is also its region name for
    every race, trial and crystal destination (the per-track families only ever
    key on those)."""
    pad = dropped_pad(options)
    return None if pad is None else track_key(pad)


def selected_letters(options) -> Tuple[str, ...]:
    return tuple(getattr(options, "_lettersanity_selected", {}).get(
        CORTEX_VORTEX, ()))


class CortexVortexTrackLocationClass(LocationClass):
    """Trophy, relic tiers, CTR Token Challenge and letters of the pad track."""

    key = "cortex_vortex_track"
    display_name = "Cortex Vortex Track"
    code_blocks = (TROPHY_CODE,)

    def all_locations(self):
        rows = [(TROPHY_NAME, TROPHY_CODE, CORTEX_VORTEX)]
        rows += [(relic_name(tier), code, CORTEX_VORTEX)
                 for tier, code in zip(RELIC_TIER_LABELS, RELIC_CODES)]
        rows.append((CTR_TOKEN_NAME, CTR_TOKEN_CODE, CORTEX_VORTEX))
        rows += [(letter_location_name(letter), code, CORTEX_VORTEX)
                 for letter, code in zip(LETTERS, LETTER_CODES)]
        return rows

    def location_name(self, kind: str, letter: str = "") -> str:
        if kind == "trophy":
            return TROPHY_NAME
        if kind == "ctr_token":
            return CTR_TOKEN_NAME
        if kind == "letter":
            return letter_location_name(letter)
        return relic_name(kind)

    def created_location_names(self, options):
        """Trophy Race, CTR Token Challenge and the selected letter checks.

        The three Time Trials are NOT listed: they belong to the relic-tier
        draw like every other Time Trial (`relic_tiers.draw_relic_tier_keep`,
        read by Regions), so listing them here would count them twice in the
        rung sizer's supply. The podium rungs belong to the podium class.
        """
        if not track_on(options):
            return []
        names = [TROPHY_NAME, CTR_TOKEN_NAME]
        mode = int(getattr(getattr(options, "lettersanity", None), "value", 0) or 0)
        if mode in (1, 2):
            chosen = selected_letters(options)
            names += [letter_location_name(letter) for letter in LETTERS
                      if letter in chosen]
        return names


CORTEX_VORTEX_TRACK_CLASS = CortexVortexTrackLocationClass()
