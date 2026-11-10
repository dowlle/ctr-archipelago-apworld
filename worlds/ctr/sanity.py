"""Ordinary pickup checks, A4-23. The world owns frozen identities and picks;
native owns collisions. Ordinals are one-based within each LEV model family.

DATAPACKAGE STABILITY: retail uses the approved sparse 35026/35029 blocks;
named tracks get a separate 128-code block at 37200000 + 128 * block_index.
All names register unconditionally. Append only, never rename or reorder.
"""
import hashlib
import json
import pkgutil
from random import Random

from Options import OptionError

from . import box_spots, content_item_boxes, crate_exclusions, destinations
from .item_boxes import BOX_TRACKS
from .location_class import LocationClass

KINDS = ("weapon_crate", "wumpa_crate", "wumpa_fruit")
SUFFIXES = ("Weapon Crate", "Wumpa Crate", "Wumpa Fruit")
BUDGETS = (80, 16, 32)
NAMED_BASE = 37200000
FEATURES = ("itemboxsanity_v1", "wumpasanity_v1")
# Retail LevelID order, not the datapackage's BOX_TRACKS order.
COUNTS = ((16, 2, 16), (16, 2, 0), (16, 2, 14), (18, 3, 0), (12, 11, 0),
          (16, 2, 9), (13, 2, 0), (24, 4, 0), (20, 6, 0), (22, 3, 0),
          (16, 10, 0), (17, 4, 0), (24, 12, 0), (19, 13, 0), (16, 3, 10),
          (24, 4, 0), (16, 3, 6), (16, 3, 9))
CATALOG = json.loads(pkgutil.get_data(__package__, "data/sanity_needs.json"))


def code(track, family, number):
    if track["origin"] == "retail":
        index = BOX_TRACKS.index(track["display_name"])
        return (35029000 + 32 * index, 35029600 + 16 * index, 35026300 + 16 * index)[family] + number - 1
    if track["origin"] == "cortex_vortex":
        return (35026100, 35026180, 35026200)[family] + number - 1
    return NAMED_BASE + 128 * track["named_block"] + (0, 80, 96)[family] + number - 1


class SanityLocations(LocationClass):
    key = "sanity"
    display_name = "Weapon crates and Wumpa pickups"
    code_blocks = (35026000, 35029000) + tuple(range(NAMED_BASE, NAMED_BASE + 12000, 1000))

    def all_locations(self):
        tracks = [(dict(origin="retail", display_name=d.region_name, retail_id=d.level_id), COUNTS[d.level_id])
                  for d in destinations.DESTINATIONS if d.kind in (destinations.KIND_RACE, destinations.KIND_TRIAL)]
        tracks += [(dict(origin="cortex_vortex", display_name="Cortex Vortex"), (69, 7, 0))]
        tracks += [(dict(origin="custom", display_name=t.ap_name, named_block=t.block_index), BUDGETS)
                   for t in destinations.NAMED_TRACKS]
        return [(f"{t['display_name']}: {SUFFIXES[f]} {n}", code(t, f, n), t["display_name"])
                for t, counts in tracks for f, count in enumerate(counts) for n in range(1, count + 1)]

    def created_location_names(self, options):
        # Content plans own their per-seed subset, as for cup and lap checks.
        return []


SANITY_CLASS = SanityLocations()


def settings(options):
    count, wumpa = int(options.itemboxsanity.value), int(options.wumpasanity.value)
    return dict(itemboxsanity=count, wumpasanity=wumpa, tracks=[]) if count or wumpa else None


