import json
import pkgutil
from BaseClasses import Region, Entrance, EntranceType
from .Locations import create_location
from .warp_pad_logic import (
    run_sphere_search, to_slot_req, build_warp_pad_map, HUB_STATIC,
    _COLOURS, _RELIC_TIERS,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import ctrAPWorld


# ---------------------------------------------------------------------------
# Native-randomization support (Phase-2 MVP).
# Shared slot_data contract: apworld EMITS resolved values, native PARSES.
# ---------------------------------------------------------------------------

# Per-pad unlock requirements are produced by warp_pad_logic.run_sphere_search
# (Icebound's real free-subset + sphere-search algorithm), not drawn i.i.d. here.

# Boss-garage trophy thresholds (vanilla 4/8/12/16). Oxide stays keys.
BOSS_TROPHY = {"ripper_roo": 4, "papu_papu": 8, "komodo_joe": 12, "pinstripe": 16}

# Vanilla race-track LevelIDs that belong to each boss's hub, in the same
# 0..15 numbering native + Icebound use (verified against
# icebound-standalone LevelID enum and data/warp_pad_ids.json):
#   Roo : Crash Cove 3, Roo's Tubes 6, Mystery Caves 9, Sewer Speedway 8
#   Papu: Coco Park 14, Tiger Temple 4, Papu's Pyramid 5, Dingo Canyon 0
#   Komodo: Blizzard Bluff 2, Dragon Mines 1, Polar Pass 12, Tiny Arena 15
#   Pinstripe: Hot Air Skyway 7, Cortex Castle 10, N. Gin Labs 11, Oxide Station 13
# Used to build the per-boss 'tracks' metadata for the Original4Tracks /
# SameHubTracks garage modes (Icebound get_modified_garage_unlocks). Oxide has
# no track list (it stays a 4-key gate).
VANILLA_BOSS_TRACKS = {
    "ripper_roo": [3, 6, 9, 8],
    "papu_papu":  [14, 4, 5, 0],
    "komodo_joe": [2, 1, 12, 15],
    "pinstripe":  [7, 10, 11, 13],
}


def _load_warp_pad_ids():
    """pad-exit-name -> {level_id, kind} from data/warp_pad_ids.json."""
    return json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8")
    )["pads"]


def _pad_name_for_track(track):
    """Track name (sphere-search key / region name) -> AP pad-exit name.

    Both the AP exit name and the warp_pad_ids.json key are '<track> Warp Pad',
    so this is a direct suffix add."""
    return f"{track} Warp Pad"


def _build_reward_track_resolver(world):
    """Return f(track_name) -> destination track_name for the pad on that track.

    Inverts world.warp_pad_map ({pad_exit_name: dest_track_levelID}) into a
    track->track map so the sphere-search rewards each physical pad with the
    rewards of the track it ACTUALLY loads under destination shuffle. Identity
    when shuffle is off."""
    pad_ids = world.warp_pad_ids
    id_to_track = {}
    for pad_name, meta in pad_ids.items():
        if pad_name.endswith(" Warp Pad"):
            id_to_track[meta["level_id"]] = pad_name[: -len(" Warp Pad")]
    remap = {}
    for pad_name, dest_lid in getattr(world, "warp_pad_map", {}).items():
        if pad_name.endswith(" Warp Pad"):
            phys_track = pad_name[: -len(" Warp Pad")]
            dest_track = id_to_track.get(dest_lid)
            if dest_track is not None:
                remap[phys_track] = dest_track

    def resolve(track):
        return remap.get(track, track)

    return resolve


def _track_dest_resolver(world):
    """Return f(track_levelID) -> the LevelID currently LOADED at that vanilla
    pad after destination shuffle (Icebound's level_links[original]==current).

    Inverts world.warp_pad_ids to levelID->pad_name, then reads
    world.warp_pad_map ({pad_exit_name: dest_track_levelID}). Identity when the
    pad is unmapped or shuffle is off (empty warp_pad_map) -- in which case
    SameHubTracks collapses to Original4Tracks, exactly as Icebound documents.
    """
    lid_to_pad = {
        meta["level_id"]: pad_name
        for pad_name, meta in getattr(world, "warp_pad_ids", {}).items()
    }
    wpm = getattr(world, "warp_pad_map", {})

    def dest(lid):
        pad = lid_to_pad.get(lid)
        if pad is None:
            return lid
        return wpm.get(pad, lid)

    return dest


