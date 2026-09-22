"""Experimental content-plan generation, independent of legacy cup displacement.

The first executable profile is standalone Trophy races. Unsupported content
and check families fail explicitly while their native consumers are developed.
This is an internal integration path, not completion of the full rewrite.
"""
import copy
import json
import pkgutil

from BaseClasses import Region, Location
from Options import OptionError

from . import content_item_pool, characters, traps, wumpa_family
from .custom_tracks import BABY_T_PARK_PROFILES
from .Locations import CTR_LOCATION_IDS
from .warp_pad_logic import HUB_STATIC

SCHEMA = 17
PADS = json.loads(pkgutil.get_data(__package__, "data/warp_pad_ids.json"))["pads"]
RETAIL = {row["level_id"]: name.removesuffix(" Warp Pad") for name, row in PADS.items()
          if row["kind"] in ("race", "trial")}
ITEM_BY_CODE = {code: name for name, code in content_item_pool.ITEMS.items()}
LOCATION_BY_CODE = {code: name for name, code in CTR_LOCATION_IDS.items()}


def error(message):
    raise OptionError("CTR content plan: " + message)


def closed(value, keys, path):
    if not isinstance(value, dict) or set(value) - set(keys):
        error(f"{path} must be a mapping with only {', '.join(keys)}.")
    return value


def package_descriptor(profile):
    """Exact portable Package record, also consumed by the native registry."""
    revision = profile["package_version"]
    sizes = (2579256, 458808) if revision == "1.0.0" else (2558168, 458808)
    files = [dict(role=role, sha256=profile[role + "_sha256"], bytes=size,
                  format="ctr-" + role, format_version=1)
             for role, size in zip(("lev", "vrm"), sizes)]
    return dict(id="package/baby-t-park/" + revision, content_id="baby-t-park",
                uuid=profile["package_uuid"], revision=revision, display_name="Baby T Park",
                author="Lockheart", files=files,
                evidence=[dict(capability="trophy", file_hashes=[f["sha256"] for f in files],
                               verifier="ctr-managed-profile", revision=1, level="structural")])


PACKAGES = tuple(package_descriptor(p) for p in BABY_T_PARK_PROFILES)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def resolve_packages(raw):
    if not isinstance(raw, list) or len(raw) > 32:
        error("tracks.custom must be a list of at most 32 complete package descriptors.")
    result = []
    for package in raw:
        matched = next((known for known in PACKAGES if canonical(known) == canonical(package)), None)
        if matched is None:
            error("custom package does not match a supported complete immutable revision. "
                  "Export its Package descriptor; legacy Gem Cup placement descriptors are not this format.")
        if matched in result:
            error("the custom package list contains a duplicate revision.")
        result.append(copy.deepcopy(matched))
    return sorted(result, key=lambda p: p["id"])


def pad_registry():
    result = []
    for name, row in PADS.items():
        title = name.removesuffix(" Warp Pad")
        physical = row["level_id"]
        keys = HUB_STATIC[title][0][1] if HUB_STATIC[title] else 0
        hub = 25 if row["kind"] in ("trial", "cup") else 26 + keys
        result.append((physical, hub, keys))
    return sorted(result)


def _zero_count(value, path):
    if type(value) is int and value == 0:
        return
    if isinstance(value, dict) and set(value) == {"min", "max"} and all(type(v) is int and v == 0 for v in value.values()):
        return
    error(f"{path}: cups and crystals are not implemented in this experimental standalone profile; "
          "use an explicit zero count. The requested settings were not changed.")


