"""Boss opponent and kit shuffle (#169 tiers 2 and 3, 0.3.0, schema 18).

Design: the 0.3.0 #169 design with independent switches, ruled 2026-10-13,
and the random character boss battles Wayfinder note (2026-09-01). Tier 1,
the track switch, is `boss_track_shuffle`; this module adds the opponent and
kit switches and owns the combined `boss_encounters` record.

WHAT THE OPTIONS DO. Three Toggles, all off by default, any combination:

  * `boss_track_shuffle` (tier 1): the garage races on a drawn venue.
  * `boss_opponent_shuffle` (tier 2): the garage races a drawn racer. The
    pool is the 15 retail racers other than N. Oxide (the Wayfinder rules
    keep Oxide outside the four ordinary garages), narrowed by
    `boss_character_allowlist` (empty = no narrowing) and then
    `boss_character_blocklist`. With track shuffle off the venue stays the
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

Every garage keeps its physical identity: the `<Boss> Garage: Boss Race`
check and code, the Key, the door requirement, the personal-win event, the
loss counter and the boss-grade driving table of the physical garage
(`ai_profile: retail`, native `data.BossDifficulty[bossID]`). So a swapped
racer drives with the garage's boss-grade profile, scaled by the client's
global AI setting as before. N. Oxide's two encounters and the Purple Gem
Cup are not part of any draw.

WEAPON FAMILIES. The certified families are the four projectile weapons the
retail boss attack path (`PickupBots_UpdateBoss`) fires through
`VehPickupItem_ShootNow`: TNT, potion, bomb and missile. TNT, potion and
bomb segments copy rows of the retail `data.BossWeapon*` tables exactly
(weapon code, throw direction, path-change flag, cooldown, juice pattern).
The missile segment is the bomb row with the missile item; retail arcade AI
fires missiles on every race track. Every family is therefore certified on
every one of the 18 boss venues. The other families of the full suite
(shield, mask, clock, warp orb, invisibility, super engine, turbo) need
their own boss adapters and are not built.

SCHEDULE SHAPE. A composed schedule has the same five checkpoint-keyed
segments as the garage's retail schedule, at the same relative lap
positions (`boss_track_shuffle.translated_schedule`), so a venue that
carries the inherited attack also carries a composed one; the same
certification applies.

THE DRAW. Once in `generate_early` (`draw`), pinned from the wire under
Universal Tracker (`restore_from_wire`). Native never redraws. With both new
switches off nothing here draws, so a tier 1 seed keeps its RNG stream and
its version 1 wire block exactly. `boss_encounter_repeats: disallow` needs
four distinct opponents and four distinct kits; the whole assignment is
tested, so impossible filters fail generation instead of repeating.

LOGIC. Opponent and kit do not change reachability (design: enemy weapons
are not player unlocks). The only logic effect is a venue moved by the
home-track pairing, which goes through the same `_boss_track_venues` table
tier 1 uses: the boss win's finish term and the garage's Wumpa route.
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

#: Racers a garage may draw: the roster without N. Oxide.
OPPONENT_NAMES: Tuple[str, ...] = tuple(
    name for name in ROSTER_CHARACTER_ID if name != "Nitros Oxide")
#: {roster name -> wire key}. The four bosses' keys are the garage keys.
OPPONENT_KEY: Dict[str, str] = {name: _option_key(name) for name in OPPONENT_NAMES}
_OPPONENT_BY_KEY: Dict[str, str] = {k: n for n, k in OPPONENT_KEY.items()}
#: {garage key -> its own boss's roster name}.
GARAGE_BOSS: Dict[str, str] = {
    "ripper_roo": "Ripper Roo", "papu_papu": "Papu Papu",
    "komodo_joe": "Komodo Joe", "pinstripe": "Pinstripe"}
assert all(OPPONENT_KEY[name] == key for key, name in GARAGE_BOSS.items())

AI_PROFILE = "retail"
ATTACK_INHERITED = bts.ATTACK_INHERITED
ATTACK_COMPOSED = "composed"

#: Retail `MetaDataBOSS` codes. Weapon: 0x01 bomb, 0x02 missile, 0x03 TNT,
#: 0x04 potion, 0x64 TNT and 0x66 potion with the boss juice cycle, 0x0f
#: none. Throw: 2 forward, 3 dropped or normal. Juice: 0 none, 1 juiced,
#: 2 alternating.
WEAPON_CODES = (0x01, 0x02, 0x03, 0x04, 0x0F, 0x64, 0x66)
THROW_CODES = (2, 3)
JUICE_CODES = (0, 1, 2)
COOLDOWN_MIN, COOLDOWN_MAX = 2, 0xFF
SEGMENTS = len(bts.RETAIL_ATTACK_CHECKPOINTS["ripper_roo"])

#: Certified weapon families: their segment variants (weapon, throw, path
#: change disabled, cooldown, juice), each a retail row unless noted.
FAMILY_VARIANTS: Dict[str, Tuple[Tuple[int, int, int, int, int], ...]] = {
    "tnt": ((0x03, 3, 0, 0x0F, 0),     # data.BossWeaponRoo: dropped TNT
            (0x64, 2, 0, 0x11, 2)),    # data.BossWeaponJoe: thrown TNT
    "potion": ((0x66, 2, 1, 0x0C, 2),  # data.BossWeaponPapu: thrown potion
               (0x04, 2, 1, 0x0C, 1)),  # data.BossWeaponOxide: juiced potion
    "bomb": ((0x01, 3, 1, 0x0F, 0),    # data.BossWeaponPinstripe
             (0x01, 3, 1, 0x0C, 0)),   # data.BossWeaponOxide
    "missile": ((0x02, 3, 1, 0x0F, 0),),  # the bomb row with the missile item
}
FAMILIES: Tuple[str, ...] = tuple(FAMILY_VARIANTS)
#: Weapon code -> family, for a schedule read back from the wire.
WEAPON_FAMILY: Dict[int, str] = {0x01: "bomb", 0x02: "missile", 0x03: "tnt", 0x64: "tnt",
                                 0x04: "potion", 0x66: "potion"}
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


def any_on(options) -> bool:
    return bts.enabled(options) or opponent_on(options) or kit_on(options)


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
    on still stop generation (see `draw`)."""
    o = world.options
    from .notices import note_ignored
    if not opponent_on(o):
        for name, label in (("boss_character_allowlist", "Boss Character Allowlist"),
                            ("boss_character_blocklist", "Boss Character Blocklist")):
            if getattr(o, name).value:
                note_ignored(world, f"{label} (Boss Opponent Shuffle off)")
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


