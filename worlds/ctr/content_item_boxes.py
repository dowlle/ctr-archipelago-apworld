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

from . import box_spots, named_tracks, crate_exclusions, country_speedway, green_hill_raceway, royal_raceway, toasty_terrace, track_fill, track_rulings
from .custom_fallback_families import CUSTOM_ITEM_BOX_CLASS
from .item_boxes import BOX_RULES, ITEM_BOX_CLASS, PLACED_COUNTS, SK_REQUIRED_TIER, SLOTS_PER_TRACK

FEATURE = "item_boxes_v1"
SPOT_FEATURE = box_spots.FEATURE
COUNT_FEATURE = "box_count_v1"
KEYS = ("shortcut_knowledge",)
SPOT_KEY = "spot_sets"
SEAT_SPOT_KEY = "seat_spots"
SEAT_SPOT_FEATURE = "seat_spots_v2"
KIND = "box"
AWARD = "box"
ARABIAN_DAY = "arabian-heights-day"
ARABIAN_NIGHT = "arabian-heights-night"
ARABIAN_DAY_BOX_REVISION = (
    "1.0.0", "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900")
ARABIAN_NIGHT_BOX_REVISION = (
    "1.1.0", "8093b663855d3fd0096fd2980a85bc6efe334c0aff250e8a33eea11909e5c21c")
# Day's pinned spots are a coordinate-for-coordinate copy of Night's weapon
# crate ordinals. Each of these seven rows had a pickup in the Boost 0 drive.
ARABIAN_DAY_ROWS = ((1, 25, 26, 27), (2, 3, 4, 5), (6, 7, 8), (9, 10, 11, 12),
                    (13, 14, 15, 16), (17, 18, 19, 20), (21, 22, 23, 24))
ARABIAN_REVIEWED_BOXES = frozenset(n for row in ARABIAN_DAY_ROWS for n in row)


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options):
    """The plan's `item_boxes` record from the seed's options; {} when Item
    Box Locations are off."""
    count = options.item_box_count.value
    # Existing YAMLs and programmatic callers retain their on/off choice.
    # A non-default count takes precedence over the deprecated switch.
    if count == 15 and options.box_locations.value == 0 and not getattr(options.item_box_count, "explicit_yaml_count", False):
        count = 0
    options.item_box_count.value = count
    options.box_locations.value = int(count > 0)
    if not count:
        return {}
    record = dict(shortcut_knowledge=int(options.shortcut_knowledge.value))
    if count != 15:
        record["box_count"] = count
    return record


PICKUP_RULE_PINS = {country_speedway.LEV_SHA256, toasty_terrace.LEV_SHA256,
                    royal_raceway.LEV_SHA256, green_hill_raceway.LEV_SHA256}


def reviewed_pickups(package):
    """LEV that supplies the physical pickup rank, if one has a ruling."""
    pin = track_rulings.source(package, PICKUP_RULE_PINS)
    return pin if pin in PICKUP_RULE_PINS else None


def weapon_seat_file(track, package):
    """The spot file entry when its spots are a weapon crate layout that this
    room's track fill turns into real weapon crates (WF1, Arabian Heights Day).
    The spots then act as fallback seats on those crates, capped at 15 boxes
    (dowlle, 2026-11-26). Every spot must match a fill crate exactly."""
    if track.get("origin") != "custom" or not track_fill.package_weapons(package):
        return None
    entry = box_spots.file_for(track, package)
    if entry is None or any(spot.get("source_family") != "weapon_crate" for spot in entry["doc"]["spots"]):
        return None
    if len(track_fill.seated_ordinals(package, entry["doc"]["spots"])) != len(entry["doc"]["spots"]):
        error(f"{track['id']}: weapon crate spots must each match a filled weapon crate exactly.")
    return entry


def spot_cap(track, package, record):
    """How many spots a track picks: the Item Box Count, or at most 15 when the
    spots are fallback seats on filled weapon crates. A saved room decides by
    its own frozen spots, never by today's catalog."""
    count = (record or {}).get("box_count", 15)
    if track.get("id") in _frozen():
        spots = _frozen()[track["id"]]
        seats = track_fill.seated_ordinals(package, spots)
        return min(count, box_spots.PICK) if spots and len(seats) == len(spots) else count
    return min(count, box_spots.PICK) if weapon_seat_file(track, package) else count


