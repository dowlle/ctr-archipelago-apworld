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

from . import (content_item_pool, characters, destinations, named_tracks, sphere0_guard, traps,
               warp_pad_rules, wumpa_family)
from .custom_track_titles import is_sanitized, seed_titles
from .custom_tracks import BABY_T_PARK_PROFILES
from . import arena_content
from .Locations import CTR_LOCATION_IDS
from .warp_pad_logic import HUB_STATIC

SCHEMA = 18
MANUAL_FEATURE = "manual_pad_requirements_v1"
#: Aggregate manual rule -> the counted item names it sums, in wire order.
#: Native holds the same three lists; the parity fixtures compare them.
SUM_FAMILIES = {"AnyCtrToken": warp_pad_rules.TOKENS, "AnyRelic": warp_pad_rules.RELICS,
                "AnyGem": warp_pad_rules.GEMS}
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


PAD_KEY_BY_LEVEL_ID = {d.level_id: d.key for d in destinations.DESTINATIONS}


def manual_rules(options):
    """{physical LevelID -> rule} from warp_pad_rules, or {} when unused.
    Shape, names and the unlock-mode conflicts are checked here; the supply
    check needs the item ledger and runs in manual_requirements."""
    raw = options.warp_pad_rules.value
    if not raw:
        return {}
    rules = warp_pad_rules.parse(raw)
    mode = int(options.warppad_unlock_requirements.value)
    if mode == 0:
        error("warp_pad_rules needs warppad_unlock_requirements randomized or "
              "random_without_4_keys; with vanilla, remove the rules or change the mode.")
    for pad, rule in rules.items():
        if mode == 2 and rule is not None and rule[0] == "Key" and rule[1] >= 4:
            error(f"warp_pad_rules {pad!r}: Key x {rule[1]} is not allowed with "
                  "random_without_4_keys.")
    ids = {d.key: d.level_id for d in destinations.DESTINATIONS}
    return {ids[pad]: rule for pad, rule in rules.items()}


def starting_counts(options):
    """Items the slot starts with: from-pool starts plus additional starts."""
    held = {}
    for source in (options.start_inventory_from_pool.value, options.start_inventory.value):
        for name, count in source.items():
            held[name] = held.get(name, 0) + count
    return held


def rule_met(rule, held):
    if rule is None:
        return True
    item, count = rule
    members = SUM_FAMILIES.get(item)
    return (sum(held.get(m, 0) for m in members) if members else held.get(item, 0)) >= count


def manual_requirements(manual, rows):
    """One requirement record per named non-free pad, checked against the base
    supply (`requirement_ceiling`). A concrete item is a count record; an Any
    rule is a sum record over the items the seed has as base items."""
    by_name = {row.name: row for row in rows}
    out = []
    for physical, rule in sorted(manual.items()):
        if rule is None:
            continue
        pad, (item, count) = PAD_KEY_BY_LEVEL_ID[physical], rule
        names = SUM_FAMILIES.get(item)
        eligible = [n for n in (names or (item,)) if by_name[n].requirement_ceiling > 0]
        have = sum(by_name[n].requirement_ceiling for n in eligible)
        if not eligible:
            error(f"warp_pad_rules {pad!r}: {item} x {count}, but this seed has no "
                  f"{item if not names else 'items of that kind'}.")
        if count > have:
            error(f"warp_pad_rules {pad!r}: {item} x {count}, but the base item pool "
                  f"holds only {have}.")
        predicate = (dict(op="sum", items=[by_name[n].item for n in eligible], count=count)
                     if names else dict(op="count", item=by_name[item].item, count=count))
        out.append(dict(id=f"manual:{physical}", predicate=predicate))
    return out


def required_features(requirements, entries=(), checks=()):
    manual = any(r["id"].startswith("manual:") for r in requirements)
    return (["content_plan_v1"] + ([MANUAL_FEATURE] if manual else [])
            + (["crystal_entries_v1"] if any(e['kind']=='crystal' for e in entries) else [])
            + (["crystal_pickups_v1"] if any(c['kind']=='crystal_pickup' for c in checks) else [])
            + (["arcade_crystals_v1"] if any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in entries) else []))