def opponent_pool(options) -> List[str]:
    """Roster names, `all_compatible` narrowed by the allowlist, then the
    blocklist."""
    allow = set(options.boss_character_allowlist.value)
    block = set(options.boss_character_blocklist.value)
    return [n for n in OPPONENT_NAMES if (not allow or n in allow) and n not in block]


def allowed_families(options) -> List[str]:
    block = set(options.boss_powerup_blocklist.value)
    return [f for f in FAMILIES if f not in block]


def allowed_signatures(options) -> List[str]:
    """Retail profiles whose weapons all survive the blocklist."""
    fams = set(allowed_families(options))
    return [key for key, rows in SIGNATURES.items()
            if all(family_of(r[0]) in fams for r in rows if r[0] != 0x0F)]


# ------------------------------------------------------------------------ draw

def _feasible_distinct(pools: Sequence[Sequence[str]]) -> bool:
    """Is there a pick of one value per pool, all different? (Four pools of
    at most 18 values: plain backtracking.)"""
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
    """Resolve and freeze the four garage encounters on `world.options`.

    Runs the tier 1 venue draw unchanged unless the home-track pairing owns
    the venues, then the opponent draw, then the kit draw. A switch that is
    off draws nothing. Results: `_boss_track_venues` (tier 1's table),
    `_boss_opponents` {garage -> roster name} and `_boss_kits` {garage ->
    tuple of segments}."""
    o = world.options
    validate_options(world)
    keys = _garage_keys()
    repeats = int(o.boss_encounter_repeats.value) == 1
    if home_pairing(o):
        bts.validate_options(world)
        _draw_home_paired(world, keys, repeats)
    else:
        bts.draw(world)
        if opponent_on(o):
            _draw_opponents(world, keys, repeats, {k: opponent_pool(o) for k in keys})
        else:
            o._boss_opponents = dict(GARAGE_BOSS)
    if kit_on(o):
        _draw_kits(world, keys, repeats)
    else:
        o._boss_kits = {}


