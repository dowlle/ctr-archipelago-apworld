from typing import List, Dict, Any
from dataclasses import dataclass
from worlds.AutoWorld import PerGameCommonOptions
from Options import Choice, OptionGroup, OptionDict, DefaultOnToggle


def create_option_groups() -> List[OptionGroup]:
    option_group_list: List[OptionGroup] = []
    for name, options in ap_ctr_option_groups.items():
        option_group_list.append(OptionGroup(name=name, options=options))

    return option_group_list


class Goal(Choice):
    """
    This will determine what your end goal is.

    oxideonce = Beat Oxide Once: Defeat N. Oxide in his first challenge.
    oxidetwice = Beat Oxide Twice: Collect 18 Relics (Sapphire or Greater) and Defeat N. Oxide a second time.
    oxidetwicefull = 101% Oxide Twice: Collect all 16 Trophies, 5 of each Token, 1 of each Gem, and 18 Relics (Gold or Greater) and Defeat N. Oxide a second time.
    alltrophies = All Trophies: Get all 16 Trophies. No Oxide required!
    allgemcups = All Gem Cups: Complete Every Gem Cup.
    """
    display_name = "Goal"
    option_oxideonce = 0
    option_oxidetwice = 1
    option_oxidetwicefull = 2
    option_alltrophies = 3
    option_allgemcups = 4
    default = 0


class ShuffleRewards(OptionDict):
    """
    Shuffles the rewards into the item pool.
    """
    display_name = "Shuffle Rewards"
    supports_weighting = False
    default = {}
    valid_keys = [ "Trophies", "Sapphire Relics", "Gold Relics", "Platinum Relics", "CTR Race Tokens", "Bonus Round Tokens", "Gems", "Characters", "Boss Keys" ]

class ShuffleWarpPads(Choice):
    """
    Shuffle Warp Pads
    none = Warp Pads will lead to their Vanilla locations.
    main_only = Only Main Track Warp Pads will be shuffled.
    challenge_only = Only Challenge Track Warp Pads will be shuffled.
    gem_only = Only Gem Cup Warp Pads will be shuffled.
    main_and_challenge = Main Track and Challenge Track Warp Pads will be shuffled.
    main_and_gem = Main Track and Gem Cup Warp Pads will be shuffled.
    challenge_and_gem = Challenge Track and Gem Cup Warp Pads will be shuffled.
    all_warppads = All Warp Pads will be shuffled.
    """
    display_name = "Shuffle Warp Pads"
    option_none = 0
    option_main_only = 1
    option_challenge_only = 2
    option_gem_only = 3
    option_main_and_challenge = 4
    option_main_and_gem = 5
    option_challenge_and_gem = 6
    option_all_warppads = 7

class Trophysanity(DefaultOnToggle):
    """
    Every Trophy Race will have a check behind its reward.
    """
    display_name = "Trophysanity"

class Relicsanity(DefaultOnToggle):
    """
    Every Time Trial will have a check behind its reward.
    """
    display_name = "Relicsanity"

class RelicDifficulty(Choice):
    """
    Determines the difficulty of the Relicsanity option. Anything above the selected option will contain junk.
    """
    display_name = "Time Trial Difficulty"
    option_none = 0
    option_sapphire = 1
    option_gold = 2
    option_platinum = 3

class Tokensanity(DefaultOnToggle):
    """
    Every CTR Token Challenge will have a check behind its reward.
    """
    display_name = "Tokensanity"

class Gemsanity(DefaultOnToggle):
    """
    Every Gem will have a check behind its reward.
    """
    display_name = "Gemsanity"

@dataclass
class ctrAPOptions(PerGameCommonOptions):

    goal: Goal
    trophysanity: Trophysanity
    relicsanity: Relicsanity
    relicdifficulty: RelicDifficulty
    tokensanity: Tokensanity
    gemsanity: Gemsanity


ap_ctr_option_groups: Dict[str, List[Any]] = {
    "General Options": [Goal],
    "Shuffle Options": [ShuffleRewards],
    "N. Sanity": [Trophysanity, Relicsanity, RelicDifficulty, Tokensanity, Gemsanity]
}