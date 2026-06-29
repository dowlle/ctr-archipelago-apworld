from typing import List, Dict, Any
from dataclasses import dataclass
from Options import Choice, OptionGroup, OptionDict, DefaultOnToggle, Toggle, NamedRange, PerGameCommonOptions


class Goal(Choice):
    """Determines the player's end goal.

    - **oxide:** N. Oxide's Challenge - Defeat N. Oxide's Challenge.
    - **oxidefinal:** N. Oxide's Final Challenge - Collect 18 Relics (Sapphire or Greater) and Defeat N. Oxide's Final Challenge.
    - **everythingplusone:** 101% - Collect all 16 Trophies, 5 of each Token, 1 of each Gem, and 18 Relics (Gold or Greater) and Defeat N. Oxide's Final Challenge.
    - **allbosses:** All Bosses - Win all 5 boss challenges.
    - **allgemcups:** All Gem Cups - Complete Every Gem Cup."""
    display_name = "Goal"
    option_oxide = 0
    option_oxidefinal = 1
    option_everythingplusone = 2
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


class ShuffleRewards(OptionDict):
    """DEPRECATED — no longer wired. Kept only so older YAMLs that still set
    `Shuffle Rewards` (with the old `Include Platinum Relics`/`Include Gems`/
    `Include Keys` keys) keep generating instead of erroring.

    The three concerns it used to cover are now first-class options:
      - "Include Platinum Relics" -> `Platinum Relic Progression` slider
        (slider = 0 already means "platinum relics not shuffled").
      - "Include Gems"            -> `Shuffle Gems` toggle.
      - "Include Keys"            -> `Shuffle Keys` toggle.

    `valid_keys` is intentionally empty so ANY leftover key parses without a
    validation error (the dict is simply ignored). Remove after a deprecation
    window."""
    display_name = "Shuffle Rewards (deprecated)"
    supports_weighting = False
    default = {}
    valid_keys = []


class ShuffleGems(Toggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **off** (default): each Gem is pinned to its own Gem Cup reward location
      (vanilla placement, out of the multiworld shuffle).
    - **on**: the 5 Gems enter the shuffled pool and can appear anywhere; their
      Gem Cup locations become normal checks holding whatever the fill places.

    The `All Gem Cups` goal ALWAYS pins the Gems to their cups regardless of this
    toggle (they are the goal items)."""
    display_name = "Shuffle Gems"


class ShuffleKeys(Toggle):
    """Shuffle the 4 boss Keys into the multiworld item pool.

    - **off** (default): each Key is pinned to its Boss Race reward location
      (vanilla placement, out of the multiworld shuffle).
    - **on**: the 4 Keys enter the shuffled pool and can appear anywhere; the
      Boss Race locations become normal checks holding whatever the fill places."""
    display_name = "Shuffle Keys"


class ShuffleWarpPads(Toggle):
    """Shuffle Warp Pads.

    Includes regular races, Slide Coliseum, and Turbo Track."""
    display_name = "Shuffle Warp Pads"


class ShuffleWarpPadsBattleArenas(Toggle):
    """Shuffled Warp Pads include Battle Arenas and their Crystal Challenges.

    Does nothing if `Shuffle Warp Pads` is off."""
    display_name = "Include Battle Arena Warp Pads"


class ShuffleWarpPadsGemCups(Toggle):
    """Shuffled Warp Pads include Gem Cups and their tounaments.

    Does nothing if `Shuffle Warp Pads` is off."""
    display_name = "Include Gem Cup Warp Pads"


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
    are not shuffled."""
    display_name = "Boss Garage Requirements"
    option_original_4_tracks = 0
    option_same_hub_tracks = 1
    option_trophies = 2
    default = 2


class AutoUnlockCtrChallengeRelicRace(Toggle):
    """Makes the second stage unlock to always free, making the CTR Challenge and
    Relic Race available immediately after beating that warp pad's trophy race."""
    display_name = "Auto-unlock CTR Challenge & Relic Race"


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
    shuffle_rewards: ShuffleRewards  # deprecated, unwired (backward-compat only)
    shuffle_gems: ShuffleGems
    shuffle_keys: ShuffleKeys
    shuffle_warp_pads: ShuffleWarpPads
    include_battle_arenas: ShuffleWarpPadsBattleArenas
    include_gem_cups: ShuffleWarpPadsGemCups
    warppad_unlock_requirements: WarpPadUnlockRequirements
    requirement_variety: RequirementVariety
    requirement_weights: RequirementWeights
    bossgarage_unlock_requirements: BossGarageRequirements
    autounlock_ctrchallenge_relicrace: AutoUnlockCtrChallengeRelicRace
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
        ShuffleWarpPads,
        ShuffleWarpPadsBattleArenas,
        ShuffleWarpPadsGemCups,
        WarpPadUnlockRequirements,
        RequirementVariety,
        RequirementWeights,
        AutoUnlockCtrChallengeRelicRace,
        BossGarageRequirements,
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