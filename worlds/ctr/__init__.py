import logging
import json
import os
from typing import Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, CollectionState, WebWorld
from .Locations import get_location_names, get_total_locations
from .Items import load_item_table, item_prefix
from .Options import ctrAPOptions, Goal, FinalOxideUnlock, create_option_groups
from .Regions import create_regions
from .Rules import set_rules
from .Types import ctrAPItem


# The v1 trap set. ORDER IS LOAD-BEARING: it must match the native effect enum
# (AP_TrapEffect in ap/ap_traps.h) so item-id N maps to effect N on receipt. These
# names also define the trailing item ids in data/items.json (contiguous after
# Wumpa Fruit); the native received-item loop maps those ids -> AP_TrapReceive.
TRAP_ITEM_NAMES = [
    "Icy Road Trap",      # AP_TRAP_ICY
    "Low Gravity Trap",   # AP_TRAP_LOWGRAV
    "No Brakes Trap",     # AP_TRAP_USF_NOBRAKE
    "Forced Boost Trap",  # AP_TRAP_BOOST
    "First Person Trap",  # AP_TRAP_FIRSTPERSON
]


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

    # Item + Location mapping
    item_name_to_id = {
        item["name"]: (item_prefix + index)
        for index, item in enumerate(load_item_table())
    }
    location_name_to_id = get_location_names()

    def __init__(self, multiworld: "MultiWorld", player: int):
        super().__init__(multiworld, player)
        self.start_region = None

    # --- Oxide-final goal helpers (issue #23) ---

    # Relic item name per FinalOxideUnlock relic-count slider.
    _OXIDE_TIER_SLIDER = {
        "Sapphire Relic": "sapphire_relic_progression",
        "Gold Relic": "gold_relic_progression",
        "Platinum Relic": "platinum_relic_progression",
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

    def _relic_slider_for(self, relic_item: str) -> int:
        return getattr(self.options, self._OXIDE_TIER_SLIDER[relic_item]).value

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

    def generate_early(self) -> None:
        """Generation-time progression guard for the Oxide-final goal (issue #23).

        When the goal IS Oxide's Final Challenge, the relic tiers that satisfy the
        configured mode+count must be able to supply the goal as PROGRESSION
        (visible to fill / beatability). A tier whose `*_relic_progression` is
        `never` (0) is opted fully out of AP progression by the player; if the
        goal can only be satisfied by such tiers, the goal would be invisible to
        AP (the stranding class in the report). Error clearly here instead of
        emitting a world whose goal AP cannot see -- respecting the per-tier
        sliders rather than silently forcing a tier back on."""
        from Options import OptionError
        if self.options.goal.value != Goal.option_oxidefinal:
            return
        n = self.options.oxide_final_challenge_relic_count.value
        tiers = self._oxide_goal_tiers()
        # A satisfying tier can supply the goal exactly when this seed classifies
        # it as PROGRESSION (its 18 relics are then reachable + visible to fill).
        # _relic_progression_map is the single source of that truth and is already
        # warp-pad-mode-aware: randomized mode keeps ALL tiers progression (slider
        # only governs pinning, not classification), while vanilla mode makes a
        # goal tier progression only when its slider > 0. Basing the guard on the
        # same map means it fires exactly when the goal really would be invisible.
        prog = self._relic_progression_map()
        prog_tiers = [t for t in tiers if prog.get(t, False)]
        # N <= 18 and each progression tier supplies 18 reachable relics, so one
        # progression tier satisfies single-tier / any_relic_type; total_relics
        # needs the summed progression supply to reach N.
        if self.options.oxide_final_challenge_unlock.value \
                == FinalOxideUnlock.option_total_relics:
            ok = 18 * len(prog_tiers) >= n
        else:
            ok = len(prog_tiers) >= 1
        if not ok:
            mode_key = self.options.oxide_final_challenge_unlock.current_key
            sliders = ", ".join(
                f"{self._OXIDE_TIER_SLIDER[t]}={self._relic_slider_for(t)}"
                for t in tiers)
            raise OptionError(
                f"CTR goal 'oxidefinal' with Oxide's Final Challenge Unlock "
                f"'{mode_key}' needs {n} relic(s) from {tiers}, but no satisfying "
                f"tier is generated as progression in this seed ({sliders}); in "
                f"vanilla warp-pad mode a tier whose *_relic_progression is "
                f"'never' (0) is opted out of progression, so the goal would be "
                f"unreachable. Raise one of those sliders above 0, switch to "
                f"randomized warp-pad unlock, or change the goal, mode, or count.")

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
        not run (caller treats None as 'keep two-stage')."""
        try:
            from BaseClasses import MultiWorld as _MW, CollectionState as _CS
            from worlds.AutoWorld import call_all as _call_all
            from Fill import distribute_items_restrictive as _dist
            seed = self.multiworld.seed
            pmw = _MW(1)
            pmw.game[1] = self.game
            pmw.player_name = {1: self.multiworld.player_name[self.player]}
            pmw.set_seed(seed)
            pw = type(self)(pmw, 1)
            pmw.worlds = {1: pw}
            pw.options = self.options  # identical option object -> identical rolls
            for step in ("generate_early", "create_regions", "create_items",
                         "set_rules", "connect_entrances", "generate_basic"):
                _call_all(pmw, step)
            pmw.state = _CS(pmw)
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
        idx = item_id - item_prefix
        classification = load_item_table()[idx]["classification"]
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
        * Vanilla mode (mode 0) -- from data/world.json, the ONLY vanilla gates that
          name a relic are both Sapphire: the Slide Coliseum pad (has('Sapphire
          Relic', 10)) and N. Oxide's Final Challenge (has('Sapphire Relic', 18)).
          Gold/Platinum gate no location, and since goal 2 ("everythingplusone")
          was dropped no surviving goal's completion_condition reads a
          relic count above Sapphire either. So:
            - Sapphire: progression iff accessibility == full (both Sapphire-gated
              LOCATIONS must be reachable) OR the goal makes you reach + win Oxide's
              Final Challenge (oxidefinal). Else useful.
            - Gold: never progression in vanilla mode -- no location gates on it and,
              with goal 2 dropped, no goal completion depends on it. Useful.
            - Platinum: never progression in vanilla mode (no location, no goal
              completion depends on it).
        """
        o = self.options
        prog = {"Sapphire Relic": True, "Gold Relic": True, "Platinum Relic": True}
        if o.warppad_unlock_requirements.value != 0:
            return prog  # randomized modes: any pad may gate on any relic tier
        goal = o.goal.value
        access_full = o.accessibility.value == 0  # Accessibility.option_full == 0
        # Base vanilla-mode classification: the ONLY vanilla LOCATION gate that
        # names a relic is Sapphire (Slide Coliseum has('Sapphire Relic', 10)),
        # so Sapphire is progression exactly when every location must be reachable
        # (accessibility: full). Gold/Platinum gate no vanilla location.
        prog["Sapphire Relic"] = access_full
        prog["Gold Relic"] = False
        prog["Platinum Relic"] = False
        # Oxide-final goal (issue #23): the relic tiers that satisfy the configured
        # mode+count must be progression so fill, the spoiler playthrough, and
        # beatability chase the REAL goal (not the old hard-coded 18 Sapphire).
        # Respect the per-tier sliders -- a satisfying tier at `never` (0) stays
        # out and is caught by generate_early's guard rather than silently forced.
        if goal == Goal.option_oxidefinal:
            # Sapphire is progression on ANY oxidefinal seed (mode-independent).
            # The two vanilla relic-count LOCATION gates are BOTH sapphire (Slide
            # Coliseum has('Sapphire Relic', 10); N. Oxide's Final Challenge has 18),
            # so once the goal makes any relic tier progression, fill may place a
            # progression relic behind the Slide Coliseum sapphire gate -- Sapphire
            # must stay progression to keep those locations reachable. This mirrors
            # the pre-#23 goal, which was itself 18 Sapphire and always set this.
            prog["Sapphire Relic"] = True
            for tier in self._oxide_goal_tiers():
                if self._relic_slider_for(tier) > 0:
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

    def _install_goal(self, player: int) -> None:
        """Set this seed's completion condition and lay any companion goal-tracking
        events (Spec §5, revised 2026-07-01).

        Goals 0/1 (Oxide, Oxide-final) are now real, coded, pool-filled locations
        (data/locations.json codes 35011104 / 35011105); each is PAIRED with a code-null
        companion event locking a distinct flag the completion condition reads. Goal 3
        (All Bosses) checks 4 code-null companion events paired with the 4 real Boss
        Race locations (35011100-35011103), replacing the wrong state.has(Trophy, 16)
        proxy -- trophies only UNLOCK the garages, they do not mean the bosses were
        beaten. Goal 4 (All Gems) keeps gemgoal()'s singleton-gem check, which is safe
        by construction (a unique item cannot false-positive from a duplicate) and needs
        no companion event."""
        mw = self.multiworld
        goal = self.options.goal.value

        if goal == Goal.option_oxide:
            flag = self._add_goal_event(
                "N. Oxide Garage", "N. Oxide's Challenge Cleared", "has('Key', 4)")
            mw.completion_condition[player] = (
                lambda state, f=flag: state.has(f, player))
        elif goal == Goal.option_oxidefinal:
            # The companion event is the seed's terminal win-flag; its win-trigger
            # is reaching Oxide's garage (Key 4). The relic requirement that turns
            # Oxide's Challenge into the FINAL Challenge (issue #23) is ANDed into
            # completion_condition below from the configured
            # oxide_final_challenge_unlock mode + count -- so fill, the spoiler
            # playthrough, and beatability chase the real goal instead of the old
            # hard-coded 18 Sapphire. The satisfying tiers are made progression by
            # _relic_progression_map, and generate_early has already errored out on
            # any mode/count/slider combo that could not reach the goal.
            flag = self._add_goal_event(
                "N. Oxide Garage", "N. Oxide's Final Challenge Cleared",
                "has('Key', 4)")
            relic_rule = self._oxide_final_relic_rule()
            mw.completion_condition[player] = (
                lambda state, f=flag, r=relic_rule:
                    state.has(f, player) and r(state))
        elif goal == Goal.option_allbosses:
            # Pair each real Boss Race location with a companion event of the same
            # reachability. The Boss Race location's own rule is "True"; the garage
            # door's trophy gate (add_boss_garage_rules 4/8/12/16) is what actually
            # gates reaching it, so a "True" event in the same region inherits that gate.
            # These per-boss "personally won" flags are also the machinery BUG-D's
            # future modes-0/1 reconciliation needs (see Options.BossGarageRequirements).
            boss_events = [
                ("Ripper Roo Garage", "Ripper Roo Boss Race Won"),
                ("Papu Papu Garage", "Papu Papu Boss Race Won"),
                ("Komodo Joe Garage", "Komodo Joe Boss Race Won"),
                ("Pinstripe Garage", "Pinstripe Boss Race Won"),
            ]
            flags = [self._add_goal_event(r, e, "True") for r, e in boss_events]
            mw.completion_condition[player] = (
                lambda state, fs=flags: all(state.has(f, player) for f in fs))
        elif goal == Goal.option_allgemcups:
            self.gemgoal(player)

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

        self._install_goal(player)

        # --- Relic-tier progression sliders (pinned-vanilla lock per the slider roll) ---
        # For each tier, roll each of its 18 time-trial locations: with `chance`%
        # it stays progression-eligible, else pin that tier's vanilla relic there
        # (place_locked_item -> out of the multiworld pool). Track n_locked per tier
        # so the general pool below creates (18 - n_locked) of that relic, keeping
        # item count == location count (same invariant the gemgoal pass relies on).
        _relic_tiers = [
            ("Sapphire", "Sapphire Relic", self.options.sapphire_relic_progression.value),
            ("Gold", "Gold Relic", self.options.gold_relic_progression.value),
            ("Platinum", "Platinum Relic", self.options.platinum_relic_progression.value),
        ]
        # Platinum relic inclusion is governed SOLELY by the Platinum Relic
        # Progression slider (slider = 0 already means "platinum relics not
        # shuffled / pinned vanilla").

        # NO two-stage reward pinning (the OPEN model): relic Time Trials and CTR
        # Token Challenges flow through the normal pool + the relic sliders, the same
        # on every randomized seed as on main. The sliders therefore govern ALL 18
        # Time Trial locations per tier again (no 16/18 seizure). Stage-2 gate
        # solvability comes from the sphere-search invariant + the per-pad relax
        # fallback, not from locking these locations out of the pool.
        # Comfort guard (Icebound force_vanilla_turbotrack): when warp-pad unlock
        # requirements are vanilla and gems are not shuffled, Turbo Track keeps its
        # vanilla 5-gem entry gate (reachable only after every Gem Cup -> all 5 gems).
        # Pin Turbo Track's three relic Time Trial rewards to their vanilla relics so
        # no required item is ever forced behind that tedious chain. The randint draw
        # below is taken unconditionally (only the pin DECISION is forced) so the RNG
        # stream is identical to the unguarded path -- guard-inactive seeds are byte
        # for byte unchanged. Pure pin -> removes progression placement options ->
        # can only maintain or improve fillability (item/location count stays balanced
        # via _relic_locked). The flag is set in create_regions.
        _force_vanilla_tt = getattr(self, "_ctr_force_vanilla_turbotrack", False)
        _TT_RELIC_LOCS = {
            "Turbo Track: Sapphire Time Trial",
            "Turbo Track: Gold Time Trial",
            "Turbo Track: Platinum Time Trial",
        }
        _relic_locked = {}  # relic item name -> count pinned out of the pool
        for _tier_label, _relic_item, _chance in _relic_tiers:
            _suffix = f": {_tier_label} Time Trial"
            _locs = sorted(n for n in self.location_name_to_id
                           if n.endswith(_suffix))
            _n = 0
            for _loc_name in _locs:
                _roll_pin = self.random.randint(0, 99) >= _chance  # (100-chance)% pin
                _force_pin = _force_vanilla_tt and _loc_name in _TT_RELIC_LOCS
                if _force_pin or _roll_pin:
                    mw.get_location(_loc_name, player).place_locked_item(
                        self.create_item(_relic_item)
                    )
                    _n += 1
            _relic_locked[_relic_item] = _relic_locked.get(_relic_item, 0) + _n

        # --- Gem & Key placement toggles (item #5) ---
        # Default OFF = pinned vanilla (each Gem locked to its Gem Cup, each Key
        # locked to its Boss Race -> out of the multiworld pool). ON = the item
        # enters the shuffled pool and its vanilla location becomes a normal check.
        # Track n_locked per item name so the general pool below creates
        # (count - n_locked) of it, keeping item count == location count.
        _GEM_GOAL = self.options.goal.value == Goal.option_allgemcups
        _gems_locked: Dict[str, int] = {}
        _keys_locked: Dict[str, int] = {}
        _vmap = json.loads(
            pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
        )["ShuffleOptions"]

        # Gems: pin to gem-cup locations when shuffle_gems is OFF. For the All-Gems
        # goal with shuffle off, gemgoal() already placed them (and
        # place_locked_item on an already-filled location would raise), so skip the
        # placement here for that goal -- the pool exclusion below still applies.
        # All-Gems + shuffle ON pins nothing anywhere: the gems ride the pool.
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

        # --- Create general item pool ---
        # For the all-gem-cups goal, gemgoal() LOCKS the 5 gems at the gem-cup
        # locations, so adding the same 5 gems from the item table again makes them
        # redundant progression items: the pool then exceeds the available
        # locations (gemgoal also consumes 5 cup locations) -> FillError ("N more
        # progression items than locations") and an item/location count mismatch.
        # Exclude the gems from the general pool for that goal (they are the goal
        # items, placed at the cups). Other goals keep gems in the pool (Turbo Track's
        # vanilla 5-gem gate needs them findable) UNLESS shuffle_gems pinned them, in
        # which case _gems_locked subtracts them.
        _GEMS = {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"}
        for item in load_item_table():
            # All-Gems goal: exclude the gems from the general pool ONLY when
            # gemgoal() locked them onto their cups (shuffle_gems off) -- adding
            # them again would overflow the pool (see the note above). With
            # shuffle_gems ON the gems stay in the pool: they are the goal items,
            # hidden wherever the fill puts them (2026-07-15 ruling).
            if _GEM_GOAL and not self.options.shuffle_gems.value \
                    and item["name"] in _GEMS:
                continue
            count = item["count"]
            if item["name"] in _relic_locked:                         # slider-pinned relics
                count = max(0, count - _relic_locked[item["name"]])
            if item["name"] in _gems_locked:                          # gems pinned vanilla
                count = max(0, count - _gems_locked[item["name"]])
            if item["name"] in _keys_locked:                          # keys pinned vanilla
                count = max(0, count - _keys_locked[item["name"]])
            if count > 0:
                for _ in range(count):
                    pool.append(self.create_item(item["name"]))

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
        unfilled = len(mw.get_unfilled_locations(self.player))
        n_filler = max(0, unfilled - len(pool))
        # Trap fill: replace trap_fill_percentage% of the filler slots with traps,
        # drawn UNIFORMLY across the 5 trap effects. Traps are non-progression, so
        # this never changes reachability at any value. DEFAULT 0 IS GENERATION-
        # NEUTRAL BY CONSTRUCTION: the else branch is byte-identical to the old
        # Wumpa-only fill and no world.random draw is taken, so a default seed's
        # spoiler + slot_data are unchanged. (Per-trap weighting is a flagged v2
        # retune -- v1 is uniform.)
        trap_pct = self.options.trap_fill_percentage.value
        if trap_pct > 0 and n_filler > 0:
            n_traps = (n_filler * trap_pct) // 100
            for _ in range(n_traps):
                pool_item = self.create_item(self.random.choice(TRAP_ITEM_NAMES))
                mw.itempool.append(pool_item)
            mw.itempool += [self.create_filler()
                            for _ in range(n_filler - n_traps)]
        else:
            mw.itempool += [self.create_filler() for _ in range(n_filler)]

        # NOTE: an earlier density-adaptive force-collapse was removed -- CTR's pool
        # is ~98% progression in EVERY config (only ~1 filler item), so a density
        # signal cannot distinguish a tight seed from a normal one and would collapse
        # two-stage on virtually all seeds (defeating "two-stage is the DEFAULT
        # experience"). Solvability is instead held by the sphere-search invariant,
        # the per-pad relax-to-tier-1 fallback + baseline collapse roll, the stage
        # count ceilings, the slider-aware relic filter, and the min-2 bootstrap
        # breadth -- all proven to fill 0/5000 randomized two-stage-active configs
        # while keeping real, distinct tier-2 gates on the great majority of pads.

    def gemgoal(self, player):
        """All-Gems goal: completion = own all 5 Gems. With Shuffle Gems OFF the
        gems are additionally locked onto their own Gem Cup locations (win every
        cup); with Shuffle Gems ON they stay in the multiworld pool and the goal
        is a hunt for wherever the fill hid them (create_items keeps them in the
        pool for this goal, and native's goal 4 already counts RECEIVED gems, so
        both placements complete identically)."""
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

        mw.completion_condition[player] = lambda state: all(
            state.has(g, player, 1)
            for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
        )

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
                # The Key-3 Cups Room hub gate is enforced separately (native hub
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
        """Podium placement checks (feat/podium-checks) for the native fan-out.

        {"enabled": bool, "any_position": bool,
         "locations": {"<levelID>": {"first": <code|null>,
                                     "podium": <code|null>,
                                     "any": <code|null>}, ...}}

        The placement listener (feat/podium-listener) reads this: at the
        finish-line capture for track=<levelID> with final placement p, it sends
        the rung location codes per the nesting rule -- p==1 -> first+podium+any;
        p in {2,3} -> podium+any; p>=4 -> any only. Codes are AP location ids; a
        rung not present in this seed (any-position off, or the whole feature off)
        is null and native must skip it. Keyed by physical race-pad LevelID 0..15,
        which equals the trophy-race track and matches the [AP RACE] track field.
        Only the 16 standard trophy races carry podium checks (boss/token/relic/
        crystal have no genuine multi-position finish).

        NOTE: podium is additive/safe-degrading (a native build without podium
        support simply ignores this block and sends no podium checks). It did NOT
        drive a schema_version bump of its own -- the v4 bump is the relic-tier
        colour change (fill_slot_data), independent of podium. A native predating
        podium still degrades safely on a v4 seed for this block specifically.
        """
        from .Locations import CTR_LOCATION_IDS
        from .podium import TROPHY_TRACKS, enabled_rung_keys, location_name
        enabled = bool(self.options.podium_placement_checks.value)
        any_pos = bool(self.options.podium_any_position_rung.value)
        block: Dict[str, object] = {
            "enabled": enabled,
            "any_position": enabled and any_pos,
            "locations": {},
        }
        if not enabled:
            return block
        rung_keys = enabled_rung_keys(any_pos)
        pad_ids = getattr(self, "warp_pad_ids", {})
        track_to_lid = {
            pad_name[: -len(" Warp Pad")]: meta["level_id"]
            for pad_name, meta in pad_ids.items()
            if pad_name.endswith(" Warp Pad")
        }
        locations: Dict[str, Dict[str, object]] = {}
        for track in TROPHY_TRACKS:
            lid = track_to_lid.get(track)
            if lid is None or not (0 <= lid < self.WARP_PAD_ID_RANGE):
                continue
            entry: Dict[str, object] = {"first": None, "podium": None, "any": None}
            for rung_key in rung_keys:
                entry[rung_key] = CTR_LOCATION_IDS.get(location_name(track, rung_key))
            locations[str(lid)] = entry
        block["locations"] = locations
        return block

    def fill_slot_data(self) -> Dict[str, object]:
        o = self.options
        # DERIVED shuffle_warp_pads (slot_data v3): the deprecated boolean option is
        # unwired; the real signal is "did any category participate" == the resolved
        # warp_pad_map being non-empty (set in create_regions as world.shuffle_warp_pads).
        # Kept in ctr_options for old-native log compatibility only.
        derived_shuffle = bool(getattr(self, "shuffle_warp_pads", False))
        slot_data: Dict[str, object] = {
            "Seed": self.multiworld.seed_name,
            "Slot": self.multiworld.player_name[self.player],
            "TotalLocations": get_total_locations(self),
            # schema_version 5 (2026-07-16, issue #23): oxide_final_unlock grows
            # from a 0/1 flag into a relic-goal MODE (0 sapphire / 1 gold / 2
            # platinum / 3 any-single-type / 4 total) plus a new oxide_final_count
            # (1-18). This is a native-version GATE: a v4 native reads
            # oxide_final_unlock==1 as the removed "18 gold AND 18 platinum" rule
            # and has no count field, so a v5 seed's Oxide-final gate would be
            # mis-enforced -- it must check schema_version >= 5. Ships with the
            # newer-schema warn/refuse (issue #8). (v4 = relic-tier colour +
            # goal-rework; v3 = podium + stage-2 padgate; v2 = two-stage contract.)
            "schema_version": 5,
            "ctr_options": {
                "schema_version": 5,
                "goal": o.goal.value,
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
            },
            "warp_pad_map": self._resolve_warp_pad_map(),
            "warp_pad_unlock": self._resolve_warp_pad_unlock(),
            "boss_garage_req": getattr(self, "boss_garage_req", {}),
            "podium_checks": self._resolve_podium_checks(),
        }
        return slot_data

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

    def write_spoiler(self, spoiler_handle) -> None:
        """Record this seed's per-pad unlock requirements (stage 1 + stage 2) with
        tier-true item names. The spoiler previously logged NOTHING about pad
        requirements, so the 2026-07-08 relic-tier wire bug was invisible to a spoiler
        read; this section makes the exact gate native enforces auditable per seed.

        Also records a terminal fill-backstop firing (rollback-precollect) so a
        rescued seed is diagnosable. Written ONLY when the backstop fired: a
        non-fired seed adds nothing here, keeping it byte-identical to a build
        without the backstop (the fired: yes/no verdict is the line's presence)."""
        if getattr(self, "_ctr_backstop_fired", False):
            player_name = self.multiworld.player_name[self.player]
            items = getattr(self, "_ctr_backstop_items", [])
            mode = getattr(self, "_ctr_backstop_mode", "?")
            spoiler_handle.write(
                f"\n\nCTR fill backstop FIRED ({player_name}, {mode} mode): "
                f"precollected {len(items)} progression item(s) into starting "
                f"inventory so the greedy fill converges -- {', '.join(items)}. "
                f"Seed stays fully reachable; this is a diagnosable rescue.\n")
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

