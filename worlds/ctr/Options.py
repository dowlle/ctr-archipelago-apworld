from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionError, OptionGroup, OptionDict, OptionList, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, StartInventoryPool)

from . import characters, legacy_yaml
from .content_playthrough import DEFAULT_REQUIREMENT_WEIGHTS
from .traps import (DEFAULT_TRAP_WEIGHTS, TRAP_WEIGHT_KEYS,
                    validate_trap_weights)
from .boss_track_shuffle import VENUES as BOSS_VENUE_TRACKS
from .boss_encounters import (OPPONENT_NAMES as BOSS_GARAGE_OPPONENTS, POOL_NAMES as BOSS_OPPONENT_NAMES,
                              GARAGE_FAMILIES as BOSS_ATTACK_FAMILIES, FAMILIES as OXIDE_ATTACK_FAMILIES)
from .arena_content import ARENAS, ARCADE

ARENA_NAMES = tuple(ARENAS.values())
ORIGINAL_ARENA_NAMES = tuple(name for level, name in ARENAS.items() if level not in ARCADE)


class OxideGoal(Choice):
    """Choose the N. Oxide part of your goal. Every goal you turn on must be
    completed.

    - **any_percent** (default): beat N. Oxide's first race.
    - **101_percent**: beat N. Oxide's Final Challenge.
    - **none**: N. Oxide is optional. Both of his races stay in the seed as
      checks.
    - **disabled**: N. Oxide's garage stays closed and both of his races leave
      the seed.

    With `none` or `disabled`, set Bosses Required Goal, Gems Required Goal or
    Wumpa Goal above 0."""
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
    """Choose whether N. Oxide's first race must come before his Final Challenge.
    Only used when Oxide Goal is `101_percent`.

    - **mandatory** (default): win the first race before the Final Challenge
      opens.
    - **optional**: the Final Challenge opens on its own requirements. The
      first race stays a check, and winning the Final Challenge also collects
      it.
    - **filler**: like optional, and the first race always holds Wumpa Fruit."""
    display_name = "Oxide 1 Optional"
    option_mandatory = 0
    option_optional = 1
    option_filler = 2
    alias_true_filler = 2
    alias_false = 0
    alias_true = 1
    default = 0


class BossesRequiredGoal(Range):
    """Choose how many of the four garage boss races you must win to finish, from
    0 to 4. The default, 0, turns this goal off.

    Only a won boss race counts, not Trophies or Keys. Every other goal you
    turn on must also be completed."""
    display_name = "Bosses Required Goal"
    range_start = 0
    range_end = 4
    default = 0


class GemsRequiredGoal(Range):
    """Choose how many of the five Gems you must hold to finish, from 0 to 5. The
    default, 0, turns this goal off. Every other goal you turn on must also be
    completed."""
    display_name = "Gems Required Goal"
    range_start = 0
    range_end = 5
    default = 0


class FinalOxideUnlock(Choice):
    """Choose which relics open N. Oxide's Final Challenge. Oxide's Final
    Challenge Relic Count sets how many.

    - **sapphire_relics** (default), **gold_relics**, **platinum_relics**:
      count only that colour.
    - **any_relic_type**: any one colour must reach the count.
    - **total_relics**: all three colours add up.

    A Platinum Relic does not count as a Gold one. The count can be at most the
    base relics of the chosen colours (Item Pool `base`); a higher count is
    lowered to that number. Extra copies still count toward opening it.
    Generation fails only when the chosen colours have no base relics, for
    example `platinum_relics` with no base Platinum Relics."""
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
    """Set how many relics open N. Oxide's Final Challenge, from 1 to 54. The
    default is 18.

    With `total_relics` up to 54 count. Every other choice counts one colour,
    so a value above 18 counts as 18. `all` means 18 in every mode."""
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
    """Choose N. Oxide's Final Challenge race. His first race does not change.

    - **cortex_vortex** (default): race N. Oxide on Cortex Vortex.
    - **oxide_station**: race N. Oxide on Oxide Station.
    - **vanilla_chaos**: on Oxide Station, all five of the seed's bosses race
      you and take turns attacking. You must finish first.
    - **vortex_chaos**: the same chaos race on Cortex Vortex.

    With Nitros Oxide in Boss Character Pool, another racer may take N. Oxide's
    place."""
    # The AP location backing this challenge is 35011105 for every choice --
    # an implementation detail, not something a player needs to know to pick
    # a venue (issue #355).
    display_name = "Oxide Final Challenge Track"
    option_cortex_vortex = 0
    option_oxide_station = 1
    option_vanilla_chaos = 2
    option_vortex_chaos = 3
    default = 0


def final_on_cortex(option) -> bool:
    """Is the Final Challenge raced on Cortex Vortex? (`oxide_final_track`)"""
    return int(option.value) in (OxideFinalTrack.option_cortex_vortex, OxideFinalTrack.option_vortex_chaos)


def final_chaos(option) -> bool:
    """Is the Final Challenge the chaos race? (`oxide_final_track`)"""
    return int(option.value) in (OxideFinalTrack.option_vanilla_chaos, OxideFinalTrack.option_vortex_chaos)


class BossTrackShuffle(Toggle):
    """Race each of the four garage bosses on a different random track. Off by
    default.

    Ripper Roo, Papu Papu, Komodo Joe and Pinstripe keep their garage, Key,
    entry requirement and attacks; only the track changes. N. Oxide is not
    affected. Boss Track Pool limits the tracks."""
    # #169 tier 1 (0.3.0). Wire: ctr_options.boss_track_shuffle plus the
    # boss_encounters block (schema 18). See boss_track_shuffle.py.
    display_name = "Boss Track Shuffle"


class BossOpponentShuffle(Toggle):
    """Race a different random racer in each of the four boss garages. Off by
    default.

    Each garage keeps its Key, entry requirement, check and boss driving. Boss
    Character Pool limits the racers. With Boss Track Shuffle also on, Boss
    Track Assignment chooses the track."""
    # #169 tier 2 (0.3.0). Wire: the plan's bosses record and boss race entries.
    # See content_bosses.py.
    display_name = "Boss Opponent Shuffle"


