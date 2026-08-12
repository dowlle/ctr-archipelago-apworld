"""Option interaction and constraint matrix (issue #178).

0.2.0 was going to roughly double the YAML surface (staged stat chains, staged
boost, a starting character, character locking, racer-locked pads, box
activation...), and #178 asked for the interactions between all of that to
live in one enforced place instead of scattered inline guards and design
notes. None of those features have landed yet -- they are still spine-1
content-class work, unbuilt on `main` -- so this module covers only the
option set that ships TODAY. The shape and the convention are exactly what
#178 asked for; the interaction *entries* are the ones that already exist in
the code, not the ones the issue's body previewed for the unbuilt features.

Convention ruled in #178 ("the one thing this issue has to settle first"):
split by consequence.

- RAISE when the combination breaks solvability or makes a goal unreachable.
  The three guards below already existed inline in `__init__.generate_early`
  (issues #87, #50, #23) and move here with their behaviour byte-identical --
  moving them is exactly the issue's own "definition of done" clause ("the
  three existing guards behave identically to today, which the existing
  tests should prove").
- DOWNGRADE-WITH-WARNING when the combination only affects flavour or leaves
  an option with nothing to do. Every downgrade case in this module was
  ALREADY a silent no-op on `main` before this issue -- generation logic
  elsewhere already resolves the conflict correctly (podium.py gates every
  rung on the master toggle; warp_pad_logic.resolve_shuffle_pools already
  excludes an uninstantiated category). So "downgrade" here means exactly
  one thing: log a line that names the option and why it did nothing. It
  does NOT mean mutating the option's own stored value the way Stardew
  Valley's forced_options.py sometimes does -- `warp_pad_shuffle_categories`
  is deliberately emitted RAW, pre-collapse, on the wire (slot_data Contract
  Sec.3, "Stef-acked known minor"), and rewriting the stored value here would
  fight that on-the-record choice for no behavioural gain, since every
  downstream reader already resolves the real, collapsed shape itself.

Every entry below is justified against a specific piece of already-shipping
code or the Specification/Contract -- never against "this quiets the fuzzer"
(briefing rule 7): none of these change what a seed generates, only what the
player is told about their own YAML.
"""
import logging

from Options import OptionError

logger = logging.getLogger(__name__)


def _who(world):
    return f"player {world.player} ({world.multiworld.player_name[world.player]})"


# ---------------------------------------------------------------------------
# RAISE guards -- moved verbatim from __init__.generate_early, behaviour
# unchanged. See each docstring for the original issue.
# ---------------------------------------------------------------------------

def raise_if_custom_trophy_weight_is_zero(world):
    """Zero-weight Trophy guard (issue #87). With randomized warp-pad
    requirements (modes 1/2) and requirement_variety=custom, run_sphere_search
    draws pad requirements weighted by the effective custom weights. Trophy is
    the ONLY item guaranteed present in the synthetic inventory at every draw
    (the sphere-0 bootstrap collects the free pads' trophy races first -- see
    the bootstrap section of warp_pad_logic.run_sphere_search), so a Trophy
    weight of 0 makes the candidate weights sum to zero at the first randomized
    draw and random.choices raises a bare ValueError. Reject that config here
    with a clean OptionError instead of emitting a raw traceback. Scoped to
    modes 1/2 (vanilla mode 0 never reads the weights) and to custom (the
    presets all keep Trophy positive)."""
    if world.options.warppad_unlock_requirements.value != 0 \
            and world.options.requirement_variety.current_key == "custom":
        from .warp_pad_logic import effective_custom_weights
        if effective_custom_weights(world).get("Trophy", 0) <= 0:
            raise OptionError(
                "CTR 'requirement_variety: custom' needs a positive 'Trophy' "
                "weight in requirement_weights (this YAML sets Trophy: 0). "
                "Trophies are the only reward available when the seed's first "
                "randomized warp-pad requirements are drawn, so with Trophy at 0 "
                "the candidate weights sum to zero and generation cannot pick a "
                "requirement. In your YAML either set 'Trophy' above 0 (the "
                "default is 100), remove the 'Trophy' entry to keep that default, "
                "or switch requirement_variety to a preset. Weight 0 remains "
                "legal for every other item, including Key.")


