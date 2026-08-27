from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility)

from .warp_pad_logic import DEFAULT_REQUIREMENT_WEIGHTS
from .traps import (DEFAULT_TRAP_WEIGHTS, TRAP_WEIGHT_KEYS,
                    validate_trap_weights)


class OxideGoal(Choice):
    """What finishing the game means.

    - **any_percent** (default): beat Oxide, the retail ending.
    - **101_percent**: beat Oxide's Final Challenge, the full-completion
      ending.
    - **none**: Oxide is not part of the goal at all.

    Combine it with Bosses Required and Gems Required to build the goal you
    want; every condition you set must be met."""
    display_name = "Oxide Goal"
    option_none = 0
    option_any_percent = 1
    option_101_percent = 2
    # The old spellings keep working, so a YAML written before the rename
    # loads unchanged. The integers are frozen: slot_data's goal_oxide and the
    # native parser (ap_verify.c, ap_hooks.c) read the number, never the name,
    # so renaming the values costs nothing on the wire.
    alias_first = 1
    alias_final = 2
    default = 1


class BossesRequiredGoal(Range):
    """How many of the 4 boss races you must win for the goal.

    Ripper Roo, Papu Papu, Komodo Joe and Pinstripe. 0 (default) turns this
    condition off.

    "Won" means you actually beat the boss - holding trophies or garage Keys
    does not count. Combines with Oxide Goal and Gems Required; every
    condition you set must be met."""
    display_name = "Bosses Required Goal"
    range_start = 0
    range_end = 4
    default = 0


class GemsRequiredGoal(Range):
    """How many of the 5 Gems you must hold for the goal.

    0 (default) turns this condition off. Combines with Oxide Goal and Bosses
    Required; every condition you set must be met.

    If you ask for Gems with Shuffle Gems on, you also need Include Gem Cup
    Warp Pads on - otherwise the Gems would sit on cups the seed left out.
    Generation says so rather than handing you an unwinnable seed."""
    display_name = "Gems Required Goal"
    range_start = 0
    range_end = 5
    default = 0


class FinalOxideUnlock(Choice):
    """Which relics turn Oxide's Challenge into Oxide's Final Challenge. The
    count comes from `Oxide's Final Challenge Relic Count`.

    - **sapphire_relics** (default), **gold_relics**, **platinum_relics**: that
      many relics of that tier.
    - **any_relic_type**: any single tier reaches the count.
    - **total_relics**: all relics added together reach the count.

    Tiers are independent: a Platinum relic does not count toward a Gold
    requirement. Requiring a tier whose relic count is 0 fails generation.
    The old `18_gold_and_platinum_relics` value was removed."""
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
    """How many relics `Oxide's Final Challenge Unlock` requires.

    - **total_relics** supports 1-54 by adding Sapphire, Gold and Platinum.
    - Every other mode supports 1-18 because it checks one 18-item tier.

    Values above 18 with a non-total mode fail generation clearly instead of
    producing an impossible goal."""
    display_name = "Oxide's Final Challenge Relic Count"
    range_start = 1
    range_end = 54
    default = 18
    special_range_names = {"all": 18}


