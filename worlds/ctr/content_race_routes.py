"""Cup leg and boss race routes of the per-track checks (one generator row 10i).

Two per-track families are also earned outside the track's own pad:

  * Reach 10 Wumpa (`wumpa: per_track`, Rulebook "Reach 10 Wumpa checks" items
    3 and 5): a track's check is earned in its own Trophy Race or CTR
    Challenge, in any Gem Cup leg on that track and in a boss race on that
    track, also while the track's own pad is still locked. A track raced only
    in cups, or only as a boss venue, keeps its check through those races.
    Only a track that can reach ten fruit takes part: a retail track, Cortex
    Vortex, or a custom package with its measured `wumpa` capability.
  * Podium rungs (Rulebook "Placement rungs" items 6 and 7): a rung is earned
    in the track's Trophy Race and in any Gem Cup race on that track, never in
    a boss race. Only a track with a Trophy Race in the seed has rungs, so a
    track raced only in cups gets none (row 10i reading of item 7), unless
    `cup_only_podium_rungs` is on (rulings of 2026-11-02): then a track raced in
    a cup leg with no rungs of its own, because it has no pad or its pad has no
    Trophy Race, gets the same rungs, routed from its legs in the cups on pads
    (Gem Cups and pool cups, as a pad track's rungs are), never a boss cup.

Routes, after the check's own pad routes, in the plan's entry order, then leg
order (the order content_laps uses):

  * a Cup entry: one route per leg on the track, mode `cup`, its `leg_id`;
  * a boss race: one route, mode `boss_race`, its `encounter_id` (Wumpa only);
  * a boss cup: one route per leg on the track, mode `boss_cup`, both ids
    (Wumpa only).

A Wumpa check that only cup legs or boss races reach is a new check of its
track (kind `wumpa`, owner the track id, the frozen `<title>: Reach 10 Wumpa`
code), listed after the boss checks. So are a cup-only track's rungs (kind
`podium`, its frozen rung codes, in `podium_rungs` order, before its Wumpa
check). No new location id: every code is the track's existing one. The plan
carries no flag for the option: a podium check with only cup routes is the
option on (cup_only_on).

LOGIC (content_plan.create_regions, recomputed from the plan, never on the
wire): a cup route needs the Cup pad region and the finish of every earlier
leg (content_cups.prefix_boost), with the check's own `boost` on top, bound to
the Cup pad's racer lock; a boss route its encounter region.
"""
from . import content_bosses, content_cups

WUMPA_KIND = "wumpa"
WUMPA_AWARD = "wumpa"
PODIUM_KIND = "podium"


def _route(entry_id, mode, pad_id, award, leg_id=None, encounter_id=None):
    return dict(entry_id=entry_id, mode=mode, leg_id=leg_id, encounter_id=encounter_id, own_pad_id=pad_id, award=award)


def race_uses(entries, pads, encounters, bosses=True):
    """[(track id, entry id, mode, pad id, leg id, encounter id)] of every cup
    leg and, with `bosses`, every boss race, in entry order, then leg order."""
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    encounter_of = {enc["entry_id"]: enc for enc in encounters}
    out = []
    for entry in entries:
        enc = encounter_of.get(entry["id"])
        if enc is not None:
            if not bosses:
                continue
            if entry["kind"] == content_bosses.CUP_KIND:
                out.extend((leg["track_id"], entry["id"], content_bosses.CUP_MODE, enc["pad_id"], leg["id"], enc["id"])
                           for leg in entry["legs"])
            else:
                out.append((entry["track_id"], entry["id"], content_bosses.MODE, enc["pad_id"], None, enc["id"]))
        elif entry["kind"] == content_cups.KIND and entry["id"] in pad_of:
            out.extend((leg["track_id"], entry["id"], content_cups.MODE, pad_of[entry["id"]], leg["id"], None)
                       for leg in entry["legs"])
    return out