class BossTrackAssignment(Choice):
    """Choose the track when Boss Track Shuffle and Boss Opponent Shuffle are both
    on.

    - **character_home_track** (default): the drawn racer races on their home
      track, for example Coco on Coco Park.
    - **independent_track**: the track is drawn separately.

    Ignored unless both shuffles are on."""
    display_name = "Boss Track Assignment"
    option_character_home_track = 0
    option_independent_track = 1
    default = 0


class BossKitShuffle(Toggle):
    """Give each of the four garage bosses a new set of attacks. Off by default.

    Each boss fires a new set of weapons at set points of the lap. The garage,
    its Key and its check stay the same; the other boss shuffles may still
    change the racer or the track. N. Oxide keeps his own attacks."""
    # #169 tier 3 (0.3.0). Wire: the plan's bosses record and boss race entries.
    # See content_bosses.py.
    display_name = "Boss Kit Shuffle"


class BossAttackAssignment(Choice):
    """Choose how Boss Kit Shuffle builds a boss's attacks.

    - **mixed_loadouts** (default): each boss uses two to four weapon types.
    - **signature_profiles**: each boss gets one complete original boss attack
      pattern: Ripper Roo's TNT, Papu Papu's potions, Komodo Joe's thrown TNT
      or Pinstripe's bombs.

    Ignored when Boss Kit Shuffle is off."""
    display_name = "Boss Attack Assignment"
    option_mixed_loadouts = 0
    option_signature_profiles = 1
    default = 0


class BossAttackIntensity(Choice):
    """Choose how often bosses attack when Boss Kit Shuffle is on: **relaxed**,
    **standard** (default), **intense** or **mayhem**. This changes the time
    between attacks, never the weapons. Ignored when Boss Kit Shuffle is off."""
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
    """Give one racer in each Purple Gem Cup race boss attacks, built like the
    boss garage attacks. Off by default.

    The cup's tracks, racers and checks stay the same, but the podium places
    get harder. Needs Boss Kit Shuffle on and at least one Gem Cup in the seed;
    with it on, the Purple Gem Cup is the first Gem Cup the seed takes.
    Otherwise generation fails."""
    # Design answer 3 (2026-10-13) and decision 5 (2026-10-28). Wire: the plan's
    # bosses.gauntlet. See content_bosses.py.
    display_name = "Purple Gem Cup Boss Gauntlet"


class OxideAttackProfile(Choice):
    """Choose the attacks in N. Oxide's garage.

    - **retail** (default): N. Oxide's original attacks.
    - **all_compatible**: a new set drawn from every weapon a boss can use,
      including the Super Engine, which only N. Oxide's garage uses.

    The attacks belong to the garage, so they also apply when another racer
    takes N. Oxide's races."""
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
    """Make boost an item you find.

    - **off** (default): every kart boosts normally.
    - **shared_global**: one set of boost upgrades for every racer.
    - **per_character**: a set for each of the 16 racers, adding 32 to 48
      items. Generation fails if they do not fit.

    The upgrades give normal boost, then Ultimate Sacred Fire, then Blue Fire
    if Progressive Boost: Blue Fire is on. Some checks need these upgrades, and
    every CTR Challenge needs the first one."""
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
    """Add a Blue Fire upgrade after Ultimate Sacred Fire, so there is one more
    Progressive Boost to find. Off by default, and ignored while Progressive
    Boost is off.

    With the last upgrade, turbo pads give Blue Fire and one second of
    reserves. Powerslides can build those reserves without losing Blue Fire,
    U-turns keep them, and the exhaust turns blue."""
    display_name = "Progressive Boost: Blue Fire"


class LogicDifficulty(Choice):
    """Choose how much racing the game expects from you without boost. Only used
    when Progressive Boost is on.

    - **easy**: winning a Trophy Race, finishing on the podium and holding 1st
      need boost.
    - **medium** (default): winning a Trophy Race needs boost. Holding 1st
      needs your first Progressive Boost, or one useful weapon when Itemsanity
      is on.
    - **hard**: no general boost requirement.

    Here, boost means your first Progressive Boost, or three useful weapons
    when Itemsanity is on. The useful weapons are Mask, Missile, Bomb, Warpball
    and N. Tropy Clock.

    Platinum Time Trials need Ultimate Sacred Fire on easy and medium, and Blue
    Fire on easy when Blue Fire is on. Some tracks need Ultimate Sacred Fire on
    every setting: finishing Cortex Castle, Hot Air Skyway and Cortex Vortex,
    and holding 1st on Cortex Castle and Hot Air Skyway. Oxide Station needs it
    for both, unless Shortcut Knowledge is hard."""
    display_name = "Logic Difficulty"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 1


class ProgressiveStatsMode(Choice):
    """Make top speed, acceleration and turning items you find.

    - **off** (default): karts keep their normal stats.
    - **shared_global**: one set of stat upgrades for every racer.
    - **per_character**: a set for each of the 16 racers, adding 192 items.
      Needs a large seed.

    Stats start at their lowest rank and end above the original maximum."""
    display_name = "Progressive Stats"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


class TrapFillPercentage(Range):
    """Set the percentage of this slot's filler items that become traps, from 0 to
    100. The default is 10; 0 means no traps. Trap Weights decides which traps
    appear.

    Traps never block progress. A received trap arms silently and goes off
    later in a race."""
    # CTR's pool is almost entirely progression, so the filler pool this dial
    # replaces is small; traps substitute filler, never stack onto progression.
    display_name = "Trap Fill Percentage"
    range_start = 0
    range_end = 100
    default = 10


