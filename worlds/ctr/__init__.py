import logging
import json
import os
from typing import ClassVar, Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from Options import OptionError
from worlds.AutoWorld import World, CollectionState, WebWorld
from .elastic_bounds import CTRSettings
from .custom_tracks import (effective_custom_destinations,
                            reconstruct_custom_tracks_from_wire,
                            replacement_trophy_location,
                            resolved_custom_tracks)
from .Locations import CTR_LOCATION_CLASSES, get_location_names
from .Items import load_item_table
from .itemsanity import ITEM_NAMES
from .custom_lettersanity import CUSTOM_LETTER_ITEM_DATA
from . import boss_track_shuffle
from . import cortex_vortex_track
from .cortex_vortex_track import LETTER_ITEM_DATA as CORTEX_VORTEX_LETTER_ITEM_DATA
from .minted_items_030 import ITEM_DATA as MINTED_030_ITEM_DATA, MINTED_TRAP_ITEM_NAMES
from .named_tracks import (NAMED_TRACKS, NAMED_TRACK_ITEM_DATA,
                           validate_tracks as _validate_named_tracks)
from . import wumpa_family
from . import lettersanity
from .Options import (ctrAPOptions, OxideGoal, FinalOxideUnlock,
                      create_option_groups)
from . import characters
from . import hit_character
from . import relic_perfect
from . import rung_sizer
from . import warp_pad_rules
from .spoiler_pad_map import changed_pad_destination_rows
from . import version
from .Regions import create_regions
from .relic_tiers import (
    draw_relic_tier_keep, restore_relic_tier_keep_from_wire,
    resolve_comfort_guards,
)
from .Rules import set_rules
from .Types import ctrAPItem


# The trap family now lives in traps.py, which owns the canonical names, the
# `trap_weights` machine keys and the weighted draw as ONE table -- see that
# module's docstring for the 0.2.0 renames (#280) and the buildable rule. The
# three lists are re-exported here because they were importable from the
# package before the move, and because everything else in this file reads them
# by these names.
#
# TRAP_ITEM_NAMES is the BUILDABLE set: it drives the trap_fill_percentage draw
# and its order is pinned to native's AP_TrapEffect enum (ap/ap_traps.h). All
# 20 registered traps are buildable in this release.
#
# FROZEN_TRAP_ITEM_NAMES (11 names, #177, ruled 2026-08-10 16:28/16:30) and
# REWORK_TRAP_ITEM_NAMES (4 names, #280, ruled 2026-08-19) retain count 0 in
# data/items.json because trap fill creates them dynamically. They now all join
# TRAP_ITEM_NAMES in native enum order.
#
# They ARE all in the "Traps" item name group below, because item_name_groups is
# part of the datapackage payload AP checksums: adding a trap to its own group
# later would be a SECOND datapackage churn, which is exactly what #177 spends
# one bump to avoid. Group membership feeds !hint, item_links and
# start_inventory_from_pool expansion; nothing in fill reads it, so this changes
# no placement.
#
# Trap registry capacity: 19 effect types now, above native's current
# AP_TRAP_REGISTRY_CAP of 16. The native wave that lands these effects must
# raise that constant or the last traps silently have no slot.
from . import traps
from .traps import (ALL_TRAP_ITEM_NAMES, FROZEN_TRAP_ITEM_NAMES,
                    REWORK_TRAP_ITEM_NAMES, TRAP_ITEM_NAMES)

# SURFACE_ITEM_NAMES (the comfort-only #14/#15 pack) now lives in item_creation;
# re-exported because it was importable from the package before the move.
from . import item_creation
from .item_creation import SURFACE_ITEM_NAMES
from . import slot_data

# Issue #334: the room page's "Connect via Game Client" link. The component only
# translates the room link into a credential-free ctr-ap:// request for the
# native client; see launcher_component.py for what it may and may not do.
from . import launcher_component
launcher_component.register()


class ctrAPWeb(WebWorld):
    theme = "Party"
    # Groups the options page + YAML template by topic (was defined in Options.py
    # but never wired here, so the page rendered one flat list).
    option_groups = create_option_groups()

    tutorials = [
        Tutorial(
            "Multiworld Setup Guide",
            "A guide to setting up Crash Team Racing for Archipelago, including "
            "single-player, multiworld, and required tools.",
            "English",
            "setup_en.md",
            "setup/en",
            ["Taor", "Icebound777"]
        )
    ]


