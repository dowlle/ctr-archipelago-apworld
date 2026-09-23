from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility)

from . import characters
from .warp_pad_logic import DEFAULT_REQUIREMENT_WEIGHTS
from .traps import (DEFAULT_TRAP_WEIGHTS, TRAP_WEIGHT_KEYS,
                    validate_trap_weights)
from .custom_tracks import KNOWN_TRACK_IDS, validate_custom_tracks


class OxideGoal(Choice):
    """What finishing the game means.

    - **any_percent** (default): beat Oxide, the retail ending.
    - **101_percent**: beat Oxide's Final Challenge.
    - **none**: Oxide is not part of the goal; both Oxide races stay as
      optional checks.
    - **disabled**: Oxide's garage never opens and both Oxide races leave the
      seed.

    With none or disabled, set Bosses Required Goal or Gems Required Goal
    above 0. Every goal condition you set must be met."""
    display_name = "Oxide Goal"
    option_none = 0
    option_any_percent = 1
    option_101_percent = 2
    # Issue #320. `none` already means "optional Oxide": the garage still opens
    # and both races remain checks. `disabled` is the separate, stronger value
    # that closes the garage and removes both locations, so it needed its own
    # integer rather than a re-reading of 0 -- every already-rolled `none` seed
    # keeps its meaning on the wire and in every shipped client.
    option_disabled = 3
    # The old spellings keep working, so a YAML written before the rename
    # loads unchanged. The integers are frozen: slot_data's goal_oxide and the
    # native parser (ap_verify.c, ap_hooks.c) read the number, never the name,
    # so renaming the values costs nothing on the wire.
    alias_first = 1
    alias_final = 2
    default = 1

    @staticmethod
    def oxide_content_present(value: int) -> bool:
        """Does this seed contain the two Oxide race LOCATIONS at all?

        True for every value except `disabled`. The one place that answer is
        computed, so Regions (which skips creating them), Rules (which skips
        their access rules), the relic classification and the forced-option
        guards cannot drift about whether the content exists."""
        return value != OxideGoal.option_disabled

    @staticmethod
    def oxide_is_goal(value: int) -> bool:
        """Is an Oxide encounter this seed's finale? False for `none` and for
        `disabled` -- the two values under which no non-Oxide goal arm may
        gate either Oxide race (2026-09-03 RC ruling)."""
        return value in (OxideGoal.option_any_percent,
                         OxideGoal.option_101_percent)


class Oxide1Optional(Choice):
    """Whether you must beat Oxide 1 before Oxide 2. Only applies when Oxide
    Goal is 101_percent.

    - **mandatory** (default): beat Oxide 1 first.
    - **optional**: the garage offers Oxide 2 once its own requirements are
      met. Oxide 1 stays a normal check, and winning Oxide 2 also collects
      it.
    - **filler**: like optional, and Oxide 1 always holds Wumpa Fruit."""
    display_name = "Oxide 1 Optional"
    option_mandatory = 0
    option_optional = 1
    option_filler = 2
    alias_true_filler = 2
    alias_false = 0
    alias_true = 1
    default = 0


class BossesRequiredGoal(Range):
    """How many of the 4 boss races you must win for the goal.

    Ripper Roo, Papu Papu, Komodo Joe and Pinstripe. 0 (default) turns this
    condition off.

    Only a won boss race counts; holding trophies or Keys does not. Every
    goal condition you set with Oxide Goal and Gems Required Goal must be
    met."""
    display_name = "Bosses Required Goal"
    range_start = 0
    range_end = 4
    default = 0


class GemsRequiredGoal(Range):
    """How many of the 5 Gems you must hold for the goal.

    0 (default) turns this condition off. Every goal condition you set with
    Oxide Goal and Bosses Required Goal must be met.

    With Include Gem Cup Warp Pads off, Shuffle Gems is turned off for you
    and each Gem stays on its own cup."""
    display_name = "Gems Required Goal"
    range_start = 0
    range_end = 5
    default = 0