class TrapWeights(OptionDict):
    """Set how often each trap is picked when Trap Fill Percentage turns filler
    into a trap. A higher weight makes a trap more likely. Traps you leave out
    keep their default weight.

    `clocked_out` defaults to 3 and puts the clock effect on you for 7.7
    seconds. `reverse_camera` defaults to 2 and forces the rear view with
    normal steering, for as long as your local Trap Duration setting.

    Seven traps are new in 0.3.0-alpha3. Each lasts as long as your Trap
    Duration setting, except Stuck Steering (always 7 seconds) and Wumpa Leak
    (one event):
    - `always_jumping` (3): the kart hops whenever it touches the ground.
    - `no_drifting` (3): no hopping and no power sliding.
    - `rival_surge` (3): the AI racers move 50% faster. Races with AI only.
    - `mud_season` (3): every surface drives like dirt. Ignore Dirt blocks it.
    - `limp_mode` (3): your top speed is halved, boosts included.
    - `stuck_steering` (1): you cannot steer to one side, picked at random.
    - `wumpa_leak` (4): you lose half of your Wumpa Fruit, rounded down.

    `first_person`, `wireframe`, `upside_down`, `mirror_mode`, `demo_camera`
    and `reverse_camera` change the camera or the screen and can be visually
    intense. Set a trap to 0 to turn it off; `upside_down` is 0 by default.

    Setting every trap to 0 while Trap Fill Percentage is above 0 is an error."""
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
    """Make weapons items you must find. Off by default.

    Until you receive a weapon, an item box gives Wumpa Fruit instead of it.
    The first use of each weapon is a check, and using it while holding 10
    fruit is another. This changes how the whole game plays."""
    display_name = "Itemsanity"

class CupSweepChecks(Toggle):
    """Winning first place in all four races of a cup sends a separate check.

    The four wins must belong to one uninterrupted cup attempt. Points wins
    remain separate.
    """
    display_name = "Cup Sweep Checks"


class LapCompletionChecks(Toggle):
    """Completing the first lap of a race on a track sends one check for that track.

    Any race with laps counts, Cup legs and boss races included, and finishing
    position does not matter. Each track has one check, however often it appears
    in the seed. Crystal Challenges have no laps and give no lap check.
    """
    display_name = "Lap Completion Checks"


class Crystalsanity(Toggle):
    """Each authored crystal in an included Crystal Challenge is a check.

    Crystal numbers identify fixed positions, not pickup order. The arena's
    completion check remains separate.
    """
    display_name = "Crystalsanity"


class HitCharacter(Toggle):
    """Add a check for each of the 16 racers, collected the first time you hit
    them in an Adventure race. Off by default.

    The eight original Adventure racers can race you from the start. The others
    join once you win the race that unlocks them, and a boss can also be hit in
    their own boss race. If that race is not in your seed, they join another
    way; the spoiler log lists the racers that need Keys."""
    display_name = "Hit Character Checks"


class RelicPerfectChecks(Toggle):
    """Add a check to each Relic Race for breaking every time crate in it.

    You get the check even when your time does not earn a relic, and it
    never changes which relic you get."""
    display_name = "Relic Race Perfect Checks"


class Lettersanity(Choice):
    """Choose whether the C, T and R letters are checks, items, or both. Every
    track with a CTR Challenge has the three letters.

    - **off** (default): letters work as in the original game.
    - **locations_only**: picking up a letter is a check.
    - **locations_and_items**: picking up a letter is a check, and each letter
      is also an item. You must receive a letter from the multiworld before you
      can pick it up.
    - **items_only**: letters are items, not checks. You must receive a letter
      from the multiworld before you can pick it up."""
    display_name = "Lettersanity"
    option_off = 0
    option_locations_only = 1
    option_locations_and_items = 2
    option_items_only = 3
    default = 0

class LettersPerTrack(Range):
    """Choose how many of each track's three letters are used, from 1 to 3. The
    default is 3. Below 3, the seed picks the letters at random.

    Only used with `locations_only` and `locations_and_items`. `items_only`
    always uses all three letters of every track."""
    display_name = "Letters Per Track"
    range_start = 1
    range_end = 3
    default = 3


class TiziHelper(Toggle):
    """Add the Tizi Helper item. Once you receive it, the first row of item boxes
    on Papu's Pyramid always gives a Mask. Off by default.

    This makes a difficult shortcut on that track easier to try. The game never
    expects you to use it. With Itemsanity on, you also need the Mask unlocked."""
    display_name = "Papu's Pyramid Mask Helper"


class ReserveTopUp(DefaultOnToggle):
    """Add Reserve Top-Up to the filler items that are not traps. On by default.
    It is drawn at weight 1, beside Wumpa Fruit at 6; Wumpa bundles keep their
    weights of 3 and 1.

    Each one adds reserves equal to about a quarter of the maximum, during a
    race while you are boosting. It waits until then, keeps your current fire
    limit, and can take you into purple fire, also with Progressive Boost. It
    gives no weapon."""
    display_name = "Reserve Top-Up"


class WumpaBundles(Toggle):
    """Let filler include bundles of Wumpa Fruit. On by default.

    Small bundles give 3 fruit and big bundles fill your kart to 10. A single
    fruit stays the most common filler. Bundles use existing filler slots and
    add no items or checks. Turn this off to keep every Wumpa filler item a
    single fruit."""
    display_name = "Wumpa Bundles"
    default = 1


class ProgressiveStartingWumpa(Range):
    """Add 0 to 10 Progressive Starting Wumpa items. Each one raises the fruit you
    start every race with by one. The default, 0, starts you with no fruit; 10
    starts every race with a full kart. These items take filler slots and add
    no checks."""
    display_name = "Progressive Starting Wumpa"
    range_start = 0
    range_end = 10
    default = 0


class WumpaCheck(Choice):
    """Add checks for reaching 10 Wumpa Fruit in a race.

    - **off** (default): no Wumpa checks.
    - **global**: one check, the first time you reach 10 fruit in any race.
    - **per_track**: one check for each track you race on in this seed, instead
      of the global one.

    These are separate from the Itemsanity checks for using a weapon while
    holding 10 fruit."""
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
    """Choose how many Wumpa Shop slots each of the five hubs has, from 0 to 25.
    Each slot is a check with a price. The default is 10 per hub, 50 checks in
    total; 0 turns the shop off.

    In Adventure races, fruit you collect while already holding 10, and the
    fruit you hold when you finish a race, go into your bank. Spend it at a
    hub's save screen while connected to the server. Later slots go on sale as
    your total banked fruit grows. Any slot can hold any item unless Wumpa Shop
    Progression is `excluded`."""
    display_name = "Wumpa Shop Slots"
    range_start = 0
    range_end = 25
    default = 10


