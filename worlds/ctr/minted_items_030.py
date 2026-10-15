"""Item names minted in the 0.3.0 id step. Names only; no seed creates them yet.

  * `Reserve Top-Up` (#451), filler: adds 983 raw reserve units and may cross
    into Saffi fire (ruled 2026-10-13 21:19 CEST).
  * `Warp Pad Preview` and `AP Box Colours` (#459), useful: each restores one
    display hidden by `spoiler_items` (answer 3, option A).
  * `Clocked Out` (#455) and `Reverse Camera` (#248), traps with the stable
    `trap_weights` keys `clocked_out` and `reverse_camera` (rulings 2026-10-13
    15:09 and 21:56 CEST).

The ids continue the positional item index after the Cortex Vortex letters
(35010200..35010202). Like those letters they live outside data/items.json,
which stays the closed 0..199 table. Every entry has count 0, so the item pool
is unchanged until a feature PR adds copies.

The two traps are NOT in traps.TRAP_REGISTRY yet: a registry row would put them
in every schema-18 `trap_identities` block and in the buildable draw. Their
feature PRs append the registry row, the native enum value and the shared
fixture row together, as the slot_data Contract's trap rules require. They are
in the `Traps` item group now, because item groups are part of the checksummed
datapackage.

FROZEN-NAME WARNING: once released these names and ids are permanent.
"""
from typing import Tuple

from BaseClasses import ItemClassification

#: (name, code, classification). APPEND ONLY.
MINTED_ITEMS_030: Tuple[Tuple[str, int, ItemClassification], ...] = (
    ("Reserve Top-Up", 35010203, ItemClassification.filler),
    ("Warp Pad Preview", 35010204, ItemClassification.useful),
    ("AP Box Colours", 35010205, ItemClassification.useful),
    ("Clocked Out", 35010206, ItemClassification.trap),
    ("Reverse Camera", 35010207, ItemClassification.trap),
)
#: Stable `trap_weights` keys the trap feature PRs will register.
MINTED_TRAP_KEYS = {"Clocked Out": "clocked_out", "Reverse Camera": "reverse_camera"}
MINTED_TRAP_ITEM_NAMES = tuple(MINTED_TRAP_KEYS)

ITEM_DATA = tuple({"name": name, "code": code, "count": 0, "classification": cls}
                  for name, code, cls in MINTED_ITEMS_030)