class FinalOxideUnlock(Choice):
    """Which relics open Oxide's Final Challenge. Oxide's Final Challenge
    Relic Count sets how many.

    - **sapphire_relics** (default), **gold_relics**, **platinum_relics**: that
      many relics of that tier.
    - **any_relic_type**: any one tier reaches the count.
    - **total_relics**: all relics added together reach the count.

    A Platinum relic does not count toward a Gold requirement. Generation
    fails if the tiers you ask for have too few relics for the count."""
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
    """How many relics Oxide's Final Challenge Unlock asks for.

    With **total_relics** this can be 1 to 54. Every other mode counts one
    tier, so 1 to 18; a higher value counts as 18. **all** means 18 in every
    mode."""
    # Above 18 in a single-tier mode, forced_options resolves the count to 18
    # and logs a warning naming the mode and the requested value (2026-09-18
    # ruling). `all` keeps its 0.2.0 meaning; total_relics players who want
    # every relic of every tier write 54.
    display_name = "Oxide's Final Challenge Relic Count"
    range_start = 1
    range_end = 54
    default = 18
    special_range_names = {"all": 18}


class OxideFinalTrack(Choice):
    """Venue for N. Oxide's Final Challenge. The opponent remains Nitros
    Oxide for both choices."""
    # The AP location backing this challenge is 35011105 for both venue
    # choices -- an implementation detail, not something a player needs to
    # know to pick a venue (issue #355).
    display_name = "Oxide Final Challenge Track"
    option_cortex_vortex = 0
    option_oxide_station = 1
    default = 0


