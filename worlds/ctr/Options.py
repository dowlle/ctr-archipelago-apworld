from typing import List, Dict, Any
from dataclasses import dataclass
from Options import (Choice, OptionGroup, OptionDict, OptionSet, DefaultOnToggle,
                     Toggle, NamedRange, Range, PerGameCommonOptions, Visibility)


class OxideGoal(Choice):
    """Which of N. Oxide's Challenges must be beaten for the goal to be met.

    - **none**: no Oxide requirement. Combine with `Bosses Required Goal`
      and/or `Gems Required Goal` instead.
    - **first** (default): defeat N. Oxide's Challenge.
    - **final**: collect relics, then defeat N. Oxide's Final Challenge.

    Issue #152: composes with `Bosses Required Goal` and `Gems Required
    Goal` as an AND of every condition set active (non-'none'/non-zero). At
    least one of the three must be active; a YAML that sets all three to
    their off value fails generation with a clear message."""
    display_name = "Oxide Goal"
    option_none = 0
    option_first = 1
    option_final = 2
    default = 1


class BossesRequiredGoal(Range):
    """How many of the 4 boss races (Ripper Roo, Papu Papu, Komodo Joe,
    Pinstripe) must be personally won for the goal to be met. 0 (default)
    means this condition is off.

    Issue #152: composes with `Oxide Goal` and `Gems Required Goal` as an AND
    of every active condition. "Personally won" means the boss-race location
    itself was checked, not merely holding N trophies or N boss-garage Keys."""
    display_name = "Bosses Required Goal"
    range_start = 0
    range_end = 4
    default = 0


class GemsRequiredGoal(Range):
    """How many of the 5 Gems must be held for the goal to be met. 0
    (default) means this condition is off.

    Issue #152: composes with `Oxide Goal` and `Bosses Required Goal` as an
    AND of every active condition. When active (> 0) with `Shuffle Gems` on,
    requires `Include Gem Cup Warp Pads` on too -- otherwise the Gems the
    goal needs would sit on cups this seed excluded, generation raises a
    clear message instead of shipping an unwinnable seed."""
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


class RandomizeGemCupTracks(Toggle):
    """Randomize which tracks each Gem Cup runs.

    - **off** (default): every Gem Cup runs its vanilla four tracks.
    - **on**: every leg of every cup is drawn at random from the 16 trophy
      tracks. A track can appear in several cups, several times in one cup,
      or not at all. Slide Coliseum and Turbo Track are never drawn. The
      Purple Gem Cup loses its vanilla all-boss-track line-up like any other
      cup.

    A track's own warp pad always stays an independent way to race it, so no
    draw can lock a check away. Seeds with this on are marked schema 7: an
    older client warns that it is out of date instead of silently loading
    the vanilla cup tracks."""
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
    """Stage the Progressive Boost chain (issue #12, ruled 07-16 + the 07-26
    correction).

    - **off** (default): no Progressive Boost items exist this seed. Every
      kart keeps full self-earned boost (slides, hang time, reserve items)
      and every turbo pad works at its vanilla strength -- byte-identical to
      a pre-#12 seed, no RNG draw taken for this feature.
    - **shared_global**: one Progressive Boost chain enters the pool. Its
      received copies raise a single shared tier for every character: 0 =
      no self-earned boost at all (ordinary turbo pads still work; Super
      Turbo pads act as ordinary pads), 1 = Boost, 2 = USF-level speeds,
      and, only with `Progressive Boost: Blue Fire` also on, 3 = the Blue
      Fire capstone.
    - **per_character**: each of the 16 racers gets its own separate chain
      (16x the shared-global pool size), per the 2026-08-07 completability
      ruling. **Not yet generatable**: CTR's current location supply cannot
      place that many additional items without new locations (issue #71,
      unbuilt), so this value raises a clear OptionError at generation
      instead of silently overflowing or under-filling. The names and codes
      are already reserved on the datapackage so #71's landing does not need
      a second naming pass."""
    # Classification is per-seed: `useful` (the spine-1 shape) unless a logic
    # reader is active. #145's Turbo checks and #109's boost-gated box slots
    # both read the chain, and create_item upgrades it to `progression` in
    # exactly those seeds (logic state never tracks useful items).
    display_name = "Progressive Boost"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


