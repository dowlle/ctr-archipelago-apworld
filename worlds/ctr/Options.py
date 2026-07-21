from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility)


class Goal(Choice):
    """Determines the player's end goal.

    - **oxide:** N. Oxide's Challenge - Defeat N. Oxide's Challenge.
    - **oxidefinal:** N. Oxide's Final Challenge - Collect 18 Relics (Sapphire or Greater) and Defeat N. Oxide's Final Challenge.
    - **allbosses:** All Bosses - Win all 4 boss races (Ripper Roo, Papu Papu, Komodo Joe, Pinstripe).
    - **allgemcups:** All Gems - Collect all 5 Gems. With `Shuffle Gems` off they
      sit on their own Gem Cups (win every cup); with `Shuffle Gems` on they are
      hidden anywhere in the multiworld and the hunt is on.

    Note: `allgemcups` requires `Include Gem Cup Warp Pads` to be **on**. The goal
    lives in the gem cups, so excluding them while `Shuffle Gems` is on would leave
    the goal's own races out of the seed; that combination fails generation with a
    clear message."""
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


class FinalOxideUnlock(Choice):
    """Choose WHICH relics gate turning Oxide's Challenge into Oxide's Final
    Challenge. The COUNT is set separately by `Oxide's Final Challenge Relic
    Count` (1-18, default 18) and is shared by every mode.

    Relic tiers are INDEPENDENT items with no downward hierarchy: a Platinum
    relic does NOT count toward a Gold requirement. (The only cross-tier
    hierarchy is location-side, on the race award path -- beating a Platinum
    time also sends that track's Gold and Sapphire checks -- which is unrelated
    to which relic ITEMS you own.)

    - **sapphire_relics** (default): N Sapphire Relic items received.
    - **gold_relics**: N Gold Relic items received.
    - **platinum_relics**: N Platinum Relic items received.
    - **any_relic_type**: any single relic type reaches N (Sapphire OR Gold OR Platinum).
    - **total_relics**: all relic items added together reach N.

    NOTE: a goal (or a settings combo) that requires a relic tier whose
    `<tier>_relic_progression` is set to `never` fails generation with a clear
    message -- raise that tier's progression, or pick a mode/count the enabled
    tiers can satisfy. The old `18_gold_and_platinum_relics` value is REMOVED;
    YAMLs carrying it must update."""
    display_name = "Oxide's Final Challenge Unlock"
    option_sapphire_relics = 0
    option_gold_relics = 1
    option_platinum_relics = 2
    option_any_relic_type = 3
    option_total_relics = 4
    # Back-compat alias: the pre-v0.1.1 default value maps exactly onto the new
    # default (sapphire_relics + the default count 18 == the old "18 Sapphire
    # Relics"). The other pre-v0.1.1 value, 18_gold_and_platinum_relics, is
    # DELIBERATELY not aliased -- it is removed, not remapped (issue #23), so an
    # old YAML carrying it fails generation with AP's standard invalid-option
    # error instead of silently changing meaning.
    alias_18_sapphire_relics = 0
    default = 0


class FinalOxideRelicCount(NamedRange):
    """How many relics `Oxide's Final Challenge Unlock` requires. Shared by every
    mode (for `total_relics` it is the summed total; for `any_relic_type` it is
    the threshold any single tier must reach).

    Range 1-18. Totals above 18 are deliberately not offered (all-relics-slog
    territory)."""
    display_name = "Oxide's Final Challenge Relic Count"
    range_start = 1
    range_end = 18
    default = 18
    special_range_names = {"all": 18}


