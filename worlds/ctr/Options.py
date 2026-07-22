from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility)


class Goal(Choice):
    """Determines the player's end goal.

    - **oxide** (default): defeat N. Oxide's Challenge.
    - **oxidefinal**: collect relics, then defeat N. Oxide's Final Challenge.
    - **allbosses**: win all 4 boss races (Ripper Roo, Papu Papu, Komodo Joe, Pinstripe).
    - **allgemcups**: collect all 5 Gems. Requires `Include Gem Cup Warp Pads` on:
      with `Shuffle Gems` off the Gems sit on their own Gem Cups, with it on they
      hide anywhere in the multiworld."""
    # allgemcups + Shuffle Gems on + gem cups excluded would leave the goal's own
    # races out of the seed; that combination fails generation with a clear message.
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
    """Which relics turn Oxide's Challenge into Oxide's Final Challenge. The
    count comes from `Oxide's Final Challenge Relic Count`.

    - **sapphire_relics** (default), **gold_relics**, **platinum_relics**: that
      many relics of that tier.
    - **any_relic_type**: any single tier reaches the count.
    - **total_relics**: all relics added together reach the count.

    Tiers are independent: a Platinum relic does not count toward a Gold
    requirement. Requiring a tier whose progression option is `never` fails
    generation. The old `18_gold_and_platinum_relics` value was removed."""
    # Item-side independence is unrelated to the location-side award-path
    # hierarchy (beating a Platinum time also sends that track's Gold and
    # Sapphire checks) -- that is about checks, not owned relic items.
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
    """How many relics `Oxide's Final Challenge Unlock` requires (1-18). For
    total_relics it is the summed total; for any_relic_type it is the threshold
    any single tier must reach."""
    # Totals above 18 are deliberately not offered (all-relics-slog territory).
    display_name = "Oxide's Final Challenge Relic Count"
    range_start = 1
    range_end = 18
    default = 18
    special_range_names = {"all": 18}