def raise_if_composed_goal_is_empty(world):
    """Issue #152 (dossier §2.2 C1): with three independent composable goal
    conditions -- OxideGoal (weighted Choice, 'none' a legal roll),
    BossesRequiredGoal and GemsRequiredGoal (both Range, 0 a legal roll) --
    every one of them landing on its OFF value is a reachable YAML outcome
    (e.g. Dex's weighted-per-option shape rolling 'none'/0/0 independently),
    and nothing before this guard rejects it. An empty composed goal makes
    completion_condition vacuously true (Rules.py `_install_goal` ANDs zero
    active predicates), so the seed would be won at connect -- AP would emit
    a world it considers already beaten. Reject clearly instead of shipping
    that."""
    o = world.options
    from .Options import OxideGoal
    if o.oxide_goal.value == OxideGoal.option_none \
            and o.bosses_required_goal.value == 0 \
            and o.gems_required_goal.value == 0:
        raise OptionError(
            "CTR: 'oxide_goal', 'bosses_required_goal' and "
            "'gems_required_goal' are all off (none/0/0) -- the composed "
            "goal (issue #152) has no active condition, so the seed would be "
            "won the instant it connects. Set at least one of the three to a "
            "non-off value.")


def raise_if_gems_required_goal_needs_excluded_cups(world):
    """Issue #50, generalized for #152's composed goal. When Gems Required
    Goal is active, its Gems ARE (in part) the 5 Gem Cups' vanilla contents.
    Turning include_gem_cups OFF keeps those cups vanilla-fixed while
    shuffle_gems ON scatters the goal Gems anywhere in the multiworld -- so
    the cups the goal's Gems would otherwise sit on are opted out of the
    seed, and the create_items #50 pin (which would put the Gems back on the
    cups) is intentionally skipped whenever gems_required_goal is active
    (gems ride the pool, 2026-07-15 ruling). Each Gem is a singleton item, so
    the required COUNT does not weaken this: needing N of 5 is still "N of
    the 5 items that live on the opted-out cups". That leaves an
    unwinnable-by-design combination, so forbid it here with a clear message
    rather than emit it. shuffle_gems OFF is fine (the Gems are pinned onto
    the cups directly, see create_items), so this fires only on the
    shuffle-ON conflict."""
    if world.options.gems_required_goal.value > 0 \
            and world.options.shuffle_gems.value \
            and not world.options.include_gem_cups.value:
        raise OptionError(
            "CTR 'gems_required_goal' > 0 requires 'include_gem_cups: true' "
            "when 'shuffle_gems' is also on (the required Gems live in the "
            "gem cups; excluding the cups while shuffling gems leaves the "
            "goal's own Gems out of the seed).")


