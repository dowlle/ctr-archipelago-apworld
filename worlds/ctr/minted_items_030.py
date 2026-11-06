"""Item names minted in the 0.3.0 id step. Feature modules own their creation.

  * `Reserve Top-Up` (#451), filler: adds 8192 raw reserve units (about 25% of
    the positive reserve range) and may cross into Saffi fire (ruled
    2026-10-13 21:19 CEST).
  * `Warp Pad Preview` and `AP Box Colours` (#459), useful: each restores one
    display hidden by `spoiler_items` (answer 3, option A).
  * `Clocked Out` (#455) and `Reverse Camera` (#248), traps with the stable
    `trap_weights` keys `clocked_out` and `reverse_camera` (rulings 2026-10-13
    15:09 and 21:56 CEST).
  * The alpha3 data package (ruled 2026-11-06): `Always Jumping`,
    `No Drifting`, `Rival Surge`, `Mud Season`, `Limp Mode`, `Stuck Steering`
    and `Wumpa Leak`, traps at 35010208..35010214, native AP_TrapEffect 22..28.

The ids continue the positional item index after the Cortex Vortex letters
(35010200..35010202). Like those letters they live outside data/items.json,
which stays the closed 0..199 table. Every entry has count 0, so the item pool
is unchanged until a feature PR adds copies.

Clocked Out is now active in traps.TRAP_REGISTRY (#455); Reverse Camera waits
for its feature implementation. Active rows appear in schema-18
`trap_identities` and the buildable draw. Their
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
    # The alpha3 data package (ruled 2026-11-06): seven traps.
    ("Always Jumping", 35010208, ItemClassification.trap),
    ("No Drifting", 35010209, ItemClassification.trap),
    ("Rival Surge", 35010210, ItemClassification.trap),
    ("Mud Season", 35010211, ItemClassification.trap),
    ("Limp Mode", 35010212, ItemClassification.trap),
    ("Stuck Steering", 35010213, ItemClassification.trap),
    ("Wumpa Leak", 35010214, ItemClassification.trap),
)
#: Stable `trap_weights` keys the trap feature PRs will register.
MINTED_TRAP_KEYS = {"Clocked Out": "clocked_out", "Reverse Camera": "reverse_camera",
                    "Always Jumping": "always_jumping", "No Drifting": "no_drifting",
                    "Rival Surge": "rival_surge", "Mud Season": "mud_season",
                    "Limp Mode": "limp_mode", "Stuck Steering": "stuck_steering",
                    "Wumpa Leak": "wumpa_leak"}
MINTED_TRAP_ITEM_NAMES = tuple(MINTED_TRAP_KEYS)

ITEM_DATA = tuple({"name": name, "code": code, "count": 0, "classification": cls}
                  for name, code, cls in MINTED_ITEMS_030)