class ProgressiveBoostBlueFire(Toggle):
    """Add the Blue Fire capstone tier above USF to the Progressive Boost
    chain (issue #12, 07-26 correction). Values sourced from CTR Unlimited's
    Retro Fueled mode.

    - **off** (default): the chain caps at USF -- 3 tiers, 2 received copies.
    - **on**: the chain gains a 4th tier -- 4 tiers, 3 received copies.

    No effect while `Progressive Boost` is off."""
    display_name = "Progressive Boost: Blue Fire"


class ProgressiveStatsMode(Choice):
    """Stage the Progressive Speed / Acceleration / Turning chains (issue
    #13, ruled 07-16 + the 07-26 update + the 2026-08-07 five-rank ladder
    ruling).

    - **off** (default): no Progressive stat items exist this seed. Every
      character keeps its normal vanilla stat table -- byte-identical to a
      pre-#13 seed, no RNG draw taken for this feature.
    - **shared_global**: three chains (Progressive Top Speed, Progressive
      Acceleration, Progressive Turning) enter the pool, 4 copies each (12
      items). While active every character starts at the ladder's bottom
      rank (`VERY LOW`, the per-stat minimum across every vanilla engine
      class) and received copies climb one shared rank per stat, per copy,
      up through `LOW / MEDIUM / HIGH` to `VERY HIGH` -- a rank beyond the
      best vanilla character. Character choice becomes cosmetic for these
      three stats while this mode is active.
    - **per_character**: each of the 16 racers gets its own separate set of
      three chains (192 items total), per the 2026-08-07 ruling. **Not yet
      generatable**: see `Progressive Boost`'s per_character note -- same
      issue #71 location-supply blocker, same reserved-names precedent."""
    # Same deliberate non-gating as ProgressiveBoostMode: pool/fill
    # correctness only, no track logic reads a stat tier yet.
    display_name = "Progressive Stats"
    option_off = 0
    option_shared_global = 1
    option_per_character = 2
    default = 0


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


class Itemsanity(Toggle):
    """Add the eleven received weapon items and their 22 use-time checks.

    Each Adventure-reachable weapon has one ordinary check and one juiced check
    (fired while holding at least ten Wumpa).  The native companion owns the
    crate-roll filter and the use-time check hook; this option owns the AP item
    pool, location set and additive wire declaration.
    """
    display_name = "Itemsanity"


class BoxLocations(Toggle):
    """Add the authored item-box checks (#109): one location per authored box
    position, broken once per seed by driving through it in any Adventure race
    mode on that track. 241 boxes are authored across all 18 tracks; how many
    of them your seed creates depends on `shortcut_knowledge` (229 at easy /
    236 at medium / 241 at hard).

    Items seat freely in box locations, including progression. A box slot's
    access logic mirrors its position: a handful need received Progressive
    Boost tiers or stat chains when those packs are randomized, and the Tiger
    Temple door box needs a door-opening weapon when Itemsanity is on.

    REQUIRES the 0.2.0 native client, which spawns and breaks the AP crates.
    On an older client these locations can never be checked, and any
    progression seated in them makes the seed unfinishable.
    """
    display_name = "Item Box Locations"


class ShortcutKnowledge(Choice):
    """How much shortcut knowledge the seed's box logic may assume (#109).

    - **easy** (default): no shortcut or respawn-trick boxes in the seed at
      all -- every created box sits on the normal racing line.
    - **medium**: adds boxes behind normal, non-technical shortcuts, plus the
      two reached by deliberately respawning.
    - **hard**: adds boxes behind technical/speedrunner shortcuts; these also
      require one received copy of each stat chain when Progressive Stats is
      randomized.

    A box above your chosen tier is NOT created (removed from the seed, not
    excluded), so no seed carries a location its player cannot in principle
    reach. Mints no datapackage name.
    """
    display_name = "Shortcut Knowledge"
    option_easy = 0
    option_medium = 1
    option_hard = 2
    default = 0