def _draw_opponents(world, keys, repeats, pools) -> None:
    o = world.options
    for key, region, _c, _h in bts.GARAGES:
        if not pools[key]:
            raise OptionError(
                f"CTR ({_who(world)}): boss_opponent_shuffle has no racer left for "
                f"{region} after boss_character_allowlist and boss_character_blocklist.")
    if repeats:
        picked = [world.random.choice(pools[k]) for k in keys]
    else:
        picked = _distinct_draw(world.random, [pools[k] for k in keys])
        if picked is None:
            raise OptionError(
                f"CTR ({_who(world)}): boss_opponent_shuffle cannot give the four boss "
                "garages four different racers from the allowed pool ("
                + ", ".join(opponent_pool(o)) + "). Allow more racers or set "
                "boss_encounter_repeats: allow.")
    o._boss_opponents = dict(zip(keys, picked))


def _draw_home_paired(world, keys, repeats) -> None:
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
    _draw_opponents(world, keys, repeats, pools)
    o._boss_track_venues = {k: HOME_TRACK[o._boss_opponents[k]] for k in keys}


def _segments(garage: str, track: str, rows, intensity: int) -> Tuple[Segment, ...]:
    checkpoints = bts.translated_schedule(garage, track)
    return tuple((cp, throw, weapon, path, scale_cooldown(cooldown, intensity), juice)
                 for cp, (weapon, throw, path, cooldown, juice) in zip(checkpoints, rows))


def _mixed_rows(rng, families: Sequence[str]):
    k = rng.randint(MIX_MIN, min(MIX_MAX, len(families)))
    chosen = rng.sample(list(families), k)
    order = chosen + [rng.choice(chosen) for _ in range(SEGMENTS - k)]
    rng.shuffle(order)
    return tuple(rng.choice(FAMILY_VARIANTS[f]) for f in order)


def _draw_kits(world, keys, repeats) -> None:
    o = world.options
    venues = bts.venues(o)
    intensity = int(o.boss_attack_intensity.value)
    kits: Dict[str, Tuple[Segment, ...]] = {}
    if int(o.boss_attack_assignment.value) == 1:
        profiles = allowed_signatures(o)
        if not profiles:
            raise OptionError(
                f"CTR ({_who(world)}): boss_attack_assignment: signature_profiles has no retail "
                "boss profile left after boss_powerup_blocklist.")
        if repeats:
            picked = [world.random.choice(profiles) for _ in keys]
        else:
            if len(profiles) < len(keys):
                raise OptionError(
                    f"CTR ({_who(world)}): boss_attack_assignment: signature_profiles needs four "
                    "different retail profiles, but boss_powerup_blocklist leaves "
                    + ", ".join(profiles) + ". Unblock weapons or set boss_encounter_repeats: allow.")
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
            # Distinct mixes by default (Wayfinder D1). Thousands of mixes
            # exist for any two families, so the bound is never reached in
            # practice; it only keeps the loop finite.
            tries = 0
            while not repeats and tuple(r[0] for r in rows) in seen:
                tries += 1
                if tries > 1000:
                    raise OptionError(f"CTR ({_who(world)}): could not draw four different boss kits.")
                rows = _mixed_rows(world.random, families)
            seen.add(tuple(r[0] for r in rows))
            kits[key] = _segments(key, venues[key], rows, intensity)
    o._boss_kits = kits


def opponents(options) -> Dict[str, str]:
    """{garage key -> opponent roster name} for this seed."""
    if not opponent_on(options):
        return dict(GARAGE_BOSS)
    resolved = getattr(options, "_boss_opponents", None)
    if resolved is None:
        raise RuntimeError("CTR: boss opponents read before boss_encounters.draw")
    return dict(resolved)


def kits(options) -> Dict[str, Tuple[Segment, ...]]:
    """{garage key -> composed schedule}; empty with kit shuffle off."""
    if not kit_on(options):
        return {}
    resolved = getattr(options, "_boss_kits", None)
    if resolved is None:
        raise RuntimeError("CTR: boss kits read before boss_encounters.draw")
    return dict(resolved)


def kit_label(schedule: Iterable[Segment]) -> str:
    fams = []
    for seg in schedule:
        f = family_of(seg[2])
        if f and f not in fams:
            fams.append(f)
    return ", ".join(fams)


# ------------------------------------------------------------------------ wire

def wire_block(options) -> Optional[Dict[str, object]]:
    """The `boss_encounters` slot_data block: None with every switch off,
    tier 1's version 1 block with only the track switch on, else version 2:
    four complete rows keyed by physical garage, each with a `schedule`
    (empty for the inherited attack), plus a `kit` record with kit shuffle
    on."""
    if not any_on(options):
        return None
    if not (opponent_on(options) or kit_on(options)):
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
    return block


