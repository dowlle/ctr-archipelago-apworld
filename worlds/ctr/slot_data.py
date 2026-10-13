"""Native slot_data assembly for the CTR world (split out of __init__.py, issue #309).

Pure move: every function here was a method body on ctrAPWorld. The World
class keeps the public methods (fill_slot_data and the _resolve_* helpers)
and delegates to these functions with itself as `world`, so the emitted
slot_data is unchanged.
"""

from typing import Dict, List

from . import (characters, cortex_vortex_track, hit_character,
               progressive_capability, traps, version, wumpa_family)
from .custom_lettersanity import CUSTOM_LETTERSANITY_CLASS
from .custom_tracks import (custom_tracks_to_wire, resolved_custom_tracks)
from .gem_cup_legs import cup_legs_to_wire, resolved_gem_cup_legs_table
from .item_boxes import ITEM_BOX_CLASS
from .itemsanity import ITEMSANITY_CLASS
from .lettersanity import LETTERSANITY_CLASS
from .Locations import get_total_locations
from .Options import OxideGoal
from .relic_perfect import RELIC_PERFECT_CLASS
from .relic_tiers import (RELIC_TIERS, SLIDE_COLISEUM_LEVEL_ID,
                          slide_coliseum_stage1_wire)
from .wumpa_checks import WUMPA_CLASS


def resolve_warp_pad_map(world) -> Dict[str, int]:
    """{"<physicalPadLevelID>": <targetTrackID>} — ALWAYS present.

    Identity over the 28 in-range pad LevelIDs AND the 5 gem-cup LevelIDs
    (100-104), then overlay any destination-shuffle remap (v3: cups now
    participate, and a track slot may load a cup and vice versa, so remap
    values span {0..27, 100..104}). Empty warp_pad_map -> pure identity.
    """
    m = {str(i): i for i in range(world.WARP_PAD_ID_RANGE)}
    pad_ids = getattr(world, "warp_pad_ids", {})
    # Gem-cup identity base (LevelID 100-104): a v3 seed always carries a cup
    # map so native never has to guess; absent == identity for a v2 native.
    for meta in pad_ids.values():
        if meta.get("kind") == "cup":
            lid = meta["level_id"]
            m[str(lid)] = lid
    for pad_name, target_track_id in getattr(world, "warp_pad_map", {}).items():
        meta = pad_ids.get(pad_name)
        if meta is None:
            continue
        lid = meta["level_id"]
        if 0 <= lid < world.WARP_PAD_ID_RANGE or meta.get("kind") == "cup":
            m[str(lid)] = int(target_track_id)
    return m


def resolve_gem_cup_legs(world) -> Dict[str, List[int]]:
    """{"<cupLevelID 100..104>": [trackLevelID x4]} -- the gem_cup_legs block
    (issue #166, schema 7).

    Serializes the seed's leg map (resolved in create_regions) as LevelIDs,
    always all five cups: the smallest COMPLETE mapping -- a partial map
    would force native to guess the missing cups, and the whole block is
    simply omitted when the option is off (native then keeps its vanilla
    advCupTrackIDs table, which is exactly what an option-off seed uses).
    Fails loudly rather than silently falling back to vanilla if
    create_regions never ran (N3, Opus review).

    The map it reads is the COMPLETE table (`world.gem_cup_legs_table`),
    not the logic map: a cup displaced by a custom track legs nothing in
    LOGIC,
    but its native table row still has to be four real LevelIDs or the
    wire stops being the complete mapping every consumer relies on. Which
    cup is displaced travels in the `custom_tracks` block, where native
    reads it before it ever loads a leg, so the displaced row is simply
    never used rather than being ambiguous.
    """
    return cup_legs_to_wire(resolved_gem_cup_legs_table(world))