def generate(world):
    o = world.options
    raw = closed(o.content_pool.value, ("preset", "tracks", "cups", "crystals", "bosses", "required_entries"), "content_pool")
    if raw.get("preset", "mixed") != "mixed":
        error("the experimental standalone profile currently requires preset: mixed.")
    tracks = closed(raw.get("tracks", {}), ("retail", "custom", "cortex_vortex", "modes", "overrides"), "tracks")
    if tracks.get("modes") != ["trophy"] or tracks.get("overrides", {}) != {}:
        error("the experimental profile currently supports explicit modes: [trophy] without overrides.")
    if tracks.get("cortex_vortex", False) is not False:
        error("Cortex Vortex content-plan routes are not implemented yet.")
    _zero_count(closed(raw.get("cups", {}), ("count",), "cups").get("count"), "cups.count")
    crystals = closed(raw.get("crystals", {}), ("pool", "count"), "crystals")
    _zero_count(crystals.get("count"), "crystals.count")
    arenas = crystals.get("pool", "all")
    if arenas != "all" and (not isinstance(arenas, list) or
            any(type(i) is not int or i not in (18, 19, 21, 23) for i in arenas) or len(set(arenas)) != len(arenas)):
        error("crystals.pool must be all or distinct retail arena IDs 18, 19, 21, 23.")
    bosses = closed(raw.get("bosses", {}), ("enabled",), "bosses")
    if bosses.get("enabled") is not False:
        error("the experimental profile needs explicit bosses: {enabled: false}; encounter routes are pending.")
    layout = closed(o.pad_layout.value, ("placement", "stages", "mode_order", "merge_trophy_ctr"), "pad_layout")
    if (layout.get("placement", "shuffle") != "shuffle" or
            layout.get("stages", "single") != "single" or
            layout.get("mode_order", "fixed") != "fixed" or
            layout.get("merge_trophy_ctr", False) is not False):
        error("the experimental Trophy profile currently needs shuffle placement, single stage, fixed order and merge off.")
    if o.oxide_goal.value != 3 or o.bosses_required_goal.value != 0 or o.gems_required_goal.value == 0:
        error("this profile needs Oxide disabled, no Boss goal, and a positive Gem goal.")
    pending = ("character_unlocks", "racer_locked_pads", "progressive_boost", "progressive_stats",
               "itemsanity", "lettersanity", "box_locations", "hit_character", "progressive_starting_wumpa",
               "podium_placement_checks", "wumpa_check", "turbo_grant", "tizi_helper")
    enabled = [name for name in pending if getattr(o, name).value]
    if enabled:
        error("these selected packs/checks do not have content-plan routes yet: " + ", ".join(enabled) + ".")
    if o.custom_tracks.value or o.cortex_vortex_track.value:
        error("legacy custom_tracks/cortex_vortex_track cannot be mixed with content_pool.")
    if o.plando_items.value or o.item_links.value:
        error("plando and item-link accounting are not validated for this experimental profile yet.")
    retail = tracks.get("retail", "all")
    if retail == "all":
        retail = sorted(RETAIL)
    if (not isinstance(retail, list) or any(type(i) is not int or i not in RETAIL for i in retail)
            or len(set(retail)) != len(retail)):
        error("tracks.retail must be all or a list of distinct retail engine track IDs 0..17.")
    packages = resolve_packages(tracks.get("custom", []))
    candidates = [dict(id=f"retail:{i}", origin="retail", retail_id=i, display_name=RETAIL[i],
                       laps=3, modes=["trophy"], capabilities=["trophy"], field_size=8) for i in sorted(retail)]
    for slot, package in enumerate(packages, 1):
        candidates.append(dict(id="custom/" + package["content_id"] + "/" + package["revision"],
                               origin="custom", package_id=package["id"], custom_slot=slot,
                               display_name=package["display_name"], laps=7, modes=["trophy"],
                               capabilities=["trophy"], field_size=8))
    required = raw.get("required_entries", [])
    ids = {t["id"] for t in candidates}
    if (not isinstance(required, list) or any(type(i) is not str or i not in ids for i in required)
            or len(set(required)) != len(required) or len(required) > 27):
        error("required_entries must be distinct eligible logical track IDs, fitting the 27 normal pads.")
    chosen = [t for t in candidates if t["id"] in required]
    optional = [t for t in candidates if t["id"] not in required]
    chosen += world.random.sample(optional, min(len(optional), 27 - len(chosen)))
    world.random.shuffle(chosen)
    registry = pad_registry()
    world.random.shuffle(registry)
    # Empty pads are valid, but a fresh Adventure must have a playable entry.
    # Keep content/counts and every physical gate unchanged. Only resolve an
    # otherwise dead shuffled layout by exchanging an occupied and open seat.
    if chosen and not any(keys == 0 for _, _, keys in registry[:len(chosen)]):
        source = world.random.randrange(len(chosen))
        destination = world.random.choice([i for i, (_, _, keys) in enumerate(registry) if keys == 0])
        registry[source], registry[destination] = registry[destination], registry[source]
    entries, pads, checks = [], [], []
    requirements = [dict(id="free", predicate=dict(op="always"))]
    requirements += [dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)]
    for index, (physical, hub, keys) in enumerate(registry):
        pad = dict(id=f"pad:{physical}", hub_id=f"hub:{hub}", kind="normal", entry_id=None,
                   entrance_req=f"keys:{keys}" if keys else "free", mode_gates=[], racer_lock=None)
        if index < len(chosen):
            track = chosen[index]
            entry_id = "entry/" + track["id"]
            entries.append(dict(id=entry_id, kind="track", track_id=track["id"], modes=["trophy"], merged=False))
            pad.update(entry_id=entry_id, mode_gates=[dict(mode="trophy", stage=1, requirement_id="free")])
            name = (f"Custom Track {track['custom_slot']}: Trophy Race" if track["origin"] == "custom"
                    else track["display_name"] + ": Trophy Race")
            code = CTR_LOCATION_IDS[name]
            checks.append(dict(location=code, owner=track["id"], kind="trophy",
                               display_name=track["display_name"] + ": Trophy Race",
                               routes=[dict(entry_id=entry_id, mode="trophy", leg_id=None,
                                            encounter_id=None, own_pad_id=pad["id"], award="win")]))
        pads.append(pad)
    for boss in range(5):
        pads.append(dict(id=f"garage:{boss}", hub_id=f"hub:{26 + boss if boss < 4 else 25}",
                         kind="garage", entry_id=None, entrance_req="free", mode_gates=[], racer_lock=None))
    world.ctr_content_items = content_item_pool.resolve(
        o.item_pool.value, len(checks), starts=o.start_inventory_from_pool.value,
        additional=o.start_inventory.value, trap_percentage=o.trap_fill_percentage.value)
    gem_ids = [r.item for r in world.ctr_content_items.rows if r.name.endswith(" Gem") and r.base]
    if o.gems_required_goal.value > len(gem_ids):
        error("Gem goal exceeds the selected distinct base Gem colours.")
    plan = dict(version=1, packages=[p for p in packages if any(t.get("package_id") == p["id"] for t in chosen)],
                tracks=chosen, entries=entries, pads=pads, encounters=[], requirements=requirements, checks=checks,
                items=world.ctr_content_items.wire(), goal=dict(op="distinct", items=gem_ids, count=o.gems_required_goal.value),
                required_features=["content_plan_v1"])
    validate(plan)
    world.ctr_content_plan = plan
    # Actual native 0.6.7 protocol/handshake validation is a release gate. This
    # room barrier already prevents the rc1 client's default 0.6.4 admission.
    world.required_client_version = (0, 6, 7)
    world.ctr_content_original_starts = copy.deepcopy(o.start_inventory_from_pool.value)
    world.ctr_starting_character = characters.resolve_starting_character(world)
    return plan