def check_fill_seats(track, package, record):
    """A saved pick on filled crates follows the rules native enforces: one box
    per filled crate at its own angle, and either every box is a seat (at most
    15) or none is."""
    spots = _frozen().get(track["id"])
    weapons = track_fill.package_weapons(package)
    if not spots or not weapons:
        return
    by_pos = {}
    for i, crate in enumerate(weapons):
        by_pos[tuple(crate["pos"])] = (i, crate["rot"][1])
    claimed = []
    for spot in spots:
        found = by_pos.get(tuple(spot["pos"]))
        if found is not None:
            if found[1] != spot["rot_y"] or found[0] in claimed:
                error(f"item_boxes.spot_sets puts two boxes or a turned box on one filled crate of {track['id']}.")
            claimed.append(found[0])
    if claimed and (len(claimed) != len(spots) or len(spots) > box_spots.PICK):
        error(f"item_boxes.spot_sets mixes fallback seats and spots on {track['id']}.")


import contextvars

#: Box spots a frozen room carries, {track id: [spot]}, set while a saved
#: plan is validated so its seats come from its own checks (WF1). A context
#: variable, so concurrent validations never read each other's spots.
FROZEN = contextvars.ContextVar("ctr_frozen_box_spots", default={})


def _frozen():
    return FROZEN.get()


def frozen_spots(plan):
    """{track id: [spot]} of a plan's box checks that carry a spot."""
    out = {}
    checks = plan.get("checks") if isinstance(plan, dict) else None
    for check in checks if isinstance(checks, (list, tuple)) else ():
        spot = check.get("spot") if isinstance(check, dict) and check.get("kind") == KIND else None
        owner = check.get("owner") if isinstance(check, dict) else None
        if isinstance(owner, str) and isinstance(spot, dict) and isinstance(spot.get("pos"), (list, tuple)) and "rot_y" in spot:
            out.setdefault(owner, []).append(spot)
    return out


def seated_crates(track, record, package):
    """Fill weapon ordinals an AP box takes over in this room (sanity omits them).
    A saved room uses the spot positions it carries, never today's catalog."""
    found = spot_sets(record).get(track["id"])
    if found is None or not track_fill.package_weapons(package):
        return []
    lev = (package.get("capabilities") or {}).get("weapon_crates", 0)
    if track["id"] in _frozen():
        return track_fill.seated_ordinals(package, _frozen()[track["id"]], lev)
    entry = box_spots.file_for(track, package)
    if entry is None:
        return []
    by_number = box_spots.spots_by_number(entry)
    return track_fill.seated_ordinals(package, [by_number[n] for n in found["picked"] if n in by_number], lev)


def free_fill_ranks(track, record, package):
    """The ranks of the filled weapon crates (WF1) no AP box takes over in this
    room, in fill order (WF1b, dowlle 2026-11-26: a seated crate is no item
    source). [] for a track that is not filled. `record` is the room's
    item_boxes record when the track has box checks, else None (no seats).
    Hand-placed spots seat the crates at their exact place and angle; a track
    without a spot file seats its fallback boxes as native does (fill order,
    spread, at most 15)."""
    weapons = track_fill.package_weapons(package) if track.get("origin") == "custom" else []
    if not weapons or ((package or {}).get("capabilities") or {}).get("weapon_crates") != 0:
        return []
    seated = set()
    if record:
        if track["id"] in spot_sets(record):
            seated = set(seated_crates(track, record, package))
        else:
            slots = len(track_boxes(track, record, package))
            seated = {physical_seat(track, record, package, n) for n in range(1, slots + 1)}
    return [crate["rank"] for number, crate in enumerate(weapons, 1) if number not in seated]