class OneLapCups(DefaultOnToggle):
    """Make Cup races one lap each instead of the usual three. On by default.

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

    Has no effect when fewer than two categories participate.

    Gem Cups are the one exception to `merged`: a cup is never placed on a pad that
    opens before the Cups Room's own two-Key door, so a cup can never be one of the
    pads you start with. An early cup also advertises the podium checks of the four
    trophy tracks it runs as legs, which is a large opening handout on tracks whose
    own pads are still shut."""
    display_name = "Warp Pad Shuffle Grouping"
    option_per_category = 0
    option_merged = 1
    default = 1


class WarpPadItemDisplay(Choice):
    """How a warp pad shows the items still waiting on its checks.

    A pad advertises its destination's unclaimed rewards in three floating slots.

    - **one_pile** (default): every unclaimed item shares those slots and they
      cycle through the whole pile together, so a pad with a race, a CTR
      challenge, relics and podium rungs left mixes them all in one rotation.
    - **by_reward_type**: each reward type keeps its own slot and only rotates
      within it, so you can tell at a glance whether the relic you see is the
      relic check or the CTR check. With the podium rungs on, the race slot can
      cycle through five or six items.

    Purely a display setting: it changes nothing about which checks exist, what
    they hold, or how anything unlocks. Needs a client that supports it -- an
    older one shows one pile whatever this says."""
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
    - **standard**: a moderate spread (up to 6).
    - **deep**: layered progression (up to 10).
    - **full** (default): every pad that can carry one gets one (up to 16).

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
    default = 4


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


class SapphireRelicCount(Range):
    """How many of the 18 Sapphire Time Trials (the easiest relic tier) stay
    in the seed. Exactly this many are created, drawn at random which ones;
    the rest do not exist this seed at all (issue #171: replaces the old
    0-100 percentage; issue #28: a removed Time Trial holds no check and no
    pinned vanilla relic -- beating it in game still awards the relic exactly
    like vanilla, it just is not part of this Archipelago seed). 0 = none,
    18 = all (default).

    The three tiers are a skill ladder (sapphire easy, platinum hard); setting
    an easier tier lower than a harder one gives inverted difficulty.

    Migration note: this replaces the removed `sapphire_relic_progression`
    option (0-100 percentage). The two are not the same numbering (a percent
    and a location count), so old YAMLs are not silently reinterpreted --
    `sapphire_relic_progression` is gone, AP ignores the unrecognized key with
    its standard notice, and this option starts from its own default (18,
    the closest equivalent to the old option's own default of 100/full)."""
    display_name = "Sapphire Relic Count"
    range_start = 0
    range_end = 18
    default = 18


class GoldRelicCount(Range):
    """How many of the 18 Gold Time Trials (the medium relic tier) stay in
    the seed. Exactly this many are created, drawn at random which ones; the
    rest do not exist this seed at all. See `Sapphire Relic Count` for the
    full removal semantics and the skill-ladder note. 0 = none, 18 = all
    (default).

    Migration note: replaces the removed `gold_relic_progression` percentage
    option; see `Sapphire Relic Count`'s migration note -- the old key is
    gone, not reinterpreted, and this option starts from its own default."""
    display_name = "Gold Relic Count"
    range_start = 0
    range_end = 18
    default = 18


class PlatinumRelicCount(Range):
    """How many of the 18 Platinum Time Trials (the hardest, expert-only
    relic tier) stay in the seed. Exactly this many are created, drawn at
    random which ones; the rest do not exist this seed at all. See
    `Sapphire Relic Count` for the full removal semantics. 0 = none (default,
    so a needed item never sits behind a platinum-only time), 18 = all.

    Migration note: replaces the removed `platinum_relic_progression`
    percentage option; see `Sapphire Relic Count`'s migration note -- the old
    key is gone, not reinterpreted, and this option starts from its own
    default (0, the closest equivalent to the old option's own default of
    0/never)."""
    display_name = "Platinum Relic Count"
    range_start = 0
    range_end = 18
    default = 0


