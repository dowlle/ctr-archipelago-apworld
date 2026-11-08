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
    (20 to 34, named_tracks.py); a generic-slot track uses its reserved
    Custom Track N box codes. The seats are the track's own weapon crates:
    the package states how many weapon crates its LEV holds
    (`capabilities.weapon_crates`, measured and checked by native on load) and
    the track gets Item Box 1 to min(weapon_crates, 15). A package that does
    not state the count gets none, because nothing then says the seats exist.
    Native picks the seats with the same spread rule (`seat_indices`).
  * Cortex Vortex has none, as on the legacy pad track.

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

HAND-PLACED SPOTS (A3-14, ruled 2026-11-06, box_spots.py). A track with a
spot file (all 18 retail tracks, and a named custom track whose LEV the file
pins) takes its boxes from the file instead: the record's `spot_sets` holds,
per track id, the file digest, the eligible pool and the picked numbers (all
when 15 or fewer), and each box check carries its `spot` (number, position,
angle) so the client stands it there. Its terms are the spot's own fields:
`needs` as the boost rank, a hard `shortcut` as the stat term; on a custom
track they replace the finish term F, and no weapon crate is hidden. A track
without a file keeps the rules above. A record without `spot_sets` (a seed from
before A3-14) keeps them for every track, and a record without a set for a
named custom track (a seed from before that track's file shipped, A3-45) keeps
them for that track.

Native re-derives the box identities, names and routes from the plan and its
registry rows (`boxes` per retail row, or the spot numbers) and refuses any
difference; like the boost rank, it reads `stats` and `spot` as given (range
checks only).
"""
import json

from Options import OptionError

from . import box_spots, named_tracks, crate_exclusions
from .custom_fallback_families import CUSTOM_ITEM_BOX_CLASS
from .item_boxes import BOX_RULES, ITEM_BOX_CLASS, PLACED_COUNTS, SK_REQUIRED_TIER, SLOTS_PER_TRACK

FEATURE = "item_boxes_v1"
SPOT_FEATURE = box_spots.FEATURE
KEYS = ("shortcut_knowledge",)
SPOT_KEY = "spot_sets"
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


def add_spot_sets(record, tracks, package_by_id, seed, player):
    """Put `spot_sets` into a record from settings(): the pick of every track
    in `tracks` that has a spot file. Draws nothing from the world's random
    stream (box_spots.pick)."""
    if not record:
        return record
    sets = []
    for track in tracks:
        found = box_spots.spot_set(track, package_by_id.get(track.get("package_id")),
                                   record["shortcut_knowledge"], seed, player)
        if found is not None:
            sets.append(dict(track_id=track["id"], **found))
    record[SPOT_KEY] = sets
    excluded = crate_exclusions.records(tracks, package_by_id, {s["track_id"] for s in sets})
    if excluded:
        record[crate_exclusions.KEY] = excluded
    return record


def spot_sets(record):
    """{track id: spot set} of a record; {} without spots."""
    return {s["track_id"]: s for s in (record or {}).get(SPOT_KEY) or ()}


def keep_spot_sets(record, track_ids):
    """Drop the spot sets of tracks that hold no pad of the plan."""
    if record and SPOT_KEY in record:
        record[SPOT_KEY] = [s for s in record[SPOT_KEY] if s["track_id"] in track_ids]
    if record and crate_exclusions.KEY in record:
        kept = [s for s in record[crate_exclusions.KEY] if s["track_id"] in track_ids]
        if kept:
            record[crate_exclusions.KEY] = kept
        else:
            del record[crate_exclusions.KEY]
    return record


def check_settings(record, capability=None):
    """Shape and values of a plan's `item_boxes` record. With the capability
    record (#133 PR 4c) present, the two Shortcut Knowledge tiers agree. The
    spot sets are checked against their tracks by check_spot_sets."""
    if not isinstance(record, dict) or set(record) - {SPOT_KEY, crate_exclusions.KEY} != set(KEYS):
        error("item_boxes must be a mapping of shortcut_knowledge and, with box spots, spot_sets.")
    tier = record["shortcut_knowledge"]
    if type(tier) is not int or tier not in (0, 1, 2):
        error("item_boxes.shortcut_knowledge must be 0, 1 or 2.")
    if capability and capability.get("shortcut_knowledge") != tier:
        error("item_boxes.shortcut_knowledge disagrees with capability.shortcut_knowledge.")
    if crate_exclusions.KEY in record:
        excluded = record[crate_exclusions.KEY]
        if not isinstance(excluded, list) or not excluded:
            error("item_boxes.crate_exclusions must be a nonempty list.")
    if SPOT_KEY in record:
        sets = record[SPOT_KEY]
        if (not isinstance(sets, list) or not sets or any(not isinstance(s, dict) or "track_id" not in s for s in sets)
                or len({s["track_id"] for s in sets}) != len(sets)):
            error("item_boxes.spot_sets must be a nonempty list of spot sets, one per track.")
    return record


def check_spot_sets(record, tracks, packages):
    """A plan's spot sets: exactly the pad tracks with a spot file of this
    build, each a valid pick from that file."""
    if not record:
        return
    if crate_exclusions.KEY in record:
        expected = {row["track_id"]: row for row in crate_exclusions.records(tracks, packages, spot_sets(record))}
        # A room generated before a later catalog entry carries only the rows
        # of its day: each carried row must equal this build's row for its
        # track, but a track without a carried row keeps its original seating.
        # Compare complete JSON records, retaining exact token types.
        canonical = lambda row: json.dumps(row, sort_keys=True)
        carried = [row.get("track_id") if isinstance(row, dict) else None for row in record[crate_exclusions.KEY]]
        if len(set(carried)) != len(carried) or any(
                track_id not in expected or canonical(row) != canonical(expected[track_id])
                for track_id, row in zip(carried, record[crate_exclusions.KEY])):
            error("item_boxes.crate_exclusions disagrees with this build's reviewed exclusions.")
    if SPOT_KEY not in record:
        return
    sets = spot_sets(record)
    by_id = {t["id"]: t for t in tracks}
    if not set(sets) <= set(by_id):
        error("item_boxes.spot_sets names a track that holds no pad.")
    for track_id, track in by_id.items():
        package = packages.get(track.get("package_id"))
        has_file = box_spots.file_for(track, package) is not None
        # A named custom track whose file shipped after the room was generated
        # keeps its crate seats there: Item Box 1 to 15 are crate seats until
        # the track's file ships (ruled 2026-11-06, D1). Retail stays strict.
        if has_file != (track_id in sets) and not (has_file and track.get("origin") == "custom"):
            error(f"item_boxes.spot_sets disagrees with this build's box spot files for {track_id}.")
        if track_id in sets:
            try:
                box_spots.check_spot_set(track, package, record["shortcut_knowledge"],
                                         {k: v for k, v in sets[track_id].items() if k != "track_id"})
            except box_spots.SpotFileError as exc:
                error(str(exc))


def spot_entry(track, record, package=None):
    """(spot set, file entry) of a track that uses spots, else None."""
    sets = spot_sets(record)
    if track["id"] not in sets:
        return None
    entry = box_spots.file_for(track, package)
    if entry is None:
        error(f"item_boxes.spot_sets names {track['id']}, which has no box spot file in this build.")
    return sets[track["id"]], entry


def spot_of(track, record, package, number):
    """A box check's `spot` field, or None for a crate-seated or legacy box."""
    found = spot_entry(track, record, package)
    if found is None:
        return None
    return box_spots.wire_spot(box_spots.spots_by_number(found[1])[number])


def box_code(track, number):
    """The location code of a track's Item Box <number>."""
    if track["origin"] == "retail":
        return ITEM_BOX_CLASS.slot_code(track["display_name"], number)
    if "named_block" in track:
        return named_tracks.location_code(track["named_block"], f"item_box_{number}")
    return CUSTOM_ITEM_BOX_CLASS.slot_code(track["custom_slot"], number)


def crate_count(package, record=None, track_id=None):
    """Eligible crates in this seed; legacy records keep the raw package count.

    Never apply today's catalog implicitly when restoring an older room.
    """
    if not package:
        return None
    excluded = next((row["crates"] for row in (record or {}).get(crate_exclusions.KEY, ())
                     if row["track_id"] == track_id), ())
    return crate_exclusions.count(package, excluded)


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
    """[(number, location code, display suffix)] of a track's box checks."""
    if not record:
        return []
    found = spot_entry(track, record, package)
    if found is not None:
        return [(n, box_code(track, n), f"Item Box {n}") for n in found[0]["picked"]]
    if track["origin"] == "retail":
        name = track["display_name"]
        return [(slot, ITEM_BOX_CLASS.slot_code(name, slot), f"Item Box {slot}")
                for slot in retail_slots(name, record["shortcut_knowledge"])]
    if track["origin"] == "custom":
        crates = crate_count(package, record, track["id"])
        if not crates:
            return []
        return [(slot, box_code(track, slot), f"Item Box {slot}") for slot in range(1, len(seat_indices(crates)) + 1)]
    return []


def box_terms(track, slot, capability, package=None, record=None):
    """(boost rank, needs stats) of one box check, the legacy box rules with
    their options: a term binds only while the pack that creates its items is
    on. A spot box takes its spot's fields."""
    from .content_capability import finish_boost
    capability = capability or {}
    boost_on = bool(capability.get("boost_mode"))
    stats_on = bool(capability.get("stats_mode"))
    found = spot_entry(track, record, package)
    if found is not None:
        spot = box_spots.spots_by_number(found[1])[slot]
        return ((box_spots.needs_rank(spot) if boost_on else 0),
                bool(stats_on and box_spots.tier(spot) == box_spots.SHORTCUT["hard"]))
    if track["origin"] == "retail":
        boost_min, needs_stats = BOX_RULES.get((track["display_name"], slot), (0, False))
        return (boost_min if boost_on else 0), bool(needs_stats and stats_on)
    return (finish_boost(track, capability, package) if boost_on else 0), False