class ShuffleGems(DefaultOnToggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **on** (default): the 5 Gems enter the shuffled pool and can appear anywhere;
      their Gem Cup locations become normal checks holding whatever the fill places.
    - **off**: each Gem is pinned to its own Gem Cup reward location
      (vanilla placement, out of the multiworld shuffle).

    Works with every goal, including `All Gems`: there the shuffled Gems become
    the goal items you hunt down across the multiworld."""
    display_name = "Shuffle Gems"


class ShuffleWarpPadsGemCups(DefaultOnToggle):
    """Bring the 5 Gem Cups (and their tournaments) into the seed: their checks
    become normal locations and, in a randomized-unlock seed, their warp pads get
    a randomized entry requirement instead of the vanilla per-cup token gate (the
    Key-2 Cups Room hub gate is always kept on top).

    Note the difference with `Shuffle Gems`: that option moves the Gem ITEMS
    around; this one brings the cup RACES and their warp pads into the seed.
    This is also the participation gate for the `cups` destination-shuffle
    category: gem cups can only be destination-shuffled (via `Warp Pad Shuffle
    Categories`) when this is on. Off -> cups stay fully vanilla-fixed (vanilla
    checks, vanilla gate, never destination-shuffled).

    Off is safe with shuffled Gems: when this is off and `Shuffle Gems` is on,
    each Gem is pinned back onto its own vanilla Gem Cup check (out of the
    multiworld pool) so opted-out cups never hold another world's progression.
    Required to be **on** for the `All Gems` goal -- that goal's races ARE the
    gem cups, so `allgemcups` + `Shuffle Gems` on + this off fails generation
    with a clear message rather than stranding the goal."""
    display_name = "Include Gem Cup Warp Pads"


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

      0             = no traps, filler stays vanilla Wumpa Fruit
      10  (default) = a taste of sabotage
      100           = every filler slot becomes a trap

    Traps are non-progression: they never gate anything, so any value is always
    solvable. A received trap does not fire on pickup -- it arms silently and
    triggers mid-race on a later lap, then clears."""
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 10


class OneLapCups(Toggle):
    """Make Cup races one lap each instead of the usual three.

    A pure pace/quality-of-life setting for seeds that send you through many
    cups. It only shortens CUP races (Arcade/VS cups, including the Gem Cups);
    single races, boss races, relic time trials and CTR Token challenges keep
    their normal lap count. It reuses the engine's built-in one-lap mechanism
    (the vanilla one-lap cheat), just scoped to cups.

    It changes NOTHING about logic, item placement or which locations exist --
    every check is reached exactly as it would be with this off, only faster.
    Off by default."""
    display_name = "One-Lap Cup Races"


class ShuffleWarpPadsBattleArenas(DefaultOnToggle):
    """Bring the 4 Battle Arenas (and their Crystal Challenges) into the seed:
    their checks become normal locations and, in a randomized-unlock seed, their
    warp pads get a randomized entry requirement instead of the vanilla gate.

    Not the same thing as `crystals` in `Warp Pad Shuffle Categories`: THIS
    option puts the arenas in the seed at all; the category set only controls
    whether their pads' DESTINATIONS get shuffled, and it does nothing while
    this is off. Off -> crystals stay fully vanilla-fixed (vanilla checks,
    vanilla gate, never destination-shuffled)."""
    display_name = "Include Battle Arena Warp Pads"


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
    pad loads its own content).

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
    """How warp pads unlock — the heart of the randomizer.

    - **randomized** (default): every warp pad gets a randomized entry
      requirement (trophies, tokens, relics, keys, gems...), chosen by a
      solvability-proven sphere search so a pad's requirement is always
      collectable before that pad opens.
    - **vanilla**: pads open on their vanilla trophy counts, like the original
      adventure.
    - **random_without_4_keys**: like randomized, but the 4 boss Keys are never
      chosen as pad requirements."""
    display_name = "Warp Pad Unlock Requirements"
    option_vanilla = 0
    option_randomized = 1
    option_random_without_4_keys = 2
    default = 1


class TwoStageDensity(Choice):
    """How many trophy pads carry a REAL second-stage gate: an extra requirement
    on the pad's CTR Challenge + relic Time Trials, on top of winning the Trophy
    Race itself. Only affects `Warp Pad Unlock Requirements` = randomized /
    random_without_4_keys.

    - **off**: no second stage at all — the CTR Challenge and relic Time Trials
      unlock the moment that pad's trophy race is won.
    - **light**: a few real second gates (cap 4 per seed).
    - **standard** (default): the tuned shipping behaviour (cap 6).
    - **deep**: layered, Icebound-style progression (cap 10).
    - **full**: every trophy pad that CAN carry a real second gate gets one
      (cap 16, no random collapse). The densest, most interlocked seeds.

    Also accepts `random` in the YAML to roll one of these per seed.

    Higher density puts more ordering pressure on AP's fill. Solo generation is
    protected by the terminal rollback backstop; expect rare longer generation
    times at deep/full on maxed-out configs. At non-standard densities an
    internal diversity discount nudges repeat requirement families (mostly
    Trophies) toward variety, so extra gates do not all come out Trophy-shaped."""
    display_name = "Two-Stage Gate Density"
    option_off = 0
    option_light = 1
    option_standard = 2
    option_deep = 3
    option_full = 4
    default = 2


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
    """Roll your own requirement mix. Used ONLY when `Requirement Variety` =
    custom. Each entry is `item name: weight` — a pad requirement is drawn with
    chance proportional to its weight, so an item with weight 100 is picked
    about five times as often as one with weight 20, and weight 0 disables an
    item entirely. Items you leave out keep their trophy_heavy_legacy weight.

    Example — trophy-light seeds that lean hard on relics and keys:

        requirement_variety: custom
        requirement_weights:
          Trophy: 30
          Key: 40
          Sapphire Relic: 40
          Gold Relic: 25
          Purple CTR Token: 0

    Valid keys: Trophy, Key, the five CTR Token colours ("Red CTR Token", ...),
    the three Relic tiers ("Sapphire Relic", "Gold Relic", "Platinum Relic"),
    and the five Gem colours ("Red Gem", ...)."""
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


