"""Boss opponent and kit shuffle (#169 tiers 2 and 3, 0.3.0, schema 18).

Design: the 0.3.0 #169 design with independent switches, ruled 2026-10-13,
and the random character boss battles Wayfinder note (2026-09-01). Tier 1,
the track switch, is `boss_track_shuffle`; this module adds the opponent and
kit switches and owns the combined `boss_encounters` record.

WHAT THE OPTIONS DO. Three Toggles, all off by default, any combination:

  * `boss_track_shuffle` (tier 1): the garage races on a drawn venue.
  * `boss_opponent_shuffle` (tier 2): the garage races a drawn racer. The
    pool (`POOL`, built so custom characters can join later) is
    `boss_character_pool`, by default the 15 retail racers other than N. Oxide.
    With N. Oxide listed (decision 7 of 2026-10-28) N. Oxide's own garage (both races) also races a drawn racer other than N. Oxide, and
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
    `boss_weapon_pool` holds the families.
  * `purple_cup_boss_gauntlet` (needs the kit switch): each Purple Gem Cup
    leg arms garage i's racer with garage i's kit on that leg's track.
  * `oxide_attack_profile: all_compatible` (independent of the switches):
    N. Oxide's garage gets a composed 13-segment profile from every family,
    the Super Engine included, as `oxide_weapon_pool` allows.

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

THE DRAW lives in content_bosses.py: this module holds the tables, pools and
kit helpers the plan draws from. Nothing here runs on a seed without
a content plan. Encounters never repeat (decision 7): four distinct venues,
opponents (five with N. Oxide's garage) and kits; the whole assignment is
tested, so impossible filters fail generation.

LOGIC. Kits do not change reachability (design: enemy weapons are not
player unlocks). The opponent changes the Hit Character checks (decision 9):
content_bosses.identity feeds the Hit block's `bosses` table and its unlock
triggers, so a boss-race Hit route follows the drawn racer and beating a garage
unlocks the drawn racer as an opponent in other races.
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
#: The default `boss_character_pool`: the pool without N. Oxide.
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


def opponent_on(options) -> bool:
    return bool(getattr(options, "boss_opponent_shuffle", None)
                and options.boss_opponent_shuffle.value)


def kit_on(options) -> bool:
    return bool(getattr(options, "boss_kit_shuffle", None)
                and options.boss_kit_shuffle.value)


def oxide_in_pool(options) -> bool:
    """N. Oxide listed in `boss_character_pool`: only with opponent shuffle on
    (decision 7 of 2026-10-28)."""
    return opponent_on(options) and OXIDE_NAME in options.boss_character_pool.value


def oxide_profile_all(options) -> bool:
    return bool(getattr(options, "oxide_attack_profile", None)
                and int(options.oxide_attack_profile.value) == 1)


def gauntlet_on(options) -> bool:
    """`purple_cup_boss_gauntlet`, only with the kit switch. The plan refuses
    it without the switch or the Purple Gem Cup (content_plan.generate)."""
    return kit_on(options) and bool(options.purple_cup_boss_gauntlet.value)


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

def opponent_pool(options) -> List[str]:
    """`boss_character_pool` in pool order. N. Oxide only when it lists him
    (decision 7)."""
    return [n for n in POOL_NAMES if n in options.boss_character_pool.value]


def final_pool(options) -> List[str]:
    """Racers N. Oxide's garage may draw: the garage pool without N. Oxide
    ("then the final boss should be different", decision 7)."""
    return [n for n in opponent_pool(options) if n != OXIDE_NAME]


def allowed_families(options) -> List[str]:
    """Garage and gauntlet families of `boss_weapon_pool`."""
    return [f for f in GARAGE_FAMILIES if f in options.boss_weapon_pool.value]


def oxide_families(options) -> List[str]:
    """N. Oxide's `all_compatible` families of `oxide_weapon_pool` (Wayfinder
    D2a: independent of `boss_weapon_pool`)."""
    return [f for f in FAMILIES if f in options.oxide_weapon_pool.value]


def allowed_signatures(options) -> List[str]:
    """Retail profiles whose weapons are all in `boss_weapon_pool`."""
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


def _mixed_rows(rng, families: Sequence[str], segments: int = SEGMENTS,
                low: int = MIX_MIN, high: int = MIX_MAX):
    k = rng.randint(min(low, len(families)), min(high, len(families)))
    chosen = rng.sample(list(families), k)
    order = chosen + [rng.choice(chosen) for _ in range(segments - k)]
    rng.shuffle(order)
    return tuple(rng.choice(FAMILY_VARIANTS[f]) for f in order)


def _intensity(options) -> int:
    return int(options.boss_attack_intensity.value) if kit_on(options) else 1


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


def kit_label(schedule: Iterable[Segment]) -> str:
    fams = []
    for seg in schedule:
        f = family_of(seg[2])
        if f and f not in fams:
            fams.append(f)
    return ", ".join(fams)


# -------------------------------------------------------------------- gauntlet

PURPLE_CUP = "Purple Gem Cup"


# ------------------------------------------------------------------------ wire

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


def _clear_subordinates(o) -> None:
    # The filters shaped the draw only; the pinned record is the answer.
    # Reset them so the tracker's own YAML cannot add notices or errors.
    o.boss_character_pool.value = set(OPPONENT_NAMES)
    o.boss_track_assignment.value = 0
    o.boss_attack_assignment.value = 0
    o.boss_attack_intensity.value = 1
    o.boss_loss_easing.value = 1
    o.boss_weapon_pool.value = set(GARAGE_FAMILIES)


