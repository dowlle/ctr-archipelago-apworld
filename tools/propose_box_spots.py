#!/usr/bin/env python3
"""Propose custom AP box spots from a LEV using the native editor's levtool parser."""

import argparse
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys


# Native QuadBlockFlags and COLL_FIXED_QUADBLK_TestTriangles.
NO_RESPONSE, TRIGGER, KILL, DOOR, GROUND = 0x10, 0x40, 0x200, 0x400, 0x1000
WATER_TERRAINS = {4, 13}
CELLS = ((0, 4, 5), (4, 6, 5), (6, 4, 1), (5, 6, 2),
         (8, 6, 7), (7, 3, 8), (1, 7, 6), (2, 6, 8))
PICKUP_MODELS = {2, 7, 8, 0x5C, 0x64, 0x65, 0x93, 0x94, 0x95}
LINE_WIDTH, OFF_LINE_LIMIT = 450, 900
PICKUP_CLEARANCE, PAD_CLEARANCE, GRID_CLEARANCE, SPOT_CLEARANCE = 350, 350, 900, 600
BOX_RADIUS, BOX_HEIGHT = 95, 175


def ground_height(x, z, points):
    """Project an XZ point onto a native high-LOD collision triangle."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    det = (bx - ax) * (cz - az) - (cx - ax) * (bz - az)
    if det == 0:
        return None
    u = ((x - ax) * (cz - az) - (z - az) * (cx - ax)) / det
    v = ((bx - ax) * (z - az) - (bz - az) * (x - ax)) / det
    if min(u, v, 1 - u - v) < -1e-8:
        return None
    return ay + u * (by - ay) + v * (cy - ay)


def lerp(a, b, fraction):
    return tuple(x + fraction * (y - x) for x, y in zip(a, b))


def segment_fraction(point, a, b):
    delta = tuple(y - x for x, y in zip(a, b))
    length_squared = sum(v * v for v in delta)
    if not length_squared:
        return 0
    projection = sum((p - x) * v for p, x, v in zip(point, a, delta))
    return max(0, min(1, projection / length_squared))


def xz(point):
    return point[0], point[2]


def clip_height(polygon, height, direction):
    """Clip a triangle or polygon to one side of a horizontal plane."""
    result = []
    for a, b in zip(polygon[-1:] + polygon[:-1], polygon):
        inside_a = direction * (a[1] - height) >= 0
        inside_b = direction * (b[1] - height) >= 0
        if inside_a != inside_b:
            result.append(lerp(a, b, (height - a[1]) / (b[1] - a[1])))
        if inside_b:
            result.append(b)
    return result


def near_surface(point, triangle, radius, below, above):
    """Test a horizontal disc swept through a vertical interval against a triangle."""
    y = point[1]
    if triangle.top < y - below or triangle.bottom > y + above:
        return False
    polygon = clip_height(clip_height(list(triangle.points), y - below, 1), y + above, -1)
    if not polygon:
        return False
    p = xz(point)
    for i in range(1, len(polygon) - 1):
        if ground_height(*p, (polygon[0], polygon[i], polygon[i + 1])) is not None:
            return True
    for a, b in zip(polygon[-1:] + polygon[:-1], polygon):
        a, b = xz(a), xz(b)
        if math.dist(p, lerp(a, b, segment_fraction(p, a, b))) <= radius:
            return True
    return False


@dataclass(frozen=True)
class Triangle:
    points: tuple
    quad: int
    checkpoint: int
    flags: int
    terrain: int
    slope: float
    bottom: int
    top: int

    @property
    def pad(self):
        # Trigger triangles use bit flags in the terrain byte, including 1 and 2 for turbo.
        return bool(self.flags & TRIGGER and self.terrain & 3)

    @property
    def hazard(self):
        return bool(self.flags & KILL or (not self.flags & TRIGGER and self.terrain in WATER_TERRAINS))

    @property
    def drivable(self):
        return bool(self.flags & GROUND and not self.flags & (NO_RESPONSE | TRIGGER | DOOR)
                    and not self.hazard and self.slope >= 0.8)


class Mesh:
    cell_size = 512

    def __init__(self, lev):
        self.triangles = []
        self.cells = defaultdict(list)
        self.neighbors = defaultdict(list)
        edges = {}
        for quad in lev.quadblocks:
            ids = quad["vertex_indices"]
            for cell in CELLS[:4] if ids[2] == ids[3] else CELLS:
                points = tuple(lev.vertices[ids[i]]["position"] for i in cell)
                a, b, c = points
                ux, uy, uz = (y - x for x, y in zip(a, b))
                vx, vy, vz = (y - x for x, y in zip(a, c))
                normal_y = uz * vx - ux * vz
                length = math.hypot(uy * vz - uz * vy, normal_y, ux * vy - uy * vx)
                if not length:
                    continue
                x, y, z = zip(*points)
                triangle = Triangle(points, quad["index"], quad["checkpoint_index"], quad["flags"],
                                    quad["terrain"], abs(normal_y) / length, min(y), max(y))
                index = len(self.triangles)
                self.triangles.append(triangle)
                for key in self.grid(min(x), max(x), min(z), max(z)):
                    self.cells[key].append(index)
                if triangle.drivable:
                    for edge in ((a, b), (b, c), (c, a)):
                        key = tuple(sorted(edge))
                        earlier = edges.setdefault(key, index)
                        if earlier != index:
                            self.neighbors[earlier].append(index)
                            self.neighbors[index].append(earlier)

    def grid(self, left, right, near, far):
        for x in range(left // self.cell_size, right // self.cell_size + 1):
            for z in range(near // self.cell_size, far // self.cell_size + 1):
                yield x, z

    def nearby(self, point, radius=0):
        x, z = map(math.floor, xz(point))
        ids = set()
        for key in self.grid(x - radius, x + radius, z - radius, z + radius):
            ids.update(self.cells.get(key, ()))
        return sorted(ids)

    def road_at(self, point, tolerance, checkpoints, *, allow_triggers=False):
        for index in self.nearby(point):
            tri = self.triangles[index]
            usable = tri.drivable or (allow_triggers and tri.pad and tri.slope >= 0.8 and not tri.hazard)
            if usable and tri.checkpoint in checkpoints:
                y = ground_height(*xz(point), tri.points)
                if y is not None and abs(point[1] - y) <= tolerance:
                    yield index

    def clearance(self, point):
        for index in self.nearby(point, PAD_CLEARANCE):
            tri = self.triangles[index]
            if tri.pad and near_surface(point, tri, PAD_CLEARANCE, 220, 220):
                return False
            if tri.hazard and near_surface(point, tri, BOX_RADIUS, 16, BOX_HEIGHT):
                return False
            if not tri.flags & (NO_RESPONSE | TRIGGER):
                # Check walls at the base, and roofs / overpasses at box height.
                offset = 0 if tri.slope < 0.8 or not tri.flags & GROUND else 38
                if near_surface(point, tri, BOX_RADIUS, -offset, BOX_HEIGHT):
                    return False
        return True

    def connected_to(self, indices):
        visited = set(indices)
        stack = list(visited)
        while stack:
            for neighbor in self.neighbors[stack.pop()]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        return visited


def lap_route(checkpoints):
    order = []
    seen = set()
    index = 0
    while index not in seen and index < len(checkpoints):
        order.append(index)
        seen.add(index)
        index = checkpoints[index]["links"]["forward"]
    if index != 0 or len(order) < 3:
        raise ValueError("checkpoint 0 must lead around a closed lap")
    distances = [checkpoints[index]["distance_to_finish"] for index in order]
    if distances[-1] < 0 or any(a <= b for a, b in zip(distances, distances[1:])):
        raise ValueError("main checkpoint cycle must have decreasing distance to finish")
    return order


def corridor(mesh, checkpoints, order):
    """Trace support along the main route and mark possible gaps without guessing a boost tier."""
    supported = set()
    gaps = []
    segments = {}
    length = checkpoints[0]["distance_to_finish"]
    for previous, index, following in zip(order[-1:] + order[:-1], order, order[1:] + order[:1]):
        cp, nxt = checkpoints[index], checkpoints[following]
        a, b = cp["position"], nxt["position"]
        start_distance = length - cp["distance_to_finish"]
        end_distance = length - nxt["distance_to_finish"] if following else length
        segments[index] = a, b, start_distance, end_distance
        steps = max(1, math.ceil(math.dist(a, b) / 100))
        missing = 0
        recent_pad = None
        for step in range(steps + 1):
            point = lerp(a, b, step / steps)
            ground = list(mesh.road_at(point, 265, {previous, index, following}, allow_triggers=True))
            supported.update(ground)
            if any(mesh.triangles[i].pad for i in ground):
                recent_pad = step
            missing = 0 if ground else missing + 1
            if missing == 3:
                fraction = (step - 2) / steps
                pad_before = recent_pad is not None and step - recent_pad <= 12
                gaps.append(dict(checkpoint=index, following=following,
                                 distance=start_distance + fraction * (end_distance - start_distance),
                                 position=[round(v) for v in lerp(a, b, fraction)], pad_before=pad_before))
    return segments, mesh.connected_to(supported), gaps


def pickup_positions(lev):
    for instance in lev.instances:
        if 0 < instance.model_offset <= len(lev.data) - 18:
            model, = struct.unpack_from("<H", lev.data, instance.model_offset + 16)
            if model in PICKUP_MODELS:
                yield instance.position


def candidates(mesh, segments, connected, gaps, pickups, grid):
    first_gap = gaps[0]["distance"] if gaps else math.inf
    for index in sorted(connected):
        tri = mesh.triangles[index]
        if not tri.drivable or tri.checkpoint not in segments:
            continue
        a, b, start, end = segments[tri.checkpoint]
        x, _, z = (round(sum(axis) / 3) for axis in zip(*tri.points))
        height = ground_height(x, z, tri.points)
        if height is None:
            continue
        pos = (x, round(height), z)
        fraction = segment_fraction(pos, a, b)
        on_route = lerp(a, b, fraction)
        lateral = math.dist(xz(pos), xz(on_route))
        vertical = abs(pos[1] - on_route[1])
        if lateral > OFF_LINE_LIMIT or vertical > 265:
            continue
        if (any(math.dist(pos, p) < PICKUP_CLEARANCE for p in pickups)
                or any(math.dist(pos, p) < GRID_CLEARANCE for p in grid)
                or not mesh.clearance(pos)):
            continue
        distance = start + fraction * (end - start)
        off_line = lateral > LINE_WIDTH
        flags = []
        if distance >= first_gap:
            flags.append("Past a possible gap on the checkpoint route. Check the required boost.")
        if off_line:
            flags.append("Off the racing corridor. Check the approach and shortcut requirement.")
        elif not all(any(mesh.road_at(lerp(pos, on_route, fraction), 150, {tri.checkpoint},
                                     allow_triggers=True)) for fraction in (0.25, 0.5, 0.75)):
            flags.append("The direct approach to the racing corridor was not measured. Check driveability.")
        yield dict(pos=list(pos), quad=tri.quad, triangle=index, checkpoint=tri.checkpoint, distance=distance,
                   lateral=round(lateral), vertical=round(vertical), off_line=off_line, flags=flags,
                   rot_y=round(math.atan2(b[0] - a[0], b[2] - a[2]) * 4096 / math.tau) % 4096)


def choose_spread(pool, count, lap_length, existing):
    """Spread on-line boxes over the whole lap first, then add up to 30% off-line."""
    chosen = []
    occupied = [row["pos"] for row in existing]

    def pick(off_line, bins):
        if not bins:
            return
        buckets = [[] for _ in range(bins)]
        for row in pool:
            if row["off_line"] == off_line:
                bucket = min(bins - 1, int(row["distance"] * bins / lap_length))
                buckets[bucket].append(row)
        for i, bucket in enumerate(buckets):
            middle = (i + 0.5) * lap_length / bins
            bucket.sort(key=lambda row: (abs(row["distance"] - middle), bool(row["flags"]),
                                         row["lateral"], row["triangle"]))
            for row in bucket:
                if all(math.dist(row["pos"], pos) >= SPOT_CLEARANCE for pos in occupied):
                    chosen.append(row)
                    occupied.append(row["pos"])
                    break

    off_line = int(count * 0.3) if any(row["off_line"] for row in pool) else 0
    pick(False, count - off_line)
    pick(True, min(off_line, int(len(chosen) * 3 / 7)))
    return sorted(chosen, key=lambda row: (row["distance"], row["triangle"]))


def propose(lev, track, count, existing=None):
    """Return the version 1 candidate file and a separate audit report."""
    if not 1 <= count <= 50:
        raise ValueError("max spots must be from 1 to 50")
    doc = deepcopy(existing) if existing is not None else {
        "format": "ctr-ap-box-spots", "version": 1, "track": track, "spots": [], "retired": [],
    }
    existing_track = doc["track"]
    if (existing_track.get("track_key") != track["track_key"]
            or set(existing_track["lev_sha256"]) != set(track["lev_sha256"])):
        raise ValueError("existing spots must match the track key and exact LEV pin")
    # Adding coordinates measured on one LEV to a multi-revision file needs review on every pin.
    next_number = max([0, *doc["retired"], *(row["number"] for row in doc["spots"])]) + 1
    order = lap_route(lev.checkpoints)
    mesh = Mesh(lev)
    segments, connected, gaps = corridor(mesh, lev.checkpoints, order)
    pickups = list(pickup_positions(lev))
    grid = [lev.checkpoints[0]["position"],
            *(spawn["position"] for spawn in lev.driver_spawns if any(spawn["position"]))]
    pool = list(candidates(mesh, segments, connected, gaps, pickups, grid))
    lap_length = lev.checkpoints[0]["distance_to_finish"]
    chosen = choose_spread(pool, min(count, max(0, 51 - next_number)), lap_length, doc["spots"])
    for number, row in enumerate(chosen, next_number):
        row["number"] = number
        row["reason"] = ("Off-line ground connected to the checkpoint corridor." if row["off_line"]
                         else "Ground within the checkpoint corridor, chosen to spread spots over the lap.")
        spot = dict(number=number, pos=row["pos"], rot_y=row["rot_y"], source="tool proposal")
        if not row["flags"]:
            spot["needs"] = "none"
        row["needs"] = spot.get("needs", "usf")
        doc["spots"].append(spot)
    return doc, dict(track=track, lap_checkpoints=order, lap_length=lap_length, gaps=gaps,
                     candidates=len(pool), pickup_keepouts=len(pickups), spots=chosen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lev", type=Path)
    parser.add_argument("track_key")
    parser.add_argument("name")
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--levtool-root", type=Path, required=True, help="native editor checkout containing levtool")
    parser.add_argument("--max-spots", type=int, default=50, help="maximum number of new spots")
    parser.add_argument("--existing", type=Path, help="existing spot file to preserve and append to")
    args = parser.parse_args()
    sources = [args.lev, args.existing] if args.existing else [args.lev]
    paths = [*sources, args.output, args.report]
    if len({p.resolve() for p in paths}) != len(paths):
        parser.error("use separate paths for the inputs, spot output and report")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from worlds.ctr.box_spot_catalog import check_draft_file

    sys.path.insert(0, str(args.levtool_root))
    from levtool.format import LevFile

    try:
        raw = args.lev.read_bytes()
        lev = LevFile(raw, args.lev)
        if lev.errors:
            raise ValueError(f"LEV parser rejected geometry: {lev.errors[0]}")
        track = dict(kind="custom", track_key=args.track_key, name=args.name,
                     lev_sha256=[hashlib.sha256(raw).hexdigest()])
        existing = check_draft_file(json.loads(args.existing.read_text()), args.existing) if args.existing else None
        doc, report = propose(lev, track, args.max_spots, existing)
        check_draft_file(doc, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(doc, indent=2) + "\n")
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
