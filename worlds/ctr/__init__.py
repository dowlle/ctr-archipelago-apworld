import logging
import json
from typing import ClassVar, Dict, List

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from Options import OptionError
from worlds.AutoWorld import World, CollectionState, WebWorld
from .elastic_bounds import CTRSettings
from .Locations import CTR_LOCATION_CLASSES, get_location_names
from .item_groups import build_item_name_groups, merge_item_groups
from .location_groups import build_location_name_groups
from .Items import load_item_table
from .itemsanity import ITEM_NAMES
from .custom_lettersanity import CUSTOM_LETTER_ITEM_DATA
from .cortex_vortex import LETTER_ITEM_DATA as CORTEX_VORTEX_LETTER_ITEM_DATA
from .minted_items_030 import ITEM_DATA as MINTED_030_ITEM_DATA, MINTED_TRAP_ITEM_NAMES
from .named_tracks import (NAMED_TRACKS, NAMED_TRACK_ITEM_DATA,
                           validate_tracks as _validate_named_tracks)
from .Options import ctrAPOptions, create_option_groups
from . import characters
from . import warp_pad_rules
from . import version
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

# SURFACE_ITEM_NAMES (the comfort-only #14/#15 pack) now lives in Items, beside
# create_item; re-exported because it was importable from the package before.
from . import Items
from .Items import SURFACE_ITEM_NAMES
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
    # Location groups (#536): the class-declared ones plus the track and
    # check-kind groups built from the registries; see location_groups.py.
    location_name_groups = build_location_name_groups(
        location_name_to_id, CTR_LOCATION_CLASSES, item_name_to_id)

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
    # Issue #536: Characters, Stats (+ one per racer), CTR Letters, Filler,
    # Ignore Ground Types. Built from the registries; see item_groups.py.
    item_name_groups = merge_item_groups(
        item_name_groups, build_item_name_groups(_item_data_by_name))

    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)
        self.start_region = None
        # Issue #179: names _exclude_goal_location has excluded so far this
        # seed, appended at the call site rather than re-derived elsewhere --
        # elastic_bounds.goal_excluded_location_reserve reads this instead of
        # restating which goals exclude a location.
        self._goal_excluded_location_names: List[str] = []

    # --- Universal Tracker support (issue #29) ---

    @staticmethod
    def interpret_slot_data(slot_data: Dict[str, object]) -> Dict[str, object]:
        """Universal Tracker hook. Returning a truthy value tells UT to re-generate
        this world with the value placed in multiworld.re_gen_passthrough[game]. We
        return the slot_data verbatim: generate_early rebuilds the seed from its
        content_plan block (content_plan.restore), so the re-generated world's logic
        graph is identical to the connected seed's instead of re-rolling a divergent
        one."""
        return slot_data

    def generate_early(self) -> None:
        """Every seed is a content plan (one generator). Universal Tracker
        rebuilds the connected seed's plan from its slot_data; a room without
        one comes from v0.2.x and is refused with the client's sentence."""
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {}).get(self.game)
        from . import content_plan
        content_plan.swap_in_bundled_cortex(self)
        if passthrough:
            if "content_plan" not in passthrough:
                raise OptionError("CTR: This room was made with v0.2.x. Play it on the v0.2.4 client.")
            content_plan.restore(self, passthrough)
        else:
            content_plan.generate(self)

    def create_regions(self):
        from . import content_plan
        content_plan.create_regions(self)

    @classmethod
    def stage_modify_multidata(cls, multiworld, multidata):
        from .custom_track_datapackage import embed_track_names
        embed_track_names(multiworld, multidata, cls.game)

    def set_rules(self):
        from . import content_plan
        content_plan.set_rules(self)
        from .win_logic import snapshot_rules
        snapshot_rules(self)

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
        sphere0_guard.mark_early_opener(self)
        sphere0_guard.mark_early_boost(self)
        # Plando on content plans (#133 PR 4f): Main.py has parsed the
        # blocks; check them before plando runs.
        from . import content_item_pool
        content_item_pool.check_planned_blocks(self)

    def pre_fill(self) -> None:
        """Item links and plando have run (#133 PR 4f): audit the created copies
        and pay for explicit plando items with this world's filler, then open a
        narrow start (sphere0_guard.bootstrap_start). Solo seeds with manual
        warp pad rules get a fill check, so a dead end names the rules."""
        # Universal Tracker (issue #29): under a fake generation there is no real
        # fill to protect. Reachability is fixed by the rules reconstructed from
        # slot_data, and the server supplies the real item placements.
        if getattr(self.multiworld, "generation_is_fake", False):
            return
        from . import content_item_pool
        self.ctr_framework_accounting = content_item_pool.settle_after_plando(self)
        # Narrow starts (0.3.0 review finding 1): open the start before
        # the fill, see sphere0_guard.bootstrap_start.
        from . import sphere0_guard
        sphere0_guard.bootstrap_start(self)
        # Independent supply never uses automatic progression starts. Manual
        # pad rules still get the solo fill check, so a dead end names them.
        if warp_pad_rules.fixed(self) and len(self.multiworld.worlds) == 1:
            self._manual_rules_fill_check()

    def post_fill(self) -> None:
        """Content plans (#133 PR 4f): refuse a fill that dropped a created
        copy or moved one to the start inventory."""
        if not getattr(self.multiworld, "generation_is_fake", False):
            from . import content_item_pool
            content_item_pool.audit_before_output(self)

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

    # -- fill simulation machinery (manual warp pad rules fill check) --
    #
    # distribute_items_restrictive mutates exactly: location placements
    # (location.item / item.location / location.locked, incl. lock_later),
    # multiworld.random (shuffles), and -- only under panic_method=
    # 'start_inventory' -- precollected_items + state (push_precollected).
    # It never reassigns multiworld.itempool or early_items (it works on
    # sorted local copies), but both are snapshotted anyway as cheap insurance.
    # Its accessibility step also wraps location.item_rule on unreachable
    # locations (inaccessible_location_rules), so item rules are restored too.

    def _fill_snapshot(self) -> dict:
        mw = self.multiworld
        # Race mode (`--race`, host.yaml `race: 1`) makes multiworld.random a
        # SystemRandom, which has no state to save (A4-8 M01). Its draws are not
        # reproducible anyway, so there is nothing to restore: the check still
        # runs, but a green replay no longer promises the same real fill.
        try:
            rng = mw.random.getstate()
        except NotImplementedError:
            rng = None
        return {
            "rng": rng,
            "state": mw.state.copy(),
            "early": {p: dict(d) for p, d in mw.early_items.items()},
            "local_early": {p: dict(d) for p, d in mw.local_early_items.items()},
            "precollected_len": {p: len(v) for p, v in mw.precollected_items.items()},
            "placements": [(loc, loc.item, loc.locked) for loc in mw.get_locations()],
            # inaccessible_location_rules (Fill.py) wraps item_rule on
            # locations the trial finds unreachable (A4-8 review).
            "item_rules": [(loc, loc.item_rule) for loc in mw.get_locations()],
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
        for loc, rule in snap["item_rules"]:
            loc.item_rule = rule
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
        if snap["rng"] is not None:
            mw.random.setstate(snap["rng"])

    def _rollback_simulate_fill(self, panic: str) -> bool:
        """Run the REAL upcoming fill on the REAL multiworld, then roll every
        mutation back. True = the fill goes green (and, since the RNG state is
        restored, the real fill will replay it identically; in race mode the
        RNG has no state, so the real fill draws again)."""
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

    # --- Item creation ---

    def create_item(self, name: str) -> "ctrAPItem":
        return Items.create_item(self, name)

    def create_event(self, event: str):
        return ctrAPItem(
            name=event,
            classification=ItemClassification.progression_skip_balancing,
            code=None,
            player=self.player,
        )

    def create_filler(self) -> Item:
        # Standard AP World signature: the core itself calls create_filler() with
        # no arguments on the panic_method='start_inventory' paths (Fill.py).
        return self.create_item("Wumpa Fruit")

    def create_items(self):
        from . import content_plan
        content_plan.create_items(self)

    def fill_slot_data(self) -> Dict[str, object]:
        return slot_data.fill_slot_data(self)

    def extend_hint_information(self, hint_data: Dict[int, Dict[int, str]]) -> None:
        """Issue #52: annotate each location with the physical warp pad that loads
        its track, so a hint reads "... at the Sewer Speedway pad" (content_plan.
        hint_text). Per-seed multidata channel only: it touches no ids, names,
        fill or reachability."""
        from . import content_plan
        text = content_plan.hint_text(self.ctr_content_plan)
        if text:
            hint_data[self.player] = text

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
        # Content plans (#133 PR 4f): no item of any slot is dropped.
        from . import content_item_pool
        content_item_pool.audit_room_before_output(multiworld)

    def write_spoiler(self, spoiler_handle) -> None:
        """Record this seed's content plan, its boss encounters, plando and item
        link accounting, and the Hit Character Key fallback."""
        spoiler_handle.write("\nCTR independent content/item plan:\n")
        json.dump(self.ctr_content_plan, spoiler_handle, indent=2)
        spoiler_handle.write("\nOriginal from-pool starts: " + repr(self.ctr_content_original_starts) + "\n")
        if getattr(self, "ctr_cortex_swap", None):
            spoiler_handle.write("CTR Cortex Vortex: the downloaded copy (" + ", ".join(self.ctr_cortex_swap)
                                 + ") was replaced by the Cortex Vortex that comes with CTR AP "
                                 "(cortex_vortex_track " + self.ctr_cortex_swap_mode + ").\n")
        # Boss opponent and kit shuffle on content plans.
        from . import content_bosses
        _lines = content_bosses.spoiler_lines(self.ctr_content_plan)
        if _lines:
            spoiler_handle.write(f"CTR boss encounters ({self.multiworld.player_name[self.player]}):\n")
            for _line in _lines:
                spoiler_handle.write(f"  {_line}\n")
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
        # Hit Character Key fallback (#133 PR 4d): nothing when Hit Character
        # is off.
        for _guest, _keys in sorted((getattr(self, "ctr_hit_character_fallback", {}) or {}).items(),
                                    key=lambda item: (item[1], item[0])):
            spoiler_handle.write(
                f"CTR Hit Character ({self.multiworld.player_name[self.player]}): "
                f"{characters.CHARACTER_ID_TO_NAME[int(_guest)]} has no unlock race in this seed and "
                f"joins races at {_keys} {'Key' if _keys == 1 else 'Keys'}.\n")

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)