def raise_if_oxidefinal_goal_has_no_progression_tier(world):
    """Generation-time progression + supply guard for the Oxide-final goal
    (issue #23; extended by issue #171/#28 R5 for exact-count supply; #152 C3
    /C4: generalized from the legacy `goal == oxidefinal` value to the
    composed `oxide_goal == final` condition, kept in lockstep with
    `_relic_progression_map`'s own `oxide_goal == final` branch -- both must
    move together, or a composed oxide-final seed either fails generation on
    a slider the player never touched (map not updated) or ships a goal tier
    that is never classified progression (guard not updated); see the #152
    build note).

    When Oxide Goal is 'final', the relic tiers that satisfy the configured
    mode+count must (a) be generated as PROGRESSION (visible to fill /
    beatability) and (b), since issue #171 replaced the old always-18-items
    pinning with exact-count removal, actually have enough relics CREATED
    this seed to reach the configured count -- a tier at 'count 5' can never
    satisfy a request for 10, no matter how it is classified. A tier whose
    count is 0 is opted fully out by the player; if the goal can only be
    satisfied by such tiers (or by tiers with too few created), the goal
    would be unreachable. Error clearly here instead of emitting a world
    whose goal AP cannot see -- respecting the per-tier counts rather than
    silently forcing a tier back on or (R5's alternative, considered and
    rejected here for this specific guard -- see the build note) silently
    clamping the player's own oxide_final_challenge_relic_count down to
    whatever happened to be created."""
    from .Options import OxideGoal, FinalOxideUnlock
    if world.options.oxide_goal.value != OxideGoal.option_final:
        return
    n = world.options.oxide_final_challenge_relic_count.value
    tiers = world._oxide_goal_tiers()
    # A satisfying tier can supply the goal exactly when this seed classifies
    # it as PROGRESSION (its created relics are then reachable + visible to
    # fill). _relic_progression_map is the single source of that truth and is
    # already warp-pad-mode-aware: randomized mode keeps ALL tiers progression
    # (the per-tier count only governs how many are created, not
    # classification), while vanilla mode makes a goal tier progression only
    # when its count > 0. Basing the guard on the same map means it fires
    # exactly when the goal really would be invisible.
    prog = world._relic_progression_map()
    prog_tiers = [t for t in tiers if prog.get(t, False)]
    created = world._ctr_relic_created  # relic item name -> count created this seed
    # total_relics needs the summed CREATED supply across progression tiers to
    # reach N; every other mode (single-tier presets + any_relic_type, whose
    # own tiers list already narrows to the modes it applies to) needs at
    # least one progression tier whose OWN created count reaches N.
    if world.options.oxide_final_challenge_unlock.value \
            == FinalOxideUnlock.option_total_relics:
        ok = sum(created.get(t, 0) for t in prog_tiers) >= n
    else:
        ok = any(created.get(t, 0) >= n for t in prog_tiers)
    if not ok:
        mode_key = world.options.oxide_final_challenge_unlock.current_key
        counts = ", ".join(
            f"{world._OXIDE_TIER_SLIDER[t]}={created.get(t, 0)} created "
            f"({'progression' if prog.get(t, False) else 'useful'})"
            for t in tiers)
        raise OptionError(
            f"CTR goal 'oxidefinal' with Oxide's Final Challenge Unlock "
            f"'{mode_key}' needs {n} relic(s) from {tiers}, but no "
            f"combination of progression-classified, created relics in this "
            f"seed can reach {n} ({counts}); a tier with count 0 is opted out "
            f"of progression, and even a progression tier cannot supply more "
            f"relics than its own created count. Lower "
            f"oxide_final_challenge_relic_count, raise the relevant relic "
            f"tier's *_relic_count, switch to randomized warp-pad unlock (all "
            f"tiers progression), or change the goal or mode.")


