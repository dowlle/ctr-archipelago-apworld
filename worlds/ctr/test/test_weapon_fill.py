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
        assert (crate["pos"], crate["rot"][1]) == (spot["pos"], spot["rot_y"])
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
        weapons[0]["rank_source"] = "default_usf"  # spot 1 is start ground, rank 0
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
    # Each fallback box needs at least its seated crate's frozen rank.
    for check, n in zip(own, range(1, 10)):
        rank = weapons[content_item_boxes.physical_seat(track, plan["item_boxes"], frozen, n) - 1]["rank"]
        assert check.get("boost", 0) >= rank
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


def test_restore_uses_the_rooms_own_spots_not_the_catalog():
    """A fill room keeps its seats when Day's spot file later changes."""
    from unittest.mock import patch
    wire = json.loads(json.dumps(make_world(day_options(track_fill=True, itemboxsanity=50, item_box_count=50),
                                            seed=11).fill_slot_data()))
    with patch.dict(box_spots.CUSTOM_FILES, {}, clear=False):
        box_spots.CUSTOM_FILES.pop(DAY, None)
        restored = make_world(day_options(), seed=999, passthrough=wire)
    assert json.loads(json.dumps(restored.fill_slot_data())) == wire


def test_donor_ruling_may_carry_any_rank():
    fill = copy.deepcopy(track_fill.bundled(DAY, DAY_LEV, 3))
    fill["families"]["weapon_crates"][1].update(rank=0, rank_source="donor_ruling")
    fill["fill_sha256"] = track_fill.payload_sha256(fill)
    track_fill.validate(fill, DAY_LEV, 3)


def test_catalog_correction_and_tampered_seats_on_restore():
    from unittest.mock import patch
    wire = json.loads(json.dumps(make_world(day_options(track_fill=True, itemboxsanity=50, item_box_count=50),
                                            seed=11).fill_slot_data()))
    # A later correction of one Day spot leaves the saved room restorable.
    corrected = copy.deepcopy(box_spots.CUSTOM_FILES[DAY])
    corrected["doc"]["spots"][1]["pos"] = [0, 0, 0]
    with patch.dict(box_spots.CUSTOM_FILES, {DAY: corrected}):
        restored = make_world(day_options(), seed=999, passthrough=wire)
    assert json.loads(json.dumps(restored.fill_slot_data())) == wire
    # A saved seat moved off its crate mixes seats and spots: refused.
    forged = copy.deepcopy(wire)
    box = next(c for c in forged["content_plan"]["checks"] if c.get("kind") == "box" and c["owner"] == TRACK)
    box["spot"]["pos"][0] += 7
    with pytest.raises(OptionError):
        make_world(day_options(), seed=999, passthrough=forged)


def test_families_are_chosen_on_their_own():
    acid = "e2a9e1daaf89ebd499d657462d19ae9c0be488f18c04d1e391d4abb6e5e791a6"
    fill = track_fill.bundled("acid-lake", acid, 3)
    assert len(fill["families"]["time_crates"]) == 29 and len(fill["families"]["weapon_crates"]) == 12
    time_only = track_fill.select_families(fill, time=True, weapons=False)
    assert time_only["families"]["weapon_crates"] == [] and len(time_only["families"]["time_crates"]) == 29
    assert track_fill.validate(time_only, acid, 3) is time_only
    weapons_only = track_fill.select_families(fill, time=False, weapons=True)
    assert weapons_only["relic_targets"] is None and len(weapons_only["families"]["weapon_crates"]) == 12
    track_fill.validate(weapons_only, acid, 3)
    assert track_fill.select_families(fill, time=True, weapons=True) is fill
    assert track_fill.select_families(fill, time=False, weapons=False) is None


# ── WF1b: filled crates are item sources (dowlle, 2026-11-26 10:48 CET) ───
# "Yes, they need to count for the logic for both": Itemsanity and Hit
# Character route from a filled track, with the crate's boost rank. A crate
# an AP box takes over is no item source in that room.

from .. import content_global_checks


def day_only(**extra):
    options = day_options(track_fill=True, itemsanity=True, hit_character=True, accessibility="full", **extra)
    options["content_pool"]["tracks"]["retail"] = []
    options["item_pool"]["base"].update(trophies=0, tokens=dict.fromkeys(("red", "green", "blue", "yellow", "purple"), 0),
                                        relics=dict.fromkeys(("sapphire", "gold", "platinum"), 0))
    return options


