"""Player-facing pad requirements read from the finished content plan."""
from collections import defaultdict

from . import (arena_content, boss_track_shuffle, characters, content_bosses, content_plan,
               content_wumpa, destinations, warp_pad_rules, wumpa_shop)


def _quantity(count, name):
    if count != 1:
        name = "Trophies" if name == "Trophy" else name + "s"
    return f"{count} {name}"


def _requirement(node):
    op = node["op"]
    if op == "always":
        return ""
    if op == "all":
        return " + ".join(_requirement(term) for term in node["terms"])
    if op == "any":
        return "(" + " or ".join(_requirement(term) for term in node["terms"]) + ")"
    count = node["count"]
    if op == "checked":
        return _quantity(count, "Boss Win")
    if op == "distinct":
        return _quantity(count, "Different Gem")
    if op == "count":
        return _quantity(count, content_plan.ITEM_BY_CODE[node["item"]])
    if op == "sum":
        names = {content_plan.ITEM_BY_CODE[code] for code in node["items"]}
        if len(names) == 1:
            return _quantity(count, next(iter(names)))
        for label, family in (("Any Relic", warp_pad_rules.RELICS),
                              ("Any CTR Token", warp_pad_rules.TOKENS),
                              ("Any Gem", warp_pad_rules.GEMS)):
            if names.issubset(family):
                return _quantity(count, label)
    raise ValueError(f"Unsupported CTR pad requirement: {node}")


def _entry_title(entry, tracks):
    if "track_id" in entry:
        return content_plan.room_title(tracks[entry["track_id"]])
    if entry["kind"] == "crystal":
        return f"{arena_content.ARENAS[entry['arena_id']]} Crystal Challenge"
    if entry["kind"] == content_bosses.CUP_KIND:
        venues = " / ".join(content_plan.room_title(tracks[leg["track_id"]]) for leg in entry["legs"])
        return f"Boss Cup ({venues})"
    return entry["display_name"]


def lines(plan):
    """One row per physical pad or garage, in hub and pad order."""
    entries = {entry["id"]: entry for entry in plan["entries"]}
    tracks = {track["id"]: track for track in plan["tracks"]}
    requirements = {row["id"]: row["predicate"] for row in plan["requirements"]}
    pads = {d.level_id: d for d in destinations.DESTINATIONS}
    hubs = {f"hub:{physical}": name for name, physical in wumpa_shop.SHOP_LEVEL_IDS.items()}
    encounters = defaultdict(list)
    for encounter in plan["encounters"]:
        encounters[encounter["pad_id"]].append(encounter)
    wumpa_goal = content_wumpa.goal_arm(plan["goal"])
    hub_order = ("N. Sanity Beach", "Lost Ruins", "Glacier Park", "Citadel City", "Gem Stone Valley", "Cups Room")
    rows = []
    for pad in plan["pads"]:
        physical = content_plan.pad_physical(pad)
        hub = hubs[pad["hub_id"]]
        hub_gate = _requirement(requirements[pad["entrance_req"]])
        if pad["kind"] == "garage":
            oxide = physical == content_bosses.OXIDE_GARAGE
            name = boss_track_shuffle.OXIDE_GARAGE if oxide else boss_track_shuffle.GARAGES[physical][1]
            races = []
            for encounter in encounters[pad["id"]]:
                title = _entry_title(entries[encounter["entry_id"]], tracks)
                gate = _requirement(requirements[encounter["requirement_id"]])
                needs = [part for part in (hub_gate, gate) if part]
                if oxide:
                    challenge = "Final Challenge" if encounter["index"] else "Challenge"
                    title = f"{challenge}: {title}"
                    if wumpa_goal and encounter["completion_location"] == content_bosses.goal_location(plan["bosses"]):
                        needs.append(f"{wumpa_goal['count']:,} Wumpa Fruit")
                races.append(f"{title} ({' + '.join(needs) or 'Free'})")
            detail = " | ".join(races) or "Disabled"
            order = 200 + physical
        else:
            destination = pads[physical]
            name = destination.pad_name
            if destination.kind == destinations.KIND_CUP:
                hub = "Cups Room"
            detail = "Empty"
            if pad["entry_id"] is not None:
                title = _entry_title(entries[pad["entry_id"]], tracks)
                gates = {gate["stage"]: _requirement(requirements[gate["requirement_id"]])
                         for gate in pad["mode_gates"]}
                needs = [gates[1]] if gates[1] else []
                if pad["racer_lock"] is not None:
                    needs.append(characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]])
                detail = f"{title} ({' + '.join(needs) or 'Free'})"
                if hub_gate:
                    detail += f" | Hub: {hub_gate}"
                if gates.get(2):
                    detail += f" | Stage 2: {gates[2]}"
            order = physical
        rows.append((hub_order.index(hub), order, f"{hub} / {name}: {detail}"))
    return [line for _, _, line in sorted(rows)]