def raise_if_full_accessibility_needs_more_sapphires_than_created(world):
    """Issue #171/#28 R5: two FIXED (not YAML-driven) world.json location
    gates name a Sapphire count -- 'Gem Stone Valley -> Slide Coliseum Warp
    Pad' (has('Sapphire Relic', 10), vanilla warp-pad unlock only; randomized
    unlock strips this exact exit rule in Regions.create_regions) and
    'N. Oxide Garage: N. Oxide's Final Challenge' (has('Key', 4) and
    has('Sapphire Relic', 18), present UNCONDITIONALLY in every warp-pad
    unlock mode, independent of the goal or oxide_final_challenge_relic_count
    -- verified at source, `data/world.json`, no other code path overrides
    this location's own requires text).

    Pre-#171, both gates always had their full 18 Sapphire Relic items
    available (pinned-vanilla or pool-placed, item existence was invariant).
    Issue #171's exact-count removal breaks that invariant: if
    sapphire_relic_count creates fewer than a gate's fixed threshold, that
    gate can NEVER be satisfied by any state, no matter what the player
    collects. Under accessibility 'full' every location must be reachable, so
    this is a genuine, generation-aborting solvability break -- RAISE, not
    clamp (clamping would mean silently overriding the player's own
    sapphire_relic_count, in a case with no clear 'safe' direction to clamp
    toward). See warn_relic_gates_may_be_permanently_unreachable for the
    non-full-accessibility case, where AP already tolerates an unreachable
    non-required location (see test_vanilla_floors.TestVanillaBadSeedClass)."""
    if world.options.accessibility.value != 0:  # Accessibility.option_full == 0
        return
    created = world._ctr_relic_created.get("Sapphire Relic", 0)
    problems = []
    if world.options.warppad_unlock_requirements.value == 0 and created < 10:
        problems.append(
            "'Gem Stone Valley -> Slide Coliseum Warp Pad' needs 10 (vanilla "
            "warp-pad unlock keeps this world.json gate; randomized unlock "
            "strips it)")
    if created < 18:
        problems.append(
            "'N. Oxide Garage: N. Oxide's Final Challenge' needs 18 (this "
            "world.json location gate is unconditional -- present in every "
            "warp-pad unlock mode, independent of the goal or "
            "oxide_final_challenge_relic_count)")
    if not problems:
        return
    raise OptionError(
        f"CTR: accessibility 'full' requires every location reachable, but "
        f"this seed creates only {created} Sapphire Relic(s) "
        f"(sapphire_relic_count), and: " + "; ".join(problems) + ". Raise "
        f"sapphire_relic_count, or switch accessibility away from 'full'.")


def apply_raise_guards(world):
    raise_if_custom_trophy_weight_is_zero(world)
    raise_if_composed_goal_is_empty(world)
    raise_if_gems_required_goal_needs_excluded_cups(world)
    raise_if_oxidefinal_goal_has_no_progression_tier(world)
    raise_if_full_accessibility_needs_more_sapphires_than_created(world)


# ---------------------------------------------------------------------------
# DOWNGRADE-WITH-WARNING guards -- log only, never mutate the option. Every
# no-op described here already happens on `main`; these functions only make
# it visible.
# ---------------------------------------------------------------------------

def warn_podium_subtoggles_without_master(world):
    """podium.created_rung_keys_from_options gates every rung on
    podium_placement_checks FIRST (returns [] outright when it's off, before
    even looking at the other four options), so Podium Finish Rungs, Podium:
    Any-Position Rung, Held-Position Rungs and Podium: Held 5th Rung cannot
    create or withhold a single location while the master switch is off."""
    o = world.options
    if o.podium_placement_checks.value:
        return
    logger.warning(
        f"CTR: Podium Placement Checks is off for {_who(world)}, so Podium "
        f"Finish Rungs, Podium: Any-Position Rung, Held-Position Rungs and "
        f"Podium: Held 5th Rung have no effect -- no podium rungs are created "
        f"this seed regardless of their values.")


def warn_podium_any_position_without_finish(world):
    """podium.created_rung_keys only reads any_on inside the `if finish_on`
    branch, so Any-Position Rung cannot matter while Finish Rungs is off.
    Scoped to podium_placement_checks ON: with the master off,
    warn_podium_subtoggles_without_master already covers it."""
    o = world.options
    if not o.podium_placement_checks.value:
        return
    if o.podium_finish_rungs.value:
        return
    logger.warning(
        f"CTR: Podium Finish Rungs is off for {_who(world)}, so Podium: "
        f"Any-Position Rung has no effect this seed.")


def warn_podium_held_fifth_without_held(world):
    """Same pattern as the finish/any-position pair, for held_fifth_on inside
    the `if held_on` branch of podium.created_rung_keys."""
    o = world.options
    if not o.podium_placement_checks.value:
        return
    if o.podium_held_rungs.value:
        return
    logger.warning(
        f"CTR: Held-Position Rungs is off for {_who(world)}, so Podium: Held "
        f"5th Rung has no effect this seed.")


