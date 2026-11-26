#!/usr/bin/env python3
"""Generate slice-1 fill files from registry, OV1 inventory and local LEVs.

The geometry tools directory supplies BX1's analyze.py and its dependencies.
The local LEV index and capability sheet are inputs and are never packaged.
Run with --check to re-derive and compare the complete output directory.

WF1 weapon crates: --weapon-targets names each target LEV, its donor, the
package lap count (or null for the capability sheet's), the fit rule and the
rank of every donor crate, and optionally donor ordinals to exclude. The donor's
weapon crates (model 8, instance-table order, signed yaw) are copied at their
exact position and angle. The target must hold no weapon crate. The fit is
OV1's 512-unit neighbourhood rule ("strict"), keeping the crates that pass, or
"ruled" where dowlle placed a whole layout: every crate must then stand on
ground at the donor's height, and the report lists the strict rule's misses. A weapon family
joins any time crate family of the same LEV in one file.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import struct
import sys
from decimal import Decimal
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TIME_COLUMN = "Relic times (sapphire / gold / platinum)"
TYPES = ("time1", "time2", "time3")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_fill_module():
    spec = importlib.util.spec_from_file_location("track_fill", ROOT / "worlds/ctr/track_fill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def target_times(row):
    text = row.get(TIME_COLUMN, "")
    if not text:
        return None
    source = "saphi" if text.endswith(" (Saphi)") else "author"
    values = []
    for clock in text.removesuffix(" (Saphi)").split(" / "):
        minutes, colon, seconds = clock.partition(":")
        try:
            time = Decimal(minutes) * 60 + Decimal(seconds) if colon else Decimal(minutes)
        except ArithmeticError:
            return None
        values.append(round(time * 960))
    if len(values) != 3 or not values[0] > values[1] > values[2] > 0:
        return None
    return dict(zip(("sapphire", "gold", "platinum"), values), source=source)


def pins(registry):
    for track in registry["tracks"]:
        for revision in track["revisions"]:
            lev = revision.get("files", {}).get("lev", {}).get("sha256")
            if lev:
                yield track["track_key"], revision["revision"], lev


def generate(args, fill_module, analyze, np):
    inventory = {row["sha"]: row for row in read_json(args.inventory)}
    paths = read_json(args.lev_paths)
    with args.pack_rows.open(encoding="utf-8", newline="") as source:
        rows = {row["LEV sha256"]: row for row in csv.DictReader(source)}
    rows.update({row["LEV sha256"]: row for row in read_json(args.sheet_rows)})
    registry_pins = sorted(set(pins(read_json(args.registry))))

    @lru_cache(maxsize=16)
    def geometry(sha):
        path = Path(paths[sha])
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError(f"LEV hash mismatch for {sha}")
        return analyze.geometry(path)

    @lru_cache(maxsize=16)
    def collision(sha):
        path = Path(paths[sha])
        data, vertices, quads, flags = analyze.mesh_data(path)
        valid = np.all(quads < len(vertices), axis=1)
        vertices = vertices[quads[valid]].astype(np.int32)
        # Reflect split, gravity, collision response, trigger, kill plane,
        # door, ground and collision surface flags from namespace_Level.h.
        collision_flags = flags[valid] & 0x3657
        keys = []
        if len(quads):
            mesh, = struct.unpack_from("<I", data, analyze.LEVEL_FIELDS["mesh_offset"])
            quad_offset, = struct.unpack_from("<I", data, mesh + 12)
            # QuadBlock layout in namespace_Level.h. Draw-order bit 31
            # controls back-face collision; the other draw bits are visual.
            collision_fields = np.dtype({
                "names": ("draw_order_low", "bounds", "terrain", "normal_y", "normal_shift", "normal_dividends"),
                "formats": ("<u4", "V12", "u1", "i1", "i1", "V20"),
                "offsets": (0x14, 0x2C, 0x38, 0x3B, 0x3F, 0x48),
                "itemsize": analyze.QUADBLOCK_SIZE,
            })
            physics = np.frombuffer(data, dtype=collision_fields, count=len(quads), offset=quad_offset)[valid]
            keys = [(quad.tobytes(), int(flag), bool(fields["draw_order_low"] & 0x80000000),
                     bytes(fields["bounds"]), int(fields["terrain"]), int(fields["normal_y"]),
                     int(fields["normal_shift"]), bytes(fields["normal_dividends"]))
                    for quad, flag, fields in zip(vertices, collision_flags, physics)]
        return vertices, keys, analyze.ground(path)

    def neighbourhood(sha, pos):
        vertices, keys, ground = collision(sha)
        dx = vertices[:, :, 0] - pos[0]
        dz = vertices[:, :, 2] - pos[2]
        distance2 = dx.astype(np.int64)**2 + dz.astype(np.int64)**2
        nearby = np.flatnonzero(np.any(distance2 <= 512**2, axis=1))
        distance = analyze.measure(pos, *ground)["distance"]
        return {keys[i] for i in nearby}, distance

    def safe_position(donor, target, pos, ruled=False):
        nearby, height = neighbourhood(donor, pos)
        target_nearby, target_height = neighbourhood(target, pos)
        grounded = math.isfinite(height) and abs(target_height - height) <= 20
        # A ruled layout keeps the ruled exact positions; only the ground under
        # each crate must still be there at the same height.
        return grounded if ruled else bool(nearby and nearby == target_nearby and grounded)

    def donor_info(target, one):
        source = geometry(one)
        target_geo = geometry(target)
        if source["road_sha"] and source["road_sha"] == target_geo["road_sha"]:
            kind, overlap = "identical", 1.0
        else:
            comparison = analyze.compare(source, target_geo)
            if not comparison or comparison["road"] < 0.95:
                return None
            kind, overlap = "similar>=0.95", comparison["road"]
        return dict(lev_sha256=one, road_sha256=source["road_sha"], kind=kind, overlap=round(overlap * 100000))

    def matched_donors(target, candidates):
        matches = [match for one in candidates if (match := donor_info(target, one))]
        return sorted(matches, key=lambda row: (row["kind"], -row["overlap"], row["lev_sha256"]))

    def laps_for(sha):
        value = str(rows.get(sha, {}).get("Laps", ""))
        return int(value) if value.isdecimal() else None

    def published_targets(target, candidates, laps):
        with_targets = [one for one in candidates if laps_for(one) == laps
                        and target_times(rows[one])]
        local = target_times(rows.get(target, {}))
        if local:
            same_times = [one for one in with_targets if inventory[one]["time"] and target_times(rows[one]) == local]
            matches = matched_donors(target, same_times)
            return local, matches[0] if matches else None
        for match in matched_donors(target, with_targets):
            source = match["lev_sha256"]
            return target_times(rows[source]), match
        return None, None

    def weapon_crates(sha):
        data = Path(paths[sha]).read_bytes()[4:]
        word = lambda offset: struct.unpack_from("<I", data, offset)[0]
        crates = []
        # Level.numInstances and ptrInstDefs; InstDef is 0x40 bytes with the
        # model pointer at 0x10, position at 0x30 and rotation at 0x36.
        for at in range(word(0x10), word(0x10) + 0x40 * word(0x0C), 0x40):
            model = word(at + 0x10)
            if model and struct.unpack_from("<h", data, model + 16)[0] == 8:
                crates.append((list(struct.unpack_from("<3h", data, at + 0x30)),
                               struct.unpack_from("<3h", data, at + 0x36)[1]))
        return crates

    output, report = {}, []
    for key, revision, target in registry_pins:
        record = inventory.get(target)
        if not record or not record["ok"] or not record["tt"] or record["time"]:
            continue
        siblings = [one for one, version in inventory.items() if one != target and version["ok"]
                    and (version["key"] == record["key"] or version["road_sha"] == record["road_sha"])]
        candidates = [one for one in siblings if inventory[one]["time"]]
        if not candidates:
            continue
        laps = laps_for(target)
        entry = dict(track=key, revision=revision, lev_sha256=target, laps=laps)
        report.append(entry)
        targets, times_donor = published_targets(target, siblings, laps) if laps else (None, None)
        donors = matched_donors(target, candidates)
        if times_donor:
            donors.sort(key=lambda row: (row["kind"], -row["overlap"], row["lev_sha256"] != times_donor["lev_sha256"]))
        for donor in donors:
            sha = donor["lev_sha256"]
            points = geometry(sha)["points"]
            crates = [dict(pos=list(pos), type=kind)
                      for kind, family in enumerate(TYPES, 1) for pos in points[family]]
            if len(crates) != inventory[sha]["time"]:
                raise ValueError(f"native and geometry time crate counts differ for {sha}")
            passed = sum(safe_position(sha, target, crate["pos"]) for crate in crates)
            entry.update(kept=passed, total=len(crates), donor=sha, overlap=donor["overlap"])
            if passed != len(crates):
                continue
            if not targets:
                entry["status"] = "no verified relic targets"
                break
            provenance = [donor]
            if times_donor and times_donor["lev_sha256"] != sha:
                provenance.append(times_donor)
            families = dict(fill_module.EMPTY_FAMILIES, grid=None, time_crates=crates, weapon_crates=[])
            payload = dict(schema=1, lev_sha256=target, generator=dict(name="ctr-track-fill", version=1),
                           donors=provenance, families=families,
                           counts={name: len(value or ()) for name, value in families.items()},
                           relic_targets=dict(targets, laps=laps))
            payload["fill_sha256"] = fill_module.payload_sha256(payload)
            fill_module.validate(payload, target, laps)
            path = Path(key) / (target[:16] + ".json")
            if path in output and output[path]["lev_sha256"] != target:
                raise ValueError(f"ambiguous LEV prefix in {path}")
            output[path] = payload
            timing_sha = times_donor["lev_sha256"] if times_donor else target
            entry.update(status="generated", targets=targets, targets_lev_sha256=timing_sha,
                         targets_revision=inventory[timing_sha]["version"])
            break
        else:
            entry["status"] = "incomplete crate set" if donors else "no same-road crate donor"
    for spec in read_json(args.weapon_targets)["targets"] if args.weapon_targets else ():
        key, target, donor = spec["track"], spec["target"], spec["donor"]
        laps = spec["laps"] or laps_for(target)
        entry = dict(track=key, family="weapon_crates", lev_sha256=target, donor=donor, fit=spec["fit"])
        report.append(entry)
        if not laps:
            entry["status"] = "no verified lap count"
            continue
        info = donor_info(target, donor)
        if inventory[target]["weapon"] or weapon_crates(target):
            entry["status"] = "target already has weapon crates"
            continue
        crates = weapon_crates(donor)
        if not info or len(crates) != inventory[donor]["weapon"] or len(crates) != len(spec["ranks"]):
            entry["status"] = "no same-road donor or donor inventory differs"
            continue
        # Donor ordinals an earlier review dropped from this layout stay out.
        excluded = set(spec.get("exclude", ()))
        passed = [n not in excluded and safe_position(donor, target, pos, spec["fit"] == "ruled")
                  for n, (pos, _) in enumerate(crates, 1)]
        strict = [safe_position(donor, target, pos) for pos, _ in crates]
        entry.update(kept=sum(passed), total=len(crates), overlap=info["overlap"],
                     dropped=[n for n, ok in enumerate(passed, 1) if not ok],
                     strict_fit_failed=[n for n, ok in enumerate(strict, 1) if not ok])
        if spec["fit"] == "ruled" and not all(passed):
            entry["status"] = "ruled layout no longer fits"
            continue
        weapons = [dict(pos=pos, rot_y=rot_y, rank=rank["rank"], rank_source=rank["rank_source"])
                   for (pos, rot_y), rank, ok in zip(crates, spec["ranks"], passed) if ok]
        if not weapons:
            entry["status"] = "no crate passes the fit"
            continue
        path = Path(key) / (target[:16] + ".json")
        payload = output.get(path) or dict(
            schema=1, lev_sha256=target, generator=dict(name="ctr-track-fill", version=1), donors=[],
            families=dict(fill_module.EMPTY_FAMILIES, grid=None, time_crates=[], weapon_crates=[]),
            relic_targets=None)
        if payload["lev_sha256"] != target:
            raise ValueError(f"ambiguous LEV prefix in {path}")
        if all(one["lev_sha256"] != donor for one in payload["donors"]):
            payload["donors"].append(info)
        payload["families"]["weapon_crates"] = weapons
        payload["counts"] = {name: len(value or ()) for name, value in payload["families"].items()}
        payload.pop("fill_sha256", None)
        payload["fill_sha256"] = fill_module.payload_sha256(payload)
        fill_module.validate(payload, target, laps)
        output[path] = payload
        entry.update(status="generated", laps=laps)
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("geometry-tools", "inventory", "lev-paths", "sheet-rows", "pack-rows", "registry", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--weapon-targets", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.geometry_tools.resolve()))
    import analyze
    import numpy

    output, report = generate(args, load_fill_module(), analyze, numpy)
    catalogue = {}
    laps = {}
    for entry in report:
        if entry["status"] == "generated" and laps.setdefault(entry["lev_sha256"], entry["laps"]) != entry["laps"]:
            raise ValueError(f"time and weapon families disagree on laps for {entry['lev_sha256']}")
    for path, fill in sorted(output.items()):
        pin = fill["lev_sha256"]
        catalogue.setdefault(path.parent.name, {})[pin] = {"laps": laps[pin], "fill_sha256": fill["fill_sha256"]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.check:
        existing = {p.relative_to(args.output): read_json(p) for p in args.output.glob("*/*.json")}
        if existing != output or read_json(args.output / "index.json") != catalogue:
            parser.exit(1, "track fill files differ from regenerated data\n")
    else:
        for path, fill in output.items():
            path = args.output / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(fill, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (args.output / "index.json").write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
    print(f"{len(output)} fill files, {len({path.parent for path in output})} tracks")


if __name__ == "__main__":
    main()