def _schedule_problem(garage: str, track: str, schedule) -> Optional[str]:
    if not isinstance(schedule, (list, tuple)) or len(schedule) != SEGMENTS:
        return f"schedule must have {SEGMENTS} segments"
    points = bts.VENUES[track]
    prev = -1
    for seg in schedule:
        if (not isinstance(seg, (list, tuple)) or len(seg) != 6
                or any(type(x) is not int for x in seg)):
            return "schedule segment is not six integers"
        cp, throw, weapon, path, cooldown, juice = seg
        if not (prev < cp < points) or (prev < 0 and cp != 0):
            return "schedule checkpoints are not increasing from 0 inside the venue"
        if ((weapon, throw, path, juice) not in CERTIFIED_ROWS
                or not COOLDOWN_MIN <= cooldown <= COOLDOWN_MAX):
            return "schedule segment has a code this build cannot race"
        prev = cp
    if all(seg[2] == 0x0F for seg in schedule):
        return "schedule never attacks"
    return None


def parse_wire(block, opponent_flag: bool, kit_flag: bool) -> Tuple[
        Dict[str, str], Dict[str, str], Dict[str, Tuple[Segment, ...]], Optional[Dict[str, object]]]:
    """Validate a version 2 `boss_encounters` block against the two switch
    scalars. Returns ({garage -> track}, {garage -> opponent name},
    {garage -> schedule}, kit record or None). Raises ValueError on anything
    this build would not emit."""
    if (not isinstance(block, Mapping) or type(block.get("version")) is not int
            or block["version"] != BLOCK_VERSION):
        raise ValueError("boss_encounters: version 2 block expected")
    if sorted(block) != sorted(("version", "garages") + (("kit",) if kit_flag else ())):
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
                or (not opponent_flag and opp != GARAGE_BOSS[key])):
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
    kit = None
    if kit_flag:
        kit = block["kit"]
        if (not isinstance(kit, Mapping) or sorted(kit) != sorted(KIT_KEYS)
                or kit["assignment"] not in ASSIGNMENTS
                or kit["intensity"] not in [n for n, _a, _b in INTENSITY]
                or type(kit["loss_easing"]) is not bool):
            raise ValueError("boss_encounters.kit: unexpected record")
    return tracks, opps, scheds, kit


def restore_from_wire(world, passthrough: Mapping) -> None:
    """Universal Tracker: pin the connected seed's encounters; never redraw.
    The three always-emitted `ctr_options` scalars are the switches (an
    older tier 1 seed has no opponent or kit scalar: both off)."""
    o = world.options
    co = passthrough.get("ctr_options", {}) or {}
    opp_flag = co.get("boss_opponent_shuffle", False)
    kit_flag = co.get("boss_kit_shuffle", False)
    if type(opp_flag) is not bool or type(kit_flag) is not bool:
        raise ValueError("ctr_options.boss_opponent_shuffle and boss_kit_shuffle must be booleans")
    if not (opp_flag or kit_flag):
        o.boss_opponent_shuffle.value = 0
        o.boss_kit_shuffle.value = 0
        _clear_subordinates(o)
        bts.restore_from_wire(world, passthrough)
        o._boss_opponents = dict(GARAGE_BOSS)
        o._boss_kits = {}
        return
    track_flag = co.get("boss_track_shuffle", False)
    if type(track_flag) is not bool:
        raise ValueError("ctr_options.boss_track_shuffle must be a boolean")
    block = passthrough.get("boss_encounters")
    if block is None:
        raise ValueError("boss_encounters missing with an opponent or kit switch on")
    tracks, opps, scheds, kit = parse_wire(block, opp_flag, kit_flag)
    if not track_flag and tracks != bts.retail_venues():
        raise ValueError("boss_encounters: a venue moved with boss_track_shuffle off")
    o.boss_track_shuffle.value = int(track_flag)
    o.boss_opponent_shuffle.value = int(opp_flag)
    o.boss_kit_shuffle.value = int(kit_flag)
    o.boss_track_allowlist.value = set()
    o.boss_track_blocklist.value = set()
    o.boss_encounter_repeats.value = 0
    _clear_subordinates(o)
    if kit is not None:
        o.boss_attack_assignment.value = ASSIGNMENTS.index(kit["assignment"])
        o.boss_attack_intensity.value = [n for n, _a, _b in INTENSITY].index(kit["intensity"])
        o.boss_loss_easing.value = int(kit["loss_easing"])
    o._boss_track_venues = tracks if track_flag else dict(bts.retail_venues())
    o._boss_opponents = opps
    o._boss_kits = scheds


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
    return tuple(lines)
