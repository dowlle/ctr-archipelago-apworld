#!/usr/bin/env python3
"""Check race-mode AP box positions against pinned custom track LEVs.

Run from an Archipelago environment. Set PYTHONPATH to a checkout with the
CTR editor's levtool. The local LEV index maps SHA-256 to file path. Pass a
registry snapshot as --registry and supplemental mode descriptors as
--descriptor when a package uses a separate LEV for its Relic Race.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RACE_MODELS = {2, 7, 8}
LETTER_MODELS = {147, 148, 149}
TIME_MODELS = {92, 100, 101}
MODELS = {"trophy": RACE_MODELS, "ctr": RACE_MODELS | LETTER_MODELS, "relic": TIME_MODELS}
REGISTRY_MODES = {"arcade": "trophy", "ctr_challenge": "ctr", "relic_race": "relic"}
OVERLAP = 100


def read(path):
    return json.loads(Path(path).read_text())


def lev_pin(files):
    if isinstance(files, dict):
        return files.get("lev", {}).get("sha256")
    return next((row["sha256"] for row in files if row["role"] == "lev"), None)


def audit(registry, descriptors, lev_index):
    from levtool.format import LevFile
    from worlds.ctr import box_spots, content_item_boxes, crate_exclusions, destinations

    entries = {}
    for track in registry["tracks"]:
        for revision in track["revisions"]:
            pin = lev_pin(revision.get("files", {}))
            modes = {REGISTRY_MODES[m]: pin for m in revision["modes"] if m in REGISTRY_MODES}
            if modes and pin:
                entries[track["track_key"], revision["revision"], pin] = modes
    for desc in descriptors:
        pin = lev_pin(desc["files"])
        enabled = desc["capabilities"]
        modes = entries.setdefault((desc["content_id"], desc["revision"], pin), {})
        if enabled.get("arcade"):
            modes["trophy"] = pin
        if enabled.get("ctr_tokens"):
            modes["ctr"] = pin
        if enabled.get("relic"):
            modes["relic"] = lev_pin(desc.get("relic_files", [])) or pin

    def instances(pin):
        path = Path(lev_index[pin])
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != pin:
            raise ValueError(f"LEV hash mismatch for {pin}")
        return LevFile.from_path(path).instances

    hits, missing, covered = set(), [], []
    for (key, revision, pin), modes in sorted(entries.items()):
        if not modes:
            continue
        absent = {main for main in {pin, *modes.values()} if main not in lev_index}
        if absent:
            missing.append((key, revision, sorted(absent)))
            continue
        main = instances(pin)
        crates = [(i, o) for i, o in enumerate(main) if o.model_id == 8]
        omitted = crate_exclusions.ordinals(pin)
        limit = content_item_boxes.seat_limit(dict(content_id=key, revision=revision,
            capabilities={"weapon_crates": len(crates)}, files=[dict(role="lev", sha256=pin)]))
        seats = [(ord_, index, obj) for ord_, (index, obj) in enumerate(crates, 1)
                 if ord_ <= limit and ord_ not in omitted]
        authored = box_spots.CUSTOM_FILES.get(destinations.canonical_track_key(key))
        if authored and pin in authored["doc"]["track"]["lev_sha256"]:
            layouts = [[(s["number"], s["pos"], None) for s in authored["doc"]["spots"]]]
        else:
            replacements = box_spots.SEAT_SPOTS.get(pin, {})
            layouts = []
            for count in range(1, 1 + min(len(seats), 15)):
                layout = []
                for number, s in enumerate(content_item_boxes.seat_indices(len(seats), count), 1):
                    ordinal, index, obj = seats[s]
                    replacement = replacements.get(str(ordinal))
                    layout.append((number, replacement["pos"], None) if replacement
                                  else (number, obj.position, index))
                layouts.append(layout)
        for mode, mode_pin in sorted(modes.items()):
            table = main if mode_pin == pin else instances(mode_pin)
            objects = [(i, obj) for i, obj in enumerate(table) if obj.model_id in MODELS[mode]]
            covered.append((key, revision, mode))
            for boxes in layouts:
                for number, pos, seat in boxes:
                    for i, obj in objects:
                        if i == seat and mode_pin == pin:
                            continue
                        distance = math.dist(pos, obj.position)
                        if distance <= OVERLAP:
                            hits.add((key, revision, pin, mode, number, tuple(pos), i,
                                      obj.model_id, tuple(obj.position), round(distance, 1)))
                for (a, pos, _), (b, other, _) in itertools.combinations(boxes, 2):
                    distance = math.dist(pos, other)
                    if distance <= OVERLAP:
                        hits.add((key, revision, pin, mode, a, tuple(pos), b, "AP", tuple(other), round(distance, 1)))
    return dict(covered=covered, missing=missing, hits=sorted(hits, key=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--lev-index", required=True, type=Path)
    parser.add_argument("--descriptor", action="append", default=[], type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--allow-missing", action="store_true", help="Report missing revisions without treating them as failures")
    args = parser.parse_args()
    report = audit(read(args.registry), [read(p) for p in args.descriptor], read(args.lev_index))
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(output)
    else:
        print(output, end="")
    print(f"{len(report['covered'])} revision/mode pairs, {len(report['missing'])} missing revisions, "
          f"{len(report['hits'])} overlaps", file=sys.stderr)
    return int(bool(report["hits"] or (report["missing"] and not args.allow_missing)))


if __name__ == "__main__":
    raise SystemExit(main())
