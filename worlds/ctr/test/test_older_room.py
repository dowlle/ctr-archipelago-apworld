"""A saved room from before TV World and North Pole gained named blocks."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from Options import OptionError

from .. import box_spots
from .test_content_plan import make_world


def saved_room():
    return json.loads((Path(__file__).parent / "fixtures" / "older-room.json").read_text())


def test_restore_after_promotion_and_spot_file_changes():
    wire = saved_room()
    plan = wire["content_plan"]
    assert plan["room_compatibility"] == 1
    # A text-only edit changes the file digest, while the old room still
    # has the same spot numbers, coordinates and effective logic.
    retail_files = {key: dict(entry, sha256="0" * 64) for key, entry in box_spots.RETAIL_FILES.items()}
    with patch.object(box_spots, "RETAIL_FILES", retail_files):
        assert make_world({}, passthrough=wire).fill_slot_data() == wire
        legacy = copy.deepcopy(wire)
        del legacy["content_plan"]["room_compatibility"]
        assert make_world({}, passthrough=legacy).fill_slot_data() == legacy

    # Format 1 also contains enough to restore when a spot file is removed.
    with patch.object(box_spots, "RETAIL_FILES", {}):
        assert make_world({}, passthrough=wire).fill_slot_data() == wire
        with pytest.raises(OptionError, match=r"generated with .*this build is .*box spot files"):
            make_world({}, passthrough=legacy)


def test_room_still_needs_consistent_codes_and_spot_numbers():
    room = saved_room()
    trophy = next(check for check in room["content_plan"]["checks"]
                  if check["owner"].startswith("custom/tv-world/") and check["kind"] == "trophy")
    trophy["location"] = 35215600
    with pytest.raises(OptionError, match="check registry or route ownership mismatch"):
        make_world({}, passthrough=room)
    room = saved_room()
    box = next(check for check in room["content_plan"]["checks"] if "spot" in check)
    box["spot"]["number"] = box["spot"]["number"] % 50 + 1
    with pytest.raises(OptionError, match="box spot number"):
        make_world({}, passthrough=room)
    room = saved_room()
    room["content_plan"]["room_compatibility"] = 2
    with pytest.raises(OptionError, match=r"generated with .*this build is .*room_compatibility"):
        make_world({}, passthrough=room)


def test_format_does_not_admit_unreviewed_physical_pickup_rules():
    room = saved_room()
    room["content_plan"]["item_boxes"]["pickup_rules"] = ["custom/fixture-loop/2.1"]
    with pytest.raises(OptionError, match="unsupported physical pickup revision"):
        make_world({}, passthrough=room)