class ShuffleGems(DefaultOnToggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **on** (default): the Gems can appear anywhere; their Gem Cup locations
      become normal checks.
    - **off**: each Gem stays on its own Gem Cup reward (vanilla placement).

    Works with every goal, including `All Gems`."""
    display_name = "Shuffle Gems"


class ShuffleWarpPadsGemCups(DefaultOnToggle):
    """Bring the 5 Gem Cups and their races into the seed: their checks become
    normal locations and, in a randomized-unlock seed, their warp pads get a
    randomized entry requirement.

    - Not the same as `Shuffle Gems`: that moves the Gem items around; this one
      includes the cup races themselves. Must be on for the `All Gems` goal.
    - **off**: cups stay fully vanilla, and shuffled Gems are pinned back onto
      their own cups."""
    # The Key-2 Cups Room hub gate is always kept on top of a randomized cup
    # requirement. This option is also the participation gate for the `cups`
    # destination-shuffle category. Off + Shuffle Gems on pins each Gem back onto
    # its own vanilla cup check (out of the pool) so opted-out cups never hold
    # another world's progression; allgemcups + Shuffle Gems on + this off fails
    # generation with a clear message rather than stranding the goal.
    display_name = "Include Gem Cup Warp Pads"


class ShuffleKeys(DefaultOnToggle):
    """Shuffle the 4 boss Keys into the multiworld item pool.

    - **on** (default): the Keys can appear anywhere; the Boss Race locations
      become normal checks.
    - **off**: each Key stays on its Boss Race reward (vanilla placement)."""
    display_name = "Shuffle Keys"


class TrapFillPercentage(Range):
    """What percentage of this slot's filler items are replaced by traps (Icy
    Road, Low Gravity, No Brakes, Forced Boost, First Person -- each equally
    likely).

      0             = no traps, filler stays Wumpa Fruit
      10  (default) = a taste of sabotage
      100           = every filler slot becomes a trap

    Traps never gate anything. A received trap arms silently and fires mid-race
    on a later lap."""
    # CTR's pool is almost entirely progression, so the filler pool this dial
    # replaces is small; traps substitute filler, never stack onto progression.
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 10


class OneLapCups(Toggle):
    """Make Cup races one lap each instead of the usual three. Off by default.

    Only cup races shorten (including the Gem Cups); single races, boss races,
    relic time trials and CTR Token challenges keep their normal lap count.
    Changes nothing about logic or which locations exist -- everything is just
    faster."""
    # Reuses the engine's built-in one-lap mechanism (the vanilla one-lap
    # cheat), scoped to cups.
    display_name = "One-Lap Cup Races"


class ShuffleWarpPadsBattleArenas(DefaultOnToggle):
    """Bring the 4 Battle Arenas and their Crystal Challenges into the seed:
    their checks become normal locations and, in a randomized-unlock seed, their
    warp pads get a randomized entry requirement.

    - **off**: the arenas are fully out of the seed and never logically
      required -- vanilla gates, vanilla Purple CTR Token rewards, and no
      randomized requirement ever demands Purple tokens. They stay playable.
    - Not the same as `crystals` in `Warp Pad Shuffle Categories`: this puts the
      arenas in the seed at all; that category only shuffles destinations."""
    # The off guarantees, precisely: crystal pads vanilla-fixed and never
    # destination-shuffled; the four Crystal Bonus Round checks keep their
    # vanilla Purple CTR Tokens LOCKED (no other world's item can hide there);
    # randomized requirements never demand Purples directly NOR through an
    # "any tokens" count that only arena play could reach (issue #118).
    display_name = "Include Battle Arena Warp Pads"


class WarpPadShuffleCategories(OptionSet):
    """Which content categories take part in warp-pad destination shuffle. A
    category left out always loads its own content.

    - **tracks**: the 16 trophy races plus Slide Coliseum and Turbo Track.
    - **cups**: the 5 Gem Cups (needs `Include Gem Cup Warp Pads` on).
    - **crystals**: the 4 Battle Arenas (needs `Include Battle Arena Warp Pads` on).

    Default: all three. Empty set: no destination shuffle. Under vanilla unlock
    requirements, tracks and crystals shuffle within themselves and cups stay
    fixed."""
    # Composed with `Warp Pad Shuffle Grouping`. The vanilla-unlock collapse in
    # full: tracks = races only (no trials), grouping forced per_category,
    # cup/trial destination shuffle requires a randomized unlock mode.
    display_name = "Warp Pad Shuffle Categories"
    valid_keys = {"tracks", "cups", "crystals"}
    default = frozenset({"tracks", "cups", "crystals"})


class WarpPadShuffleGrouping(Choice):
    """How the categories in `Warp Pad Shuffle Categories` are pooled for
    destination shuffle.

    - **merged** (default): one cross-category pool -- a track slot can load a
      cup or crystal and vice versa. Needs a randomized unlock mode.
    - **per_category**: each category shuffles only within itself.

    Has no effect when fewer than two categories participate."""
    display_name = "Warp Pad Shuffle Grouping"
    option_per_category = 0
    option_merged = 1
    default = 1


class WarpPadUnlockRequirements(Choice):
    """How warp pads unlock -- the heart of the randomizer.

    - **randomized** (default): every warp pad gets a randomized entry
      requirement (trophies, tokens, relics, keys, gems...), always collectable
      before that pad opens.
    - **vanilla**: pads open on their vanilla trophy counts, like the original
      adventure.
    - **random_without_4_keys**: like randomized, but the 4 boss Keys are never
      pad requirements."""
    # "Always collectable" is enforced by the solvability-proven sphere search
    # at generation time.
    display_name = "Warp Pad Unlock Requirements"
    option_vanilla = 0
    option_randomized = 1
    option_random_without_4_keys = 2
    default = 1


class TwoStageDensity(Choice):
    """How many trophy pads carry a real second-stage gate, meaning an extra
    requirement on the pad's CTR Challenge and relic Time Trials on top of
    winning the Trophy Race. Only affects the randomized warp pad modes.

    - **off**: no second gates.
    - **light**: a few per seed (up to 4).
    - **standard** (default): the tuned shipping behaviour (up to 6).
    - **deep**: layered progression (up to 10).
    - **full**: every pad that can carry one gets one (up to 16).

    Also accepts `random`. The densest settings can generate slower on
    maxed-out configs."""
    # Higher density puts more ordering pressure on AP's fill. Solo generation
    # is protected by the terminal rollback backstop. At non-standard densities
    # an internal diversity discount nudges repeat requirement families (mostly
    # Trophies) toward variety, so extra gates do not all come out
    # Trophy-shaped. full = no random collapse.
    display_name = "Two-Stage Gate Density"
    option_off = 0
    option_light = 1
    option_standard = 2
    option_deep = 3
    option_full = 4
    default = 2


class RequirementVariety(Choice):
    """Weight preset for randomized warp-pad requirements (randomized modes
    only).

    - **icebound_beta5** (default): Icebound's rebalanced weights -- still
      trophy-leaning, with more token, relic and key variety.
    - **trophy_heavy_legacy**: the previous, more trophy-dominated weights.
    - **custom**: use the weights from `Requirement Weights`."""
    # The exact tables: icebound_beta5 = Trophy 90, each CTR Token 16 (Purple
    # 12), each Relic tier 18, Key 20, each Gem 4; Any* collapse Token x0.8
    # (cap 16), Relic x0.5 (cap 27), Gem capped at 5 (no -1 reduction).
    # trophy_heavy_legacy = Trophy 100, Token 15 (Purple 10), Relic 20, Key 25,
    # Gem 2; Any* collapse Token x0.6, Relic x0.3, Gem -1 (no caps). custom
    # falls back to trophy_heavy_legacy weights for unlisted items and uses the
    # legacy Any* collapse.
    display_name = "Requirement Variety"
    option_icebound_beta5 = 0
    option_trophy_heavy_legacy = 1
    option_custom = 2
    default = 0


class RequirementWeights(OptionDict):
    """Roll your own requirement mix. Used only when `Requirement Variety` =
    custom. Each entry is `item name: weight` -- higher weight means picked more
    often; 0 disables an item, except Trophy, which must stay above 0. Items you
    leave out keep their default weight.

    Example:

        requirement_variety: custom
        requirement_weights:
          Trophy: 30
          Key: 40
          Sapphire Relic: 40

    Valid keys: Trophy, Key, the five CTR Token colours, the three Relic tiers,
    and the five Gem colours."""
    # Trophy must stay above 0 because it bootstraps the randomized warp-pad
    # requirements. Unlisted items fall back to their trophy_heavy_legacy
    # weight (see RequirementVariety's comment for the tables).
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
    with 4, 8, 12, 16 trophies respectively."""
    # HIDDEN from the YAML template and options page: `trophies` is currently
    # the only implemented mode, so there is nothing to choose. The option (and
    # its slot_data key `bossgarage_mode`) stays wired for when the track-based
    # modes return.
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
    """Share your wipeouts with the other DeathLink players, and take theirs.

    - **off** (default): disabled.
    - **mask_reset**: send a death only when the mask carries you back, meaning
      you fell off the track or were eaten. Low frequency.
    - **any_hit**: also send on every hit that lands on you (spin-out, blast,
      squish, burn). Much higher frequency, so pair it with `DeathLink Amnesty`.

    Receiving a death always forces the full mask reset on you. Only
    adventure-mode races send."""
    # A received death never triggers an outgoing one (no ping-pong). Type
    # rationale: AP core ships DeathLink as an on/off Toggle; CTR uses a 3-value
    # Choice because the send tiers are a real gameplay difference, and a
    # separate toggle would permit "any_hit but do not send", which is not a
    # supported mode. off mirrors 0 into slot_data, matching the Toggle
    # convention native keys off.
    display_name = "DeathLink"
    option_off = 0
    option_mask_reset = 1
    option_any_hit = 2
    default = 0