def crystal_selection(world, raw):
    o=world.options
    pool=raw.get('pool','all')
    allowed=list(arena_content.ARENAS)
    if pool!='all' and (not isinstance(pool,list) or any(type(i) is not int or i not in allowed for i in pool) or len(set(pool))!=len(pool)):
        error('crystals.pool must be all or distinct arena LevelIDs 18 through 24.')
    eligible=(list(arena_content.ARENAS) if pool=='all' else list(pool))
    if not o.include_battle_arenas.value:
        return [],0
    if not o.include_arcade_arenas.value:
        if pool!='all' and any(i in arena_content.ARCADE for i in eligible):
            error('an arcade arena in crystals.pool requires include_arcade_arenas.')
        eligible=[i for i in eligible if i not in arena_content.ARCADE]
    count=raw.get('count',0)
    if isinstance(count,dict) and set(count)=={'min','max'}:
        low,high=count['min'],count['max']
        if type(low) is not int or type(high) is not int or not 0<=low<=high<=len(eligible):
            error('crystals.count range exceeds the eligible arena pool.')
        count=low if low==high else world.random.randint(low,high)
    if type(count) is not int or not 0<=count<=len(eligible):
        error('crystals.count must fit the eligible arena pool.')
    return eligible,count


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
    arena_pool, arena_count = crystal_selection(world, crystals)
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
               "podium_placement_checks", "wumpa_check", "turbo_grant", "tizi_helper", "relic_perfect_checks",
               "boss_track_shuffle")
    enabled = [name for name in pending if getattr(o, name).value]
    if enabled:
        error("these selected packs/checks do not have content-plan routes yet: " + ", ".join(enabled) + ".")
    # The content-plan wire carries death_link only, so native applies the
    # legacy send coupling. An explicit send list would be dropped silently.
    if set(o.death_link_send.value) != {"follow_death_link"}:
        error("an explicit death_link_send list has no content-plan route yet; leave it unset.")
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
    # Field mapping (ruling of 2026-10-13): the named-block identity is the registry
    # `track_key`. The package descriptor carries it in its existing wire field
    # `content_id` (same string, e.g. "baby-t-park"); the wire name is kept so
    # schema 1 plans and the native registry do not change. Lookups below are
    # therefore by track_key.
    # #306: a package whose track key has a named block uses that block's
    # ids and frozen name; any other package keeps its generic slot ids and is
    # shown under its sanitized, clash-suffixed room title (B+).
    named = {p["id"]: destinations.named_track(p["content_id"]) for p in packages}
    titles = seed_titles([(slot, p["display_name"], p["author"], p["content_id"])
                          for slot, p in enumerate(packages, 1) if named[p["id"]] is None])
    for slot, package in enumerate(packages, 1):
        block = named[package["id"]]
        addressing = (dict(named_block=block.block_index, room_title=block.ap_name) if block
                      else dict(room_title=titles.get(slot, f"Custom Track {slot}")))
        candidates.append(dict(id="custom/" + package["content_id"] + "/" + package["revision"],
                               origin="custom", package_id=package["id"], custom_slot=slot,
                               display_name=package["display_name"], laps=7, modes=["trophy"],
                               capabilities=["trophy"], field_size=8, **addressing))
    required = raw.get("required_entries", [])
    arena_candidates=[dict(id=f'arena:{lid}', arena_id=lid, display_name=arena_content.ARENAS[lid]) for lid in arena_pool]
    ids = {t["id"] for t in candidates+arena_candidates}
    if (not isinstance(required, list) or any(type(i) is not str or i not in ids for i in required)
            or len(set(required)) != len(required) or len(required) > 27):
        error("required_entries must be distinct eligible logical track IDs, fitting the 27 normal pads.")
    chosen_arenas=[a for a in arena_candidates if a['id'] in required]
    if len(chosen_arenas)>arena_count:
        error('required arena entries exceed crystals.count; no content count was changed.')
    chosen_arenas+=world.random.sample([a for a in arena_candidates if a['id'] not in required],arena_count-len(chosen_arenas))
    chosen = [t for t in candidates if t["id"] in required]
    if len(chosen)+arena_count>27:
        error('required entries and selected arenas exceed the 27 normal pads.')
    optional = [t for t in candidates if t["id"] not in required]
    chosen += world.random.sample(optional, min(len(optional), 27 - len(chosen)-arena_count))
    chosen += chosen_arenas
    world.random.shuffle(chosen)
    registry = pad_registry()
    world.random.shuffle(registry)
    manual = manual_rules(o)
    if manual:
        # Reserve every named physical seat for selected content, then keep the
        # other seats in their shuffled order. A rule never disappears because
        # its seat drew empty, and no content or item is added to fit it.
        if len(manual) > len(chosen):
            error(f"warp_pad_rules names {len(manual)} pads, but only {len(chosen)} "
                  "entries are selected; name fewer pads or select more content. "
                  "No content or items were added.")
        registry = ([seat for seat in registry if seat[0] in manual]
                    + [seat for seat in registry if seat[0] not in manual])
    # Empty pads are valid, but a fresh Adventure must start with at least
    # sphere0_guard.MIN_STARTING_CHECKS open checks (start-check rulings
    # 2026-10-01 and 2026-10-02), or generate_basic refuses the slot. Keep
    # content/counts and every physical gate unchanged and grant no item: only
    # a layout that falls short exchanges a gated occupied seat with an open
    # empty one, until enough open seats hold content. A layout that already
    # has enough takes no draw here, so its seed is unchanged.
    need = min(len(chosen), sphere0_guard.MIN_STARTING_CHECKS)
    held = starting_counts(o)

    def opens_at_start(seat):
        # Hub gate free, and a manual rule on this seat met by the real start.
        physical, _hub, keys = seat
        return keys == 0 and (physical not in manual or rule_met(manual[physical], held))

    while sum(opens_at_start(seat) for seat in registry[:len(chosen)]) < need:
        # A named seat is never exchanged, so its rule stays where it was set.
        gated = [i for i in range(len(chosen))
                 if registry[i][2] != 0 and registry[i][0] not in manual]
        empty = [i for i in range(len(chosen), len(registry)) if registry[i][2] == 0]
        if not gated or not empty:
            if manual:
                error(f"warp_pad_rules leave only "
                      f"{sum(opens_at_start(seat) for seat in registry[:len(chosen)])} "
                      f"of the {need} starting checks a slot needs. Rules are fixed and "
                      "no item is granted; make a named pad free or lower its count.")
            break
        source = world.random.choice(gated)
        destination = world.random.choice(empty)
        registry[source], registry[destination] = registry[destination], registry[source]
    entries, pads, checks = [], [], []
    requirements = [dict(id="free", predicate=dict(op="always"))]
    requirements += [dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)]
    gate_for = {physical: "free" if rule is None else f"manual:{physical}"
                for physical, rule in manual.items()}
    for index, (physical, hub, keys) in enumerate(registry):
        pad = dict(id=f"pad:{physical}", hub_id=f"hub:{hub}", kind="normal", entry_id=None,
                   entrance_req=f"keys:{keys}" if keys else "free", mode_gates=[], racer_lock=None)
        if index < len(chosen):
            track = chosen[index]
            entry_id = "entry/" + track["id"]
            crystal='arena_id' in track
            mode='crystal' if crystal else 'trophy'
            entry=(dict(id=entry_id,kind='crystal',arena_id=track['arena_id'],target=20,
                        time_limit_ticks=arena_content.TIMERS[track['arena_id']]) if crystal else
                   dict(id=entry_id,kind='track',track_id=track['id'],modes=['trophy'],merged=False))
            entries.append(entry)
            pad.update(entry_id=entry_id,mode_gates=[dict(mode=mode,stage=1,requirement_id=gate_for.get(physical,'free'))])
            if crystal:
                checks.extend(arena_content.checks(entry,pad['id'],bool(o.crystalsanity.value)))
            else:
                name,code,title=trophy_identity(track)
                checks.append(dict(location=code,owner=track['id'],kind='trophy',display_name=title+': Trophy Race',
                    routes=[dict(entry_id=entry_id,mode='trophy',leg_id=None,encounter_id=None,own_pad_id=pad['id'],award='win')]))
        pads.append(pad)
    for boss in range(5):
        pads.append(dict(id=f"garage:{boss}", hub_id=f"hub:{26 + boss if boss < 4 else 25}",
                         kind="garage", entry_id=None, entrance_req="free", mode_gates=[], racer_lock=None))
    world.ctr_content_items = content_item_pool.resolve(
        o.item_pool.value, len(checks), starts=o.start_inventory_from_pool.value,
        additional=o.start_inventory.value, trap_percentage=o.trap_fill_percentage.value)
    if manual:
        requirements += manual_requirements(manual, world.ctr_content_items.rows)
        world._ctr_pad_rules = {key: manual[lid] for lid, key in PAD_KEY_BY_LEVEL_ID.items()
                                if lid in manual}
    gem_ids = [r.item for r in world.ctr_content_items.rows if r.name.endswith(" Gem") and r.base]
    if o.gems_required_goal.value > len(gem_ids):
        error("Gem goal exceeds the selected distinct base Gem colours.")
    plan = dict(version=1, packages=[p for p in packages if any(t.get("package_id") == p["id"] for t in chosen)],
                tracks=[t for t in chosen if 'arena_id' not in t], entries=entries, pads=pads, encounters=[], requirements=requirements, checks=checks,
                items=world.ctr_content_items.wire(), goal=dict(op="distinct", items=gem_ids, count=o.gems_required_goal.value),
                required_features=required_features(requirements,entries,checks))
    validate(plan)
    world.ctr_content_plan = plan
    # Actual native 0.6.7 protocol/handshake validation is a release gate. This
    # room barrier already prevents the rc1 client's default 0.6.4 admission.
    world.required_client_version = (0, 6, 7)
    world.ctr_content_original_starts = copy.deepcopy(o.start_inventory_from_pool.value)
    world.ctr_starting_character = characters.resolve_starting_character(world)
    return plan