def add_spot_sets(record, tracks, package_by_id, seed, player, blue_fire=False, logic_difficulty=None):
    """Put `spot_sets` into a record from settings(): the pick of every track
    in `tracks` that has a spot file. Draws nothing from the world's random
    stream (box_spots.pick). `blue_fire` is the capability record's
    boost_blue_fire: only then do blue_fire spots join a pool. `logic_difficulty`
    is the capability record's: a `rule_of` spot reads its crate ruling with it."""
    if not record:
        return record
    sets = []
    for track in tracks:
        package = package_by_id.get(track.get("package_id"))
        found = box_spots.spot_set(track, package, record["shortcut_knowledge"], seed, player,
                                   spot_cap(track, package, record), blue_fire, logic_difficulty)
        if found is not None:
            sets.append(dict(track_id=track["id"], **found))
    record[SPOT_KEY] = sets
    pickups = [t["id"] for t in tracks if t.get("origin") == "custom"
               and t["id"] not in {s["track_id"] for s in sets}
               and reviewed_pickups(package_by_id.get(t.get("package_id")))]
    if pickups:
        record[country_speedway.BOX_RULES_KEY] = pickups
    excluded = crate_exclusions.records(tracks, package_by_id, {s["track_id"] for s in sets})
    if excluded:
        record[crate_exclusions.KEY] = excluded
    replacements = reviewed_seat_spot_sets(record, tracks, package_by_id)
    if replacements:
        record[SEAT_SPOT_KEY] = replacements
    return record


def spot_sets(record):
    """{track id: spot set} of a record; {} without spots."""
    return {s["track_id"]: s for s in (record or {}).get(SPOT_KEY) or ()}


def seat_spot_sets(record):
    return {row["track_id"]: row["picked"] for row in (record or {}).get(SEAT_SPOT_KEY, ())}


def reviewed_seat_spot_sets(record, tracks, packages):
    full_spots = spot_sets(record)
    replacements = []
    for track in tracks:
        if track["origin"] != "custom" or track["id"] in full_spots:
            continue
        package = packages.get(track.get("package_id"))
        spots = box_spots.SEAT_SPOTS.get(box_spots.lev_pin(package))
        if not spots:
            continue
        picked = [number for number, _, _ in track_boxes(track, record, package)
                  if str(physical_seat(track, record, package, number)) in spots]
        if picked:
            replacements.append(dict(track_id=track["id"], picked=picked))
    return replacements


def keep_spot_sets(record, track_ids):
    """Drop the spot sets of tracks that hold no pad of the plan."""
    if record and country_speedway.BOX_RULES_KEY in record:
        kept = [tid for tid in record[country_speedway.BOX_RULES_KEY] if tid in track_ids]
        if kept:
            record[country_speedway.BOX_RULES_KEY] = kept
        else:
            del record[country_speedway.BOX_RULES_KEY]
    if record and SPOT_KEY in record:
        record[SPOT_KEY] = [s for s in record[SPOT_KEY] if s["track_id"] in track_ids]
    if record and crate_exclusions.KEY in record:
        kept = [s for s in record[crate_exclusions.KEY] if s["track_id"] in track_ids]
        if kept:
            record[crate_exclusions.KEY] = kept
        else:
            del record[crate_exclusions.KEY]
    if record and SEAT_SPOT_KEY in record:
        kept = [s for s in record[SEAT_SPOT_KEY] if s["track_id"] in track_ids]
        if kept:
            record[SEAT_SPOT_KEY] = kept
        else:
            del record[SEAT_SPOT_KEY]
    return record


def check_settings(record, capability=None):
    """Shape and values of a plan's `item_boxes` record. With the capability
    record (#133 PR 4c) present, the two Shortcut Knowledge tiers agree. The
    spot sets are checked against their tracks by check_spot_sets."""
    optional = {SPOT_KEY, SEAT_SPOT_KEY, crate_exclusions.KEY, "box_count", country_speedway.BOX_RULES_KEY}
    if not isinstance(record, dict) or set(record) - optional != set(KEYS):
        error("item_boxes must be a mapping of shortcut_knowledge and, with box spots, spot_sets.")
    tier = record["shortcut_knowledge"]
    if country_speedway.BOX_RULES_KEY in record:
        ids = record[country_speedway.BOX_RULES_KEY]
        if (not isinstance(ids, list) or not ids or any(type(tid) is not str for tid in ids)
                or len(set(ids)) != len(ids)):
            error("item_boxes.pickup_rules must be a nonempty list of unique track ids.")
    if "box_count" in record and (type(record["box_count"]) is not int or not 1 <= record["box_count"] <= 50
                                  or record["box_count"] == 15):
        error("item_boxes.box_count must be 1 to 50, omitting the default 15.")
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
    if SEAT_SPOT_KEY in record:
        sets = record[SEAT_SPOT_KEY]
        if (not isinstance(sets, list) or not sets or len(sets) > 160
                or any(not isinstance(row, dict) or set(row) != {"track_id", "picked"}
                       or type(row["track_id"]) is not str or not isinstance(row["picked"], list)
                       or not row["picked"]
                       or any(type(n) is not int or not 1 <= n <= SLOTS_PER_TRACK for n in row["picked"])
                       or row["picked"] != sorted(set(row["picked"])) for row in sets)
                or len(seat_spot_sets(record)) != len(sets)):
            error("item_boxes.seat_spots must name distinct tracks and sorted fallback box numbers.")
    return record


