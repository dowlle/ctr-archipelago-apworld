import logging
import json
import os
from typing import ClassVar, Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from Options import OptionError
from worlds.AutoWorld import World, CollectionState, WebWorld
from .elastic_bounds import CTRSettings, estimated_filler_reserve
from .gem_cup_legs import (cup_legs_to_wire, resolved_gem_cup_legs,
                           resolved_gem_cup_legs_table)
from .custom_tracks import (custom_tracks_to_wire,
                            reconstruct_custom_tracks_from_wire,
                            resolved_custom_tracks)
from .Locations import CTR_LOCATION_CLASSES, get_location_names, get_total_locations
from .Items import load_item_table
from . import item_supply
from . import wumpa_family
from .wumpa_checks import WUMPA_CLASS
from .itemsanity import ITEMSANITY_CLASS, ITEM_NAMES, WEAPONS
from . import item_boxes
from .item_boxes import ITEM_BOX_CLASS
from . import tizi_helper
from .tizi_helper import TIZI_HELPER_ITEM
from . import turbo_grant
from .turbo_grant import TURBO_GRANT_ITEM
from . import lettersanity
from .lettersanity import LETTERSANITY_CLASS
from .Options import (ctrAPOptions, OxideGoal, FinalOxideUnlock,
                      create_option_groups)
