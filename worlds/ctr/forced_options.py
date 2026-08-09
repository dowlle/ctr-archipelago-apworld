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


def raise_if_allgemcups_goal_needs_excluded_cups(world):
    """Issue #50: the All-Gems goal's own races ARE the 5 Gem Cups. Turning
    include_gem_cups OFF keeps those cups vanilla-fixed while shuffle_gems ON
    scatters the 5 goal Gems anywhere in the multiworld -- so the goal's own
    cup races are opted out of the seed and the create_items #50 pin (which
    would put the Gems back on the cups) is intentionally skipped for the goal
    (gems ride the pool, 2026-07-15 ruling). That leaves an unwinnable-by-design
    combination, so forbid it here with a clear message rather than emit it.
    shuffle_gems OFF is fine (gemgoal pins the gems onto the cups directly), so
    this fires only on the shuffle-ON conflict."""
    from .Options import Goal
    if world.options.goal.value == Goal.option_allgemcups \
            and world.options.shuffle_gems.value \
            and not world.options.include_gem_cups.value:
        raise OptionError(
            "CTR goal 'allgemcups' requires 'include_gem_cups: true' (the "
            "goal lives in the gem cups; excluding them while shuffling gems "
            "leaves the goal's own races out of the seed).")


def raise_if_oxidefinal_goal_has_no_progression_tier(world):
    """Generation-time progression guard for the Oxide-final goal (issue #23).

    When the goal IS Oxide's Final Challenge, the relic tiers that satisfy the
    configured mode+count must be able to supply the goal as PROGRESSION
    (visible to fill / beatability). A tier whose *_relic_progression is
    'never' (0) is opted fully out of AP progression by the player; if the
    goal can only be satisfied by such tiers, the goal would be invisible to
    AP (the stranding class in the report). Error clearly here instead of
    emitting a world whose goal AP cannot see -- respecting the per-tier
    sliders rather than silently forcing a tier back on."""
    from .Options import Goal, FinalOxideUnlock
    if world.options.goal.value != Goal.option_oxidefinal:
        return
    n = world.options.oxide_final_challenge_relic_count.value
    tiers = world._oxide_goal_tiers()
    # A satisfying tier can supply the goal exactly when this seed classifies
    # it as PROGRESSION (its 18 relics are then reachable + visible to fill).
    # _relic_progression_map is the single source of that truth and is already
    # warp-pad-mode-aware: randomized mode keeps ALL tiers progression (slider
    # only governs pinning, not classification), while vanilla mode makes a
    # goal tier progression only when its slider > 0. Basing the guard on the
    # same map means it fires exactly when the goal really would be invisible.
    prog = world._relic_progression_map()
    prog_tiers = [t for t in tiers if prog.get(t, False)]
    # N <= 18 and each progression tier supplies 18 reachable relics, so one
    # progression tier satisfies single-tier / any_relic_type; total_relics
    # needs the summed progression supply to reach N.
    if world.options.oxide_final_challenge_unlock.value \
            == FinalOxideUnlock.option_total_relics:
        ok = 18 * len(prog_tiers) >= n
    else:
        ok = len(prog_tiers) >= 1
    if not ok:
        mode_key = world.options.oxide_final_challenge_unlock.current_key
        sliders = ", ".join(
            f"{world._OXIDE_TIER_SLIDER[t]}={world._relic_slider_for(t)}"
            for t in tiers)
        raise OptionError(
            f"CTR goal 'oxidefinal' with Oxide's Final Challenge Unlock "
            f"'{mode_key}' needs {n} relic(s) from {tiers}, but no satisfying "
            f"tier is generated as progression in this seed ({sliders}); in "
            f"vanilla warp-pad mode a tier whose *_relic_progression is "
            f"'never' (0) is opted out of progression, so the goal would be "
            f"unreachable. Raise one of those sliders above 0, switch to "
            f"randomized warp-pad unlock, or change the goal, mode, or count.")


def apply_raise_guards(world):
    raise_if_custom_trophy_weight_is_zero(world)
    raise_if_allgemcups_goal_needs_excluded_cups(world)
    raise_if_oxidefinal_goal_has_no_progression_tier(world)


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


def apply_downgrade_warnings(world):
    warn_podium_subtoggles_without_master(world)
    warn_podium_any_position_without_finish(world)
    warn_podium_held_fifth_without_held(world)
    warn_shuffle_crystals_without_include(world)
    warn_shuffle_cups_without_include(world)
    warn_sphere_search_tuning_ignored_in_vanilla(world)
    warn_vanilla_unlock_collapses_destination_shuffle(world)


def apply(world):
    """Single entry point for generate_early. Raise guards run first (they can
    abort generation); downgrade warnings are informational only and never
    change what the seed emits."""
    apply_raise_guards(world)
    apply_downgrade_warnings(world)
