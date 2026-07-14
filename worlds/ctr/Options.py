from typing import List, Dict, Any
from dataclasses import dataclass
from Options import Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle, Toggle, NamedRange, Range, PerGameCommonOptions


class Goal(Choice):
    """Determines the player's end goal.

    - **oxide:** N. Oxide's Challenge - Defeat N. Oxide's Challenge.
    - **oxidefinal:** N. Oxide's Final Challenge - Collect 18 Relics (Sapphire or Greater) and Defeat N. Oxide's Final Challenge.
    - **allbosses:** All Bosses - Win all 4 boss races (Ripper Roo, Papu Papu, Komodo Joe, Pinstripe).
    - **allgemcups:** All Gems - Complete every Gem Cup to collect all 5 Gems."""
    display_name = "Goal"
    option_oxide = 0
    option_oxidefinal = 1
    # Value 2 ("everythingplusone" / 101%) was DROPPED: its implemented condition
    # felt arbitrary and was not true vanilla 101%; goal 1 (Oxide-final) covers the
    # "harder ending" niche. The numeric slot 2 is left as a
    # DOCUMENTED GAP -- the surviving values keep their ints because `ctr_options.goal`
    # is consumed natively by AP_EvaluateGoal (slot_data contract), so renumbering
    # would be a cross-layer break. AP's Choice permits non-contiguous option values,
    # and an old YAML with `goal: everythingplusone` now fails generation with AP's
    # standard invalid-option error (the intended UX -- no silently-accepting alias).
    option_allbosses = 3
    option_allgemcups = 4
    default = 0


class RelicTime(Choice):
    """Choose the required minimum relic time to beat to get any prizes.

    If you choose Gold or Platinum as minimum time, then upon reaching that
    time the lower rank prize(s) will also be awarded."""
    display_name = "Relic Races: Required Minimum Time"
    option_sapphire = 0
    option_gold = 1
    option_platinum = 2
    default = 0


class RelicsRequirePerfect(Toggle):
    """If turned on, to get one or more prizes from a relic race, not only do the
    relic times need to be bested, but all time boxes have to be broken during
    that run as well."""
    display_name = "Relic Races Require Perfects"


class SapphireRelicProgression(NamedRange):
    """How often required progression may sit behind a SAPPHIRE relic-race time
    (the easiest tier). Per-location likelihood: for each of the 18 Sapphire Time
    Trial locations, with this % chance the location stays progression-eligible;
    otherwise its vanilla Sapphire Relic is pinned there (removed from the
    multiworld shuffle) and it can never gate progression.
      0   = never : relics pinned vanilla, out of AP generation
      100 = full  : every sapphire location may hold progression
    `random` gives a surprise value. NOTE: the three tiers are a skill ladder
    (sapphire easy -> gold -> platinum hard). Setting an EASIER tier LOWER than a
    HARDER tier is allowed but yields an inverted, counter-intuitive difficulty."""
    display_name = "Sapphire Relic Progression"
    range_start = 0
    range_end = 100
    default = 100
    special_range_names = {"never": 0, "full": 100}


class GoldRelicProgression(NamedRange):
    """How often required progression may sit behind a GOLD relic-race time (the
    medium tier). Per-location likelihood over the 18 Gold Time Trial locations;
    locked locations pin their vanilla Gold Relic (out of the multiworld shuffle).
      0 = never, 100 = full. `random` for a surprise value. See the Sapphire
    option's note on the tier skill-ladder / inverted configs."""
    display_name = "Gold Relic Progression"
    range_start = 0
    range_end = 100
    default = 100
    special_range_names = {"never": 0, "full": 100}


class PlatinumRelicProgression(NamedRange):
    """How often required progression may sit behind a PLATINUM relic-race time
    (the hardest, expert-only tier). Per-location likelihood over the 18 Platinum
    Time Trial locations; locked locations pin their vanilla Platinum Relic (out
    of the multiworld shuffle). Default 0 = never (the safe live-bug fix: a needed
    item never sits behind a platinum-only time). 100 = full (hardest). `random`
    for a surprise value. See the Sapphire option's note on inverted configs."""
    display_name = "Platinum Relic Progression"
    range_start = 0
    range_end = 100
    default = 0
    special_range_names = {"never": 0, "full": 100}