def warn_shuffle_crystals_without_include(world):
    """warp_pad_logic.resolve_shuffle_pools only appends the crystals pool
    when include_battle_arenas is true -- identically in both the
    vanilla-collapse branch and the randomized-mode branch -- so 'crystals' in
    Warp Pad Shuffle Categories has no effect while Include Battle Arena Warp
    Pads is off, in every unlock mode."""
    o = world.options
    if "crystals" not in set(o.warp_pad_shuffle_categories.value):
        return
    if o.include_battle_arenas.value:
        return
    logger.warning(
        f"CTR: Include Battle Arena Warp Pads is off for {_who(world)}, so "
        f"the 'crystals' entry in Warp Pad Shuffle Categories has no effect "
        f"-- the arenas stay out of the seed and never destination-shuffle.")


def warn_shuffle_cups_without_include(world):
    """resolve_shuffle_pools only appends the cups pool when include_gem_cups
    is true, and only on the randomized-mode branch. Scoped to unlock mode !=
    vanilla: under vanilla, cups are excluded unconditionally (even with
    include_gem_cups on) -- warn_vanilla_unlock_collapses_destination_shuffle
    covers that case instead, so this warning does not double up with it."""
    o = world.options
    if o.warppad_unlock_requirements.value == 0:
        return
    if "cups" not in set(o.warp_pad_shuffle_categories.value):
        return
    if o.include_gem_cups.value:
        return
    logger.warning(
        f"CTR: Include Gem Cup Warp Pads is off for {_who(world)}, so the "
        f"'cups' entry in Warp Pad Shuffle Categories has no effect -- the "
        f"cups stay out of the seed and never destination-shuffle.")


def warn_sphere_search_tuning_ignored_in_vanilla(world):
    """Two-Stage Gate Density, Requirement Variety and Requirement Weights are
    only ever read inside warp_pad_logic._load_requirement_preset, which only
    ever runs from run_sphere_search, which Regions.create_regions only calls
    when warppad_unlock_requirements is randomized or random_without_4_keys
    (unlock_mode 0 skips it entirely -- 'all type:0, identity'). So in vanilla
    mode all three are parsed and then never consulted."""
    o = world.options
    if o.warppad_unlock_requirements.value != 0:
        return
    parts = [f"Two-Stage Gate Density ('{o.two_stage_density.current_key}')",
             f"Requirement Variety ('{o.requirement_variety.current_key}')"]
    if o.requirement_variety.current_key == "custom" and o.requirement_weights.value:
        parts.append("Requirement Weights")
    logger.warning(
        f"CTR: Warp Pad Unlock Requirements 'vanilla' never runs the "
        f"randomized requirement sphere-search for {_who(world)}, so " +
        ", ".join(parts) + " have no effect this seed.")


def warn_vanilla_unlock_collapses_destination_shuffle(world):
    """Vanilla unlock mode always forces the destination-shuffle configuration
    into its legacy shape, regardless of the YAML -- verbatim from
    resolve_shuffle_pools' own 'Vanilla-unlock collapse' docstring: grouping is
    forced to per_category, the two trial pads drop out of the 'tracks'
    category (races-only, _LEGACY_RACE_IDS), and 'cups' never participates
    even when selected. Category SELECTION is still honoured -- an unselected
    category still never shuffles -- so this only fires for parts the YAML
    actually asked for."""
    o = world.options
    if o.warppad_unlock_requirements.value != 0:
        return
    cats = set(o.warp_pad_shuffle_categories.value)
    parts = []
    if o.warp_pad_shuffle_grouping.current_key == "merged":
        parts.append("'Warp Pad Shuffle Grouping: merged' is forced to "
                     "'per_category'")
    if "tracks" in cats:
        parts.append("Slide Coliseum and Turbo Track drop out of the "
                     "'tracks' shuffle pool (races-only)")
    if "cups" in cats:
        parts.append("the 'cups' category never participates")
    if not parts:
        return
    logger.warning(
        f"CTR: Warp Pad Unlock Requirements 'vanilla' collapses destination "
        f"shuffle to its legacy shape for {_who(world)}: " + "; ".join(parts) +
        ". Only randomized unlock modes get the full category x grouping "
        f"matrix.")