class StartingCharacter(Choice):
    """Which of the 16 racers you start your Adventure as (issues #54 / #209,
    ruling R2/R3).

    In vanilla CTR only the eight original racers can be taken into Adventure
    at all; this option moves the choice out of the Garage and into your YAML,
    which is what makes the other eight selectable without any Garage-picker
    work. The 15 racers you do NOT start as become multiworld unlock items.

    - **random_starter** (default): a random pick from the eight vanilla
      Adventure racers (Crash, Neo Cortex, Tiny Tiger, Coco, N. Gin,
      Dingodile, Polar, Pura).
    - **random_any**: a random pick from all sixteen, so a seed can start you
      as Ripper Roo, Penta Penguin or Nitros Oxide.
    - any named racer: exactly that one.

    Whichever racer you start as is yours from the first frame -- it is never
    an item, never placed in the pool, and logic always assumes you have it."""
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
    """Which engine/stat class your starting racer drives with (issue #209,
    "a YAML option picks the starting character ... plus the starting
    engine/stat class").

    CTR gives every racer one of four classes, and the class -- not the racer
    -- is what the physics actually reads (`VehBirth_SetConsts` indexes
    `metaPhys[..].value[engineID]`).

    - **vanilla** (default): each racer keeps the class the game gives them,
      so Crash stays BALANCED, Tiny stays SPEED, and so on.
    - **balanced / acceleration / speed / turning**: force your starting racer
      onto that class instead, whoever they are.

    This only ever affects the racer you START as. It has no effect while
    Progressive Stats is active (those chains own the stats outright), and it
    never affects reachability, so it cannot change what a seed requires."""
    display_name = "Starting Stat Class"
    option_vanilla = 0
    option_balanced = 1
    option_acceleration = 2
    option_speed = 3
    option_turning = 4
    default = 0


class CharacterUnlocks(DefaultOnToggle):
    """Whether the other 15 racers have to be unlocked through the multiworld
    (issues #54 / #209, R4; the "all-unlocked mode" comfort option ruled in the
    2026-07-23 wayfarer's gap 7a).

    - **on** (default): the 15 racers you did not start as enter the item pool
      as unlock items. You play as your starting racer until their unlocks
      arrive. This is the feature.
    - **off**: every racer is available from the moment you start. No unlock
      items are created at all, which frees 15 pool slots, and Racer-Locked
      Warp Pads has nothing left to lock so it is forced off.

    Turn this off if you want the roster without the item economy -- or if a
    deliberately reduced seed (Podium Placement Checks off, heavy exclusions)
    does not have 15 spare locations for the unlocks. Those 15 items bring no
    locations of their own, so on a minimum-supply seed they genuinely do not
    fit, and generation will tell you so rather than quietly dropping them."""
    display_name = "Character Unlocks"


class RacerLockedPads(Toggle):
    """Let warp pads demand a specific racer before they will open (ruling R8).

    - **off** (default): no pad ever names a racer. The 15 character unlock
      items still exist and still unlock those racers to play as, but nothing
      in logic requires one, so they are `useful` items rather than
      progression and the seed only ever plans around the racer you start as.
    - **on**: a small number of this seed's randomized pads additionally
      require you to be a specific racer, on top of whatever trophies, keys,
      tokens, relics or gems that pad already asked for. The character unlock
      items become `progression` items, because a pad genuinely depends on
      one.

    You swap racer from the Adventure hub, so "unlocked" and "usable" mean the
    same thing: walk into the hub, pick the racer the pad wants, drive in.

    Never applied to the always-open starter pads or to any pad this seed left
    free, so the opening of the seed is unchanged either way, and a racer's own
    unlock item can never be placed behind a pad that requires that racer."""
    display_name = "Racer-Locked Warp Pads"