class FinalOxideUnlock(Choice):
    """Choose what types of relics are required to turn Oxide's Challenge into
    Oxide's Final Challenge.

    - **18 Sapphire Relics**: You need all 18 Sapphire relics (Golds and Platinums are ignored).
    - **18 Gold+Platinum Relics**: You need at least a combined total of 18 Gold relics and Platinum relics."""
    display_name = "Oxide's Final Challenge Unlock"
    option_18_sapphire_relics = 0
    option_18_gold_and_platinum_relics = 1
    default = 0


class ShuffleGems(Toggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **off** (default): each Gem is pinned to its own Gem Cup reward location
      (vanilla placement, out of the multiworld shuffle).
    - **on**: the 5 Gems enter the shuffled pool and can appear anywhere; their
      Gem Cup locations become normal checks holding whatever the fill places.

    The `All Gem Cups` goal ALWAYS pins the Gems to their cups regardless of this
    toggle (they are the goal items)."""
    display_name = "Shuffle Gems"


class ShuffleKeys(DefaultOnToggle):
    """Shuffle the 4 boss Keys into the multiworld item pool.

    - **on** (default): the 4 Keys enter the shuffled pool and can appear anywhere;
      the Boss Race locations become normal checks holding whatever the fill places.
    - **off**: each Key is pinned to its Boss Race reward location
      (vanilla placement, out of the multiworld shuffle)."""
    display_name = "Shuffle Keys"


class TrapFillPercentage(Range):
    """What percentage of this slot's FILLER items are replaced by traps.

    CTR's item pool is almost entirely progression, so the filler pool is small;
    this dial replaces that share of it with trap items rather than adding traps on
    top of progression. The 5 traps (Icy Road Trap, Low Gravity Trap, No Brakes
    Trap, Forced Boost Trap, First Person Trap) are drawn UNIFORMLY -- each is
    equally likely.

      0   (default) = no traps, filler stays vanilla Wumpa Fruit
      100           = every filler slot becomes a trap

    Traps are non-progression: they never gate anything, so any value is always
    solvable. A received trap does not fire on pickup -- it arms silently and
    triggers mid-race on a later lap, then clears."""
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 0


class ShuffleWarpPadsBattleArenas(Toggle):
    """Bring the 4 Battle Arenas (and their Crystal Challenges) into the seed:
    their checks become normal locations and, in a randomized-unlock seed, their
    warp pads get a randomized entry requirement instead of the vanilla gate.

    This is also the PARTICIPATION GATE for the `crystals` destination-shuffle
    category: crystals can only be destination-shuffled (via `Warp Pad Shuffle
    Categories`) when this is on. Off -> crystals stay fully vanilla-fixed
    (vanilla checks, vanilla gate, never destination-shuffled)."""
    display_name = "Include Battle Arena Warp Pads"


class ShuffleWarpPadsGemCups(Toggle):
    """Bring the 5 Gem Cups (and their tournaments) into the seed: their checks
    become normal locations and, in a randomized-unlock seed, their warp pads get
    a randomized entry requirement instead of the vanilla per-cup token gate (the
    Key-2 Cups Room hub gate is always kept on top).

    This is also the PARTICIPATION GATE for the `cups` destination-shuffle
    category: gem cups can only be destination-shuffled (via `Warp Pad Shuffle
    Categories`) when this is on. Off -> cups stay fully vanilla-fixed (vanilla
    checks, vanilla gate, never destination-shuffled)."""
    display_name = "Include Gem Cup Warp Pads"


class WarpPadShuffleCategories(OptionSet):
    """Which content CATEGORIES take part in warp-pad destination shuffle. A
    category left out stays 100% vanilla-fixed (its pad always loads its own
    content); a category included has its pads' DESTINATIONS shuffled (composed
    with `Warp Pad Shuffle Grouping`).

    - **tracks**: the 16 trophy races plus Slide Coliseum and Turbo Track.
    - **cups**: the 5 Gem Cups. Only participates when `Include Gem Cup Warp
      Pads` is also on (that option is what puts cup content in the seed).
    - **crystals**: the 4 Battle Arenas. Only participates when `Include Battle
      Arena Warp Pads` is also on.

    Default: all three. An EMPTY set means no destination shuffle at all (every
    pad loads its own content). ⚠ NOTE: this defaults destination shuffle ON,
    where the old `Shuffle Warp Pads` boolean defaulted OFF.

    VANILLA-UNLOCK COLLAPSE: when `Warp Pad Unlock Requirements` = vanilla, this
    is forced to LEGACY behaviour regardless of the values here — tracks (races
    only, no trials) and crystals shuffle strictly within themselves
    (per_category), and cups/trials stay fixed. Merged grouping and cup/trial
    destination shuffle require a randomized unlock mode."""
    display_name = "Warp Pad Shuffle Categories"
    valid_keys = {"tracks", "cups", "crystals"}
    default = frozenset({"tracks", "cups", "crystals"})


class WarpPadShuffleGrouping(Choice):
    """How the categories selected in `Warp Pad Shuffle Categories` are pooled for
    destination shuffle.

    - **merged** (default): ONE cross-category shuffle pool — a track slot can
      load a cup or crystal and vice versa. Requires a randomized unlock mode
      (collapses to per_category under vanilla unlock).
    - **per_category**: each participating category shuffles only within itself
      (a track always loads a track, a cup a cup, a crystal a crystal).

    Has no effect when fewer than two categories participate (nothing to merge)."""
    display_name = "Warp Pad Shuffle Grouping"
    option_per_category = 0
    option_merged = 1
    default = 1


class WarpPadUnlockRequirements(Choice):
    """Choose the requirements for opening warp pads."""
    display_name = "Warp Pad Unlock Requirements"
    option_vanilla = 0
    option_randomized = 1
    option_random_without_4_keys = 2
    default = 0


class RequirementVariety(Choice):
    """Tuning preset for the WEIGHTS used when randomized warp-pad requirements
    are generated (only affects `Warp Pad Unlock Requirements` = randomized /
    random_without_4_keys).

    - **icebound_beta5** (default): Icebound's rebalanced beta5 weights -- Trophy 90,
      each CTR Token 16 (Purple 12), each Relic tier 18, Key 20, each Gem 4. Any*
      collapse scales Token x0.8 (cap 16), Relic x0.5 (cap 27), Gem capped at 5
      (no -1 reduction).
    - **trophy_heavy_legacy**: the previous weights -- Trophy 100, Token 15 (Purple 10),
      Relic 20, Key 25, Gem 2. Any* collapse Token x0.6, Relic x0.3, Gem -1 (no caps).
    - **custom**: use the per-item weights from `Requirement Weights`; any item not
      listed there falls back to its trophy_heavy_legacy weight. Custom mode uses the
      legacy Any* collapse (x0.6 / x0.3 / -1, no caps)."""
    display_name = "Requirement Variety"
    option_icebound_beta5 = 0
    option_trophy_heavy_legacy = 1
    option_custom = 2
    default = 0


class RequirementWeights(OptionDict):
    """Per-item requirement weights, used ONLY when `Requirement Variety` = custom.

    Higher weight = that item type is chosen more often as a warp-pad requirement.
    Any item omitted from this dict falls back to its trophy_heavy_legacy weight.
    Valid keys: Trophy, Key, the five CTR Token colours, the three Relic tiers, and
    the five Gem colours."""
    display_name = "Requirement Weights"
    supports_weighting = False
    default = {}
    valid_keys = [
        "Trophy", "Key",
        "Red CTR Token", "Green CTR Token", "Blue CTR Token",
        "Yellow CTR Token", "Purple CTR Token",
        "Sapphire Relic", "Gold Relic", "Platinum Relic",
        "Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem",
    ]


class RequirementSpecificity(Choice):
    """How an Any*-of-a-type warp-pad requirement (the aggregates Icebound's chooser
    produces when it collapses a token/relic/gem pick) is expressed in logic and in
    the seed sent to native.

    - **any_of** (default): a collapsed requirement stays a GENUINE "any N of that
      type" gate -- satisfied by ANY mix of that type summed across all colours/tiers
      (e.g. "any 3 CTR Tokens" = any 3 of the 5 token colours combined; "any 4
      relics" = any 4 of Sapphire+Gold+Platinum; "any 2 gems" = any 2 of the 5 gem
      colours). This matches Icebound's AnyCtrToken / AnyRelic / AnyGem semantics and
      emits NEW slot_data type codes 6/7/8 (colour -1) that native sums per type.
    - **specific_colour**: the legacy flatten path -- a collapsed Any* requirement is
      lowered to the single most-owned colour/tier (`_resolve_any`) and emitted as a
      concrete colour-specific gate (type 3/4/5). The gate then means "exactly N of
      THIS one colour/tier". More restrictive; keeps native compatible with builds
      that lack the any-of aggregate patch.

    any_of is MORE PERMISSIVE than specific_colour (a sum across colours is easier to
    satisfy than N of one colour). NATIVE NOTE: any_of emits type 6/7/8 which native
    only understands with the ap_any_of_aggregates patch applied -- on an unpatched
    native build those type codes fall through to "always open". Use specific_colour
    if your native build is not patched."""
    display_name = "Requirement Specificity"
    option_any_of = 0
    option_specific_colour = 1
    default = 0


class TwoStageDensity(Choice):
    """How many trophy pads keep a REAL second-stage gate (a distinct requirement
    on the pad's CTR Challenge + relic Time Trials beyond the Trophy Race itself)
    when requirements are randomized. Only affects `Warp Pad Unlock Requirements`
    = randomized / random_without_4_keys.

    Each value sets the per-seed cap on real stage-2 gates and the per-pad chance
    that a stage 2 collapses to echo its stage 1 (no extra gate):

    - **off**: every stage 2 echoes its stage 1 -- single-stage seeds.
    - **light**: cap 4, collapse chance 50% -- a few real second gates.
    - **standard** (default): cap 6, collapse chance 35% -- the tuned shipping
      behaviour (byte-identical to seeds generated before this option existed).
    - **deep**: cap 10, collapse chance 20% -- closest to Icebound's layered feel.

    Higher density puts more ordering pressure on AP's fill. Solo generation is
    protected by the terminal rollback backstop; expect rare longer generation
    times at deep on maxed-out configs. At non-standard densities an internal
    diversity discount also nudges repeat requirement families (mostly Trophies)
    toward variety, so extra gates do not all come out Trophy-shaped."""
    display_name = "Two-Stage Gate Density"
    option_off = 0
    option_light = 1
    option_standard = 2
    option_deep = 3
    default = 2


class BossGarageRequirements(Choice):
    """Choose the requirements for opening boss garages.

    - **Original 4 Tracks**: At least one race has to be won on each of the regular race warp pads
      which, in vanilla, would be placed in this hub.
    - **Same Hub Tracks**: At least one race has to be won on each of the four warp pads which, in
      vanilla, would be the regular race warp pads of this hub.
    - **Trophies**: Roo, Papu, Joe and Pinstripe unlock with 4, 8, 12, 16 trophies respectively.

    As an example for **Original 4 Tracks**, unlocking Roo would require winning races in
    Crash Cove, Roo's Tubes, Mystery Caves, and Sewer Speedway.
    **Original 4 Tracks** and **Same Hub Tracks** behave identically if warp pads
    are not shuffled.

    CURRENTLY ONLY **Trophies** IS SELECTABLE. Original 4 Tracks (0) and Same Hub
    Tracks (1) are hard-disabled (see BUG-D note below); **Trophies** (2) is the
    only valid value until they are reconciled."""
    display_name = "Boss Garage Requirements"
    # BUG-D: modes 0/1 are a cross-layer
    # paradigm mismatch. The apworld logic gates ALL modes on a flat trophy count
    # (Rules.add_boss_garage_rules 4/8/12/16), but native enforces a per-track WIN
    # for modes 0/1 (ap_hooks.c AP_BossReqMet / AH_Garage.c). Orthogonal criteria =>
    # a 16-trophy player who did NOT win the four required tracks is softlocked, and
    # winning four tracks under-count opens a garage early. These two
    # modes are not shippable until reconciled, so they are removed from the
    # selectable set here (default 2 = Trophies is unaffected and fully implemented).
    #
    # NOT deleted, only disabled: the per-boss vanilla/destination track lists are
    # still resolved + emitted in slot_data (Regions._resolve_boss_reqs, kept intact),
    # and re-enabling is a one-line uncomment once the reconciliation lands. That
    # reconciliation is the SAME machinery as the goal-rework Goal-3 fix: the 4 code-
    # null per-boss "personally won" companion events (paired with the Boss Race
    # locations) are exactly the per-track win flags modes 0/1 need to gate on instead
    # of a flat trophy count. Build those there, then tighten add_boss_garage_rules
    # (or the native gate) to can_reach the four required Trophy Races and restore
    # these two options.
    # option_original_4_tracks = 0  # disabled -- see BUG-D above
    # option_same_hub_tracks = 1    # disabled -- see BUG-D above
    option_trophies = 2
    default = 2


class AutoUnlockCtrChallengeRelicRace(Toggle):
    """Makes the second stage unlock to always free, making the CTR Challenge and
    Relic Race available immediately after beating that warp pad's trophy race."""
    display_name = "Auto-unlock CTR Challenge & Relic Race"


class ComfortGuards(DefaultOnToggle):
    """Enable Icebound's hand-tuned solvability/comfort guards that prevent tedious
    forced item chains. Default ON (matches Icebound's behaviour).

    The guard activates only when warp-pad unlock requirements are **vanilla** and
    gems are **not** shuffled. In that configuration the Turbo Track warp pad keeps
    its vanilla 5-gem entry gate, and reaching it requires winning every Gem Cup
    (each needing 4 CTR tokens) to collect all 5 gems. To stop a required item from
    being forced behind that whole tokens -> gem cups -> 5 gems chain (Icebound's
    `force_vanilla_turbotrack`), the guard pins Turbo Track's three relic Time Trial
    rewards to their vanilla relics (out of the multiworld shuffle), so progression
    is never placed there. It also keeps the Gem Cup and trial warp pads out of the
    trophy-pad destination shuffle so a Gem Cup can never land in the Turbo Track pad
    (Icebound's `limit_arena_gemcup_shuffle`); our shuffle groups already segregate
    them, and this guard enforces that invariant explicitly.

    Turning this OFF removes the pin, allowing the (tedious but still solvable)
    forced chain. The guard is inert whenever unlock requirements are randomized or
    gems are shuffled."""
    display_name = "Comfort Guards"


class PodiumPlacementChecks(DefaultOnToggle):
    """Add podium placement location checks to the 16 adventure trophy races.

    Each trophy race gains a nested rung ladder -- "Finish 1st" and "Finish 2nd
    or 3rd" (and, with the any-position rung below, "Finish (Any Position)") --
    where a better result satisfies every rung at or below it, so finishing 1st
    awards all of that race's rungs at once. This adds 32 (or 48 with the
    any-position rung) extra location checks as room for more items.

    Placement is observed live at the finish line: because vanilla adventure only
    lets you "complete" a trophy race by winning it, a 2nd/3rd placement check is
    earned the moment you cross the line but does NOT by itself advance adventure
    progression. Only the 16 standard trophy races get placement checks -- boss,
    CTR Token, relic, and crystal events do not (they have no genuine multi-
    position finish)."""
    display_name = "Podium Placement Checks"


class PodiumAnyPositionRung(DefaultOnToggle):
    """When Podium Placement Checks is on, add a third "Finish (Any Position)"
    rung to each trophy race -- a check earned simply by crossing the finish line
    in any position. Raises the podium check count from 32 to 48. Has no effect
    when Podium Placement Checks is off."""
    display_name = "Podium: Any-Position Rung"


class SkipMaskHints(DefaultOnToggle):
    """Sets all adventure mode mask hint cutscenes as 'already seen', effectively skipping them."""
    display_name = "Skip Mask Hints"


class AutoskipPodiumCutscenes(Toggle):
    """Automatically inputs the Start-button at the start of each podium cutscene,
    effectively skipping it."""
    display_name = "Auto-Skip Podium Cutscenes"


class SkipMaskCongrats(Toggle):
    """The voice clips of masks will be muted, making it behave as if the
    PAL-exclusive language glitch was active."""
    display_name = "Skip Mask Congrats"


class HelperTiziano(Toggle):
    """Modifies the item boxes while performing the 'Tiziano' shortcut.

    During regular races on Papu's Pyramid, if the player is in 7th or 8th place,
    every item box is a guaranteed mask item."""
    display_name = "Tiziano Helper"


class HelperTA(Toggle):
    """Modifies the item boxes while performing the 'TA' super-shortcut.

    During regular races on Tiny Arena, if the player is in 1st place,
    every item box is a guaranteed TNT/Nitro item."""
    display_name = "TA Helper"


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # general
    goal: Goal
    rr_required_minimum_time: RelicTime
    rr_require_perfects: RelicsRequirePerfect
    oxide_final_challenge_unlock: FinalOxideUnlock
    sapphire_relic_progression: SapphireRelicProgression
    gold_relic_progression: GoldRelicProgression
    platinum_relic_progression: PlatinumRelicProgression
    # randomization
    shuffle_gems: ShuffleGems
    shuffle_keys: ShuffleKeys
    trap_fill_percentage: TrapFillPercentage
    warp_pad_shuffle_categories: WarpPadShuffleCategories
    warp_pad_shuffle_grouping: WarpPadShuffleGrouping
    include_battle_arenas: ShuffleWarpPadsBattleArenas
    include_gem_cups: ShuffleWarpPadsGemCups
    warppad_unlock_requirements: WarpPadUnlockRequirements
    requirement_variety: RequirementVariety
    requirement_weights: RequirementWeights
    requirement_specificity: RequirementSpecificity
    two_stage_density: TwoStageDensity
    bossgarage_unlock_requirements: BossGarageRequirements
    autounlock_ctrchallenge_relicrace: AutoUnlockCtrChallengeRelicRace
    comfort_guards: ComfortGuards
    # extra locations
    podium_placement_checks: PodiumPlacementChecks
    podium_any_position_rung: PodiumAnyPositionRung
    # qol
    skip_mask_hints: SkipMaskHints
    autoskip_podium_cutscenes: AutoskipPodiumCutscenes
    skip_mask_congrats: SkipMaskCongrats
    # trick settings
    helper_tiziano: HelperTiziano
    helper_ta: HelperTA


ap_ctr_option_groups: Dict[str, List[Any]] = {
    "General Options": [Goal, FinalOxideUnlock, RelicTime, RelicsRequirePerfect],
    "Randomization Options": [
        ShuffleGems,
        ShuffleKeys,
        TrapFillPercentage,
        WarpPadShuffleCategories,
        WarpPadShuffleGrouping,
        ShuffleWarpPadsBattleArenas,
        ShuffleWarpPadsGemCups,
        WarpPadUnlockRequirements,
        RequirementVariety,
        RequirementWeights,
        RequirementSpecificity,
        TwoStageDensity,
        AutoUnlockCtrChallengeRelicRace,
        ComfortGuards,
        BossGarageRequirements,
        PodiumPlacementChecks,
        PodiumAnyPositionRung,
    ],
    "Difficulty": [SapphireRelicProgression, GoldRelicProgression, PlatinumRelicProgression],
    "Quality of Life": [SkipMaskHints, AutoskipPodiumCutscenes, SkipMaskCongrats],
    "Tricks": [HelperTiziano, HelperTA],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]