def warn_relic_gates_may_be_permanently_unreachable(world):
    """The non-full-accessibility counterpart of
    raise_if_full_accessibility_needs_more_sapphires_than_created (issue
    #171/#28 R5): under accessibility != full, AP already tolerates an
    unreachable, non-required location (the vanilla+minimal case is
    documented pre-existing in test_vanilla_floors.TestVanillaBadSeedClass),
    so this is a warning, not a generation-aborting error. Surfaced rather
    than left fully silent because issue #171 makes it newly reachable BY
    PLAYER CHOICE -- pre-#171 these two fixed gates always had their full 18
    Sapphires (pinned or not), so no YAML combination could permanently lock
    them; now sapphire_relic_count alone can."""
    if world.options.accessibility.value == 0:
        return
    created = world._ctr_relic_created.get("Sapphire Relic", 0)
    problems = []
    if world.options.warppad_unlock_requirements.value == 0 and created < 10:
        problems.append("'Gem Stone Valley -> Slide Coliseum Warp Pad' (needs 10)")
    if created < 18:
        problems.append("'N. Oxide Garage: N. Oxide's Final Challenge' (needs 18)")
    if not problems:
        return
    logger.warning(
        f"CTR: player {world.player} ({world.multiworld.player_name[world.player]}) "
        f"created only {created} Sapphire Relic(s) this seed (sapphire_relic_count), "
        f"so " + " and ".join(problems) + " can never be reached by any state -- "
        f"permanently unreachable, but tolerated under this accessibility setting.")


def warn_editable_stats_overridden_by_progressive(world):
    """characters.effective_stat_config resolves the ruled precedence in one
    place: progressive stats non-off wins outright and the in-game stat panel
    goes read-only with no edit control at all, whatever `editable_stats` says.
    The 2026-08-08 ruling is explicit that this combination does NOT reject the
    seed, so this is a downgrade-with-warning entry (#178 convention) rather
    than a raise: the option is simply left with nothing to do."""
    o = world.options
    if not o.progressive_stats.value:
        return
    if not o.editable_stats.value:
        return
    logger.warning(
        f"CTR: Progressive Stats is on for {_who(world)}, so Editable Stats "
        f"has no effect -- progressive stats own the stat table and the "
        f"in-game panel stays read-only with no edit control. Set Progressive "
        f"Stats to 'off' if you want to tune stats yourself.")


def warn_penta_stats_without_vanilla_stats(world):
    """`penta_stats` picks between Penta's ordinary TURN-class table and the
    PAL/JP MAX class, and both are VANILLA class tables. As soon as progressive
    or editable stats own the stat package (characters.effective_stat_config
    returns a non-vanilla source) Penta reads that package like every other
    racer, so the selector has no gameplay effect. Warn rather than raise: the
    seed is completely valid, the option just does nothing in it."""
    from .characters import STAT_SOURCE_VANILLA, effective_stat_config
    o = world.options
    if not o.penta_stats.value:
        return  # PAL is the default; a defaulted option needs no notice
    source, _owner, _editable = effective_stat_config(world)
    if source == STAT_SOURCE_VANILLA:
        return
    logger.warning(
        f"CTR: Penta Penguin Stats is set to 'ntsc' for {_who(world)}, but "
        f"this seed's stats are owned by Progressive Stats or Editable Stats, "
        f"so Penta uses the AP-defined stats like every other racer and the "
        f"selector has no gameplay effect.")


def warn_racer_locks_without_character_unlocks(world):
    """Racer locks gate a pad on holding a character unlock item. In
    all-unlocked mode (`character_unlocks: false`) no such item is ever
    created, so there is nothing a lock could gate --
    characters.racer_locks_enabled resolves the pair to "off" and no pad is
    locked. Downgrade-with-warning, not a raise: the seed is completely valid,
    the toggle just has nothing to do in it."""
    o = world.options
    if not o.racer_locked_pads.value:
        return
    if o.character_unlocks.value:
        return
    logger.warning(
        f"CTR: Racer-Locked Warp Pads is on for {_who(world)}, but Character "
        f"Unlocks is off (all-unlocked mode), so there are no character unlock "
        f"items for a pad to require and no pad is locked to a racer. Turn "
        f"Character Unlocks on to use racer locks.")