def _resolve_boss_reqs(world, boss_mode):
    """Resolve all 3 boss-garage modes to flat {type,count} server-side, plus
    mode-specific 'tracks' metadata for the two track-based modes.

    MVP: modes 0/1/2 all enforce trophy-count gates (4/8/12/16) in BOTH AP logic
    (Rules.add_boss_garage_rules) and native (AP_BossReqMet on type:1). Native
    pad-specific win-bit tracking is not yet available, so Original4Tracks (0) and
    SameHubTracks (1) currently FEEL identical to Trophies (2). For those two modes
    we additionally emit a per-boss 'tracks' list of required race LevelIDs so a
    FUTURE native build (see native_patches/6_bossmodes.patch) can switch from the
    trophy count to a per-track win check without an apworld change. Mode 2
    (Trophies) carries no track list. Oxide = 4 keys, fixed, no tracks.

    boss_mode: 0 Original4Tracks / 1 SameHubTracks / 2 Trophies (default).
    """
    req = {b: {"type": 1, "count": c} for b, c in BOSS_TROPHY.items()}
    req["oxide"] = {"type": 2, "count": 4}

    if boss_mode == 0:
        # Original 4 Tracks: the four VANILLA race tracks of that hub, by LevelID
        # (you must win on those specific tracks wherever their pad now loads).
        for b, tracks in VANILLA_BOSS_TRACKS.items():
            req[b]["tracks"] = list(tracks)
    elif boss_mode == 1:
        # Same Hub Tracks: the tracks currently LOADED at this hub's four vanilla
        # race pads after destination shuffle (Icebound level_links lookup).
        dest = _track_dest_resolver(world)
        for b, tracks in VANILLA_BOSS_TRACKS.items():
            req[b]["tracks"] = [dest(t) for t in tracks]
    # boss_mode == 2 (Trophies): trophy counts only, no track list.

    return req


# ---------------------------------------------------------------------------
# Universal Tracker (interpret_slot_data) support
# ---------------------------------------------------------------------------
# Universal Tracker re-generates the world locally from the connected room's
# slot_data. Left alone it re-rolls this seed's per-pad requirements and
# destination shuffle (world.random is a DIFFERENT stream), so the tracker's
# reachability view diverges from the real seed in both directions (issue #29).
# The fix pins the rolled state back from slot_data during that re-generation:
# ctrAPWorld.interpret_slot_data returns the slot_data, UT re-runs generation
# with it in multiworld.re_gen_passthrough, and these helpers reconstruct the
# exact warp_pad_map / warp_pad_unlock state the sphere search would have rolled
# -- so the graph AP builds is identical to the generating seed's.


def _slot_req_to_concrete(req):
    """Inverse of warp_pad_logic.to_slot_req: a {type,count,colour} wire req back
    to the (item, count) tuple Rules.add_time_trial_and_ctr_requirements consumes,
    or None for a type-0 (no-gate) req. type 6/7/8 map to the AnyCtrToken/AnyRelic/
    AnyGem aggregate names Rules resolves via AGG_BY_NAME."""
    t = int(req.get("type", 0))
    if t == 0:
        return None
    count = int(req.get("count", 0))
    colour = int(req.get("colour", -1))
    if t == 1:
        return ("Trophy", count)
    if t == 2:
        return ("Key", count)
    if t == 3:
        return (_COLOURS[colour] + " CTR Token", count)
    if t == 4:
        return (_RELIC_TIERS[colour] + " Relic", count)
    if t == 5:
        return (_COLOURS[colour] + " Gem", count)
    if t == 6:
        return ("AnyCtrToken", count)
    if t == 7:
        return ("AnyRelic", count)
    if t == 8:
        return ("AnyGem", count)
    return None


def _ut_reconstruct_warp_pad_map(world, passthrough):
    """Rebuild world.warp_pad_map ({pad_exit_name: dest_track_levelID}) from the
    seed's slot_data instead of re-rolling build_warp_pad_map.

    slot_data.warp_pad_map is the FULL 0..27 + cup identity map overlaid with the
    remaps; build_warp_pad_map returns only the pads that participate in a pool.
    Every consumer in create_regions reads world.warp_pad_map via .get(pad, pad)
    and skips identity entries, so keeping only the NON-identity remaps reproduces
    the same graph and the same `do_shuffle` verdict as the real seed.
    """
    pad_by_lid = {meta["level_id"]: name
                  for name, meta in world.warp_pad_ids.items()}
    out = {}
    for lid_str, dest_lid in passthrough.get("warp_pad_map", {}).items():
        lid = int(lid_str)
        name = pad_by_lid.get(lid)
        if name is not None and int(dest_lid) != lid:
            out[name] = int(dest_lid)
    return out