def global_routes(plan, kind):
    return [c for c in plan["checks"] if c["kind"] == kind]


@pytest.mark.parametrize("count", [15, 50, 0])
def test_day_only_pool_with_itemsanity_generates(count):
    # Count 0: no AP box seats, Weapon Crate checks give the start its room.
    extra = dict(item_box_count=count) if count else dict(box_locations=False, itemboxsanity=50)
    world, plan = plan_of(day_only(**extra))
    package, = plan["packages"]
    track, = plan["tracks"]
    free = content_item_boxes.free_fill_ranks(track, plan.get("item_boxes"), package)
    # The cap of 15 keeps at least 12 of Day's 27 crates free.
    assert len(free) == (27 if count == 0 else 12)
    for kind in ("itemsanity", "hit"):
        checks = global_routes(plan, kind)
        assert checks and all(r["entry_id"] == "entry/" + TRACK for c in checks for r in c["routes"])
    # Seated crates are no item source: the free crates' ranks are the
    # unseated rows of the fill, and the route takes the lowest.
    if count:
        picked = set(content_item_boxes.spot_sets(plan["item_boxes"])[TRACK]["picked"])
        rows = track_fill.package_weapons(package)
        assert free == [rows[n - 1]["rank"] for n in range(1, 28) if n not in picked]
    assert content_global_checks.crate_rank(track, {package["id"]: package}, plan.get("item_boxes")) == min(free)
    content_plan.validate(json.loads(json.dumps(plan)))
    distribute_items_restrictive(world.multiworld)
    assert world.multiworld.fulfills_accessibility(CollectionState(world.multiworld))


def test_switch_off_day_only_pool_with_itemsanity_still_refuses():
    options = day_only()
    options["track_fill"] = False
    with pytest.raises(OptionError, match="itemsanity needs at least one Trophy Race"):
        make_world(options, seed=0)


def test_fully_seated_fallback_track_is_no_route_until_a_crate_is_free():
    """Tribal Trials 1.0.0 seats a fallback box on each of its 9 filled
    crates at Item Box Count 15, so it holds no item source; at count 5 four
    crates stay free and it routes both families."""
    package = crateless_package("tribal-trials", TRIBAL_LEV, "Tribal Trials")
    base = dict(custom=[package], track_fill=True, itemsanity=True, hit_character=True,
                progressive_boost="shared_global")
    _, plan = plan_of(box_options(**base))
    track = next(t for t in plan["tracks"] if t.get("package_id") == plan["packages"][0]["id"])
    for kind in ("itemsanity", "hit"):
        assert not [r for c in global_routes(plan, kind) for r in c["routes"] if r["entry_id"] == "entry/" + track["id"]]
    _, plan = plan_of(box_options(item_box_count=5, **base))
    frozen, = plan["packages"]
    free = content_item_boxes.free_fill_ranks(track, plan["item_boxes"], frozen)
    seats = {content_item_boxes.physical_seat(track, plan["item_boxes"], frozen, n) for n in range(1, 6)}
    assert len(free) == 4 and len(seats) == 5
    for kind in ("itemsanity", "hit"):
        assert [r for c in global_routes(plan, kind) for r in c["routes"] if r["entry_id"] == "entry/" + track["id"]]
    content_plan.validate(json.loads(json.dumps(plan)))


def test_crate_rank_is_the_lowest_free_rank_and_needs_the_boost_chain():
    package = dict(id="p", capabilities=dict(weapon_crates=0),
                   fill=dict(families=dict(weapon_crates=[dict(pos=[0, 0, 0], rot=[0, 0, 0], rank=2),
                                                         dict(pos=[9, 0, 0], rot=[0, 0, 0], rank=1)])))
    track = dict(id="t", origin="custom", package_id="p")
    assert content_global_checks.crate_rank(track, {"p": package}) == 1
    assert content_global_checks.crate_rank(dict(track, origin="retail"), {"p": package}) == 0
    # No fill: a crateless package stays no route, as before WF1b.
    assert content_global_checks.crate_rank(track, {"p": dict(package, fill=None)}) is None
    assert content_global_checks.crate_rank(track, {"p": dict(package, capabilities=dict(weapon_crates=4))}) == 0
    entries = [dict(id="e", kind="track", track_id="t")]
    plan = dict(capability=dict(boost_mode=1), entries=entries, tracks=[track], packages=[package],
                pads=[dict(id="pad:1", entry_id="e")])
    route = dict(entry_id="e", mode="trophy", leg_id=None, own_pad_id="pad:1")
    assert content_global_checks.route_crate_ranks(plan, [route]) == [1]
    assert content_global_checks.route_crate_ranks(dict(plan, capability={}), [route]) == [0]