def check_spot_sets(record, tracks, packages, *, restoring=False, carried=False, require_reviewed_exclusions=False,
                    blue_fire=False, logic_difficulty=None):
    """Validate saved picks and crate exclusions, or match the source catalog."""
    if not record:
        return
    by_id = {t["id"]: t for t in tracks}
    sets = spot_sets(record)
    for tid in record.get(country_speedway.BOX_RULES_KEY, ()):
        track = by_id.get(tid)
        if (not track or track.get("origin") != "custom" or tid in sets
                or not reviewed_pickups(packages.get(track.get("package_id")))):
            error("item_boxes.pickup_rules names an unsupported physical pickup revision.")
    expected = {row["track_id"]: row for row in crate_exclusions.records(tracks, packages, sets)}
    carried_rows = record.get(crate_exclusions.KEY, ())
    carried_ids = [row.get("track_id") if isinstance(row, dict) else None for row in carried_rows]
    if any(tid not in carried_ids and row["crates"][0]["pos"] is None for tid, row in expected.items()):
        error("item_boxes.crate_exclusions is missing carried ordinals.")
    if carried:
        for row in carried_rows:
            track = by_id.get(row["track_id"])
            package = packages.get((track or {}).get("package_id"))
            ordinals = [crate["ordinal"] for crate in row["crates"]]
            if (not package or row["track_id"] in sets or row["lev_sha256"] != box_spots.lev_pin(package)
                    or ordinals != sorted(set(ordinals))
                    or ordinals[-1] > package["capabilities"].get("weapon_crates", 0)):
                error("item_boxes.crate_exclusions disagrees with the room's pinned fallback track.")
        if len(carried_ids) != len(set(carried_ids)):
            error("item_boxes.crate_exclusions names a track more than once.")
        if require_reviewed_exclusions:
            # Native compares a version 2 room's carried rows with the reviewed
            # catalog wherever the pin has a version 2 entry, stamped or not.
            canonical = lambda crates: json.dumps(crates, sort_keys=True)
            held = {row["track_id"]: row["crates"] for row in carried_rows}
            for row in expected.values():
                pin = row["lev_sha256"]
                if not crate_exclusions.ordinals(pin) - crate_exclusions.ordinals(pin, sanity_version=1):
                    continue
                if row["track_id"] not in held:
                    error("item_boxes is missing reviewed fallback exclusions.")
                if canonical(held[row["track_id"]]) != canonical(row["crates"]):
                    error("item_boxes.crate_exclusions disagrees with this build's reviewed exclusions.")
    elif carried_rows or require_reviewed_exclusions:
        # A room generated before a later catalog entry carries only the rows
        # of its day: each carried row must equal this build's row for its
        # track, but a track without a carried row keeps its original seating.
        # Compare complete JSON records, retaining exact token types.
        canonical = lambda row: json.dumps(row, sort_keys=True)
        if len(set(carried_ids)) != len(carried_ids) or any(
                track_id not in expected or canonical(row) != canonical(expected[track_id])
                for track_id, row in zip(carried_ids, carried_rows)):
            error("item_boxes.crate_exclusions disagrees with this build's reviewed exclusions.")
        if require_reviewed_exclusions:
            for track_id, row in expected.items():
                pin = row["lev_sha256"]
                if (track_id not in carried_ids
                        and crate_exclusions.ordinals(pin) - crate_exclusions.ordinals(pin, sanity_version=1)):
                    error("item_boxes is missing reviewed fallback exclusions.")
    if SEAT_SPOT_KEY in record:
        expected_spots = {row["track_id"]: row["picked"] for row in reviewed_seat_spot_sets(record, tracks, packages)}
        if seat_spot_sets(record) != expected_spots:
            error("item_boxes.seat_spots disagrees with this room's reviewed fallback seats.")
    if SPOT_KEY not in record:
        return
    if not set(sets) <= set(by_id):
        error("item_boxes.spot_sets names a track that holds no pad.")
    for track_id, track in by_id.items():
        package = packages.get(track.get("package_id"))
        if carried:
            spot_set = sets.get(track_id)
            if spot_set is None:
                if track["origin"] == "retail":
                    error(f"item_boxes.spot_sets is missing retail track {track_id}.")
                continue
            picked = spot_set["picked"]
            check_fill_seats(track, package, record)
            if (picked != sorted(set(picked)) or len(picked) != min(spot_set["pool"], spot_cap(track, package, record))
                    or not (track["origin"] == "retail" and "lev_sha256" not in spot_set
                            or "named_block" in track and package is not None
                            and spot_set.get("lev_sha256") == box_spots.lev_pin(package))):
                error(f"item_boxes.spot_sets disagrees with the room's track or pick for {track_id}.")
            continue
        has_file = box_spots.file_for(track, package) is not None
        # A named custom track whose file shipped after the room was generated
        # keeps its crate seats there: Item Box 1 to 15 are crate seats until
        # the track's file ships (ruled 2026-11-06, D1). Retail stays strict.
        if has_file != (track_id in sets) and not (has_file and track.get("origin") == "custom"):
            error(f"item_boxes.spot_sets disagrees with this build's box spot files for {track_id}.")
        if track_id in sets:
            check_fill_seats(track, package, record)
            try:
                box_spots.check_spot_set(track, package, record["shortcut_knowledge"],
                                         {k: v for k, v in sets[track_id].items() if k != "track_id"},
                                         spot_cap(track, package, record), compare_digest=not restoring,
                                         blue_fire=blue_fire, logic_difficulty=logic_difficulty)
            except box_spots.SpotFileError as exc:
                error(str(exc))