def cup_only_on(checks):
    """Whether a plan's checks have `cup_only_podium_rungs` on: a podium rung
    whose routes are all cup leg routes."""
    return any(check["kind"] == PODIUM_KIND and check["routes"] and all(map(is_race_route, check["routes"]))
               for check in checks)


def extend(checks, tracks, entries, pads, encounters, settings, fruit, location, titles, rung=None):
    """Adds the cup leg and boss race routes to the plan's per-track Wumpa
    checks and podium rungs, in place. Returns the new checks of tracks that
    only cups or boss races reach, in order of first use: a cup-only track's
    rungs, then its Wumpa check.

    `checks` are the checks built so far, `tracks` {track id: record},
    `fruit(track)` whether the track can reach ten fruit, `location(track)`
    its Reach 10 Wumpa code and `titles` {track id: room title}. With
    `cup_only_podium_rungs` on, `rung(track, key)` is a cup-only track's rung
    check of that rung key, without routes; None when the option is off. A
    cup-only track is a cup leg track with no rungs of its own: no pad, or a
    pad without a Trophy Race."""
    wumpa = settings.get("wumpa") == "per_track"
    rungs = bool(settings.get("podium_rungs"))
    if not (wumpa or rungs):
        return []
    by_owner = {}
    for check in checks:
        if check["kind"] in (WUMPA_KIND, PODIUM_KIND) and check["owner"] in tracks:
            by_owner.setdefault((check["kind"], check["owner"]), []).append(check)
    award = {}
    added = []
    for track_id, entry_id, mode, pad_id, leg_id, encounter_id in race_uses(entries, pads, encounters, wumpa):
        if rungs and mode == content_cups.MODE:
            if rung is not None and (PODIUM_KIND, track_id) not in by_owner:
                own = by_owner[(PODIUM_KIND, track_id)] = []
                for key in settings["podium_rungs"]:
                    check = rung(tracks[track_id], key)
                    award[check["location"]] = key
                    own.append(check)
                added.extend(own)
            for check in by_owner.get((PODIUM_KIND, track_id), ()):
                key = check["routes"][0]["award"] if check["routes"] else award[check["location"]]
                check["routes"].append(_route(entry_id, mode, pad_id, key, leg_id))
        if not wumpa or not fruit(tracks[track_id]):
            continue
        if (WUMPA_KIND, track_id) not in by_owner:
            check = dict(location=location(tracks[track_id]), owner=track_id, kind=WUMPA_KIND,
                         display_name=f"{titles[track_id]}: Reach 10 Wumpa", routes=[])
            by_owner[(WUMPA_KIND, track_id)] = [check]
            added.append(check)
        for check in by_owner[(WUMPA_KIND, track_id)]:
            check["routes"].append(_route(entry_id, mode, pad_id, WUMPA_AWARD, leg_id, encounter_id))
    return added


def count(standalone, legs, venues, settings, fruit, has_wumpa):
    """How many Wumpa checks `extend` adds for a drawn layout: the distinct
    cup leg and boss venue tracks (records) that can reach ten fruit and hold
    no Wumpa check of their own pad. `has_wumpa(track)` tells the latter."""
    if settings.get("wumpa") != "per_track":
        return 0
    own = {t["id"] for t in standalone if has_wumpa(t)}
    seen = {}
    for track in list(legs) + list(venues):
        seen.setdefault(track["id"], track)
    return sum(1 for track_id, track in seen.items() if track_id not in own and fruit(track))


def count_cup_only_rungs(standalone, legs, settings, on):
    """How many rung checks `extend` adds with `cup_only_podium_rungs`: the
    seed's rungs for each distinct cup leg track with no rungs of its own: no
    pad, or a pad without a Trophy Race (`standalone` holds the pad tracks)."""
    if not on or not settings.get("podium_rungs"):
        return 0
    own = {t["id"] for t in standalone if "trophy" in t["modes"]}
    return len({leg["id"] for leg in legs} - own) * len(settings["podium_rungs"])


def is_race_route(route):
    """A cup leg or boss race route, which create_regions rules on its own."""
    return route["leg_id"] is not None or route["encounter_id"] is not None