class ShuffleGems(DefaultOnToggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **on** (default): the Gems can appear anywhere; their Gem Cup locations
      become normal checks.
    - **off**: each Gem stays on its own Gem Cup reward (vanilla placement).

    With Include Gem Cup Warp Pads off, each Gem stays on its own cup
    anyway."""
    display_name = "Shuffle Gems"


class ShuffleWarpPadsGemCups(DefaultOnToggle):
    """Include the 5 Gem Cups and their races in the seed.

    - **on** (default): the cup checks are normal locations and, with
      randomized unlocks, their warp pads get a randomized requirement.
    - **off**: the cups stay as in the retail game and each Gem stays on its
      own cup.

    Shuffle Gems moves the Gem items; this option decides whether the cup
    races are part of the seed."""
    # The Key-2 Cups Room hub gate is always kept on top of a randomized cup
    # requirement. This option is also the participation gate for the `cups`
    # destination-shuffle category. Off + Shuffle Gems on pins each Gem back onto
    # its own vanilla cup check (out of the pool) so opted-out cups never hold
    # another world's progression; a Gems Required goal + Shuffle Gems on +
    # this off resolves Shuffle Gems to off with a warning (2026-09-21 ruling,
    # forced_options.resolve_shuffle_gems_off_when_gem_goal_excludes_cups)
    # rather than stranding the goal or failing the whole multiworld.
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


class CustomTracks(OptionDict):
    """Race a community custom track in place of a Gem Cup.

    The cup keeps its warp pad, but behind it is one race on the custom track
    instead of four retail tracks. Leave this empty (the default) for a
    normal seed.

    You also need the track's files and a client that can load them. Use the
    track's exact entry rather than writing your own: generation refuses an
    entry this version does not know, and the game refuses files that do not
    match it.

    The only known track is baby-t-park, and only purple_gem_cup can be
    replaced."""
    # Ruled 2026-08-28 (Wayfinder): an early instance of the self-describing
    # `custom_tracks` descriptor rather than a throwaway toggle, and full
    # DISPLACEMENT of the replaced cup's destination. Shape, validation,
    # displacement and wire block all live in custom_tracks.py.
    #
    # default is {} rather than a rendered example, unlike TrapWeights: an
    # example default would put digests a player has not verified into every
    # generated template, and this option is off unless someone means it.
    display_name = "Custom Tracks"
    supports_weighting = False
    default = {}
    valid_keys = list(KNOWN_TRACK_IDS)

    def verify_keys(self) -> None:
        # Core's VerifyKeys would only reject an unknown top-level id, with a
        # message that lists the allowed set and says nothing about the body.
        # This is the same function generate_early calls, so a rolled YAML and
        # a programmatically built world fail identically (the TrapWeights
        # precedent).
        validate_custom_tracks(self.value)


class ShuffleKeys(DefaultOnToggle):
    """Shuffle the 4 boss Keys into the multiworld item pool.

    - **on** (default): the Keys can appear anywhere; the Boss Race locations
      become normal checks.
    - **off**: each Key stays on its Boss Race reward (vanilla placement)."""
    display_name = "Shuffle Keys"


class ProgressiveBoostMode(Choice):
    """Make boost an item you have to find.

    Boost arrives in stages: normal boost, then Ultimate Sacred Fire, plus a
    Blue Fire tier if Progressive Boost: Blue Fire is on. Some checks need
    the speed, such as the climb on Hot Air Skyway, and every CTR Token
    Challenge waits for your first boost.

    - **off** (default): every kart boosts normally.
    - **shared_global**: one boost ladder for every racer.
    - **per_character**: a ladder for each of the 16 racers, 32 to 48 items.
      Needs a large seed; generation stops if they do not fit."""
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

    - **off** (default): the ladder stops at Ultimate Sacred Fire.
    - **on**: one more tier, so one more Progressive Boost to find.

    No effect while Progressive Boost is off."""
    display_name = "Progressive Boost: Blue Fire"


class LogicDifficulty(Choice):
    """How much the logic expects you to manage in races while boost and
    weapons are randomized.

    Race requirements apply when Progressive Boost and Itemsanity are both
    on. Platinum Time Trials follow this whenever Progressive Boost is on.

    - **easy**: winning, finishing on the podium and holding 1st wait for
      boost or three useful weapons.
    - **medium** (default): only winning waits.
    - **hard**: no extra requirement.

    Tracks that need speed ignore this: Cortex Castle and Hot Air Skyway
    always need Ultimate Sacred Fire."""
    display_name = "Logic Difficulty"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 1


class ProgressiveStatsMode(Choice):
    """Make top speed, acceleration and turning items you have to find.

    Karts start at the bottom of all three and climb as the stats arrive,
    ending above the retail maximum.

    - **off** (default): karts keep their normal stats.
    - **shared_global**: one set of stat ladders for every racer.
    - **per_character**: a set for each of the 16 racers, 192 items. Needs a
      large seed."""
    display_name = "Progressive Stats"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


class TrapFillPercentage(Range):
    """What percentage of this slot's filler items are replaced by traps.

    - **0**: no traps, filler stays Wumpa Fruit.
    - **10** (default): a taste of sabotage.
    - **100**: every filler slot becomes a trap.

    Which trap you get is decided by Trap Weights.

    Traps never gate anything. A received trap arms silently and fires mid-race
    on a later lap."""
    # CTR's pool is almost entirely progression, so the filler pool this dial
    # replaces is small; traps substitute filler, never stack onto progression.
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 10


class TrapWeights(OptionDict):
    """How often each trap is picked when Trap Fill Percentage turns a filler
    item into a trap.

    Weights are relative: higher means more often, 0 means never. Traps you
    leave out keep their default weight.

    `first_person`, `wireframe`, `upside_down`, `mirror_mode` and
    `demo_camera` change the camera or the screen and can be visually
    intense. Set a trap to 0 to turn it off; `upside_down` is 0 by default.

    Setting every trap to 0 while Trap Fill Percentage is above 0 is an
    error."""
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

    Until a weapon arrives from the multiworld you cannot get it from a
    crate; the roulette hands you Wumpa Fruit instead. Using each weapon for
    the first time is itself a check, and using one while holding ten fruit
    is a second.

    It changes how the whole game plays, not just what you collect."""
    display_name = "Itemsanity"

class HitCharacter(Toggle):
    """Add a check for each of the 16 racers, paid the first time you hit
    them in an Adventure race.

    The 8 retail Adventure racers can race you from the start. The other 8
    join once you win their boss race or the tracks that unlock them. If
    that race is not in your seed, Keys unlock them instead; the spoiler log
    lists which racers use Keys."""
    display_name = "Hit Character Checks"


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


class WumpaCheck(Choice):
    """Add checks for reaching 10 Wumpa Fruit during a race.

    - **off** (default): no Wumpa checks.
    - **global**: one check, the first time you reach 10 fruit in any race.
    - **per_track**: one check for each track you race on in this seed,
      instead of the global one.

    Different from Itemsanity's juiced weapon checks, which pay out when you
    fire a weapon at 10 fruit."""
    display_name = "Wumpa Check"
    option_off = 0
    option_global = 1
    option_per_track = 2
    default = 0

    @classmethod
    def from_any(cls, data: Any) -> "WumpaCheck":
        """Accept the retired Boolean spelling.

        This option shipped in Alpha 6 as a `Toggle`, so an existing YAML holds
        `wumpa_check: true` or `false`. AP's `Choice.from_any` cannot take those:
        its integer branch tests `type(data) == int`, which a real `bool` fails,
        and the text branch then looks for an option literally named "true".

        The mapping is silent rather than warned, unlike the racer-lock
        compatibility path, because nothing about the player's seed changes:
        false meant no Wumpa check and true meant the single global check, which
        are exactly `off` and `global`.
        """
        if isinstance(data, bool):
            return cls(cls.option_global if data else cls.option_off)
        return super().from_any(data)


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
    much longer seed. Some sit past jumps or shortcuts you need boost for;
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
    Changes nothing about logic or which locations exist; everything is just
    faster."""
    # Reuses the engine's built-in one-lap mechanism (the vanilla one-lap
    # cheat), scoped to cups.
    display_name = "One-Lap Cup Races"


class ShuffleWarpPadsBattleArenas(DefaultOnToggle):
    """Include the 4 Battle Arenas and their Crystal Challenges in the seed.

    - **on** (default): their checks are normal locations and, with
      randomized unlocks, their warp pads get a randomized requirement.
    - **off**: the arenas stay as in the retail game and nothing in the seed
      requires them. You can still play them, but their Purple CTR Tokens are
      out of logic and can open a pad that asks for any CTR Tokens earlier
      than the tracker expects."""
    # The off guarantees, precisely: crystal pads vanilla-fixed and never
    # destination-shuffled; the four Crystal Bonus Round checks keep their
    # vanilla Purple CTR Tokens LOCKED (no other world's item can hide there);
    # randomized requirements never demand Purples directly NOR through an
    # "any tokens" count that only arena play could reach (issue #118).
    display_name = "Include Battle Arena Warp Pads"


class WarpPadShuffleCategories(OptionSet):
    """Which destinations take part in destination shuffle. Anything left
    out always loads its own content.

    - **tracks**: the 16 trophy races plus Slide Coliseum and Turbo Track.
    - **cups**: the 5 Gem Cups (needs Include Gem Cup Warp Pads on).
    - **crystals**: the 4 Battle Arenas (needs Include Battle Arena Warp Pads
      on).

    Default: all three. An empty set turns destination shuffle off. With
    vanilla unlock requirements, tracks and crystals shuffle only among
    themselves and cups stay fixed."""
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


class TrialTrackRaces(Choice):
    """Standalone Adventure race family for one trial track.

    Trophy Race also restores that track's per-track Reach 10 Wumpa route.
    CTR Challenge includes Trophy Race by construction, so a CTR-only seed
    cannot be expressed.
    """
    display_name = "Trial Track Races"
    option_off = 0
    option_trophy_race = 1
    option_trophy_and_ctr_challenge = 2
    default = 0


class SlideColiseumRaces(TrialTrackRaces):
    """Add race checks to Slide Coliseum's warp pad, which normally runs
    only relic races.

    - **off** (default): relic races only, as in the retail game.
    - **trophy_race**: adds a Trophy Race check.
    - **trophy_and_ctr_challenge**: adds a Trophy Race and a CTR Token
      Challenge check."""
    display_name = "Slide Coliseum Races"


class TurboTrackRaces(TrialTrackRaces):
    """Add race checks to Turbo Track's warp pad, which normally runs only
    relic races.

    - **off** (default): relic races only, as in the retail game.
    - **trophy_race**: adds a Trophy Race check.
    - **trophy_and_ctr_challenge**: adds a Trophy Race and a CTR Token
      Challenge check."""
    display_name = "Turbo Track Races"


class CortexVortexTrack(Toggle):
    """Add Cortex Vortex as a regular track: a Trophy Race, three Time Trials
    and a CTR Token Challenge.

    It takes the warp pad of one other destination, chosen per seed, and
    that destination's checks leave the seed. A boss race on that track
    still runs. Crossing the finish line needs Ultimate Sacred Fire.
    Cortex Vortex has no item boxes."""
    # Default off until a runtime pass proves an 8-kart race, relic mode and
    # the AI on this LEV (frozen contract, 2026-09-13).
    display_name = "Cortex Vortex Track"


class ApItemTypeColors(DefaultOnToggle):
    """Colour the Archipelago markers by what kind of item is behind them.

    On by default, so colour tells you whether a check holds progression,
    something useful, filler or a trap. Turn it off to make every marker the
    same greyish-white."""
    display_name = "AP Item Type Colours"


class ColorBoxesByItem(DefaultOnToggle):
    """Colour each AP item box by the kind of item inside it.

    On (default): a box shows the Archipelago colour of its item before you
    break it:

    - purple: progression
    - blue: useful
    - cyan: filler
    - salmon: trap

    Off: every AP item box is pink for everyone in this slot, so the colour
    gives nothing away. Use this for races and tournaments.

    Players can also turn the colours off in the game under Options,
    Archipelago, Item Box Colours. When this option is off, that row shows
    "OFF (SEED)". Only does something when Item Box Locations is on."""
    display_name = "Item Box Colours"


class WarpPadUnlockRequirements(Choice):
    """How warp pads unlock.

    - **randomized** (default): every warp pad gets a randomized entry
      requirement (trophies, tokens, relics, keys, gems...), always collectable
      before that pad opens.
    - **vanilla**: pads open on their vanilla trophy counts, like the original
      adventure.
    - **random_without_4_keys**: like randomized, but no pad needs all 4 Keys.
      Pads can still ask for 1 to 3 Keys. For no Keys on pads at all, set
      Requirement Variety to custom and `Key: 0` in Requirement Weights."""
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
    """Which mix of items randomized warp pads ask for. Only used with
    randomized unlock requirements.

    - **icebound_beta5** (default): Icebound's rebalanced mix. Trophies are
      the most common, with plenty of CTR Tokens, Relics and Keys and a few
      Gems.
    - **trophy_heavy_legacy**: the older mix, with more Trophies.
    - **custom**: use the weights from Requirement Weights."""
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
    """Your own mix of warp-pad requirements, used only when Requirement
    Variety is custom.

    Each entry is `item name: weight`. Higher means picked more often, 0
    means never; Trophy must stay above 0. Items you leave out keep their
    icebound_beta5 weight, which is also what the pre-filled values show.

    Valid keys: Trophy, Key, the five CTR Token colours, the three Relic
    tiers and the five Gem colours."""
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
      squish, burn). Much higher frequency, so pair it with DeathLink
      Amnesty.

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
    (default) sends every death; N sends one per N. Meant for the any_hit
    tier. Incoming deaths are unaffected; amnesty only throttles what you
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
    """Include the finish-line rungs on each trophy race (needs Podium
    Placement Checks on): "Finish on Podium" (top 3) and "Finish (Any
    Position)". Toggle the any-position half with Podium: Any-Position
    Rung."""
    display_name = "Podium Finish Rungs"