def spot_entry(track, record, package=None):
    """(spot set, file entry) of a track that uses spots, else None."""
    sets = spot_sets(record)
    if track["id"] not in sets:
        return None
    # check_spot_sets already refused a digest other than this build's file
    # unless the room is being restored; then a restore-only file may apply.
    entry = box_spots.file_for(track, package, sets[track["id"]].get("file_sha256"))
    if entry is None:
        error(f"item_boxes.spot_sets names {track['id']}, which has no box spot file in this build.")
    return sets[track["id"]], entry


def spot_of(track, record, package, number):
    """A box check's `spot` field, or None for a crate-seated or legacy box."""
    found = spot_entry(track, record, package)
    if found is None:
        if number not in seat_spot_sets(record).get(track["id"], ()):
            return None
        spot = box_spots.SEAT_SPOTS[box_spots.lev_pin(package)][str(physical_seat(track, record, package, number))]
        return dict(number=number, pos=list(spot["pos"]), rot_y=spot["rot_y"])
    return box_spots.wire_spot(box_spots.spots_by_number(found[1])[number])


def box_code(track, number):
    """The location code of a track's Item Box <number>."""
    if track["origin"] == "retail":
        return ITEM_BOX_CLASS.slot_code(track["display_name"], number)
    if "named_block" in track:
        return named_tracks.location_code(track["named_block"], f"item_box_{number}")
    return CUSTOM_ITEM_BOX_CLASS.slot_code(track["custom_slot"], number)


def carried_crates(record, track_id):
    return next((row["crates"] for row in (record or {}).get(crate_exclusions.KEY, ())
                 if row["track_id"] == track_id), ())


def crate_count(package, record=None, track_id=None):
    """Eligible crates in this seed; legacy records keep the raw package count.

    Never apply today's catalog implicitly when restoring an older room.
    """
    if not package:
        return None
    return crate_exclusions.count(package, carried_crates(record, track_id))


def seat_limit(package):
    from .sanity import reviewed_counts

    raw = crate_count(package)
    if raw == 0 and track_fill.package_weapons(package):
        # WF1: a LEV measured without weapon crates seats its fallback boxes
        # on the crates its frozen fill adds (native ap_boxes.c, fill order).
        # A reviewed pickup prefix bounds the LEV's own crates, not these.
        return len(track_fill.package_weapons(package))
    reviewed = reviewed_counts(package)
    return min(raw, reviewed[0]) if raw is not None and reviewed is not None else raw


