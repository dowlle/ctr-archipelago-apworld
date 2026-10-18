"""Item Box Locations on content plans (#133 PR 4e).

`box_locations` with `shortcut_knowledge` and `color_boxes_by_item` in a
content-plan seed. The plan's optional `item_boxes` record (feature
`item_boxes_v1`) holds the Shortcut Knowledge tier; it is absent when Item Box
Locations are off, and then no track has a box check, so such a plan keeps its
earlier wire.

WHICH TRACKS HAVE BOX CHECKS.

  * A retail track keeps its frozen box ids and box rules (item_boxes.py): the
    slots 1 to its placed count, minus the slots its Shortcut Knowledge tier
    removes (SK_REQUIRED_TIER), named `<Track>: Item Box N`.
  * A custom track on a named block uses the block's Item Box 1 to 15 offsets
    (20 to 34, named_tracks.py). The seats are the track's own weapon crates:
    the package states how many weapon crates its LEV holds
    (`capabilities.weapon_crates`, measured and checked by native on load) and
    the track gets Item Box 1 to min(weapon_crates, 15). A package that does
    not state the count gets none, because nothing then says the seats exist.
    Native picks the seats with the same spread rule (`seat_indices`).
  * A generic-slot (B+) custom track has no box ids yet, so it has no box
    checks, and native stands no AP box on it. Its weapon crates stay ordinary
    weapon crates. Cortex Vortex has none either, as on the legacy pad track.

ROUTES. A box sits at a place, not at a race type (the 2026-08-06 positioning
ruling), so each box check has one route per mode of its track's entry, in the
pad's mode order, award `box`. The first mode opens with the pad, so a box is
open whenever its pad is ("Its own accessible pad", custom-track spec).

RULES (as on the legacy path, Rules.add_item_box_rules).

  * Retail: BOX_RULES. `Progressive Boost >= n` as the check's `boost` rank
    when Progressive Boost is on, and "one copy of each stat chain" as
    `stats: true` when Progressive Stats is on, both bound to the pad's racer
    lock (the legacy single-racer gate). The Tiger Temple door box (slot 5)
    also needs a door-opener weapon while Itemsanity is on
    (content_global_checks.tiger_temple_door).
  * Custom: the track's finish term F (content_capability.finish_boost) when
    Progressive Boost is on, and no stat term. A box is not a finish check,
    but a track whose lap needs USF has ground behind that jump, and nothing
    measures which crates sit there, so every box takes F: the safe
    direction, as the 2026-10-17 ruling chose for finish checks.

Native re-derives the box identities, names and routes from the plan and its
registry rows (`boxes` per retail row) and refuses any difference; like the
boost rank, it reads `stats` as given (range checks only).
"""
from Options import OptionError

from . import named_tracks
from .item_boxes import BOX_RULES, ITEM_BOX_CLASS, PLACED_COUNTS, SK_REQUIRED_TIER, SLOTS_PER_TRACK

FEATURE = "item_boxes_v1"
KEYS = ("shortcut_knowledge",)
KIND = "box"
AWARD = "box"


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options):
    """The plan's `item_boxes` record from the seed's options; {} when Item
    Box Locations are off."""
    if not options.box_locations.value:
        return {}
    return dict(shortcut_knowledge=int(options.shortcut_knowledge.value))


def check_settings(record, capability=None):
    """Shape and values of a plan's `item_boxes` record. With the capability
    record (#133 PR 4c) present, the two Shortcut Knowledge tiers agree."""
    if not isinstance(record, dict) or set(record) != set(KEYS):
        error("item_boxes must be a mapping of exactly shortcut_knowledge.")
    tier = record["shortcut_knowledge"]
    if type(tier) is not int or tier not in (0, 1, 2):
        error("item_boxes.shortcut_knowledge must be 0, 1 or 2.")
    if capability and capability.get("shortcut_knowledge") != tier:
        error("item_boxes.shortcut_knowledge disagrees with capability.shortcut_knowledge.")
    return record


def crate_count(package):
    """The package's stated weapon crate count, or None when it states none."""
    if not package:
        return None
    return package.get("capabilities", {}).get("weapon_crates")


def seat_indices(crates, slots=SLOTS_PER_TRACK):
    """Which weapon crates, by their order in the LEV instance table, take the
    Item Box seats: min(crates, slots) of them, spread over the whole table
    (seat i is crate floor(i * crates / seats)), so a track with more crates
    than seats keeps ordinary crates between its AP boxes. Native computes the
    same (ap_box_seat_logic.h)."""
    seats = min(crates, slots)
    return [i * crates // seats for i in range(seats)]


def retail_slots(track_name, tier):
    """The 1-based retail box slots a track creates at a Shortcut Knowledge tier."""
    return [slot for slot in range(1, PLACED_COUNTS[track_name] + 1)
            if SK_REQUIRED_TIER.get((track_name, slot), 0) <= tier]


def track_boxes(track, record, package=None):
    """[(slot, location code, display suffix)] of a track's box checks."""
    if not record:
        return []
    if track["origin"] == "retail":
        name = track["display_name"]
        return [(slot, ITEM_BOX_CLASS.slot_code(name, slot), f"Item Box {slot}")
                for slot in retail_slots(name, record["shortcut_knowledge"])]
    if track["origin"] == "custom" and "named_block" in track:
        crates = crate_count(package)
        if not crates:
            return []
        return [(slot, named_tracks.location_code(track["named_block"], f"item_box_{slot}"), f"Item Box {slot}")
                for slot in range(1, len(seat_indices(crates)) + 1)]
    return []


def box_terms(track, slot, capability, package=None):
    """(boost rank, needs stats) of one box check, the legacy box rules with
    their options: a term binds only while the pack that creates its items is
    on."""
    from .content_capability import finish_boost
    capability = capability or {}
    boost_on = bool(capability.get("boost_mode"))
    stats_on = bool(capability.get("stats_mode"))
    if track["origin"] == "retail":
        boost_min, needs_stats = BOX_RULES.get((track["display_name"], slot), (0, False))
        return (boost_min if boost_on else 0), bool(needs_stats and stats_on)
    return (finish_boost(track, capability, package) if boost_on else 0), False
