"""Start pad activities from the in-game tracker (#375, 0.3.0).

Design: `0.3.0 design - tracker pad start, solo mode, in-game updater (#375
#89 #301) - 2026-10-13` and `2026-09-20 -- Design -- Start pad content from
the in-game tracker`.

ONE OPTION. `tracker_pad_launch` (DefaultOnToggle). On, the native in-game
tracker can start a pad's or boss garage's activities from the hub pause,
under the same gates as the physical pad plus the hub's door Keys. Off, the
tracker stays inspection only. A race or sync host turns it off for everyone.

NO LOGIC. The option creates no location or item and no rule reads it. A
tracker start only reaches places the pad exit's own access rule already
covers: the exit stays in its physical hub region with its hub Key rule
(Regions.py), and native refuses a hub whose door Keys are missing.

WIRE. `ctr_options.tracker_pad_launch` is a JSON Boolean, always emitted on
ordinary and content-plan rooms (schema 18, Contract running section). Native
reads an absent or non-Boolean value as off. Universal Tracker restores it
from the room; an absent key is a pre-#375 room and restores to off.

OFF IS GENERATION-NEUTRAL. Either value takes no random draw, so a seed
generates the same placements with it on or off; only the emitted Boolean
differs.
"""
from typing import Dict

WIRE_KEY = "tracker_pad_launch"


def enabled(world) -> bool:
    """The seed's value, read from the connected room on a Tracker restore.

    The content-plan restore bypasses the ordinary option restorer, so this
    resolves the option the same way `spoiler_items.enabled` does."""
    passthrough = getattr(getattr(world, "multiworld", None), "re_gen_passthrough", {}).get(
        getattr(world, "game", ""))
    if passthrough:
        world.options.tracker_pad_launch.value = int(
            passthrough.get("ctr_options", {}).get(WIRE_KEY, False) is True)
    return bool(world.options.tracker_pad_launch.value)


def fill_slot_data(world) -> Dict[str, object]:
    """The always-emitted wire Boolean."""
    return {WIRE_KEY: enabled(world)}


def restore_slot_data(options, ctr_options) -> None:
    """Universal Tracker restore: absent or not a Boolean is off, as native
    reads it."""
    options.tracker_pad_launch.value = int(ctr_options.get(WIRE_KEY, False) is True)