class WumpaShopPrices(Range):
    """Scale every Wumpa Shop price and every slot unlock amount, from 25 to 400
    percent. The default, 100, gives prices from 10 to 30 fruit in N. Sanity
    Beach up to 40 to 80 in Citadel City. A slot's price does not depend on its
    item."""
    display_name = "Wumpa Shop Prices"
    range_start = 25
    range_end = 400
    default = 100


class WumpaShopLogicScale(Range):
    """Scale how much shop spending the game expects from you at each Key count,
    from 25 to 400 percent.

    At the default, 100, a slot costing up to 100 fruit is expected with 0
    Keys, up to 300 with 1 Key, 600 with 2, 900 with 3, and more than 900 with
    all 4. A slot counts its price or its unlock amount, whichever is higher. A
    higher percentage expects more spending earlier; a lower one moves
    expensive slots later. You still need the Keys to reach a shop's hub.

    This only changes where items are placed and what the tracker expects.
    Prices stay the same, and you can always farm and buy early."""
    display_name = "Wumpa Shop Logic Scale"
    range_start = 25
    range_end = 400
    default = 100


class WumpaShopProgression(Choice):
    """Whether Wumpa Shop slots may hold progression items.

    - **allowed** (default): any shop slot may hold progression, priced like
      any other slot.
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


class ShopHintsProgressionOnly(Toggle):
    """Wumpa Shop Hints only hint progression items.

    Off (default): opening a shop page hints every unsold item on it.

    On: opening a shop page hints only the unsold slots that hold a progression
    item. Useful items, filler and traps are not hinted. Without Wumpa Shop
    Hints this option does nothing."""
    display_name = "Shop Hints Progression Only"


class GoalWumpa(Range):
    """Set how much Wumpa Fruit you must bank over the whole seed to finish, from
    0 to 5000. The default, 0, turns this goal off.

    In Adventure races, fruit you collect while already holding 10, and the
    fruit you hold when you finish a race, go into the bank. Spending in the
    Wumpa Shop never lowers this total. 1000 is a long goal of many races.
    Every other goal you turn on must also be completed."""
    display_name = "Wumpa Goal"
    range_start = 0
    range_end = 5000
    default = 0


class TurboGrant(Toggle):
    """Add one item that puts a Turbo in your weapon slot at the start of every
    race, once you have it. Off by default.

    A restart counts as a new race. If your weapon slot is full, the Turbo
    waits until it is free. With Itemsanity on, it also waits until you have
    unlocked Turbo. Progressive Boost still sets how strong the Turbo is. The
    item takes a filler slot and adds no check."""
    display_name = "Turbo Grant"


class BoxLocations(Toggle):
    """Place Archipelago item boxes on the tracks and make each one a check. Off
    by default.

    These are extra boxes added for Archipelago, not the normal item boxes that
    give you weapons. Breaking one gives no weapon or fruit. About 240 stand on
    the 18 original race tracks, and a custom track gets up to 15. Break one in
    an Adventure race on its track to collect it.

    This makes a much longer seed. Some boxes sit behind jumps or shortcuts, so
    Shortcut Knowledge decides which ones are in the seed."""
    display_name = "Item Box Locations"


class ShortcutKnowledge(Choice):
    """Choose which shortcuts the game expects you to take.

    - **easy** (default): only shortcuts anyone can take.
    - **medium**: the well-known ones as well.
    - **hard**: every shortcut, including routes that need Ultimate Sacred
      Fire.

    Higher settings put the checks behind those shortcuts in reach sooner. With
    Item Box Locations on, a box behind a shortcut above your setting is left
    out of the seed."""
    display_name = "Shortcut Knowledge"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 0


class OneLapCups(DefaultOnToggle):
    """Shorten cup races. On by default.

    Each cup race, Gem Cups included, uses half its track's laps, rounded down
    and at least one: an original track races one lap instead of three. Boss
    cup races run three laps on any track, so they run one. Single races, boss
    races, Relic Races and CTR Challenges keep their full laps. The checks do
    not change."""
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
    """Colour each Archipelago item box by the kind of item inside. Only used when
    Item Box Locations is on.

    On (default): a box shows the colour of its item before you break it:

    - purple: progression
    - blue: useful
    - cyan: filler
    - salmon: trap

    Off: every box is pink, so the colour gives nothing away. Use this for
    races and tournaments.

    Players can also turn the colours off in the game under Options,
    Archipelago, Item Box Colours. When this option is off, that row shows
    OFF (SEED)."""
    display_name = "Item Box Colours"


class SpoilerItems(Toggle):
    """Hide reward previews until you find the items that show them. Off by
    default.

    With this on, the rewards above a warp pad stay hidden until you receive
    Warp Pad Preview. Until then, a pad with open checks shows one plain
    Archipelago marker, and a finished pad shows nothing. With Item Box
    Locations and Item Box Colours on, item boxes also stay pink until you
    receive AP Box Colours. Both items take filler slots and add no checks.
    Pads still open and count their checks as usual."""
    display_name = "Spoiler Items"


class PadApproachHints(Toggle):
    """Hint a warp pad's open checks when you drive up to it. Off by default.

    With this on, when a pad shows its name as you approach, the game hints
    every check behind it that is open for you and not yet collected. A closed
    pad, or one that needs a racer you do not have, hints nothing. Each check
    is hinted at most once, also after a reconnect.

    Hints cannot be undone. Everyone in the room sees them, and one drive
    through a hub can hint many checks."""
    display_name = "Pad Approach Hints"


class PadHintsWaitForSpoiler(DefaultOnToggle):
    """Pad Approach Hints wait for Warp Pad Preview. On by default.

    Off: Pad Approach Hints work as before.

    On: with Spoiler Items and Pad Approach Hints both on, a pad hints nothing
    until you receive Warp Pad Preview, the item that also reveals the pad's
    items. The hints you skipped are not lost: the next time you drive up to
    the pad after the preview arrives, it hints them. Without Spoiler Items or
    Pad Approach Hints this option does nothing."""
    display_name = "Pad Hints Wait for Spoiler"


class PadHintsProgressionOnly(DefaultOnToggle):
    """Pad Approach Hints only hint progression items. On by default.

    Off: a pad hints every open check behind it.

    On: a pad hints only the checks that hold a progression item, which keeps
    the hint list short. Checks with useful items, filler and traps are not
    hinted, and a later approach does not hint them either. Without Pad
    Approach Hints this option does nothing."""
    display_name = "Pad Hints Progression Only"


class TrapDisplay(Choice):
    """Choose how a location holding a trap looks in CTR before you collect
    it: on item boxes, on warp pad glow and in the Wumpa Shop.

    - **shown** (default): traps look like traps.
    - **as_progression**: traps look like progression items.
    - **mixed**: each trap location looks like progression or like filler,
      picked once per location when the seed is generated.

    Received traps still say their name in the feed. Other games and the
    Archipelago server still show the item as a trap. It never changes the
    logic."""
    display_name = "Trap Display"
    option_shown = 0
    option_as_progression = 1
    option_mixed = 2
    default = 0


class RaceTypeSelector(Choice):
    """Choose when a warp pad shows the race type menu.

    - **always** (default): every race pad you can enter shows the menu, with
      the races open on that pad, in the pad's order.
    - **productive**: the menu shows only when more than one race type still
      has a check, or none has. With exactly one, the pad starts that race.

    Race types with nothing left to check are grey, but you can still pick
    them. This is the starting value; you can change it at any time in the
    client's Options menu. It never changes the logic."""
    display_name = "Race Type Selector"
    option_productive = 0
    option_always = 1
    default = 1


