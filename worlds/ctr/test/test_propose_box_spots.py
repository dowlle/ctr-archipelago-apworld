"""Synthetic LEV geometry for the offline AP box authoring tool."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools.propose_box_spots import GROUND, KILL, NO_RESPONSE, TRIGGER, Mesh, ground_height, propose
from ..box_spot_catalog import SpotFileError, check_draft_file
from ..box_spots import check_file


TRACK = dict(kind="custom", track_key="fixture", name="Fixture", lev_sha256=["a" * 64])


def add_quad(lev, x, z, width, length, checkpoint, *, flags=GROUND, terrain=0, y=0):
    corners = ((0, 0), (2, 0), (0, 2), (2, 2), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2))
    start = len(lev.vertices)
    lev.vertices.extend(dict(position=(x + dx * width // 2, y, z + dz * length // 2)) for dx, dz in corners)
    lev.quadblocks.append(dict(index=len(lev.quadblocks), vertex_indices=tuple(range(start, start + 9)),
                               flags=flags, terrain=terrain, checkpoint_index=checkpoint))


@pytest.fixture
def lev():
    positions = [(0, 0, 0), (6000, 0, 0), (6000, 0, 6000), (0, 0, 6000)]
    checkpoints = [dict(position=point, links={"forward": (i + 1) % 4}, distance_to_finish=24000 - 6000 * i)
                   for i, point in enumerate(positions)]
    track = SimpleNamespace(checkpoints=checkpoints, vertices=[], quadblocks=[], instances=[],
                            driver_spawns=[{"position": (300, 0, 0)}])
    for i in range(6):
        add_quad(track, i * 1000, -1000, 1000, 2000, 0)
        add_quad(track, 5000, i * 1000, 2000, 1000, 1)
        add_quad(track, i * 1000, 5000, 1000, 2000, 2)
        add_quad(track, -1000, i * 1000, 2000, 1000, 3)
    return track


def test_deterministic_and_spread_in_lap_order(lev):
    doc, report = propose(lev, TRACK, 16)
    assert (doc, report) == propose(lev, TRACK, 16)
    assert check_draft_file(doc)
    with pytest.raises(SpotFileError, match="missing or unknown source_family"):
        check_file(doc)
    assert 8 <= len(doc["spots"]) <= 16
    assert {row["checkpoint"] for row in report["spots"]} == {0, 1, 2, 3}
    distances = [row["distance"] for row in report["spots"]]
    assert distances == sorted(distances)
    assert 0 < sum(row["off_line"] for row in report["spots"]) <= 0.3 * len(doc["spots"])


def test_snap_to_ground_and_avoid_hazards_and_grid(lev):
    # One slab defines a kill plane above otherwise valid racing ground.
    add_quad(lev, 3000, -1000, 1000, 2000, 0, flags=GROUND | KILL, y=5)
    add_quad(lev, 6900, 1000, 800, 3000, 1, flags=GROUND | NO_RESPONSE, y=10)
    add_quad(lev, 2000, 6000, 1500, 1500, 2, terrain=4)
    add_quad(lev, -1000, 2300, 2000, 400, 3, flags=TRIGGER, terrain=2)
    doc, report = propose(lev, TRACK, 36)
    assert len(doc["spots"]) >= 8
    mesh = Mesh(lev)
    for row in report["spots"]:
        x, y, z = row["pos"]
        triangle = mesh.triangles[row["triangle"]]
        assert triangle.drivable
        assert ground_height(x, z, triangle.points) == pytest.approx(y, abs=0.5)
        assert not (2905 <= x <= 4095 and -1095 <= z <= 1095)
        assert not (-1350 <= x <= 1350 and 1950 <= z <= 3050)
        assert (x - 300) ** 2 + z ** 2 >= 900 ** 2


def test_gap_retains_careful_default(lev):
    # Remove a full checkpoint-width tile so the trace must cross a gap.
    lev.quadblocks[12]["flags"] = GROUND | KILL
    doc, report = propose(lev, TRACK, 16)
    assert report["gaps"]
    with_gap = [row["number"] for row in report["spots"] if row["distance"] >= report["gaps"][0]["distance"]]
    assert with_gap
    assert all("needs" not in spot for spot in doc["spots"] if spot["number"] in with_gap)


def test_append_preserves_existing_numbers_and_retired_holes(lev):
    base, _ = propose(lev, TRACK, 5)
    base["spots"][0]["number"] = 47
    base["retired"] = [4, 48]
    base["spots"] = [spot for spot in base["spots"] if spot["number"] != 4]
    snapshot = deepcopy(base)
    doc, report = propose(lev, TRACK, 50, base)
    assert base == snapshot
    assert doc["spots"][:len(base["spots"])] == base["spots"]
    assert doc["retired"] == base["retired"]
    assert [row["number"] for row in report["spots"]] == [49, 50]
    assert check_draft_file(doc)
    with pytest.raises(ValueError, match="exact LEV pin"):
        propose(lev, dict(TRACK, lev_sha256=["b" * 64]), 50, base)


def test_open_checkpoint_chain_is_rejected(lev):
    lev.checkpoints[-1]["links"]["forward"] = 255
    with pytest.raises(ValueError, match="closed lap"):
        propose(lev, TRACK, 10)