def predicate(world, node):
    player = world.player
    if node["op"] == "always":
        return lambda state: True
    if node["op"] == "count":
        return lambda state: state.has(ITEM_BY_CODE[node["item"]], player, node["count"])
    if node["op"] == "distinct":
        return lambda state: sum(state.has(ITEM_BY_CODE[code], player) for code in node["items"]) >= node["count"]
    error("unsupported predicate in experimental content plan.")


def create_regions(world):
    mw, player, plan = world.multiworld, world.player, world.ctr_content_plan
    menu = Region("Menu", player, mw)
    mw.regions.append(menu)
    req = {r["id"]: r["predicate"] for r in plan["requirements"]}
    by_pad = {r["routes"][0]["own_pad_id"]: r for r in plan["checks"]}
    for pad in plan["pads"]:
        if pad["entry_id"] is None:
            continue
        region = Region(pad["entry_id"], player, mw)
        mw.regions.append(region)
        menu.connect(region, pad["id"], predicate(world, req[pad["entrance_req"]]))
        check = by_pad[pad["id"]]
        region.locations.append(Location(player, LOCATION_BY_CODE[check["location"]], check["location"], region))
    from .custom_track_presentation import location_aliases
    world.location_id_to_alias = location_aliases(world)


def create_items(world):
    plan = world.ctr_content_items
    names = plan.selected_names()
    names += traps.draw_trap_names(world, plan.trap_count)
    names += [wumpa_family.draw_filler_name(world) for _ in range(plan.filler_count - plan.trap_count)]
    world.multiworld.itempool.extend(world.create_item(name) for name in names)
    # Main.py has granted these starts. Consume only this world's local removal
    # request; retain the original configuration for spoiler/Tracker diagnostics.
    world.options.start_inventory_from_pool.value = {}