class PentaStats(Choice):
    """Which stat table Penta Penguin drives with (ruling R15).

    Penta is a cheat-code racer in retail, and the two regional releases give
    him very different karts.

    - **pal** (default): Penta drives with his ordinary TURN-class stats, the
      fair, balanced version. This is the default because it is the one that
      does not distort a seed's difficulty.
    - **ntsc**: Penta drives the max-stat cheat version -- the fifth "MAX"
      engine class that ships in the PAL/JP build and that the NTSC-U cheat
      code produces. It is a best-of-each-axis cherry-pick of the four normal
      classes (SPEED's top speed, ACCEL's acceleration, TURN's whole handling
      group), so it is the best vanilla kart in the game but it invents no
      numbers and goes nowhere above vanilla.

    This only applies while VANILLA character stats are in play. As soon as
    Progressive Stats or Editable Stats owns the stat table, Penta reads that
    like every other racer and this option has no gameplay effect at all."""
    display_name = "Penta Penguin Stats"
    option_pal = 0
    option_ntsc = 1
    default = 0


class EditableStats(Choice):
    """Let you tune your kart's stats yourself, from the hub stat panel
    (2026-08-08 ruling).

    **Only available when `progressive_stats` is off.** If you enable both,
    the seed still generates and Progressive Stats wins: the stat panel goes
    read-only and no edit control appears at all. This is deliberate -- the
    two are separate configuration concepts and the seed is never rejected for
    setting both.

    - **off** (default): no editing. The panel shows whatever owns your stats.
    - **global**: one custom stat package shared by every racer.
    - **per_character**: a separate custom package per racer, so each of the
      sixteen can be tuned independently.

    Edited values follow your slot on the Archipelago server rather than a
    local save file, so they survive a reconnect and a change of machine.
    Editing never affects reachability: no location's access rule reads a stat,
    at any setting."""
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
    itemsanity: Itemsanity
    # authored item-box checks (#109)
    box_locations: BoxLocations
    shortcut_knowledge: ShortcutKnowledge
    # capability item packs (issues #12, #13)
    progressive_boost: ProgressiveBoostMode
    progressive_boost_blue_fire: ProgressiveBoostBlueFire
    progressive_stats: ProgressiveStatsMode
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
    "Goal": [OxideGoal, BossesRequiredGoal, GemsRequiredGoal,
            FinalOxideUnlock, FinalOxideRelicCount],
    "Items & Pool": [ShuffleGems, ShuffleWarpPadsGemCups, RandomizeGemCupTracks,
                     ShuffleKeys, TrapFillPercentage, Itemsanity],
    "Capability Items": [ProgressiveBoostMode, ProgressiveBoostBlueFire,
                         ProgressiveStatsMode],
    # Grouped together on purpose: a player reads "who do I start as", "who can
    # I unlock", "can a pad demand a racer" and "who owns my stats" as one
    # decision, and the 2026-08-08 note asked for exactly this grouping.
    "Characters": [StartingCharacter, StartingStatClass, CharacterUnlocks,
                   RacerLockedPads, PentaStats, EditableStats],
    "Warp Pads": [
        ShuffleWarpPadsBattleArenas,
        WarpPadShuffleCategories,
        WarpPadShuffleGrouping,
        WarpPadItemDisplay,
        WarpPadUnlockRequirements,
        TwoStageDensity,
        RequirementVariety,
        RequirementWeights,
    ],
    "Extra Checks": [PodiumPlacementChecks, PodiumFinishRungs,
                     PodiumAnyPositionRung, PodiumHeldRungs, PodiumHeldFifthRung],
    "Quality of Life": [OneLapCups],
    "DeathLink": [DeathLink, DeathLinkAmnesty],
    "Relic Difficulty": [SapphireRelicCount, GoldRelicCount,
                         PlatinumRelicCount],
}

def create_option_groups() -> List[OptionGroup]:
    return [
        OptionGroup(name=x, options=y)
        for x, y in ap_ctr_option_groups.items()
    ]