class ctrAPWorld(World):
    """
    Crash Team Racing (CTR) is a kart racing game developed by Naughty Dog and published by Sony
    Computer Entertainment for the PlayStation in 1999.
    It features characters from the Crash Bandicoot series and combines fast-paced racing with
    power-ups and weapons.
    """

    game = "Crash Team Racing"
    web = ctrAPWeb()
    topology_present = True
    options_dataclass = ctrAPOptions
    options: ctrAPOptions

    # Issue #179: host.yaml settings group (elastic-option friendly bounds +
    # future per-option vetoes). Explicit settings_key -- the AutoWorld default
    # would be "ctr_options" (folder name "ctr" + "_options"), which collides in
    # NAME (though not in namespace: one lives in host.yaml, the other on the
    # wire) with the slot_data Contract's top-level `ctr_options` dict. "ctr"
    # avoids inviting that confusion in a host's host.yaml.
    settings_key = "ctr"
    settings: ClassVar[CTRSettings]

    # Universal Tracker: interpret_slot_data is a staticmethod that always forces a
    # re-generation from the connected seed's slot_data, and that re-generation
    # reconstructs the whole logic graph from the wire (map + per-pad requirements +
    # the mirrored options). So UT can skip its throwaway first generation and track
    # a slot straight from slot_data with no player YAML (issue #29).
    ut_can_gen_without_yaml = True

    # Item + Location mapping
    _item_data_by_name = {item["name"]: item for item in
                          (*load_item_table(), *CUSTOM_LETTER_ITEM_DATA,
                           *CORTEX_VORTEX_LETTER_ITEM_DATA, *NAMED_TRACK_ITEM_DATA,
                           *MINTED_030_ITEM_DATA)}
    item_name_to_id = {
        name: item["code"] for name, item in _item_data_by_name.items()
    }
    # The Cortex Vortex letter items (35010200-202) sit directly after the
    # positional data/items.json table; an append to that table must move past
    # them rather than silently sharing a code.
    assert len(set(item_name_to_id.values())) == len(item_name_to_id), \
        "two CTR item names share one code"
    # Named custom-track letter items (#306) sit in their own range; nothing
    # else may use a name or code there.
    _validate_named_tracks(
        NAMED_TRACKS, None,
        {n: c for n, c in item_name_to_id.items()
         if n not in {row["name"] for row in NAMED_TRACK_ITEM_DATA}})
    location_name_to_id = get_location_names()
    location_name_groups = CTR_LOCATION_CLASSES.location_name_groups()

    # Item groups (issue #167). Group names live in the SAME namespace as item
    # names (AutoWorld.AutoWorldRegister builds all_item_and_group_names from the
    # union), so none of these four may collide with an entry in data/items.json --
    # test_item_groups asserts that plus verbatim membership. The server exposes
    # them for group hints (!hint Gems) and core expands them in item_links,
    # local_items / non_local_items, start_inventory_from_pool and plando_items
    # (Options.py 872/1534/1667, BaseClasses.py 274-280); nothing in fill reads
    # them, so placement is unchanged. AutoWorld adds "Everything" itself.
    item_name_groups = {
        "Relics": {"Sapphire Relic", "Gold Relic", "Platinum Relic"},
        "CTR Tokens": {"Red CTR Token", "Green CTR Token", "Blue CTR Token",
                       "Yellow CTR Token", "Purple CTR Token"},
        "Gems": {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"},
        # Sourced from the trap registry so the group cannot drift from the
        # native effect enum (the buildable set), the #177 freeze or the #280
        # rework. All 20 are in the group and buildable. The two 0.3.0 traps
        # (minted_items_030) join now, before their feature builds, because the
        # group is part of the checksummed datapackage.
        "Traps": set(ALL_TRAP_ITEM_NAMES) | set(MINTED_TRAP_ITEM_NAMES),
        "Itemsanity Weapons": set(ITEM_NAMES),
    }

    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)
        self.start_region = None
        # Issue #179: names _exclude_goal_location has excluded so far this
        # seed, appended at the call site rather than re-derived elsewhere --
        # elastic_bounds.goal_excluded_location_reserve reads this instead of
        # restating which goals exclude a location.
        self._goal_excluded_location_names: List[str] = []

    # --- Oxide-final goal helpers (issue #23) ---

    # Relic item name per its issue #171 exact-count option field (renamed from
    # _OXIDE_TIER_SLIDER when the three options converted from 0-100 percentage
    # sliders to 0-18 exact counts; kept as a label lookup for build/error
    # messages -- forced_options.py's oxide-final guard uses it that way).
    _OXIDE_TIER_SLIDER = {
        "Sapphire Relic": "sapphire_relic_count",
        "Gold Relic": "gold_relic_count",
        "Platinum Relic": "platinum_relic_count",
    }

    def _oxide_goal_tiers(self) -> List[str]:
        """Relic item names that can satisfy the configured Oxide-final mode.
        Single-tier modes name one tier; any_relic_type / total_relics draw on
        all three (independent items -- no downward hierarchy)."""
        mode = self.options.oxide_final_challenge_unlock.value
        F = FinalOxideUnlock
        if mode == F.option_gold_relics:
            return ["Gold Relic"]
        if mode == F.option_platinum_relics:
            return ["Platinum Relic"]
        if mode in (F.option_any_relic_type, F.option_total_relics):
            return ["Sapphire Relic", "Gold Relic", "Platinum Relic"]
        return ["Sapphire Relic"]  # sapphire_relics (default) + any unknown

    def _oxide_final_relic_rule(self):
        """A CollectionState predicate for the configured Oxide-final relic
        requirement (mode + count). Relic tiers are independent counted items,
        so this reads item counts directly: owning N relic items IS the
        requirement, and a duplicate landing elsewhere cannot false-complete a
        count -- so no companion-flag decoupling is needed for the relic half
        (the Key-4 reachability half keeps its flag event)."""
        return self._oxide_final_relic_term().compile()

    def _oxide_final_relic_term(self):
        """`_oxide_final_relic_rule` as a logic term (`logic_terms`), the form
        the Final Challenge's `win_logic` export is built from."""
        from .logic_terms import Has, ItemSum, Or
        p = self.player
        n = self.options.oxide_final_challenge_relic_count.value
        mode = self.options.oxide_final_challenge_unlock.value
        F = FinalOxideUnlock
        S, G, Pl = "Sapphire Relic", "Gold Relic", "Platinum Relic"
        if mode == F.option_gold_relics:
            return Has(G, n, p)
        if mode == F.option_platinum_relics:
            return Has(Pl, n, p)
        if mode == F.option_any_relic_type:
            return Or(Has(S, n, p), Has(G, n, p), Has(Pl, n, p))
        if mode == F.option_total_relics:
            return ItemSum((S, G, Pl), n, p)
        return Has(S, n, p)  # sapphire_relics (default)

    # --- Universal Tracker support (issue #29) ---

    @staticmethod
    def interpret_slot_data(slot_data: Dict[str, object]) -> Dict[str, object]:
        """Universal Tracker hook. Returning a truthy value tells UT to re-generate
        this world with the value placed in multiworld.re_gen_passthrough[game]. We
        return the slot_data verbatim: generate_early restores the seed's options
        from it and create_regions pins the rolled warp-pad map + per-pad unlock
        requirements + gem-cup leg map from it (Regions._ut_reconstruct_*,
        gem_cup_legs.reconstruct_gem_cup_legs_from_wire), so the re-generated
        world's logic graph is identical to the connected seed's instead of
        re-rolling a divergent one. Everything the reconstruction needs already
        travels on the wire (ctr_options, warp_pad_map, warp_pad_unlock,
        gem_cup_legs), so no extra emit is required in fill_slot_data."""
        return slot_data

    def _ut_restore_options(self, passthrough: Dict[str, object]) -> None:
        """Restore the logic-relevant options from the connected seed's slot_data so
        UT's re-generation reasons about the SAME world the seed was built from,
        regardless of the tracking player's own YAML.

        Only options that steer the reachability graph are restored. Schema 18
        carries include_battle_arenas explicitly. Older seeds use their pad
        requirements to recover it, and include_gem_cups always does. Logic-irrelevant
        mirrors (one_lap_cups, death_link, ...) are skipped."""
        o = self.options
        co = passthrough.get("ctr_options", {})
        from .cup_sweeps import restore_options as restore_sweep_options
        restore_sweep_options(o, passthrough)
        # #169 tier 1: pin the seed's boss venues from the wire, never redraw.
        boss_track_shuffle.restore_from_wire(self, passthrough)

        def _restore(opt_name: str, key: str) -> None:
            if key in co:
                getattr(o, opt_name).value = co[key]

        # Issue #152: restore the composed goal fields. Wire data from a
        # pre-#152 seed carries only the legacy `goal` int (no goal_oxide/
        # goal_bosses/goal_gems keys) -- translate it into the exactly
        # equivalent composed values so UT's re-generation reasons about the
        # same win condition an older seed actually has.
        if "goal_oxide" in co or "goal_bosses" in co or "goal_gems" in co:
            _restore("oxide_goal", "goal_oxide")
            _restore("bosses_required_goal", "goal_bosses")
            _restore("gems_required_goal", "goal_gems")
        elif "goal" in co:
            _legacy = co["goal"]
            _LEGACY_GOAL_MAP = {
                # legacy int -> (oxide_goal, bosses_required_goal, gems_required_goal)
                0: (OxideGoal.option_any_percent, 0, 0),
                1: (OxideGoal.option_101_percent, 0, 0),
                3: (OxideGoal.option_none, 4, 0),
                4: (OxideGoal.option_none, 0, 5),
            }
            if _legacy in _LEGACY_GOAL_MAP:
                _oxide, _bosses, _gems = _LEGACY_GOAL_MAP[_legacy]
                o.oxide_goal.value = _oxide
                o.bosses_required_goal.value = _bosses
                o.gems_required_goal.value = _gems
            # else: unrecognised legacy value -- leave the tracking player's
            # own YAML defaults in place, matching the pre-#152
            # _restore("goal", "goal") no-op-when-absent/unknown behaviour.
        _restore("warppad_unlock_requirements", "warppad_unlock_mode")
        _restore("bossgarage_unlock_requirements", "bossgarage_mode")
        _restore("shuffle_gems", "shuffle_gems")
        _restore("shuffle_keys", "shuffle_keys")
        _restore("oxide_final_challenge_unlock", "oxide_final_unlock")
        _restore("oxide_final_challenge_relic_count", "oxide_final_count")
        _restore("oxide_final_track", "oxide_final_track")
        # Missing on older rooms: preserve mandatory-first behavior even if
        # the tracking player's own YAML enables the new option.
        o.oxide_1_optional.value = (
            co.get("oxide_1_optional", 0)
            if type(co.get("schema_version", 0)) is int and
            co.get("schema_version", 0) >= 13 and
            type(co.get("oxide_1_optional", 0)) is int and
            co.get("oxide_1_optional", 0) in (1, 2) and
            o.oxide_goal.value == OxideGoal.option_101_percent else 0)
        # #145 made the boost chain a reachability input (the Itemsanity Turbo
        # checks require one received Progressive Boost when the chain is
        # randomized), so the seed's mode must override the tracking player's
        # own YAML or UT's Turbo logic diverges from server truth. The wire
        # value is the option value verbatim (0 off / 1 shared_global /
        # 2 per_character); absent on pre-#12 wires -> no-op.
        _restore("progressive_boost", "boost_mode")
        _restore("logic_difficulty", "logic_difficulty")
        # Blue Fire is a reachability input too, not only a pool size: the
        # #85 relic-tier floor raises EVERY Platinum Time Trial to rank 3 when
        # logic_difficulty is easy AND Blue Fire is on (usf_finish.
        # relic_tier_boost_min). Restoring the difficulty but not this toggle
        # left UT computing the rank-2 floor against a rank-3 server, which is
        # exactly the Platinum-only divergence the check-ut fuzz arm reported.
        # The wire value is the capability block's `boost_blue_fire` boolean
        # (progressive_capability.fill_slot_data). An absent key is a pre-#85
        # seed, which had no Blue Fire tier at all, so it restores to off
        # rather than letting the tracking player's YAML raise the floor.
        o.progressive_boost_blue_fire.value = int(
            bool(co.get("boost_blue_fire", 0)))
        # #109 box seeds: the toggle + knowledge tier decide which box slots
        # exist and the stat chains join the boost chain as reachability
        # inputs (hard-tier slots), so all three seed values must win over
        # the tracking player's YAML. All raw scalars, absent on older wires.
        _restore("progressive_stats", "stats_mode")
        if "box_locations" in co:
            o.box_locations.value = int(bool(co["box_locations"]))
        _restore("shortcut_knowledge", "shortcut_knowledge")
        _restore("slide_coliseum_races", "slide_coliseum_races")
        _restore("turbo_track_races", "turbo_track_races")
        # Cortex Vortex pad track: the option, the dropped destination and its
        # letter selection, pinned before anything below reads which
        # destinations this seed kept (lettersanity rows, relic tiers).
        cortex_vortex_track.restore_from_wire(o, passthrough)
        # Character phase (#54/#209). Two logic-relevant keys, both of which UT
        # gets wrong by default if it falls back to the tracking player's YAML:
        #   character_unlocks decides whether 15 unlock items exist AT ALL, so
        #     restoring it wrong rebuilds a different pool -- and on a reduced
        #     seed the re-generation does not even FIT, which is exactly how
        #     the fuzz matrix's check-ut arm caught this (6/500 seeds);
        #   racer_locked_pads carries the requested lock COUNT, which is what a
        #     support log reports back; the locks themselves are pinned from
        #     the racer_locks block rather than re-drawn, and the
        #     progression/useful split follows that pinned map.
        # starting_stat_class / penta_stats / editable_stats are cosmetic or
        # native-only and are deliberately NOT restored (same reasoning as
        # one_lap_cups). The starting racer itself is restored separately in
        # generate_early, because it is a per-seed draw, not an option value.
        if "character_unlocks" in co:
            o.character_unlocks.value = int(bool(co["character_unlocks"]))
        # Remove Playable Oxide (#426) decides whether Oxide's unlock item is
        # in the pool, so it is restored like character_unlocks: a tight seed
        # that fits 14 unlock items does not fit a re-generation that rebuilds
        # 15 (the check-ut arm found exactly that). Absent on an older wire
        # means off, whatever the tracking player's own YAML says.
        o.remove_playable_oxide.value = int(
            bool(co.get("remove_playable_oxide", False)))
        if "racer_locked_pads" in co:
            # An Alpha 6 seed put a Boolean here, a 0.2.0 seed puts the
            # requested maximum. `int(True)` is 1, which is the honest reading
            # of the old wire: it said "on", and the pad map says the rest.
            _requested = co["racer_locked_pads"]
            o.racer_locked_pads.value = max(
                0, min(int(_requested),
                       type(o.racer_locked_pads).range_end))
            # A restored count is already a number, so the Alpha 6 YAML
            # normalization must not also fire on top of it.
            o.racer_locked_pads.legacy_boolean_auto = False

        # Derive the two content-inclusion toggles from the pad gates: a cup /
        # crystal pad only carries a non-type-0 stage-1 requirement when its class
        # was included in this seed's randomization pool.
        _CUP_LIDS = {100, 101, 102, 103, 104}
        _CRYSTAL_LIDS = {18, 19, 21, 23}
        inc_cups = inc_arenas = False
        for lid_str, stages in passthrough.get("warp_pad_unlock", {}).items():
            if int(stages.get("stage1", {}).get("type", 0)) == 0:
                continue
            lid = int(lid_str)
            if lid in _CUP_LIDS:
                inc_cups = True
            elif lid in _CRYSTAL_LIDS:
                inc_arenas = True
        # The Cortex Vortex pad track only ever drops a Gem Cup or a crystal
        # arena whose content is in the seed (cortex_vortex_track.
        # _statically_eligible), which proves that toggle on even where no pad
        # gate says so (vanilla unlock mode). Without this the tracker would
        # pin vanilla rewards onto the dropped destination's absent location.
        _dropped = cortex_vortex_track.dropped_level_id(o)
        if _dropped is not None:
            _kind = cortex_vortex_track.destination_table()[_dropped][2]
            inc_cups = inc_cups or _kind == "cup"
            inc_arenas = inc_arenas or _kind == "crystal"
        o.include_gem_cups.value = int(inc_cups)
        o.crystalsanity.value = int(co.get("crystalsanity") is True)
        o.include_battle_arenas.value = int(bool(co["include_battle_arenas"])) \
            if type(co.get("schema_version")) is int and co["schema_version"] >= 18 \
            and "include_battle_arenas" in co \
            else int(inc_arenas)

        # Podium rung set is decided by five options that are NOT on the wire, but
        # the podium_checks block encodes exactly which rungs this seed created:
        # its "enabled" flag plus, per track, a 5-slot array in podium.SLOT_ORDER
        # ([held_1st, held_3rd, held_5th, finish_podium, finish_any], -1 = absent).
        # Recover the toggles from a sample track so create_regions / Rules /
        # _resolve_podium_checks rebuild the identical rung locations.
        pod = passthrough.get("podium_checks", {}) or {}
        from .podium import TRIAL_TRACKS
        o._trial_podium_wire = {}
        for ti, track in enumerate(TRIAL_TRACKS):
            row = (pod.get("locations", {}) or {}).get(str(16+ti))
            if (pod.get("enabled", False) and isinstance(row, (list, tuple)) and len(row) == 5
                    and all(type(code) is int and code in (-1, 35015200+ti*5+ri)
                            for ri, code in enumerate(row))):
                o._trial_podium_wire[track] = list(row)
        o.podium_placement_checks.value = int(bool(pod.get("enabled", False)))
        sample = next(iter((pod.get("locations", {}) or {}).values()), None)
        o.podium_held_rungs.value = int(bool(sample) and sample[0] != -1)
        o.podium_held_fifth_rung.value = int(bool(sample) and sample[2] != -1)
        o.podium_finish_rungs.value = int(bool(sample) and sample[3] != -1)
        o.podium_any_position_rung.value = int(bool(sample) and sample[4] != -1)

        # Issue #166: the emitter writes the top-level `gem_cup_legs` key only
        # when the option randomized the cups' legs, so key presence IS the
        # toggle's value. create_regions pins the actual map from the same
        # block (gem_cup_legs.reconstruct_gem_cup_legs_from_wire); an absent
        # key (any pre-#166 seed) correctly restores to off + vanilla legs.
        o.randomize_gem_cup_tracks.value = int("gem_cup_legs" in passthrough)
        # Custom tracks: the descriptor itself is pinned from the wire in
        # create_regions (custom_tracks.reconstruct_custom_tracks_from_wire),
        # which is what actually steers the graph. The option VALUE is
        # restored here too so the tracking player's own YAML can never
        # contribute a track the seed does not have, and so the restored
        # option set is honest rather than silently defaulted. Reconstructed
        # rather than copied verbatim: the wire is LevelID-keyed and the
        # option is word-keyed, and the reconstruction is the one place that
        # translation lives. An absent block is any pre-custom-tracks seed and
        # correctly restores to off.
        o.custom_tracks.value = {
            track_id: {
                "package_uuid": entry["package_uuid"],
                "package_version": entry["package_version"],
                "minimum_client_version": entry["minimum_client_version"],
                "minimum_apworld_version": entry["minimum_apworld_version"],
                "lev_sha256": entry["lev_sha256"],
                "vrm_sha256": entry["vrm_sha256"],
                "navigation": dict(entry["navigation"]),
                "laps": entry["laps"],
                "replaces": entry["replaces"],
                "host_level_id": entry["host_level_id"],
                "boxes": entry["boxes"],
                "flags": dict(entry["flags"]),
                **({"modes": dict(entry["modes"])} if "modes" in entry else {}),
            }
            for track_id, entry in
            reconstruct_custom_tracks_from_wire(passthrough).items()
        }
        # Itemsanity's block is conditional for off-toggle parity, while the
        # raw scalar in ctr_options is always emitted.  Prefer that scalar for
        # new seeds and retain block-presence fallback for the narrow interval
        # where a candidate wire may have carried the block but no scalar.
        if "itemsanity" in co:
            o.itemsanity.value = int(bool(co["itemsanity"]))
        else:
            o.itemsanity.value = int("itemsanity_checks" in passthrough)
        # Tizi Helper (#223): one always-emitted scalar, no conditional block to
        # fall back on. An absent key is any pre-#223 seed, which correctly
        # restores to off. The option creates one `useful` item and no location,
        # so this restore changes nothing a tracker computes -- it is here so the
        # restored option set is honest rather than silently defaulted.
        o.tizi_helper.value = int(bool(co.get("tizi_helper", 0)))
        # The wumpa family's two scalars, same convention: absent keys are a
        # pre-activation seed and restore to off / zero, which is honest --
        # such a seed created none of these items.
        wumpa_family.restore_slot_data(o, co)
        # The wumpa CHECK is a three-way mode (2026-08-29 spec) with an
        # always-emitted scalar. Prefer the scalar; fall back to block presence
        # for a pre-widening seed, where a present block always meant the single
        # global check -- which is exactly mode 1.
        if "wumpa_check" in co:
            o.wumpa_check.value = int(co["wumpa_check"])
        else:
            o.wumpa_check.value = int("wumpa_checks" in passthrough)
        # Turbo Grant (#224): identical scalar, identical reasoning. Absent key
        # is any pre-#224 seed and correctly restores to off.
        o.turbo_grant.value = int(bool(co.get("turbo_grant", 0)))
        lb = passthrough.get("lettersanity_checks", {}) or {}
        mode = co.get("lettersanity", lb.get("mode", 0))
        count = lb.get("letters_per_track", 3)
        selected = lettersanity.restore_letter_selection(o, lb, mode, count)
        o.lettersanity.value = mode
        o.letters_per_track.value = count
        if cortex_vortex_track.track_on(o):
            selected[cortex_vortex_track.CORTEX_VORTEX] = o._cortex_vortex_letters
        o._lettersanity_selected = selected
        # Hit Character encounters (0.2.1 candidate): pin the connected seed's
        # block verbatim (refusing a malformed/conflicting wire), then restore
        # the always-emitted scalar. The restore validates the raw boolean type
        # and never redraws the seed or the candidate arrays.
        hit_character.restore_from_wire(self, passthrough)
        o.hit_character.value = int(bool(co.get("hit_character", 0)))
        # Relic Race perfect checks (#49): the always-emitted scalar is the
        # option; an enabled seed's block must equal what these restored
        # options emit (Cortex Vortex's dropped destination was restored
        # above), otherwise the restore refuses. See relic_perfect.
        relic_perfect.restore_from_wire(o, passthrough)

    def generate_early(self) -> None:
        """Universal Tracker restore, then the option interaction / constraint
        matrix (issue #178): raise-guards that block an unsolvable seed, then
        downgrade-warnings that tell the player when an option they set has no
        effect this seed. See forced_options.py for the full convention and
        the per-constraint justification.

        Issue #171/#28 R1-R3: the per-tier relic Time Trial draw also runs
        here (`self._ctr_relic_keep` / `self._ctr_relic_created`), before
        anything downstream needs it -- the #178 raise-guards below check
        created counts (R5's derived gate-count constraint), then
        `create_regions` reads `_ctr_relic_keep` to decide which Time Trial
        locations to build (R1: a below-count slot is never created), then
        `create_items` reads `_ctr_relic_created` to size the relic item
        pool (R3)."""
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if passthrough and "content_plan" in passthrough:
            from . import content_plan
            content_plan.restore(self, passthrough)
            return
        if self.options.content_pool.value:
            from . import content_plan
            content_plan.generate(self)
            return
        if self.options.include_arcade_arenas.value and self.options.include_battle_arenas.value:
            raise OptionError("include_arcade_arenas requires an explicit content_pool with Crystal entries; no silent legacy migration.")
        if self.options.item_pool.value or self.options.pad_layout.value:
            raise OptionError("CTR item_pool and pad_layout require an explicit content_pool; no silent legacy migration.")
        # Cortex Vortex pad track (2026-09-13 contract): draw the destination
        # that goes without a pad FIRST, because the letter selection below and
        # the relic-tier draw both leave its checks out. A Universal Tracker
        # re-generation pins it from the wire in _ut_restore_options instead.
        # No draw with the option off, so such a seed keeps its RNG stream.
        _passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if not _passthrough:
            # 2026-09-21 ruling: a Gems Required Goal with include_gem_cups off
            # resolves shuffle_gems OFF (Gems stay on their vanilla cups)
            # instead of failing the whole multiworld. This MUST run before the
            # Cortex Vortex draw and the comfort-guard/relic draws below: all
            # three read shuffle_gems (directly or through
            # relic_tiers.resolve_comfort_guards), and an RNG draw taken
            # against the pre-resolution value would not match the seed the
            # rest of generation builds. The rest of the #178 matrix still runs
            # from forced_options.apply further down. See
            # forced_options.resolve_shuffle_gems_off_when_gem_goal_excludes_cups.
            from . import forced_options as _forced_options
            _forced_options.resolve_shuffle_gems_off_when_gem_goal_excludes_cups(self)
            # No one-way DeathLink (2026-09-30): sending implies receiving.
            _forced_options.resolve_death_link_off_when_send_conditions_set(self)
            # Boss track shuffle (#169 tier 1): freeze the four garage venues
            # before the Cortex Vortex draw, whose supply check counts Wumpa
            # locations a boss venue can keep. Draws nothing with the option
            # off, so such a seed keeps its RNG stream.
            boss_track_shuffle.draw(self)
            cortex_vortex_track.draw_dropped_destination(self)
        if not hasattr(self.options, "_lettersanity_selected"):
            mode = int(self.options.lettersanity.value)
            if mode in (1, 2):
                count = int(self.options.letters_per_track.value)
                self.options._lettersanity_selected = {
                    track: tuple(self.random.sample(lettersanity.LETTERS, count))
                    for track in lettersanity.eligible_letter_tracks(self.options)}
            else:
                self.options._lettersanity_selected = {
                    track: lettersanity.LETTERS for track in lettersanity.eligible_letter_tracks(self.options)}
            # Cortex Vortex's own letters, drawn after the retail selection so
            # the retail draws are unchanged by the option.
            if cortex_vortex_track.track_on(self.options):
                self.options._lettersanity_selected[cortex_vortex_track.CORTEX_VORTEX] = \
                    cortex_vortex_track.draw_letters(self)

        # Comfort guard flags (Icebound force_vanilla_turbotrack): needed by
        # the relic draw below, ahead of when Regions.create_regions would
        # otherwise compute them. See relic_tiers.resolve_comfort_guards.
        self._ctr_comfort_guards, self._ctr_force_vanilla_turbotrack = \
            resolve_comfort_guards(self.options)

        # Universal Tracker re-generation (issue #29): restore the seed's options
        # from slot_data so the rest of generation rebuilds the SAME world, then
        # skip the constraint matrix (the connected seed already passed it, and
        # the tracking player's own sliders/downgrades are irrelevant to the
        # pinned graph).
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if passthrough:
            self._ut_restore_options(passthrough)
            # The comfort guard flags above were computed from the tracking
            # player's own YAML. Recompute them from the restored options so
            # they match the connected seed: a seed whose shuffle_gems was
            # resolved OFF (Gem goal with Gem Cups excluded) has
            # force_vanilla_turbotrack set even when the tracker's YAML still
            # says shuffle_gems on.
            self._ctr_comfort_guards, self._ctr_force_vanilla_turbotrack = \
                resolve_comfort_guards(self.options)
            self._ctr_relic_keep, self._ctr_relic_created = \
                restore_relic_tier_keep_from_wire(
                    self, passthrough.get("ctr_options", {}) or {})
            # The starting racer is a per-seed DRAW, not an option value, so UT
            # must take the connected seed's answer rather than re-rolling one
            # (a re-roll would put a different 15 unlock items in the pool and
            # desync every racer-lock rule). Absent on a pre-character-phase
            # wire -> fall back to the normal resolution.
            self.ctr_starting_character = characters.restore_starting_character(
                self, passthrough.get("ctr_options", {}) or {})
            return
        self._ctr_relic_keep, self._ctr_relic_created = draw_relic_tier_keep(self)
        # Drawn BEFORE forced_options so a constraint entry can read it, and
        # before create_regions/create_items, both of which need to know which
        # racer is already owned. See characters.resolve_starting_character.
        self.ctr_starting_character = characters.resolve_starting_character(self)
        from . import forced_options
        forced_options.apply(self)
        # Manual warp pad rules (#463): validated once the seed's pads and
        # item supply are known. Takes no random draw.
        warp_pad_rules.resolve(self)
        rung_sizer.apply_rung_sizing(self)
        # Hit Character encounters (0.2.1 candidate): draw the single roster
        # seed and cache the resolved block. No-op (and no RNG draw) when the
        # option is off. This is the block's ONLY RNG draw; the per-guest Key
        # fallback is stamped into the same cached block later, in
        # hit_character.install_rules, because it can only be decided once
        # every location exists.
        hit_character.resolve_for_generation(self)

    def create_regions(self):
        if hasattr(self, "ctr_content_plan"):
            from . import content_plan
            content_plan.create_regions(self)
            return
        create_regions(self)
        from .custom_track_presentation import location_aliases
        self.location_id_to_alias = location_aliases(self)

    @classmethod
    def stage_modify_multidata(cls, multiworld, multidata):
        from .custom_track_datapackage import embed_track_names
        embed_track_names(multiworld, multidata, cls.game)

    def set_rules(self):
        if hasattr(self, "ctr_content_plan"):
            from . import content_plan
            content_plan.set_rules(self)
            return
        set_rules(self)

    def generate_basic(self) -> None:
        """Starting-check guard (sphere0_guard.py): refuse a slot that can
        reach fewer than MIN_STARTING_CHECKS checks from its starting
        inventory, because AP's fill cannot begin there or runs out of early
        spots for the item that opens the next check (rulings 2026-10-01 and
        2026-10-02). Universal Tracker skips it: the connected seed already
        generated. Inside that regeneration only, aliased custom locations take
        their room title as their name (#306 B+), so the Tracker Page shows
        `Baby T Park: Trophy Race` instead of the generic name with the title
        in brackets. generate_basic is the last step UT runs, after rules.
        A content plan with second-stage gates and a narrow start then marks
        one local early opener (sphere0_guard.mark_early_opener, ruling
        2026-10-17), and a content plan with Progressive Boost and a narrow
        start marks the starting racer's first boost early
        (sphere0_guard.mark_early_boost, ruling 2026-10-18), and with racer
        locks as well the next widest opener too (second ruling 2026-10-18)."""
        if getattr(self.multiworld, "generation_is_fake", False):
            from .custom_track_presentation import apply_ut_room_names
            apply_ut_room_names(self)
            return
        from . import sphere0_guard
        sphere0_guard.raise_if_narrow(self)
        if hasattr(self, "ctr_content_plan"):
            sphere0_guard.mark_early_opener(self)
            sphere0_guard.mark_early_boost(self)
            # Plando on content plans (#133 PR 4f): Main.py has parsed the
            # blocks; check them before plando runs.
            from . import content_item_pool
            content_item_pool.check_planned_blocks(self)

    def pre_fill(self) -> None:
        """Terminal fill backstop for solo generations, in both warp-pad modes.

        Two-stage gating is kept as rolled: there is no fill prediction and no
        stage-2 collapse here. The room fillability probe that used to dry-run
        the whole room on a mirror multiworld was removed in favour of measured
        fill success (0.2.3: no collapse verdict in 6,300+ probed seeds).

        Solo only: the rollback-precollect backstop replays the real fill and,
        if it dead-ends, precollects the stranded progression so the seed
        cannot ship an unfillable red. See _rollback_precollect_backstop."""
        # Universal Tracker (issue #29): under a fake generation there is no real
        # fill to protect. Reachability is fixed by the rules reconstructed from
        # slot_data, and the server supplies the real item placements.
        if getattr(self.multiworld, "generation_is_fake", False):
            return
        if hasattr(self, "ctr_content_plan"):
            # Item links and plando have run (#133 PR 4f): audit the created
            # copies and pay for explicit plando items with this world's filler.
            from . import content_item_pool
            self.ctr_framework_accounting = content_item_pool.settle_after_plando(self)
            # Independent supply never uses automatic progression starts. Manual
            # pad rules still get the solo fill check, so a dead end names them.
            if warp_pad_rules.fixed(self) and len(self.multiworld.worlds) == 1:
                self._manual_rules_fill_check()
            return
        # Solo only (replay fidelity: nothing consumes multiworld.random between
        # here and the fill). Vanilla and randomized both route through the same
        # mode-agnostic machinery; a non-fired seed is byte-identical to an
        # un-backstopped build, a fired seed is logged to the spoiler.
        if len(self.multiworld.worlds) == 1:
            mode = ("vanilla" if self.options.warppad_unlock_requirements.value == 0
                    else "randomized")
            if warp_pad_rules.fixed(self):
                # Manual warp pad rules (#463): the backstop would rescue a
                # dead end by handing the player the stranded items, which
                # weakens a rule the player wrote. Check the fill instead and
                # report the failure with the rules.
                self._manual_rules_fill_check()
            else:
                self._rollback_precollect_backstop(mode)

    def post_fill(self) -> None:
        """Content plans (#133 PR 4f): refuse a fill that dropped a created
        copy or moved one to the start inventory."""
        if hasattr(self, "ctr_content_plan") and not getattr(self.multiworld, "generation_is_fake", False):
            from . import content_item_pool
            content_item_pool.audit_before_output(self)

    _ROLLBACK_BACKSTOP_MAX_ROUNDS = 40

    def _manual_rules_fill_check(self) -> None:
        """Solo seeds with manual warp pad rules: replay the upcoming fill and,
        if it dead-ends, refuse with the fixed rules and the fill's own cause.
        Grants no item, relaxes no rule. A green replay changes nothing."""
        try:
            from settings import get_settings
            panic = get_settings().generator.panic_method
        except Exception:
            panic = "swap"
        self._ctr_fill_failure = ""
        if self._rollback_simulate_fill(panic) is True:
            return
        rules = ", ".join(
            f"{pad}: {warp_pad_rules.describe(rule)}"
            for pad, rule in sorted(warp_pad_rules.fixed(self).items()))
        raise OptionError(
            f"CTR warp_pad_rules: the item fill cannot place everything with "
            f"your manual rules ({rules}). Cause: "
            f"{self._ctr_fill_failure or 'not every location can be reached'} "
            f"Loosen a rule, change its count, or move it to a pad that opens "
            f"later.")

    def _vanilla_fill_backstop(self) -> None:
        """Vanilla-mode entry to the shared terminal backstop. Kept as a named
        method because the vanilla-fill story (levers 1+2 -- honest relic
        classification + vanilla early-Keys, the latter removed 2026-10-02 --
        shrink the tight-fill FillError class to a ~0.1-0.2% residual that
        this removes exactly) is documented
        against this name across the design notes. See
        _rollback_precollect_backstop for the mechanism."""
        self._rollback_precollect_backstop("vanilla")

    def _rollback_precollect_backstop(self, mode: str) -> None:
        """Mode-agnostic terminal fill backstop: REPLAY the upcoming fill and, if
        it dead-ends, precollect the stranded progression so the real fill goes
        green. Called for solo generations in BOTH warp-pad modes (the machinery
        is mode-agnostic; only the vanilla-specific docstring/entry assumptions
        were lifted). It removes the residual exactly rather than approximating it:

        1. SIMULATE the real fill by RUNNING it on this very multiworld and then
           rolling every mutation back (placements, locked flags, itempool,
           precollected items, state, and multiworld.random's RNG state). Because
           it is the actual distribute_items_restrictive on the actual object
           graph with the actual RNG state and the actual host panic_method, the
           simulation makes the exact decisions the real fill is about to make:
           in a solo generation nothing consumes multiworld.random between our
           pre_fill and the fill (Main.py runs them back to back), so after
           rollback the real fill replays the simulation move for move.
        2. If the simulation fills: return. The real fill provably fills; the
           seed is byte-identical to a build without this backstop.
        3. If the simulation dead-ends: enumerate the stranded progression items
           (a rollback-simulation with panic_method='start_inventory' -- AP's own
           mechanism for naming unplaceable items), precollect them from the real
           itempool into starting inventory, top up with filler to keep
           item count == location count, and re-simulate. Loop until the simulated
           fill goes green (bounded: every round strictly removes progression from
           the ordered pool). The real fill then replays the green simulation.

        REPLAY FIDELITY (why solo is enough for both modes): pre_fill routes
        straight here in both modes and nothing else in CTR's pre_fill consumes
        self.multiworld.random. create_filler returns a fixed Wumpa Fruit, so
        the precollect top-up draws no RNG either. So the RNG state the
        simulation snapshots is exactly the state the real fill will run from
        (harness-asserted over 100 seeds).

        SOLO ONLY (enforced by the caller): with other worlds present, their
        pre_fill hooks may run after ours and consume multiworld.random, breaking
        replay fidelity -- and mixed pools relax CTR's tightness anyway. This is
        why the multiworld FillError residual is NOT covered by this backstop.

        Fail-open: any unexpected error leaves generation to proceed as if the
        backstop did not exist. CTR_PROBE_LOG_ONLY=1 logs the would-fire verdict
        without intervening (acceptance-sweep instrumentation).

        No gate, rule, slot_data, or schema change: the only effect on a fired
        seed is items moved to starting inventory (the player begins with them
        collected), which never removes reachability. A fired seed is recorded on
        self for write_spoiler so rescued seeds are diagnosable; a non-fired seed
        records nothing (byte-neutral)."""
        try:
            from settings import get_settings
            panic = get_settings().generator.panic_method
        except Exception:
            panic = "swap"
        mw = self.multiworld
        log_only = bool(os.environ.get("CTR_PROBE_LOG_ONLY"))
        fired: List[str] = []
        try:
            converged = False
            for _round in range(self._ROLLBACK_BACKSTOP_MAX_ROUNDS):
                if self._rollback_simulate_fill(panic) is True:
                    converged = True
                    break
                if log_only:
                    logging.info("[CTR] %s fill backstop LOG-ONLY: simulated "
                                 "fill dead-ends; would intervene.", mode)
                    self._ctr_backstop_would_fire = True
                    return
                stranded = self._rollback_enumerate_stranded()
                if not stranded:
                    logging.warning(
                        "[CTR] %s fill backstop: simulated fill dead-ends but "
                        "no stranded items identified; leaving the seed unchanged "
                        "(fail-open).", mode)
                    return
                for name in stranded:
                    for i, item in enumerate(mw.itempool):
                        if item.player == self.player and item.name == name:
                            if self._completes_goal_at_start(item):
                                # Fuzz 32541: a stranded Gem on a one-Gem goal
                                # would start the slot with its goal complete.
                                logging.warning(
                                    "[CTR] %s fill backstop: stranded item %r "
                                    "would complete the goal from starting "
                                    "inventory; not precollecting it "
                                    "(fail-open).", mode, name)
                                return
                            del mw.itempool[i]
                            mw.push_precollected(item)
                            mw.itempool.append(self.create_filler())
                            fired.append(name)
                            break
                    else:
                        logging.warning(
                            "[CTR] %s fill backstop: stranded item %r not in "
                            "the real itempool; stopping intervention (fail-open).",
                            mode, name)
                        return
            if converged and fired:
                self._ctr_backstop_fired = True
                self._ctr_backstop_mode = mode
                self._ctr_backstop_items = list(fired)
                logging.info(
                    "[CTR] %s tight-fill backstop fired: precollected %d "
                    "item(s) (%s); simulated fill green -- seed fully beatable "
                    "from starting inventory.", mode, len(fired), ", ".join(fired))
            elif not converged:
                logging.warning(
                    "[CTR] %s fill backstop: no convergence after %d rounds "
                    "(precollected so far: %s); generation proceeds.",
                    mode, self._ROLLBACK_BACKSTOP_MAX_ROUNDS,
                    ", ".join(fired) or "none")
        except Exception as exc:
            logging.warning(
                "[CTR] %s fill backstop errored (%s: %s); proceeding without "
                "it (fail-open)%s.", mode, type(exc).__name__, exc,
                " after precollecting: " + ", ".join(fired) if fired else "")

    # -- rollback simulation machinery (vanilla fill backstop) --
    #
    # distribute_items_restrictive mutates exactly: location placements
    # (location.item / item.location / location.locked, incl. lock_later),
    # multiworld.random (shuffles), and -- only under panic_method=
    # 'start_inventory' -- precollected_items + state (push_precollected).
    # It never reassigns multiworld.itempool or early_items (it works on
    # sorted local copies), but both are snapshotted anyway as cheap insurance.

    def _fill_snapshot(self) -> dict:
        mw = self.multiworld
        return {
            "rng": mw.random.getstate(),
            "state": mw.state.copy(),
            "early": {p: dict(d) for p, d in mw.early_items.items()},
            "local_early": {p: dict(d) for p, d in mw.local_early_items.items()},
            "precollected_len": {p: len(v) for p, v in mw.precollected_items.items()},
            "placements": [(loc, loc.item, loc.locked) for loc in mw.get_locations()],
            "itempool": list(mw.itempool),
        }

    def _fill_rollback(self, snap: dict) -> None:
        mw = self.multiworld
        for loc, item, locked in snap["placements"]:
            if loc.item is not None and loc.item is not item:
                loc.item.location = None
            loc.item = item
            loc.locked = locked
            if item is not None:
                item.location = loc
        mw.itempool[:] = snap["itempool"]
        for p, ln in snap["precollected_len"].items():
            del mw.precollected_items[p][ln:]
        mw.early_items.clear()
        for p, d in snap["early"].items():
            mw.early_items[p] = dict(d)
        mw.local_early_items.clear()
        for p, d in snap["local_early"].items():
            mw.local_early_items[p] = dict(d)
        mw.state = snap["state"]
        mw.random.setstate(snap["rng"])

    def _rollback_simulate_fill(self, panic: str) -> bool:
        """Run the REAL upcoming fill on the REAL multiworld, then roll every
        mutation back. True = the fill goes green (and, since the RNG state is
        restored, the real fill will replay it identically)."""
        from Fill import distribute_items_restrictive as _dist, FillError as _FE
        snap = self._fill_snapshot()
        prev_disable = logging.root.manager.disable
        logging.disable(logging.ERROR)  # sim log noise would read as real-fill output
        try:
            try:
                _dist(self.multiworld, panic)
                # Main.py's output step also runs the accessibility check;
                # green means both pass (fuzz 32541 filled but failed it).
                return bool(self.multiworld.fulfills_accessibility())
            except _FE as exc:
                self._ctr_fill_failure = " ".join(str(exc).split())[:600]
                return False
        finally:
            self._fill_rollback(snap)
            logging.disable(prev_disable)

    def _completes_goal_at_start(self, item) -> bool:
        """True when precollecting ``item`` would leave this slot's goal
        complete from starting inventory."""
        from BaseClasses import CollectionState
        state = CollectionState(self.multiworld)
        state.collect(item, True)
        return bool(self.multiworld.has_beaten_game(state, self.player))

    def _rollback_enumerate_stranded(self) -> List[str]:
        """Names of this player's items the upcoming fill cannot place, via a
        rollback simulation under panic_method='start_inventory' (AP's own
        mechanism for naming unplaceable items instead of raising)."""
        from Fill import distribute_items_restrictive as _dist
        mw = self.multiworld
        snap = self._fill_snapshot()
        prev_disable = logging.root.manager.disable
        logging.disable(logging.ERROR)
        try:
            _dist(mw, panic_method="start_inventory")
            before = snap["precollected_len"][self.player]
            return [it.name for it in mw.precollected_items[self.player][before:]
                    if it.player == self.player]
        finally:
            self._fill_rollback(snap)
            logging.disable(prev_disable)

    # --- Item creation ---

    def create_item(self, name: str) -> "ctrAPItem":
        return item_creation.create_item(self, name)

    def _relic_progression_map(self) -> Dict[str, bool]:
        """Which relic tiers are genuine PROGRESSION in this seed (True) vs merely
        USEFUL (False). See item_creation.relic_progression_map for the full
        (warp-pad mode, goal, accessibility) matrix."""
        return item_creation.relic_progression_map(self)

    def create_event(self, event: str):
        return ctrAPItem(
            name=event,
            classification=ItemClassification.progression_skip_balancing,
            code=None,
            player=self.player,
        )

    def place_items_from_dict(self, option_dict: Dict[str, str]):
        for loc, item in option_dict.items():
            self.get_location(
                location_name=loc
            ).place_locked_item(
                item=self.create_item(item)
            )

    def create_filler(self) -> Item:
        # Standard AP World signature: the core itself calls create_filler() with
        # no arguments on the panic_method='start_inventory' paths (Fill.py), which
        # the vanilla fill backstop's enumeration simulation exercises.
        return self.create_item("Wumpa Fruit")

    def _add_goal_event(self, region_name: str, event_name: str, logic_text: str) -> str:
        """Create a code-null companion EVENT location and lock a distinct flag item
        on it, gated by the SAME win-trigger (logic_text) as its paired real reward
        location. Per Spec §5's standing rule (option b): a goal meaning "the player
        personally did X" must key completion off a singleton or a companion flag,
        NEVER a state.has() against whatever arbitrary shuffled item happens to land on
        the real reward location -- a duplicate of that item arriving from elsewhere in
        the multiworld would false-complete the goal. The flag item is named after the
        event and is read ONLY by completion_condition (code null -> native never sends
        it as a check). logic_text is stored on the location so Rules.set_rules -- which
        runs AFTER create_items and rebuilds every location's access_rule from its
        logic_text -- gates the event exactly like a JSON location. Returns the flag
        item name."""
        from BaseClasses import Location
        mw = self.multiworld
        region = mw.get_region(region_name, self.player)
        loc = Location(self.player, event_name, None, region)
        loc.logic_text = logic_text
        loc.place_locked_item(self.create_event(event_name))
        region.locations.append(loc)
        mw.regions.location_cache[self.player][event_name] = loc
        return event_name

    def _exclude_goal_location(self, player: int, location_name: str) -> None:
        """Issue #27: mark this seed's goal location EXCLUDED so fill places only
        filler there. The real (coded) location stays present -- the native client
        sends the check in the same moment as the goal, so it is claimed by play
        rather than by release -- but LocationProgressType.EXCLUDED bars fill from
        seating any progression item on it, which keeps another world's progression
        off the finish line and stops the player's own progression from being wasted
        on a location only reachable once the seed is already won. Runs from
        _install_goal (create_items), after create_regions has built the JSON
        location, so get_location resolves it. Generation-side only: no datapackage,
        slot_data, or client change -- the location still exists and is still sent."""
        from BaseClasses import LocationProgressType
        loc = self.multiworld.get_location(location_name, player)
        loc.progress_type = LocationProgressType.EXCLUDED
        # Issue #179: record it for elastic_bounds.goal_excluded_location_reserve.
        self._goal_excluded_location_names.append(location_name)

    def _legacy_goal_value(self) -> int:
        """Best-effort legacy `ctr_options.goal` int for a composed goal
        (issue #152), for spoiler-log / ap-state debug readability ONLY --
        see the fill_slot_data comment at its call site for why a
        schema>=7-aware native never reads this for evaluation. -1 when the
        composed goal has no single-condition legacy analogue."""
        o = self.options
        oxide = o.oxide_goal.value
        bosses = o.bosses_required_goal.value
        gems = o.gems_required_goal.value
        if oxide == OxideGoal.option_any_percent and bosses == 0 and gems == 0:
            return 0  # legacy option_oxide
        if oxide == OxideGoal.option_101_percent and bosses == 0 and gems == 0:
            return 1  # legacy option_oxidefinal
        if oxide == OxideGoal.option_none and bosses == 4 and gems == 0:
            return 3  # legacy option_allbosses
        if oxide == OxideGoal.option_none and bosses == 0 and gems == 5:
            return 4  # legacy option_allgemcups
        return -1

    def _install_goal(self, player: int) -> None:
        """Set this seed's composed completion condition and lay any companion
        goal-tracking events (Spec §5, revised 2026-07-01; composed 2026-08-10,
        issue #152).

        The goal is the AND of every ACTIVE condition among Oxide Goal
        (none/first/final), Bosses Required Goal (0-4) and Gems Required Goal
        (0-5) -- generate_early's raise_if_composed_goal_is_empty guard has
        already rejected the all-off combination, so `predicates` below is
        never empty by the time completion_condition is installed.

        Oxide first/final are real, coded, pool-filled locations
        (data/locations.json codes 35011104 / 35011105); each is PAIRED with
        a code-null companion event locking a distinct flag the predicate
        reads (Spec §5's standing rule: a goal meaning "the player personally
        did X" must key off a singleton or a companion flag, never a
        state.has() against an arbitrary shuffled item -- a duplicate landing
        elsewhere in the multiworld must not false-complete it). Bosses
        Required Goal checks N of the 4 real Boss Race locations the same
        way, replacing the wrong state.has(Trophy, 16) proxy -- trophies only
        UNLOCK the garages, they do not mean the bosses were beaten. Gems
        Required Goal counts held Gems directly via gemgoal(): singleton
        items, safe by construction (a duplicate cannot false-positive a
        count), so it needs no companion event."""
        mw = self.multiworld
        o = self.options
        predicates: List = []

        # Reused by Rules.add_oxide_access_contract (WO-A1 companion): the
        # SAME "bosses won" / "gems held" predicates goal completion uses,
        # so the Oxide garage door and the goal can never read a different
        # answer to the same question. None when that companion condition is
        # inactive (its value is 0), exactly like the goal's own predicates
        # list above.
        self._ctr_boss_won_predicate = None
        self._ctr_gems_predicate = None
        # The same two arms as logic terms (logic_terms); the predicates
        # above are their compiled forms.
        self._ctr_boss_won_term = None
        self._ctr_gems_term = None

        # Both Oxide goal events inherit Oxide Station's confirmed finish
        # capability (triage ruling 2026-08-19): the challenge is raced on
        # Oxide Station, so the composed goal must not become true from Key 4
        # alone while the ordinary Trophy Race logic still demands the finish
        # term. track_finish_term carries the whole ruling -- two Progressive
        # Boosts at easy/medium, vacuous at hard shortcut knowledge, vacuous
        # when the chain is not randomized, racer-aware in per-character mode.
        # The Final Challenge takes its venue's record instead: Cortex Vortex
        # needs USF with no hard-shortcut escape.
        from .usf_finish import oxide_final_track_name, track_finish_term
        oxide_finish = track_finish_term("Oxide Station", self)
        # The Cortex Vortex venue is raced from the garage, never from the pad
        # carrying the Cortex Vortex pad track, so no pad racer lock applies.
        final_track = oxide_final_track_name(self)
        final_finish = track_finish_term(
            final_track, self, bind_racer=final_track != "Cortex Vortex")

        if o.oxide_goal.value == OxideGoal.option_any_percent:
            flag = self._add_goal_event(
                "N. Oxide Garage", "N. Oxide's Challenge Cleared", "has('Key', 4)")
            predicates.append(
                lambda state, f=flag, ft=oxide_finish:
                    state.has(f, player) and ft(state, player))
            # Issue #27: keep the real goal location as a check (the client sends it
            # in the same moment as the goal, so it is claimed by play), but mark it
            # EXCLUDED so fill only places filler there. No world's progression can
            # sit on the finish line, and the player's own progression can't be
            # stranded on a location that is only reachable once the seed is won.
            self._exclude_goal_location(player, "N. Oxide Garage: N. Oxide's Challenge")
        elif o.oxide_goal.value == OxideGoal.option_101_percent:
            # The companion event is the seed's terminal win-flag; its win-trigger
            # is reaching Oxide's garage (Key 4). The relic requirement that turns
            # Oxide's Challenge into the FINAL Challenge (issue #23) is ANDed into
            # this predicate from the configured oxide_final_challenge_unlock
            # mode + count -- so fill, the spoiler playthrough, and beatability
            # chase the real goal instead of the old hard-coded 18 Sapphire. The
            # satisfying tiers are made progression by _relic_progression_map,
            # and generate_early has already errored out on any mode/count
            # combo that could not reach the goal.
            flag = self._add_goal_event(
                "N. Oxide Garage", "N. Oxide's Final Challenge Cleared",
                "has('Key', 4)")
            relic_rule = self._oxide_final_relic_rule()
            predicates.append(
                lambda state, f=flag, r=relic_rule, ft=final_finish:
                    state.has(f, player) and r(state) and ft(state, player))
            # Issue #27: exclude the real Final Challenge location only -- when
            # Oxide Goal is 'final' the FIRST Challenge is not this seed's goal
            # location and stays a normal, fillable check (issue #152 C8).
            self._exclude_goal_location(
                player, "N. Oxide Garage: N. Oxide's Final Challenge")
            if o.oxide_1_optional.value == 2:
                # Lock the existing generic filler, not an EXCLUDED hint:
                # fast filler placement/plando must not replace it with a trap,
                # useful item or another world's progression.
                mw.get_location("N. Oxide Garage: N. Oxide's Challenge", player).place_locked_item(
                    self.create_item("Wumpa Fruit"))
        # option_none and option_disabled (issue #320): Oxide is not a
        # completion condition, so no predicate and no event. Under
        # `none` both races stay in the seed as ordinary optional
        # checks; under `disabled` create_regions never created them.
        # Either way the seed finishes on its remaining Boss/Gem arms
        # and native rolls the credits from the hub (#244).

        if o.bosses_required_goal.value > 0:
            # Pair each real Boss Race location with a companion event of the same
            # reachability. The Boss Race location's own rule is "True"; the garage
            # door's trophy gate (add_boss_garage_rules 4/8/12/16) is what actually
            # gates reaching it, so a "True" event in the same region inherits that gate.
            # These per-boss "personally won" flags are also the machinery BUG-D's
            # future modes-0/1 reconciliation needs (see Options.BossGarageRequirements).
            # Issue #152: the legacy All Bosses goal's all() becomes a tally
            # compared against the configured count -- "any N", per the
            # dossier's C11 ruling that N-of semantics must read identically
            # on both sides of the contract (native mirrors this in
            # AP_EvaluateGoal).
            boss_events = [
                ("Ripper Roo Garage", "Ripper Roo Boss Race Won"),
                ("Papu Papu Garage", "Papu Papu Boss Race Won"),
                ("Komodo Joe Garage", "Komodo Joe Boss Race Won"),
                ("Pinstripe Garage", "Pinstripe Boss Race Won"),
            ]
            flags = [self._add_goal_event(r, e, "True") for r, e in boss_events]
            n_bosses = o.bosses_required_goal.value
            from .logic_terms import BossWins
            self._ctr_boss_won_term = BossWins(flags, n_bosses, player)
            boss_predicate = self._ctr_boss_won_term.compile()
            predicates.append(boss_predicate)
            self._ctr_boss_won_predicate = boss_predicate

        if o.gems_required_goal.value > 0:
            self._ctr_gems_predicate = self.gemgoal(
                player, o.gems_required_goal.value, predicates)

        # generate_early's raise_if_composed_goal_is_empty already rejects the
        # all-off combination, so this can never be empty here; the assert is
        # a load-bearing guard against the guard drifting out of lockstep with
        # this method, not a normal-path check.
        assert predicates, (
            "CTR: _install_goal found no active goal condition -- "
            "raise_if_composed_goal_is_empty should already have rejected "
            "this seed.")
        mw.completion_condition[player] = (
            lambda state, ps=tuple(predicates): all(p(state) for p in ps))

    def create_items(self):
        item_creation.create_items(self)

    def gemgoal(self, player, n: int, predicates: List):
        """Gems Required Goal (issue #152, generalized from the legacy
        All-Gems goal): appends a "hold >= n of the 5 Gems" predicate to
        `predicates` (composed with any Oxide/Bosses predicates by
        _install_goal, which owns setting completion_condition) AND returns
        that same predicate so a caller that needs the identical answer
        elsewhere (the Oxide access contract, Rules.add_oxide_access_contract)
        can reuse it rather than re-deriving it (issue #WO-A1-companion: the
        garage door must read the same truth as goal completion). With
        Shuffle Gems OFF the gems are additionally locked onto their own Gem
        Cup locations (win enough cups); with Shuffle Gems ON they stay in
        the multiworld pool and the goal is a hunt for wherever the fill hid
        them (create_items keeps them in the pool for this goal, and
        native's goal_gems field already counts RECEIVED gems, so both
        placements complete identically). n == 5 is byte-equivalent to the
        legacy All-Gems goal's own all()."""
        # Read via pkgutil so it works when the world is loaded from a zipped
        # .apworld (open()/os.path on __file__ raises NotADirectoryError inside a
        # zip -- the gem-cup goal crashed on every distributed seed). pkgutil is
        # the mandatory pattern for all packaged data reads in this world.
        mw = self.multiworld
        if not self.options.shuffle_gems.value:
            _mapping = json.loads(
                pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
            )
            for loc_name, gem_name in _mapping["ShuffleOptions"]["Gems"].items():
                loc_name = replacement_trophy_location(
                    resolved_custom_tracks(self), loc_name)
                loc = mw.get_location(loc_name, player)
                loc.place_locked_item(self.create_item(gem_name))

        gems = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        from .logic_terms import Distinct
        self._ctr_gems_term = Distinct(gems, n, player)
        predicate = self._ctr_gems_term.compile()
        predicates.append(predicate)
        return predicate

    # --- Native-randomization slot_data (Phase-2 MVP shared contract) ---

    # Native warp_pad_map / warp_pad_unlock: the dense array covers pad LevelID
    # 0..27 (race/crystal/trial tracks). Gem cups (LevelID 100-104) sit OUTSIDE
    # that array and are emitted as EXTRA string keys ("100".."104"). Under
    # slot_data v3 gem cups are destination-shuffle-eligible: warp_pad_map carries
    # their identity (and any remap) so a v3 native enforces cup destinations, and
    # warp_pad_unlock emits a cup key whenever include_gem_cups randomizes its
    # requirement (see _resolve_warp_pad_unlock). A v2 native simply ignores the
    # out-of-range cup keys (contract §3 compat) -> cups stay identity there.
    WARP_PAD_ID_RANGE = 28

    def _resolve_warp_pad_map(self) -> Dict[str, int]:
        """{"<physicalPadLevelID>": <targetTrackID>}, always present. See slot_data."""
        return slot_data.resolve_warp_pad_map(self)

    def _resolve_gem_cup_legs(self) -> Dict[str, List[int]]:
        """The gem_cup_legs wire block (issue #166, schema 7). See slot_data."""
        return slot_data.resolve_gem_cup_legs(self)

    def _resolve_warp_pad_unlock(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """The two-stage warp_pad_unlock wire block, always present. See slot_data."""
        return slot_data.resolve_warp_pad_unlock(self)

    def _resolve_podium_checks(self) -> Dict[str, object]:
        """The podium position-rung wire block (schema 6). See slot_data."""
        return slot_data.resolve_podium_checks(self)

    def _resolve_itemsanity_checks(self) -> Dict[str, object]:
        """Ordered 22-code fan-out for the native use-time hook (#145). See slot_data."""
        return slot_data.resolve_itemsanity_checks(self)

    def fill_slot_data(self) -> Dict[str, object]:
        return slot_data.fill_slot_data(self)

    def extend_hint_information(self, hint_data: Dict[int, Dict[int, str]]) -> None:
        """Issue #52: annotate each location with the PHYSICAL warp pad that loads
        its track, so under destination shuffle a hint reads "... at the Sewer
        Speedway pad". This is the INVERSE of Regions.pad_dest_region
        (Regions.py:523-527): for a location whose region is a shuffled DESTINATION,
        name the physical pad whose exit now loads that region.

        Per-seed multidata channel only (AutoWorld.extend_hint_information ->
        Main.er_hint_data -> the server's Hint.entrance text, rendered "at <text>").
        It touches no ids, names, the datapackage, fill, or reachability, so there is
        NO schema_version / world_version bump. AP calls it at output, after
        create_regions has run, so warp_pad_map / warp_pad_ids / every region and
        location are already resolved.

        Identity / vanilla seeds have an empty warp_pad_map, so this emits no hint
        text (a location's own name already carries its track) -- the correct no-op.
        """
        warp_pad_map = getattr(self, "warp_pad_map", None)
        if not warp_pad_map:
            return
        pad_ids = getattr(self, "warp_pad_ids", {})

        # Rebuild lid_to_region EXACTLY as Regions.py:517-522 (from world.json's own
        # pad-exit targets), NOT by stripping " Warp Pad": a cup pad name strips to
        # "Red Cup" but its region is "Red Gem Cup" (pad key != region name).
        data = json.loads(
            pkgutil.get_data(__package__, "data/world.json").decode("utf-8"))
        lid_to_region: Dict[int, str] = {}
        for reg in data["regions"]:
            for ex in reg.get("exits", []):
                meta = pad_ids.get(ex["name"])
                if meta is not None and ex.get("target") is not None:
                    lid_to_region[meta["level_id"]] = ex["target"]
        # The Cortex Vortex pad track's region, reached through whichever pad
        # loads destination 110 (unused with the option off).
        lid_to_region[cortex_vortex_track.DESTINATION_ID] = \
            cortex_vortex_track.CORTEX_VORTEX

        # Inverse of pad_dest_region, filtered to genuinely-shuffled pads. A pad that
        # loads its own vanilla destination (a fixed point within a pool) is not worth
        # a hint; warp_pad_map already holds non-identity remaps only, but skip
        # explicitly to match the research spec. Label = the pad-exit name minus
        # " Warp Pad" ("Sewer Speedway"), the vanilla hub spot the player recognizes.
        region_to_label: Dict[str, str] = {}
        for pad_name, dest_lid in warp_pad_map.items():
            meta = pad_ids.get(pad_name)
            if meta is not None and dest_lid == meta.get("level_id"):
                continue  # identity within a pool
            dest_region = lid_to_region.get(dest_lid)
            if dest_region is None:
                continue
            label = (pad_name[:-len(" Warp Pad")]
                     if pad_name.endswith(" Warp Pad") else pad_name)
            region_to_label[dest_region] = f"the {label} pad"

        if not region_to_label:
            return

        text: Dict[int, str] = {}
        for loc in self.multiworld.get_locations(self.player):
            if loc.address is None or loc.parent_region is None:
                continue
            region_name = loc.parent_region.name
            label = region_to_label.get(region_name)
            if label is None and region_name.endswith(": Podium"):
                # Podium-rung locations live in the dead-end "<track>: Podium" region
                # (Regions.py:399), not "<track>", so their parent_region never matches
                # a destination region directly. Map by the track-name prefix so rungs
                # of a shuffled track carry the pad hint too (podium_placement_checks).
                label = region_to_label.get(region_name[:-len(": Podium")])
            if label is not None:
                text[loc.address] = label

        if text:
            hint_data[self.player] = text

    def _describe_pad_req(self, req: Dict[str, int]) -> str:
        """Render a {type,count,colour} pad requirement as a tier-true, human-readable
        string. Decodes via the SAME ITEM_BY_TYPE / AGG_BY_TYPE tables native mirrors,
        so it reflects exactly what the wire carries -- a dropped relic tier (the
        pre-schema-4 bug, every gold/platinum gate flattened to sapphire) would surface
        here rather than staying invisible."""
        from .Rules import ITEM_BY_TYPE, AGG_BY_TYPE
        t, count, colour = req["type"], req["count"], req["colour"]
        if t == 0:
            return "free (native default)"
        if t == 1 and count == 0:
            return "free (0 trophies, bootstrap)"
        if t in AGG_BY_TYPE:
            label = {6: "CTR Token", 7: "Relic", 8: "Gem"}[t]
            return f"any {count} {label}"
        return f"{count}x {ITEM_BY_TYPE[t](colour if colour >= 0 else 0)}"

    @classmethod
    def stage_post_fill(cls, multiworld) -> None:
        """Prove the racer-lock self-lock invariant on the FILLED multiworld,
        once for every CTR slot in the room.

        Issue #209 names "a fill can never place a character's own unlock item
        behind a pad that requires that same character" as a thing that has to
        be built and proven, not asserted. With the unlock items as progression
        AP's fill already guarantees it; this re-derives it from the real
        placements so a future change to the lock selection cannot quietly
        break it. A stage hook runs after every world's `post_fill`, so it sees
        the final placements, and one shared all-items state serves every CTR
        slot. No-op when racer locks are off.
        """
        characters.verify_room_no_self_lock(multiworld)

    def write_spoiler(self, spoiler_handle) -> None:
        """Record this seed's per-pad unlock requirements (stage 1 + stage 2) with
        tier-true item names. The spoiler previously logged NOTHING about pad
        requirements, so the 2026-07-08 relic-tier wire bug was invisible to a spoiler
        read; this section makes the exact gate native enforces auditable per seed.

        Also records a terminal fill-backstop firing (rollback-precollect) so a
        rescued seed is diagnosable. Written ONLY when the backstop fired: a
        non-fired seed adds nothing here, keeping it byte-identical to a build
        without the backstop (the fired: yes/no verdict is the line's presence)."""
        if hasattr(self, "ctr_content_plan"):
            spoiler_handle.write("\nCTR independent content/item plan:\n")
            json.dump(self.ctr_content_plan, spoiler_handle, indent=2)
            spoiler_handle.write("\nOriginal from-pool starts: " + repr(self.ctr_content_original_starts) + "\n")
            # Plando and item links (#133 PR 4f): only when either moved an item.
            accounting = getattr(self, "ctr_framework_accounting", None)
            if accounting and any(accounting.values()):
                spoiler_handle.write(
                    "Plando and item links: "
                    + "; ".join(f"{label} {dict(sorted(accounting[key].items()))}"
                                for key, label in (("from_pool", "plando from the pool"),
                                                   ("added", "explicit plando items"),
                                                   ("removed", "filler removed for them"),
                                                   ("linked", "linked copies"))
                                if accounting[key]) + "\n")
            # Hit Character Key fallback on content plans (#133 PR 4d): the
            # same lines as a normal seed's; nothing when Hit Character is off.
            for _guest, _keys in sorted((getattr(self, "ctr_hit_character_fallback", {}) or {}).items(),
                                        key=lambda item: (item[1], item[0])):
                spoiler_handle.write(
                    f"CTR Hit Character ({self.multiworld.player_name[self.player]}): "
                    f"{characters.CHARACTER_ID_TO_NAME[int(_guest)]} has no unlock race in this seed and "
                    f"joins races at {_keys} {'Key' if _keys == 1 else 'Keys'}.\n")
            return
        # Character phase (#54/#209): which racer this seed starts you as, and
        # which pads demand a specific racer. Both are per-seed DRAWS rather
        # than option values, so without this a spoiler read cannot tell you
        # what the seed actually decided.
        _player_name = self.multiworld.player_name[self.player]
        spoiler_handle.write(
            f"\n\nCTR starting character ({_player_name}): "
            f"{getattr(self, 'ctr_starting_character', '?')}\n")
        _boss_venues = boss_track_shuffle.spoiler_lines(self.options)
        if _boss_venues:
            spoiler_handle.write(f"CTR boss tracks ({_player_name}):\n")
            for _line in _boss_venues:
                spoiler_handle.write(f"  {_line}\n")
        _locks = getattr(self, "ctr_racer_locks", {}) or {}
        if _locks:
            spoiler_handle.write(
                f"CTR racer-locked pads ({_player_name}):\n")
            for _pad, _character in sorted(_locks.items()):
                spoiler_handle.write(f"  {_pad}: requires {_character}\n")

        # Hit Character Key fallback (2026-09-18): which guests had no unlock
        # win in this seed and now join the opponent pool on Keys instead. This
        # is a per-seed DERIVATION from the created locations, not an option
        # value, so a spoiler read cannot otherwise tell. Nothing is written
        # when no guest fell back, keeping those spoilers byte-identical.
        for _guest, _keys in sorted(
                (getattr(self, "ctr_hit_character_fallback", {}) or {}).items(),
                key=lambda item: item[1]):
            spoiler_handle.write(
                f"\n\nCTR Hit Character ({_player_name}): "
                f"{characters.CHARACTER_ID_TO_NAME[int(_guest)]} has no unlock "
                f"race in this seed and joins races at {_keys} "
                f"{'Key' if _keys == 1 else 'Keys'}.\n")

        if getattr(self, "_ctr_backstop_fired", False):
            player_name = self.multiworld.player_name[self.player]
            items = getattr(self, "_ctr_backstop_items", [])
            mode = getattr(self, "_ctr_backstop_mode", "?")
            spoiler_handle.write(
                f"\n\nCTR fill backstop FIRED ({player_name}, {mode} mode): "
                f"precollected {len(items)} progression item(s) into starting "
                f"inventory so the greedy fill converges -- {', '.join(items)}. "
                f"Seed stays fully reachable; this is a diagnosable rescue.\n")

        # Issue #261: tell the player which destination each changed physical
        # pad loads. Identity entries produce no section at all, preserving the
        # exact spoiler output for seeds without an effective destination swap.
        # A pad whose resolved destination is a cup a custom track displaced
        # reports the custom track as the effective load, with the displaced
        # cup retained for auditability (H6-01).
        _pad_ids = getattr(self, "warp_pad_ids", {})
        destination_rows = changed_pad_destination_rows(
            self._resolve_warp_pad_map(),
            _pad_ids,
            effective_custom_destinations(
                getattr(self, "custom_tracks", {}) or {}),
            {cortex_vortex_track.DESTINATION_ID: cortex_vortex_track.CORTEX_VORTEX},
        )
        # Cortex Vortex pad track: which destination went without a pad and
        # which physical pad loads the track. Written only with the option on.
        _dropped = cortex_vortex_track.dropped_level_id(self.options)
        if _dropped is not None:
            _pad_names = {meta["level_id"]: name for name, meta in _pad_ids.items()}
            _loaded_by = next(
                (_pad_names.get(int(lid), f"pad {lid}")
                 for lid, dest in self._resolve_warp_pad_map().items()
                 if int(dest) == cortex_vortex_track.DESTINATION_ID), "?")
            _dest_region = cortex_vortex_track.destination_table()[_dropped][1]
            spoiler_handle.write(
                f"\n\nCTR Cortex Vortex track ({_player_name}): "
                f"{_dest_region} (destination {_dropped}) has no pad this seed "
                f"and its checks are removed; Cortex Vortex is loaded by "
                f"{_loaded_by}.\n")
        if destination_rows:
            spoiler_handle.write(
                f"\n\nCTR shuffled warp-pad destinations ({_player_name}):\n")
            for _, physical_name, destination_name in destination_rows:
                spoiler_handle.write(
                    f"  {physical_name}: loads {destination_name}\n")

        padgate = self._resolve_warp_pad_unlock()
        id_to_name = {
            meta["level_id"]: pad_name
            for pad_name, meta in getattr(self, "warp_pad_ids", {}).items()
        }
        rows = []
        for lid_str, stages in padgate.items():
            s1 = stages.get("stage1", {"type": 0, "count": 0, "colour": -1})
            s2 = stages.get("stage2", {"type": 0, "count": 0, "colour": -1})
            if s1.get("type", 0) == 0 and s2.get("type", 0) == 0:
                continue  # fully-default (vanilla / non-randomized) pad -- keep it compact
            try:
                lid = int(lid_str)
            except (TypeError, ValueError):
                lid = 1_000_000
            name = id_to_name.get(lid, f"pad {lid_str}")
            parts = [f"stage1: {self._describe_pad_req(s1)}"]
            if s2.get("type", 0) != 0:
                parts.append(f"stage2: {self._describe_pad_req(s2)}")
            rows.append((lid, name, "; ".join(parts)))
        player_name = self.multiworld.player_name[self.player]
        spoiler_handle.write(
            f"\n\nCTR warp-pad unlock requirements ({player_name}):\n")
        if not rows:
            spoiler_handle.write(
                "  (vanilla unlock mode -- no randomized pad requirements)\n")
            return
        for _, name, desc in sorted(rows):
            spoiler_handle.write(f"  {name}: {desc}\n")

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)