def trophy_identity(track):
    """(location name, code, room title) of a track's Trophy Race check."""
    if track["origin"] == "custom":
        title = track.get("room_title", track["display_name"])
        if "named_block" in track:
            code = named_tracks.location_code(track["named_block"], "trophy")
            return LOCATION_BY_CODE[code], code, title
        name = f"Custom Track {track['custom_slot']}: Trophy Race"
        return name, CTR_LOCATION_IDS[name], title
    name = track["display_name"] + ": Trophy Race"
    return name, CTR_LOCATION_IDS[name], track["display_name"]


def predicate(world, node):
    player = world.player
    if node["op"] == "always":
        return lambda state: True
    if node["op"] == "count":
        return lambda state: state.has(ITEM_BY_CODE[node["item"]], player, node["count"])
    if node["op"] == "sum":
        names = [ITEM_BY_CODE[code] for code in node["items"]]
        return lambda state: sum(state.count(name, player) for name in names) >= node["count"]
    if node["op"] == "distinct":
        return lambda state: sum(state.has(ITEM_BY_CODE[code], player) for code in node["items"]) >= node["count"]
    error("unsupported predicate in experimental content plan.")


def create_regions(world):
    mw, player, plan = world.multiworld, world.player, world.ctr_content_plan
    menu = Region("Menu", player, mw)
    mw.regions.append(menu)
    req = {r["id"]: r["predicate"] for r in plan["requirements"]}
    by_pad={}
    for check in plan['checks']:
        by_pad.setdefault(check['routes'][0]['own_pad_id'],[]).append(check)
    for pad in plan["pads"]:
        if pad["entry_id"] is None:
            continue
        region = Region(pad["entry_id"], player, mw)
        mw.regions.append(region)
        gates = [predicate(world, req[pad["entrance_req"]])]
        gates += [predicate(world, req[g["requirement_id"]]) for g in pad["mode_gates"]]
        menu.connect(region, pad["id"], gates[0] if len(gates) == 1 else
                     (lambda state, gates=tuple(gates): all(g(state) for g in gates)))
        for check in by_pad[pad['id']]:
            region.locations.append(Location(player,LOCATION_BY_CODE[check['location']],check['location'],region))
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
    plan=world.ctr_content_plan
    extra=({'include_battle_arenas':True,
            'include_arcade_arenas':any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']),
            'crystalsanity':any(c['kind']=='crystal_pickup' for c in plan['checks'])}
           if any(e['kind']=='crystal' for e in plan['entries']) else {})
    return dict(schema_version=SCHEMA, content_plan=copy.deepcopy(world.ctr_content_plan),
                ctr_options=dict(schema_version=SCHEMA, world_version="0.3.0-content-dev", content_plan=True,
                                 goal=-1, goal_oxide=3, goal_bosses=0, goal_gems=o.gems_required_goal.value,
                                 starting_character=characters.ROSTER_CHARACTER_ID[world.ctr_starting_character], character_unlocks=False,
                                 progressive_boost=0, progressive_stats=0, hit_character=False,
                                 death_link=o.death_link.value, deathlink_amnesty=o.deathlink_amnesty.value,**extra))


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
    manual = {rid: row for rid, row in requirements.items() if rid.startswith("manual:")}
    require({rid: row for rid, row in requirements.items() if rid not in manual} == expected_requirements,
            "unsupported or changed physical hub requirements")
    require(plan['required_features']==required_features(plan['requirements'],plan['entries'],plan['checks']),
            'required features do not match the selected content/checks')
    crystalsanity=any(c['kind']=='crystal_pickup' for c in plan['checks'])
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
            physical = pad_id.split(":")[1]
            gate = f"manual:{physical}" if f"manual:{physical}" in manual else "free"
            mode='crystal' if entries[pad['entry_id']]['kind']=='crystal' else 'trophy'
            require(pad['mode_gates']==[dict(mode=mode,stage=1,requirement_id=gate)],'unsupported mode gates')
            occupied.append(pad["entry_id"])
    require(len(occupied) == len(set(occupied)) and set(occupied) == set(entries), "entry occurrence ownership mismatch")
    require(all(f"pad:{rid.split(':')[1]}" in pads and pads[f"pad:{rid.split(':')[1]}"]["entry_id"] is not None
                for rid in manual), "manual requirement without an occupied pad")
    used_tracks, used_packages, slots, retail_ids = set(), set(), set(), set()
    expected_checks = {}
    arena_ids=set()
    for entry in entries.values():
        if entry['kind']=='crystal':
            lid=entry['arena_id']
            require(lid in arena_content.ARENAS and lid not in arena_ids,'unknown or repeated arena')
            arena_ids.add(lid)
            require(entry['id']==f'entry/arena:{lid}' and entry['target']==20 and entry['time_limit_ticks']==arena_content.TIMERS[lid],
                    'arena metadata mismatch')
            pad_id=next(p['id'] for p in pads.values() if p['entry_id']==entry['id'])
            expected_checks.update({c['location']:c for c in arena_content.checks(entry,pad_id,crystalsanity)})
            continue
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
            block = destinations.named_track(package["content_id"])
            if "named_block" in track:
                require(block is not None and track["named_block"] == block.block_index and
                        track.get("room_title") == block.ap_name, "named block does not match this build's registry")
            else:
                require(block is None, "a track with a named block must use it")
                require(is_sanitized(track.get("room_title", track["display_name"])), "room title is not sanitized")
        _name, code, title = trophy_identity(track)
        pad_id = next(p["id"] for p in pads.values() if p["entry_id"] == entry["id"])
        expected_checks[code] = dict(location=code, owner=track["id"], kind="trophy",
                                    display_name=title + ": Trophy Race",
                                    routes=[dict(entry_id=entry["id"], mode="trophy", leg_id=None,
                                                 encounter_id=None, own_pad_id=pad_id, award="win")])
    require(used_tracks == set(tracks) and used_packages == set(packages), "unused track/package")
    require(not entries or any(p["entry_id"] is not None and p["entrance_req"] == "free" for p in pads.values()),
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
    for rid, row in manual.items():
        predicate_ = row["predicate"]
        if predicate_["op"] == "count":
            item = predicate_["item"]
            require(item in rows and ITEM_BY_CODE.get(item) in content_item_pool.COUNTED_NAMES
                    and 1 <= predicate_["count"] <= rows[item]["requirement_ceiling"],
                    f"{rid}: count rule item or count outside the base supply")
        else:
            require(predicate_["op"] == "sum", f"{rid}: unsupported manual predicate")
            family = next((names for names in SUM_FAMILIES.values()
                           if predicate_["items"] == [rows[content_item_pool.ITEMS[n]]["item"] for n in names
                                                      if rows[content_item_pool.ITEMS[n]]["requirement_ceiling"] > 0]), None)
            require(family is not None and predicate_["items"] and
                    1 <= predicate_["count"] <= sum(rows[code]["requirement_ceiling"] for code in predicate_["items"]),
                    f"{rid}: sum rule items or count outside the base supply")
    return True


def _tracker_arrays(value, depth=0, budget=None):
    """AP room persistence stores JSON arrays as tuples; restore their JSON form.

    Keep scalar types and object keys exact so normal admission still refuses
    malformed numbers, booleans and fields. Bound this walk before copying.
    """
    if budget is None:
        budget = [0]
    budget[0] += 1
    if depth > 32 or budget[0] > 500000:
        error("content_plan: nesting/node budget")
    if type(value) in (list, tuple):
        return [_tracker_arrays(v, depth + 1, budget) for v in value]
    if type(value) is dict:
        return {k: _tracker_arrays(v, depth + 1, budget) for k, v in value.items()}
    return value


def restore(world, slot_data):
    plan = _tracker_arrays(slot_data["content_plan"])
    validate(plan)
    co = slot_data.get("ctr_options", {})
    if (type(slot_data.get("schema_version")) is not int or slot_data["schema_version"] != SCHEMA or
            type(co.get("schema_version")) is not int or co["schema_version"] != SCHEMA or co.get("content_plan") is not True):
        error("content-plan envelope is missing or inconsistent")
    has_crystals=any(e['kind']=='crystal' for e in plan['entries'])
    for key,want in dict(include_battle_arenas=has_crystals,
                         include_arcade_arenas=any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']),
                         crystalsanity=any(c['kind']=='crystal_pickup' for c in plan['checks'])).items():
        if has_crystals and co.get(key) is not want:
            error('Crystal option envelope disagrees with plan: '+key)
        if not has_crystals and key in co:
            error('Crystal option without selected Crystal entries: '+key)
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
    world.options.crystalsanity.value=int(any(c['kind']=='crystal_pickup' for c in plan['checks']))
    world.options.include_battle_arenas.value=int(any(e['kind']=='crystal' for e in plan['entries']))
    world.options.include_arcade_arenas.value=int(any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']))
    world.options.death_link.value = co.get("death_link", 0)
    world.options.deathlink_amnesty.value = co.get("deathlink_amnesty", 1)
    # Optional legacy classifiers must not read the tracking player's unrelated YAML.
    world.options.character_unlocks.value = 0
    world.options.racer_locked_pads.value = 0
    world.options.progressive_boost.value = 0
    world.options.progressive_stats.value = 0