def seat_indices(crates, slots=SLOTS_PER_TRACK):
    """Which weapon crates, by their order in the LEV instance table, take the
    Item Box seats: min(crates, slots) of them, spread over the whole table
    (seat i is crate floor(i * crates / seats)), so a track with more crates
    than seats keeps ordinary crates between its AP boxes. Native computes the
    same (ap_box_seat_logic.h)."""
    seats = min(crates, slots)
    return [i * crates // seats for i in range(seats)]


def physical_seat(track, record, package, number):
    """One-based native weapon ordinal after this room's exclusions and spread."""
    omitted = {row["ordinal"] for row in carried_crates(record, track["id"])}
    crates = [n for n in range(1, seat_limit(package) + 1) if n not in omitted]
    seats = seat_indices(len(crates), min(record.get("box_count", 15), 15))
    return crates[seats[number - 1]]


def retail_slots(track_name, tier):
    """The 1-based retail box slots a track creates at a Shortcut Knowledge tier."""
    return [slot for slot in range(1, PLACED_COUNTS[track_name] + 1)
            if SK_REQUIRED_TIER.get((track_name, slot), 0) <= tier]


def track_boxes(track, record, package=None):
    """[(number, location code, display suffix)] of a track's box checks."""
    if not record:
        return []
    spot_set = spot_sets(record).get(track["id"])
    if spot_set is not None:
        return [(n, box_code(track, n), f"Item Box {n}") for n in spot_set["picked"]]
    if track["origin"] == "retail":
        name = track["display_name"]
        return [(slot, ITEM_BOX_CLASS.slot_code(name, slot), f"Item Box {slot}")
                for slot in retail_slots(name, record["shortcut_knowledge"])]
    if track["origin"] == "custom":
        limit = seat_limit(package)
        if not limit:
            return []
        crates = limit - sum(row["ordinal"] <= limit for row in carried_crates(record, track["id"]))
        return [(slot, box_code(track, slot), f"Item Box {slot}")
                for slot in range(1, len(seat_indices(crates, min(record.get("box_count", 15), 15))) + 1)]
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
        rank = (box_spots.spot_rank(spot, package, bool(capability.get("boost_blue_fire")),
                                    capability.get("logic_difficulty", 2)) if boost_on else 0)
        if (rank and track_rulings.scoped_version() >= track_rulings.ARABIAN_BOOST_VERSION
                and found[1]["doc"]["track"].get("track_key") == ARABIAN_DAY
                and track_rulings.revision_ref(package) == ARABIAN_DAY_BOX_REVISION
                and slot in ARABIAN_REVIEWED_BOXES):
            rank = 0
        return (rank,
                bool(stats_on and box_spots.tier(spot) == box_spots.SHORTCUT["hard"]))
    if track["origin"] == "retail":
        boost_min, needs_stats = BOX_RULES.get((track["display_name"], slot), (0, False))
        return (boost_min if boost_on else 0), bool(needs_stats and stats_on)
    weapons = track_fill.package_weapons(package) if track["origin"] == "custom" else []
    if weapons and crate_count(package) == 0:
        # WF1: a fallback box on a filled crate needs at least that crate's
        # frozen rank, on top of the track's finish term.
        rank = weapons[physical_seat(track, record, package, slot) - 1]["rank"]
        return (max(finish_boost(track, capability, package), rank) if boost_on else 0), False
    if track["id"] in (record or {}).get(country_speedway.BOX_RULES_KEY, ()):
        pin = reviewed_pickups(package)
        if pin == country_speedway.LEV_SHA256:
            rank = country_speedway.rank("weapon_crate", physical_seat(track, record, package, slot))
            return (rank if boost_on else 0), False
        if pin:
            return 0, False
    if boost_on and package and track_rulings.scoped_version() >= track_rulings.ARABIAN_BOOST_VERSION:
        key = package["content_id"]
        if key == ARABIAN_NIGHT:
            # AP box numbers are spread seats, not the LEV's crate ordinals.
            if (track_rulings.revision_ref(package) == ARABIAN_NIGHT_BOX_REVISION
                    and physical_seat(track, record, package, slot) in ARABIAN_REVIEWED_BOXES):
                return 0, False
            return 2, False
        if key == ARABIAN_DAY:
            # Unmatched crate seats keep the measured default even when this
            # package inherits the reviewed finish rule.
            return (2 if package["capabilities"].get("super_turbo_pads", True) else 0), False
    return (finish_boost(track, capability, package) if boost_on else 0), False