def test_itemsanity_on_a_usf_only_free_set_needs_usf():
    """With every free crate at rank 2, a filled track's Itemsanity route
    needs Progressive Boost 2 for the pad's racer, on top of the weapon."""
    world, plan = plan_of(day_only(box_locations=False, itemboxsanity=50))
    package, = plan["packages"]
    for crate in package["fill"]["families"]["weapon_crates"]:
        assert crate["rank"] in (0, 2)
    # Day has Boost 0 crates, so its routes need no boost.
    assert content_global_checks.crate_rank(plan["tracks"][0], {package["id"]: package}) == 0
    usf = copy.deepcopy(package)
    for crate in usf["fill"]["families"]["weapon_crates"]:
        crate["rank"] = 2
    assert content_global_checks.crate_rank(plan["tracks"][0], {package["id"]: usf}) == 2


def test_missing_fruit_counts_still_give_weapon_crate_checks():
    """The client's YAML export states weapon_crates but not fruit_crates or
    loose_fruit; a filled track still gets its Weapon Crate checks."""
    package = crateless_package("tribal-trials", TRIBAL_LEV, "Tribal Trials")
    for key in ("fruit_crates", "loose_fruit"):
        package["capabilities"].pop(key)
    world, plan = plan_of(box_options(custom=[package], track_fill=True, itemboxsanity=50, item_box_count=5,
                                      progressive_boost="shared_global", accessibility="full"))
    frozen, = plan["packages"]
    track = next(t for t in plan["tracks"] if t.get("package_id") == frozen["id"])
    row = sanity_row_of(plan, track["id"])
    assert row["counts"] == [9, 0, 0] and len(row["weapon_crate"]) == 4
    content_plan.validate(json.loads(json.dumps(plan)))
    distribute_items_restrictive(world.multiworld)
    assert world.multiworld.fulfills_accessibility(CollectionState(world.multiworld))
    # Without the fill the same descriptor has no sanity inventory.
    _, plan = plan_of(box_options(custom=[package], itemboxsanity=50, item_box_count=5,
                                  progressive_boost="shared_global"))
    assert not [r for r in (plan.get("sanity") or {}).get("tracks", ()) if r["track_id"] == track["id"]]


DARK_RUINS_LEV = "8728705c81dacb2ace83a7ecc54e38ffdedde8696932656d37b9533b8ba7530b"


def test_usf_only_free_crates_put_usf_on_the_route():
    """Dark Ruins 1.0.1's 12 filled crates all need USF (rank 2). At Item Box
    Count 5 seven stay free, so Itemsanity on that track needs the weapon and
    Progressive Boost 2; the plan routes from it and validates."""
    package = crateless_package("dark-ruins", DARK_RUINS_LEV, "Dark Ruins")
    package["laps"] = 3
    options = box_options(custom=[package], track_fill=True, itemsanity=True, hit_character=True,
                          item_box_count=5, progressive_boost="shared_global", accessibility="full")
    world, plan = plan_of(options)
    frozen, = plan["packages"]
    track = next(t for t in plan["tracks"] if t.get("package_id") == frozen["id"])
    assert content_item_boxes.free_fill_ranks(track, plan["item_boxes"], frozen) == [2] * 7
    assert content_global_checks.crate_rank(track, {frozen["id"]: frozen}, plan["item_boxes"]) == 2
    use = next(c for c in plan["checks"] if c["kind"] == "itemsanity")
    mine = [r for r in use["routes"] if r["entry_id"] == "entry/" + track["id"]]
    assert mine
    assert content_global_checks.route_crate_ranks(plan, mine) == [2] * len(mine)
    content_plan.validate(json.loads(json.dumps(plan)))
    distribute_items_restrictive(world.multiworld)
    assert world.multiworld.fulfills_accessibility(CollectionState(world.multiworld))