def inventory(track, package=None):
    if track["origin"] == "retail":
        return CATALOG.get("retail:" + str(track["retail_id"]))
    if track["origin"] == "cortex_vortex":
        return CATALOG.get("cortex_vortex")
    if "named_block" in track:
        pin = box_spots.lev_pin(package)
        if pin in CATALOG:
            return CATALOG[pin]
        caps = (package or {}).get("capabilities", {})
        if all(k in caps for k in ("weapon_crates", "fruit_crates", "loose_fruit")):
            counts = [caps[k] for k in ("weapon_crates", "fruit_crates", "loose_fruit")]
            return dict(lev_sha256=pin, counts=counts,
                        needs={kind: {str(n): dict(needs="usf", reviewed=False) for n in range(1, min(count, budget) + 1)}
                               for kind, count, budget in zip(KINDS, counts, BUDGETS)})
    return None


def eligible(track, family, record, item_boxes, package):
    inv = inventory(track, package)
    if inv is None:
        return []  # No measured revision, no invented objects.
    out = list(range(1, min(inv["counts"][family], BUDGETS[family]) + 1))
    if family == 0:
        # Reviewed exclusions are keyed by exact LEV: custom revisions and the retail Roo's Tubes crate.
        excluded = {c["ordinal"] for c in crate_exclusions.EXCLUSIONS.get(inv["lev_sha256"], ())}
        # Seat the AP boxes first, only on a standalone fallback pad. Authored
        # spot tracks hide no weapon crates. Match the runtime's eligible spread.
        if track["origin"] == "custom" and item_boxes and track["id"] not in content_item_boxes.spot_sets(item_boxes):
            all_crates = [n for n in range(1, inv["counts"][0] + 1) if n not in excluded]
            slots = len(content_item_boxes.track_boxes(track, item_boxes, package))
            excluded.update(all_crates[i] for i in content_item_boxes.seat_indices(len(all_crates), slots))
        out = [n for n in out if n not in excluded]
    tier = record["shortcut_knowledge"]
    return [n for n in out if inv.get("needs", {}).get(KINDS[family], {}).get(str(n), {}).get("shortcut", 0) <= tier]


def add_tracks(record, tracks, packages, item_boxes, seed, player, tier, standalone=()):
    if record is None:
        return
    record["shortcut_knowledge"] = tier
    seen = set()
    for track in tracks:
        if track["id"] in seen:
            continue
        seen.add(track["id"])
        package = packages.get(track.get("package_id"))
        inv = inventory(track, package)
        if inv is None:
            continue
        row = dict(track_id=track["id"], lev_sha256=inv["lev_sha256"], counts=inv["counts"][:])
        for f, kind in enumerate(KINDS):
            numbers = eligible(track, f, record, item_boxes if track["id"] in standalone else None, package)
            if f == 0:
                key = f"{seed}:{player}:itemboxsanity:{track['id']}".encode()
                rng = Random(int.from_bytes(hashlib.sha256(key).digest(), "big"))
                numbers = sorted(rng.sample(numbers, min(len(numbers), record["itemboxsanity"])))
            elif not record["wumpasanity"] & f:
                numbers = []
            row[kind] = numbers
        record["tracks"].append(row)


def routes(tracks, entries, pads, encounters):
    from . import content_race_routes
    out = {t["id"]: [] for t in tracks}
    pad_of = {p["entry_id"]: p["id"] for p in pads if p["entry_id"] is not None}
    for e in entries:
        if e["kind"] == "track" and e["id"] in pad_of:
            out[e["track_id"]].extend(content_race_routes._route(e["id"], m, pad_of[e["id"]], "pickup")
                                       for m in e["modes"] if m in ("trophy", "ctr"))
    for track, entry, mode, pad, leg, encounter in content_race_routes.race_uses(entries, pads, encounters):
        out[track].append(content_race_routes._route(entry, mode, pad, "pickup", leg, encounter))
    return out