class BossGarageRequirements(Choice):
    """Boss garages unlock on trophy counts: Roo, Papu, Joe and Pinstripe open
    with 4, 8, 12, 16 trophies respectively.

    HIDDEN from the YAML template and options page: `trophies` is currently the
    only implemented mode, so there is nothing to choose. The option (and its
    slot_data key `bossgarage_mode`) stays wired for when the track-based modes
    return."""
    display_name = "Boss Garage Requirements"
    visibility = Visibility.none
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


class DeathLink(Choice):
    """DeathLink: share your wipeouts with the other DeathLink players in the
    multiworld, and take theirs.

    - **off** (default): DeathLink is disabled; nothing is sent or received.
    - **mask_reset**: send a death only when the mask carries you back, i.e. you
      fell off the track or were eaten. Unambiguous, low-frequency wipeouts.
    - **any_hit**: additionally send on every hit that lands on you (spin-out,
      blast, squish, burn), so the cadence is much higher; pair this with
      `DeathLink Amnesty` to keep it playable.

    Receiving a death always forces the full mask reset on you (carried back),
    the game's heaviest wipeout, regardless of which tier you send at. Only
    adventure-mode races send; a received death never triggers an outgoing one.

    NOTE ON THE TYPE: AP core ships DeathLink as a plain on/off Toggle. CTR uses a
    3-value Choice instead because the two send tiers (mask_reset vs any_hit) are a
    real gameplay difference in a kart racer, not a cosmetic one, and folding them
    into a separate toggle would let a player pick "any_hit but do not send", which
    is not a mode we support. off still reads as the disabled state, so the value
    mirrored into slot_data is 0 when DeathLink is off, matching the Toggle
    convention native keys off."""
    display_name = "DeathLink"
    option_off = 0
    option_mask_reset = 1
    option_any_hit = 2
    default = 0


class DeathLinkAmnesty(Range):
    """How many of YOUR deaths must pile up before one is actually sent. 1
    (default) sends every death; N sends one death per N. Meant for the `any_hit`
    tier, where hits are frequent enough to spam the multiworld; it does nothing
    useful at `mask_reset` (those wipeouts are already rare) and is inert while
    DeathLink is off. Incoming deaths are unaffected: you always take every death
    another player sends you, amnesty only throttles your OUTGOING deaths."""
    display_name = "DeathLink Amnesty"
    range_start = 1
    range_end = 30
    default = 1


class PodiumPlacementChecks(DefaultOnToggle):
    """Add finishing-position location checks to the 16 adventure trophy races.

    This is the master switch for the whole podium-rung feature. With it on, each
    trophy race can carry up to five position rungs, split across two families you
    toggle separately:

    - Finish rungs (`Podium Finish Rungs`): "Finish on Podium" and "Finish (Any
      Position)", earned by where you cross the finish line.
    - Held rungs (`Held-Position Rungs`): "Held 1st" and "Held 3rd" (plus an
      optional "Held 5th"), earned by the best live position you hold DURING the
      race, not just at the line.

    A better result awards every rung at or below it, so winning a race sends all
    of that race's rungs at once. These checks exist mostly to make room for more
    items in the pool (today that means traps; future item packs lean on them
    harder); they never advance adventure progression by themselves. Off means no
    position checks at all, whatever the family toggles say."""
    display_name = "Podium Placement Checks"


