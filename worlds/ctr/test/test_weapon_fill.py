"""WF1: Arabian Heights Day's copied weapon crate layout becomes real weapon
crates under the experimental track fill switch.

dowlle, 2026-11-26: the weapon crates go on exactly Night's 27
positions, and the published Item Box numbers 1 to 27 stay on them as fallback
AP seats until Day has its own AP placements, at most 15 per track.
"""

import copy
import json

import pytest
from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError

from .. import box_spots, content_item_boxes, content_plan, named_tracks, sanity, track_fill
from .test_content_item_boxes import box_options, boxes, btp, first_world
from .test_content_plan import make_world

DAY = "arabian-heights-day"
DAY_LEV = "a84dcf7132574b3b2cdd3d51ac4511cd68bbdd38e77ea31208be2029bbb72900"
NIGHT_LEV = "8093b663855d3fd0096fd2980a85bc6efe334c0aff250e8a33eea11909e5c21c"
TRACK = f"custom/{DAY}/1.0.0"


def day_package():
    package = btp(0)
    package.update(content_id=DAY, display_name="Arabian Heights Day", id=f"package/{DAY}/1.0.0",
                   revision="1.0.0", evidence=[], laps=3)
    package["files"][0]["sha256"] = DAY_LEV
    return package


def day_options(**extra):
    extra.setdefault("progressive_boost", "shared_global")
    return box_options(custom=[day_package()], **extra)


def plan_of(options, seed=None):
    world = first_world(options) if seed is None else make_world(options, seed=seed)
    return world, world.ctr_content_plan


def sanity_row(plan):
    return next(row for row in plan["sanity"]["tracks"] if row["track_id"] == TRACK)


def test_day_fill_is_nights_layout_with_the_published_spot_ranks():
    fill = track_fill.bundled(DAY, DAY_LEV, 3)
    weapons = fill["families"]["weapon_crates"]
    spots = box_spots.CUSTOM_FILES[DAY]["doc"]["spots"]
    assert fill["families"]["time_crates"] == [] and fill["relic_targets"] is None
    assert [d["lev_sha256"] for d in fill["donors"]] == [NIGHT_LEV]
    assert len(weapons) == 27 == fill["counts"]["weapon_crates"]
    for number, (spot, crate) in enumerate(zip(spots, weapons), 1):
        assert spot["number"] == number and spot["provenance"] == ["a6-16-night-weapon-crates", number]
        assert (crate["pos"], crate["rot_y"]) == (spot["pos"], spot["rot_y"])
        assert track_fill.RANK_NAMES[crate["rank"]] == spot.get("needs", "usf")
    # The fill holds no time crates, so Day gains no Relic Race.
    assert track_fill.bundled(DAY, DAY_LEV, 5) is None


@pytest.mark.parametrize("change", ["time_targets", "duplicate", "rank_source", "family"])
def test_weapon_rows_are_closed(change):
    fill = copy.deepcopy(track_fill.bundled(DAY, DAY_LEV, 3))
    weapons = fill["families"]["weapon_crates"]
    if change == "time_targets":
        fill["relic_targets"] = dict(sapphire=3, gold=2, platinum=1, source="saphi", laps=3)
    elif change == "duplicate":
        weapons[1]["pos"] = list(weapons[0]["pos"])
    elif change == "rank_source":
        weapons[0]["rank_source"] = "default_usf"
    else:
        weapons[0]["model"] = 8
    fill["fill_sha256"] = track_fill.payload_sha256(fill)
    with pytest.raises(ValueError):
        track_fill.validate(fill, DAY_LEV, 3)


def test_switch_off_keeps_todays_day_room():
    off = make_world(day_options(), seed=6).fill_slot_data()
    explicit_off = make_world(day_options(track_fill=False), seed=6).fill_slot_data()
    assert off == explicit_off
    assert off["schema_version"] == 18
    package, = off["content_plan"]["packages"]
    assert "fill" not in package and package["capabilities"]["weapon_crates"] == 0