class TrackerPadLaunch(DefaultOnToggle):
    """Start what a warp pad or boss garage offers from the in-game tracker. On by
    default.

    In a hub, pause, open the tracker, pick a pad or garage and press Cross.
    What you can start now is listed first; the rest is grey and shows what you
    still need. Starting one takes you to the pad's hub and enters it as if you
    had driven onto it, with the same requirements.

    Turn this off to use the tracker for information only. A race or sync host
    can turn it off for everyone. It never changes the logic."""
    display_name = "Tracker Pad Launch"


class AdventureStructure(Choice):
    """Choose whether a track's Trophy Race and CTR Challenge stay two separate
    races or are merged into one.

    - **classic** (default): two races, as in the original game. Win the Trophy
      Race first; the CTR Challenge and the Relic Race open after it.
    - **trophy_ctr_combined**: merges the Trophy Race and the CTR Challenge into
      one race, played as the CTR Challenge. Finishing first earns the track's
      Trophy Race check. Finishing first with all three letters also earns its
      CTR Token check. Item boxes, Wumpa and placement checks come from this one
      race, and placement counts even without the letters. The Relic Race opens
      after it, like any later race on the pad. `ctr_first` is the old name and
      still works.

    The checks keep their names, so "Trophy Race" is still the track's first
    check. A track without a CTR Challenge uses classic."""
    display_name = "Adventure Structure"
    option_classic = 0
    option_trophy_ctr_combined = 1
    alias_ctr_first = 1
    default = 0


class WarpPadUnlockRequirements(Choice):
    """Choose how warp pads and boss garages open.

    - **randomized** (default): each pad gets a random requirement, such as
      Trophies, CTR Tokens, Relics, Keys or Gems, that you can always collect
      before the pad opens.
    - **vanilla**: the original game's requirements, such as 4, 8, 12 and 16
      Trophies for the boss garages.
    - **random_without_4_keys**: like randomized, but no pad asks for all 4
      Keys. Pads can still ask for 1 to 3 Keys.

    To keep Keys off pads entirely, set `Key: 0` in Requirement Weights. With
    random requirements, Garage Requirement Level sets the size of the boss
    garage requirements."""
    # "Always collectable" is enforced by the solvability-proven sphere search
    # at generation time.
    display_name = "Warp Pad Unlock Requirements"
    option_vanilla = 0
    option_randomized = 1
    option_random_without_4_keys = 2
    default = 1


class TwoStageDensity(Choice):
    """Choose how many warp pads have a second requirement. The first requirement
    opens the pad's first race. The second opens its later races and their
    checks; in the default order those are the CTR Challenge with its letters
    and the Relic Race with its time trials. This spreads a track's checks
    across the seed.

    - **off**: every pad opens fully at its first requirement.
    - **light**, **standard**, **deep**, **full** (default): more pads get a
      second requirement at each step."""
    # Higher density puts more ordering pressure on AP's fill. Solo generation
    # is protected by the terminal rollback backstop. At non-standard densities
    # an internal diversity discount nudges repeat requirement families (mostly
    # Trophies) toward variety, so extra gates do not all come out
    # Trophy-shaped. full = no random collapse.
    display_name = "Pads With Two Requirements"
    option_off = 0
    option_light = 1
    option_standard = 2
    option_deep = 3
    option_full = 4
    default = 4


class RequirementWeights(OptionDict):
    """Set how often each item is picked for a random warp pad or boss garage
    requirement. Ignored with vanilla requirements.

    Each entry is `item name: weight`. A higher weight is picked more often and
    0 means never; Trophy must stay above 0. Items you leave out keep the
    weight shown here. Valid names: Trophy, Key, the five CTR Token colours,
    the three Relic colours and the five Gem colours."""
    # Trophy must stay above 0 because it bootstraps the randomized warp-pad
    # requirements. Unlisted items fall back to their icebound_beta5 weight.
    display_name = "Requirement Weights"
    supports_weighting = False
    # Pre-filled with the icebound_beta5 table (single source: content_playthrough)
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
    """Set the first requirement of chosen warp pads yourself. Leave it empty
    (default) for none.

    Example:
    ```yaml
    warp_pad_rules:
      Crash Cove: {item: free, count: 0}
      Red Cup: {item: Red CTR Token, count: 3}
      Skull Rock: {item: AnyRelic, count: 2}
    ```

    Use the pad's own name without "Warp Pad". Content shuffled onto a pad uses
    that pad's requirement, and hub doors still need their Keys. `item` is
    `free` with `count: 0`, or Trophy, Key, a CTR Token colour such as Red CTR
    Token, a Relic colour such as Gold Relic, or a Gem colour such as Red Gem.
    AnyCtrToken, AnyRelic and AnyGem count every colour together. Every item
    except `free` needs a whole `count` from 1 up to how many the seed has.
    Wumpa Fruit and racers are not allowed.

    Pads you leave out keep random requirements, and a pad can still get a
    second requirement. Your rules ignore Requirement Weights.
    `random_without_4_keys` refuses a rule of 4 Keys, and vanilla requirements
    refuse every rule. A pad you name always gets content."""
    display_name = "Warp Pad Rules"
    default = {}