from . import characters
from . import progressive_capability
from . import rung_sizer
from .spoiler_pad_map import changed_pad_destination_rows
from . import version
from .Regions import create_regions
from .relic_tiers import (
    RELIC_TIERS, draw_relic_tier_keep, restore_relic_tier_keep_from_wire,
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

# Comfort-only issues #14/#15 pack. It stays atomic when a reduced location
# set cannot host all five, rather than emitting a seed-dependent subset.
SURFACE_ITEM_NAMES = frozenset({
    "Ignore Grass", "Ignore Dirt", "Ignore Snow", "Ignore Water", "Ignore Ice",
})


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
    _item_data_by_name = {item["name"]: item for item in load_item_table()}
    item_name_to_id = {
        name: item["code"] for name, item in _item_data_by_name.items()
    }
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
        # rework. All 20 are in the group and buildable.
        "Traps": set(ALL_TRAP_ITEM_NAMES),
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
        p = self.player
        n = self.options.oxide_final_challenge_relic_count.value
        mode = self.options.oxide_final_challenge_unlock.value
        F = FinalOxideUnlock
        S, G, Pl = "Sapphire Relic", "Gold Relic", "Platinum Relic"
        if mode == F.option_gold_relics:
            return lambda st: st.has(G, p, n)
        if mode == F.option_platinum_relics:
            return lambda st: st.has(Pl, p, n)
        if mode == F.option_any_relic_type:
            return lambda st: st.has(S, p, n) or st.has(G, p, n) or st.has(Pl, p, n)
        if mode == F.option_total_relics:
            return lambda st: (st.count(S, p) + st.count(G, p)
                               + st.count(Pl, p)) >= n
        return lambda st: st.has(S, p, n)  # sapphire_relics (default)

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

        Only options that steer the reachability graph are restored. include_gem_cups
        / include_battle_arenas are not on the wire, so they are DERIVED from whether
        their pad class carries a randomized (non-type-0) stage-1 requirement -- the
        exact condition create_items / create_regions gate their exit-rule handling
        on. Logic-irrelevant mirrors (one_lap_cups, death_link, ...) are skipped."""
        o = self.options
        co = passthrough.get("ctr_options", {})

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
        # #145 made the boost chain a reachability input (the Itemsanity Turbo
        # checks require one received Progressive Boost when the chain is
        # randomized), so the seed's mode must override the tracking player's
        # own YAML or UT's Turbo logic diverges from server truth. The wire
        # value is the option value verbatim (0 off / 1 shared_global /
        # 2 per_character); absent on pre-#12 wires -> no-op.
        _restore("progressive_boost", "boost_mode")
        _restore("logic_difficulty", "logic_difficulty")
        # #109 box seeds: the toggle + knowledge tier decide which box slots
        # exist and the stat chains join the boost chain as reachability
        # inputs (hard-tier slots), so all three seed values must win over
        # the tracking player's YAML. All raw scalars, absent on older wires.
        _restore("progressive_stats", "stats_mode")
        if "box_locations" in co:
            o.box_locations.value = int(bool(co["box_locations"]))
        _restore("shortcut_knowledge", "shortcut_knowledge")
        # Character phase (#54/#209). Two logic-relevant keys, both of which UT
        # gets wrong by default if it falls back to the tracking player's YAML:
        #   character_unlocks decides whether 15 unlock items exist AT ALL, so
        #     restoring it wrong rebuilds a different pool -- and on a reduced
        #     seed the re-generation does not even FIT, which is exactly how
        #     the fuzz matrix's check-ut arm caught this (6/500 seeds);
        #   racer_locked_pads decides whether those items are progression, and
        #     a progression/useful split UT gets wrong makes every downstream
        #     sphere wrong.
        # starting_stat_class / penta_stats / editable_stats are cosmetic or
        # native-only and are deliberately NOT restored (same reasoning as
        # one_lap_cups). The starting racer itself is restored separately in
        # generate_early, because it is a per-seed draw, not an option value.
        if "character_unlocks" in co:
            o.character_unlocks.value = int(bool(co["character_unlocks"]))
        if "racer_locked_pads" in co:
            o.racer_locked_pads.value = int(bool(co["racer_locked_pads"]))

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
        o.include_gem_cups.value = int(inc_cups)
        o.include_battle_arenas.value = int(inc_arenas)

        # Podium rung set is decided by five options that are NOT on the wire, but
        # the podium_checks block encodes exactly which rungs this seed created:
        # its "enabled" flag plus, per track, a 5-slot array in podium.SLOT_ORDER
        # ([held_1st, held_3rd, held_5th, finish_podium, finish_any], -1 = absent).
        # Recover the toggles from a sample track so create_regions / Rules /
        # _resolve_podium_checks rebuild the identical rung locations.
        pod = passthrough.get("podium_checks", {}) or {}
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
        o.lettersanity.value = int(co.get("lettersanity", lb.get("mode", 0)))
        o.letters_per_track.value = int(lb.get("letters_per_track", 3))
        by_id = {v: k for k, v in lettersanity.TRACK_LEVEL_IDS.items()}
        o._lettersanity_selected = {
            by_id[int(lid)]: tuple(letter for letter, code in zip(lettersanity.LETTERS, codes) if code != -1)
            for lid, codes in (lb.get("locations", {}) or {}).items() if int(lid) in by_id}

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
        if not hasattr(self.options, "_lettersanity_selected"):
            mode = int(self.options.lettersanity.value)
            if mode in (1, 2):
                count = int(self.options.letters_per_track.value)
                self.options._lettersanity_selected = {
                    track: tuple(self.random.sample(lettersanity.LETTERS, count))
                    for track in lettersanity.LETTER_TRACKS}
            else:
                self.options._lettersanity_selected = {
                    track: lettersanity.LETTERS for track in lettersanity.LETTER_TRACKS}

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
        rung_sizer.apply_rung_sizing(self)

    def create_regions(self):
        create_regions(self)

    def set_rules(self):
        set_rules(self)

    def pre_fill(self) -> None:
        """Per-seed fillability guards -- one branch per warp-pad fill mode.

        RANDOMIZED-MODE BRANCH: two-stage guard (design rule: a pad's tier 2 MAY
        collapse if a seed needs it FOR GENERATION).

        CTR's item pool is ~98% progression in every config, and AP's greedy
        fill_restrictive cannot reliably ORDER a near-full pool through stacked
        logical stage-2 gates -- every seed stays fully reachable, but a small
        fraction (~0.1-0.2%) is not greedily fillable, raising FillError. The
        relaxation knobs (per-pad collapse roll, real-gate cap, count ceilings,
        slider filter, min-3 bootstrap) shrink that tail but cannot zero it, while
        a FULL stage-2 collapse fills 0/10000. So: keep genuine two-stage by default
        and, only when THIS seed would FillError, collapse every stage-2 gate for it.

        Mechanism: run a faithful DRY-RUN of the exact fill on an independent,
        identically-seeded+optioned parallel multiworld (same world.random stream ->
        same fill decisions). If the dry run raises FillError, re-install the real
        world's TT/token rules in COLLAPSED form (add_time_trial_and_ctr_requirements
        already honours the flag) so the real fill that Main runs next is the
        guaranteed-fillable single-stage DAG. Any probe error falls back to KEEPING
        two-stage (fail-open: never makes a fillable seed worse).

        TERMINAL BACKSTOP (both modes, solo only): after any mode-specific rung,
        the shared rollback-precollect backstop replays the real fill and, if it
        still dead-ends, precollects the stranded progression so the seed cannot
        ship an unfillable red. See _rollback_precollect_backstop."""
        # Universal Tracker (issue #29): under a fake generation there is no real
        # fill to protect, and the two-stage probe would re-roll a parallel fill on
        # a DIFFERENT seed and could wrongly collapse the stage-2 gates we just
        # pinned from slot_data. Skip all fill machinery -- reachability is fixed by
        # the reconstructed rules, and the server supplies the real item placements.
        if getattr(self.multiworld, "generation_is_fake", False):
            return
        solo = len(self.multiworld.worlds) == 1
        # Randomized two-stage rung: faithful parallel-MW probe; on a predicted
        # FillError collapse every stage-2 gate for this seed. Necessary but, on
        # dense post-fix trees, not always sufficient (the stage-2 collapse cannot
        # touch the stage-1 + near-full-pool residual -- 0.43% at the max any_of
        # corner on 60415b4ad) -- the terminal backstop below closes that residual.
        if (getattr(self, "_ctr_two_stage_active", False)
                and not getattr(self, "_ctr_force_collapse_stage2", False)):
            if self._probe_two_stage_fillable() is False:
                self._ctr_force_collapse_stage2 = True
                # Overwrite the stage-2 access rules with the collapsed (plain
                # can_reach Trophy Race) form; fill_slot_data also emits type-0
                # stage 2. This re-install only reassigns loc.access_rule closures
                # and consumes no multiworld.random (verified) -- so the terminal
                # backstop's replay fidelity survives it.
                from .Rules import add_time_trial_and_ctr_requirements
                add_time_trial_and_ctr_requirements(self, self.player)
                from .warp_pad_logic import warn_stage2_collapsed
                n = len(self.multiworld.worlds)
                warn_stage2_collapsed(
                    self, "fill",
                    f"{n} slot{'' if n == 1 else 's'} in the room")
        # Terminal rollback-precollect backstop -- the universal solo safety net.
        # Solo only (replay fidelity: nothing consumes multiworld.random between
        # here and the fill). Vanilla and randomized both route through the same
        # mode-agnostic machinery; a non-fired seed is byte-identical to an
        # un-backstopped build, a fired seed is logged to the spoiler.
        if solo:
            mode = ("vanilla" if self.options.warppad_unlock_requirements.value == 0
                    else "randomized")
            self._rollback_precollect_backstop(mode)

    def _probe_two_stage_fillable(self):
        """True/False if a faithful parallel dry-run fills; None if the probe could
        not run (caller treats None as 'keep two-stage').

        MULTIWORLD-AWARE (issue #75, ruled 2026-08-07). The probe mirrors the REAL
        room: same player count, same games per slot, each slot carrying its own
        option object. It used to dry-run `_MW(1)` unconditionally, so in a
        multiworld it predicted the fillability of a room that does not exist.

        Why that mattered: CTR's FillError tail is a property of the ROOM, not of
        the CTR slot. Measured on 0.1.5 (`podium_placement_checks: false`, 2-player
        against a 0-location companion, 10,000 seeds), the solo-shaped probe let 90
        seeds reach a real FillError, and separately collapsed stage 2 on seeds that
        fill perfectly well in the real room -- a third of its collapses in the
        tightest config were such false positives. Mirroring the room removes both
        directions of the error, because the dry run and the real fill are finally
        the same problem.

        SOLO IS UNCHANGED BY CONSTRUCTION: with one player the mirror IS `_MW(1)`
        with this world's own options, i.e. exactly the shipped probe. Verified as a
        byte-identical 10,000-seed arm, not just argued.

        COMPANION PRE_FILL IS MIRRORED (Bethany/Dex CTR+KH2 report, 2026-08-21).
        The probe used to skip the `pre_fill` step entirely, and that skew was a
        systematic false-collapse source: a companion whose `pre_fill` locks
        items into dedicated locations (KH2 places Donald, Goofy and keyblade
        abilities into 66 of its own locations) leaves the REAL room's main fill
        with matching item and location counts, while the mirror still showed
        those locations as open with no items for them. The mirror's fill then
        dead-ended on the phantom surplus and collapsed stage 2 on a room the
        real generator fills without complaint (measured 6 of 6 collapses on
        Dex's CTR+KH2 pair). The mirror now runs Main.py's `pre_fill` step via
        the same `call_all`, with one exception: every CTR world instance on the
        mirror has its `pre_fill` replaced by a no-op, because CTR's `pre_fill`
        IS this method's caller (running it would recurse) and its only
        multiworld-relevant action is the collapse decision this probe exists to
        make -- the room state with CTR pre_fill skipped is exactly the
        keep-two-stage room the probe is predicting. The exception keys on the
        world CLASS, never on a game-name string, so it covers every CTR slot in
        the room and no companion. Only the mirror's RNG streams are consumed;
        `self.multiworld.random` is untouched, so backstop replay fidelity is
        unaffected.

        The probe does not reproduce item links. It is a fillability predictor,
        not a second generator; any error keeps two-stage."""
        try:
            from BaseClasses import MultiWorld as _MW, CollectionState as _CS
            from worlds.AutoWorld import call_all as _call_all, AutoWorldRegister
            from Fill import distribute_items_restrictive as _dist
            real = self.multiworld
            # AP numbers real slots 1..N contiguously, which is what _MW(n) builds.
            # If that ever stops holding, fail open rather than probe a room whose
            # slot numbering does not match the one we are predicting for.
            players = tuple(real.player_ids)
            if players != tuple(range(1, len(players) + 1)):
                logging.warning("[CTR] two-stage fillability probe skipped: "
                                "non-contiguous player ids; keeping two-stage.")
                return None
            pmw = _MW(len(players))
            pmw.game = dict(real.game)
            pmw.player_name = dict(real.player_name)
            pmw.set_seed(real.seed)
            # Same construction style as the shipped solo probe, one slot per real
            # slot: instantiate the slot's own world type and hand it the REAL
            # world's option object, so every slot rolls identically to the room
            # being predicted.
            pmw.worlds = {
                p: AutoWorldRegister.world_types[real.game[p]](pmw, p)
                for p in players
            }
            for p in players:
                pmw.worlds[p].options = real.worlds[p].options
            # State BEFORE the world steps, exactly as Main.py:51 orders it
            # (`multiworld.state = CollectionState(multiworld)` runs before any
            # `call_all`). The probe used to build it afterwards, which worked
            # only for as long as no CTR step touched `multiworld.state`; the
            # character phase's `push_precollected` in create_items does, and it
            # made the probe fail open (returning None) on every seed instead of
            # returning a verdict. Ordering it like the real generator is the
            # fidelity fix, not a workaround: a probe that does not mirror
            # Main.py cannot predict Main.py.
            pmw.state = _CS(pmw)
            for step in ("generate_early", "create_regions", "create_items",
                         "set_rules", "connect_entrances", "generate_basic"):
                _call_all(pmw, step)
            # Main.py's pre_fill step, with the mirror's CTR slots no-opped
            # (see COMPANION PRE_FILL IS MIRRORED above). Instance-attribute
            # assignment shadows the bound method for exactly these objects;
            # call_all still walks every slot in real player order and still
            # runs any stage_pre_fill class hooks.
            for p in players:
                if isinstance(pmw.worlds[p], ctrAPWorld):
                    pmw.worlds[p].pre_fill = lambda: None
            _call_all(pmw, "pre_fill")
            _dist(pmw)
            return True
        except Exception as e:
            from Fill import FillError as _FE
            if isinstance(e, _FE):
                return False
            logging.warning("[CTR] two-stage fillability probe errored (%s); "
                            "keeping two-stage.", type(e).__name__)
            return None

    _ROLLBACK_BACKSTOP_MAX_ROUNDS = 40

    def _vanilla_fill_backstop(self) -> None:
        """Vanilla-mode entry to the shared terminal backstop. Kept as a named
        method because the vanilla-fill story (levers 1+2 -- honest relic
        classification + vanilla early-Keys -- shrink the tight-fill FillError
        class to a ~0.1-0.2% residual that this removes exactly) is documented
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

        REPLAY FIDELITY across modes (why solo is enough for both):
          - vanilla mode: pre_fill routes straight here;
          - randomized mode: the two-stage probe builds its OWN parallel
            MultiWorld with its own RNG, and the stage-2 collapse re-install
            (add_time_trial_and_ctr_requirements) only reassigns loc.access_rule
            closures -- neither consumes self.multiworld.random. create_filler
            returns a fixed Wumpa Fruit, so the precollect top-up draws no RNG
            either. So the RNG state the simulation snapshots is exactly the state
            the real fill will run from (harness-asserted over 100 seeds).

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
                return True
            except _FE:
                return False
        finally:
            self._fill_rollback(snap)
            logging.disable(prev_disable)

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
        item_id: int = self.item_name_to_id[name]
        classification = self._item_data_by_name[name]["classification"]
        # Honest per-seed relic classification (vanilla-fill lever 1).
        # data/items.json marks every relic "progression" unconditionally, but in a
        # vanilla-warp-pad seed whose goal/accessibility does not depend on a relic
        # tier, that tier gates nothing -- yet the ordered fill still treats it as
        # progression, inflating the pool to exactly the location count (zero slack)
        # and cornering fill_restrictive on the deepest currency. Downgrade such a
        # tier to "useful" so it leaves the ordered fill (placed by remaining_fill).
        # The map is a pure function of options; see _relic_progression_map.
        relic_prog = getattr(self, "_ctr_relic_prog", None)
        if relic_prog is not None and relic_prog.get(name) is False:
            classification = ItemClassification.useful
        # Honest per-seed BOOST classification, the same lever in the other
        # direction. #145 Itemsanity is the first logic reader of a capability
        # tier: its Turbo checks require one received Progressive Boost when
        # the chain is randomized (Decision 2 ruling, 2026-08-10). Logic state
        # only tracks progression items, so the gate is only real if the chain
        # is progression in exactly those seeds -- left `useful` (the #12/#13
        # shape), the Turbo checks sit permanently outside logic and fill
        # forbids progression/useful there, which surfaced as FillErrors in
        # the 5,000-run default fuzz arm. Every other seed keeps the frozen
        # `useful` classification from data/items.json.
        # #109 box slots are the second reader: boost-gated slots exist in
        # every box seed, and the hard-knowledge slots additionally read the
        # three stat chains (the hard-tier general rule), so those chains
        # upgrade too -- but ONLY at hard, because no easier tier creates a
        # stats-reading slot.
        # The USF finish gate (usf_finish.py, ruled 2026-08-12) is the
        # third reader and the one that makes the boost upgrade UNCONDITIONAL:
        # Hot Air Skyway's Trophy Race is a static location present in every
        # seed, so every randomized-boost seed reads the chain now, whatever
        # itemsanity and box locations are set to. Left `useful`, that track's
        # finish -- and its time trials, token challenge and finish rungs --
        # would sit permanently outside logic, the same FillError class the
        # #145 upgrade was written for. The stat chains keep their narrower
        # condition: no rule outside the hard box tier reads them.
        _boost_mode = int(self.options.progressive_boost.value)
        _boost_names = ({progressive_capability.BOOST_CHAIN} if _boost_mode == 1
                        else {progressive_capability.boost_item_name(c)
                              for c in progressive_capability.ROSTER}
                        if _boost_mode == 2 else set())
        if name in _boost_names:
            classification = ItemClassification.progression
        _stats_mode = int(self.options.progressive_stats.value)
        _stat_names = (set(progressive_capability.STAT_CHAINS)
                       if _stats_mode == 1 else
                       {progressive_capability.stat_item_name(chain, character)
                        for character in progressive_capability.ROSTER
                        for chain in progressive_capability.STAT_CHAINS}
                       if _stats_mode == 2 else set())
        if (name in _stat_names
                and ITEM_BOX_CLASS.is_enabled(self.options)
                and int(self.options.shortcut_knowledge.value) == item_boxes.SK_HARD):
            classification = ItemClassification.progression
        # Honest per-seed CHARACTER classification (R17), the same lever again.
        # data/items.json freezes all 16 racers as `useful`; a racer-locked seed
        # has pads whose access rule reads one, so in exactly those seeds the
        # unlock items are genuine progression. Locks off leaves them `useful`,
        # which is both the correct AP semantics for an item that gates nothing
        # and a deliberate relaxation of an already ~98%-progression pool.
        if name in characters.ROSTER_CHARACTER_ID:
            classification = characters.unlock_classification(self)
        return ctrAPItem(
            name=name,
            classification=classification,
            code=item_id,
            player=self.player,
        )

    def _relic_progression_map(self) -> Dict[str, bool]:
        """Which relic tiers are genuine PROGRESSION in this seed (True) vs merely
        USEFUL (False). A relic tier is progression only when some reachable-required
        location or the goal actually depends on owning it.

        Enumeration of the (warp-pad mode, goal, accessibility) matrix -- vanilla
        mode is the ONLY case that ever downgrades:

        * Randomized / random_without_4_keys (mode 1/2): ALL relics stay
          progression. The sphere search may assign a relic entry or stage-2
          requirement to ANY pad, so relics must remain orderable by fill; the
          randomized path's own pre_fill relax-not-pin guard handles fillability.
          No behavioural change from today.
        * Vanilla mode (mode 0) -- two relic-count gates exist: the FIXED Slide
          Coliseum pad exit (has('Sapphire Relic', 10), data/world.json) and
          N. Oxide's Final Challenge, whose gate follows the CONFIGURED
          oxide_final_challenge_unlock mode + count in every seed (issue #53,
          Rules.add_oxide_final_challenge_rule -- the world.json 18-Sapphire
          text is legacy and overridden). So:
            - Sapphire: progression iff accessibility == full (the fixed Slide
              Coliseum gate must be reachable) OR the goal makes you reach + win
              Oxide's Final Challenge (oxidefinal). Else useful, unless it is a
              satisfying tier of the configured mode (next rule).
            - Any tier satisfying the configured mode (created > 0): progression
              iff accessibility == full (the Final Challenge location must be
              reachable) OR oxide_goal == final. Else useful.
            - A tier that is neither: useful.
        """
        o = self.options
        prog = {"Sapphire Relic": True, "Gold Relic": True, "Platinum Relic": True}
        # Universal Tracker (issue #29): read the seed's RESOLVED classification off
        # the wire rather than trying to recompute it from inputs that do not travel
        # (the per-tier progression sliders are not emitted). This map is not merely
        # cosmetic on the UT path: CollectionState.collect ignores non-advancement
        # items, so a tier the seed classified `useful` can never satisfy a has()
        # gate server-side. Assuming "all tiers progression" therefore made UT open
        # the vanilla Slide Coliseum pad (has('Sapphire Relic', 10), data/world.json)
        # on seeds where the server never can -- UT then reported its three time
        # trials in logic against a sphere that will never contain them (the ~12.6%
        # UT-check failures, all vanilla + accessibility:minimal + non-oxidefinal
        # seeds). The earlier comment here was right that no vanilla gate names
        # gold/platinum, but missed the Sapphire one.
        #
        # BACKWARDS COMPATIBILITY: seeds generated before `relic_progression` was
        # emitted carry no such key. For those, fall back to the historical
        # all-progression behaviour -- no worse than before, and it keeps UT usable
        # against already-rolled seeds.
        _pt = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        if _pt:
            wire = (_pt.get("ctr_options") or {}).get("relic_progression")
            if isinstance(wire, dict):
                return {tier: bool(wire.get(tier, True)) for tier in prog}
            return prog
        if o.warppad_unlock_requirements.value != 0:
            return prog  # randomized modes: any pad may gate on any relic tier
        access_full = o.accessibility.value == 0  # Accessibility.option_full == 0
        # Base vanilla-mode classification: the fixed vanilla LOCATION gate that
        # names a relic is Sapphire (Slide Coliseum has('Sapphire Relic', 10)),
        # so Sapphire is progression exactly when every location must be reachable
        # (accessibility: full). Gold/Platinum gate no FIXED vanilla location.
        prog["Sapphire Relic"] = access_full
        prog["Gold Relic"] = False
        prog["Platinum Relic"] = False
        # N. Oxide's Final Challenge (issue #53): the location's gate reads the
        # CONFIGURED oxide_final_challenge_unlock mode + count in every seed
        # (Rules.add_oxide_final_challenge_rule, native parity), so under
        # accessibility 'full' the satisfying tiers must be progression for the
        # location to be reachable -- the same created>0 respect as the goal
        # branch below (a tier the player opted out of stays useful and the
        # forced_options supply guard raises instead). Kept in lockstep with
        # raise_if_full_accessibility_needs_more_sapphires_than_created.
        if access_full:
            for tier in self._oxide_goal_tiers():
                if self._ctr_relic_created.get(tier, 0) > 0:
                    prog[tier] = True
        # Oxide-final goal (issue #23; #152 C4: generalized from the legacy
        # `goal == oxidefinal` value to the composed `oxide_goal == final`
        # condition -- this branch and forced_options.py's
        # raise_if_oxidefinal_goal_has_no_progression_tier guard must move in
        # lockstep, see that guard's docstring): the relic tiers that satisfy
        # the configured mode+count must be progression so fill, the spoiler
        # playthrough, and beatability chase the REAL goal (not the old
        # hard-coded 18 Sapphire). Respect the per-tier exact counts (issue
        # #171: was a percentage slider, now a created-location count) -- a
        # satisfying tier with 0 created stays out and is caught by
        # generate_early's guard rather than silently forced.
        if o.oxide_goal.value == OxideGoal.option_101_percent:
            # Sapphire is progression on ANY oxide-final seed (mode-independent):
            # once the goal makes any relic tier progression, fill may place a
            # progression relic behind the Slide Coliseum sapphire gate (the fixed
            # has('Sapphire Relic', 10) vanilla exit rule) -- Sapphire must stay
            # progression to keep those locations reachable. This mirrors the
            # pre-#23 goal, which was itself 18 Sapphire and always set this.
            # (The Final Challenge location gate itself is mode-aware since
            # issue #53, see the access_full block above.)
            prog["Sapphire Relic"] = True
            for tier in self._oxide_goal_tiers():
                if self._ctr_relic_created.get(tier, 0) > 0:
                    prog[tier] = True
        return prog

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

        # Both Oxide goal events inherit Oxide Station's confirmed finish
        # capability (triage ruling 2026-08-19): the challenge is raced on
        # Oxide Station, so the composed goal must not become true from Key 4
        # alone while the ordinary Trophy Race logic still demands the finish
        # term. track_finish_term carries the whole ruling -- two Progressive
        # Boosts at easy/medium, vacuous at hard shortcut knowledge, vacuous
        # when the chain is not randomized, racer-aware in per-character mode.
        from .usf_finish import track_finish_term
        oxide_finish = track_finish_term("Oxide Station", self)

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
                lambda state, f=flag, r=relic_rule, ft=oxide_finish:
                    state.has(f, player) and r(state) and ft(state, player))
            # Issue #27: exclude the real Final Challenge location only -- when
            # Oxide Goal is 'final' the FIRST Challenge is not this seed's goal
            # location and stays a normal, fillable check (issue #152 C8).
            self._exclude_goal_location(
                player, "N. Oxide Garage: N. Oxide's Final Challenge")
        # option_none: no Oxide predicate, nothing to lay.

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
            boss_predicate = (
                lambda state, fs=flags, n=n_bosses:
                    sum(state.has(f, player) for f in fs) >= n)
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
        player = self.player
        mw = self.multiworld
        pool = []

        # Per-seed relic classification (lever 1); consumed by create_item for every
        # relic created below (pool + slider/goal pins). Computed once here so the
        # whole create_items pass sees a single consistent map.
        self._ctr_relic_prog = self._relic_progression_map()

        # Vanilla-fill lever 2: in VANILLA warp-pad mode, seat the 4
        # hub-backbone Keys into early spheres so greedy fill_restrictive cannot
        # strand a Key in the zero-slack vanilla pool (the residual after lever 1).
        # VANILLA-ONLY: randomized mode already has its pre_fill guard and must stay
        # byte-identical, so it is untouched. Only meaningful when Keys are actually
        # in the shuffled pool (shuffle_keys on); when off, Keys are pinned to boss
        # races and never enter fill, so this is inert. early_items is a fill-order
        # hint (distribute_early_items, allow_partial) -- it changes neither what is
        # required nor any emitted slot_data value.
        if (self.options.warppad_unlock_requirements.value == 0
                and self.options.shuffle_keys.value):
            mw.early_items.setdefault(player, {})["Key"] = 4

        # Itemsanity's native crate filter returns Wumpa when the player has no
        # received weapon.  Seed one or two distinct weapon types into early
        # fill so an enabled seed has an opening weapon without granting it as
        # starting inventory.  No RNG is consumed while the toggle is off.
        if self.options.itemsanity.value:
            early_count = self.random.randint(1, 2)
            for weapon in self.random.sample(WEAPONS, early_count):
                mw.early_items.setdefault(player, {})[weapon] = 1

        self._install_goal(player)

        # --- Relic-tier exact-count removal (issue #171 conversion; issue #28
        # R1: removal, not pinning) ---
        # generate_early's relic draw (relic_tiers.draw_relic_tier_keep) already
        # decided exactly which of each tier's 18 Time Trial locations this seed
        # creates (self._ctr_relic_keep), and Regions.create_regions already built
        # Location objects for only those -- a below-count slot was never created
        # at all, so unlike the pinned-vanilla block this replaces (used to sit
        # here, __init__.py:849-902 on origin/main), there is no location left to
        # place_locked_item onto. _relic_locked below exists purely so the general
        # item-pool loop two blocks down creates (18 - n_created) fewer of that
        # relic -- the exact same "keep item count == location count" invariant
        # the old block's own n_locked bookkeeping maintained, just driven by the
        # draw's created count instead of a per-location pin roll. The Turbo Track
        # comfort guard is enforced inside the draw itself now (excluded from the
        # sample pool, relic_tiers.draw_relic_tier_keep), so there is nothing
        # left for create_items to force here.
        _relic_locked = {
            _relic_item: 18 - self._ctr_relic_created.get(_relic_item, 18)
            for _tier_label, _relic_item, _opt_name in RELIC_TIERS
        }

        # --- Gem & Key placement toggles (item #5) ---
        # Default OFF = pinned vanilla (each Gem locked to its Gem Cup, each Key
        # locked to its Boss Race -> out of the multiworld pool). ON = the item
        # enters the shuffled pool and its vanilla location becomes a normal check.
        # Track n_locked per item name so the general pool below creates
        # (count - n_locked) of it, keeping item count == location count.
        # Issue #152 C6 (drift fix, folded into the composition per the
        # dossier's Q30 ruling): renamed from the legacy `goal ==
        # option_allgemcups` check to the composed `gems_required_goal > 0`
        # condition. Behaviourally identical for what used to be reachable
        # (the old Choice's allgemcups value maps onto gems_required_goal ==
        # 5), and now correctly fires for any active Gems Required Goal
        # count, not just "all 5".
        _GEM_GOAL = self.options.gems_required_goal.value > 0
        _gems_locked: Dict[str, int] = {}
        _keys_locked: Dict[str, int] = {}
        _vmap = json.loads(
            pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
        )["ShuffleOptions"]

        # Gems: pin to gem-cup locations when shuffle_gems is OFF. When Gems
        # Required Goal is active with shuffle off, gemgoal() already placed
        # them (and place_locked_item on an already-filled location would
        # raise), so skip the placement here for that goal -- the pool
        # exclusion below still applies. Gems Required Goal + shuffle ON pins
        # nothing anywhere: the gems ride the pool (2026-07-15 ruling).
        if not self.options.shuffle_gems.value and not _GEM_GOAL:
            for _loc_name, _gem_name in _vmap["Gems"].items():
                mw.get_location(_loc_name, player).place_locked_item(
                    self.create_item(_gem_name)
                )
                _gems_locked[_gem_name] = _gems_locked.get(_gem_name, 0) + 1

        # Keys: pin to boss-race locations when shuffle_keys is OFF.
        if not self.options.shuffle_keys.value:
            for _loc_name, _key_name in _vmap["Boss Keys"].items():
                mw.get_location(_loc_name, player).place_locked_item(
                    self.create_item(_key_name)
                )
                _keys_locked[_key_name] = _keys_locked.get(_key_name, 0) + 1

        # Battle arenas (issue #50): pin the vanilla Purple CTR Tokens onto the 4
        # Crystal Bonus Round checks when include_battle_arenas is OFF.
        #
        # The option never removed those locations -- the four Crystal Bonus Round
        # entries live unconditionally in data/world.json, so the location count is
        # 213 with the option on and off alike. All the option did (Regions.py,
        # warp_pad_logic) was keep the crystal pads out of the randomized-unlock
        # pool. The checks themselves stayed live multiworld slots, and a 12-seed
        # sample put a logic-required progression item on an arena check in 4 of
        # them: the player is forced through content they explicitly opted out of.
        #
        # Pinning is the same contract the Gems / Boss Keys toggles above use:
        # place_locked_item takes the location out of the multiworld pool and puts
        # its vanilla item back on it, so nobody else's progression can be hidden
        # there. The mapping already existed in data/vanilla_mapping.json and was
        # read by nothing until now. Removing the locations outright would be the
        # cleaner fix but is a native/location-table change, not apworld-only.
        _arena_locked: Dict[str, int] = {}
        if not self.options.include_battle_arenas.value:
            for _loc_name, _token_name in _vmap["Bonus Round Tokens"].items():
                mw.get_location(_loc_name, player).place_locked_item(
                    self.create_item(_token_name)
                )
                _arena_locked[_token_name] = _arena_locked.get(_token_name, 0) + 1

        # Gem cups (issue #50, sibling of the arena block above): pin the vanilla
        # Gem onto each of the 5 "<Colour> Gem Cup: Gem" checks when
        # include_gem_cups is OFF but shuffle_gems is ON. Same defect as the
        # arenas: the option only keeps the cup warp pads vanilla-gated
        # (Regions.py) -- the 5 cup locations stay unconditional in
        # data/world.json, so with the Gems shuffled they are live multiworld
        # slots and fill hid logic-required progression on them (measured 4 of a
        # 12-seed sample). Pinning restores the vanilla Gem there and takes the
        # slot out of the pool; the cups stay reachable in logic (their vanilla
        # has('<Colour> CTR Token', 4) gate persists), so nothing softlocks.
        #
        # The three sibling configs are already covered elsewhere and must NOT
        # double-pin (place_locked_item on a filled location raises):
        #   - shuffle_gems OFF, gems_required_goal == 0: _gems_locked block
        #     (above) pinned them.
        #   - shuffle_gems OFF, gems_required_goal > 0: gemgoal() pinned them.
        #   - shuffle_gems ON, gems_required_goal > 0: forbidden in
        #     generate_early (raise_if_gems_required_goal_needs_excluded_cups
        #     -- the goal Gems ride the pool, so pinning them onto opted-out
        #     cups would strand the goal; the _GEM_GOAL guard below is the
        #     belt-and-suspenders).
        _cups_locked: Dict[str, int] = {}
        if not self.options.include_gem_cups.value \
                and self.options.shuffle_gems.value and not _GEM_GOAL:
            for _loc_name, _gem_name in _vmap["Gems"].items():
                mw.get_location(_loc_name, player).place_locked_item(
                    self.create_item(_gem_name)
                )
                _cups_locked[_gem_name] = _cups_locked.get(_gem_name, 0) + 1

        # Resolved once, before the pool loop reads it per item: how many copies
        # of each supply-spending wumpa name this seed creates. Empty dict when
        # the ladder is off, so the loop's lookup is a cheap miss.
        _wumpa_counts = wumpa_family.created_item_counts(self)

        # --- Create general item pool ---
        # When Gems Required Goal is active, gemgoal() LOCKS the 5 gems at the
        # gem-cup locations, so adding the same 5 gems from the item table again
        # makes them redundant progression items: the pool then exceeds the
        # available locations (gemgoal also consumes 5 cup locations) -> FillError
        # ("N more progression items than locations") and an item/location count
        # mismatch. Exclude the gems from the general pool for that goal (they
        # are the goal items, placed at the cups). Seeds without Gems Required
        # Goal active keep gems in the pool (Turbo Track's vanilla 5-gem gate
        # needs them findable) UNLESS shuffle_gems pinned them, in which case
        # _gems_locked subtracts them.
        _GEMS = {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"}
        for item in load_item_table():
            # Gems Required Goal: exclude the gems from the general pool ONLY
            # when gemgoal() locked them onto their cups (shuffle_gems off) --
            # adding them again would overflow the pool (see the note above).
            # With shuffle_gems ON the gems stay in the pool: they are the goal
            # items, hidden wherever the fill puts them (2026-07-15 ruling).
            if _GEM_GOAL and not self.options.shuffle_gems.value \
                    and item["name"] in _GEMS:
                continue
            count = item["count"]
            if self.options.itemsanity.value and item["name"] in ITEM_NAMES:
                count = 1
            # Tizi Helper (#223): exactly one copy, only when the option is on.
            # Same shape as the itemsanity line above -- the entry ships count 0
            # in data/items.json and the option is what makes it real. It adds no
            # location, so it is a straight +1 against this seed's supply; being
            # here (before the #14/#15 comfort-pack trim and the character
            # supply check) is what lets a deliberately reduced seed free a
            # comfort slot for it instead of overflowing the pool.
            if item["name"] == TIZI_HELPER_ITEM:
                count = tizi_helper.created_item_count(self)
            # The starting-wumpa ladder (2026-08-10 ruling): up to ten copies
            # of ONE progressive name, per the #12/#13 convention. Like the
            # helper above it carries no location of its own, so every copy is
            # one otherwise-filler slot spent, and it sits here -- before the
            # shedding tiers -- so a reduced seed can free a comfort slot for it
            # rather than overflowing. The two wumpa BUNDLES are deliberately
            # NOT here: they are filler substitutes drawn from the filler budget
            # further down, so counting them as pool demand would double-count
            # them against the supply check.
            if item["name"] in _wumpa_counts:
                count = _wumpa_counts[item["name"]]
            # Turbo Grant (#224): same shape and the same supply reasoning as
            # the helper above -- one copy when the option is on, no location of
            # its own, and placed before the comfort-pack trim so a reduced seed
            # frees a comfort slot for it rather than overflowing the pool.
            if item["name"] == TURBO_GRANT_ITEM:
                count = turbo_grant.created_item_count(self)
            if int(self.options.lettersanity.value) in (2, 3) and item["name"] in lettersanity.ITEM_NAMES:
                track = item["name"].rsplit("(", 1)[1][:-1]
                letter = item["name"].split(" ", 2)[1]
                count = int(int(self.options.lettersanity.value) == 3 or
                            letter in self.options._lettersanity_selected[track])
            if item["name"] in _relic_locked:                         # slider-pinned relics
                count = max(0, count - _relic_locked[item["name"]])
            if item["name"] in _gems_locked:                          # gems pinned vanilla
                count = max(0, count - _gems_locked[item["name"]])
            if item["name"] in _keys_locked:                          # keys pinned vanilla
                count = max(0, count - _keys_locked[item["name"]])
            if item["name"] in _arena_locked:                         # arenas pinned vanilla
                count = max(0, count - _arena_locked[item["name"]])
            if item["name"] in _cups_locked:                          # gem cups pinned vanilla
                count = max(0, count - _cups_locked[item["name"]])
            if count > 0:
                for _ in range(count):
                    pool.append(self.create_item(item["name"]))

        # --- Character unlocks (issues #54 / #209, R4). ALWAYS ON: the
        # character phase is core 0.2.0 content, not a toggle, so every seed
        # puts the 15 racers you did not start as into the pool and pushes the
        # one you did start as as precollected. They add ZERO locations, so
        # they are a straight +15 against this seed's supply -- which is why
        # they go in BEFORE the comfort-pack trim below rather than after it,
        # so a deliberately reduced seed frees the five optional #14/#15
        # comfort items for them instead of overflowing.
        #
        # Classification is per-seed (R17) and lives in create_item: progression
        # when racer-locked pads are on, useful when they are off.
        _start_character = self.ctr_starting_character
        mw.push_precollected(self.create_item(
            characters.unlock_item_name(_start_character)))
        for _unlock_name in characters.created_unlock_names(self):
            pool.append(self.create_item(_unlock_name))

        # --- Overflow shedding (Stef's ruling, 2026-08-18): FILLER first, then
        # the comfort pack, then refuse. The tiers, the reasoning and what is
        # never shed all live in item_supply.shed_overflow, which is a pure
        # function so every tier is reachable from a synthetic pool instead of
        # only from a seed whose options happen to land on the right overflow.
        # That testability is the point: the all-or-nothing behaviour this
        # replaced survived because reaching it needed roughly a 1-in-500 seed.
        #
        # A returned pool may be SMALLER than `unfilled` (tier 2 drops the pack
        # whole), which the filler top-up at the end of this method closes, and
        # it may still be LARGER, which the general capacity guard below
        # refuses.
        unfilled = len(mw.get_unfilled_locations(self.player))
        pool = item_supply.shed_overflow(
            pool, unfilled, SURFACE_ITEM_NAMES,
            filler_floor=estimated_filler_reserve(self))

        if int(self.options.lettersanity.value) == 3 and len(pool) > unfilled:
            raise OptionError(
                f"CTR: Lettersanity 'items_only' needs 48 spare filler slots, but this "
                f"option combination has only {max(0, unfilled - (len(pool) - 48))}. "
                "Enable more location checks or reduce other item packs.")

        # --- Progressive Boost / Progressive Stats item packs (issues #12,
        # #13/#252). Classification is resolved per seed in create_item from
        # the live rule readers. Empty dict when
        # both packs are off, so this is a no-op (byte-identical to a
        # pre-#12/#13 seed, no RNG draw taken) in the default configuration.
        # Runs AFTER the #14/#15 comfort-pack trim above so a tight seed's
        # freed slots (from omitting the comfort pack) are available to these
        # items too -- `unfilled` is the same live count either block reads,
        # `len(pool)` reflects whatever the trim above already did.
        _capability_counts = progressive_capability.created_item_counts(self)
        if _capability_counts:
            _capability_supply = unfilled - len(pool)
            progressive_capability.raise_if_capability_items_exceed_location_supply(
                self, available_supply=_capability_supply)
            for _cap_name, _cap_count in _capability_counts.items():
                for _ in range(_cap_count):
                    pool.append(self.create_item(_cap_name))

        # The character-unlock capacity check (issues #54/#209, R4). It runs
        # AFTER every option-specific item family -- character unlocks, the
        # shedding tiers, itemsanity weapons, and the progressive packs above --
        # is in the pool, so `len(pool)` is the COMPLETE current pool and
        # `unfilled` is the live post-creation location count (never a predicted
        # constant). Computed against the supply that would remain WITHOUT the
        # unlocks, so the message is honest about what is missing rather than
        # blaming whichever family happened to be appended last. No-op in
        # all-unlocked mode and on every seed that fits.
        #
        # It runs FIRST of the two capacity checks deliberately: when the
        # unlocks are what does not fit, its message says so specifically, which
        # is more useful than the general one below.
        characters.raise_if_unlocks_exceed_location_supply(
            self, available_supply=unfilled - (
                len(pool) - len(characters.created_unlock_names(self))))

        # THE general net-capacity check (2026-08-18). Every earlier guard is
        # per-family and therefore silent outside its own feature: the
        # lettersanity one covers only `items_only`, the capability one runs
        # only with a pack enabled, and the character one is a no-op when the
        # unlocks are off. A seed with all three inapplicable could reach fill
        # with more items than locations and die inside Archipelago's filler
        # stage with a message naming none of this -- which is exactly what the
        # 2026-08-18 mismatch did. This is the backstop that makes the next
        # no-location item family fail loudly at option-validation time instead
        # of one seed in five hundred later.
        #
        # It is placed after the shedding tiers ON PURPOSE: shedding is the
        # world's own attempt to fit, and only a seed that survives both tiers
        # still over is genuinely unsatisfiable.
        if len(pool) > unfilled:
            raise OptionError(
                f"CTR: this option combination creates {len(pool) - unfilled} more "
                f"item(s) than it has locations to hold them ({len(pool)} items, "
                f"{unfilled} locations). Enable more checks -- item boxes, itemsanity, "
                "podium rungs or lettersanity locations -- or turn off one of the "
                "options that add an item without adding a location.")

        mw.itempool += pool
        # Size filler off the UNFILLED locations, i.e. total minus the locations
        # already locked above (the goal-tracking companion events _install_goal
        # locks, and for the gem-cup goal the 5 locked gems). Using the static
        # get_total_locations over-counted by the
        # number of locked locations -> 1 (or 5) excess filler items -> the
        # item/location count mismatch the fuzzer flags. Clamp at 0 for safety.
        #
        # Count against THIS player's pool, not the global mw.itempool: in a
        # multiworld, mw.itempool already holds every earlier-processed world's
        # items here, so the old `unfilled - len(mw.itempool)` went negative and
        # silently skipped the top-up for any CTR world whose create_items did not
        # run first -> that player ended 1 item short of their locations ->
        # deterministic "Player X had 1 more locations than items" + FillError on
        # every multi-CTR generation with a filler-needing config. Solo unchanged
        # (there len(pool) == len(mw.itempool)).
        n_filler = max(0, unfilled - len(pool))
        # Trap fill: replace trap_fill_percentage% of the filler slots with traps,
        # drawn against the player's trap_weights (#280 -- the uniform v1 draw is
        # gone). Traps are non-progression, so this never changes reachability at
        # any value. trap_fill_percentage 0 IS GENERATION-NEUTRAL BY
        # CONSTRUCTION: the else branch is byte-identical to the old Wumpa-only
        # fill and no world.random draw is taken, so such a seed's spoiler +
        # slot_data are unchanged -- which is also why an all-zero weight table
        # is only an error when the fill is above 0.
        trap_pct = self.options.trap_fill_percentage.value
        if trap_pct > 0 and n_filler > 0:
            n_traps = (n_filler * trap_pct) // 100
            for trap_name in traps.draw_trap_names(self, n_traps):
                mw.itempool.append(self.create_item(trap_name))
            mw.itempool += [self.create_item(wumpa_family.draw_filler_name(self))
                            for _ in range(n_filler - n_traps)]
        else:
            mw.itempool += [self.create_item(wumpa_family.draw_filler_name(self))
                            for _ in range(n_filler)]

        # NOTE: an earlier density-adaptive force-collapse was removed -- CTR's pool
        # is ~98% progression in EVERY config (only ~1 filler item), so a density
        # signal cannot distinguish a tight seed from a normal one and would collapse
        # two-stage on virtually all seeds (defeating "two-stage is the DEFAULT
        # experience"). Solvability is instead held by the sphere-search invariant,
        # the per-pad relax-to-tier-1 fallback + baseline collapse roll, the stage
        # count ceilings, the slider-aware relic filter, and the min-2 bootstrap
        # breadth -- all proven to fill 0/5000 randomized two-stage-active configs
        # while keeping real, distinct tier-2 gates on the great majority of pads.

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
                loc = mw.get_location(loc_name, player)
                loc.place_locked_item(self.create_item(gem_name))

        gems = ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        predicate = (
            lambda state, gems=gems, n=n:
                state.has_from_list_unique(gems, player, n))
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
        """{"<physicalPadLevelID>": <targetTrackID>} — ALWAYS present.

        Identity over the 28 in-range pad LevelIDs AND the 5 gem-cup LevelIDs
        (100-104), then overlay any destination-shuffle remap (v3: cups now
        participate, and a track slot may load a cup and vice versa, so remap
        values span {0..27, 100..104}). Empty warp_pad_map -> pure identity.
        """
        m = {str(i): i for i in range(self.WARP_PAD_ID_RANGE)}
        pad_ids = getattr(self, "warp_pad_ids", {})
        # Gem-cup identity base (LevelID 100-104): a v3 seed always carries a cup
        # map so native never has to guess; absent == identity for a v2 native.
        for meta in pad_ids.values():
            if meta.get("kind") == "cup":
                lid = meta["level_id"]
                m[str(lid)] = lid
        for pad_name, target_track_id in getattr(self, "warp_pad_map", {}).items():
            meta = pad_ids.get(pad_name)
            if meta is None:
                continue
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE or meta.get("kind") == "cup":
                m[str(lid)] = int(target_track_id)
        return m

    def _resolve_gem_cup_legs(self) -> Dict[str, List[int]]:
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
        return cup_legs_to_wire(resolved_gem_cup_legs_table(self))

    def _resolve_warp_pad_unlock(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """{"<padLevelID>": {"stage1": {type,count,colour},
                             "stage2": {type,count,colour}}} — ALWAYS present.

        Two-stage contract (Option A, schema_version 2). Stage 1 opens the pad's
        Trophy Race; stage 2 (the 16 trophy pads only) opens that pad's CTR Token
        Challenge + 3 relic Time Trials, ANDed on top of stage 1. Both are keyed by
        PHYSICAL pad LevelID. Every in-range pad defaults to stage1/stage2 type 0
        ({0,0,-1}) so a vanilla-mode / fixed / no-stage-2 pad falls back to native's
        own rule (type 0 stage 2 = native opens the token/relic menu immediately).
        """
        pad_ids = getattr(self, "warp_pad_ids", {})
        unlock = getattr(self, "warp_pad_unlock", {})
        unlock_s2 = getattr(self, "warp_pad_unlock_stage2", {})

        def _req(d):
            return {"type": int(d["type"]), "count": int(d["count"]),
                    "colour": int(d["colour"])}

        _ZERO = {"type": 0, "count": 0, "colour": -1}

        # Default all in-range pad LevelIDs to type 0 for both stages.
        out: Dict[str, Dict[str, Dict[str, int]]] = {}
        for meta in pad_ids.values():
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
                out[str(lid)] = {"stage1": dict(_ZERO), "stage2": dict(_ZERO)}

        # Overlay the per-seed randomized requirements (stage 1 + stage 2).
        for pad_name, req in unlock.items():
            meta = pad_ids.get(pad_name)
            if meta is None:
                continue
            lid = meta["level_id"]
            if 0 <= lid < self.WARP_PAD_ID_RANGE:
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
        # Density-adaptive collapse (create_items): on a tight seed every stage 2 is
        # dropped in AP logic, so emit type-0 stage 2 to native too (the relic/token
        # menu opens the instant the trophy race is beaten) -- AP rules and native
        # stay in lockstep.
        if not getattr(self, "_ctr_force_collapse_stage2", False):
            for pad_name, req in unlock_s2.items():
                meta = pad_ids.get(pad_name)
                if meta is None:
                    continue
                lid = meta["level_id"]
                if 0 <= lid < self.WARP_PAD_ID_RANGE:
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

    def _resolve_podium_checks(self) -> Dict[str, object]:
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
        from .podium import PODIUM_CLASS, TROPHY_TRACKS
        enabled = bool(self.options.podium_placement_checks.value)
        block: Dict[str, object] = {"enabled": enabled, "locations": {}}
        rung_keys = PODIUM_CLASS.created_rung_keys(self.options)
        if not rung_keys:
            return block
        pad_ids = getattr(self, "warp_pad_ids", {})
        track_to_lid = {
            pad_name[: -len(" Warp Pad")]: meta["level_id"]
            for pad_name, meta in pad_ids.items()
            if pad_name.endswith(" Warp Pad")
        }
        locations: Dict[str, object] = {}
        for track in TROPHY_TRACKS:
            lid = track_to_lid.get(track)
            if lid is None or not (0 <= lid < self.WARP_PAD_ID_RANGE):
                continue
            locations[str(lid)] = PODIUM_CLASS.slot_codes(track, rung_keys)
        block["locations"] = locations
        return block

    def _resolve_itemsanity_checks(self) -> Dict[str, object]:
        """Ordered 22-code fan-out for the native use-time hook (#145).

        This is called only for an enabled seed.  Its order is the frozen
        item-major class order, resolving through the class index rather than
        rebuilding the code arithmetic at this second call site.
        """
        return {
            "enabled": True,
            "locations": [code for _name, code, _region in
                          ITEMSANITY_CLASS.created_locations(self.options)],
        }

    def fill_slot_data(self) -> Dict[str, object]:
        o = self.options
        # DERIVED shuffle_warp_pads (slot_data v3): the deprecated boolean option is
        # unwired; the real signal is "did any category participate" == the resolved
        # warp_pad_map being non-empty (set in create_regions as world.shuffle_warp_pads).
        # Kept in ctr_options for old-native log compatibility only.
        derived_shuffle = bool(getattr(self, "shuffle_warp_pads", False))
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
        custom_tracks = resolved_custom_tracks(self)
        schema = 8
        slot_data: Dict[str, object] = {
            "Seed": self.multiworld.seed_name,
            "Slot": self.multiworld.player_name[self.player],
            "TotalLocations": get_total_locations(self),
            # schema_version 6 (position-rung rework, shipped 0.1.x): the
            # podium_checks block changes SHAPE -- each per-track entry becomes a
            # 5-slot code array [held_1st, held_3rd, held_5th, finish_podium,
            # finish_any] (-1 = absent), replacing the v3-era {first,podium,any}
            # object. A native predating schema 6 must not read the old object, so
            # this is a native-version GATE (schema_version >= 6), shipped with the
            # #8 newer-schema warn/refuse. (v5 = oxide-final relic-goal mode/count;
            # v4 = relic-tier colour + goal-rework; v3 = podium + stage-2 padgate;
            # v2 = two-stage contract; v7 = gem_cup_legs; v8 = custom_tracks
            # support and the public Alpha6 pair gate, both unconditional.)
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
                "goal": self._legacy_goal_value(),
                "goal_oxide": o.oxide_goal.value,
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
                "shuffle_warp_pads": derived_shuffle,
                "warp_pad_shuffle_categories": sorted(o.warp_pad_shuffle_categories.value),
                "warp_pad_shuffle_grouping": o.warp_pad_shuffle_grouping.current_key,
                "shuffle_gems": bool(o.shuffle_gems.value),
                "shuffle_keys": bool(o.shuffle_keys.value),
                "warppad_unlock_mode": o.warppad_unlock_requirements.value,
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
                # QoL, additive (no schema bump): one-lap cup races. Native
                # json_int defaults the absent key to 0, so a pre-one-lap-cups
                # native (or an old seed on a new native) is exactly vanilla lap
                # counts. Pure pace setting -- never touches logic/fill/reachability.
                "one_lap_cups": bool(o.one_lap_cups.value),
                # DeathLink (issue #6): ADDITIVE keys, no schema bump. A native
                # predating these keys reads neither and DeathLink stays off (the
                # one_lap_cups precedent: absent additive key degrades to the 0/off
                # default). death_link is 0 off / 1 mask_reset / 2 any_hit; amnesty
                # is send-every-Nth (>=1). Native enables the "DeathLink" connection
                # tag and its send/receive plumbing only when death_link != 0.
                "death_link": o.death_link.value,
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
                    (getattr(self, "_ctr_relic_prog", None)
                     or self._relic_progression_map()).items()
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
                        self.location_name_to_id[name]
                        for name in self._ctr_relic_keep.get(relic_item, ()))
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
                "world_version": self.world_version.as_simple_string(),
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
                **progressive_capability.fill_slot_data(self),
                # Ruled capability-logic preference. Always emitted because
                # Universal Tracker must rebuild the same seven-track gates.
                "logic_difficulty": int(o.logic_difficulty.value),
                # Always emit this scalar.  It is additive tracker/diagnostic
                # metadata; option-off parity applies to generated content and
                # to the conditional top-level feature block below.
                "itemsanity": bool(o.itemsanity.value),
                # The wumpa family's two scalars (2026-08-10 ruling). Always
                # emitted, same convention as itemsanity and tizi_helper, and
                # DIAGNOSTIC / TRACKER ONLY: native drives both from received
                # items (a bundle hands over fruit on arrival, the ladder is the
                # count of copies received) and reads neither key.
                **wumpa_family.fill_slot_data(self),
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
                **characters.fill_slot_data(self),
            },
            "warp_pad_map": self._resolve_warp_pad_map(),
            "warp_pad_unlock": self._resolve_warp_pad_unlock(),
            "boss_garage_req": getattr(self, "boss_garage_req", {}),
            "podium_checks": self._resolve_podium_checks(),
            # Racer-locked pads (#54/#209, R8). Top-level block rather than a
            # 10th `Req` type on purpose -- a lock ANDs onto the pad's existing
            # stage-1 requirement instead of replacing it, and a native that
            # does not know this block simply never sees it rather than hitting
            # a `switch` default on an unevaluable type. See the characters.py
            # docstring and Contract 7h. Always present, `pads` empty when off.
            "racer_locks": characters.racer_lock_slot_data(self),
        }
        if legs_randomized:
            # Issue #166: the five cups' leg tracks (see _resolve_gem_cup_legs).
            # Emitted only when randomized -- absent means vanilla legs to both
            # native (advCupTrackIDs fallback) and UT (reconstruct falls back to
            # the vanilla table). HARD bump (schema 7 above), NOT the additive
            # no-bump precedent: an old native keeps loading the vanilla legs
            # while this seed's podium logic follows the shuffled map.
            slot_data["gem_cup_legs"] = self._resolve_gem_cup_legs()
        if o.itemsanity.value:
            # Additive under schema 7.  Omitted when off, so disabled seeds do
            # not gain a dormant 22-slot feature block.
            slot_data["itemsanity_checks"] = self._resolve_itemsanity_checks()
        if int(o.lettersanity.value) != 0:
            slot_data["lettersanity_checks"] = LETTERSANITY_CLASS.wire_block(o)
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
            slot_data["custom_tracks"] = custom_tracks_to_wire(custom_tracks)
        return slot_data

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

    def post_fill(self) -> None:
        """Prove the racer-lock self-lock invariant on the FILLED multiworld.

        Issue #209 names "a fill can never place a character's own unlock item
        behind a pad that requires that same character" as a thing that has to
        be built and proven, not asserted. With the unlock items as progression
        AP's fill already guarantees it; this re-derives it from the real
        placements so a future change to the lock selection cannot quietly
        break it. No-op when racer locks are off.
        """
        characters.verify_no_self_lock(self)

    def write_spoiler(self, spoiler_handle) -> None:
        """Record this seed's per-pad unlock requirements (stage 1 + stage 2) with
        tier-true item names. The spoiler previously logged NOTHING about pad
        requirements, so the 2026-07-08 relic-tier wire bug was invisible to a spoiler
        read; this section makes the exact gate native enforces auditable per seed.

        Also records a terminal fill-backstop firing (rollback-precollect) so a
        rescued seed is diagnosable. Written ONLY when the backstop fired: a
        non-fired seed adds nothing here, keeping it byte-identical to a build
        without the backstop (the fired: yes/no verdict is the line's presence)."""
        # Character phase (#54/#209): which racer this seed starts you as, and
        # which pads demand a specific racer. Both are per-seed DRAWS rather
        # than option values, so without this a spoiler read cannot tell you
        # what the seed actually decided.
        _player_name = self.multiworld.player_name[self.player]
        spoiler_handle.write(
            f"\n\nCTR starting character ({_player_name}): "
            f"{getattr(self, 'ctr_starting_character', '?')}\n")
        _locks = getattr(self, "ctr_racer_locks", {}) or {}
        if _locks:
            spoiler_handle.write(
                f"CTR racer-locked pads ({_player_name}):\n")
            for _pad, _character in sorted(_locks.items()):
                spoiler_handle.write(f"  {_pad}: requires {_character}\n")

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
        destination_rows = changed_pad_destination_rows(
            self._resolve_warp_pad_map(),
            getattr(self, "warp_pad_ids", {}),
        )
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