def resolve_warp_pad_unlock(world) -> Dict[str, Dict[str, Dict[str, int]]]:
    """{"<padLevelID>": {"stage1": {type,count,colour},
                         "stage2": {type,count,colour}}} — ALWAYS present.

    Two-stage contract (Option A, schema_version 2). Stage 1 opens the pad's
    Trophy Race; stage 2 (the 16 trophy pads only) opens that pad's CTR Token
    Challenge + 3 relic Time Trials, ANDed on top of stage 1. Both are keyed by
    PHYSICAL pad LevelID. Every in-range pad defaults to stage1/stage2 type 0
    ({0,0,-1}) so a vanilla-mode / fixed / no-stage-2 pad falls back to native's
    own rule (type 0 stage 2 = native opens the token/relic menu immediately).
    """
    pad_ids = getattr(world, "warp_pad_ids", {})
    unlock = getattr(world, "warp_pad_unlock", {})
    unlock_s2 = getattr(world, "warp_pad_unlock_stage2", {})

    def _req(d):
        return {"type": int(d["type"]), "count": int(d["count"]),
                "colour": int(d["colour"])}

    _ZERO = {"type": 0, "count": 0, "colour": -1}

    # Default all in-range pad LevelIDs to type 0 for both stages.
    out: Dict[str, Dict[str, Dict[str, int]]] = {}
    for meta in pad_ids.values():
        lid = meta["level_id"]
        if 0 <= lid < world.WARP_PAD_ID_RANGE:
            out[str(lid)] = {"stage1": dict(_ZERO), "stage2": dict(_ZERO)}

    # Overlay the per-seed randomized requirements (stage 1 + stage 2).
    for pad_name, req in unlock.items():
        meta = pad_ids.get(pad_name)
        if meta is None:
            continue
        lid = meta["level_id"]
        if 0 <= lid < world.WARP_PAD_ID_RANGE:
            out[str(lid)]["stage1"] = _req(req)
        elif meta.get("kind") == "cup":
            # Gem cups (LevelID 100-104) sit OUTSIDE the dense 0..27 array, but
            # when include_gem_cups randomizes them they carry a SINGLE-STAGE
            # requirement (Round-4). Emit them keyed by their own LevelID, with a
            # type-0 ({0,0,-1}) stage 2 (cups have no second stage). They appear
            # ONLY when world.warp_pad_unlock holds them (option ON); option OFF
            # leaves no cup key, so native keeps its own fixed cup rule unchanged.
            # The Key-2 Cups Room hub gate is enforced separately (native hub
            # progression + the AP region rule); this requirement is ANDed on top.
            out.setdefault(
                str(lid), {"stage1": dict(_ZERO), "stage2": dict(_ZERO)})
            out[str(lid)]["stage1"] = _req(req)
    # Vanilla mode, fewer than 10 Sapphire Relics created (ruling 2026-10-01):
    # the Slide Coliseum pad opens at the Sapphires that exist. Native
    # prefers a non-type-0 stage 1 on pad 16 over its hardcoded 10, so the
    # lowered gate travels here; the exit rule in Regions reads the same
    # helper. No entry means the retail 10 on both sides.
    _slide = slide_coliseum_stage1_wire(world)
    if _slide is not None:
        out.setdefault(str(SLIDE_COLISEUM_LEVEL_ID),
                       {"stage1": dict(_ZERO), "stage2": dict(_ZERO)})
        out[str(SLIDE_COLISEUM_LEVEL_ID)]["stage1"] = dict(_slide)
    for pad_name, req in unlock_s2.items():
        meta = pad_ids.get(pad_name)
        if meta is None:
            continue
        lid = meta["level_id"]
        if 0 <= lid < world.WARP_PAD_ID_RANGE:
            out[str(lid)]["stage2"] = _req(req)
        elif meta.get("kind") == "cup":
            # Cup pad (LevelID 100-104) hosting a TROPHY-track destination
            # under merged destination shuffle carries a REAL stage 2
            # (contract §2/§4, design §5): stop forcing type-0 on cups. The
            # cup key exists here only when include_gem_cups randomized it
            # (stage 1 already emitted above); setdefault guards the ordering.
            out.setdefault(
                str(lid), {"stage1": dict(_ZERO), "stage2": dict(_ZERO)})
            out[str(lid)]["stage2"] = _req(req)
    return out