class DeathLink(Choice):
    """Choose what a DeathLink from another player does to you. DeathLinks are
    only sent and received during Adventure races, and a received one is never
    saved for a later race.

    - **off** (default): nothing is sent or received.
    - **mask_reset**: you are reset as if you fell off the track.
    - **weapon_hit**: you spin out as if a weapon hit you. A shield, an Aku Aku
      mask or the short protection after a hit blocks it.
    - **race_loss**: your race ends at once as a last-place loss, and nothing
      that race would pay out is awarded. In a Gem Cup the cup carries on, and
      if you still win it on points, the cup reward is paid.

    DeathLink Send chooses what makes you send one. At its default, mask_reset
    and weapon_hit send when you fall off or are eaten, and race_loss also
    sends when you lose a race. If you list a send trigger while this is off,
    this becomes mask_reset, because a slot that sends also receives."""
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
    """Choose what makes you send a DeathLink.

    - **mask_grab**: falling off the track or being eaten.
    - **weapon_hit**: getting hit by a weapon.
    - **race_loss**: losing a race or a whole Gem Cup, or restarting or leaving
      a race from the pause menu. This only counts while that race's win is in
      logic for you and not collected yet.

    The default, `[follow_death_link]`, sends what DeathLink implies. A list
    you write replaces it, so include every trigger you want. Use `[]` to
    receive DeathLinks without sending any. A death caused by a received
    DeathLink is never sent back. Listing any trigger while DeathLink is off
    turns DeathLink on as mask_reset."""
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
    """Set how many of your deaths count as one sent DeathLink, from 1 to 30. The
    default, 1, sends every death; 3 sends one for every three. Useful with
    weapon hits, which happen often. Incoming DeathLinks are not affected."""
    # Does nothing useful when only mask grabs and race losses send (both are
    # rare) and is inert while DeathLink is off.
    display_name = "DeathLink Amnesty"
    range_start = 1
    range_end = 30
    default = 1


class StartingCharacter(Choice):
    """Choose your starting racer.

    - **random_starter** (default): one of the eight original Adventure racers.
    - **random_any**: any of the 16 racers.
    - A racer's name: start as that racer.

    With Character Unlocks on, the other 15 racers are items. With it off,
    every racer is available in the hub from the start."""
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
    """Choose your starting racer's kart stats.

    - **vanilla** (default): that racer's usual stats.
    - **balanced**, **acceleration**, **speed**, **turning**: that stat class
      instead.

    Only your starting racer changes. Progressive Stats overrides this, and the
    logic never needs a particular value."""
    display_name = "Starting Stat Class"
    option_vanilla = 0
    option_balanced = 1
    option_acceleration = 2
    option_speed = 3
    option_turning = 4
    default = 0


class CharacterUnlocks(DefaultOnToggle):
    """Start with one racer and find the other 15 as items. On by default. The
    character select only offers the racers you have. Turn this off to have
    every racer from the start."""
    display_name = "Character Unlocks"


class RemovePlayableOxide(Toggle):
    """Remove Nitros Oxide from the racers you can unlock. Off by default.

    His unlock item is not created, so the pool gets one more filler or trap.
    `random_any` never starts you as him, and no warp pad is locked to him. He
    still races you as a boss, and his Hit Character check stays. Needs
    Character Unlocks on, and cannot be used with Starting Character set to
    Nitros Oxide."""
    display_name = "Remove Playable Oxide"


class RacerLockedPads(Range):
    """Set the most warp pads that can require a specific racer, from 0 to 27. The
    default, 0, turns this off.

    To enter a locked pad you need that racer unlocked, and the game seats you
    as them. Your starting racer is never required. A seed with few random pads
    may get fewer locks. Needs Character Unlocks on."""
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
    """Choose which version of Penta Penguin's stats to use. Penta is the one
    racer whose stats differ by region.

    - **ntsc** (default): the unfinished NTSC-U stats, which reuse Polar and
      Pura's turning stats.
    - **pal**: the PAL stats, with top values in every category. This makes
      Penta the strongest racer.

    Progressive Stats or Editable Stats overrides this."""
    display_name = "Penta Penguin Stats"
    # The labels were inverted until 2026-08-21. The NUMBERS are the ones the
    # client has always read (0 the ordinary TURN-class table, 1 the MAX
    # table), so nothing moved on the wire; only the names above them did.
    option_ntsc = 0
    option_pal = 1
    default = 0


class EditableStats(Choice):
    """Choose whether you can set kart stats yourself in the hub stat panel.

    - **off** (default): the panel only shows your stats.
    - **global**: one setup for every racer.
    - **per_character**: a separate setup for each of the 16 racers.

    Each stat takes one of five ranks, from VERY LOW to VERY HIGH, the same
    ranks Progressive Stats uses. With Progressive Stats on, the panel is
    read-only."""
    display_name = "Editable Stats"
    option_off = 0
    option_global = 1
    option_per_character = 2
    default = 0


class ContentItemPool(OptionDict):
    """Set how many Trophies, Relics, CTR Tokens and Gems the seed has. Leave it
    empty (default) for 16 Trophies, 4 Keys, 18 Sapphire Relics, 18 Gold
    Relics, no Platinum Relics, 4 CTR Tokens of each colour and 5 Gems. `base`
    always has 4 Keys.

    `base` sets the counts that requirements may ask for. `extra` adds copies
    in place of filler. A Relic colour gets Time Trial checks on as many Relic
    Races as it has items, base and extra together, up to the Relic Races in
    the seed, drawn at random; relic items beyond that land on other checks.
    The five terrain items (Ignore Grass, Ignore Dirt, Ignore Snow, Ignore
    Water and Ignore Ice) are dropped together when the items do not fit. Any
    other shortage stops generation.

    Example, fewer relics:
    ```yaml
    item_pool:
      base:
        relics: {sapphire: 12, gold: 6, platinum: 0}
    ```

    `extra` takes exact counts, not percentages. Extra Trophies and Keys are
    the same items as the base ones, so requirements are easier to meet. Pads
    and garages only ask for the base count.

    Example, 4 extra Trophies and 2 extra Keys:
    ```yaml
    item_pool:
      extra:
        trophies: 4
        keys: 2
    ```"""
    display_name = "Item Pool"
    default = {}