class ShuffleGems(DefaultOnToggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **on** (default): the Gems can appear anywhere; their Gem Cup locations
      become normal checks.
    - **off**: each Gem stays on its own Gem Cup reward (vanilla placement).

    Works with every goal, including a Gems Required goal."""
    display_name = "Shuffle Gems"


class ShuffleWarpPadsGemCups(DefaultOnToggle):
    """Bring the 5 Gem Cups and their races into the seed: their checks become
    normal locations and, in a randomized-unlock seed, their warp pads get a
    randomized entry requirement.

    - Not the same as `Shuffle Gems`: that moves the Gem items around; this one
      includes the cup races themselves. It must be on when a shuffled Gem is
      required for your goal.
    - **off**: cups stay fully vanilla, and shuffled Gems are pinned back onto
      their own cups."""
    # The Key-2 Cups Room hub gate is always kept on top of a randomized cup
    # requirement. This option is also the participation gate for the `cups`
    # destination-shuffle category. Off + Shuffle Gems on pins each Gem back onto
    # its own vanilla cup check (out of the pool) so opted-out cups never hold
    # another world's progression; allgemcups + Shuffle Gems on + this off fails
    # generation with a clear message rather than stranding the goal.
    display_name = "Include Gem Cup Warp Pads"


class RandomizeGemCupTracks(Toggle):
    """Shuffle which four tracks each Gem Cup runs.

    The retail Gem Cups always run the same four tracks. Turn this on and
    every leg is drawn independently from the 16 trophy tracks. A track may
    appear more than once, while Slide Coliseum and Turbo Track are not drawn.

    The cup still awards its Gem. Only the tracks change."""
    # Ruled 2026-08-07 (issue #166): exactly two states, vanilla or
    # completely random over the 16-trophy-track pool, repeats allowed; the
    # reporter's intermediate "shuffled" permutation mode was dropped. Wire:
    # top-level `gem_cup_legs` block, emitted only when on.
    display_name = "Randomize Gem Cup Tracks"


class ShuffleKeys(DefaultOnToggle):
    """Shuffle the 4 boss Keys into the multiworld item pool.

    - **on** (default): the Keys can appear anywhere; the Boss Race locations
      become normal checks.
    - **off**: each Key stays on its Boss Race reward (vanilla placement)."""
    display_name = "Shuffle Keys"


class ProgressiveBoostMode(Choice):
    """Turn your kart's boost into something you have to find.

    Normally every kart can boost from the start. Switch this on and boost
    arrives from the multiworld in stages: ordinary boost first, then Ultra
    Sacred Fire. If Blue Fire is also on, one final Retro Fueled-style tier
    turns turbo pads into Blue Fire pads, lets powerslides stack its reserves,
    preserves reserves through U-turns, and turns the exhaust blue.

    Some checks genuinely need the speed and stay out of reach until it
    arrives. Hot Air Skyway is the clearest case - its mid-track climb
    cannot be cleared below USF.

    - **off** (default): every kart boosts normally, as in the retail game.
    - **shared_global**: one boost ladder, shared by every character.
    - **per_character**: each of the 16 racers has their own ladder. That is
      sixteen times as many items, so the seed needs plenty of places to put
      them; if there is not enough room, generation stops and says so.

    per_character means 16 racers x 2 copies (3 with Blue Fire) = 32 to 48
    Progressive Boost items by itself; add per_character Progressive Stats
    too and the two packs together reach up to 16 x (3 boost + 12 stat
    copies) = 240 progressive items (224 without Blue Fire). A solo game
    returns every pool item to you, so most of your checks in a
    per_character seed will hand back a progressive item rather than
    something else."""
    # Classification: `useful` (the spine-1 shape) while this option is off,
    # `progression` in every seed that randomizes the chain. It started
    # per-seed -- #145's Turbo checks and #109's boost-gated box slots were
    # the only readers -- but the USF finish gate (usf_finish.py) reads it on
    # a static location, so create_item now upgrades it unconditionally
    # (logic state never tracks useful items).
    display_name = "Progressive Boost"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


class ProgressiveBoostBlueFire(Toggle):
    """Add a Retro Fueled-style Blue Fire tier after Ultimate Sacred Fire.

    The final Progressive Boost turns turbo pads into Blue Fire pads with one
    second of reserves. Powerslides can stack those reserves without losing
    Blue Fire, U-turns retain reserves, and active Blue Fire exhaust is blue.

    - **off** (default): the ladder stops at USF.
    - **on**: one more tier, so one more Progressive Boost to find.

    No effect while Progressive Boost is off."""
    display_name = "Progressive Boost: Blue Fire"


class LogicDifficulty(Choice):
    """How much the logic expects you to be able to do.

    It only applies while both Progressive Boost and Itemsanity are
    randomizing your capabilities.

    - **easy**: winning a race, finishing on the podium and holding first
      all wait until you have boost or a couple of decent weapons.
    - **medium** (default): only winning the race waits. Placement checks
      stay available.
    - **hard**: no extra requirement; you are expected to manage.

    Tracks whose geometry genuinely demands speed ignore this setting.
    Cortex Castle and Hot Air Skyway always need USF, and so does Oxide
    Station unless Shortcut Knowledge is set to hard."""
    display_name = "Logic Difficulty"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 1


class ProgressiveStatsMode(Choice):
    """Turn your kart's top speed, acceleration and turning into items.

    Every kart starts at the bottom of all three and climbs as the stats
    arrive. The ladder reaches beyond the retail maximum at the top end.

    - **off** (default): karts keep their normal stats.
    - **shared_global**: one set of stat ladders, shared by every character.
    - **per_character**: a separate set for each of the 16 racers. Sixteen
      times as many items, so the seed needs the room to hold them.

    per_character means 16 racers x 3 chains x 4 copies = 192 Progressive
    Stats items by itself; add per_character Progressive Boost too and the
    two packs together reach up to 16 x (3 boost + 12 stat copies) = 240
    progressive items (224 without Blue Fire). A solo game returns every
    pool item to you, so most of your checks in a per_character seed will
    hand back a progressive item rather than something else."""
    display_name = "Progressive Stats"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


class TrapFillPercentage(Range):
    """What percentage of this slot's filler items are replaced by traps.

      0             = no traps, filler stays Wumpa Fruit
      10  (default) = a taste of sabotage
      100           = every filler slot becomes a trap

    Which trap you get is decided by `Trap Weights`.

    Traps never gate anything. A received trap arms silently and fires mid-race
    on a later lap."""
    # CTR's pool is almost entirely progression, so the filler pool this dial
    # replaces is small; traps substitute filler, never stack onto progression.
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 10


class TrapWeights(OptionDict):
    """How often each trap is picked, once `Trap Fill Percentage` has decided
    that a filler slot becomes a trap.

    Each entry is `trap: weight`. Higher weight means picked more often, 0
    means never picked. The numbers are relative and do not have to add up to
    anything. Traps you leave out keep their default weight, so you only have
    to list the ones you want to change.

    This option is a mapping, not a single value, so you have to edit it by
    hand. The Archipelago website's options pages cannot show a mapping: this
    option does not appear on them at all, and a YAML you export from there
    has no `trap_weights` block, which means every trap keeps its default
    weight. The downloadable YAML template does contain the full block, so the
    simplest route is to start from the template and edit the numbers.

    Example - never pick first person, pick icy road twice as often as usual,
    everything else default::

        trap_fill_percentage: 10
        trap_weights:
          first_person: 0
          icy_road: 10

    All 19 listed traps have a working native effect in this build and can be
    picked. Setting every trap to 0 while `Trap Fill Percentage` is above 0
    is an error, because then no trap could be picked at all.

    Valid keys: icy_road, low_gravity, forced_usf, forced_boost, first_person,
    wumpa_wipeout, flatten, item_reroll, forced_use, empty_crates,
    weakened_kart, boost_blocker, wireframe, nitro, reverse_steering,
    red_potion, upside_down, mirror_mode, warpball_ambush."""
    # Machine keys, not item names: the 0.2.0 rework renamed five traps, and a
    # name-keyed option would have invalidated every YAML that mentioned one.
    # The defaults live in traps.DEFAULT_TRAP_WEIGHTS (the reviewed table)
    # rather than here, so one registry owns names, keys and weights together.
    #
    # default is the FULL table, not {}: OptionDict renders its default into
    # the generated YAML template, and an empty default would document the
    # option as "write your own" while hiding the numbers a player is actually
    # editing away from.
    display_name = "Trap Weights"
    supports_weighting = False
    default = dict(DEFAULT_TRAP_WEIGHTS)
    valid_keys = list(TRAP_WEIGHT_KEYS)

    def verify_keys(self) -> None:
        # Core's VerifyKeys already rejects unknown keys, but with a message
        # that only lists the allowed set. This one names the CTR option, says
        # what the keys are, and range-checks the values -- and it is the same
        # function generate_early calls, so a rolled YAML and a
        # programmatically built world fail identically.
        validate_trap_weights(self.value)


class Itemsanity(Toggle):
    """Turn weapons into items you have to unlock.

    Until a weapon arrives from the multiworld you cannot get it from a crate
    - the roulette hands you Wumpa Fruit instead. Using each weapon for the
    first time is itself a check, and using one while holding ten fruit is a
    second.

    It changes how the whole game plays, not just what you collect."""
    display_name = "Itemsanity"

class Lettersanity(Choice):
    """Turn the C-T-R letters into checks, items, or both.

    Every track hides the three letters that spell CTR. Normally collecting
    all three wins you a token.

    - **off** (default): letters work as they do in the retail game.
    - **locations_only**: collecting a letter is a check.
    - **locations_and_items**: collecting one is a check, and the letters
      themselves also arrive from the multiworld.
    - **items_only**: letters arrive as items and are not checks."""
    display_name = "Lettersanity"
    option_off = 0
    option_locations_only = 1
    option_locations_and_items = 2
    option_items_only = 3
    default = 0

class LettersPerTrack(Range):
    """How many of each track's three letters are used.

    Lower it to shorten location-bearing Lettersanity modes. The seed randomly
    chooses this many of each track's C, T, and R locations; at 3 all count.

    This does not reduce **items_only**, which uses all 48 letter items and no
    letter locations. It has no effect while Lettersanity is off."""
    display_name = "Letters Per Track"
    range_start = 1
    range_end = 3
    default = 3


class TiziHelper(Toggle):
    """Guarantee a Mask on the crate row before Papu's Pyramid's tricky jump.

    That jump is the single most common run-ender on the track. With this on,
    the crate row just before it always contains an Aku Aku mask, so a clean
    run is not decided by a coin flip.

    With Itemsanity on you also need to have unlocked the Mask for it to
    appear."""
    display_name = "Tizi Helper"


class WumpaBundles(Toggle):
    """Let filler contain bundles of Wumpa Fruit.

    Small bundles give 3 fruit and big bundles fill your kart to 10. Plain
    single-fruit filler remains the most common result. This adds variety to
    existing filler slots; it does not add items or locations."""
    display_name = "Wumpa Bundles"


class ProgressiveStartingWumpa(Range):
    """How many Progressive Starting Wumpa items to add.

    Each one permanently raises the fruit you start every race with by one.
    0 (default) keeps the retail zero-fruit start; 10 fills your kart at the
    start of every race. These items use slots that would otherwise be
    filler and add no locations of their own."""
    display_name = "Progressive Starting Wumpa"
    range_start = 0
    range_end = 10
    default = 0


class WumpaCheck(Toggle):
    """Add one check for reaching 10 Wumpa Fruit during a race.

    This is one global location for the whole seed, not one per track. It is
    separate from Itemsanity's juiced weapon checks: this pays out when you
    reach 10 fruit, while those pay out when you fire a weapon at 10."""
    display_name = "Wumpa Check"


class TurboGrant(Toggle):
    """Add one useful item that puts a Turbo into your weapon slot.

    If you are outside a race or your slot is occupied, it waits until it can
    be delivered. With Itemsanity on, it also waits for the Turbo weapon to be
    unlocked. Progressive Boost still controls how strong the fired Turbo is.
    This uses one filler slot and adds no location."""
    display_name = "Turbo Grant"


class BoxLocations(Toggle):
    """Turn item boxes on the track into checks.

    Around 240 weapon crates across the game become Archipelago locations.
    Drive through one in any Adventure race on that track and it pays out.

    Boxes are the densest source of checks in the game, so this makes for a
    much longer seed. Some sit past jumps or shortcuts you need boost for -
    Shortcut Knowledge decides how much the logic expects of you there."""
    display_name = "Item Box Locations"


class ShortcutKnowledge(Choice):
    """How much shortcut skill the logic assumes you have.

    Higher settings expect you to take routes that need boost, precise jumps
    or wall rides, so checks behind them come into reach sooner and the seed
    asks more of you.

    - **easy** (default): only shortcuts anyone can take.
    - **medium**: the well-known ones.
    - **hard**: everything, including the routes that need Ultimate Sacred Fire.

    Mostly matters with Item Box Locations on, since that is where most of
    the shortcut-gated checks live."""
    display_name = "Shortcut Knowledge"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 0


class OneLapCups(DefaultOnToggle):
    """Make Cup races one lap each instead of the usual three. On by default.

    Only cup races shorten (including the Gem Cups); single races, boss races,
    relic time trials and CTR Token challenges keep their normal lap count.
    Changes nothing about logic or which locations exist - everything is just
    faster."""
    # Reuses the engine's built-in one-lap mechanism (the vanilla one-lap
    # cheat), scoped to cups.
    display_name = "One-Lap Cup Races"


class ShuffleWarpPadsBattleArenas(DefaultOnToggle):
    """Include the 4 Battle Arenas and their Crystal Challenges.

    Their checks become normal locations, and in a randomized-unlock seed
    their warp pads get their own entry requirement.

    Turn it off to leave the battle arenas out of the seed."""
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
    """How warp-pad destinations are shuffled among each other.

    - **per_category**: tracks swap with tracks, cups with cups,
      arenas with arenas. Each pad still leads to the same kind of thing.
    - **merged** (default): everything shuffles together, so a track pad can lead to a
      Gem Cup and back again.

    Only matters when Warp Pad Shuffle Categories has something in it."""
    display_name = "Warp Pad Shuffle Grouping"
    option_per_category = 0
    option_merged = 1
    default = 1


class WarpPadItemDisplay(Choice):
    """How each warp pad shows the rewards still waiting behind it.

    Pads use three floating slots and cycle through their remaining reward
    models, including CTR rewards and Archipelago items.

    - **one_pile** (default): every remaining reward shares the three slots.
    - **by_reward_type**: each reward type keeps its own slot and rotates
      within it, making the kinds of checks left easier to distinguish."""
    # Requested in issue #59 (thanks stroodlydoodles and MarioSpore), modelled on
    # Icebound's randomizer. The apworld half is this option plus its slot_data
    # mirror; the pad render itself is native's (its glow pass already enumerates
    # a destination's unchecked reward bits and cycles a 3-wide window over them,
    # which IS the one_pile behaviour, so by_reward_type is a grouping of that
    # same enumeration -- no new location or item data is needed on the wire).
    display_name = "Warp Pad Item Display"
    option_one_pile = 0
    option_by_reward_type = 1
    default = 0


class ApItemTypeColors(DefaultOnToggle):
    """Colour the Archipelago markers by what kind of item is behind them.

    On by default, so colour tells you whether a check holds progression,
    something useful, filler or a trap. Turn it off to make every marker the
    same greyish-white."""
    display_name = "AP Item Type Colours"


class WarpPadUnlockRequirements(Choice):
    """How warp pads unlock, the heart of the randomizer.

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
    """How often a warp pad asks for something twice.

    A two-stage pad opens for racing at the first requirement, then wants a
    second before its time trials, token challenge, and letter locations
    unlock. It spreads a track's checks across the seed instead of handing
    them all over at once.

    - **off**: every pad opens fully at its first requirement.
    - **light** / **standard** / **deep** / **full** (default): progressively more pads
      get a second stage."""
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
    default = 4


class RequirementVariety(Choice):
    """Weight preset for randomized warp-pad requirements (randomized modes
    only).

    - **icebound_beta5** (default): Icebound's rebalanced weights - still
      trophy-leaning, with more token, relic and key variety.
    - **trophy_heavy_legacy**: the previous, more trophy-dominated weights.
    - **custom**: use the weights from `Requirement Weights`."""
    # The exact tables: icebound_beta5 = Trophy 90, each CTR Token 16 (Purple
    # 12), each Relic tier 18, Key 20, each Gem 4; Any* collapse Token x0.8
    # (cap 16), Relic x0.5 (cap 27), Gem capped at 5 (no -1 reduction).
    # trophy_heavy_legacy = Trophy 100, Token 15 (Purple 10), Relic 20, Key 25,
    # Gem 2; Any* collapse Token x0.6, Relic x0.3, Gem -1 (no caps). custom
    # falls back to icebound_beta5 weights for unlisted items and uses the
    # legacy Any* collapse.
    display_name = "Requirement Variety"
    option_icebound_beta5 = 0
    option_trophy_heavy_legacy = 1
    option_custom = 2
    default = 0


class RequirementWeights(OptionDict):
    """Roll your own requirement mix. Used only when `Requirement Variety` =
    custom. Each entry is `item name: weight` - higher weight means picked more
    often; 0 disables an item, except Trophy, which must stay above 0. The
    pre-filled values are the icebound_beta5 weights - tweak from there. Items
    you leave out keep their icebound_beta5 default weight.

    Example:

        requirement_variety: custom
        requirement_weights:
          Trophy: 30
          Key: 40
          Sapphire Relic: 40

    Valid keys: Trophy, Key, the five CTR Token colours, the three Relic tiers,
    and the five Gem colours."""
    # Trophy must stay above 0 because it bootstraps the randomized warp-pad
    # requirements. Unlisted items fall back to their icebound_beta5 weight
    # (see RequirementVariety's comment for the tables).
    display_name = "Requirement Weights"
    supports_weighting = False
    # Pre-filled with the icebound_beta5 table (single source: warp_pad_logic)
    # so the YAML template and options page show real numbers to tweak from
    # instead of an empty dict.
    default = dict(DEFAULT_REQUIREMENT_WEIGHTS)
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
    tier. Incoming deaths are unaffected - amnesty only throttles what you
    send."""
    # Does nothing useful at mask_reset (those wipeouts are already rare) and
    # is inert while DeathLink is off.
    display_name = "DeathLink Amnesty"
    range_start = 1
    range_end = 30
    default = 1


class PodiumPlacementChecks(DefaultOnToggle):
    """Turn race placements into checks.

    Each track can pay out for finishing, for finishing on the podium, and
    for holding a position during the race. The four options below choose
    which of those count.

    A generous source of checks that does not ask you to win everything."""
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


class SapphireRelicCount(Range):
    """How many Sapphire Relics exist in the seed.

    Relics come from relic races. This sets how many of the sapphire tier are
    in the item pool, which is also the most you can be asked to collect.

    Lower it for a shorter seed. Set it to 0 to remove Sapphire checks and
    items. Gold or Platinum checks on the same relic races can still exist."""
    display_name = "Sapphire Relic Count"
    range_start = 0
    range_end = 18
    default = 18


class GoldRelicCount(Range):
    """How many Gold Relics exist in the seed.

    Same idea as Sapphire, one tier up. Set it to 0 to remove the tier and
    its checks entirely."""
    display_name = "Gold Relic Count"
    range_start = 0
    range_end = 18
    default = 18


class PlatinumRelicCount(Range):
    """How many Platinum Relics exist in the seed.

    The hardest relic tier. Set it to 0 to remove it and its checks entirely,
    which is a reasonable choice if you do not intend to chase platinum
    times."""
    display_name = "Platinum Relic Count"
    range_start = 0
    range_end = 18
    default = 0


class StartingCharacter(Choice):
    """Which racer you begin with.

    - **random_starter** (default): one of the 8 retail Adventure racers.
    - **random_any**: any of the 16 playable racers.
    - A racer's name: always begin as that racer.

    With Character Unlocks on, the other 15 racers become items. With it off,
    this still decides who is seated when Adventure starts, but the whole
    roster is immediately available from the hub picker."""
    display_name = "Starting Character"
    option_random_starter = 0
    option_random_any = 1
    option_crash_bandicoot = 2
    option_coco_bandicoot = 3
    option_polar = 4
    option_pura = 5
    option_neo_cortex = 6
    option_n_tropy = 7
    option_ripper_roo = 8
    option_papu_papu = 9
    option_komodo_joe = 10
    option_pinstripe = 11
    option_dingodile = 12
    option_tiny_tiger = 13
    option_n_gin = 14
    option_fake_crash = 15
    option_nitros_oxide = 16
    option_penta_penguin = 17
    default = 0


class StartingStatClass(Choice):
    """Which stat class your starting kart uses.

    Leave it on **vanilla** to keep that racer's usual class, or override the
    starting racer with balanced, acceleration, speed, or turning stats.

    This affects only the racer you start as. Progressive Stats overrides it,
    and logic never requires a particular value."""
    display_name = "Starting Stat Class"
    option_vanilla = 0
    option_balanced = 1
    option_acceleration = 2
    option_speed = 3
    option_turning = 4
    default = 0


class CharacterUnlocks(DefaultOnToggle):
    """Make the roster something you unlock instead of something you start with.

    You begin with one racer and the rest arrive as items. Until then the
    character select only offers who you actually have.

    With this off, every racer is available from the start, as in the retail
    game."""
    display_name = "Character Unlocks"


class RacerLockedPads(Toggle):
    """Lock some warp pads to a specific racer.

    You need to have unlocked the racer a pad names. When you enter, the game
    seats you as that racer for the destination and restores your previous
    racer when you return to the hub. The pad shows who it needs.

    Never your starting racer - a lock you already satisfy would be no lock
    at all. Needs Character Unlocks to be on, since otherwise every racer is
    available from the start."""
    display_name = "Racer-Locked Warp Pads"


class PentaStats(Choice):
    """Which version of Penta Penguin's stats to use.

    Penta is the one racer whose stats differ by region. He was added very
    late and shipped unfinished in NTSC-U, where he simply reuses Polar and
    Pura's turning class. The later PAL release finished him, with top values
    in every category, which makes him the strongest racer in the game.

    - **ntsc** (default): the turning-class version, same as Polar and Pura.
    - **pal**: the maxed-out version, which makes him the strongest racer in
      the game.

    Progressive Stats or Editable Stats overrides this choice."""
    display_name = "Penta Penguin Stats"
    # The labels were inverted until 2026-08-21. The NUMBERS are the ones the
    # client has always read (0 the ordinary TURN-class table, 1 the MAX
    # table), so nothing moved on the wire; only the names above them did.
    option_ntsc = 0
    option_pal = 1
    default = 0


class EditableStats(Choice):
    """Tune your kart's stats yourself from the hub stat panel.

    - **off** (default): no editing; the panel just shows what you have.
    - **global**: one custom setup shared by every racer.
    - **per_character**: a separate setup for each of the 16 racers.

    Progressive Stats wins if you enable both - the panel goes read-only and
    no edit controls appear. The seed still generates; the two are simply
    different ways to decide the same numbers."""
    display_name = "Editable Stats"
    option_off = 0
    option_global = 1
    option_per_character = 2
    default = 0


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # goal & endgame (issue #152: composed conditions, ANDed)
    oxide_goal: OxideGoal
    bosses_required_goal: BossesRequiredGoal
    gems_required_goal: GemsRequiredGoal
    oxide_final_challenge_unlock: FinalOxideUnlock
    oxide_final_challenge_relic_count: FinalOxideRelicCount
    # items & pool
    shuffle_gems: ShuffleGems
    include_gem_cups: ShuffleWarpPadsGemCups
    randomize_gem_cup_tracks: RandomizeGemCupTracks
    shuffle_keys: ShuffleKeys
    trap_fill_percentage: TrapFillPercentage
    trap_weights: TrapWeights
    itemsanity: Itemsanity
    # Papu's Pyramid mask helper (#223)
    tizi_helper: TiziHelper
    # The wumpa family (2026-08-10 ruling): two bundle fillers, the starting
    # ladder, and the one global check.
    wumpa_bundles: WumpaBundles
    progressive_starting_wumpa: ProgressiveStartingWumpa
    wumpa_check: WumpaCheck
    # in-race Turbo hand-out (#224), the second ruled namespace amendment
    turbo_grant: TurboGrant
    lettersanity: Lettersanity
    letters_per_track: LettersPerTrack
    # authored item-box checks (#109)
    box_locations: BoxLocations
    shortcut_knowledge: ShortcutKnowledge
    # capability item packs (issues #12, #13)
    progressive_boost: ProgressiveBoostMode
    progressive_boost_blue_fire: ProgressiveBoostBlueFire
    progressive_stats: ProgressiveStatsMode
    logic_difficulty: LogicDifficulty
    # character phase (issues #54, #209)
    starting_character: StartingCharacter
    starting_stat_class: StartingStatClass
    character_unlocks: CharacterUnlocks
    racer_locked_pads: RacerLockedPads
    penta_stats: PentaStats
    editable_stats: EditableStats
    # warp pads: content & destination shuffle
    include_battle_arenas: ShuffleWarpPadsBattleArenas
    warp_pad_shuffle_categories: WarpPadShuffleCategories
    warp_pad_shuffle_grouping: WarpPadShuffleGrouping
    # warp pads: display (issue #59)
    warp_pad_item_display: WarpPadItemDisplay
    # warp pads: AP-logo marker colours (issue #212)
    ap_item_type_colors: ApItemTypeColors
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
    sapphire_relic_count: SapphireRelicCount
    gold_relic_count: GoldRelicCount
    platinum_relic_count: PlatinumRelicCount
    # wired but hidden (single implemented mode; see BUG-D note)
    bossgarage_unlock_requirements: BossGarageRequirements


ap_ctr_option_groups: Dict[str, List[Any]] = {
    # Ordered the way a player fills a YAML: what am I trying to do, then how
    # the randomizer works, then how big the seed is, then tuning, then
    # cosmetics. Mechanics before decoration -- pad unlocking is the heart of
    # this randomizer and used to sit BELOW the marker-colour options.
    #
    # Every option must appear in exactly one group. Anything left out lands in
    # an unlabelled bucket at the bottom of the web page, which is where
    # box_locations, shortcut_knowledge, lettersanity, letters_per_track and
    # bossgarage_unlock_requirements used to end up.
    "Goal": [OxideGoal, BossesRequiredGoal, GemsRequiredGoal,
             FinalOxideUnlock, FinalOxideRelicCount],
    "Warp Pad Unlocking": [WarpPadUnlockRequirements, TwoStageDensity,
                           RequirementVariety, RequirementWeights,
                           BossGarageRequirements],
    "Warp Pad Shuffle": [WarpPadShuffleCategories, WarpPadShuffleGrouping,
                         ShuffleWarpPadsBattleArenas, ShuffleWarpPadsGemCups,
                         RandomizeGemCupTracks],
    # The "how long is this seed" decisions, together, because they are read
    # against each other rather than one at a time.
    "Extra Checks": [BoxLocations, ShortcutKnowledge, Itemsanity,
                     Lettersanity, LettersPerTrack,
                     PodiumPlacementChecks, PodiumFinishRungs,
                     PodiumAnyPositionRung, PodiumHeldRungs,
                     PodiumHeldFifthRung],
    "Items & Pool": [ShuffleGems, ShuffleKeys, TrapFillPercentage, TrapWeights,
                     TiziHelper, WumpaBundles, ProgressiveStartingWumpa,
                     WumpaCheck, TurboGrant],
    "Capability Items": [ProgressiveBoostMode, ProgressiveBoostBlueFire,
                         ProgressiveStatsMode, LogicDifficulty],
    # Grouped together on purpose: a player reads "who do I start as", "who can
    # I unlock", "can a pad demand a racer" and "who owns my stats" as one
    # decision.
    "Characters": [StartingCharacter, StartingStatClass, CharacterUnlocks,
                   RacerLockedPads, PentaStats, EditableStats],
    "Relic Difficulty": [SapphireRelicCount, GoldRelicCount,
                         PlatinumRelicCount],
    "Quality of Life": [OneLapCups, WarpPadItemDisplay, ApItemTypeColors],
    "DeathLink": [DeathLink, DeathLinkAmnesty],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]