def set_rules(world):
    world.multiworld.completion_condition[world.player] = predicate(world, world.ctr_content_plan["goal"])


def wire(world):
    o = world.options
    return dict(schema_version=SCHEMA, content_plan=copy.deepcopy(world.ctr_content_plan),
                ctr_options=dict(schema_version=SCHEMA, world_version="0.3.0-content-dev", content_plan=True,
                                 goal=-1, goal_oxide=3, goal_bosses=0, goal_gems=o.gems_required_goal.value,
                                 starting_character=characters.ROSTER_CHARACTER_ID[world.ctr_starting_character], character_unlocks=False,
                                 progressive_boost=0, progressive_stats=0, hit_character=False,
                                 death_link=o.death_link.value, deathlink_amnesty=o.deathlink_amnesty.value))


def validate(plan):
    """Closed shape plus registry/ownership/accounting for the implemented profile."""
    from .content_plan_schema import validate_shape
    try:
        validate_shape(plan)
    except (ValueError, TypeError, OverflowError) as exc:
        error(str(exc))

    def require(test, message):
        if not test:
            error(message)

    def table(name, key="id"):
        result = {row[key]: row for row in plan[name]}
        require(len(result) == len(plan[name]), "duplicate identity in " + name)
        return result

    packages = table("packages")
    resolve_packages(plan["packages"])
    tracks, entries, pads = table("tracks"), table("entries"), table("pads")
    checks, requirements = table("checks", "location"), table("requirements")
    require(not plan["encounters"], "encounter routes are not implemented by this profile")
    expected_requirements = {"free": {"id": "free", "predicate": {"op": "always"}}}
    expected_requirements.update({f"keys:{n}": dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)})
    require(requirements == expected_requirements, "unsupported or changed physical hub requirements")
    expected_pads = {f"pad:{physical}": (f"hub:{hub}", f"keys:{keys}" if keys else "free")
                     for physical, hub, keys in pad_registry()}
    expected_pads.update({f"garage:{i}": (f"hub:{26+i if i<4 else 25}", "free") for i in range(5)})
    require(set(pads) == set(expected_pads), "physical pad registry mismatch")
    occupied = []
    for pad_id, pad in pads.items():
        require((pad["hub_id"], pad["entrance_req"]) == expected_pads[pad_id], "pad has wrong hub or hub gate")
        require(pad["kind"] == ("garage" if pad_id.startswith("garage:") else "normal"), "pad kind mismatch")
        require(pad["racer_lock"] is None, "racer-lock routes are not implemented")
        if pad["entry_id"] is None:
            require(not pad["mode_gates"], "empty pad has mode gates")
        else:
            require(pad["kind"] == "normal" and pad["entry_id"] in entries, "invalid normal entry")
            require(pad["mode_gates"] == [dict(mode="trophy", stage=1, requirement_id="free")], "unsupported mode gates")
            occupied.append(pad["entry_id"])
    require(len(occupied) == len(set(occupied)) and set(occupied) == set(entries), "entry occurrence ownership mismatch")
    used_tracks, used_packages, slots, retail_ids = set(), set(), set(), set()
    expected_checks = {}
    for entry in entries.values():
        require(entry["kind"] == "track" and entry["modes"] == ["trophy"] and entry["merged"] is False,
                "unsupported entry kind or modes")
        require(entry["track_id"] in tracks and entry["track_id"] not in used_tracks, "missing or repeated standalone track")
        used_tracks.add(entry["track_id"])
        track = tracks[entry["track_id"]]
        require(track["modes"] == ["trophy"] and track["capabilities"] == ["trophy"] and track["field_size"] == 8,
                "unsupported track capabilities")
        if track["origin"] == "retail":
            i = track["retail_id"]
            require(i in RETAIL and i not in retail_ids, "unknown or duplicate retail track")
            retail_ids.add(i)
            require(track["display_name"] == RETAIL[i] and track["laps"] == 3 and track["id"] == f"retail:{i}",
                    "retail track metadata mismatch")
            name = RETAIL[i] + ": Trophy Race"
        else:
            require(track["origin"] == "custom" and track["package_id"] in packages, "unknown custom package")
            package = packages[track["package_id"]]
            used_packages.add(package["id"])
            slot = track["custom_slot"]
            require(1 <= slot <= 32 and slot not in slots, "unregistered or duplicate custom slot")
            slots.add(slot)
            require(track["laps"] == 7 and track["display_name"] == package["display_name"] and
                    track["id"] == "custom/" + package["content_id"] + "/" + package["revision"], "custom track metadata mismatch")
            name = f"Custom Track {slot}: Trophy Race"
        code = CTR_LOCATION_IDS[name]
        pad_id = next(p["id"] for p in pads.values() if p["entry_id"] == entry["id"])
        expected_checks[code] = dict(location=code, owner=track["id"], kind="trophy",
                                    display_name=track["display_name"] + ": Trophy Race",
                                    routes=[dict(entry_id=entry["id"], mode="trophy", leg_id=None,
                                                 encounter_id=None, own_pad_id=pad_id, award="win")])
    require(used_tracks == set(tracks) and used_packages == set(packages), "unused track/package")
    require(not tracks or any(p["entry_id"] is not None and p["entrance_req"] == "free" for p in pads.values()),
            "content layout has no playable starting pad")
    require(checks == expected_checks, "check registry or route ownership mismatch")
    item_plan = plan["items"]
    rows = {row["item"]: row for row in item_plan["rows"]}
    require(len(rows) == len(item_plan["rows"]) and set(rows) == {content_item_pool.ITEMS[n] for n in content_item_pool.COUNTED_NAMES},
            "item family registry mismatch")
    for row in rows.values():
        require(row["start_from_pool"] <= 10000 and row["start_additional"] <= 10000,
                "starting count exceeds the framework ItemDict bound")
        require(row["locked_selected"] == 0 and row["remaining"] == row["base"] + row["extra"] - row["start_from_pool"],
                "invalid remaining selected count")
        require(row["receipt_cap"] == row["base"] + row["extra"] + row["start_additional"] and
                row["requirement_ceiling"] == row["base"], "invalid receipt cap or base requirement ceiling")
    require(rows[35010014]["base"] == 4, "four base Keys are mandatory")
    require(all(rows[i]["base"] in (0, 1) for i in range(35010009, 35010014)), "base Gems are distinct colours")
    require(item_plan["coded_checks"] == len(checks) and item_plan["locked_checks"] == 0 and
            sum(r["remaining"] for r in rows.values()) + item_plan["filler_count"] == len(checks) and
            item_plan["trap_count"] <= item_plan["filler_count"], "item/check capacity mismatch")
    goal = plan["goal"]
    gems = [i for i in range(35010009, 35010014) if rows[i]["base"]]
    require(goal["op"] == "distinct" and goal["items"] == gems and 1 <= goal["count"] <= len(gems),
            "goal must count selected distinct base Gem colours")
    return True