class RetailTracks(OptionSet):
    """Choose which of the 18 original race tracks can appear on warp pads, in
    cups or in shuffled boss races.

    **all** (default) includes all 16 Trophy tracks plus Slide Coliseum and
    Turbo Track. To limit the choice, list track names instead."""
    display_name = "Original Tracks"
    valid_keys = ["all"] + sorted(BOSS_VENUE_TRACKS)
    default = frozenset({"all"})

    @classmethod
    def from_any(cls, data: Any) -> "RetailTracks":
        # First option rolled: refuse a whole 0.2.x YAML here, once, naming
        # every old option (legacy_yaml.py).
        legacy_yaml.check_caller()
        return super().from_any(data)


class TrackModes(OptionDict):
    """Choose which races each track offers: `trophy`, `ctr` and `relic`. The
    default gives all three to every track, Slide Coliseum and Turbo Track
    included.

    A track name overrides `default` for that track. A custom track goes by its
    track key or its title. Every track needs at least one race, and `ctr` also
    needs `trophy`. A track never gets a race it cannot run.

    Example:
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
    """List the custom tracks this seed may use on warp pads, in cups and in boss
    races. Leave it empty (default) to use none.

    Copy each track's complete entry from its download or the AP-Pie track
    picker. Play Solo can also write the entries into a YAML for you. Keep each
    entry unchanged: the game checks the installed files against it.

    A custom track takes the place of an original track on a warp pad. If there
    are more tracks than pads, some are left out; list a track key in
    Guaranteed Warp Pads to make sure it gets one. You can list up to 132
    tracks. A registered track keeps its own check names, for example "Baby T
    Park: Trophy Race". Any other track uses its title, and a title that
    matches an original track gets "(Custom)" added."""
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
    """Choose whether Cortex Vortex can appear as a track. It has a Trophy Race,
    CTR Challenge and Relic Race, no item boxes, and you need Ultimate Sacred
    Fire to cross its finish line.

    - **off** (default): no warp pad or cup race. N. Oxide's Final Challenge
      can still race there.
    - **in_pool**: it may get a warp pad or a cup race, or neither.
    - **own_pad**: it always gets a warp pad."""
    # alias_false: a YAML `off` reaches us as false. `true` has no alias: the old
    # true meant a dropped destination, which is gone.
    display_name = "Cortex Vortex Track"
    option_off = 0
    option_in_pool = 1
    option_own_pad = 2
    alias_false = 0
    default = 0


class RequiredEntries(OptionList):
    """List original tracks, arenas or custom track keys that must get a warp pad.
    Leave it empty (default) for no guarantees. To guarantee Cortex Vortex, set
    Cortex Vortex Track to `own_pad` instead."""
    display_name = "Guaranteed Warp Pads"
    default = []


class CupCount(Range):
    """Choose how many cups the seed has, from 0 to 27. The default, 5, is the
    original Gem Cups, starting with Red, each with its Gem check. A sixth cup
    and later take other cup names. 0 means no cups."""
    display_name = "Cup Count"
    range_start = 0
    range_end = 27
    default = 5


class CupTracks(Choice):
    """Choose the tracks in each cup. Slide Coliseum and Turbo Track can appear
    in cups too.

    - **off**: an original Gem Cup keeps its four original tracks. A sixth cup
      and later draw four different tracks.
    - **random_repeats**: each race is drawn on its own, so a track can repeat.
      `random` means the same.
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
    """Set the most races in each cup that may be a custom track or Cortex Vortex,
    from 0 to 4. The default is 4."""
    display_name = "Custom Races Per Cup"
    range_start = 0
    range_end = 4
    default = 4


class CrystalChallengeCount(Range):
    """Choose how many Crystal Challenges the seed has, from 0 to 7, drawn from
    Crystal Arenas. The default is 4. 0 removes the arena checks; Purple CTR
    Tokens stay in the item pool and can still be found elsewhere."""
    display_name = "Crystal Challenge Count"
    range_start = 0
    range_end = 7
    default = 4


class CrystalArenas(OptionSet):
    """Choose which arenas a Crystal Challenge can use. The default is all
    seven: Rocky Road, Rampage Ruins, Skull Rock, Nitro Court, Parking Lot,
    The North Bowl and Lab Basement. Crystal Challenge Count sets how many of
    them the seed uses.

    Parking Lot, The North Bowl and Lab Basement are the new arenas. Each of
    those uses a warp pad, has 20 crystals and gives no Purple CTR Token. To
    keep only the four original arenas, list Rocky Road, Rampage Ruins, Skull
    Rock and Nitro Court. Crystal Challenge Count cannot be higher than the
    number of arenas listed."""
    display_name = "Crystal Arenas"
    valid_keys = sorted(ARENA_NAMES)
    default = frozenset(ARENA_NAMES)


class BossGarages(DefaultOnToggle):
    """Put boss races in the four boss garages and N. Oxide's garage. On by
    default.

    Off leaves the garages empty. That needs Oxide Goal set to `disabled`,
    Bosses Required Goal at 0, and Gems Required Goal or Wumpa Goal above 0."""
    display_name = "Boss Garages"


class BossCups(Range):
    """Choose how many of the four boss garages hold a four-race boss cup instead
    of one race, from 0 to 4. The default is 0. The same boss and weapons race
    all four races of a boss cup."""
    display_name = "Boss Cups"
    range_start = 0
    range_end = 4
    default = 0


class GarageRequirementLevel(Choice):
    """Choose how large the four boss garage requirements are when warp pad
    requirements are random. Each garage draws an item and a count.

    - **standard**: small.
    - **high** (default): medium, growing from garage to garage.
    - **very_high**: large.
    - **chaotic**: any size, on any garage.

    With vanilla requirements the garages need 4, 8, 12 and 16 Trophies. N.
    Oxide's garage always needs 4 Keys."""
    display_name = "Garage Requirement Level"
    option_standard = 0
    option_high = 1
    option_very_high = 2
    option_chaotic = 3
    default = 1