def checks(record, tracks, entries, pads, encounters, capability):
    if record is None:
        return []
    by_id = {t["id"]: t for t in tracks}
    uses = routes(tracks, entries, pads, encounters)
    out = []
    for row in record["tracks"]:
        t = by_id[row["track_id"]]
        for f, kind in enumerate(KINDS):
            for n in row[kind]:
                c = dict(location=code(t, f, n), owner=t["id"], kind=kind,
                         display_name=f"{t.get('room_title', t['display_name'])}: {SUFFIXES[f]} {n}", routes=uses[t["id"]])
                need = inventory(t) if t["origin"] != "custom" else CATALOG.get(row["lev_sha256"])
                if need is None:
                    need = dict(needs={kind: {str(n): dict(needs="usf") for n in row[kind]} for kind in KINDS})
                fields = (need or {}).get("needs", {}).get(kind, {}).get(str(n), {})
                if capability and capability.get("boost_mode") and fields.get("needs", "none") != "none":
                    c["boost"] = 2 if fields.get("needs") == "usf" else 1
                if capability and capability.get("stats_mode") and fields.get("shortcut") == 2:
                    c["stats"] = True
                out.append(c)
    return out


def door_codes(plan):
    """The selected Tiger Temple pickups behind its weapon-opened door."""
    track = next((t for t in plan["tracks"] if t["id"] == "retail:4"), None)
    if track is None:
        return set()
    needs = CATALOG["retail:4"]["needs"]
    return {code(track, f, n) for row in plan.get("sanity", {}).get("tracks", ())
            if row["track_id"] == "retail:4" for f, kind in enumerate(KINDS) for n in row[kind]
            if needs.get(kind, {}).get(str(n), {}).get("door")}


def validate(record, plan):
    if record is None:
        return
    def require(ok, why):
        if not ok:
            raise OptionError("CTR sanity: " + why)
    require(type(record) is dict and set(record) == {"itemboxsanity", "wumpasanity", "shortcut_knowledge", "tracks"}, "record shape")
    require(type(record["itemboxsanity"]) is int and 0 <= record["itemboxsanity"] <= 50, "crate count")
    require(type(record["wumpasanity"]) is int and 0 <= record["wumpasanity"] <= 3, "Wumpasanity mode")
    require(record["itemboxsanity"] or record["wumpasanity"], "empty feature")
    require(type(record["shortcut_knowledge"]) is int and 0 <= record["shortcut_knowledge"] <= 2, "shortcut tier")
    require(not plan.get("capability") or record["shortcut_knowledge"] == plan["capability"]["shortcut_knowledge"], "shortcut tier mismatch")
    packages = {p["id"]: p for p in plan["packages"]}
    by_id = {t["id"]: t for t in plan["tracks"]}
    uses = routes(plan["tracks"], plan["entries"], plan["pads"], plan["encounters"])
    expected = {t["id"] for t in plan["tracks"] if uses[t["id"]] and inventory(t, packages.get(t.get("package_id"))) is not None}
    require(type(record["tracks"]) is list and len(record["tracks"]) == len(expected), "track count")
    seen = set()
    for row in record["tracks"]:
        require(type(row) is dict and set(row) == {"track_id", "lev_sha256", "counts", *KINDS}, "track shape")
        tid = row["track_id"]
        require(tid in expected and tid not in seen, "unknown or duplicate track")
        seen.add(tid)
        t, package = by_id[tid], packages.get(by_id[tid].get("package_id"))
        inv = inventory(t, package)
        require(row["lev_sha256"] == inv["lev_sha256"] and row["counts"] == inv["counts"], "revision or counts mismatch")
        for f, kind in enumerate(KINDS):
            numbers = row[kind]
            standalone = any(e["kind"] == "track" and e.get("track_id") == tid and e["id"] in
                             {p["entry_id"] for p in plan["pads"]} for e in plan["entries"])
            pool = eligible(t, f, record, plan.get("item_boxes") if standalone else None, package)
            require(type(numbers) is list and all(type(n) is int for n in numbers) and numbers == sorted(set(numbers)), "ordinal shape")
            count = min(len(pool), record["itemboxsanity"]) if f == 0 else len(pool) if record["wumpasanity"] & f else 0
            require(len(numbers) == count and set(numbers) <= set(pool), "ordinal pick mismatch")