def warn_racer_locks_have_no_eligible_pads(world):
    """Racer locks can only be placed on a pad this seed randomized and left
    non-free (characters.eligible_lock_pads). A vanilla-unlock seed randomizes
    no pad at all, so the toggle silently produces zero locks -- and, through
    R17, still keeps the 15 character unlocks as progression, which is a real
    cost for no feature. Say so rather than leaving the player to wonder."""
    o = world.options
    if not o.racer_locked_pads.value:
        return
    if o.warppad_unlock_requirements.value != 0:
        return
    logger.warning(
        f"CTR: Racer-Locked Warp Pads is on for {_who(world)}, but Warp Pad "
        f"Unlock Requirements is 'vanilla', so no pad carries a randomized "
        f"requirement and no racer lock can be placed. The 15 character "
        f"unlock items still exist and are still playable racers.")


def warn_wumpa_bundles_have_no_filler_slots(world):
    """Wumpa bundles substitute into the FILLER budget, so a seed that turns
    every filler slot into a trap leaves them nowhere to land.

    `trap_fill_percentage` 100 makes `n_traps == n_filler` in create_items, and
    the non-trap remainder that h_dossier.draw_filler_name would fill is then
    empty. The option is not wrong and the seed is perfectly generatable -- it
    simply cannot express the bundles -- which is exactly the downgrade-with-
    warning shape rather than a raise."""
    o = world.options
    if not o.wumpa_bundles.value:
        return
    if o.trap_fill_percentage.value < 100:
        return
    logger.warning(
        f"CTR: Trap Fill Percentage is 100 for {_who(world)}, so every filler "
        f"slot becomes a trap and Wumpa Bundles has no effect this seed.")


def warn_grants_gated_behind_unreceived_weapons(world):
    """With Itemsanity ON, `Invincibility Mask` needs the separate `Mask` item
    and `Turbo Grant` needs the separate `Turbo` item before either can be
    delivered (2026-08-11 ruling).

    This is NOT a solvability problem -- both weapon items always exist in an
    itemsanity pool, the grants are `useful` and nothing in logic reads them, and
    a grant that arrives early queues rather than being discarded. It is a
    surprise problem: a player who receives a grant on sphere 1 and sees nothing
    happen should have been told why in their generation log, not left to
    discover the gate in-game."""
    o = world.options
    if not (o.useful_item_grants.value and o.itemsanity.value):
        return
    logger.warning(
        f"CTR: Itemsanity is on for {_who(world)}, so Invincibility Mask waits "
        f"for the Mask weapon item and Turbo Grant waits for the Turbo weapon "
        f"item. Grants received before then are queued, never lost.")


def apply_downgrade_warnings(world):
    warn_podium_subtoggles_without_master(world)
    warn_podium_any_position_without_finish(world)
    warn_podium_held_fifth_without_held(world)
    warn_shuffle_crystals_without_include(world)
    warn_shuffle_cups_without_include(world)
    warn_sphere_search_tuning_ignored_in_vanilla(world)
    warn_vanilla_unlock_collapses_destination_shuffle(world)
    warn_relic_gates_may_be_permanently_unreachable(world)
    warn_editable_stats_overridden_by_progressive(world)
    warn_penta_stats_without_vanilla_stats(world)
    warn_racer_locks_without_character_unlocks(world)
    warn_racer_locks_have_no_eligible_pads(world)
    warn_wumpa_bundles_have_no_filler_slots(world)
    warn_grants_gated_behind_unreceived_weapons(world)


def apply(world):
    """Single entry point for generate_early. Raise guards run first (they can
    abort generation); downgrade warnings are informational only and never
    change what the seed emits."""
    apply_raise_guards(world)
    apply_downgrade_warnings(world)