@pytest.mark.parametrize("count", [15, 50])
def test_fill_room_seats_at_most_15_published_numbers_on_real_crates(count):
    world, plan = plan_of(day_options(track_fill=True, item_box_count=count, itemboxsanity=50,
                                      accessibility="full"))
    wire = world.fill_slot_data()
    assert wire["schema_version"] == wire["ctr_options"]["schema_version"] == track_fill.SCHEMA
    package, = plan["packages"]
    assert track_fill.FEATURE in plan["required_features"]
    assert package["capabilities"]["weapon_crates"] == 0, "the measured LEV count is unchanged"
    assert len(package["fill"]["families"]["weapon_crates"]) == 27
    record = content_item_boxes.spot_sets(plan["item_boxes"])[TRACK]
    assert record["pool"] == 27 and len(record["picked"]) == 15
    own = boxes(plan, TRACK)
    assert [c["spot"]["number"] for c in own] == record["picked"]
    assert [c["location"] for c in own] == [named_tracks.location_code(3, f"item_box_{n}") for n in record["picked"]]
    assert [c["location"] for c in own] == [35200619 + n for n in record["picked"]]
    # Sanity sees all 27 filled crates and leaves out exactly the seated ones.
    row = sanity_row(plan)
    assert row["counts"][0] == 27
    assert set(row["weapon_crate"]) == set(range(1, 28)) - set(record["picked"])
    checks = {c["display_name"]: c for c in plan["checks"] if c["kind"] == "weapon_crate" and c["owner"] == TRACK}
    for n in row["weapon_crate"]:
        rank = package["fill"]["families"]["weapon_crates"][n - 1]["rank"]
        assert checks[f"Arabian Heights Day: Weapon Crate {n}"].get("boost", 0) == rank
    distribute_items_restrictive(world.multiworld)
    assert world.multiworld.fulfills_accessibility(CollectionState(world.multiworld))


def test_box_count_zero_leaves_all_27_crates_live():
    _, plan = plan_of(day_options(track_fill=True, item_box_count=0, itemboxsanity=50))
    package, = plan["packages"]
    assert len(track_fill.package_weapons(package)) == 27
    assert not plan.get("item_boxes")
    assert sanity_row(plan)["weapon_crate"] == list(range(1, 28))


def test_fill_room_restores_from_its_frozen_payload():
    wire = make_world(day_options(track_fill=True, itemboxsanity=50), seed=11).fill_slot_data()
    wire = json.loads(json.dumps(wire))
    restored = make_world(day_options(), seed=999, passthrough=wire)
    assert json.loads(json.dumps(restored.fill_slot_data())) == wire
    forged = copy.deepcopy(wire)
    forged["content_plan"]["packages"][0]["fill"]["families"]["weapon_crates"][0]["pos"][0] += 1
    with pytest.raises(OptionError):
        make_world(day_options(), seed=999, passthrough=forged)


def test_weapon_fill_requires_a_crateless_lev():
    package = day_package()
    package["capabilities"]["weapon_crates"] = 4
    _, plan = plan_of(box_options(custom=[package], track_fill=True))
    assert "fill" not in plan["packages"][0]
    package["capabilities"]["weapon_crates"] = 0
    package["files"][0]["sha256"] = "01" * 32
    _, plan = plan_of(box_options(custom=[package], track_fill=True))
    assert "fill" not in plan["packages"][0]


def test_seated_ordinals_follow_exact_position_and_angle():
    package = dict(fill=track_fill.bundled(DAY, DAY_LEV, 3))
    spots = box_spots.spots_by_number(box_spots.CUSTOM_FILES[DAY])
    assert track_fill.seated_ordinals(package, [spots[3], spots[21]]) == [3, 21]
    moved = dict(spots[3], rot_y=spots[3]["rot_y"] + 1)
    assert track_fill.seated_ordinals(package, [moved]) == []
    assert sanity.fill_needs({"origin": "custom"}, dict(package, capabilities={"weapon_crates": 0}), 0, 1) == {"needs": "none"}