def _ut_reconstruct_unlock(world, passthrough):
    """Rebuild the per-pad unlock state the sphere search would have produced,
    read back from slot_data.warp_pad_unlock (physical-pad keyed):

    * world.warp_pad_unlock[pad] = stage-1 wire req (only non-type-0 pads, matching
      add_warp_pad_unlock_rules which skips type 0);
    * world.warp_pad_unlock_stage2[pad] = stage-2 wire req (all pads, for parity
      with the emit path / spoiler);
    * world.warp_pad_unlock_stage2_concrete[dest_track] = (item, count) for the
      Time-Trial / CTR-Token stage-2 gate, keyed by the DESTINATION track (where
      those locations live under shuffle), exactly as create_regions keys it.

    This is the logic-critical half: Rules reads warp_pad_unlock and
    warp_pad_unlock_stage2_concrete to build the pad-entry and tier-2 access rules,
    so pinning them makes UT's reachability identical to the generating seed.
    """
    pad_by_lid = {meta["level_id"]: name
                  for name, meta in world.warp_pad_ids.items()}
    lid_to_track = {meta["level_id"]: name[: -len(" Warp Pad")]
                    for name, meta in world.warp_pad_ids.items()
                    if name.endswith(" Warp Pad")}
    full_map = {int(k): int(v)
                for k, v in passthrough.get("warp_pad_map", {}).items()}
    _ZERO = {"type": 0, "count": 0, "colour": -1}
    two_stage_active = False
    for lid_str, stages in passthrough.get("warp_pad_unlock", {}).items():
        lid = int(lid_str)
        pad_name = pad_by_lid.get(lid)
        if pad_name is None:
            continue
        s1 = stages.get("stage1", _ZERO)
        s2 = stages.get("stage2", _ZERO)
        if int(s1.get("type", 0)) != 0:
            world.warp_pad_unlock[pad_name] = {
                "type": int(s1["type"]), "count": int(s1["count"]),
                "colour": int(s1["colour"])}
        world.warp_pad_unlock_stage2[pad_name] = {
            "type": int(s2.get("type", 0)), "count": int(s2.get("count", 0)),
            "colour": int(s2.get("colour", -1))}
        if int(s2.get("type", 0)) != 0:
            two_stage_active = True
            concrete = _slot_req_to_concrete(s2)
            dest_track = lid_to_track.get(full_map.get(lid, lid))
            if concrete is not None and dest_track is not None:
                world.warp_pad_unlock_stage2_concrete[dest_track] = concrete
    world._ctr_two_stage_active = two_stage_active


