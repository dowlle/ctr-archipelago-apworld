"""Track fill admission, opt-in generation, and frozen room restoration."""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from Options import OptionError

from .. import content_plan, track_fill
from .test_content_plan import make_world
from .test_custom_packages import named_fixture, options_with


def fill_options():
    descriptor = named_fixture()
    descriptor.update(id="package/tv-world/1.0.0", revision="1.0.0", laps=3)
    path = Path(__file__).resolve().parents[1] / "data/track_fill/tv-world/e55a14baab68d763.json"
    descriptor["files"][0]["sha256"] = json.loads(path.read_text())["lev_sha256"]
    options = options_with([descriptor])
    options["content_pool"]["tracks"]["modes"] = ["trophy", "relic"]
    return options


def test_bundled_fills_match_pins_and_hashes():
    root = Path(__file__).resolve().parents[1] / "data/track_fill"
    files = sorted(root.glob("*/*.json"))
    index = json.loads((root / "index.json").read_text())
    assert files
    for path in files:
        fill = json.loads(path.read_text())
        assert path.stem == fill["lev_sha256"][:16]
        key, sha = path.parent.name, fill["lev_sha256"]
        assert track_fill.bundled(key, sha, index[key][sha]["laps"]) == fill
    with patch.object(track_fill.pkgutil, "get_data", side_effect=OSError("missing zip entry")):
        assert track_fill.bundled("ancient-lake", "a" * 64, 3) is None


def test_acid_lake_requires_verified_laps_and_catalogue_digest():
    key = "acid-lake"
    sha = "e2a9e1daaf89ebd499d657462d19ae9c0be488f18c04d1e391d4abb6e5e791a6"
    fill = track_fill.bundled(key, sha, 3)
    assert fill["counts"]["time_crates"] == 29
    assert track_fill.bundled(key, sha, 7) is None
    fill["families"]["time_crates"].pop()
    fill["counts"]["time_crates"] -= 1
    fill["fill_sha256"] = track_fill.payload_sha256(fill)
    with patch.object(track_fill.pkgutil, "get_data", return_value=track_fill.canonical_bytes(fill)):
        with pytest.raises(ValueError, match="generated catalogue pin"):
            track_fill.bundled(key, sha, 3)


@pytest.mark.parametrize("modes,laps", [(["trophy"], 3), (["trophy", "relic"], 7)])
def test_unused_fill_preserves_schema_18_slot_data(modes, laps):
    options = fill_options()
    options["content_pool"]["tracks"]["modes"] = modes
    options["content_pool"]["tracks"]["custom"][0]["laps"] = laps
    ordinary = make_world(options).fill_slot_data()
    opted_in = make_world(dict(options, track_fill=True)).fill_slot_data()
    assert opted_in == ordinary
    assert opted_in["schema_version"] == 18


def test_fill_room_is_frozen_and_schema_bump_is_conditional():
    wire = make_world(dict(fill_options(), track_fill=True)).fill_slot_data()
    assert wire["schema_version"] == wire["ctr_options"]["schema_version"] == 19
    package, = wire["content_plan"]["packages"]
    assert package["capabilities"]["relic"]
    assert wire["content_plan"]["required_features"][-1] == track_fill.FEATURE
    assert len(package["fill"]["families"]["time_crates"]) == 66
    ordinary = make_world(fill_options()).fill_slot_data()
    assert ordinary["schema_version"] == ordinary["ctr_options"]["schema_version"] == 18
    assert "fill" not in ordinary["content_plan"]["packages"][0]
    assert track_fill.FEATURE not in ordinary["content_plan"]["required_features"]
    with patch.object(track_fill, "bundled", side_effect=AssertionError("room must use its frozen fill")):
        restored = make_world(fill_options(), passthrough=wire)
    assert restored.ctr_content_plan["packages"][0] == package

    changed = copy.deepcopy(wire)
    changed_plan = changed["content_plan"]
    changed_plan["packages"][0]["laps"] = 7
    track, = (track for track in changed_plan["tracks"] if track.get("package_id") == package["id"])
    track["laps"] = 7
    with pytest.raises(OptionError, match="relic target laps differ"):
        make_world(fill_options(), passthrough=changed)

    for change in ("count", "pin", "digest", "feature"):
        plan = copy.deepcopy(wire["content_plan"])
        fill = plan["packages"][0]["fill"]
        if change == "count":
            fill["counts"]["time_crates"] += 1
        elif change == "pin":
            fill["lev_sha256"] = "e" * 64
        elif change == "digest":
            fill["families"]["time_crates"][0]["pos"][0] += 1
        else:
            plan["required_features"].remove(track_fill.FEATURE)
        with pytest.raises(OptionError):
            content_plan.validate(plan)