# ── Part 2: the BX3 tracks ─────────────────────────────────────────────────

TRIBAL_LEV = "a7b4aef448047524863c032d8121f65f74012f741d64a6ad80f2b07456fcbfcd"


def crateless_package(key, lev, name):
    package = btp(0)
    package.update(content_id=key, display_name=name, id=f"package/{key}/1.0.0", revision="1.0.0",
                   evidence=[], laps=3, uuid="11111111-2222-4333-8444-000000000777")
    package["files"][0]["sha256"] = lev
    package["capabilities"].update(weapon_crates=0, fruit_crates=0, loose_fruit=0)
    return package


def test_fallback_track_seats_at_most_15_boxes_on_filled_crates():
    """Tribal Trials 1.0.0 has no AP spots of its own: its 9 filled crates
    take the fallback seats, and sanity leaves exactly those out."""
    package = crateless_package("tribal-trials", TRIBAL_LEV, "Tribal Trials")
    world, plan = plan_of(box_options(custom=[package], track_fill=True, itemboxsanity=50,
                                      progressive_boost="shared_global", accessibility="full"))
    frozen, = plan["packages"]
    weapons = track_fill.package_weapons(frozen)
    assert len(weapons) == 9 and frozen["capabilities"]["weapon_crates"] == 0
    track = next(t for t in plan["tracks"] if t.get("package_id") == frozen["id"])
    assert track["id"] not in content_item_boxes.spot_sets(plan["item_boxes"])
    own = boxes(plan, track["id"])
    assert len(own) == 9 and all("spot" not in c for c in own)
    seats = {content_item_boxes.physical_seat(track, plan["item_boxes"], frozen, n) for n in range(1, 10)}
    assert seats == set(range(1, 10))
    # All nine crates are seated, so sanity counts them and picks none.
    row = sanity_row_of(plan, track["id"])
    assert row["counts"][0] == 9 and row["weapon_crate"] == []
    distribute_items_restrictive(world.multiworld)
    assert world.multiworld.fulfills_accessibility(CollectionState(world.multiworld))


def test_authored_spots_keep_every_filled_crate():
    """Arctic Alleyway 1.0.0 has dowlle's AP spots: its AP boxes stand there
    and all 16 filled weapon crates stay ordinary crates."""
    lev = "a31f66f5ac7d0fcf1a99cfa4af0d956e655f51a3fbc27b3511e24e23f139dda9"
    package = crateless_package("arctic-alleyway", lev, "Arctic Alleyway")
    _, plan = plan_of(box_options(custom=[package], track_fill=True, itemboxsanity=50,
                                  progressive_boost="shared_global"))
    frozen, = plan["packages"]
    assert len(track_fill.package_weapons(frozen)) == 16
    track = next(t for t in plan["tracks"] if t.get("package_id") == frozen["id"])
    record = content_item_boxes.spot_sets(plan["item_boxes"]).get(track["id"])
    if record is not None:  # the named-block catalogue track
        assert len(record["picked"]) == 15
        assert content_item_boxes.seated_crates(track, plan["item_boxes"], frozen) == []
        assert sanity_row_of(plan, track["id"])["weapon_crate"] == list(range(1, 17))


def test_held_weak_layouts_and_big_forest_carry_no_weapon_fill():
    index = json.loads((box_spots.pkgutil.get_data(box_spots.__package__, "data/track_fill/index.json")))
    for key in ("mario-circuit-1", "neonstadion", "the-dairy-track", "big-forest"):
        assert key not in index


def sanity_row_of(plan, track_id):
    return next(row for row in plan["sanity"]["tracks"] if row["track_id"] == track_id)