def resolve_podium_checks(world) -> Dict[str, object]:
    """Podium position rungs (position-rung rework, shipped 0.1.x) for the native fan-out.

    Schema 6 shape (agreed with the native session):

    {"enabled": bool,
     "locations": {"<levelID>": [held_1st, held_3rd, held_5th,
                                 finish_podium, finish_any], ...}}

    Each per-track value is a 5-slot array of AP location codes in the fixed
    SLOT_ORDER; a rung absent from THIS seed is -1 (native skips it). Keyed by
    physical race-pad LevelID 0..15, which equals the trophy-race track and
    matches the [AP RACE] track field. Only the 16 standard trophy races carry
    podium rungs (boss/token/relic/crystal have no genuine live/finish ladder).

    The placement listener reads this: at the live/finish capture for
    track=<levelID> it sends the rung codes per the ladder (a better result
    grants every lower rung), skipping any -1 slot.

    SCHEMA BUMP: the array shape replaces the v3-era
    {"first","podium","any"} object, so this rides the schema 5 -> 6 bump
    (fill_slot_data). A native predating schema 6 must not read this block as
    the old object; the #8 newer-schema guard covers that direction.
    """
    # #176: the code array comes from the location class itself
    # (PodiumLocationClass.slot_codes), so the wire block and the created
    # locations resolve through the same frozen superset instead of this
    # method re-deriving the name -> code lookup.
    from .podium import PODIUM_CLASS, enabled_trophy_tracks, track_rung_keys
    enabled = bool(world.options.podium_placement_checks.value)
    block: Dict[str, object] = {"enabled": enabled, "locations": {}}
    rung_keys = PODIUM_CLASS.created_rung_keys(world.options)
    if not rung_keys:
        return block
    pad_ids = getattr(world, "warp_pad_ids", {})
    track_to_lid = {
        pad_name[: -len(" Warp Pad")]: meta["level_id"]
        for pad_name, meta in pad_ids.items()
        if pad_name.endswith(" Warp Pad")
    }
    locations: Dict[str, object] = {}
    for track in enabled_trophy_tracks(world.options):
        lid = track_to_lid.get(track)
        if lid is None or not (0 <= lid < world.WARP_PAD_ID_RANGE):
            continue
        locations[str(lid)] = PODIUM_CLASS.slot_codes(track, track_rung_keys(world.options, track))
    block["locations"] = locations
    return block


def resolve_itemsanity_checks(world) -> Dict[str, object]:
    """Ordered 22-code fan-out for the native use-time hook (#145).

    This is called only for an enabled seed.  Its order is the frozen
    item-major class order, resolving through the class index rather than
    rebuilding the code arithmetic at this second call site.
    """
    return {
        "enabled": True,
        "locations": [code for _name, code, _region in
                      ITEMSANITY_CLASS.created_locations(world.options)],
    }


#: The global slot_data schema this apworld emits for a normal seed. The
#: 0.3.0 wire changes share this one step; the number is fixed at integration.
SLOT_DATA_SCHEMA = 18


