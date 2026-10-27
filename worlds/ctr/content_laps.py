"""Lap completion checks on content plans (#344).

With `lap_completion_checks` on, every plan track the seed races on a
standalone pad or as a Cup leg owns one `<title>: Complete One Lap` check
(kind `lap`, owner the track id), paid by the first accepted lap of any race on
it. Its routes, in the plan's entry order:

  * a standalone Track entry: one route per mode of the entry, in the entry's
    mode order (Trophy Race, CTR Challenge and Relic Race all have laps), award
    `lap`, `leg_id` null;
  * a Cup entry: one route per leg that races the track, mode `cup`, award
    `lap`, with its `leg_id`.

Boss races and boss cups are no route (the normal room's conservative reading,
lap_checks.py): native sends a lap check only from a pad whose record carries
it. Crystal Challenges have no laps.

Codes: retail `<Track>: Complete One Lap` (35028000 block), Cortex Vortex
35026009, named block offset 16, generic slot N `Custom Track N: Complete One
Lap` (35028100 + N - 1). The checks follow the Cup Leg Victory checks in the
plan's check list.

LOGIC (content_plan.create_regions, recomputed from the plan, never on the
wire): a standalone route needs its pad region, the second-stage gate of its
mode when it has one, and the track's finish rank (content_capability
finish_boost, the Ultimate Sacred Fire rulings) bound to the pad's racer lock;
a Cup route needs the Cup pad region and the finish of every leg up to and
including its own (content_cups.prefix_boost plus the leg's finish), bound to
the Cup pad's racer lock. No win or rank term.

Feature `lap_checks_v1` is appended last in `required_features` exactly when a
lap check exists. A plan with the option off keeps its wire and draws exactly.
"""
from . import content_cups

FEATURE = "lap_checks_v1"
KIND = "lap"
AWARD = "lap"
SUFFIX = "Complete One Lap"


def _route(entry_id, mode, pad_id, leg_id=None):
    return dict(entry_id=entry_id, mode=mode, leg_id=leg_id, encounter_id=None, own_pad_id=pad_id, award=AWARD)


def checks(tracks, entries, pads, titles, location):
    """Every lap check of the plan. `tracks` maps track id to record, `titles`
    track id to room title, and `location(track)` gives a track's lap code."""
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    out = {}

    def add(track_id, route):
        if track_id not in out:
            out[track_id] = dict(location=location(tracks[track_id]), owner=track_id, kind=KIND,
                                 display_name=f"{titles[track_id]}: {SUFFIX}", routes=[])
        out[track_id]["routes"].append(route)
    for entry in entries:
        if entry["id"] not in pad_of:
            continue
        if entry["kind"] == "track":
            for mode in entry["modes"]:
                add(entry["track_id"], _route(entry["id"], mode, pad_of[entry["id"]]))
        elif entry["kind"] == content_cups.KIND:
            for leg in entry["legs"]:
                add(leg["track_id"], _route(entry["id"], content_cups.MODE, pad_of[entry["id"]], leg["id"]))
    return list(out.values())


def count(chosen, is_track):
    """How many lap checks a drawn layout makes: its distinct standalone and
    Cup leg tracks."""
    ids = {t["id"] for t in chosen if is_track(t)}
    ids |= {leg["id"] for cup in chosen if "cup_index" in cup for leg in cup["legs"]}
    return len(ids)
