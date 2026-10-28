"""Boss opponent and kit shuffle (#169 tiers 2 and 3, 0.3.0, schema 18).

Design: the 0.3.0 #169 design with independent switches, ruled 2026-10-13,
and the random character boss battles Wayfinder note (2026-09-01). Tier 1,
the track switch, is `boss_track_shuffle`; this module adds the opponent and
kit switches and owns the combined `boss_encounters` record.

WHAT THE OPTIONS DO. Three Toggles, all off by default, any combination:

  * `boss_track_shuffle` (tier 1): the garage races on a drawn venue.
  * `boss_opponent_shuffle` (tier 2): the garage races a drawn racer. The
    pool (`POOL`, built so custom characters can join later) is the 15
    retail racers other than N. Oxide, plus N. Oxide with
    `boss_oxide_in_pool` (decision 7 of 2026-10-28), narrowed by
    `boss_character_allowlist` (empty = no narrowing) and then
    `boss_character_blocklist`. With `boss_oxide_in_pool` N. Oxide's own
    garage (both races) also races a drawn racer other than N. Oxide, and
    all five bosses differ. With track shuffle off the venue stays the
    garage's own track (design ruling 2026-10-13, answer 1). With both on,
    `boss_track_assignment: character_home_track` (default) races the drawn
    racer on their one home track (the Wayfinder B0 table) and
    `independent_track` keeps the tier 1 venue draw.
  * `boss_kit_shuffle` (tier 3): the garage gets a composed attack schedule.
    `mixed_loadouts` (default) uses two to four distinct weapon families per
    encounter, `signature_profiles` gives each encounter one whole retail
    boss profile. `boss_attack_intensity` scales every segment's cooldown
    only, never the families or checkpoints. `boss_loss_easing` (default on)
    keeps the retail rule that each lost race lengthens the cooldowns.
    `boss_powerup_blocklist` removes families.
  * `purple_cup_boss_gauntlet` (needs the kit switch): each Purple Gem Cup
    leg arms garage i's racer with garage i's kit on that leg's track.
  * `oxide_attack_profile: all_compatible` (independent of the switches):
    N. Oxide's garage gets a composed 13-segment profile from every family,
    the Super Engine included, minus `oxide_powerup_blocklist`.

Every garage keeps its physical identity: the `<Boss> Garage: Boss Race`
check and code, the Key, the door requirement, the personal-win event, the
loss counter and the boss-grade driving table of the physical garage
(`ai_profile: retail`, native `data.BossDifficulty[bossID]`). So a swapped
racer drives with the garage's boss-grade profile, scaled by the client's
global AI setting as before. N. Oxide's garage keeps its door, checks and
goal; only its racer (decision 7) and its attack profile can change.

WEAPON FAMILIES. The projectile families are the four weapons the retail
boss attack path (`PickupBots_UpdateBoss`) fires through
`VehPickupItem_ShootNow`: TNT, potion, bomb and missile. TNT, potion and
bomb segments copy rows of the retail `data.BossWeapon*` tables exactly
(weapon code, throw direction, path-change flag, cooldown, juice pattern).
The missile segment is the bomb row with the missile item; retail arcade AI
fires missiles on every race track. The advanced families (decisions 5 and
6 of 2026-10-28, Wayfinder D2) are turbo, shield, mask, clock, warp orb and
invisibility, plus the Super Engine for N. Oxide's profile only; native's
boss adapter fires them with the retail item effect and duration, once per
segment entry, with the per-weapon rules of decision 6.

SCHEDULE SHAPE. A composed schedule has the same five checkpoint-keyed
segments as the garage's retail schedule, at the same relative lap
positions (`boss_track_shuffle.translated_schedule`), so a venue that
carries the inherited attack also carries a composed one; the same
certification applies.

THE DRAW. Once in `generate_early` (`draw`), pinned from the wire under
Universal Tracker (`restore_from_wire`). Native never redraws. With both new
switches off nothing here draws, so a tier 1 seed keeps its RNG stream and
its version 1 wire block exactly. Encounters never repeat (decision 7):
four distinct venues, opponents (five with N. Oxide's garage) and kits;
the whole assignment is tested, so impossible filters fail generation.

LOGIC. Kits do not change reachability (design: enemy weapons are not
player unlocks). A venue moved by the home-track pairing goes through the
same `_boss_track_venues` table tier 1 uses: the boss win's finish term and
the garage's Wumpa route. The opponent changes the Hit Character checks
(decision 9): `boss_identity` feeds the Hit block's `bosses` table and its
unlock triggers, so a boss-race Hit route follows the drawn racer and
beating a garage unlocks the drawn racer as an opponent in other races.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from Options import OptionError

from . import boss_track_shuffle as bts
from .characters import ROSTER_CHARACTER_ID, _option_key

#: Wire block version with an opponent or kit switch on. Version 1 (tier 1
#: track rows only) is still emitted when only the track switch is on.
BLOCK_VERSION = 2

#: Wayfinder B0 (ruled 2026-09-02): every racer's one home track.
HOME_TRACK: Dict[str, str] = {
    "Crash Bandicoot": "Crash Cove",
    "Ripper Roo": "Roo's Tubes",
    "Coco Bandicoot": "Coco Park",
    "Pura": "Tiger Temple",
    "Papu Papu": "Papu's Pyramid",
    "Dingodile": "Dingo Canyon",
    "Polar": "Polar Pass",
    "Neo Cortex": "Cortex Castle",
    "N. Gin": "N. Gin Labs",
    "Tiny Tiger": "Tiny Arena",
    "Pinstripe": "Hot Air Skyway",
    "Komodo Joe": "Dragon Mines",
    "Nitros Oxide": "Oxide Station",
    "Penta Penguin": "Blizzard Bluff",
    "N. Tropy": "Turbo Track",
    "Fake Crash": "Sewer Speedway",
}
assert set(HOME_TRACK) == set(ROSTER_CHARACTER_ID)
assert set(HOME_TRACK.values()) <= set(bts.VENUES)

#: The boss character pool (decision 7 of 2026-10-28: built so custom
#: characters can join later). One record per racer: roster name, wire key,
#: engine character id, home track, and where it comes from. Retail racers
#: only today; a custom character will add a record with its own frozen
#: identity and package pin, and every draw below reads this table, never a
#: hard-coded roster.
POOL: Tuple[Tuple[str, str, int, str, str], ...] = tuple(
    (name, _option_key(name), cid, HOME_TRACK[name], "retail")
    for name, cid in ROSTER_CHARACTER_ID.items())
#: Every pool racer by roster name, N. Oxide included.
POOL_NAMES: Tuple[str, ...] = tuple(rec[0] for rec in POOL)
#: Racers a garage may draw without `boss_oxide_in_pool`: the pool without
#: N. Oxide.
OPPONENT_NAMES: Tuple[str, ...] = tuple(n for n in POOL_NAMES if n != "Nitros Oxide")
#: {roster name -> wire key}. The four bosses' keys are the garage keys.
OPPONENT_KEY: Dict[str, str] = {rec[0]: rec[1] for rec in POOL}
_OPPONENT_BY_KEY: Dict[str, str] = {k: n for n, k in OPPONENT_KEY.items()}
#: {roster name -> engine character id}.
OPPONENT_ENGINE_ID: Dict[str, int] = {rec[0]: rec[2] for rec in POOL}
#: {garage key -> its own boss's roster name}.
GARAGE_BOSS: Dict[str, str] = {
    "ripper_roo": "Ripper Roo", "papu_papu": "Papu Papu",
    "komodo_joe": "Komodo Joe", "pinstripe": "Pinstripe"}
assert all(OPPONENT_KEY[name] == key for key, name in GARAGE_BOSS.items())
assert OPPONENT_KEY["Nitros Oxide"] == "nitros_oxide"

AI_PROFILE = "retail"
ATTACK_INHERITED = bts.ATTACK_INHERITED
ATTACK_COMPOSED = "composed"

#: Retail `MetaDataBOSS` codes. Weapon: 0x01 bomb, 0x02 missile, 0x03 TNT,
#: 0x04 potion, 0x64 TNT and 0x66 potion with the boss juice cycle, 0x0f
#: none. Throw: 2 forward, 3 dropped or normal. Juice: 0 none, 1 juiced,
#: 2 alternating.
WEAPON_CODES = (0x00, 0x01, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0C, 0x0D, 0x0F, 0x64, 0x66)
THROW_CODES = (2, 3)
JUICE_CODES = (0, 1, 2)
COOLDOWN_MIN, COOLDOWN_MAX = 2, 0xFF
SEGMENTS = len(bts.RETAIL_ATTACK_CHECKPOINTS["ripper_roo"])

#: Certified weapon families: their segment variants (weapon, throw, path
#: change disabled, cooldown, juice), each a retail row unless noted.
#: Projectile families fire through the retail boss path
#: (`PickupBots_UpdateBoss` -> `VehPickupItem_ShootNow`). The advanced
#: families (decision 5 and 6 of 2026-10-28, Wayfinder D2) are engine item
#: ids fired through native's boss adapter, one use per segment entry; their
#: rows are new, with the retail item effect and duration.
FAMILY_VARIANTS: Dict[str, Tuple[Tuple[int, int, int, int, int], ...]] = {
    "tnt": ((0x03, 3, 0, 0x0F, 0),     # data.BossWeaponRoo: dropped TNT
            (0x64, 2, 0, 0x11, 2)),    # data.BossWeaponJoe: thrown TNT
    "potion": ((0x66, 2, 1, 0x0C, 2),  # data.BossWeaponPapu: thrown potion
               (0x04, 2, 1, 0x0C, 1)),  # data.BossWeaponOxide: juiced potion
    "bomb": ((0x01, 3, 1, 0x0F, 0),    # data.BossWeaponPinstripe
             (0x01, 3, 1, 0x0C, 0)),   # data.BossWeaponOxide
    "missile": ((0x02, 3, 1, 0x0F, 0),),  # the bomb row with the missile item
    "turbo": ((0x00, 3, 1, 0x0C, 0),),
    "shield": ((0x06, 3, 1, 0x0C, 0),),
    "mask": ((0x07, 3, 1, 0x0C, 0),),
    "clock": ((0x08, 3, 1, 0x0C, 0),),
    "warp_orb": ((0x09, 2, 1, 0x0C, 0),),
    "invisibility": ((0x0C, 3, 1, 0x0C, 0),    # retail 0x1e00
                     (0x0C, 3, 1, 0x0C, 1)),   # retail juiced 0x2d00
    "super_engine": ((0x0D, 3, 1, 0x0C, 0),),  # N. Oxide's final record only
}
FAMILIES: Tuple[str, ...] = tuple(FAMILY_VARIANTS)
#: Families only N. Oxide's `all_compatible` profile may use (decision 6).
OXIDE_ONLY_FAMILIES: Tuple[str, ...] = ("super_engine",)
#: Families a garage kit or a gauntlet leg may use.
GARAGE_FAMILIES: Tuple[str, ...] = tuple(f for f in FAMILIES if f not in OXIDE_ONLY_FAMILIES)
#: Weapon code -> family, for a schedule read back from the wire.
WEAPON_FAMILY: Dict[int, str] = {0x01: "bomb", 0x02: "missile", 0x03: "tnt", 0x64: "tnt",
                                 0x04: "potion", 0x66: "potion", 0x00: "turbo", 0x06: "shield",
                                 0x07: "mask", 0x08: "clock", 0x09: "warp_orb",
                                 0x0C: "invisibility", 0x0D: "super_engine"}
MIX_MIN, MIX_MAX = 2, 4

#: signature_profiles: the four retail garage schedules (weapon, throw,
#: path, cooldown, juice per segment), copied from data.BossWeapon*.
SIGNATURES: Dict[str, Tuple[Tuple[int, int, int, int, int], ...]] = {
    "ripper_roo": ((0x03, 3, 0, 0x0F, 0),) * 5,
    "papu_papu": ((0x66, 2, 1, 0x0C, 2), (0x0F, 2, 1, 0x0C, 2), (0x66, 2, 1, 0x0C, 2),
                  (0x0F, 2, 1, 0x0C, 2), (0x66, 2, 1, 0x0C, 2)),
    "komodo_joe": ((0x64, 2, 0, 0x11, 2), (0x64, 2, 0, 0x11, 2), (0x0F, 2, 0, 0x11, 2),
                   (0x64, 2, 0, 0x11, 2), (0x64, 2, 0, 0x11, 2)),
    "pinstripe": ((0x01, 3, 1, 0x0F, 0), (0x01, 3, 1, 0x0F, 0), (0x0F, 3, 1, 0x0F, 0),
                  (0x01, 3, 1, 0x0F, 0), (0x01, 3, 1, 0x0F, 0)),
}

#: Every (weapon, throw, path, juice) a composed segment may carry: the
#: family variants and the signature rows. The cooldown is free within its
#: range because intensity scales it. Native AP_BossKitRowCertified is the twin.
CERTIFIED_ROWS = frozenset(
    (w, t, p, j) for rows in tuple(FAMILY_VARIANTS.values()) + tuple(SIGNATURES.values())
    for w, t, p, _c, j in rows)

#: N. Oxide as a wire opponent (decision 7: only with `boss_oxide_in_pool`).
OXIDE_NAME = "Nitros Oxide"
OXIDE_KEY = "nitros_oxide"
#: The final record covers both N. Oxide garage races (decision 7).
FINAL_LOCATIONS: Tuple[int, int] = (35011104, 35011105)
FINAL_KEYS = ("locations", "opponent", "attack", "schedule")
#: Retail data.BossWeaponOxide segment starts (Oxide Station checkpoints,
#: 0x7f is the table's last). A composed Oxide profile keeps them, so the
#: retail Oxide certification and native's Cortex Vortex remap
#: (AP_OxideWeaponCheckpoint) carry over unchanged.
OXIDE_CHECKPOINTS: Tuple[int, ...] = (0x00, 0x10, 0x21, 0x2F, 0x3B, 0x40, 0x46, 0x56, 0x5D,
                                      0x60, 0x65, 0x66, 0x7F)
OXIDE_SEGMENTS = len(OXIDE_CHECKPOINTS)
#: Purple Gem Cup gauntlet: four legs, leg i armed with garage i's racer.
GAUNTLET_LEGS = 4
GAUNTLET_LEG_KEYS = ("track", "attacker", "schedule")

#: boss_attack_intensity -> cooldown factor (numerator, denominator).
INTENSITY: Tuple[Tuple[str, int, int], ...] = (
    ("relaxed", 3, 2), ("standard", 1, 1), ("intense", 3, 4), ("mayhem", 1, 2))
ASSIGNMENTS = ("mixed_loadouts", "signature_profiles")

ROW_KEYS = bts.ROW_KEYS + ("schedule",)
KIT_KEYS = ("assignment", "intensity", "loss_easing")

Segment = Tuple[int, int, int, int, int, int]


def _garage_keys() -> List[str]:
    return [key for key, _r, _c, _h in bts.GARAGES]


def opponent_on(options) -> bool:
    return bool(getattr(options, "boss_opponent_shuffle", None)
                and options.boss_opponent_shuffle.value)


def kit_on(options) -> bool:
    return bool(getattr(options, "boss_kit_shuffle", None)
                and options.boss_kit_shuffle.value)


def oxide_in_pool(options) -> bool:
    """Effective `boss_oxide_in_pool`: only with opponent shuffle on
    (decision 7 of 2026-10-28)."""
    return opponent_on(options) and bool(getattr(options, "boss_oxide_in_pool", None)
                                         and options.boss_oxide_in_pool.value)


def oxide_profile_all(options) -> bool:
    return bool(getattr(options, "oxide_attack_profile", None)
                and int(options.oxide_attack_profile.value) == 1)


def gauntlet_on(options) -> bool:
    """`purple_cup_boss_gauntlet`; `validate_options` refuses it without the
    kit switch (design answer 3, 2026-10-13)."""
    return kit_on(options) and bool(getattr(options, "purple_cup_boss_gauntlet", None)
                                    and options.purple_cup_boss_gauntlet.value)


def final_on(options) -> bool:
    """Does the seed carry the `final` record (N. Oxide's garage)?"""
    return oxide_in_pool(options) or oxide_profile_all(options)


def any_on(options) -> bool:
    return bts.enabled(options) or opponent_on(options) or kit_on(options) or final_on(options)


def home_pairing(options) -> bool:
    """Is the drawn racer's home track the venue? Only with both draw
    switches on and `character_home_track` (design ruling 2026-10-13, answer 1)."""
    return (bts.enabled(options) and opponent_on(options)
            and int(options.boss_track_assignment.value) == 0)


def _who(world) -> str:
    from .notices import slot_label
    return slot_label(world)


def scale_cooldown(cooldown: int, intensity: int) -> int:
    _name, num, den = INTENSITY[intensity]
    return max(COOLDOWN_MIN, min(COOLDOWN_MAX, (cooldown * num) // den))


def family_of(weapon: int) -> Optional[str]:
    return WEAPON_FAMILY.get(weapon)


# --------------------------------------------------------------------- options

def validate_options(world) -> None:
    """Subordinate controls without their switch are ignored with a notice,
    not refused: the 2026-10-15 tier 1 ruling (the DeathLink Send pattern),
    applied the same way to the new controls. Impossible draws with a switch
    on still stop generation (see `draw`). The Purple Gem Cup gauntlet
    without Boss Kit Shuffle is refused (design answer 3, 2026-10-13)."""
    o = world.options
    from .notices import note_ignored
    if (getattr(o, "purple_cup_boss_gauntlet", None) and o.purple_cup_boss_gauntlet.value
            and not kit_on(o)):
        raise OptionError(
            f"CTR ({_who(world)}): purple_cup_boss_gauntlet needs boss_kit_shuffle on. Turn on "
            "boss_kit_shuffle or turn off purple_cup_boss_gauntlet.")
    if not opponent_on(o):
        for name, label in (("boss_character_allowlist", "Boss Character Allowlist"),
                            ("boss_character_blocklist", "Boss Character Blocklist")):
            if getattr(o, name).value:
                note_ignored(world, f"{label} (Boss Opponent Shuffle off)")
        if o.boss_oxide_in_pool.value:
            note_ignored(world, "Boss Pool Includes N. Oxide (Boss Opponent Shuffle off)")
    if int(o.boss_track_assignment.value) != 0 and not (bts.enabled(o) and opponent_on(o)):
        note_ignored(world, "Boss Track Assignment (needs Boss Track Shuffle and Boss Opponent Shuffle)")
    if not kit_on(o):
        if int(o.boss_attack_assignment.value) != 0:
            note_ignored(world, "Boss Attack Assignment (Boss Kit Shuffle off)")
        if int(o.boss_attack_intensity.value) != 1:
            note_ignored(world, "Boss Attack Intensity (Boss Kit Shuffle off)")
        if not o.boss_loss_easing.value:
            note_ignored(world, "Boss Loss Easing (Boss Kit Shuffle off)")
        if o.boss_powerup_blocklist.value:
            note_ignored(world, "Boss Powerup Blocklist (Boss Kit Shuffle off)")
    if not oxide_profile_all(o) and o.oxide_powerup_blocklist.value:
        note_ignored(world, "N. Oxide Powerup Blocklist (N. Oxide Attack Profile retail)")


def opponent_pool(options) -> List[str]:
    """Pool names, `all_compatible` narrowed by the allowlist, then the
    blocklist. N. Oxide only with `boss_oxide_in_pool` (decision 7)."""
    allow = set(options.boss_character_allowlist.value)
    block = set(options.boss_character_blocklist.value)
    with_oxide = oxide_in_pool(options)
    return [n for n in POOL_NAMES
            if (with_oxide or n != OXIDE_NAME) and (not allow or n in allow) and n not in block]


def final_pool(options) -> List[str]:
    """Racers N. Oxide's garage may draw: the garage pool without N. Oxide
    ("then the final boss should be different", decision 7)."""
    return [n for n in opponent_pool(options) if n != OXIDE_NAME]


def allowed_families(options) -> List[str]:
    """Garage and gauntlet families after `boss_powerup_blocklist`."""
    block = set(options.boss_powerup_blocklist.value)
    return [f for f in GARAGE_FAMILIES if f not in block]


def oxide_families(options) -> List[str]:
    """N. Oxide's `all_compatible` families after `oxide_powerup_blocklist`
    (Wayfinder D2a: independent of `boss_powerup_blocklist`)."""
    block = set(options.oxide_powerup_blocklist.value)
    return [f for f in FAMILIES if f not in block]


def allowed_signatures(options) -> List[str]:
    """Retail profiles whose weapons all survive the blocklist."""
    fams = set(allowed_families(options))
    return [key for key, rows in SIGNATURES.items()
            if all(family_of(r[0]) in fams for r in rows if r[0] != 0x0F)]


# ------------------------------------------------------------------------ draw

def _feasible_distinct(pools: Sequence[Sequence[str]]) -> bool:
    """Is there a pick of one value per pool, all different? (At most five
    pools of at most 18 values: plain backtracking.)"""
    def go(i, used):
        if i == len(pools):
            return True
        return any(v not in used and go(i + 1, used | {v}) for v in pools[i])
    return go(0, frozenset())


def _distinct_draw(rng, pools: Sequence[Sequence[str]]) -> Optional[List[str]]:
    """A uniform pick over every all-different assignment, or None when none
    exists. Rejection sampling of independent uniform picks is uniform over
    the accepted set; the feasibility test first keeps it from looping on an
    empty set. Never lists the assignments (0.3.0 review finding 2)."""
    pools = [list(p) for p in pools]
    if not all(pools) or not _feasible_distinct(pools):
        return None
    while True:
        picked = [rng.choice(p) for p in pools]
        if len(set(picked)) == len(picked):
            return picked


def draw(world) -> None:
    """Resolve and freeze the garage encounters and N. Oxide's garage record
    on `world.options`.

    Runs the tier 1 venue draw unchanged unless the home-track pairing owns
    the venues, then the opponent draw (with `boss_oxide_in_pool`, jointly
    with N. Oxide's garage racer, so all five differ), then the kit draw,
    then N. Oxide's composed profile. A switch that is off draws nothing.
    Results: `_boss_track_venues` (tier 1's table), `_boss_opponents`
    {garage -> roster name}, `_boss_kits` {garage -> tuple of segments},
    `_boss_final_opponent` (roster name) and `_boss_final_schedule` (tuple of
    13 segments, empty for N. Oxide's retail table)."""
    o = world.options
    validate_options(world)
    keys = _garage_keys()
    o._boss_final_opponent = OXIDE_NAME
    if home_pairing(o):
        bts.validate_options(world)
        _draw_home_paired(world, keys)
    else:
        bts.draw(world)
        if opponent_on(o):
            _draw_opponents(world, keys, {k: opponent_pool(o) for k in keys})
        else:
            o._boss_opponents = dict(GARAGE_BOSS)
    if kit_on(o):
        _draw_kits(world, keys)
    else:
        o._boss_kits = {}
    o._boss_final_schedule = _draw_oxide_profile(world) if oxide_profile_all(o) else ()


def _draw_opponents(world, keys, pools) -> None:
    """Four distinct garage racers; with `boss_oxide_in_pool` a fifth for N.
    Oxide's garage, drawn jointly so the five differ (decision 7)."""
    o = world.options
    for key, region, _c, _h in bts.GARAGES:
        if not pools[key]:
            raise OptionError(
                f"CTR ({_who(world)}): boss_opponent_shuffle has no racer left for "
                f"{region} after boss_character_allowlist and boss_character_blocklist.")
    lists = [pools[k] for k in keys]
    with_final = oxide_in_pool(o)
    if with_final:
        if not final_pool(o):
            raise OptionError(
                f"CTR ({_who(world)}): boss_oxide_in_pool has no racer other than N. Oxide left for "
                f"{bts.OXIDE_GARAGE} after boss_character_allowlist and boss_character_blocklist.")
        lists.append(final_pool(o))
    picked = _distinct_draw(world.random, lists)
    if picked is None:
        count = len(lists)
        raise OptionError(
            f"CTR ({_who(world)}): boss_opponent_shuffle cannot give the "
            + ("four boss garages and N. Oxide's garage five" if with_final else "four boss garages four")
            + " different racers from the allowed pool (" + ", ".join(opponent_pool(o))
            + f"). Bosses never repeat, so allow at least {count} racers that fit.")
    o._boss_opponents = dict(zip(keys, picked[:len(keys)]))
    if with_final:
        o._boss_final_opponent = picked[len(keys)]


def _draw_home_paired(world, keys) -> None:
    """Both draw switches on, character_home_track: a racer qualifies for a
    garage when their home track is in the track pool and carries the
    garage's attack. Distinct racers give distinct venues, as the home
    table is one to one."""
    o = world.options
    venues = set(bts.venue_pool(o))
    pools = {k: [n for n in opponent_pool(o)
                 if HOME_TRACK[n] in venues and bts.inherited_attack_certified(k, HOME_TRACK[n])]
             for k in keys}
    for key, region, _c, _h in bts.GARAGES:
        if not pools[key]:
            raise OptionError(
                f"CTR ({_who(world)}): boss_track_assignment: character_home_track has no racer "
                f"left for {region} whose home track is in the boss track pool. Allow more racers "
                "or tracks, or set boss_track_assignment: independent_track.")
    _draw_opponents(world, keys, pools)
    o._boss_track_venues = {k: HOME_TRACK[o._boss_opponents[k]] for k in keys}


def _segments(garage: str, track: str, rows, intensity: int) -> Tuple[Segment, ...]:
    checkpoints = bts.translated_schedule(garage, track)
    return tuple((cp, throw, weapon, path, scale_cooldown(cooldown, intensity), juice)
                 for cp, (weapon, throw, path, cooldown, juice) in zip(checkpoints, rows))


def _mixed_rows(rng, families: Sequence[str], segments: int = SEGMENTS,
                low: int = MIX_MIN, high: int = MIX_MAX):
    k = rng.randint(min(low, len(families)), min(high, len(families)))
    chosen = rng.sample(list(families), k)
    order = chosen + [rng.choice(chosen) for _ in range(segments - k)]
    rng.shuffle(order)
    return tuple(rng.choice(FAMILY_VARIANTS[f]) for f in order)


def _intensity(options) -> int:
    return int(options.boss_attack_intensity.value) if kit_on(options) else 1


def _draw_kits(world, keys) -> None:
    o = world.options
    venues = bts.venues(o)
    intensity = int(o.boss_attack_intensity.value)
    kits: Dict[str, Tuple[Segment, ...]] = {}
    if int(o.boss_attack_assignment.value) == 1:
        profiles = allowed_signatures(o)
        if len(profiles) < len(keys):
            raise OptionError(
                f"CTR ({_who(world)}): boss_attack_assignment: signature_profiles needs four "
                "different retail profiles, but boss_powerup_blocklist leaves "
                + (", ".join(profiles) or "none") + ". Bosses never repeat, so unblock weapons.")
        picked = world.random.sample(profiles, len(keys))
        for key, profile in zip(keys, picked):
            kits[key] = _segments(key, venues[key], SIGNATURES[profile], intensity)
    else:
        families = allowed_families(o)
        if len(families) < MIX_MIN:
            raise OptionError(
                f"CTR ({_who(world)}): boss_attack_assignment: mixed_loadouts needs at least "
                f"{MIX_MIN} weapon types, but boss_powerup_blocklist leaves "
                + (", ".join(families) or "none") + ".")
        seen = set()
        for key in keys:
            rows = _mixed_rows(world.random, families)
            # Distinct mixes (Wayfinder D1, never a repeat since decision 7).
            # Thousands of mixes exist for any two families, so the bound is
            # never reached in practice; it only keeps the loop finite.
            tries = 0
            while tuple(r[0] for r in rows) in seen:
                tries += 1
                if tries > 1000:
                    raise OptionError(f"CTR ({_who(world)}): could not draw four different boss kits.")
                rows = _mixed_rows(world.random, families)
            seen.add(tuple(r[0] for r in rows))
            kits[key] = _segments(key, venues[key], rows, intensity)
    o._boss_kits = kits


def _draw_oxide_profile(world) -> Tuple[Segment, ...]:
    """N. Oxide's `all_compatible` profile (Wayfinder D2a): the 13 retail
    Oxide segment starts, each segment a certified row of an allowed family,
    two to six families, the Super Engine allowed. Cooldowns follow
    `boss_attack_intensity` when the kit switch is on, else standard."""
    o = world.options
    families = oxide_families(o)
    if not families:
        raise OptionError(
            f"CTR ({_who(world)}): oxide_attack_profile: all_compatible has no weapon type left "
            "after oxide_powerup_blocklist.")
    rows = _mixed_rows(world.random, families, OXIDE_SEGMENTS, 2, 6)
    intensity = _intensity(o)
    return tuple((cp, throw, weapon, path, scale_cooldown(cooldown, intensity), juice)
                 for cp, (weapon, throw, path, cooldown, juice) in zip(OXIDE_CHECKPOINTS, rows))


def opponents(options) -> Dict[str, str]:
    """{garage key -> opponent roster name} for this seed."""
    if not opponent_on(options):
        return dict(GARAGE_BOSS)
    resolved = getattr(options, "_boss_opponents", None)
    if resolved is None:
        raise RuntimeError("CTR: boss opponents read before boss_encounters.draw")
    return dict(resolved)


def final_opponent(options) -> str:
    """The racer of N. Oxide's garage (both races): N. Oxide unless
    `boss_oxide_in_pool` drew another racer."""
    if not oxide_in_pool(options):
        return OXIDE_NAME
    resolved = getattr(options, "_boss_final_opponent", None)
    if resolved is None:
        raise RuntimeError("CTR: N. Oxide's garage racer read before boss_encounters.draw")
    return resolved


def final_schedule(options) -> Tuple[Segment, ...]:
    """N. Oxide's composed profile, or () for his retail table."""
    if not oxide_profile_all(options):
        return ()
    resolved = getattr(options, "_boss_final_schedule", None)
    if resolved is None:
        raise RuntimeError("CTR: N. Oxide's profile read before boss_encounters.draw")
    return tuple(resolved)


def kits(options) -> Dict[str, Tuple[Segment, ...]]:
    """{garage key -> composed schedule}; empty with kit shuffle off."""
    if not kit_on(options):
        return {}
    resolved = getattr(options, "_boss_kits", None)
    if resolved is None:
        raise RuntimeError("CTR: boss kits read before boss_encounters.draw")
    return dict(resolved)


def boss_identity(options) -> Dict[int, int]:
    """{boss win AP code -> engine id of the racer actually raced there}: the
    four garage codes follow the drawn garage racer, both N. Oxide codes the
    racer of N. Oxide's garage. The Hit Character `bosses` table and every
    boss-race Hit route read this (decision 9 of 2026-10-28)."""
    opp = opponents(options)
    out = {code: OPPONENT_ENGINE_ID[opp[key]] for key, _r, code, _h in bts.GARAGES}
    final = OPPONENT_ENGINE_ID[final_opponent(options)]
    for code in FINAL_LOCATIONS:
        out[code] = final
    return out


def kit_label(schedule: Iterable[Segment]) -> str:
    fams = []
    for seg in schedule:
        f = family_of(seg[2])
        if f and f not in fams:
            fams.append(f)
    return ", ".join(fams)


# -------------------------------------------------------------------- gauntlet

PURPLE_CUP = "Purple Gem Cup"


def gauntlet_legs(world) -> List[Dict[str, object]]:
    """The Purple Gem Cup gauntlet (decision 5): leg i is armed with garage
    i's racer and garage i's composed kit, its segments mapped onto the leg's
    track the way a drawn venue maps them. A leg that is not a retail race
    track (Cortex Vortex, a custom track) carries no attack (`track` -1).
    Derived from the frozen kits and the seed's leg table, so it takes no
    random draw."""
    o = world.options
    from .gem_cup_legs import resolved_gem_cup_legs
    legs = list(resolved_gem_cup_legs(world).get(PURPLE_CUP, ()))
    opp = opponents(o)
    ks = kits(o)
    out: List[Dict[str, object]] = []
    for i, key in enumerate(_garage_keys()):
        track = legs[i] if i < len(legs) else None
        attacker = OPPONENT_KEY[opp[key]]
        if track not in bts.VENUES or not bts.inherited_attack_certified(key, track):
            out.append({"track": -1, "attacker": attacker, "schedule": []})
            continue
        cps = bts.translated_schedule(key, track)
        out.append({"track": bts.VENUE_LEVEL_IDS[track], "attacker": attacker,
                    "schedule": [[cp] + list(seg[1:]) for cp, seg in zip(cps, ks[key])]})
    return out


# ------------------------------------------------------------------------ wire

def _version1_only(options) -> bool:
    return bts.enabled(options) and not (opponent_on(options) or kit_on(options) or final_on(options))


def wire_block(options, world=None) -> Optional[Dict[str, object]]:
    """The `boss_encounters` slot_data block: None with every switch off,
    tier 1's version 1 block with only the track switch on, else version 2:
    four complete rows keyed by physical garage, each with a `schedule`
    (empty for the inherited attack), plus a `kit` record with kit shuffle
    on, a `final` record for N. Oxide's garage with `boss_oxide_in_pool` or
    `oxide_attack_profile: all_compatible`, and a `gauntlet` record with the
    Purple Gem Cup gauntlet on (needs `world` for the cup's legs)."""
    if not any_on(options):
        return None
    if _version1_only(options):
        return bts.wire_block(options)
    v = bts.venues(options)
    opp = opponents(options)
    ks = kits(options)
    garages: Dict[str, Dict[str, object]] = {}
    for key, _region, code, home in bts.GARAGES:
        garages[key] = {
            "location": code,
            "home_track": bts.VENUE_LEVEL_IDS[home],
            "track": bts.VENUE_LEVEL_IDS[v[key]],
            "opponent": OPPONENT_KEY[opp[key]],
            "ai_profile": AI_PROFILE,
            "attack": ATTACK_COMPOSED if key in ks else ATTACK_INHERITED,
            "packages": [],
            "schedule": [list(seg) for seg in ks.get(key, ())],
        }
    block: Dict[str, object] = {"version": BLOCK_VERSION, "garages": garages}
    if kit_on(options):
        block["kit"] = {
            "assignment": ASSIGNMENTS[int(options.boss_attack_assignment.value)],
            "intensity": INTENSITY[int(options.boss_attack_intensity.value)][0],
            "loss_easing": bool(options.boss_loss_easing.value),
        }
    if final_on(options):
        sched = final_schedule(options)
        block["final"] = {
            "locations": list(FINAL_LOCATIONS),
            "opponent": OPPONENT_KEY[final_opponent(options)],
            "attack": ATTACK_COMPOSED if sched else ATTACK_INHERITED,
            "schedule": [list(seg) for seg in sched],
        }
    if gauntlet_on(options):
        if world is None:
            raise RuntimeError("CTR: the gauntlet record needs the world for the cup's legs")
        block["gauntlet"] = {"legs": gauntlet_legs(world)}
    return block


def _row_problem(seg, garage_row: bool) -> Optional[str]:
    if (not isinstance(seg, (list, tuple)) or len(seg) != 6
            or any(type(x) is not int for x in seg)):
        return "schedule segment is not six integers"
    _cp, throw, weapon, path, cooldown, juice = seg
    if ((weapon, throw, path, juice) not in CERTIFIED_ROWS
            or not COOLDOWN_MIN <= cooldown <= COOLDOWN_MAX
            or (garage_row and family_of(weapon) in OXIDE_ONLY_FAMILIES)):
        return "schedule segment has a code this build cannot race"
    return None


def _schedule_problem(garage: str, track: str, schedule) -> Optional[str]:
    if not isinstance(schedule, (list, tuple)) or len(schedule) != SEGMENTS:
        return f"schedule must have {SEGMENTS} segments"
    points = bts.VENUES[track]
    prev = -1
    for seg in schedule:
        problem = _row_problem(seg, True)
        if problem:
            return problem
        cp = seg[0]
        if not (prev < cp < points) or (prev < 0 and cp != 0):
            return "schedule checkpoints are not increasing from 0 inside the venue"
        prev = cp
    # The segments start where the garage's retail segments map to on this
    # venue, as `_segments` composes them. Native checks the same.
    if tuple(seg[0] for seg in schedule) != bts.translated_schedule(garage, track):
        return "schedule checkpoints are not the garage's mapped segments"
    if all(seg[2] == 0x0F for seg in schedule):
        return "schedule never attacks"
    return None


def _final_problem(final, opponent_flag: bool, oxide_flag: bool, profile_all: bool,
                   garage_opps: Mapping[str, str]) -> Optional[str]:
    if not isinstance(final, Mapping) or sorted(final) != sorted(FINAL_KEYS):
        return "unexpected fields"
    if (not isinstance(final["locations"], (list, tuple))
            or [type(c) for c in final["locations"]] != [int, int]
            or tuple(final["locations"]) != FINAL_LOCATIONS):
        return "locations must be N. Oxide's two races"
    opp = _OPPONENT_BY_KEY.get(final["opponent"]) if isinstance(final["opponent"], str) else None
    if opp is None:
        return "unknown opponent"
    if oxide_flag:
        if opp == OXIDE_NAME or opp in garage_opps.values():
            return "opponent must be a racer other than N. Oxide and the four garage racers"
    elif opp != OXIDE_NAME:
        return "opponent moved without boss_oxide_in_pool"
    schedule = final["schedule"]
    if profile_all:
        if final["attack"] != ATTACK_COMPOSED or not isinstance(schedule, (list, tuple)) \
                or len(schedule) != OXIDE_SEGMENTS:
            return f"all_compatible needs a composed {OXIDE_SEGMENTS}-segment schedule"
        for seg in schedule:
            problem = _row_problem(seg, False)
            if problem:
                return problem
        if tuple(seg[0] for seg in schedule) != OXIDE_CHECKPOINTS:
            return "schedule checkpoints are not N. Oxide's retail segments"
        if all(seg[2] == 0x0F for seg in schedule):
            return "schedule never attacks"
    elif final["attack"] != ATTACK_INHERITED or not isinstance(schedule, (list, tuple)) or len(schedule):
        return "attack does not match oxide_attack_profile"
    return None


def _gauntlet_problem(gauntlet, opps: Mapping[str, str],
                      scheds: Mapping[str, Tuple[Segment, ...]]) -> Optional[str]:
    if not isinstance(gauntlet, Mapping) or sorted(gauntlet) != ["legs"]:
        return "unexpected fields"
    legs = gauntlet["legs"]
    if not isinstance(legs, (list, tuple)) or len(legs) != GAUNTLET_LEGS:
        return f"legs must be {GAUNTLET_LEGS}"
    for i, key in enumerate(_garage_keys()):
        leg = legs[i]
        if not isinstance(leg, Mapping) or sorted(leg) != sorted(GAUNTLET_LEG_KEYS):
            return f"leg {i} has unexpected fields"
        if leg["attacker"] != OPPONENT_KEY[opps[key]]:
            return f"leg {i} attacker is not {key}'s racer"
        track_id, schedule = leg["track"], leg["schedule"]
        if type(track_id) is not int or not isinstance(schedule, (list, tuple)):
            return f"leg {i} is malformed"
        if track_id == -1:
            if len(schedule):
                return f"leg {i} has no track but a schedule"
            continue
        track = bts._VENUE_BY_LEVEL_ID.get(track_id)
        if track is None or not bts.inherited_attack_certified(key, track):
            return f"leg {i} track this build cannot race"
        problem = _schedule_problem(key, track, schedule)
        if problem:
            return f"leg {i}: {problem}"
        if [list(seg[1:]) for seg in schedule] != [list(seg[1:]) for seg in scheds[key]]:
            return f"leg {i} kit is not {key}'s kit"
    return None


def parse_wire(block, opponent_flag: bool, kit_flag: bool, oxide_flag: bool = False,
               gauntlet_flag: bool = False, profile_all: bool = False):
    """Validate a version 2 `boss_encounters` block against the switch
    scalars. Returns ({garage -> track}, {garage -> opponent name},
    {garage -> schedule}, kit record or None, final opponent name, final
    schedule). Raises ValueError on anything this build would not emit."""
    if (not isinstance(block, Mapping) or type(block.get("version")) is not int
            or block["version"] != BLOCK_VERSION):
        raise ValueError("boss_encounters: version 2 block expected")
    if oxide_flag and not opponent_flag:
        raise ValueError("boss_encounters: boss_oxide_in_pool without boss_opponent_shuffle")
    if gauntlet_flag and not kit_flag:
        raise ValueError("boss_encounters: purple_cup_boss_gauntlet without boss_kit_shuffle")
    final_flag = oxide_flag or profile_all
    want = ("version", "garages") + (("kit",) if kit_flag else ()) \
        + (("final",) if final_flag else ()) + (("gauntlet",) if gauntlet_flag else ())
    if sorted(block) != sorted(want):
        raise ValueError("boss_encounters: unexpected top-level fields")
    rows = block.get("garages")
    keys = _garage_keys()
    if not isinstance(rows, Mapping) or sorted(rows) != sorted(keys):
        raise ValueError("boss_encounters: garages must be exactly " + ", ".join(keys))
    tracks: Dict[str, str] = {}
    opps: Dict[str, str] = {}
    scheds: Dict[str, Tuple[Segment, ...]] = {}
    for key, _region, code, home in bts.GARAGES:
        row = rows[key]
        if not isinstance(row, Mapping) or sorted(row) != sorted(ROW_KEYS):
            raise ValueError(f"boss_encounters.{key}: unexpected fields")
        track = bts._VENUE_BY_LEVEL_ID.get(row["track"]) if type(row["track"]) is int else None
        opp = _OPPONENT_BY_KEY.get(row["opponent"]) if isinstance(row["opponent"], str) else None
        if track is None or opp is None:
            raise ValueError(f"boss_encounters.{key}: unknown track or opponent")
        if (type(row["location"]) is not int or type(row["home_track"]) is not int
                or row["location"] != code or row["home_track"] != bts.VENUE_LEVEL_IDS[home]
                or row["ai_profile"] != AI_PROFILE
                or not isinstance(row["packages"], (list, tuple)) or len(row["packages"])
                or not bts.inherited_attack_certified(key, track)
                or (not opponent_flag and opp != GARAGE_BOSS[key])
                or (opp == OXIDE_NAME and not oxide_flag)):
            raise ValueError(f"boss_encounters.{key}: record this build cannot race")
        if row["attack"] == ATTACK_COMPOSED and kit_flag:
            problem = _schedule_problem(key, track, row["schedule"])
            if problem:
                raise ValueError(f"boss_encounters.{key}: {problem}")
            scheds[key] = tuple(tuple(seg) for seg in row["schedule"])
        elif (row["attack"] != ATTACK_INHERITED or kit_flag
              or not isinstance(row["schedule"], (list, tuple)) or len(row["schedule"])):
            raise ValueError(f"boss_encounters.{key}: attack does not match boss_kit_shuffle")
        tracks[key] = track
        opps[key] = opp
    # Bosses never repeat (decision 7 of 2026-10-28).
    if len(set(opps.values())) != len(keys):
        raise ValueError("boss_encounters: two garages race the same racer")
    if len(set(tracks.values())) != len(keys):
        raise ValueError("boss_encounters: two garages race on the same track")
    kit = None
    if kit_flag:
        kit = block["kit"]
        if (not isinstance(kit, Mapping) or sorted(kit) != sorted(KIT_KEYS)
                or kit["assignment"] not in ASSIGNMENTS
                or kit["intensity"] not in [n for n, _a, _b in INTENSITY]
                or type(kit["loss_easing"]) is not bool):
            raise ValueError("boss_encounters.kit: unexpected record")
    final_opp, final_sched = OXIDE_NAME, ()
    if final_flag:
        problem = _final_problem(block["final"], opponent_flag, oxide_flag, profile_all, opps)
        if problem:
            raise ValueError(f"boss_encounters.final: {problem}")
        final_opp = _OPPONENT_BY_KEY[block["final"]["opponent"]]
        final_sched = tuple(tuple(seg) for seg in block["final"]["schedule"])
    if gauntlet_flag:
        problem = _gauntlet_problem(block["gauntlet"], opps, scheds)
        if problem:
            raise ValueError(f"boss_encounters.gauntlet: {problem}")
    return tracks, opps, scheds, kit, final_opp, final_sched


def _flag(co: Mapping, name: str) -> bool:
    value = co.get(name, False)
    if type(value) is not bool:
        raise ValueError(f"ctr_options.{name} must be a boolean")
    return value


def restore_from_wire(world, passthrough: Mapping) -> None:
    """Universal Tracker: pin the connected seed's encounters; never redraw.
    The always-emitted `ctr_options` scalars are the switches (an older seed
    without a scalar reads it as off or retail)."""
    o = world.options
    co = passthrough.get("ctr_options", {}) or {}
    opp_flag = _flag(co, "boss_opponent_shuffle")
    kit_flag = _flag(co, "boss_kit_shuffle")
    oxide_flag = _flag(co, "boss_oxide_in_pool")
    gauntlet_flag = _flag(co, "purple_cup_boss_gauntlet")
    profile = co.get("oxide_attack_profile", "retail")
    if profile not in ("retail", "all_compatible"):
        raise ValueError("ctr_options.oxide_attack_profile must be retail or all_compatible")
    profile_all = profile == "all_compatible"
    o.boss_oxide_in_pool.value = int(oxide_flag)
    o.purple_cup_boss_gauntlet.value = int(gauntlet_flag)
    o.oxide_attack_profile.value = int(profile_all)
    o.oxide_powerup_blocklist.value = set()
    if not (opp_flag or kit_flag or oxide_flag or profile_all or gauntlet_flag):
        o.boss_opponent_shuffle.value = 0
        o.boss_kit_shuffle.value = 0
        _clear_subordinates(o)
        bts.restore_from_wire(world, passthrough)
        o._boss_opponents = dict(GARAGE_BOSS)
        o._boss_kits = {}
        o._boss_final_opponent = OXIDE_NAME
        o._boss_final_schedule = ()
        return
    track_flag = _flag(co, "boss_track_shuffle")
    block = passthrough.get("boss_encounters")
    if block is None:
        raise ValueError("boss_encounters missing with a version 2 switch on")
    tracks, opps, scheds, kit, final_opp, final_sched = parse_wire(
        block, opp_flag, kit_flag, oxide_flag, gauntlet_flag, profile_all)
    if not track_flag and tracks != bts.retail_venues():
        raise ValueError("boss_encounters: a venue moved with boss_track_shuffle off")
    o.boss_track_shuffle.value = int(track_flag)
    o.boss_opponent_shuffle.value = int(opp_flag)
    o.boss_kit_shuffle.value = int(kit_flag)
    o.boss_track_allowlist.value = set()
    o.boss_track_blocklist.value = set()
    _clear_subordinates(o)
    if kit is not None:
        o.boss_attack_assignment.value = ASSIGNMENTS.index(kit["assignment"])
        o.boss_attack_intensity.value = [n for n, _a, _b in INTENSITY].index(kit["intensity"])
        o.boss_loss_easing.value = int(kit["loss_easing"])
    o._boss_track_venues = tracks if track_flag else dict(bts.retail_venues())
    o._boss_opponents = opps
    o._boss_kits = scheds
    o._boss_final_opponent = final_opp
    o._boss_final_schedule = final_sched


def _clear_subordinates(o) -> None:
    # The filters shaped the draw only; the pinned record is the answer.
    # Reset them so the tracker's own YAML cannot add notices or errors.
    o.boss_character_allowlist.value = set()
    o.boss_character_blocklist.value = set()
    o.boss_track_assignment.value = 0
    o.boss_attack_assignment.value = 0
    o.boss_attack_intensity.value = 1
    o.boss_loss_easing.value = 1
    o.boss_powerup_blocklist.value = set()


def spoiler_lines(options) -> Iterable[str]:
    if not any_on(options):
        return ()
    v = bts.venues(options)
    opp = opponents(options)
    ks = kits(options)
    lines = []
    for key, region, _c, _h in bts.GARAGES:
        parts = [v[key]]
        if opponent_on(options):
            parts.append(f"vs {opp[key]}")
        if key in ks:
            parts.append(f"kit: {kit_label(ks[key])}")
        lines.append(f"{region}: " + ", ".join(parts))
    if final_on(options):
        parts = [f"vs {final_opponent(options)}"]
        if oxide_profile_all(options):
            parts.append(f"kit: {kit_label(final_schedule(options))}")
        lines.append(f"{bts.OXIDE_GARAGE}: " + ", ".join(parts))
    if gauntlet_on(options):
        lines.append(f"{PURPLE_CUP}: boss gauntlet, leg attackers "
                     + ", ".join(opp[k] for k in _garage_keys()))
    return tuple(lines)
