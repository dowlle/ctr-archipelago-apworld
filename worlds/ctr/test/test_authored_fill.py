"""JB1: a hand-placed weapon crate layout for N-Gage Jungle Boogie.

No version of the track has crates to copy, so the fill names an authored
source instead of a donor. It is held to the weapon-only rules of a ruled
donor: no time crates, no grid, no relic targets, and every crate ranked on
the target LEV alone.
"""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from .. import track_fill
from .test_content_item_boxes import box_options, btp, first_world
from .test_content_plan import make_world

JB = "jungle-boogie-n-gage"
JB_LEV = "ac968f6ce814ecbe67a7efd6e926f4fa7c59803c56e8f05a194156962ec0f906"
TRACK = f"custom/{JB}/1.0.0"
ROOT = Path(__file__).resolve().parents[3]


def jb_package(weapon_crates=0):
    package = btp(weapon_crates)
    package.update(content_id=JB, display_name="N-Gage Jungle Boogie", id=f"package/{JB}/1.0.0",
                   revision="1.0.0", evidence=[], laps=3)
    package["files"][0]["sha256"] = JB_LEV
    return package


def rehashed(fill):
    fill["fill_sha256"] = track_fill.payload_sha256(fill)
    return fill


def test_jungle_boogie_fill_is_the_authored_16_crate_layout():
    fill = track_fill.bundled(JB, JB_LEV, 3)
    weapons = fill["families"]["weapon_crates"]
    assert fill["donors"] == []
    assert fill["source"] == {"kind": "authored", "provenance": "jb1-jungle-boogie-n-gage"}
    assert len(weapons) == 16 == fill["counts"]["weapon_crates"]
    assert fill["families"]["time_crates"] == [] and fill["families"]["grid"] is None
    assert fill["relic_targets"] is None
    assert {(c["rank"], c["rank_source"]) for c in weapons} == {(0, "start_ground")}
    # Four rows of four, one angle per row.
    assert [len({c["rot"][1] for c in weapons[i:i + 4]}) for i in range(0, 16, 4)] == [1, 1, 1, 1]
    assert weapons[0]["pos"] == [2788, -169, -545]
    assert track_fill.bundled(JB, JB_LEV, 5) is None


def test_only_jungle_boogie_is_authored():
    root = ROOT / "worlds/ctr/data/track_fill"
    fills = {path.parent.name: json.loads(path.read_text()) for path in sorted(root.glob("*/*.json"))}
    assert [key for key, fill in fills.items() if "source" in fill or fill["donors"] == []] == [JB]


@pytest.mark.parametrize("change,message", [
    (lambda f: f.pop("source"), "record fields"),
    (lambda f: f["source"].update(kind="copied"), "authored track fill source"),
    (lambda f: f["source"].update(provenance="Not A Key"), "authored track fill source"),
    (lambda f: f["source"].update(provenance="a" * 65), "authored track fill source"),
    (lambda f: f["source"].update(extra=1), "authored track fill source"),
    (lambda f: f.update(donors=[{"lev_sha256": "1" * 64, "road_sha256": "2" * 64,
                                 "kind": "identical", "overlap": 100000}]), "record fields"),
    (lambda f: f["families"]["weapon_crates"][0].update(rank_source="donor_ruling"), "ranked on the target"),
    (lambda f: f["families"]["weapon_crates"][0].update(rank=2), "weapon crate"),
    (lambda f: (f["families"].update(time_crates=[{"pos": [0, 0, 0], "type": 1}]),
                f["counts"].update(time_crates=1)), "ranked on the target"),
    (lambda f: (f["families"].update(grid=[{"pos": [0, 0, 0], "rot_y": 0}] * 8),
                f["counts"].update(grid=8)), "ranked on the target"),
    (lambda f: (f["families"].update(weapon_crates=[]), f["counts"].update(weapon_crates=0)), "set size"),
    (lambda f: f["families"]["weapon_crates"][1].update(pos=list(f["families"]["weapon_crates"][0]["pos"])),
     "weapon crate"),
    (lambda f: f.update(lev_sha256="f" * 64), "LEV hash"),
])
def test_authored_fill_is_held_to_the_weapon_only_rules(change, message):
    fill = copy.deepcopy(track_fill.bundled(JB, JB_LEV, 3))
    change(fill)
    with pytest.raises(ValueError, match=message):
        track_fill.validate(rehashed(fill), JB_LEV, 3)


def test_authored_fill_hash_covers_its_source():
    fill = copy.deepcopy(track_fill.bundled(JB, JB_LEV, 3))
    fill["source"]["provenance"] = "another-review"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        track_fill.validate(fill, JB_LEV, 3)


def test_donor_fills_still_refuse_a_source_or_no_donor():
    pin = "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900"
    fill = copy.deepcopy(track_fill.bundled("arabian-heights-day", pin, 3))
    fill["source"] = {"kind": "authored", "provenance": "jb1-jungle-boogie-n-gage"}
    with pytest.raises(ValueError, match="record fields"):
        track_fill.validate(rehashed(fill), pin, 3)
    fill.pop("source")
    fill["donors"] = []
    with pytest.raises(ValueError, match="record fields"):
        track_fill.validate(rehashed(fill), pin, 3)


def test_fill_room_carries_16_crates_on_a_crateless_lev():
    world = first_world(box_options(custom=[jb_package()], track_fill=True, itemboxsanity=50))
    package, = world.ctr_content_plan["packages"]
    assert package["fill"] == track_fill.bundled(JB, JB_LEV, 3)
    assert package["capabilities"]["weapon_crates"] == 0
    assert package["capabilities"]["relic"] is False and "relic_targets" not in package
    assert track_fill.FEATURE in world.ctr_content_plan["required_features"]
    assert world.fill_slot_data()["schema_version"] == track_fill.SCHEMA


@pytest.mark.parametrize("weapon_crates", [None, 4])
def test_no_fill_without_a_measured_crateless_lev(weapon_crates):
    world = first_world(box_options(custom=[jb_package(weapon_crates)], track_fill=True))
    assert "fill" not in world.ctr_content_plan["packages"][0]


def test_switch_off_keeps_todays_room():
    options = box_options(custom=[jb_package()])
    off = make_world(options, seed=3).fill_slot_data()
    assert make_world(dict(options, track_fill=False), seed=3).fill_slot_data() == off
    assert "fill" not in off["content_plan"]["packages"][0]
    assert off["schema_version"] == 18


def test_generator_keeps_authored_files():
    spec = importlib.util.spec_from_file_location("generate_ctr_track_fill",
                                                  ROOT / "tools/generate-ctr-track-fill.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    kept = tool.authored_fills(ROOT / "worlds/ctr/data/track_fill", track_fill)
    (path, (fill, laps)), = kept.items()
    assert path == Path(JB) / (JB_LEV[:16] + ".json")
    assert laps == 3 and fill == track_fill.bundled(JB, JB_LEV, 3)