def create_regions(world: "ctrAPWorld"):
    """Build all regions, exits, and locations from JSON definitions."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/world.json").decode("utf-8")
    )

    player, mw = world.player, world.multiworld

    # --- Resolve native-randomization options up front -------------------
    opts = world.options
    unlock_mode = opts.warppad_unlock_requirements.value       # 0 vanilla / 1 randomized / 2 no-4-keys
    boss_mode = opts.bossgarage_unlock_requirements.value      # 0 orig4 / 1 same_hub / 2 trophies

    world.warp_pad_ids = _load_warp_pad_ids()
    # Universal Tracker re-generation (issue #29): when UT re-runs generation with
    # the connected room's slot_data in re_gen_passthrough, pin the rolled state
    # from it instead of re-rolling build_warp_pad_map / run_sphere_search below.
    # options were already restored in generate_early, so every option-driven
    # branch here (floor strip, trial/cup/crystal exit rules, floor rekey) matches
    # the seed; only the two RNG rolls need replacing.
    ut_passthrough = getattr(mw, "re_gen_passthrough", {}).get(world.game)
    # do_shuffle is derived from the destination-shuffle map below (non-empty ==
    # at least one participating category), NOT the deprecated shuffle_warp_pads
    # boolean. Set once build_warp_pad_map has resolved the participating pools.

    # --- Comfort guards (Icebound force_vanilla_turbotrack / limit_arena_gemcup) ---
    # Activate only in Icebound's exact condition: warp-pad unlock = VANILLA and gems
    # NOT shuffled. There the Turbo Track pad keeps its vanilla 5-gem gate, so any
    # required item reachable only through it forces the tedious tokens -> gem cups ->
    # 5 gems chain. The flag drives (a) build_warp_pad_map keeping Gem Cup / trial pads
    # out of the trophy-pad destination shuffle (so a Gem Cup can never land in the
    # Turbo Track pad), and (b) create_items pinning Turbo Track's relic rewards
    # vanilla so progression is never placed behind that gate. Inert when unlocks are
    # randomized or gems are shuffled. ALWAYS ON since the 2026-07-15 release
    # polish (design ruling): the former `comfort_guards` YAML toggle only ever
    # bought its user the tedious forced chain, so the knob was removed.
    world._ctr_comfort_guards = True
    world._ctr_force_vanilla_turbotrack = (
        world._ctr_comfort_guards
        and unlock_mode == 0
        and not bool(opts.shuffle_gems.value)
    )

    # Per-pad resolved unlock requirement: {pad_exit_name -> {type,count,colour}}.
    # The concrete (item, count) used to build the AP access rule (parallel dict).
    world.warp_pad_unlock = {}            # STAGE 1, physical-pad keyed (slot_data)
    world.warp_pad_unlock_concrete = {}   # STAGE 1 concrete (item,count), pad keyed
    # STAGE 2 (two-stage port): the second per-pad gate on the 16 trophy pads'
    # CTR Token Challenge + 3 relic Time Trials. Slot_data is physical-pad keyed
    # ({pad_exit_name -> {type,count,colour}}); the concrete (item,count) for the AP
    # access rules is keyed by DESTINATION track (where those locations live).
    world.warp_pad_unlock_stage2 = {}            # physical-pad keyed (slot_data)
    world.warp_pad_unlock_stage2_concrete = {}   # dest-track keyed (AP rules)
    world._ctr_two_stage_active = False
    world._ctr_force_collapse_stage2 = False      # density-adaptive collapse (create_items)

    # Destination shuffle. Build the NON-IDENTITY warp_pad_map FIRST so the
    # sphere-search rewards each physical pad with the rewards of the track it
    # actually loads (A.4<->logic coupling). build_warp_pad_map resolves the
    # participating pools itself (categories × grouping × include_* × the vanilla
    # collapse) and returns an empty (identity) map when nothing participates.
    # do_shuffle is then simply "the map is non-empty" -- the gate the rest of
    # create_regions keys off (floor re-keying, exit rewiring). Requires the
    # comfort-guard flag (above) already set, which build_warp_pad_map reads.
    world.warp_pad_map = (
        _ut_reconstruct_warp_pad_map(world, ut_passthrough)
        if ut_passthrough else build_warp_pad_map(world))
    do_shuffle = bool(world.warp_pad_map)
    world.shuffle_warp_pads = do_shuffle

    # Boss-garage requirements, resolved to flat {type,count} (+ 'tracks' for
    # modes 0/1). warp_pad_map (above) is read for SameHubTracks, so resolve here.
    world.boss_garage_req = _resolve_boss_reqs(world, boss_mode)

    # Stash the unlock mode; the sphere-search runs at the END of create_regions
    # (after regions+locations+exits exist, so build_graph can read them).
    world._ctr_unlock_mode = unlock_mode

    regions = []

    for reg in data["regions"]:
        region = Region(reg["name"], player, mw)
        region.type = reg.get("type", "generic")
        region.is_start = reg.get("is_start", False)
        mw.regions.append(region)
        regions.append(region)

    region_lookup = {r.name: r for r in regions}

    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for loc_data in reg.get("locations", []):
            name = loc_data["name"]
            location = create_location(player, name, region)
            location.type = loc_data.get("type", "default")
            location.logic_text = loc_data.get("requires", "True")
            region.locations.append(location)
            mw.regions.location_cache[player][name] = location

    # --- Podium placement checks (position-rung rework, v0.2.0 Phase A) -------
    # Per adventure trophy race, a 5-rung superset split into held-position rungs
    # (Held 1st / Held 3rd / optional Held 5th) and finish-line rungs (Finish on
    # Podium / optional Finish (Any Position)). Which rungs a seed creates is
    # decided by podium.created_rung_keys_from_options (the single source shared
    # with Rules + slot_data). NEW event-only locations fired native-side from the
    # placement listener at the live/finish capture points; they are NOT AdvProgress
    # bits and never touch the warp-pad/trophy gate logic. Their reachability ==
    # the track's Trophy Race (installed in Rules.add_podium_placement_rules, a
    # placeholder 'True' here is overwritten there, plus cup-leg reachability); a
    # win fires every rung, so any winnable race yields all of them -> no extra
    # solvability burden, and the extra unfilled locations pull matching filler in
    # create_items (item/location count stays balanced automatically).
    from .podium import TROPHY_TRACKS, created_rung_keys_from_options, location_name
    _rung_keys = created_rung_keys_from_options(opts)
    if _rung_keys:
        # Issue #86 -- JOINT PODIUM REGION. AP-core ANDs a Location's own rule
        # with its PARENT region's reachability (BaseClasses.Location.can_reach:
        # parent_region.can_reach AND access_rule). If the rungs are parented to
        # the track region, a shut track warp pad makes that parent unreachable,
        # so the cup-leg branch of the OR rule installed in
        # Rules.add_podium_placement_rules can never fire -- a cup-only rung is
        # hidden in Universal Tracker and dropped from fill logic. Fix: hold each
        # track's rungs in a dedicated dead-end "<track>: Podium" region reached
        # by a rule-True entrance from the track region AND from every Gem Cup
        # that legs the track (data/gem_cup_legs.json). The rung's own OR rule is
        # left unchanged in Rules; can_reach then evaluates to
        # (trackRegion OR cup) AND (trophyLoc OR cup), which reduces to exactly
        # (trophyLoc OR cup) since trophyLoc reachability implies trackRegion.
        # The region holds ONLY rungs and has no exits, so a cup leg exposes
        # nothing else on the track -- golden rule preserved (the concern in
        # Rules.add_podium_placement_rules's docstring). The rule-True entrances
        # need no register_indirect_condition (they never read region
        # reachability) and the new "podium"-type regions are sphere-search
        # reward-neutral (podium locations resolve to reward None).
        _cup_legs = json.loads(
            pkgutil.get_data(__package__, "data/gem_cup_legs.json").decode("utf-8")
        )["cup_legs"]
        _track_to_cups: dict = {}
        for _cup, _legs in _cup_legs.items():
            for _leg in _legs:
                _track_to_cups.setdefault(_leg, []).append(_cup)
        for _track in TROPHY_TRACKS:
            _track_region = region_lookup.get(_track)
            if _track_region is None:
                continue
            _podium = Region(f"{_track}: Podium", player, mw)
            _podium.type = "podium"
            mw.regions.append(_podium)
            regions.append(_podium)
            region_lookup[_podium.name] = _podium
            for _rk in _rung_keys:
                _name = location_name(_track, _rk)
                _loc = create_location(player, _name, _podium)
                _loc.type = "podium"
                _loc.logic_text = "True"  # real OR rule set in Rules (Trophy Race OR cup)
                _podium.locations.append(_loc)
                mw.regions.location_cache[player][_name] = _loc
            # Rule-True entrances into the dead-end podium region: one from the
            # track region, one from each Gem Cup that legs this track (names
            # unique per track AND cup -- Purple Gem Cup legs four tracks, and a
            # track can be legged by two cups). Cup filtered to regions that
            # exist this seed, mirroring Rules.add_podium_placement_rules. No
            # access_rule_text -> set_rules' getattr default "True" covers it.
            _sources = [_track_region]
            _sources += [region_lookup[_c] for _c in _track_to_cups.get(_track, [])
                         if _c in region_lookup]
            for _src in _sources:
                _ent = Entrance(player=player,
                                name=f"{_src.name} -> {_podium.name}",
                                parent=_src)
                _ent.connect(_podium)
                _src.exits.append(_ent)
                mw.regions.entrance_cache[player][_ent.name] = _ent

    # Trophy-race LOCATIONS carry NO floor in any mode (issue #80): world.json now
    # normalizes every "<track>: Trophy Race" requires to "always". The vanilla
    # per-pad trophy floor lives on the pad ENTRANCE instead (Rules.add_vanilla_floor_rules,
    # keyed by PHYSICAL pad like native), and randomized modes own all entry
    # requirements via the sphere search. No location-floor strip is needed here.

    # TRIAL pads (Slide Coliseum / Turbo Track): in randomized mode their warp-pad
    # exit carries a randomized SINGLE-STAGE entry requirement (sphere-search), so
    # strip the vanilla relic/gem gate from the exit access rule and keep ONLY the
    # hub Key gate (Gem Stone Valley is behind Key 1). The randomized requirement is
    # ANDed on top in Rules.add_warp_pad_unlock_rules. The 3 relic Time Trials inside
    # the trial region have no Trophy Race, so they are gated purely by reaching the
    # (now randomized) pad. Vanilla mode (0) keeps the real relic/gem gate untouched.
    _TRIAL_PAD_EXITS = ("Slide Coliseum Warp Pad", "Turbo Track Warp Pad")
    if unlock_mode in (1, 2):
        for reg in data["regions"]:
            for ex in reg.get("exits", []):
                if ex["name"] in _TRIAL_PAD_EXITS:
                    ex["access_rule"] = "has('Key', 1)"

    # GEM-CUP pads (Red/Green/Blue/Yellow/Purple Cup): same OPEN treatment as the
    # trials, gated by the include_gem_cups YAML option (mirrors include_battle_arenas
    # for crystals). When ON in randomized mode, strip each cup's vanilla per-cup
    # has('<Colour> CTR Token', 4) gate from the exit access rule and keep ONLY the
    # Key-2 Cups Room hub gate (HARD CONSTRAINT: cups STAY behind their key
    # hub gate). The gate is Key 2, matching native (arrKeysNeeded[GEM_STONE_VALLEY]=2,
    # the GSV->Cups door = 2 keyholes) -- NOT 3. The randomized single-stage requirement
    # is ANDed on TOP of that key gate in Rules.add_warp_pad_unlock_rules, never replacing
    # it. The Cups Room region entrance ('Gem Stone Valley <-> Cups Room' = has('Key', 2))
    # is left untouched, so the key gate is enforced both structurally (region
    # reachability) and on the pad exit. Option OFF -> cups keep their vanilla token gate,
    # unchanged. The gem REWARD ('<Colour> Gem Cup: Gem') is untouched in either case.
    _CUP_PAD_EXITS = (
        "Red Cup Warp Pad", "Green Cup Warp Pad", "Blue Cup Warp Pad",
        "Yellow Cup Warp Pad", "Purple Cup Warp Pad",
    )
    inc_cups = bool(opts.include_gem_cups.value)
    if unlock_mode in (1, 2) and inc_cups:
        for reg in data["regions"]:
            for ex in reg.get("exits", []):
                if ex["name"] in _CUP_PAD_EXITS:
                    ex["access_rule"] = "has('Key', 2)"

    # CRYSTAL / battle-arena pads (Skull Rock, Rampage Ruins, Rocky Road, Nitro
    # Court): same OPEN treatment as trials and cups, gated by include_battle_arenas
    # (their participation gate). In randomized mode a
    # crystal pad is gated by its PHYSICAL HUB FLOOR only -- Skull Rock 0 keys (a
    # genuine 5th sphere-0 bootstrap pad), Rampage Ruins Key 1 (Lost Ruins),
    # Rocky Road Key 2 (Glacier Park), Nitro Court Key 3 (Citadel City) -- the
    # vanilla "+1 Key" arena gate is stripped. The
    # hub-floor Key rule kept on the exit mirrors the trial/cup pattern (the hub
    # doors also enforce it structurally); the randomized single-stage requirement
    # is ANDed on top in Rules.add_warp_pad_unlock_rules. Option OFF or vanilla
    # mode: the vanilla has('Key', hub+1) gates stay untouched, matching native's
    # arrKeysNeeded fallback. Native side needs NO code change: an included arena
    # always reaches the wire with a non-type-0 stage-1 (a FREE pad emits the
    # explicit type-1/count-0, see to_slot_req), which the LInB battle-maps branch
    # and AP_PadStage1Met enforce verbatim with no vanilla-key AND; the type-0
    # vanilla fallback is only reachable in exactly the configs where the vanilla
    # gate is correct (ap_hooks.c AP_PadStage1Met + AH_WarpPad.c battle maps).
    _CRYSTAL_PAD_EXITS = {
        "Skull Rock Warp Pad": "always",
        "Rampage Ruins Warp Pad": "has('Key', 1)",
        "Rocky Road Warp Pad": "has('Key', 2)",
        "Nitro Court Warp Pad": "has('Key', 3)",
    }
    inc_arenas_open = bool(opts.include_battle_arenas.value)
    if unlock_mode in (1, 2) and inc_arenas_open:
        for reg in data["regions"]:
            for ex in reg.get("exits", []):
                _new_rule = _CRYSTAL_PAD_EXITS.get(ex["name"])
                if _new_rule is not None:
                    ex["access_rule"] = _new_rule

    # AP destination shuffle: rewire each shuffled warp-pad exit to the track
    # region it ACTUALLY loads, so AP-core (item placement + solvability) reasons
    # about the same topology native runs. The exit stays in its PHYSICAL hub
    # region and keeps its physical-pad access rule (Rules.add_warp_pad_unlock_rules)
    # + the hub boss-key gate, so the requirement and keys apply to the PHYSICAL
    # pad while the locations reached are the DESTINATION track's. Empty (identity)
    # when shuffle is off. warp_pad_map is {pad_exit_name: dest_track_levelID}.
    #
    # A destination LevelID resolves to the REGION that LevelID's pad vanilla-loads,
    # taken from world.json's own pad-exit targets. This is NOT the same as
    # stripping " Warp Pad" off the pad name: for gem cups the pad name strips to
    # "<Colour> Cup" but the region is "<Colour> Gem Cup" (pad key != region name).
    # Under merged shuffle a track/crystal pad can now load a cup destination, so a
    # wrong region name would leave that exit UNCONNECTED (connected_region None) and
    # crash AP reachability -- hence resolving through the real exit targets.
    _lid_to_region = {}
    for reg in data["regions"]:
        for ex in reg.get("exits", []):
            meta = world.warp_pad_ids.get(ex["name"])
            if meta is not None and ex.get("target") is not None:
                _lid_to_region[meta["level_id"]] = ex["target"]
    pad_dest_region = {}
    for pad_name, dest_lid in getattr(world, "warp_pad_map", {}).items():
        dest_region = _lid_to_region.get(dest_lid)
        if dest_region is not None:
            pad_dest_region[pad_name] = dest_region

    # VANILLA unlock mode + destination shuffle: no floor re-keying is needed here.
    # The vanilla trophy floor now lives on the pad ENTRANCE, keyed by the PHYSICAL
    # pad (Rules.add_vanilla_floor_rules), and the exit wiring below keeps that exit
    # in its physical hub with its physical-pad rule while retargeting it to the
    # shuffled destination -- so the physical pad's floor already gates the
    # destination it loads, exactly as native keys numTrophiesToOpen by physLevelID.
    # (This superseded the old location-floor re-key hack, issue #80.)

    for reg in data["regions"]:
        region = region_lookup[reg["name"]]
        for ex in reg.get("exits", []):
            ent = Entrance(
                player=player,
                name=ex["name"],
                parent=region,
                randomization_group=ex.get("randomization_group"),
                randomization_type=EntranceType[ex.get("randomization_type")],
            )
            ent.access_rule_text = ex.get("access_rule", "True")
            # Destination shuffle: a shuffled warp-pad exit leads to the track it
            # loads (dest region), not its static target. Non-pad exits and the
            # no-shuffle case fall back to the static target unchanged.
            tgt = pad_dest_region.get(ex["name"], ex.get("target"))
            if tgt in region_lookup:
                ent.connect(region_lookup[tgt])
            region.exits.append(ent)
            mw.regions.entrance_cache[player][ent.name] = ent

    world.start_region = next(
        (r for r in regions if getattr(r, "is_start", False)),
        None
    )

    # --- Sphere-search warp-pad unlock requirements (Icebound's real algorithm).
    # Runs here, after regions+locations+exits exist, so build_graph can read the
    # live AP graph. unlock_mode 0 (vanilla) skips it -> all type:0, identity.
    unlock_mode = getattr(world, "_ctr_unlock_mode", 0)
    if ut_passthrough:
        # UT re-generation: pin stage-1 / stage-2 requirements from slot_data
        # instead of re-rolling the sphere search (issue #29). Vanilla-mode seeds
        # carry only type-0 pads, so this is a no-op there, matching the skip below.
        _ut_reconstruct_unlock(world, ut_passthrough)
    elif unlock_mode in (1, 2):
        reward_track_for = _build_reward_track_resolver(world)
        # two_stage_density = off (Icebound clear_stage2_unlocks): collapse every
        # stage 2 to OPEN -- no two-stage hold-back, no token pinning; the seed
        # behaves like the single-stage baseline. This absorbed the former
        # `autounlock_ctrchallenge_relicrace` toggle (2026-07-15 release polish):
        # the old off=echo behaviour was outcome-identical (an echoed stage-2
        # requirement is met the moment stage 1 is), so one knob now covers it.
        collapse_s2 = (getattr(world.options.two_stage_density, "current_key",
                               "standard") == "off")
        world._ctr_two_stage_active = not collapse_s2
        pad_reqs = run_sphere_search(world, unlock_mode, reward_track_for,
                                     collapse_stage2=collapse_s2,
                                     include_gem_cups=bool(world.options.include_gem_cups.value))
        # Filter to the pad kinds the YAML actually randomizes: race always;
        # crystal only when include_battle_arenas; cups only when include_gem_cups;
        # trials always.
        inc_arenas = bool(world.options.include_battle_arenas.value)
        inc_cups = bool(world.options.include_gem_cups.value)
        _NO_STAGE2 = {"type": 0, "count": 0, "colour": -1}  # native: opens immediately
        for track, stages in pad_reqs.items():
            pad_name = _pad_name_for_track(track)
            meta = world.warp_pad_ids.get(pad_name)
            if meta is None:
                continue
            kind = meta["kind"]
            if kind == "crystal" and not inc_arenas:
                continue  # battle arenas not in this seed's shuffle pool
            if kind == "cup" and not inc_cups:
                continue  # gem cups not in this seed's pool -> keep vanilla token gate
            # 'trial' (Slide/Turbo) and 'cup' (Red/Green/Blue/Yellow/Purple Cup):
            # SINGLE-STAGE randomized -- the sphere-search
            # assigned a stage-1 entry requirement (stages[2] is always None for a
            # non-TROPHY_TRACK), wired as a normal single-stage node. No longer
            # native-fixed (the OPEN model). The to_slot_req(s2) below yields the
            # native "no stage 2" sentinel for them automatically.
            s1 = stages[1]
            s2 = stages[2]
            # STAGE 1 (unchanged contract).
            world.warp_pad_unlock[pad_name] = to_slot_req(s1)
            if s1 is not None:
                world.warp_pad_unlock_concrete[pad_name] = s1
            # STAGE 2 — physical-pad keyed slot_data (None -> type 0 = no gate).
            world.warp_pad_unlock_stage2[pad_name] = (
                to_slot_req(s2) if s2 is not None else dict(_NO_STAGE2)
            )
            # Concrete stage-2 req keyed by the DESTINATION track (the track this
            # physical pad loads), where its CTR/relic locations live, for Rules.
            if s2 is not None:
                dest_track = reward_track_for(track)
                world.warp_pad_unlock_stage2_concrete[dest_track] = s2

        # NO reward pinning (the OPEN model). The relic Time Trials and CTR Token
        # Challenges keep flowing through the NORMAL multiworld pool and the relic-tier
        # sliders exactly as on main -- relics appear as genuine progression items, not
        # locked-to-location vanilla rewards. Solvability of the stage-2 gates is
        # provided by (a) the sphere-search only ever assigning a stage-2 requirement
        # whose item TYPE is owned in the synthetic inventory at that sphere, and (b)
        # the per-pad RELAX-not-pin fallback (warp_pad_logic.run_sphere_search) that
        # collapses a pad's tier 2 to equal its tier 1 when nothing is ownable. AP's
        # fill_restrictive then seats the required progression in the (now un-pinned,
        # plentiful) reachable location frontier. stage2_pin stays empty.

    # --- Vanilla-hub return-exit drift fix (Option 1b) -----------------------
    # Under destination shuffle the wiring loop above rewires only the FORWARD
    # pad exits; every destination region's "<Dest> -> Hub" return exit still
    # points at its VANILLA hub, handing AP an ungated phantom edge into hubs
    # the player cannot reach on foot (in-game a warp-pad race returns you to
    # the PHYSICAL pad, native is the source of truth). Proven load-bearing on
    # 2026-07-17 (community seed 87763653607652956054: fill placed all 4 Keys
    # behind phantom edges -> in-game hard lock, zero Keys obtainable).
    # Retarget each shuffled destination's return exit to the PHYSICAL hub of
    # the pad that loads it, so the fill graph matches the game. Runs AFTER
    # run_sphere_search on purpose (sub-variant 1b of the 2026-07-10 drift
    # evidence note): the sphere search keeps its already-fuzzed view of the
    # graph; only AP's main fill and reachability see the corrected topology.
    if pad_dest_region:
        pad_phys_hub = {}
        for reg in data["regions"]:
            for ex in reg.get("exits", []):
                if ex["name"] in pad_dest_region:
                    pad_phys_hub[ex["name"]] = reg["name"]
        for pad_name, dest_region_name in pad_dest_region.items():
            phys_hub = pad_phys_hub.get(pad_name)
            ret = mw.regions.entrance_cache[player].get(
                f"{dest_region_name} -> Hub")
            new_target = region_lookup.get(phys_hub) if phys_hub else None
            if ret is None or new_target is None:
                continue
            old_target = ret.connected_region
            if old_target is new_target:
                continue  # same-hub shuffle: already game-accurate
            if old_target is not None and ret in old_target.entrances:
                old_target.entrances.remove(ret)
            ret.connected_region = None
            ret.connect(new_target)

    return regions