def restore(world, slot_data):
    plan = copy.deepcopy(slot_data["content_plan"])
    validate(plan)
    co = slot_data.get("ctr_options", {})
    if (type(slot_data.get("schema_version")) is not int or slot_data["schema_version"] != SCHEMA or
            type(co.get("schema_version")) is not int or co["schema_version"] != SCHEMA or co.get("content_plan") is not True):
        error("content-plan envelope is missing or inconsistent")
    starting = co.get("starting_character")
    if type(starting) is not int or not 0 <= starting < 16:
        error("invalid starting racer")
    rows = tuple(content_item_pool.ItemRow(name=ITEM_BY_CODE[r["item"]], **r) for r in plan["items"]["rows"])
    world.ctr_content_items = content_item_pool.ItemPlan(rows, **{k: v for k, v in plan["items"].items() if k != "rows"})
    world.ctr_content_plan = plan
    world.required_client_version = (0, 6, 7)
    world.ctr_starting_character = characters.CHARACTER_ID_TO_NAME[starting]
    world.ctr_content_original_starts = {r.name: r.start_from_pool for r in rows if r.start_from_pool}
    world.options.start_inventory_from_pool.value = copy.deepcopy(world.ctr_content_original_starts)
    world.options.start_inventory.value = {r.name: r.start_additional for r in rows if r.start_additional}
    world.options.gems_required_goal.value = plan["goal"]["count"]
    world.options.death_link.value = co.get("death_link", 0)
    world.options.deathlink_amnesty.value = co.get("deathlink_amnesty", 1)
    # Optional legacy classifiers must not read the tracking player's unrelated YAML.
    world.options.character_unlocks.value = 0
    world.options.racer_locked_pads.value = 0
    world.options.progressive_boost.value = 0
    world.options.progressive_stats.value = 0