class DeathLinkAmnesty(Range):
    """How many of your deaths must pile up before one is actually sent. 1
    (default) sends every death; N sends one per N. Meant for the `any_hit`
    tier. Incoming deaths are unaffected -- amnesty only throttles what you
    send."""
    # Does nothing useful at mask_reset (those wipeouts are already rare) and
    # is inert while DeathLink is off.
    display_name = "DeathLink Amnesty"
    range_start = 1
    range_end = 30
    default = 1


class PodiumPlacementChecks(DefaultOnToggle):
    """Add finishing-position checks to the 16 adventure trophy races -- the
    master switch for the podium-rung feature.

    - Finish rungs (`Podium Finish Rungs`): earned by where you cross the line.
    - Held rungs (`Held-Position Rungs`): earned by the best position you hold
      during the race.

    A better result awards every rung at or below it. These checks make room
    for more items in the pool; they never advance adventure progression."""
    # Up to five rungs per race across the two families. The pool room is what
    # traps live in today; future item packs lean on these harder.
    display_name = "Podium Placement Checks"


class PodiumFinishRungs(DefaultOnToggle):
    """Include the finish-line rungs on each trophy race (needs `Podium
    Placement Checks` on): "Finish on Podium" (top 3) and "Finish (Any
    Position)". Toggle the any-position half with `Podium: Any-Position
    Rung`."""
    display_name = "Podium Finish Rungs"