def test_installed_rules_need_the_free_crates_rank():
    """Day-only seed 254 seats all eight Boost 0 crates, so its 12 free
    filled crates all need USF (rank 2): Itemsanity: Bomb and every
    ordinary Hit check open with the Bomb and two Progressive Boosts, not
    with one, and never without the Bomb."""
    world = make_world(day_only(), seed=254)
    plan = world.ctr_content_plan
    package, = plan["packages"]
    track, = plan["tracks"]
    assert set(content_item_boxes.free_fill_ranks(track, plan["item_boxes"], package)) == {2}
    from .. import progressive_capability
    mw, player = world.multiworld, world.player
    boost = progressive_capability.boost_item_name()
    bomb = mw.get_location("Itemsanity: Bomb", player)
    hit = next(mw.get_location(c["display_name"], player) for c in plan["checks"]
               if c["kind"] == "hit" and all(r["mode"] not in ("boss_race", "boss_cup") for r in c["routes"]))
    pool = [item for item in mw.itempool if item.player == player]
    progression = [item for item in pool if item.advancement and item.name not in (boost, "Bomb")]
    # The boosts stand pre-placed on box locations in this room.
    boosts = [loc.item for loc in mw.get_locations(player) if loc.item is not None and loc.item.name == boost]
    assert len(boosts) >= 2

    boosts_held = boosts

    def state_with(count, weapon=True):
        state = CollectionState(mw)
        for item in progression + boosts_held[:count]:
            state.collect(item, True)
        if weapon:
            state.collect(next(i for i in pool if i.name == "Bomb"), True)
        state.sweep_for_advancements(locations=[loc for loc in mw.get_locations(player) if loc.address is None])
        return state

    assert not bomb.can_reach(state_with(1))
    assert bomb.can_reach(state_with(2))
    assert not bomb.can_reach(state_with(2, weapon=False))
    assert not hit.can_reach(state_with(1)) and hit.can_reach(state_with(2))


def test_boss_routes_take_their_venues_rank():
    package = dict(id="p", capabilities=dict(weapon_crates=0),
                   fill=dict(families=dict(weapon_crates=[dict(pos=[0, 0, 0], rot=[0, 0, 0], rank=2)])))
    tracks = [dict(id="t", origin="custom", package_id="p"), dict(id="r", origin="retail")]
    entries = [dict(id="boss", kind="boss_race", track_id="t"),
               dict(id="cup", kind="boss_cup", legs=[dict(id="leg:0", track_id="t"), dict(id="leg:1", track_id="r")]),
               dict(id="retail-boss", kind="boss_race", track_id="r")]
    plan = dict(capability=dict(boost_mode=1), entries=entries, tracks=tracks, packages=[package], pads=[], checks=[])
    routes = [dict(entry_id="boss", mode="boss_race", leg_id=None), dict(entry_id="cup", mode="boss_cup", leg_id=None),
              dict(entry_id="retail-boss", mode="boss_race", leg_id=None)]
    assert content_global_checks.route_crate_ranks(plan, routes) == [2, 2, 0]


def test_boss_races_ignore_pad_seats_and_boss_cups_keep_them():
    """A boss race on a custom garage venue stands no AP box, so its pad's
    seats do not narrow the free crates; a boss cup leg may stand them."""
    from unittest import mock
    package = dict(id="p", capabilities=dict(weapon_crates=0),
                   fill=dict(families=dict(weapon_crates=[dict(pos=[0, 0, 0], rot=[0, 0, 0], rank=0),
                                                         dict(pos=[9, 0, 0], rot=[0, 0, 0], rank=2)])))
    tracks = [dict(id="t", origin="custom", package_id="p")]
    entries = [dict(id="e", kind="track", track_id="t"), dict(id="boss", kind="boss_race", track_id="t"),
               dict(id="cup", kind="boss_cup", legs=[dict(id="leg:0", track_id="t")])]
    plan = dict(capability=dict(boost_mode=1), entries=entries, tracks=tracks, packages=[package],
                pads=[dict(id="pad:1", entry_id="e")], checks=[], item_boxes=dict(box_count=15))
    seated = lambda track, record, pkg: [2] if record else [0, 2]  # the pad seats the rank-0 crate
    with mock.patch.object(content_item_boxes, "free_fill_ranks", seated):
        routes = [dict(entry_id="boss", mode="boss_race", leg_id=None), dict(entry_id="cup", mode="boss_cup", leg_id=None),
                  dict(entry_id="e", mode="trophy", leg_id=None)]
        assert content_global_checks.route_crate_ranks(plan, routes) == [0, 2, 2]