class BossTrackPool(OptionSet):
    """Limit the tracks Boss Track Shuffle can use. Leave it empty (default) to
    allow every eligible track. Ignored when Boss Track Shuffle is off.

    List original track names, Cortex Vortex, or custom tracks by track key or
    title. Cortex Vortex and a custom track only count when they are in the
    seed. A boss race needs one track of its own, and a boss cup needs four
    different tracks, so list enough of them.

    Example, the four garage bosses race on four of these five tracks:
    ```yaml
    boss_track_pool: [Crash Cove, Tiger Temple, Blizzard Bluff, N. Gin Labs, Cortex Castle]
    ```"""
    # No valid_keys: a custom track's name is only known from its package.
    display_name = "Boss Track Pool"
    default = frozenset()


class BossCharacterPool(OptionSet):
    """Choose the racers Boss Opponent Shuffle can draw. The default is every
    racer except Nitros Oxide. Ignored when Boss Opponent Shuffle is off.

    Add Nitros Oxide to let him be a garage boss. Another racer from this list
    then takes both of N. Oxide's own races."""
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
    """Choose the weapons N. Oxide's garage can draw when N. Oxide Attack Profile
    is `all_compatible`. This list includes the Super Engine and is separate
    from Boss Weapon Pool. Ignored with `retail`."""
    display_name = "N. Oxide Weapon Pool"
    valid_keys = sorted(OXIDE_ATTACK_FAMILIES)
    default = frozenset(OXIDE_ATTACK_FAMILIES)


class PadPlacement(Choice):
    """Choose what goes on the 27 warp pads. Each pad keeps its own requirement,
    whatever lands on it.

    - **vanilla**: original content stays on its original pad where it can;
      other content uses the free pads.
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
    """Choose the order in which a track's races open on its pad.

    - **fixed** (default): Trophy Race, CTR Challenge, then Relic Race.
    - **per_seed**: one random order, used by every pad.
    - **per_pad**: a random order on each pad.

    A pad with more than one race never starts with a race that has no check of
    its own: with letter items on, the CTR Challenge moves later, and so does a
    Relic Race without time trial checks."""
    display_name = "Race Mode Order"
    option_fixed = 0
    option_per_seed = 1
    option_per_pad = 2
    default = 0


class PodiumRungs(OptionSet):
    """Choose the placement checks on each track with a Trophy Race. An empty list
    means none.

    - **held_1st**, **held_3rd**, **held_5th**: hold that place in a race for
      half a second.
    - **finish_on_podium**: finish in the top 3.
    - **finish_any**: finish in any place.

    A better place also pays the checks below it. The default is every check
    except held_5th.

    With Progressive Boost on, Logic Difficulty decides when held_1st needs
    boost. On Cortex Castle and Hot Air Skyway held_1st needs Ultimate Sacred
    Fire, and on Oxide Station too unless Shortcut Knowledge is hard."""
    display_name = "Podium Rungs"
    valid_keys = ["held_1st", "held_3rd", "held_5th", "finish_on_podium", "finish_any"]
    default = frozenset({"held_1st", "held_3rd", "finish_on_podium", "finish_any"})


class CupOnlyPodiumRungs(Toggle):
    """Give Podium Rungs checks to a track that appears in cups but has no Trophy
    Race. Off by default.

    That is a track without its own pad, or one whose pad has no Trophy Race.
    Its checks are earned in cup races, never in boss races or boss cups. Does
    nothing when Podium Rungs is empty."""
    display_name = "Cup-Only Podium Rungs"


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
    cup_only_podium_rungs: CupOnlyPodiumRungs
    relic_perfect_checks: RelicPerfectChecks
    lettersanity: Lettersanity
    letters_per_track: LettersPerTrack
    cup_sweep_checks: CupSweepChecks
    lap_completion_checks: LapCompletionChecks
    box_locations: BoxLocations
    itemsanity: Itemsanity
    crystalsanity: Crystalsanity
    wumpa_check: WumpaCheck
    hit_character: HitCharacter
    wumpa_shop_slots: WumpaShopSlots
    wumpa_shop_prices: WumpaShopPrices
    wumpa_shop_logic_scale: WumpaShopLogicScale
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
    pad_approach_hints: PadApproachHints
    pad_hints_wait_for_spoiler: PadHintsWaitForSpoiler
    pad_hints_progression_only: PadHintsProgressionOnly
    trap_display: TrapDisplay
    shop_hints_progression_only: ShopHintsProgressionOnly
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
    "Checks": [PodiumRungs, CupOnlyPodiumRungs, RelicPerfectChecks, Lettersanity, LettersPerTrack, CupSweepChecks,
               LapCompletionChecks, BoxLocations, Itemsanity, Crystalsanity, WumpaCheck, HitCharacter],
    "Wumpa Shop": [WumpaShopSlots, WumpaShopPrices, WumpaShopLogicScale, WumpaShopProgression, WumpaShopHints,
                    ShopHintsProgressionOnly],
    "Items and Traps": [ContentItemPool, TrapFillPercentage, TrapWeights, WumpaBundles, ReserveTopUp,
                        ProgressiveStartingWumpa, TurboGrant, TiziHelper,
                        TrapDisplay],
    "Characters and Stats": [StartingCharacter, CharacterUnlocks, RemovePlayableOxide, StartingStatClass, PentaStats,
                             EditableStats, ProgressiveStatsMode],
    "Boost": [ProgressiveBoostMode, ProgressiveBoostBlueFire, LogicDifficulty, ShortcutKnowledge],
    "DeathLink": [DeathLink, DeathLinkSend, DeathLinkAmnesty],
    "Display": [WarpPadItemDisplay, ApItemTypeColors, ColorBoxesByItem, SpoilerItems, PadApproachHints,
                PadHintsWaitForSpoiler, PadHintsProgressionOnly,
                RaceTypeSelector,
                TrackerPadLaunch],
}


def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]