class PodiumAnyPositionRung(DefaultOnToggle):
    """Also include the "Finish (Any Position)" rung on each trophy race, earned
    by simply crossing the finish line. Off keeps only "Finish on Podium". Needs
    `Podium Finish Rungs` on."""
    display_name = "Podium: Any-Position Rung"


class PodiumHeldRungs(DefaultOnToggle):
    """Include the live-position "held" rungs on each trophy race (needs `Podium
    Placement Checks` on): "Held 1st" and "Held 3rd", earned the moment you hold
    that position on track. Add "Held 5th" with `Podium: Held 5th Rung`."""
    display_name = "Held-Position Rungs"


class PodiumHeldFifthRung(Toggle):
    """Also add a "Held 5th" rung to each trophy race, earned by holding 5th
    place or better at any point. Needs `Held-Position Rungs` on. Off by
    default; turn it on for 16 extra early checks."""
    # The widest, easiest held rung -- kept off by default to hold the
    # item/location pool in balance.
    display_name = "Podium: Held 5th Rung"


class SapphireRelicProgression(NamedRange):
    """How often progression may sit behind a Sapphire relic-race time (the
    easiest tier). Per-location % chance over the 18 Sapphire Time Trials; a
    location that misses the roll keeps its vanilla Sapphire Relic and never
    gates progression. 0 = never, 100 = full (default). Also accepts `random`.

    The three tiers are a skill ladder (sapphire easy, platinum hard); setting
    an easier tier lower than a harder one gives inverted difficulty."""
    display_name = "Sapphire Relic Progression"
    range_start = 0
    range_end = 100
    default = 100
    special_range_names = {"never": 0, "full": 100}


class GoldRelicProgression(NamedRange):
    """How often progression may sit behind a Gold relic-race time (the medium
    tier). Per-location % chance over the 18 Gold Time Trials; a location that
    misses the roll keeps its vanilla Gold Relic. 0 = never, 100 = full
    (default). Also accepts `random`. See `Sapphire Relic Progression` for the
    skill-ladder note."""
    display_name = "Gold Relic Progression"
    range_start = 0
    range_end = 100
    default = 100
    special_range_names = {"never": 0, "full": 100}


class PlatinumRelicProgression(NamedRange):
    """How often progression may sit behind a Platinum relic-race time (the
    hardest, expert-only tier). Per-location % chance over the 18 Platinum Time
    Trials; a location that misses the roll keeps its vanilla Platinum Relic.
    0 = never (default, so a needed item never sits behind a platinum-only
    time), 100 = full. Also accepts `random`."""
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