class PodiumAnyPositionRung(DefaultOnToggle):
    """Also include the "Finish (Any Position)" rung on each trophy race, earned
    by simply crossing the finish line. Off keeps only "Finish on Podium". Needs
    Podium Finish Rungs on."""
    display_name = "Podium: Any-Position Rung"


class PodiumHeldRungs(DefaultOnToggle):
    """Include the live-position "held" rungs on each trophy race (needs Podium
    Placement Checks on): "Held 1st" and "Held 3rd", earned the moment you hold
    that position on track. Add "Held 5th" with Podium: Held 5th Rung."""
    display_name = "Held-Position Rungs"


class PodiumHeldFifthRung(Toggle):
    """Also add a "Held 5th" rung to each trophy race, earned by holding 5th
    place or better at any point. Needs Held-Position Rungs on. Off by
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


class RacerLockedPads(Range):
    """The most warp pads that can require a specific racer.

    To enter a locked pad you need that racer unlocked; the game seats you as
    them for that destination. 0 (default) turns this off. A seed with few
    randomized pads gets fewer locks than you asked for. Your starting racer
    is never required. Needs Character Unlocks on."""
    display_name = "Racer-Locked Warp Pads"
    range_start = 0
    # The complete supported physical-pad census. No seed has more pads than
    # this to lock, so no larger request could mean anything. Read from the pad
    # data rather than typed here so the ceiling cannot drift when a pad is
    # added; `test_character_phase` pins it against the same file.
    range_end = characters.PHYSICAL_PAD_COUNT
    default = 0

    # Set by `from_any` when the YAML wrote the Alpha 6 Boolean instead of a
    # count. Read by characters.legacy_boolean_request.
    legacy_boolean_auto = False

    # Up to Alpha 6 this option was a toggle, and `bool` is an `int` subclass,
    # so `racer_locked_pads: true` would otherwise quietly become "at most one
    # lock" -- a different seed than the player asked for, with nothing said
    # about it. During the Alpha 6 compatibility window `true` normalizes to
    # the automatic density that toggle chose (a quarter of the eligible pads,
    # clamped 1..6) and forced_options logs it once. `false` is 0, which needs
    # no message because off means the same thing in both spellings. Dropping
    # this path is a later major option cleanup, not a silent removal.
    _TRUE_TEXT = frozenset(("true", "yes", "on"))
    _FALSE_TEXT = frozenset(("false", "no", "off"))

    @classmethod
    def _legacy_true(cls) -> "RacerLockedPads":
        option = cls(0)
        option.legacy_boolean_auto = True
        return option

    @classmethod
    def from_any(cls, data: Any) -> "RacerLockedPads":
        if isinstance(data, bool):
            return cls._legacy_true() if data else cls(0)
        # `isinstance` rather than Range's `type(data) == int` only because the
        # bool branch above has already taken the one case they differ on.
        if isinstance(data, int):
            return cls(data)
        return cls.from_text(str(data))

    @classmethod
    def from_text(cls, text: str) -> "RacerLockedPads":
        # A quoted `"true"` never reaches `from_any` as a bool, and Range's own
        # true/false spelling is disabled for an option whose default is 0, so
        # the normalization has to be reachable from text as well.
        lowered = text.strip().lower()
        if lowered in cls._TRUE_TEXT:
            return cls._legacy_true()
        if lowered in cls._FALSE_TEXT:
            return cls(0)
        return super().from_text(text)


class PentaStats(Choice):
    """Which version of Penta Penguin's stats to use. Penta is the one racer
    whose stats differ by region.

    - **ntsc** (default): the unfinished NTSC-U version, which reuses Polar
      and Pura's turning stats.
    - **pal**: the finished PAL version, with top values in every category.
      This makes him the strongest racer in the game.

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

    Progressive Stats wins if you enable both: the panel goes read-only and
    no edit controls appear."""
    display_name = "Editable Stats"
    option_off = 0
    option_global = 1
    option_per_character = 2
    default = 0


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # goal & endgame (issue #152: composed conditions, ANDed)
    oxide_goal: OxideGoal
    oxide_1_optional: Oxide1Optional
    bosses_required_goal: BossesRequiredGoal
    gems_required_goal: GemsRequiredGoal
    oxide_final_challenge_unlock: FinalOxideUnlock
    oxide_final_challenge_relic_count: FinalOxideRelicCount
    oxide_final_track: OxideFinalTrack
    # items & pool
    shuffle_gems: ShuffleGems
    include_gem_cups: ShuffleWarpPadsGemCups
    randomize_gem_cup_tracks: RandomizeGemCupTracks
    # community custom tracks (Baby T Park event spike): a self-describing
    # descriptor that DISPLACES the cup destination it names
    custom_tracks: CustomTracks
    slide_coliseum_races: SlideColiseumRaces
    turbo_track_races: TurboTrackRaces
    cortex_vortex_track: CortexVortexTrack
    shuffle_keys: ShuffleKeys
    trap_fill_percentage: TrapFillPercentage
    trap_weights: TrapWeights
    itemsanity: Itemsanity
    # Hit Character encounter checks (0.2.1 candidate)
    hit_character: HitCharacter
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
    # item boxes: colour by the item inside (ruling R11)
    color_boxes_by_item: ColorBoxesByItem
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
    "Goal": [OxideGoal, Oxide1Optional, BossesRequiredGoal, GemsRequiredGoal,
             FinalOxideUnlock, FinalOxideRelicCount, OxideFinalTrack],
    "Warp Pad Unlocking": [WarpPadUnlockRequirements, TwoStageDensity,
                           RequirementVariety, RequirementWeights,
                           BossGarageRequirements],
    "Warp Pad Shuffle": [WarpPadShuffleCategories, WarpPadShuffleGrouping,
                         ShuffleWarpPadsBattleArenas, ShuffleWarpPadsGemCups,
                         RandomizeGemCupTracks, CustomTracks],
    # The "how long is this seed" decisions, together, because they are read
    # against each other rather than one at a time.
    "Extra Checks": [BoxLocations, ShortcutKnowledge, Itemsanity,
                     HitCharacter,
                     Lettersanity, LettersPerTrack,
                     SlideColiseumRaces, TurboTrackRaces, CortexVortexTrack,
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
    "Quality of Life": [OneLapCups, WarpPadItemDisplay, ApItemTypeColors,
                        ColorBoxesByItem],
    "DeathLink": [DeathLink, DeathLinkAmnesty],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]