class PodiumFinishRungs(DefaultOnToggle):
    """Include the finish-line rungs on each trophy race (needs `Podium Placement
    Checks` on): "Finish on Podium" (cross the line 1st, 2nd or 3rd) and "Finish
    (Any Position)" (just cross the line). Toggle the any-position half separately
    with `Podium: Any-Position Rung`. Off leaves only the held-position rungs, if
    those are on."""
    display_name = "Podium Finish Rungs"


class PodiumAnyPositionRung(DefaultOnToggle):
    """When the finish rungs are on (`Podium Finish Rungs`), also include the
    "Finish (Any Position)" rung on each trophy race, earned by simply crossing the
    finish line. Off keeps only "Finish on Podium" in the finish family. Has no
    effect when `Podium Placement Checks` or `Podium Finish Rungs` is off."""
    display_name = "Podium: Any-Position Rung"


class PodiumHeldRungs(DefaultOnToggle):
    """Include the live-position "held" rungs on each trophy race (needs `Podium
    Placement Checks` on): "Held 1st" and "Held 3rd", earned the moment you hold
    that position on track rather than at the finish. Add a harder "Held 5th" rung
    with `Podium: Held 5th Rung`. Off leaves only the finish-line rungs, if those
    are on."""
    display_name = "Held-Position Rungs"


class PodiumHeldFifthRung(Toggle):
    """Also add a "Held 5th" rung to each trophy race, earned by holding 5th place
    or better at any point. Only has an effect when `Held-Position Rungs` is on.
    Off by default: it is the widest, easiest held rung, kept off to hold the
    item/location pool in balance. Turn it on for 16 extra early checks."""
    display_name = "Podium: Held 5th Rung"


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


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # goal & endgame
    goal: Goal
    oxide_final_challenge_unlock: FinalOxideUnlock
    oxide_final_challenge_relic_count: FinalOxideRelicCount
    # items & pool
    shuffle_gems: ShuffleGems
    include_gem_cups: ShuffleWarpPadsGemCups
    shuffle_keys: ShuffleKeys
    trap_fill_percentage: TrapFillPercentage
    # warp pads: content & destination shuffle
    include_battle_arenas: ShuffleWarpPadsBattleArenas
    warp_pad_shuffle_categories: WarpPadShuffleCategories
    warp_pad_shuffle_grouping: WarpPadShuffleGrouping
    # warp pads: unlock requirements
    warppad_unlock_requirements: WarpPadUnlockRequirements
    two_stage_density: TwoStageDensity
    requirement_variety: RequirementVariety
    requirement_weights: RequirementWeights
    # extra location checks (podium position rungs)
    podium_placement_checks: PodiumPlacementChecks
    podium_finish_rungs: PodiumFinishRungs
    podium_any_position_rung: PodiumAnyPositionRung
    podium_held_rungs: PodiumHeldRungs
    podium_held_fifth_rung: PodiumHeldFifthRung
    # quality of life
    one_lap_cups: OneLapCups
    # deathlink
    death_link: DeathLink
    deathlink_amnesty: DeathLinkAmnesty
    # relic difficulty
    sapphire_relic_progression: SapphireRelicProgression
    gold_relic_progression: GoldRelicProgression
    platinum_relic_progression: PlatinumRelicProgression
    # wired but hidden (single implemented mode; see BUG-D note)
    bossgarage_unlock_requirements: BossGarageRequirements


ap_ctr_option_groups: Dict[str, List[Any]] = {
    "Goal": [Goal, FinalOxideUnlock, FinalOxideRelicCount],
    "Items & Pool": [ShuffleGems, ShuffleWarpPadsGemCups, ShuffleKeys,
                     TrapFillPercentage],
    "Warp Pads": [
        ShuffleWarpPadsBattleArenas,
        WarpPadShuffleCategories,
        WarpPadShuffleGrouping,
        WarpPadUnlockRequirements,
        TwoStageDensity,
        RequirementVariety,
        RequirementWeights,
    ],
    "Extra Checks": [PodiumPlacementChecks, PodiumFinishRungs,
                     PodiumAnyPositionRung, PodiumHeldRungs, PodiumHeldFifthRung],
    "Quality of Life": [OneLapCups],
    "DeathLink": [DeathLink, DeathLinkAmnesty],
    "Relic Difficulty": [SapphireRelicProgression, GoldRelicProgression,
                         PlatinumRelicProgression],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]
