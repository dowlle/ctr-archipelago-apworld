from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionError, OptionGroup, OptionDict, OptionList, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility, StartInventoryPool)

from . import characters
from .warp_pad_logic import DEFAULT_REQUIREMENT_WEIGHTS
from .traps import (DEFAULT_TRAP_WEIGHTS, TRAP_WEIGHT_KEYS,
                    validate_trap_weights)
from .custom_tracks import KNOWN_TRACK_IDS, validate_custom_tracks
from .boss_track_shuffle import VENUES as BOSS_VENUE_TRACKS
from .boss_encounters import (OPPONENT_NAMES as BOSS_GARAGE_OPPONENTS, POOL_NAMES as BOSS_OPPONENT_NAMES,
                              GARAGE_FAMILIES as BOSS_ATTACK_FAMILIES, FAMILIES as OXIDE_ATTACK_FAMILIES)
from .arena_content import ARENAS, ARCADE

ARENA_NAMES = tuple(ARENAS.values())
ORIGINAL_ARENA_NAMES = tuple(name for level, name in ARENAS.items() if level not in ARCADE)


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
    Oxide Goal and Bosses Required Goal must be met."""
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
    """Venue for N. Oxide's Final Challenge. The opponent is N. Oxide for
    both choices, unless Nitros Oxide is in Boss Character Pool and another
    racer takes his races."""
    # The AP location backing this challenge is 35011105 for both venue
    # choices -- an implementation detail, not something a player needs to
    # know to pick a venue (issue #355).
    display_name = "Oxide Final Challenge Track"
    option_cortex_vortex = 0
    option_oxide_station = 1
    default = 0


class BossTrackShuffle(Toggle):
    """Race each of the four boss garages on a randomly drawn track.

    Ripper Roo, Papu Papu, Komodo Joe and Pinstripe keep their garage, their
    Key, their door requirement and their own attacks; only the track they
    race on changes. Each boss gets a different track. N. Oxide is not
    affected. Boss Track Pool narrows the draw."""
    # #169 tier 1 (0.3.0). Wire: ctr_options.boss_track_shuffle plus the
    # boss_encounters block (schema 18). See boss_track_shuffle.py.
    display_name = "Boss Track Shuffle"


class BossOpponentShuffle(Toggle):
    """Race each of the four boss garages against a randomly drawn racer.

    The garage keeps its Key, its door requirement, its check and its own
    boss-grade driving. With Boss Track Shuffle off, the race stays on the
    garage's own track; with both on, Boss Track Assignment decides the
    track. Each garage gets a different racer, from Boss Character Pool."""
    # #169 tier 2 (0.3.0). Wire: the plan's bosses record and boss race entries.
    # See content_bosses.py.
    display_name = "Boss Opponent Shuffle"


class BossTrackAssignment(Choice):
    """With Boss Track Shuffle and Boss Opponent Shuffle both on, how the
    track is chosen.

    - **character_home_track** (default): the drawn racer races on their own
      home track, for example Coco on Coco Park.
    - **independent_track**: the track is drawn on its own.

    Ignored unless both switches are on."""
    display_name = "Boss Track Assignment"
    option_character_home_track = 0
    option_independent_track = 1
    default = 0


class BossKitShuffle(Toggle):
    """Give each of the four boss garages a new attack kit.

    Each boss gets a new set of weapons, used at set points of the lap. The
    garage, its Key, its check and its racer stay the same unless the other
    boss switches change them. N. Oxide keeps his own attacks."""
    # #169 tier 3 (0.3.0). Wire: the plan's bosses record and boss race entries.
    # See content_bosses.py.
    display_name = "Boss Kit Shuffle"


class BossAttackAssignment(Choice):
    """With Boss Kit Shuffle on, how a kit is made.

    - **mixed_loadouts** (default): each boss uses two to four different
      weapon types.
    - **signature_profiles**: each boss gets one of the four retail boss
      attack patterns as a whole (Ripper Roo's TNT, Papu Papu's potions,
      Komodo Joe's thrown TNT, Pinstripe's bombs).

    Ignored when Boss Kit Shuffle is off."""
    display_name = "Boss Attack Assignment"
    option_mixed_loadouts = 0
    option_signature_profiles = 1
    default = 0


class BossAttackIntensity(Choice):
    """With Boss Kit Shuffle on, how often a boss attacks. It changes the
    wait between attacks only, never which weapons are used.

    Ignored when Boss Kit Shuffle is off."""
    display_name = "Boss Attack Intensity"
    option_relaxed = 0
    option_standard = 1
    option_intense = 2
    option_mayhem = 3
    default = 1


class BossLossEasing(DefaultOnToggle):
    """With Boss Kit Shuffle on, each lost race against a garage's boss makes
    that boss attack a little less often, as in the original game. Turn off
    to keep the attacks the same on every try.

    Ignored when Boss Kit Shuffle is off."""
    display_name = "Boss Loss Easing"


class PurpleCupBossGauntlet(Toggle):
    """In each Purple Gem Cup race, one racer attacks you like a boss, with a
    kit made the same way as the boss garage kits. The cup's tracks, racers
    and checks do not change, but the podium places get harder.

    Needs Boss Kit Shuffle on and the Purple Gem Cup in the seed; a YAML
    without either is refused."""
    # Design answer 3 (2026-10-13) and decision 5 (2026-10-28). Wire: the plan's
    # bosses.gauntlet. See content_bosses.py.
    display_name = "Purple Gem Cup Boss Gauntlet"


class OxideAttackProfile(Choice):
    """How N. Oxide's garage races attack you.

    - **retail** (default): N. Oxide's own attacks from the original game.
    - **all_compatible**: a new attack kit drawn from every weapon a boss can
      use, including the Super Engine, which only N. Oxide's garage uses.

    The kit belongs to N. Oxide's garage, so it also applies when another
    racer takes his races."""
    # Wayfinder D2a (ruled 2026-09-02) and decision 5 (2026-10-28).
    display_name = "N. Oxide Attack Profile"
    option_retail = 0
    option_all_compatible = 1
    default = 0


class ShuffleGems(DefaultOnToggle):
    """Shuffle the 5 Gems into the multiworld item pool.

    - **on** (default): the Gems can appear anywhere; their Gem Cup locations
      become normal checks.
    - **off**: each Gem stays on its own Gem Cup reward (vanilla placement).

    Off needs all five Gem Cups in the seed. With any of them missing, all five
    Gems shuffle."""
    display_name = "Shuffle Gems"


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
    """How much the logic expects you to manage in races while boost is
    randomized. Only matters when Progressive Boost is on. Platinum Time
    Trials follow it too.

    Below, "boost" means your first Progressive Boost, or three useful
    weapons when Itemsanity is on. The useful weapons are Mask, Missile,
    Bomb, Warpball and N. Tropy Clock.

    - **easy**: winning, finishing on the podium and holding 1st need boost.
    - **medium** (default): winning needs boost.
    - **hard**: no extra requirement.

    On easy and medium, holding 1st needs your first Progressive Boost, or
    one useful weapon when Itemsanity is on.

    Some tracks need Ultimate Sacred Fire whatever you pick here: finishing
    Cortex Castle, Hot Air Skyway and Cortex Vortex, and holding 1st on
    Cortex Castle and Hot Air Skyway. Oxide Station needs it for both,
    unless Shortcut Knowledge is hard."""
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
    leave out keep their default weight. `clocked_out` defaults to 3 and
    applies the retail clock to the receiving player for 7.7 seconds.
    `reverse_camera` defaults to 2 and forces rear view with normal steering,
    using the local Trap Duration setting.

    `first_person`, `wireframe`, `upside_down`, `mirror_mode`, `demo_camera`
    and `reverse_camera` change the camera or the screen and can be visually
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

class CupSweepChecks(Toggle):
    """Winning first place in all four races of a cup sends a separate check.

    The four wins must belong to one uninterrupted cup attempt. Points wins
    remain separate.
    """
    display_name = "Cup Sweep Checks"


class Crystalsanity(Toggle):
    """Each authored crystal in an included Crystal Challenge is a check.

    Crystal numbers identify fixed positions, not pickup order. The arena's
    completion check remains separate.
    """
    display_name = "Crystalsanity"


class HitCharacter(Toggle):
    """Add a check for each of the 16 racers, paid the first time you hit
    them in an Adventure race.

    The 8 retail Adventure racers can race you from the start. The other 8
    join once you win their boss race or the tracks that unlock them. If
    that race is not in your seed, Keys unlock them instead; the spoiler log
    lists which racers use Keys."""
    display_name = "Hit Character Checks"


class RelicPerfectChecks(Toggle):
    """Add a check to each Relic Race for breaking every time crate in it.

    You get the check even when your time does not earn a relic, and it
    never changes which relic you get."""
    display_name = "Relic Race Perfect Checks"


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
    """Adds a Useful item to the pool that guarantees a Mask from the first
    row of crates on Papu's Pyramid.

    This allows for a more consistent chance of being able to pull off the
    'Tiziano' ultra shortcut.

    With Itemsanity on you also need to have unlocked the Mask for it to
    appear."""
    display_name = "Tizi Helper"


class ReserveTopUp(DefaultOnToggle):
    """Let non-trap filler include Reserve Top-Up at relative weight 1
    beside Wumpa Fruit at weight 6 (bundles retain weights 3 and 1).

    One copy adds 983 raw reserve units to active positive reserves in a live
    race. It waits in the hub or without a boost, preserves the fire cap and
    can cross into purple Saffi fire, including with Progressive Boost.
    It gives no weapon. Off preserves the existing filler draw."""
    display_name = "Reserve Top-Up"


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


class WumpaShopSlots(Range):
    """How many Wumpa Shop slots each of the five hubs gets.

    In Adventure races, every fruit you collect while already holding 10 is
    banked, and so is the fruit you hold when you finish a race. Spend banked
    fruit at the save screen of a hub: each slot is a check with a price. 10
    (default) adds 50 checks, 25 adds 125. 0 turns the shop off.

    Later slots of each shop go on sale once enough fruit has been banked over
    the whole seed. Any slot may hold any item unless Wumpa Shop Progression
    is excluded. Buying needs a connection to the server."""
    display_name = "Wumpa Shop Slots"
    range_start = 0
    range_end = 25
    default = 10


class WumpaShopPrices(Range):
    """Scales every Wumpa Shop price and every shelf unlock, in percent.

    100 (default) keeps the normal prices: 10 to 30 fruit in N. Sanity Beach up
    to 40 to 80 in Citadel City. A slot that holds progression always costs
    the lowest price of its hub."""
    display_name = "Wumpa Shop Prices"
    range_start = 25
    range_end = 400
    default = 100


class WumpaShopProgression(Choice):
    """Whether Wumpa Shop slots may hold progression items.

    - **allowed** (default): any shop slot may hold progression, priced at
      its hub's lowest price.
    - **excluded**: no shop slot holds progression; useful items, filler
      and traps only."""
    display_name = "Wumpa Shop Progression"
    option_allowed = 0
    option_excluded = 1
    default = 0


class WumpaShopHints(DefaultOnToggle):
    """Opening a Wumpa Shop page hints the unsold items on it, so their owners
    see where their items are."""
    display_name = "Wumpa Shop Hints"


class GoalWumpa(Range):
    """Bank this many Wumpa Fruit over the whole seed for the goal.

    0 (default) turns this condition off. Banked fruit is the fruit you collect
    while already holding 10, plus the fruit you hold when you finish a race.
    Spending fruit in the Wumpa Shop never lowers this count. Every goal
    condition you set must be met. 1000 is a long goal of many races."""
    display_name = "Wumpa Goal"
    range_start = 0
    range_end = 5000
    default = 0


class TurboGrant(Toggle):
    """Add one useful item that puts a Turbo into your weapon slot at the start
    of every race, once you have received it.

    One Turbo per race; a restart counts as a new race. If your slot is
    occupied, that race's Turbo waits until the slot is free. With Itemsanity
    on, it also waits for the Turbo weapon to be unlocked. Progressive Boost
    still controls how strong the fired Turbo is. This uses one filler slot and
    adds no location.

    Changed in 0.3.0: before, the item gave a single Turbo once."""
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


class SpoilerItems(Toggle):
    """Hide reward previews until you find the items that show them.

    Off (default): warp pads and AP item boxes show what they hold, as usual.

    On: the floating rewards above warp pads stay hidden until you receive
    Warp Pad Preview. Until then, a pad with any open location shows one
    plain Archipelago marker, and a finished pad shows nothing. With Item Box
    Locations and Item Box Colours both on, AP item boxes also stay pink until
    you receive AP Box Colours. You can switch the in-game Item Box Colours
    row to OFF before that, and the boxes then stay pink after it arrives.

    Both are useful items that add no location, so each one takes a slot that
    would otherwise hold filler. Pads still open, close and count their checks
    as usual; only the previews wait for the items."""
    display_name = "Spoiler Items"


class RaceTypeSelector(Choice):
    """When a warp pad asks which race to run.

    - **always** (default): every race pad you can enter opens the race
      type menu, with the races the pad has open now, in the pad's order.
    - **productive**: the menu opens only when more than one race type still
      has a check, or when none has; with exactly one, the pad loads it.

    Race types with nothing left to check are grey but you can still pick
    them to race again. This is the starting value: the client's Options
    menu can change it at any time. It only changes the menu, never what is
    in logic."""
    display_name = "Race Type Selector"
    option_productive = 0
    option_always = 1
    default = 1


class TrackerPadLaunch(DefaultOnToggle):
    """Start warp pad and boss garage activities from the in-game tracker.

    On (default): in a hub, pause and open the tracker, pick a pad or boss
    garage and press Cross to see what it offers. Modes you can start now are
    listed first; modes you cannot start yet stay in the list, grey, with the
    reason (hub Keys, the pad's requirement, a racer, the second requirement).
    Starting one takes you to that pad's hub and enters the pad exactly as if
    you had driven onto it, with the same requirements.

    Off: the tracker only shows information. A race or sync host can turn
    this off for everyone. This never changes what is in logic."""
    display_name = "Tracker Pad Launch"


class AdventureStructure(Choice):
    """Which race on a track earns its Trophy Race check.

    - **classic** (default): as in the retail game. Win the Trophy Race
      first; the CTR Challenge and the Relic Race open after it.
    - **ctr_first**: the first race on each track is its CTR Challenge.
      First place sends that track's Trophy Race check, and first place with
      the letters also sends its CTR Token Challenge check. The track has no
      plain Trophy Race: item boxes, Wumpa and placement checks come from the
      CTR Challenge race, and placement counts even without the letters.
      The Relic Race still opens after that, behind the warp pad's second
      requirement.

    The checks keep their names: "Trophy Race" stays the track's first check
    even though the CTR Challenge earns it. A track without a CTR Challenge
    keeps the classic order."""
    display_name = "Adventure Structure"
    option_classic = 0
    option_ctr_first = 1
    default = 0


class WarpPadUnlockRequirements(Choice):
    """How warp pads unlock.

    - **randomized** (default): every warp pad gets a randomized entry
      requirement (trophies, tokens, relics, keys, gems...), always collectable
      before that pad opens.
    - **vanilla**: pads open on their vanilla trophy counts, like the original
      adventure.
    - **random_without_4_keys**: like randomized, but no pad needs all 4 Keys.
      Pads can still ask for 1 to 3 Keys. For no Keys on pads at all, set
      `Key: 0` in Requirement Weights.

    Boss garages follow this too: vanilla asks 4, 8, 12 and 16 Trophies, and
    the two random values draw by Garage Requirement Level."""
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


class RequirementWeights(OptionDict):
    """How often each item is drawn for a random warp pad or garage requirement.

    Each entry is `item name: weight`. Higher means picked more often, 0
    means never; Trophy must stay above 0. Items you leave out keep the weight
    shown here. Ignored with vanilla requirements.

    Valid keys: Trophy, Key, the five CTR Token colours, the three Relic
    tiers and the five Gem colours."""
    # Trophy must stay above 0 because it bootstraps the randomized warp-pad
    # requirements. Unlisted items fall back to their icebound_beta5 weight.
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


class WarpPadRules(OptionDict):
    """Set the entry requirement of chosen warp pads yourself.

    Each entry is `pad name: {item: ..., count: ...}`. The pad name is the
    pad's own name without "Warp Pad", for example `Crash Cove`, `Roo's Tubes`,
    `Red Cup` or `Skull Rock`. A track or cup that is shuffled onto a pad
    uses that pad's requirement, and hub doors still need their Keys.

    `item` is `free`, Trophy, Key, a CTR Token colour (Red CTR Token ...), a
    Relic tier (Sapphire Relic, Gold Relic, Platinum Relic), a Gem colour
    (Red Gem ...), or the sums AnyCtrToken, AnyRelic and AnyGem. `free` needs
    `count: 0`; every other item needs a whole `count` of at least 1, no more
    than the seed has of it. Wumpa Fruit and character items are not allowed.

    The rule is the first requirement of the pad. A second requirement on the
    pad still follows Two-Stage Gate Density. Pads you leave out keep the
    randomized rule from Warp Pad Unlock Requirements. Your entries ignore
    Requirement Weights, and random_without_4_keys refuses a rule of 4 Keys.
    A seed with vanilla warp pad requirements refuses any entry. A named pad
    always gets content.

    Example:
    ```yaml
    warp_pad_rules:
      Crash Cove: {item: free, count: 0}
      Red Cup: {item: Red CTR Token, count: 3}
      Skull Rock: {item: AnyRelic, count: 2}
    ```"""
    display_name = "Warp Pad Rules"
    default = {}


class DeathLink(Choice):
    """What happens to you when another DeathLink player dies. DeathLink Send
    chooses what makes you send a death.

    - **off** (default): disabled, nothing is sent or received.
    - **mask_reset**: a received death forces the full mask reset on you.
    - **race_loss**: a received death ends your current race on the spot as a
      last-place loss, and nothing that race would have paid out (placement,
      trophy, relic, and similar checks) is awarded. In a Gem Cup the cup
      carries on, and if that was the last race and you still win the cup on
      points, the cup reward is still paid.
    - **weapon_hit**: a received death spins you out as if a weapon hit you.
      A shield, an Aku Aku mask or the short invincibility after a hit stop
      it, just as they stop a weapon.

    While DeathLink Send is left at its default, this option also decides what
    you send, as it did before DeathLink Send existed: mask_reset and
    weapon_hit send on mask grabs, race_loss on mask grabs and race losses. Set DeathLink Send to choose
    sending yourself; listing
    any trigger there while this is off turns this on as mask_reset, because
    a slot that sends deaths also receives them. Deaths are
    only sent and received during adventure-mode races; a received death is
    never saved for a later race."""
    # A received death never triggers an outgoing one (no ping-pong). Type
    # rationale: AP core ships DeathLink as an on/off Toggle; CTR uses a
    # Choice because the receive effects are real gameplay differences. off
    # mirrors 0 into slot_data, matching the Toggle convention native keys
    # off. The integer values are the wire contract with native
    # (ap_deathlink.h CTR_DL_*): race_loss = 3 (issue #286) ends the attempt
    # as a forced loss on receive; a native build predating it falls back to
    # the mask reset for any unknown nonzero value; weapon_hit = 4 (issue
    # #483) spins the kart out on receive, and a native predating it receives
    # it as the mask reset by the same fallback. Send conditions live in
    # DeathLinkSend below; this option only couples to them through the legacy
    # fallback (DL_LEGACY_SEND).
    display_name = "DeathLink"
    option_off = 0
    option_mask_reset = 1
    option_race_loss = 3
    option_weapon_hit = 4
    default = 0


# Wire bits of slot_data ctr_options.death_link_send. Fixed contract with
# native: never renumber.
DL_SEND_MASK_GRAB = 1
DL_SEND_WEAPON_HIT = 2
DL_SEND_RACE_LOSS = 4

DL_SEND_BITS = {
    "mask_grab": DL_SEND_MASK_GRAB,
    "weapon_hit": DL_SEND_WEAPON_HIT,
    "race_loss": DL_SEND_RACE_LOSS,
}

# Legacy coupling, used while DeathLink Send is left at its default: the send
# side that each death_link value implied before death_link_send existed.
# weapon_hit (#483) is newer than death_link_send and has no history to keep;
# it couples like mask_reset (mask grabs only), the mildest choice, so a
# weapon_hit slot does not broadcast a death for every hit it takes. Native's
# AP_DeathLinkLegacySendMask maps 4 the same way.
DL_LEGACY_SEND = {
    DeathLink.option_off: 0,
    DeathLink.option_mask_reset: DL_SEND_MASK_GRAB,
    DeathLink.option_race_loss: DL_SEND_MASK_GRAB | DL_SEND_RACE_LOSS,
    DeathLink.option_weapon_hit: DL_SEND_MASK_GRAB,
}


class DeathLinkSend(OptionSet):
    """What makes you send a DeathLink. Only matters while DeathLink is not
    off.

    - **mask_grab**: falling off the track or being eaten.
    - **weapon_hit**: getting hit by a weapon.
    - **race_loss**: losing a race or the whole Gem Cup, or restarting or
      exiting to the map from the pause menu, but only while that race's
      win is in logic for you and not collected yet. Losing a race you
      already won, or one you are not expected to win yet, sends nothing.

    Default: **follow_death_link**, the only value that is not a trigger. It
    sends what DeathLink implies: mask_reset and weapon_hit send on mask
    grabs, race_loss on mask grabs and race losses, off sends nothing. Any list you write replaces that, so every
    trigger you want must be in it (follow_death_link listed together with
    triggers is ignored). To receive DeathLinks without sending any,
    use an empty list (`death_link_send: []`). A death that was forced on you
    by a received DeathLink is never sent back.

    There is no send-only DeathLink: if you list any trigger while DeathLink
    is off, DeathLink is turned on as mask_reset (the mildest receive effect).
    Set DeathLink to mask_reset, weapon_hit
    or race_loss yourself to choose the receive effect."""
    # Unset vs explicitly empty: the default is the one-element sentinel set
    # {"follow_death_link"}, so a YAML that omits the option (every YAML written
    # before it existed) gets the legacy coupling, while an explicit empty list
    # is a real empty set and means "send nothing". A plain empty-set default
    # could not tell those two apart. Mixing the sentinel with triggers is
    # resolved in verify() (the triggers win) instead of raising, because the
    # fuzzer and random rolls draw arbitrary subsets of valid_keys. Bits are
    # the slot_data contract with native, see DL_SEND_BITS.
    display_name = "DeathLink Send"
    valid_keys = {"follow_death_link", "mask_grab", "weapon_hit", "race_loss"}
    default = frozenset({"follow_death_link"})

    def verify(self, world, player_name, plando_options) -> None:
        super().verify(world, player_name, plando_options)
        # A random or hand-written set that lists follow_death_link next to
        # triggers means the triggers: the sentinel is dropped, not an error.
        if "follow_death_link" in self.value and len(self.value) > 1:
            self.value.discard("follow_death_link")

    def send_mask(self, death_link_value: int) -> int:
        """The int bitmask emitted as slot_data ctr_options.death_link_send."""
        if "follow_death_link" in self.value:
            return DL_LEGACY_SEND.get(death_link_value, DL_SEND_MASK_GRAB)
        mask = 0
        for key in self.value:
            mask |= DL_SEND_BITS[key]
        return mask


class DeathLinkAmnesty(Range):
    """How many of your deaths must pile up before one is actually sent. 1
    (default) sends every death; N sends one per N. Meant for weapon hits,
    which are frequent. Incoming deaths are unaffected; amnesty only
    throttles what you send."""
    # Does nothing useful when only mask grabs and race losses send (both are
    # rare) and is inert while DeathLink is off.
    display_name = "DeathLink Amnesty"
    range_start = 1
    range_end = 30
    default = 1


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


class RemovePlayableOxide(Toggle):
    """Take Nitros Oxide out of the racers you can unlock.

    His unlock item is not created, so the pool gets one more filler or trap
    instead. Random Any never starts you as him and no warp pad is locked to
    him. He still races against you as the boss, and his Hit Character check
    stays. Needs Character Unlocks on. Cannot be used with Starting Character
    set to Nitros Oxide."""
    display_name = "Remove Playable Oxide"


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


class ContentItemPool(OptionDict):
    """How many of each counted item the seed has. Empty (default) keeps 16
    Trophies, 4 Keys, 18 Sapphire Relics, 18 Gold Relics, 0 Platinum Relics, 4 CTR
    Tokens of each colour and the 5 Gems.

    `base` sets the counts a requirement may ask for. `extra` adds copies that
    replace filler. Keys are always 4. A relic tier's Time Trial checks exist on
    as many Relic Races as there are items of that tier, drawn at random, capped
    by the Relic Races in the seed; items beyond that land on other checks. The
    five surface items are created too, and are dropped together when the items
    do not fit; any other shortage is refused.

    Example, fewer relics:
    ```yaml
    item_pool:
      base:
        relics: {sapphire: 12, gold: 6, platinum: 0}
    ```"""
    display_name = "Item Pool"
    default = {}


class RetailTracks(OptionSet):
    """Which of the 18 original race tracks may get a warp pad, a cup leg or a
    random boss race.

    **all** (default) is every one of them: the 16 Trophy tracks, Slide
    Coliseum and Turbo Track. Otherwise list track names."""
    display_name = "Original Tracks"
    valid_keys = ["all"] + sorted(BOSS_VENUE_TRACKS)
    default = frozenset({"all"})


class TrackModes(OptionDict):
    """Which races each track offers: `trophy`, `ctr` and `relic`.

    `default` applies to every track, Slide Coliseum and Turbo Track included.
    A track name replaces `default` for that track; a custom track goes by its
    track key or its title. A track never gets a race it cannot run. A list
    with `ctr` needs `trophy` too, and every list needs at least one race.

    Example, Relic Races only on the two trial tracks:
    ```yaml
    track_modes:
      default: [trophy, ctr, relic]
      Slide Coliseum: [relic]
      Turbo Track: [relic]
    ```"""
    display_name = "Track Modes"
    supports_weighting = False
    default = {"default": ["trophy", "ctr", "relic"]}


class CustomTracks(OptionList):
    """Custom tracks the seed may use on warp pads, in cups and as boss tracks.

    Each entry is a track's whole package descriptor, as its download gives it
    to you: use it as it is. The game checks the files against it when it loads
    the track. A custom track takes the place of an original track on a pad,
    and a seed with more tracks than pads leaves some out. `required_entries`
    keeps one in the seed. A track with a named block keeps its own check names
    (for example "Baby T Park: Trophy Race"). Any other track shows its title,
    and a title that matches an original track gets "(Custom)" added.

    The old form, a mapping that puts Baby T Park on the Purple Gem Cup, is
    refused."""
    # default is empty on purpose: an example would put file digests a player
    # has not verified into every generated template.
    display_name = "Custom Tracks"
    supports_weighting = False
    default = []

    @classmethod
    def from_any(cls, data: Any) -> "CustomTracks":
        if isinstance(data, dict):
            if data:
                raise OptionError("CTR custom_tracks: the mapping that puts a custom track on the Purple Gem Cup is "
                                  "gone. Use a list of track packages.")
            return cls([])
        return super().from_any(data)


class CortexVortexTrack(Choice):
    """Add Cortex Vortex as a track with all three races.

    - **off** (default): it is no pad or cup track. The Final Challenge can
      still race there.
    - **in_pool**: the seed may use it on a pad or in a cup, or not at all.
    - **own_pad**: it is sure to get a warp pad.

    Crossing its finish line needs Ultimate Sacred Fire. It has no item boxes."""
    # alias_false: a YAML `off` reaches us as false. `true` has no alias: the old
    # true meant a dropped destination, which is gone.
    display_name = "Cortex Vortex Track"
    option_off = 0
    option_in_pool = 1
    option_own_pad = 2
    alias_false = 0
    default = 0


class RequiredEntries(OptionList):
    """Content that must get its own warp pad.

    List original track names, arena names and custom track keys. For Cortex
    Vortex use Cortex Vortex Track: own_pad instead."""
    display_name = "Required Entries"
    default = []


class CupCount(Range):
    """How many cups the seed has.

    The first five are the original Gem Cups, Red first, each with its Gem
    check. A sixth cup and later take names from the cup name pool. 0 means no
    cups."""
    display_name = "Cup Count"
    range_start = 0
    range_end = 27
    default = 5


class CupTracks(Choice):
    """Which tracks a cup races. Applies to every cup. Slide Coliseum and Turbo
    Track are never cup races.

    - **off**: an original Gem Cup races its original four tracks. A sixth cup
      and later draw four different tracks.
    - **random_repeats**: every race is drawn, repeats allowed. `random` means
      the same here.
    - **random_no_repeats** (default): four different tracks per cup."""
    # Archipelago keeps the option name `random` for itself, so the value is
    # random_repeats and the word `random` maps to it.
    display_name = "Cup Tracks"
    option_off = 0
    option_random_repeats = 1
    option_random_no_repeats = 2
    alias_false = 0
    default = 2

    @classmethod
    def from_text(cls, text: str) -> "CupTracks":
        if text.strip().lower() == "random":
            return cls(cls.option_random_repeats)
        return super().from_text(text)


class CupCustomLegs(Range):
    """The most races per cup that may be a custom track or Cortex Vortex."""
    display_name = "Custom Races Per Cup"
    range_start = 0
    range_end = 4
    default = 4


class CrystalChallengeCount(Range):
    """How many Crystal Challenges the seed has, drawn from Crystal Arenas.

    0 means no arenas: their checks leave the seed. Purple CTR Tokens stay in
    the item pool, so they can still be found anywhere."""
    display_name = "Crystal Challenge Count"
    range_start = 0
    range_end = 7
    default = 4


class CrystalArenas(OptionSet):
    """Which arenas a Crystal Challenge can use.

    Default: the four original arenas. Listing Parking Lot, The North Bowl or
    Lab Basement brings in that arcade arena. It takes a normal warp pad, has
    twenty crystals and gives no Purple CTR Token. Crystal Challenge Count
    cannot be above the number of arenas listed here."""
    display_name = "Crystal Arenas"
    valid_keys = sorted(ARENA_NAMES)
    default = frozenset(ORIGINAL_ARENA_NAMES)


class BossGarages(DefaultOnToggle):
    """Fill the four boss garages and N. Oxide's garage with boss races.

    Off leaves them empty, which needs Oxide Goal disabled, Bosses Required
    Goal 0 and a Gems or Wumpa goal."""
    display_name = "Boss Garages"


class BossCups(Range):
    """How many of the four garages hold a four-race boss cup instead of one
    race. The garage's boss races all four, with one weapon set."""
    display_name = "Boss Cups"
    range_start = 0
    range_end = 4
    default = 0


class GarageRequirementLevel(Choice):
    """How large a drawn garage requirement is. With random pad requirements
    each garage draws a kind and a count. Vanilla requirements ask 4, 8, 12 and
    16 Trophies. N. Oxide's garage always asks for 4 Keys.

    - **standard**: small.
    - **high** (default): medium, growing with each garage.
    - **very_high**: large.
    - **chaotic**: anything, on any garage."""
    display_name = "Garage Requirement Level"
    option_standard = 0
    option_high = 1
    option_very_high = 2
    option_chaotic = 3
    default = 1


class BossTrackPool(OptionSet):
    """Tracks a random boss race or boss cup may use. Empty (default) means
    every eligible track.

    List original track names, Cortex Vortex, and custom tracks by track key or
    title. Cortex Vortex and custom tracks count when they are in the seed and
    carry the boss's attacks. A boss race needs one track of its own, and a boss
    cup needs four different tracks. Ignored when Boss Track Shuffle is off."""
    # No valid_keys: a custom track's name is only known from its package.
    display_name = "Boss Track Pool"
    default = frozenset()


class BossCharacterPool(OptionSet):
    """With Boss Opponent Shuffle on, the racers a boss may be.

    Default: every racer but Nitros Oxide. Listing Nitros Oxide lets him be a
    garage boss; both of his own races then go to another racer of this list.
    Ignored when Boss Opponent Shuffle is off."""
    display_name = "Boss Character Pool"
    valid_keys = sorted(BOSS_OPPONENT_NAMES)
    default = frozenset(BOSS_GARAGE_OPPONENTS)


class BossWeaponPool(OptionSet):
    """With Boss Kit Shuffle on, the weapons a garage boss may get. Ignored
    when Boss Kit Shuffle is off."""
    display_name = "Boss Weapon Pool"
    valid_keys = sorted(BOSS_ATTACK_FAMILIES)
    default = frozenset(BOSS_ATTACK_FAMILIES)


class OxideWeaponPool(OptionSet):
    """With N. Oxide Attack Profile all_compatible, the weapons N. Oxide's
    garage may get, Super Engine included. Separate from Boss Weapon Pool.
    Ignored with the retail profile."""
    display_name = "N. Oxide Weapon Pool"
    valid_keys = sorted(OXIDE_ATTACK_FAMILIES)
    default = frozenset(OXIDE_ATTACK_FAMILIES)


class PadPlacement(Choice):
    """Where content sits on the 27 warp pads. Each pad keeps its own
    requirement, whatever lands on it.

    - **vanilla**: original content on its original pad, other content on the
      remaining pads.
    - **shuffle_within_kind**: tracks on track pads, cups on cup pads, arenas
      on arena pads.
    - **shuffle** (default): any content on any pad.

    Content that does not fit its own kind of pad goes on any free pad."""
    display_name = "Pad Placement"
    option_vanilla = 0
    option_shuffle_within_kind = 1
    option_shuffle = 2
    default = 2


class RaceModeOrder(Choice):
    """In which order a track's races open on its pad.

    - **fixed** (default): Trophy Race, CTR Challenge, Relic Race.
    - **per_seed**: one drawn order for the whole seed.
    - **per_pad**: a drawn order on each pad."""
    display_name = "Race Mode Order"
    option_fixed = 0
    option_per_seed = 1
    option_per_pad = 2
    default = 0


class PodiumRungs(OptionSet):
    """Which placement checks each track with a Trophy Race has. Empty means
    none.

    - **held_1st**, **held_3rd**, **held_5th**: earned the moment you hold that
      place on track, for half a second.
    - **finish_on_podium**: finish in the top 3.
    - **finish_any**: finish in any place.

    A higher place also pays the rungs below it. Default: all but held_5th.

    With Progressive Boost on, on easy and medium Logic Difficulty, Held 1st
    needs your first Progressive Boost, or one useful weapon when Itemsanity is
    on. On Cortex Castle and Hot Air Skyway it needs Ultimate Sacred Fire, and
    on Oxide Station too unless Shortcut Knowledge is hard."""
    display_name = "Podium Rungs"
    valid_keys = ["held_1st", "held_3rd", "held_5th", "finish_on_podium", "finish_any"]
    default = frozenset({"held_1st", "held_3rd", "finish_on_podium", "finish_any"})


@dataclass
class ctrAPOptions(PerGameCommonOptions):

    # content: tracks, custom tracks, Cortex Vortex
    retail_tracks: RetailTracks
    track_modes: TrackModes
    custom_tracks: CustomTracks
    cortex_vortex_track: CortexVortexTrack
    required_entries: RequiredEntries
    # content: cups and arenas
    cup_count: CupCount
    cup_tracks: CupTracks
    cup_custom_legs: CupCustomLegs
    one_lap_cups: OneLapCups
    crystal_challenge_count: CrystalChallengeCount
    crystal_arenas: CrystalArenas
    # content: bosses
    boss_garages: BossGarages
    boss_cups: BossCups
    garage_requirement_level: GarageRequirementLevel
    boss_track_shuffle: BossTrackShuffle
    boss_track_pool: BossTrackPool
    boss_opponent_shuffle: BossOpponentShuffle
    boss_character_pool: BossCharacterPool
    boss_track_assignment: BossTrackAssignment
    boss_kit_shuffle: BossKitShuffle
    boss_attack_assignment: BossAttackAssignment
    boss_attack_intensity: BossAttackIntensity
    boss_loss_easing: BossLossEasing
    boss_weapon_pool: BossWeaponPool
    oxide_attack_profile: OxideAttackProfile
    oxide_weapon_pool: OxideWeaponPool
    purple_cup_boss_gauntlet: PurpleCupBossGauntlet
    # goal
    oxide_goal: OxideGoal
    oxide_1_optional: Oxide1Optional
    bosses_required_goal: BossesRequiredGoal
    gems_required_goal: GemsRequiredGoal
    goal_wumpa: GoalWumpa
    oxide_final_challenge_unlock: FinalOxideUnlock
    oxide_final_challenge_relic_count: FinalOxideRelicCount
    oxide_final_track: OxideFinalTrack
    # pads and requirements
    pad_placement: PadPlacement
    race_mode_order: RaceModeOrder
    adventure_structure: AdventureStructure
    warppad_unlock_requirements: WarpPadUnlockRequirements
    requirement_weights: RequirementWeights
    two_stage_density: TwoStageDensity
    warp_pad_rules: WarpPadRules
    racer_locked_pads: RacerLockedPads
    shuffle_keys: ShuffleKeys
    shuffle_gems: ShuffleGems
    # checks
    podium_rungs: PodiumRungs
    relic_perfect_checks: RelicPerfectChecks
    lettersanity: Lettersanity
    letters_per_track: LettersPerTrack
    cup_sweep_checks: CupSweepChecks
    box_locations: BoxLocations
    itemsanity: Itemsanity
    crystalsanity: Crystalsanity
    wumpa_check: WumpaCheck
    hit_character: HitCharacter
    wumpa_shop_slots: WumpaShopSlots
    wumpa_shop_prices: WumpaShopPrices
    wumpa_shop_progression: WumpaShopProgression
    wumpa_shop_hints: WumpaShopHints
    # items and traps
    item_pool: ContentItemPool
    start_inventory_from_pool: StartInventoryPool
    trap_fill_percentage: TrapFillPercentage
    trap_weights: TrapWeights
    wumpa_bundles: WumpaBundles
    reserve_top_up: ReserveTopUp
    progressive_starting_wumpa: ProgressiveStartingWumpa
    turbo_grant: TurboGrant
    tizi_helper: TiziHelper
    # characters and stats
    starting_character: StartingCharacter
    character_unlocks: CharacterUnlocks
    remove_playable_oxide: RemovePlayableOxide
    starting_stat_class: StartingStatClass
    penta_stats: PentaStats
    editable_stats: EditableStats
    progressive_stats: ProgressiveStatsMode
    # boost
    progressive_boost: ProgressiveBoostMode
    progressive_boost_blue_fire: ProgressiveBoostBlueFire
    logic_difficulty: LogicDifficulty
    shortcut_knowledge: ShortcutKnowledge
    # deathlink
    death_link: DeathLink
    death_link_send: DeathLinkSend
    deathlink_amnesty: DeathLinkAmnesty
    # display
    warp_pad_item_display: WarpPadItemDisplay
    ap_item_type_colors: ApItemTypeColors
    color_boxes_by_item: ColorBoxesByItem
    spoiler_items: SpoilerItems
    race_type_selector: RaceTypeSelector
    tracker_pad_launch: TrackerPadLaunch


ap_ctr_option_groups: Dict[str, List[Any]] = {
    # Ordered the way a player fills a YAML: what is in the seed, what finishes
    # it, how it opens, what pays out, then items, racers, boost and cosmetics.
    # Every option must appear in exactly one group. Anything left out lands in
    # an unlabelled bucket at the bottom of the web page.
    "Tracks": [RetailTracks, TrackModes, CustomTracks, CortexVortexTrack, RequiredEntries],
    "Cups and Arenas": [CupCount, CupTracks, CupCustomLegs, OneLapCups, CrystalChallengeCount, CrystalArenas],
    "Bosses": [BossGarages, BossCups, GarageRequirementLevel, BossTrackShuffle, BossTrackPool, BossOpponentShuffle,
               BossCharacterPool, BossTrackAssignment, BossKitShuffle, BossAttackAssignment, BossAttackIntensity,
               BossLossEasing, BossWeaponPool, OxideAttackProfile, OxideWeaponPool, PurpleCupBossGauntlet],
    "Goal": [OxideGoal, Oxide1Optional, BossesRequiredGoal, GemsRequiredGoal, GoalWumpa, FinalOxideUnlock,
             FinalOxideRelicCount, OxideFinalTrack],
    "Pads and Requirements": [PadPlacement, RaceModeOrder, AdventureStructure, WarpPadUnlockRequirements,
                              RequirementWeights, TwoStageDensity, WarpPadRules, RacerLockedPads, ShuffleKeys,
                              ShuffleGems],
    "Checks": [PodiumRungs, RelicPerfectChecks, Lettersanity, LettersPerTrack, CupSweepChecks, BoxLocations,
               Itemsanity, Crystalsanity, WumpaCheck, HitCharacter],
    "Wumpa Shop": [WumpaShopSlots, WumpaShopPrices, WumpaShopProgression, WumpaShopHints],
    "Items and Traps": [ContentItemPool, TrapFillPercentage, TrapWeights, WumpaBundles, ReserveTopUp,
                        ProgressiveStartingWumpa, TurboGrant, TiziHelper],
    "Characters and Stats": [StartingCharacter, CharacterUnlocks, RemovePlayableOxide, StartingStatClass, PentaStats,
                             EditableStats, ProgressiveStatsMode],
    "Boost": [ProgressiveBoostMode, ProgressiveBoostBlueFire, LogicDifficulty, ShortcutKnowledge],
    "DeathLink": [DeathLink, DeathLinkSend, DeathLinkAmnesty],
    "Display": [WarpPadItemDisplay, ApItemTypeColors, ColorBoxesByItem, SpoilerItems, RaceTypeSelector,
                TrackerPadLaunch],
}


def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]


# Retired options (one generator row 7). They are in no option list, so a YAML that
# still names them has that name ignored silently (Stef, 2026-10-30). The original
# generator's code still names some of them; row 12 deletes both.

class BossTrackAllowlist(OptionSet):
    """With Boss Track Shuffle on, draw boss tracks only from these tracks.
    Leave empty to allow every track. Ignored when Boss Track Shuffle is
    off."""
    display_name = "Boss Track Allowlist"
    valid_keys = sorted(BOSS_VENUE_TRACKS)
    default = frozenset()


class BossTrackBlocklist(OptionSet):
    """With Boss Track Shuffle on, never draw these tracks for a boss race.
    Applied after the allowlist. Ignored when Boss Track Shuffle is off."""
    display_name = "Boss Track Blocklist"
    valid_keys = sorted(BOSS_VENUE_TRACKS)
    default = frozenset()


class BossEncounterRepeats(Choice):
    """Whether two boss garages may use the same drawn track.

    - **disallow** (default): the four bosses race on four different tracks.
    - **allow**: each garage draws on its own, so tracks can repeat.

    A track that is also an ordinary race or a Gem Cup leg never counts as a
    repeat."""
    display_name = "Boss Encounter Repeats"
    option_disallow = 0
    option_allow = 1
    default = 0


class BossOxideInPool(Toggle):
    """With Boss Opponent Shuffle on, N. Oxide can be drawn as the racer of
    one of the four boss garages, and N. Oxide's own garage then races a
    randomly drawn racer instead of N. Oxide (both of its races). All five
    bosses are different racers. N. Oxide's garage keeps its door, its
    checks and the goal. Ignored when Boss Opponent Shuffle is off."""
    # Decision 7 of 2026-10-28. Wire: the plan's bosses record. See content_bosses.py.
    display_name = "Boss Pool Includes N. Oxide"


class BossCharacterAllowlist(OptionSet):
    """With Boss Opponent Shuffle on, draw boss opponents only from these
    racers. Leave empty to allow every racer. Ignored when Boss Opponent
    Shuffle is off."""
    display_name = "Boss Character Allowlist"
    valid_keys = sorted(BOSS_OPPONENT_NAMES)
    default = frozenset()


class BossCharacterBlocklist(OptionSet):
    """With Boss Opponent Shuffle on, never draw these racers as a boss.
    Applied after the allowlist. Ignored when Boss Opponent Shuffle is off."""
    display_name = "Boss Character Blocklist"
    valid_keys = sorted(BOSS_OPPONENT_NAMES)
    default = frozenset()


class BossPowerupBlocklist(OptionSet):
    """With Boss Kit Shuffle on, weapon types a boss never uses. Ignored when
    Boss Kit Shuffle is off."""
    display_name = "Boss Powerup Blocklist"
    valid_keys = sorted(BOSS_ATTACK_FAMILIES)
    default = frozenset()


class OxidePowerupBlocklist(OptionSet):
    """With N. Oxide Attack Profile all_compatible, weapon types N. Oxide's
    garage never uses. Separate from Boss Powerup Blocklist. Ignored with
    the retail profile."""
    display_name = "N. Oxide Powerup Blocklist"
    valid_keys = sorted(OXIDE_ATTACK_FAMILIES)
    default = frozenset()


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


class LegacyCustomTracks(OptionDict):
    """Race a community custom track in place of a Gem Cup.

    The cup keeps its warp pad, but behind it is one race on the custom track
    instead of four retail tracks. Leave this empty (the default) for a
    normal seed.

    You also need the track's files and a client that can load them. Use the
    track's exact entry rather than writing your own: generation refuses an
    entry this version does not know, and the game refuses files that do not
    match it.

    The only known track is baby-t-park, and only purple_gem_cup can be
    replaced.

    A track this version knows by name keeps that name for its checks
    everywhere (for example "Baby T Park: Trophy Race"). For any other
    track, an entry may carry a `title` and an `author`. They only change the
    name the room and Universal Tracker show for the track's checks; a title
    that matches a retail track gets "(Custom)" added."""
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


class IncludeArcadeArenas(Toggle):
    """Permit Parking Lot, The North Bowl and Lab Basement in the Crystal pool.

    Uses the explicit content_pool profile and ordinary physical pad seats.
    Does nothing when battle arenas are off. Each arena has twenty authored
    crystals, a separate completion check and no Purple Token grant.
    """
    display_name = "Include Arcade Arenas"


class ShuffleWarpPadsBattleArenas(DefaultOnToggle):
    """Include the 4 Battle Arenas and their Crystal Challenges in the seed.

    - **on** (default): their checks are normal locations and, with
      randomized unlocks, their warp pads get a randomized requirement.
    - **off**: the four Crystal Challenge locations leave the seed and the
      four arena warp pads stay closed. Purple CTR Tokens remain in the item
      pool and can be found anywhere, and the Purple Gem Cup still asks for
      them."""
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


class LegacyCortexVortexTrack(Toggle):
    """Add Cortex Vortex as a regular track: a Trophy Race, three Time Trials
    and a CTR Token Challenge.

    It takes the warp pad of one other destination, chosen per seed, and
    that destination's checks leave the seed. A boss race on that track
    still runs. Crossing the finish line needs Ultimate Sacred Fire.
    Cortex Vortex has no item boxes."""
    # Default off until a runtime pass proves an 8-kart race, relic mode and
    # the AI on this LEV (frozen contract, 2026-09-13).
    display_name = "Cortex Vortex Track"


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
    that position on track. Add "Held 5th" with Podium: Held 5th Rung.

    With Progressive Boost on, on easy and medium Logic Difficulty, logic
    expects "Held 1st" only once you have your first Progressive Boost, or one
    useful weapon when Itemsanity is on. On Cortex Castle and Hot Air Skyway it needs
    Ultimate Sacred Fire, and on Oxide Station too unless Shortcut Knowledge
    is hard. "Held 3rd" and "Held 5th" need nothing extra."""
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


class ContentPool(OptionDict):
    """Experimental independent content selection. Empty keeps the legacy generator.

    The development profile builds standalone track entries and Crystal
    Challenges. `tracks.modes` selects Trophy Race, CTR Challenge and Relic Race
    (default all three); each track gets the selected modes it can run, and
    `tracks.overrides` can narrow them per track. Custom tracks are complete
    package descriptors (track key, file pins, authored laps, measured capability
    flags): any track is accepted, and the game checks the files against the pins
    when it loads them. Trophy needs arcade, CTR needs arcade and ctr_tokens,
    Relic needs relic and time_trial. A track key with a named id block uses that
    block's checks; any other track uses a generic Custom Track slot under its
    own title. `tracks.cortex_vortex: true` adds Cortex Vortex as a track with
    all three modes, from the Cortex Vortex files bundled with the game.
    `bosses.enabled: true` puts the boss races back in the five garages: each
    boss on its home track, or on its Boss Track Shuffle track, and N. Oxide's
    two challenges, with Oxide Goal and Bosses Required Goal; false leaves the
    garages empty. `cups.count` sets how many cups the seed has. The first five
    are the original Gem Cups, Red first, and a sixth cup onward takes a name
    from the cup name pool. `cups.tracks` is off, random or random_no_repeats
    (the default): off races a Gem Cup's original four tracks, and a sixth cup
    onward draws four different tracks; random draws every race with repeats
    allowed; random_no_repeats draws four different tracks per cup. It wins over
    `cups.composition.repeats.within_cup`. Slide Coliseum and Turbo Track are
    never cup races. Unsupported selected content fails clearly.
    """
    display_name = "Content Pool (Experimental)"
    default = {}


class ContentPadLayout(OptionDict):
    """Physical pad placement and mode stages for content_pool.

    `stages`: two (default) or single. With two, a pad's first mode opens with
    the pad and its other modes share one second requirement, as
    two_stage_density sets; single is two_stage_density off. Later modes count
    once the pad's first race is won. `mode_order`: fixed (Trophy, CTR, Relic),
    per_seed (one random order for the seed) or per_pad. `placement`: shuffle
    (default, any content on any pad), shuffle_within_kind (tracks on track
    pads, cups on cup pads, arenas on arena pads) or vanilla (original content
    on its original pad). Content that does not fit takes any free pad.
    `merge_trophy_ctr` must stay false for now.
    """
    display_name = "Content Pad Layout (Experimental)"
    default = {}