def fill_slot_data(world) -> Dict[str, object]:
    if hasattr(world, "ctr_content_plan"):
        from . import content_plan
        return content_plan.wire(world)
    o = world.options
    # DERIVED shuffle_warp_pads (slot_data v3): the deprecated boolean option is
    # unwired; the real signal is "did any category participate" == the resolved
    # warp_pad_map being non-empty (set in create_regions as world.shuffle_warp_pads).
    # Kept in ctr_options for old-native log compatibility only.
    derived_shuffle = bool(getattr(world, "shuffle_warp_pads", False))
    # schema_version 7 (0.2.0, issue #166): the top-level gem_cup_legs block.
    # The BUMP is unconditional (Q28 ruling, #152 dossier: "ALWAYS BUMP...no
    # conditional emission". "They should just update the client to be
    # honest. Keeps it simple."). The `gem_cup_legs` block ITSELF stays
    # conditional on the option actually randomizing the cups' legs -- only
    # then does a native need to parse it to load the same tracks the
    # generation logic used. Every 0.2.0 seed, on or off, now declares 7.
    legs_randomized = bool(o.randomize_gem_cup_tracks.value)
    # Custom tracks (Baby T Park spike). A descriptor DISPLACES a cup
    # destination, so a native that cannot serve the custom track would
    # run the retail four-leg cup while this seed's logic says that cup
    # legs nothing -- the same reachability-desync class as the v3 cup
    # destination keys. Schema 8 is unconditional for the public Alpha6
    # pair, following the standing "always bump, never conditionally" rule.
    custom_tracks = resolved_custom_tracks(world)
    # schema_version 9 (0.2.0 RC, issue #320): `goal_oxide` gains the value
    # 3 (`disabled`). The bump is a native-version GATE, not bookkeeping: a
    # schema-8 client reads 3 through AP_ComposedGoalMet's else-if chain,
    # correctly contributes no Oxide completion arm -- and then leaves the
    # garage WIDE OPEN, because its AP_OxideEntryReady only special-cased
    # value 0. It would also still expect the two Oxide location checks
    # this seed no longer contains. Reusing schema 8 would hide that
    # mismatch from the player instead of raising the #8 newer-schema
    # warning. Unconditional per the Q28 standing ruling ("ALWAYS BUMP...
    # no conditional emission"), so every 0.2.0 RC seed declares 9.
    # Schema 11 composes the schema-10 trial-track work with the independent
    # Oxide Final venue descriptor below. A schema-10 client would otherwise
    # load Oxide Station while the seed selected Cortex Vortex.
    # Trial Lettersanity needs the paired 18-track native consumer and
    # split item receipt mapping. Old clients must report a newer seed,
    # not silently discard required trial letter items/checks.
    # Schema 13: encounter priority can skip Oxide 1 and a final win
    # collects both checks. Old clients cannot enforce that contract.
    # Schema 15 (2026-09-13 contract): the Cortex Vortex pad track puts
    # destination 110 in warp_pad_map and gem_cup_legs and removes a
    # destination's checks. Unconditional, per the standing Q28 rule.
    # Schema 16: the top-level `hit_character_encounters` block (block schema 2)
    # plus the always-emitted `ctr_options.hit_character` scalar. Hit
    # Character integrated after Cortex Vortex, so it takes 16, not the 14
    # it was drafted against; a schema-15 client reports the newer seed
    # instead of silently ignoring the encounter data.
    # 2026-09-14: the encounter block moved to its own block schema 2 (the
    # pool draw). The global schema stays 16: 16 was never tagged, the Hit
    # block carries its own version, and a block-schema-1 client refuses a
    # block-2 seed visibly at admission, so a global bump adds nothing.
    # 2026-09-18: the encounter block moved to block schema 3 (the per-guest
    # Key fallback), emitted for every enabled seed. Same reasoning, same
    # global schema 16: a block-2 client refuses a block-3 seed visibly,
    # while a global bump would only add the out-of-date banner to every
    # seed with Hit Character off.
    # Schema 18 (0.3.0 wire step, issue #307 first): the required top-level
    # `trap_identities` block names each trap item's effect by its stable key.
    # A schema-18 native refuses every trap of a seed that lacks the block, so
    # the number must move with it; a pre-18 client shows the out-of-date
    # banner and applies its frozen trap table, which agrees because trap item
    # ids never move. 17 is the separately admitted content-plan profile.
    schema = SLOT_DATA_SCHEMA
    slot_data: Dict[str, object] = {
        "Seed": world.multiworld.seed_name,
        "Slot": world.multiworld.player_name[world.player],
        "TotalLocations": get_total_locations(world),
        # schema_version 6 (position-rung rework, shipped 0.1.x): the
        # podium_checks block changes SHAPE -- each per-track entry becomes a
        # 5-slot code array [held_1st, held_3rd, held_5th, finish_podium,
        # finish_any] (-1 = absent), replacing the v3-era {first,podium,any}
        # object. A native predating schema 6 must not read the old object, so
        # this is a native-version GATE (schema_version >= 6), shipped with the
        # #8 newer-schema warn/refuse. (v5 = oxide-final relic-goal mode/count;
        # v4 = relic-tier colour + goal-rework; v3 = podium + stage-2 padgate;
        # v2 = two-stage contract; v7 = gem_cup_legs; v8 = custom_tracks
        # support and the public Alpha6 pair gate; v9 = goal_oxide value 3
        # (`disabled`), all unconditional.)
        "schema_version": schema,
        "ctr_options": {
            "schema_version": schema,
            # Issue #152: composed goal conditions replace the single
            # `goal` Choice. `goal` stays on the wire, best-effort, purely
            # for spoiler-log / ap-state / debug readability -- a
            # schema>=7-aware native reads ONLY goal_oxide/goal_bosses/
            # goal_gems for evaluation and ignores `goal` entirely (issue
            # #163 already gates ALL goal evaluation on schema_newer, and
            # schema is unconditionally 8 on every Alpha6 seed per Q28, so
            # there is no compat direction left for `goal` to protect).
            # Emitted as the exact legacy-equivalent int when the composed
            # goal happens to match one of the four old single-condition
            # goals, else -1 (no legacy analogue; never read as a real
            # goal value by a schema-aware client).
            "goal": world._legacy_goal_value(),
            "goal_oxide": o.oxide_goal.value,
            "oxide_1_optional": (int(o.oxide_1_optional.value)
                                 if o.oxide_goal.value == OxideGoal.option_101_percent else 0),
            "goal_bosses": o.bosses_required_goal.value,
            "goal_gems": o.gems_required_goal.value,
            # relic_min_time / relics_require_perfect were dropped with their
            # YAML options (2026-07-15 release polish): native parsed both but
            # never enforced them. json_int defaults the absent keys to 0, the
            # exact values every seed ever sent. Reintroduce key+option together
            # when the native enforcement lands.
            # oxide_final_unlock = relic-goal MODE (0-4); oxide_final_count =
            # the shared 1-18 count. 0 (sapphire) stays frozen = the old 0.
            "oxide_final_unlock": o.oxide_final_challenge_unlock.value,
            "oxide_final_count": o.oxide_final_challenge_relic_count.value,
            "oxide_final_track": int(o.oxide_final_track.value),
            "shuffle_warp_pads": derived_shuffle,
            "warp_pad_shuffle_categories": sorted(o.warp_pad_shuffle_categories.value),
            "warp_pad_shuffle_grouping": o.warp_pad_shuffle_grouping.current_key,
            "shuffle_gems": bool(o.shuffle_gems.value),
            "shuffle_keys": bool(o.shuffle_keys.value),
            "warppad_unlock_mode": o.warppad_unlock_requirements.value,
            "slide_coliseum_races": int(o.slide_coliseum_races.value),
            "turbo_track_races": int(o.turbo_track_races.value),
            # Always emitted 0/1; the conditional block below carries
            # the resolved destination and codes when it is 1.
            "cortex_vortex_track": int(o.cortex_vortex_track.value),
            "bossgarage_mode": o.bossgarage_unlock_requirements.value,
            # Warp-pad item display (issue #59): 0 one_pile / 1
            # by_reward_type. ADDITIVE key, no schema bump -- the one_lap_cups
            # precedent: native json_int defaults the absent key to 0, which
            # IS today's one-pile rotation, so an older client on a new seed
            # and a new client on an old seed both behave exactly as they do
            # now. Display only: it steers no gate, no location and no item,
            # and nothing in AP logic reads it, so two seeds differing only in
            # this value are identical apart from the key itself.
            "warp_pad_item_display": o.warp_pad_item_display.value,
            # AP-logo marker colours (issue #212): on = item-classification
            # tints, off = one uniform greyish-white colour. ADDITIVE key,
            # no schema bump -- native json_int defaults the absent key to 1
            # (colours enabled), the shipped behaviour, so an older client on
            # a new seed and a new client on an old seed both render exactly
            # as they do now. Display only: it tints no gate, no location, no
            # item, and nothing in AP logic reads it, so two seeds differing
            # only in this value are identical apart from the key itself.
            "ap_item_type_colors": bool(o.ap_item_type_colors.value),
            # AP item box colours (ruling R11; default on per the
            # 2026-09-23 ruling): on = each AP item box wears its item's
            # Archipelago colour (each player can still turn that off in the
            # client), off = every box pink and the players cannot turn it
            # on. ADDITIVE key, no schema bump -- native json_int defaults
            # the absent key to 0 (pink), so a seed from before this key
            # shows pink boxes, as it always did. Display only: nothing in
            # AP logic reads it.
            "color_boxes_by_item": bool(o.color_boxes_by_item.value),
            # QoL, additive (no schema bump): one-lap cup races. Native
            # json_int defaults the absent key to 0, so a pre-one-lap-cups
            # native (or an old seed on a new native) is exactly vanilla lap
            # counts. Pure pace setting -- never touches logic/fill/reachability.
            "one_lap_cups": bool(o.one_lap_cups.value),
            # DeathLink (issue #6): ADDITIVE keys, no schema bump. A native
            # predating these keys reads neither and DeathLink stays off (the
            # one_lap_cups precedent: absent additive key degrades to the 0/off
            # default). death_link is 0 off / 1 mask_reset / 2 any_hit /
            # 3 race_loss (#286: native falls back to mask reset for any
            # nonzero value it does not know, so no bump); amnesty
            # is send-every-Nth (>=1). Native enables the "DeathLink" connection
            # tag and its send/receive plumbing only when death_link != 0.
            "death_link": o.death_link.value,
            # DeathLink send conditions (0.2.3), same additive/no-bump
            # convention, always emitted. int bitmask: 1 mask_grab,
            # 2 weapon_hit, 4 race_loss. While the option is left at its
            # default this is the legacy coupling derived from death_link
            # (mask_reset 1, any_hit 1|2, race_loss 1|4, off 0); a native
            # that finds the key absent applies the same fallback itself.
            # An explicit empty list is 0: receive only.
            "death_link_send": o.death_link_send.send_mask(
                o.death_link.value),
            "deathlink_amnesty": o.deathlink_amnesty.value,
            # Universal Tracker: this seed's RESOLVED per-tier relic
            # classification (True = progression, False = useful), exactly as
            # create_item applied it. ADDITIVE key, no schema bump -- native
            # reads ctr_options by explicit named key (ap_seedcfg json_int) and
            # never enumerates, so an unknown key is inert there; it is also
            # purely a tracker-side hint and steers nothing native does.
            # UT cannot recompute this (the per-tier sliders are not on the
            # wire) and guessing "all progression" made it report vanilla
            # Sapphire-gated locations as in-logic that the server can never
            # send -- see _relic_progression_map.
            "relic_progression": {
                tier: bool(flag) for tier, flag in
                (getattr(world, "_ctr_relic_prog", None)
                 or world._relic_progression_map()).items()
            },
            # Issue #171: exactly which Time Trial locations this seed
            # created per relic tier (AP location codes, not names -- the
            # datapackage already carries name<->code). ADDITIVE key, no
            # schema bump -- native ignores it today (package 3, the
            # local-grant native companion, is what will read it; not
            # this order -- see the build note); Universal Tracker is the
            # one real consumer right now, via
            # relic_tiers.restore_relic_tier_keep_from_wire, so its
            # re-generation creates the SAME location set the real seed
            # did instead of re-rolling a different random subset.
            "relic_tier_locations": {
                relic_item: sorted(
                    world.location_name_to_id[name]
                    for name in world._ctr_relic_keep.get(relic_item, ()))
                for _tier_label, relic_item, _opt_name in RELIC_TIERS
            },
            # This apworld's own world_version, read at generation time from
            # the packaged archipelago.json (AutoWorld sets world_version from
            # the manifest; it can never be assigned in-class). Under the
            # release policy the apworld's world_version IS the pair version,
            # so a seed carrying a version higher than a client's compiled
            # CTR_AP_VERSION proves a newer client exists -- that is the whole
            # basis of the client's zero-network update notice (#150).
            # ADDITIVE key, no schema bump (the one_lap_cups precedent): a
            # native predating it reads nothing and says nothing, and the key
            # steers no gate, no location, no item and no logic, so two seeds
            # differing only in it are identical apart from the key.
            "world_version": world.world_version.as_simple_string(),
            # Human-facing prerelease identity. Archipelago requires the
            # manifest world_version above to stay numeric. This additive
            # diagnostic key never steers logic, gates, items or locations.
            "build_version": version.BUILD_VERSION,
            # Progressive Boost / Progressive Stats (issues #12, #13).
            # ADDITIVE keys, no schema bump (Q28 already makes schema 7
            # unconditional on every 0.2.0 seed, so this feature rides
            # that standing bump rather than needing its own). boost_mode
            # / stats_mode: 0 off / 1 shared_global / 2 per_character.
            # Native and Universal Tracker consume the same scalar modes;
            # per-racer ranks need no extra wire because ReceivedItems
            # already carries the frozen per-character item names.
            # boost_blue_fire only matters when boost_mode != 0. No
            # native consumer exists yet (apworld-only order scope): a
            # pre-this-feature native reads none of these three keys by
            # explicit named lookup and is unaffected either way.
            **progressive_capability.fill_slot_data(world),
            # Ruled capability-logic preference. Always emitted because
            # Universal Tracker must rebuild the same seven-track gates.
            "logic_difficulty": int(o.logic_difficulty.value),
            # Always emit this scalar.  It is additive tracker/diagnostic
            # metadata; option-off parity applies to generated content and
            # to the conditional top-level feature block below.
            "itemsanity": bool(o.itemsanity.value),
            # Hit Character encounters (0.2.1 candidate). Always emitted as
            # a boolean, on or off, so a tracker reads the seed's real
            # configuration; the conditional top-level block below carries
            # the resolved encounter data and is present only when enabled.
            "hit_character": bool(o.hit_character.value),
            # Relic Race perfect checks (#49). Always emitted as a boolean,
            # same convention as itemsanity and hit_character; the
            # top-level `relic_perfect_checks` block below is present only
            # when enabled. Native reads the block, not this scalar.
            "relic_perfect_checks": bool(o.relic_perfect_checks.value),
            # The wumpa family's two scalars (2026-08-10 ruling). Always
            # emitted, same convention as itemsanity and tizi_helper, and
            # DIAGNOSTIC / TRACKER ONLY: native drives both from received
            # items (a bundle hands over fruit on arrival, the ladder is the
            # count of copies received) and reads neither key.
            **wumpa_family.fill_slot_data(world),
            # The wumpa CHECK mode (2026-08-29 spec). Always emitted as a raw
            # scalar even when off, unlike the pre-widening arrangement where
            # block presence was the only signal. Block presence can say
            # "some Wumpa check exists"; it cannot distinguish `global` from
            # `per_track` without a tracker re-deriving a three-way setting
            # from block shape, which is exactly the inference the standing
            # convention exists to avoid. The conditional block below carries
            # the resolved code mapping.
            "wumpa_check": int(o.wumpa_check.value),
            # Tizi Helper (#223), same always-emitted scalar convention.
            # DIAGNOSTIC / TRACKER ONLY: native does NOT read this key. The
            # helper's runtime gate is "did this slot receive item 35010188"
            # (plus, when itemsanity is on, the Mask item), which the client
            # already knows from ReceivedItems, and itemsanity's own on/off
            # is read off server location membership. The scalar exists so a
            # tracker and a Universal Tracker restore can see the option
            # without inferring it from an item that may not have arrived yet.
            "tizi_helper": bool(o.tizi_helper.value),
            # Turbo Grant (#224), same always-emitted scalar convention and
            # the same DIAGNOSTIC / TRACKER ONLY status: native does NOT read
            # this key. Its runtime gate is "did this slot receive item
            # 35010189" (plus, when itemsanity is on, the `Turbo` weapon
            # item), both of which the client already knows from
            # ReceivedItems, and itemsanity's own on/off is read off server
            # location membership. Reading a config flag as well would add a
            # second source of truth for one boolean.
            "turbo_grant": bool(o.turbo_grant.value),
            "lettersanity": int(o.lettersanity.value),
            # #109 box scalars, same convention: both always emitted raw
            # (shortcut_knowledge even when box_locations is false, so
            # trackers can read the tier without inferring it); the
            # conditional item_box_checks block below is the feature.
            # box_locations=true REQUIRES the 0.2.0 native that spawns the
            # crates -- on an older client these locations can never be
            # checked (seating spec 5.4); schema 7 + the #8 banner already
            # cover the version direction, so no bump.
            "box_locations": bool(o.box_locations.value),
            "shortcut_knowledge": int(o.shortcut_knowledge.value),
            # Character phase (#54/#209). Eight scalars, all emitted
            # unconditionally so a tracker reads the seed's real character
            # configuration without inferring it from block presence.
            # `stat_source` / `stat_owner` / `stat_editing_allowed` are the
            # RESOLVED outcome of the progressive-vs-editable precedence:
            # native must read those and must NOT re-implement the rule
            # (2026-08-08 ruling; the precedence lives in exactly one
            # function, characters.effective_stat_config).
            **characters.fill_slot_data(world),
        },
        "warp_pad_map": world._resolve_warp_pad_map(),
        "warp_pad_unlock": world._resolve_warp_pad_unlock(),
        "boss_garage_req": getattr(world, "boss_garage_req", {}),
        "podium_checks": world._resolve_podium_checks(),
        # Racer-locked pads (#54/#209, R8). Top-level block rather than a
        # 10th `Req` type on purpose -- a lock ANDs onto the pad's existing
        # stage-1 requirement instead of replacing it, and a native that
        # does not know this block simply never sees it rather than hitting
        # a `switch` default on an unevaluable type. See the characters.py
        # docstring and Contract 7h. Always present, `pads` empty when off.
        "racer_locks": characters.racer_lock_slot_data(world),
        "oxide_final_venue": {
            "version": 1,
            "track": ("cortex_vortex" if int(o.oxide_final_track.value) == 0
                      else "oxide_station"),
            "opponent": "nitros_oxide",
            "location": 35011105,
            # Widened 2026-09-13: the code exists whenever per-track
            # Wumpa is on and Cortex Vortex is raced at all -- as a pad
            # track, or as this venue with Oxide content present.
            "wumpa_location": (35016121 if WUMPA_CLASS.cortex_vortex_active(o)
                               else -1),
            "host_level_id": 13,
            "lev_sha256": ("4e3a2daf56c67be3ac645d3bb5375e516"
                           "c828a0bca24c35ac69b3366c466fe13"),
            "vrm_sha256": ("4131444b9d1d53971befcfd11349efcea"
                           "f887c20b795c8890fdcb2c36bdff07d"),
        },
    }
    from .trial_trophy import TRIAL_TROPHY_CLASS, TRIAL_TRACKS
    if TRIAL_TROPHY_CLASS.is_enabled(o):
        trial_locations = {}
        for track, level_id in zip(TRIAL_TRACKS, (16, 17)):
            created = set(TRIAL_TROPHY_CLASS.created_location_names(o))
            trophy = TRIAL_TROPHY_CLASS.location_name(track)
            ctr = TRIAL_TROPHY_CLASS.ctr_location_name(track)
            trial_locations[str(level_id)] = [
                TRIAL_TROPHY_CLASS.code_for(track) if trophy in created else -1,
                TRIAL_TROPHY_CLASS.name_to_code()[ctr] if ctr in created else -1,
            ]
        slot_data["trial_track_checks"] = {
            "enabled": True,
            "locations": trial_locations,
        }
    if cortex_vortex_track.track_on(o):
        # 2026-09-13 contract: present only with the option on.
        slot_data["cortex_vortex_track"] = cortex_vortex_track.wire_block(world)
    if legs_randomized:
        # Issue #166: the five cups' leg tracks (see _resolve_gem_cup_legs).
        # Emitted only when randomized -- absent means vanilla legs to both
        # native (advCupTrackIDs fallback) and UT (reconstruct falls back to
        # the vanilla table). HARD bump (schema 7 above), NOT the additive
        # no-bump precedent: an old native keeps loading the vanilla legs
        # while this seed's podium logic follows the shuffled map.
        slot_data["gem_cup_legs"] = world._resolve_gem_cup_legs()
    if o.itemsanity.value:
        # Additive under schema 7.  Omitted when off, so disabled seeds do
        # not gain a dormant 22-slot feature block.
        slot_data["itemsanity_checks"] = world._resolve_itemsanity_checks()
    hit_character_block = hit_character.slot_data(world)
    if hit_character_block is not None:
        # Conditional on enabled, matching the scalar's always-emit
        # convention. The block is fully resolved in generate_early (seed
        # drawn once, cached); UT pins the connected seed's block verbatim.
        slot_data["hit_character_encounters"] = hit_character_block
    if o.relic_perfect_checks.value:
        # Relic Race perfect checks (#49). Additive, no schema bump, same
        # off-parity convention as itemsanity: omitted when off. LevelID ->
        # [code] for every created check (Contract, relic_perfect_checks).
        slot_data["relic_perfect_checks"] = RELIC_PERFECT_CLASS.wire_block(o)
    if int(o.lettersanity.value) != 0:
        slot_data["lettersanity_checks"] = LETTERSANITY_CLASS.wire_block(o)
    custom_letters = CUSTOM_LETTERSANITY_CLASS.wire_block(o)
    if custom_letters is not None and custom_letters["tracks"]:
        slot_data["custom_lettersanity_checks"] = custom_letters
    if int(o.wumpa_check.value) != 0:
        # Additive under schema 7, same off-parity convention as itemsanity:
        # omitted entirely when the mode is off, while the raw scalar above
        # is always emitted.
        #
        # NATIVE READS THIS BLOCK from the 2026-08-29 spec onwards. Before it,
        # the client hardcoded 35016100 and gated purely on server location
        # membership; per-track checks make that impossible, because the seed
        # decides which of the 19 destination codes exist and which custom
        # destination (if any) is live. The wire is now the authority on which
        # codes exist, and native must never hardcode the new ranges. Location
        # membership remains the final send gate on top of it.
        slot_data["wumpa_checks"] = WUMPA_CLASS.wire_block(o)
    if o.box_locations.value:
        # Additive under schema 7, same off-parity convention. The block
        # (18 tracks x fixed 15-entry code arrays, -1 = slot not live,
        # plus the placement_counts desync guard) is built by the class
        # so the wire and the created locations resolve through one
        # seating decision. Slot order is the placement-file order
        # COUNTED ACROSS THE FILE -- native must count the same way
        # (item_boxes module docstring; Contract 7e).
        slot_data["item_box_checks"] = ITEM_BOX_CLASS.wire_block(o)
    if custom_tracks:
        # The custom-track descriptor, forwarded verbatim from the YAML
        # (normalized) plus the resolved bindings. This is what replaces
        # the native loader's config.ini section: the seed, not a file
        # sitting next to the executable, is what says which track is
        # loaded, which cup it takes over and which digests must match.
        #
        # Emitted only when a track is bound, so an option-off seed's wire
        # is untouched. Carries its OWN `version` as well as riding the
        # schema 8 bump above -- the schema number gates whether a native
        # may trust this seed at all, the block version gates whether it
        # understands this block's shape as it evolves.
        slot_data["custom_tracks"] = custom_tracks_to_wire(custom_tracks,
                                                            world.options)
    # Race-loss DeathLink stakes (0.2.4, Contract 7m): every win check's
    # logic as data, serialised from the installed rule terms. Always
    # emitted with its own block version; no schema bump, because an older
    # native ignores the key and keeps the 0.2.3 send behaviour.
    from .win_logic import wire_block
    slot_data["win_logic"] = wire_block(world)
    slot_data["trap_identities"] = traps.trap_identities_block(world.item_name_to_id)
    return slot_data
