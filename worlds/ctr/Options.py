from typing import List, Dict, Any
from dataclasses import dataclass
from Options import Choice, OptionGroup, OptionDict, DefaultOnToggle, Toggle, PerGameCommonOptions


class Goal(Choice):
    """
    This will determine what your end goal is.

    oxide = N. Oxide's Challenge: Defeat N. Oxide's Challenge.
    oxidefinal = N. Oxide's Final Challenge: Collect 18 Relics (Sapphire or Greater) and Defeat N. Oxide's Final Challenge.
    everythingplusone = 101%: Collect all 16 Trophies, 5 of each Token, 1 of each Gem, and 18 Relics (Gold or Greater) and Defeat N. Oxide's Final Challenge.
    allbosses = All Bosses: Win all 5 boss challenges.
    allgemcups = All Gem Cups: Complete Every Gem Cup.
    """
    display_name = "Goal"
    option_oxide = 0
    option_oxidefinal = 1
    option_everythingplusone = 2
    option_allbosses = 3
    option_allgemcups = 4
    default = 0


class RelicTime(Choice):
    """
    Choose the required minimum relic time to beat to get any prizes.
    If you choose Gold or Platinum as minimum time, then upon reaching that
    time the lower rank prize(s) will also be awarded.
    """
    display_name = "Relic Races: Required Minimum Time"
    option_sapphire = 0
    option_gold = 1
    option_platinum = 2
    default = 0


class RelicsRequirePerfect(Toggle):
    """
    If turned on, to get one or more prizes from a relic race, not only do the
    relic times need to be bested, but all time boxes have to be broken during
    that run as well.
    """
    display_name = "Relic Races Require Perfects"


class FinalOxideUnlock(Choice):
    """
    Choose what types of relics are required to turn Oxide's Challenge into
    Oxide's Final Challenge.
    18 Sapphire Relics: You need all 18 Sapphire relics (Golds and Platinums are ignored).
    18 Gold+Platinum Relics: You need at least a combined total of 18 Gold relics and Platinum relics.
    """
    display_name = "Oxide's Final Challenge Unlock"
    option_18_sapphire_relics = 0
    option_18_gold_and_platinum_relics = 1
    default = 0


class ShuffleRewards(OptionDict):
    """
    Shuffles the rewards into the item pool.
    Trophies, CTR Tokens, Sapphire & Gold Relics are always shuffled.
    If Platinum Relics are not shuffled, then logic won't expect beating the
    platinum times in Relic Races.
    """
    display_name = "Shuffle Rewards"
    supports_weighting = False
    default = {}
    valid_keys = [
        "Include Platinum Relics",
        "Include Gems",
        "Include Keys"
    ]


class ShuffleWarpPads(Toggle):
    """
    Shuffle Warp Pads.
    Includes regular races, Slide Coliseum, and Turbo Track.
    """
    display_name = "Shuffle Warp Pads"


class ShuffleWarpPadsBattleArenas(Toggle):
    """
    Shuffled Warp Pads include Battle Arenas and their Crystal Challenges.
    Does nothing if `Shuffle Warp Pads` is off.
    """
    display_name = "Include Battle Arena Warp Pads"


class ShuffleWarpPadsGemCups(Toggle):
    """
    Shuffled Warp Pads include Gem Cups and their tounaments.
    Does nothing if `Shuffle Warp Pads` is off.
    """
    display_name = "Include Gem Cup Warp Pads"


class WarpPadUnlockRequirements(Choice):
    """
    Choose the requirements for opening warp pads.
    """
    diplay_name = "Warp Pad Unlock Requirements"
    option_vanilla = 0
    option_random = 1
    option_random_without_4_keys = 2
    default = 0


class BossGarageRequirements(Choice):
    """
    Choose the requirements for opening boss garages.
    `Original 4 Tracks` and `Same Hub Tracks` behave identically if warp pads
    are not shuffled.
    `Trophies` sets the requirements for Roo, Papu, Joe and Pinstripe to
    4, 8, 12, 16 trophies respectively.
    """
    diplay_name = "Boss Garage Requirements"
    option_original_4_tracks = 0
    option_same_hub_tracks = 1
    option_trophies = 2
    default = 2


class AutoUnlockCtrChallengeRelicRace(Toggle):
    """
    Makes the second stage unlock to always free, making the CTR Challenge and
    Relic Race available immediately after beating that warp pad's trophy race.
    """
    display_name = "Auto-unlock CTR Challenge & Relic Race"


class SkipMaskHints(DefaultOnToggle):
    """
    Sets all adventure mode mask hint cutscenes as 'already seen', effectively skipping them.
    """
    display_name = "Skip Mask Hints"


class AutoskipPodiumCutscenes(Toggle):
    """
    Automatically inputs the Start-button at the start of each podium cutscene,
    effectively skipping it.
    """
    display_name = "Auto-Skip Podium Cutscenes"


class SkipMaskCongrats(Toggle):
    """
    The voice clips of masks will be muted, making it behave as if the
    PAL-exclusive language glitch was active.
    """
    display_name = "Skip Mask Congrats"


class HelperTiziano(Toggle):
    """
    Modifies the item boxes while performing the 'Tiziano' shortcut.
    During regular races on Papu's Pyramid, if the player is in 7th or 8th place,
    every item box is a guaranteed mask item.
    """
    display_name = "Tiziano Helper"


class HelperTA(Toggle):
    """
    Modifies the item boxes while performing the 'TA' super-shortcut.
    During regular races on Tiny Arena, if the player is in 1st place,
    every item box is a guaranteed TNT/Nitro item.
    """
    display_name = "TA Helper"


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # general
    goal: Goal
    rr_required_minimum_time: RelicTime
    rr_require_perfects: RelicsRequirePerfect
    oxide_final_challenge_unlock: FinalOxideUnlock
    # randomization
    shuffle_rewards: ShuffleRewards
    shuffle_warp_pads: ShuffleWarpPads
    include_battle_arenas: ShuffleWarpPadsBattleArenas
    include_gem_cups: ShuffleWarpPadsGemCups
    warppad_unlock_requirements: WarpPadUnlockRequirements
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
        ShuffleRewards,
        ShuffleWarpPads,
        ShuffleWarpPadsBattleArenas,
        ShuffleWarpPadsGemCups,
        WarpPadUnlockRequirements,
        AutoUnlockCtrChallengeRelicRace,
        BossGarageRequirements,
    ],
    "Quality of Life": [SkipMaskHints, AutoskipPodiumCutscenes, SkipMaskCongrats],
    "Tricks": [HelperTiziano, HelperTA],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]