import json
import pkgutil
from BaseClasses import Region, Entrance, EntranceType
from .Locations import create_location
from .warp_pad_logic import (
    run_sphere_search, to_slot_req, build_warp_pad_map, HUB_STATIC,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import ctrAPWorld


# ---------------------------------------------------------------------------
# Native-randomization support (Phase-2 MVP).
# Shared slot_data contract: apworld EMITS resolved values, native PARSES.
# See spec "2026-06-22 -- Spec -- Randomized Playthrough MVP (Phase 2-MVP)".
# ---------------------------------------------------------------------------

# Per-pad unlock requirements are produced by warp_pad_logic.run_sphere_search
# (Icebound's real free-subset + sphere-search algorithm), not drawn i.i.d. here.

# Boss-garage trophy thresholds (vanilla 4/8/12/16). Oxide stays keys.
BOSS_TROPHY = {"ripper_roo": 4, "papu_papu": 8, "komodo_joe": 12, "pinstripe": 16}


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


def _resolve_boss_reqs(boss_mode):
    """Resolve all 3 boss-garage modes to flat {type,count} server-side.

    MVP: modes 0/1/2 all collapse to trophy-count gates (4/8/12/16). The real
    bossgarage_mode int still ships in ctr_options so a future native build can
    branch; today native enforces these flat counts. Oxide = 4 keys, fixed.
    """
    req = {b: {"type": 1, "count": c} for b, c in BOSS_TROPHY.items()}
    req["oxide"] = {"type": 2, "count": 4}
    return req


def create_regions(world: "ctrAPWorld"):
    """Build all regions, exits, and locations from JSON definitions."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/world.json").decode("utf-8")
    )

    player, mw = world.player, world.multiworld

    # --- Resolve native-randomization options up front -------------------
    opts = world.options
    do_shuffle = bool(opts.shuffle_warp_pads.value)            # STRETCH gate
    unlock_mode = opts.warppad_unlock_requirements.value       # 0 vanilla / 1 randomized / 2 no-4-keys
    boss_mode = opts.bossgarage_unlock_requirements.value      # 0 orig4 / 1 same_hub / 2 trophies

    world.warp_pad_ids = _load_warp_pad_ids()
    world.shuffle_warp_pads = do_shuffle

    # --- Comfort guards (Icebound force_vanilla_turbotrack / limit_arena_gemcup) ---
    # Activate only in Icebound's exact condition: warp-pad unlock = VANILLA and gems
    # NOT shuffled. There the Turbo Track pad keeps its vanilla 5-gem gate, so any
    # required item reachable only through it forces the tedious tokens -> gem cups ->
    # 5 gems chain. The flag drives (a) build_warp_pad_map keeping Gem Cup / trial pads
    # out of the trophy-pad destination shuffle (so a Gem Cup can never land in the
    # Turbo Track pad), and (b) create_items pinning Turbo Track's relic rewards
    # vanilla so progression is never placed behind that gate. Inert when unlocks are
    # randomized or gems are shuffled; OFF removes the guard (allows the chain).
    world._ctr_comfort_guards = bool(opts.comfort_guards.value)
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
    # actually loads (A.4<->logic coupling). Empty (identity) when shuffle off.
    world.warp_pad_map = build_warp_pad_map(world) if do_shuffle else {}

    # Boss-garage requirements, resolved to flat {type,count}.
    world.boss_garage_req = _resolve_boss_reqs(boss_mode)

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

    # Remove the vanilla per-track trophy floor from the trophy-race LOCATION when
    # warp-pad requirements are RANDOMIZED. world.json keys numTrophiesToOpen on
    # "<track>: Trophy Race" by TRACK (the vanilla unlock spine). Keeping it would
    # (a) mis-key under destination shuffle (a low-floor pad loading a high-floor
    # track inherits the wrong floor -> the progression stall) and (b) force a
    # deterministic vanilla trophy path into every seed. In randomized mode the
    # randomizer owns ALL entry requirements (sphere-search per-pad reqs + truly
    # free bootstrap pads), so we drop the vanilla floor entirely here; free pads
    # are emitted as "0 trophies" (to_slot_req) so native never falls back to the
    # floor. Vanilla unlock mode (0) is left untouched and keeps its real floors.
    # (Time-trial / token locations are gated by can_reach(Trophy Race) in
    # Rules.add_time_trial_and_ctr_requirements, so they follow automatically.)
    if unlock_mode in (1, 2):
        for region in regions:
            if getattr(region, "type", None) != "race":
                continue
            for loc in region.locations:
                if loc.name.endswith(": Trophy Race"):
                    loc.logic_text = "True"

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
    # Key-2 Cups Room hub gate (Stef's HARD CONSTRAINT: cups STAY behind their key
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

    # AP destination shuffle: rewire each shuffled warp-pad exit to the track
    # region it ACTUALLY loads, so AP-core (item placement + solvability) reasons
    # about the same topology native runs. The exit stays in its PHYSICAL hub
    # region and keeps its physical-pad access rule (Rules.add_warp_pad_unlock_rules)
    # + the hub boss-key gate, so the requirement and keys apply to the PHYSICAL
    # pad while the locations reached are the DESTINATION track's. Empty (identity)
    # when shuffle is off. warp_pad_map is {pad_exit_name: dest_track_levelID};
    # level_id maps back to a track name (== region name) to find the dest region.
    _id_to_track = {
        meta["level_id"]: pad_name[: -len(" Warp Pad")]
        for pad_name, meta in world.warp_pad_ids.items()
        if pad_name.endswith(" Warp Pad")
    }
    pad_dest_region = {}
    for pad_name, dest_lid in getattr(world, "warp_pad_map", {}).items():
        dest_track = _id_to_track.get(dest_lid)
        if dest_track is not None:
            pad_dest_region[pad_name] = dest_track

    # VANILLA unlock mode + destination shuffle: the vanilla trophy floor stays on
    # the trophy-race LOCATION (keyed by track), but native keys numTrophiesToOpen
    # by the PHYSICAL pad. Under shuffle a low-floor pad loading a high-floor track
    # would demand the destination's floor -> unsolvable (FillError). Re-key each
    # shuffled destination track's trophy-race floor to the PHYSICAL pad that loads
    # it. (Randomized modes already strip the floor above; this branch is only for
    # vanilla mode, which keeps real floors but must still follow the physical pad.)
    if unlock_mode == 0 and do_shuffle:
        orig_floor = {
            reg["name"]: loc.get("requires", "True")
            for reg in data["regions"] if reg.get("type") == "race"
            for loc in reg.get("locations", [])
            if loc["name"].endswith(": Trophy Race")
        }
        for pad_name, dest_track in pad_dest_region.items():
            phys = pad_name[: -len(" Warp Pad")] if pad_name.endswith(" Warp Pad") else pad_name
            if phys == dest_track:
                continue
            dest_region = region_lookup.get(dest_track)
            if dest_region is None or phys not in orig_floor:
                continue
            for loc in dest_region.locations:
                if loc.name.endswith(": Trophy Race"):
                    loc.logic_text = orig_floor[phys]

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
    if unlock_mode in (1, 2):
        reward_track_for = _build_reward_track_resolver(world)
        # autounlock_ctrchallenge_relicrace (Icebound clear_stage2_unlocks): collapse
        # every stage 2 to OPEN. Then there is no two-stage hold-back and no token
        # pinning -- the seed behaves like the single-stage baseline.
        collapse_s2 = bool(world.options.autounlock_ctrchallenge_relicrace.value)
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
            # native-fixed (Stef's OPEN model). The to_slot_req(s2) below yields the
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

        # NO reward pinning (Stef's OPEN model). The relic Time Trials and CTR Token
        # Challenges keep flowing through the NORMAL multiworld pool and the relic-tier
        # sliders exactly as on main -- relics appear as genuine progression items, not
        # locked-to-location vanilla rewards. Solvability of the stage-2 gates is
        # provided by (a) the sphere-search only ever assigning a stage-2 requirement
        # whose item TYPE is owned in the synthetic inventory at that sphere, and (b)
        # the per-pad RELAX-not-pin fallback (warp_pad_logic.run_sphere_search) that
        # collapses a pad's tier 2 to equal its tier 1 when nothing is ownable. AP's
        # fill_restrictive then seats the required progression in the (now un-pinned,
        # plentiful) reachable location frontier. stage2_pin stays empty.

    return regions
