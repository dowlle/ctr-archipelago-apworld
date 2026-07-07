import logging
import json
import os
from typing import Dict, List
import pkgutil

from BaseClasses import MultiWorld, Item, Tutorial, ItemClassification
from worlds.AutoWorld import World, CollectionState, WebWorld
from .Locations import get_location_names, get_total_locations
from .Items import load_item_table, item_prefix
from .Options import ctrAPOptions, Goal
from .Regions import create_regions
from .Rom import CrashTeamRacingProcedurePatch, write_tokens
from .Rules import set_rules
from .Types import ctrAPItem


class ctrAPWeb(WebWorld):
    theme = "Party"

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

    def create_regions(self):
        create_regions(self)

    def set_rules(self):
        set_rules(self)

    def pre_fill(self) -> None:
        """Per-seed fillability guards -- one branch per warp-pad fill mode.

        RANDOMIZED-MODE BRANCH: two-stage guard (Dowlle: "a pad's tier 2 MAY collapse
        if a seed needs it FOR GENERATION").

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

        VANILLA-MODE BRANCH: tight-fill backstop (lever 3, design note 2026-07-03;
        Spec 6.2a) -- see _vanilla_fill_backstop. Solo generations only."""
        if not getattr(self, "_ctr_two_stage_active", False):
            if (self.options.warppad_unlock_requirements.value == 0
                    and len(self.multiworld.worlds) == 1):
                self._vanilla_fill_backstop()
            return
        if getattr(self, "_ctr_force_collapse_stage2", False):
            return  # already collapsed
        fillable = self._probe_two_stage_fillable()
        if fillable is False:
            self._ctr_force_collapse_stage2 = True
            # Overwrite the stage-2 access rules with the collapsed (plain
            # can_reach Trophy Race) form; fill_slot_data also emits type-0 stage 2.
            from .Rules import add_time_trial_and_ctr_requirements
            add_time_trial_and_ctr_requirements(self, self.player)

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

    _VANILLA_BACKSTOP_MAX_ROUNDS = 40

    def _vanilla_fill_backstop(self) -> None:
        """Vanilla-mode tight-fill backstop (lever 3, design note 2026-07-03).

        Levers 1+2 (honest relic classification + vanilla early-Keys) shrink the
        vanilla tight-fill FillError class (Spec 6.2a) to a ~0.1-0.2% residual on
        relic-starved slider corners. The residual is pure placement-ordering luck:
        pool == locations on every seed, and a failing seed is fully beatable --
        greedy fill_restrictive just corners itself. This backstop removes the
        residual exactly, by REPLAYING the upcoming fill rather than approximating
        it:

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

        SOLO ONLY (enforced by the caller): with other worlds present, their
        pre_fill hooks may run after ours and consume multiworld.random, breaking
        replay fidelity -- and mixed pools relax CTR's tightness anyway. Vanilla
        multiworld seeds keep the (tiny) pre-existing residual, per Spec 6.2a.

        Fail-open: any unexpected error leaves generation to proceed as if the
        backstop did not exist. CTR_PROBE_LOG_ONLY=1 logs the would-fire verdict
        without intervening (acceptance-sweep instrumentation).

        No gate, rule, slot_data, or schema change: the only effect on a fired
        seed is items moved to starting inventory (the player begins with them
        collected), which never removes reachability."""
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
            for _round in range(self._VANILLA_BACKSTOP_MAX_ROUNDS):
                if self._rollback_simulate_fill(panic) is True:
                    converged = True
                    break
                if log_only:
                    logging.info("[CTR] vanilla fill backstop LOG-ONLY: simulated "
                                 "fill dead-ends; would intervene.")
                    return
                stranded = self._rollback_enumerate_stranded()
                if not stranded:
                    logging.warning(
                        "[CTR] vanilla fill backstop: simulated fill dead-ends but "
                        "no stranded items identified; leaving the seed unchanged "
                        "(fail-open).")
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
                            "[CTR] vanilla fill backstop: stranded item %r not in "
                            "the real itempool; stopping intervention (fail-open).",
                            name)
                        return
            if converged and fired:
                logging.info(
                    "[CTR] vanilla tight-fill backstop fired: precollected %d "
                    "item(s) (%s); simulated fill green -- seed fully beatable "
                    "from starting inventory.", len(fired), ", ".join(fired))
            elif not converged:
                logging.warning(
                    "[CTR] vanilla fill backstop: no convergence after %d rounds "
                    "(precollected so far: %s); generation proceeds.",
                    self._VANILLA_BACKSTOP_MAX_ROUNDS, ", ".join(fired) or "none")
        except Exception as exc:
            logging.warning(
                "[CTR] vanilla fill backstop errored (%s: %s); proceeding without "
                "it (fail-open)%s.", type(exc).__name__, exc,
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
        # Honest per-seed relic classification (design note 2026-07-03; Spec 6.2a).
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
          Gold/Platinum gate no location; only goal 2's completion_condition reads a
          relic count (18 Gold). So:
            - Sapphire: progression iff accessibility == full (both Sapphire-gated
              LOCATIONS must be reachable) OR the goal makes you reach + win Oxide's
              Final Challenge (oxidefinal / everythingplusone). Else useful.
            - Gold: progression iff goal == everythingplusone (completion needs 18
              Gold). No location gates on it. Else useful.
            - Platinum: never progression in vanilla mode (no location, no goal
              completion depends on it).
        """
        o = self.options
        prog = {"Sapphire Relic": True, "Gold Relic": True, "Platinum Relic": True}
        if o.warppad_unlock_requirements.value != 0:
            return prog  # randomized modes: any pad may gate on any relic tier
        goal = o.goal.value
        access_full = o.accessibility.value == 0  # Accessibility.option_full == 0
        reach_oxide_final = access_full or goal in (
            Goal.option_oxidefinal, Goal.option_everythingplusone)
        prog["Sapphire Relic"] = reach_oxide_final
        prog["Gold Relic"] = goal == Goal.option_everythingplusone
        prog["Platinum Relic"] = False
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

    def create_items(self):
        player = self.player
        mw = self.multiworld
        pool = []

        # Per-seed relic classification (lever 1); consumed by create_item for every
        # relic created below (pool + slider/goal pins). Computed once here so the
        # whole create_items pass sees a single consistent map.
        self._ctr_relic_prog = self._relic_progression_map()

        # Lever 2 (design note 2026-07-03): in VANILLA warp-pad mode, seat the 4
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

        if self.options.goal.value <= 2:
            victory = ctrAPItem(
                name="Victory",
                classification=ItemClassification.progression_skip_balancing,
                code=None,
                player=player,
            )

            match self.options.goal.value:
                case 0:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Victory",
                        player=player,
                    )
                case 1:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Final Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Victory",
                        player=player,
                    )
                case 2:
                    mw.get_location(
                        location_name="N. Oxide Garage: N. Oxide's Final Challenge",
                        player=player,
                    ).place_locked_item(victory)
                    mw.completion_condition[player] = (
                        lambda state:
                            state.has("Victory", player)
                            and state.has("Gold Relic", player, 18)
                            and all(state.has(g, player, 1)
                                    for g in ["Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"]
                                )
                    )

        elif self.options.goal.value >= 3:
            match self.options.goal.value:
                case 3:
                    mw.completion_condition[player] = lambda state: state.has(
                        item="Trophy",
                        player=player,
                        count=16,
                    )
                case 4:
                    self.gemgoal(player)

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
        # Progression slider now (slider = 0 already means "platinum relics not
        # shuffled / pinned vanilla"). The old ShuffleRewards "Include Platinum
        # Relics" coupling that forced this slider to 0 has been retired (item #5);
        # ShuffleRewards is deprecated and no longer read.

        # NO two-stage reward pinning (Dowlle's OPEN model): relic Time Trials and CTR
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

        # Gems: pin to gem-cup locations when shuffle_gems is OFF. For the all-gem-
        # cups goal the gems are ALWAYS pinned, but gemgoal() already placed them
        # (and place_locked_item on an already-filled location would raise), so skip
        # the placement here for that goal -- the pool exclusion below still applies.
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
        # items, placed at the cups). Other goals keep gems in the pool (e.g.
        # everythingplusone needs them findable; Turbo Track logic needs them)
        # UNLESS shuffle_gems pinned them, in which case _gems_locked subtracts them.
        _GEMS = {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"}
        for item in load_item_table():
            if _GEM_GOAL and item["name"] in _GEMS:
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
        # already locked above (the victory item, and for the gem-cup goal the 5
        # locked gems). Using the static get_total_locations over-counted by the
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
        mw.itempool += [self.create_filler()
                        for _ in range(max(0, unfilled - len(pool)))]

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
        """Locks gem rewards in the appropriate Gem Cup locations."""
        # Read via pkgutil so it works when the world is loaded from a zipped
        # .apworld (open()/os.path on __file__ raises NotADirectoryError inside a
        # zip -- the gem-cup goal crashed on every distributed seed). pkgutil is
        # the mandatory pattern for all packaged data reads in this world.
        _mapping = json.loads(
            pkgutil.get_data(__package__, "data/vanilla_mapping.json").decode("utf-8")
        )
        mw = self.multiworld
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
        crystal have no genuine multi-position finish -- podium-listener handoff
        §3.3).

        NOTE: additive to schema_version 2 (a v2 native build simply ignores this
        block and sends no podium checks -- safe degradation). The schema_version
        bump is deferred until the native fan-out lands and its version comparison
        is confirmed `>=` rather than `==` (see the handoff's open questions), so
        existing seeds stay byte-safe.
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
            "schema_version": 3,
            "ctr_options": {
                "schema_version": 3,
                "goal": o.goal.value,
                "relic_min_time": o.rr_required_minimum_time.value,
                "relics_require_perfect": bool(o.rr_require_perfects.value),
                "oxide_final_unlock": o.oxide_final_challenge_unlock.value,
                "shuffle_warp_pads": derived_shuffle,
                "warp_pad_shuffle_categories": sorted(o.warp_pad_shuffle_categories.value),
                "warp_pad_shuffle_grouping": o.warp_pad_shuffle_grouping.current_key,
                "shuffle_gems": bool(o.shuffle_gems.value),
                "shuffle_keys": bool(o.shuffle_keys.value),
                "warppad_unlock_mode": o.warppad_unlock_requirements.value,
                "bossgarage_mode": o.bossgarage_unlock_requirements.value,
            },
            "warp_pad_map": self._resolve_warp_pad_map(),
            "warp_pad_unlock": self._resolve_warp_pad_unlock(),
            "boss_garage_req": getattr(self, "boss_garage_req", {}),
            "podium_checks": self._resolve_podium_checks(),
        }
        return slot_data

    def collect(self, state: "CollectionState", item: "Item") -> bool:
        return super().collect(state, item)

    def remove(self, state: "CollectionState", item: "Item") -> bool:
        return super().remove(state, item)

    # --- Output generation ---

    def generate_output(self, output_directory: str) -> None:
        patch: CrashTeamRacingProcedurePatch = CrashTeamRacingProcedurePatch(
            player=self.player,
            player_name=self.player_name
        )
        pkg_ressource: bytes | None = pkgutil.get_data(
            package=__name__,
            resource="data/base_patch.bsdiff4",
        )
        if pkg_ressource is not None:
            patch.write_file(
                file_name="base_patch.bsdiff4",
                file=pkg_ressource,
            )
        else:
            None #todo we should really throw some kind of exception here

        write_tokens(
            patch=patch,
            item_placement=self.multiworld.get_locations(self.player),
        )

        # Write output
        out_file_name: str = self.multiworld.get_out_file_name_base(
            player=self.player,
        )
        patch.write(
            os.path.join(
                output_directory,
                f"{out_file_name}{patch.patch_file_ending}"
            )
        )


# Register the BizHawk client so `BizHawkClient` launcher can claim CTR ROMs.
# ADDED FOR CLIENT TESTING — not in upstream icebound777/ctr-apworld yet.
from . import client  # noqa: E402, F401

