"""Hit Character encounter checks and wire block (0.2.1 candidate).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Landing a player-
attributable hit on each of the sixteen racers during an Adventure race. The
signal is a native dispatch event (`BOTS_ChangeState` after the accepted
damage-state transition, `game/BOTS.c`), owned by a later native job; the
apworld owns the names, the option, the AP location codes and the emitted
`hit_character_encounters` wire block. Nothing in this module hooks the race
loop or claims a reachability proof -- it is registration plus wire data.

WHO OWNS THE SEMANTICS. The apworld decides which engine ids exist, how the
deterministic candidate rotation is laid out, and which ordinary destinations
each guest is pinned to. Native owns the actual hit dispatch, the model
loading and the field seating; it never reconstructs the candidate lists from
its own RNG, it consumes the ordered lists this module emits.

DATAPACKAGE STABILITY. This class claims the additive block 35025000, stride 1
in engine-character-id order, and registers all sixteen names UNCONDITIONALLY.
The block sits clear of every existing class block (the highest previously
claimed class code is 35023100). `Hit <canonical name>` reuses
`characters.CHARACTER_ID_TO_NAME`, so the location names can never drift from
the roster the rest of the world uses.

FROZEN-NAME WARNING. These names ride the 0.2.0/0.2.1 datapackage line; after
that bump they are permanent and their ids can never move.

WIRE SHAPE. The top-level `hit_character_encounters` block (schema 1) is
emitted only when the option is enabled. `ctr_options.hit_character` is always
emitted as a boolean, so a tracker can tell "off" from "pre-feature seed". The
candidate lists are fully resolved here, including the deterministic rotation
and the guest pins; native never re-draws them.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from Options import OptionError

from . import characters, progressive_capability
from .location_class import LocationClass

#: Additive location block, stride 1 in engine-character-id order.
HIT_CHARACTER_CODE_BASE = 35025000

#: Wire-block version, independent of the seed's global `schema_version`.
HIT_CHARACTER_SCHEMA = 1

#: Inclusive bounds of the global `ctr_options.schema_version` this apworld
#: accepts for an enabled encounter block. The upper bound is the signed 32-bit
#: integer ceiling native's int32 reader can represent; a larger wire value is
#: refused rather than truncated to something that could activate the wrong
#: feature. Hit Character is global schema 16: it integrated after the Cortex
#: Vortex pad track took 15, so an enabled block needs at least 16.
GLOBAL_SCHEMA_MIN = 16
GLOBAL_SCHEMA_MAX = 2147483647

#: The eight retail Adventure default racers (engine ids 0..7) and the eight
#: guest racers (engine ids 8..15). The split is the engine's own
#: `ADVENTURE_STARTERS` boundary, not the apworld roster order.
DEFAULT_RACER_IDS: Tuple[int, ...] = tuple(range(8))
GUEST_RACER_IDS: Tuple[int, ...] = tuple(range(8, 16))

#: Ordinary destination level ids 0..17 and cup ids 100..104.
TRACK_LEVEL_IDS: Tuple[int, ...] = tuple(range(18))
CUP_IDS: Tuple[int, ...] = (100, 101, 102, 103, 104)

#: Guest pin table, keyed by guest engine id:
#:     (ordinary destination level ids, authoritative any-of AP win codes, kind)
#: The ordinary pins deliberately differ from the retail champion metadata; they
#: are the approved encounter destinations. `kind` describes the authoritative
#: trigger -- a boss win or an ordinary/trial track win.
PIN_GUESTS: Dict[int, Tuple[Tuple[int, ...], Tuple[int, ...], str]] = {
    8: ((7,), (35011103,), "boss"),           # Pinstripe -> Hot Air Skyway
    9: ((5,), (35011101,), "boss"),           # Papu Papu -> Papu's Pyramid
    10: ((6,), (35011100,), "boss"),          # Ripper Roo -> Roo's Tubes
    11: ((1,), (35011102,), "boss"),          # Komodo Joe -> Dragon Mines
    12: ((16, 17), (35016200, 35016201), "track"),   # N. Tropy -> trials
    13: ((2, 12), (35011008, 35011010), "track"),    # Penta -> Blizzard/Polar
    14: ((3, 8), (35011000, 35011003), "track"),     # Fake Crash -> Cove/Sewer
    15: ((13,), (35011104, 35011105), "boss"),       # Oxide -> Oxide Station
}

#: Boss-win AP code -> engine opponent id. The shared appearance identity table;
#: both Oxide win codes map to Oxide. Not a boss loader or randomizer.
BOSS_WIN_OPPONENTS: Dict[int, int] = {
    35011100: 10,  # Ripper Roo Garage: Boss Race
    35011101: 9,   # Papu Papu Garage: Boss Race
    35011102: 11,  # Komodo Joe Garage: Boss Race
    35011103: 8,   # Pinstripe Garage: Boss Race
    35011104: 15,  # N. Oxide Garage: N. Oxide's Challenge
    35011105: 15,  # N. Oxide Garage: N. Oxide's Final Challenge
}

#: `policy` block, verbatim.
POLICY_SELF_CHARACTER = "never_seat_player"


class HitCharacterLocationClass(LocationClass):
    """The sixteen Hit Character checks as a `LocationClass` (#176 shape).

    Global, not per-track: a hit can land wherever you race, so every check
    parents to the world's root `Menu` region exactly as itemsanity does.
    """

    key = "hit_character"
    display_name = "Hit Character Encounters"
    code_blocks = (HIT_CHARACTER_CODE_BASE,)

    #: The AP region every Hit Character check parents to.
    REGION = "Menu"

    def all_locations(self):
        return [
            (self.location_name(cid), HIT_CHARACTER_CODE_BASE + cid, self.REGION)
            for cid in sorted(characters.CHARACTER_ID_TO_NAME)
        ]

    def location_name(self, engine_id: int) -> str:
        """AP location name for an engine character id, e.g. 'Hit N. Tropy'."""
        return f"Hit {characters.CHARACTER_ID_TO_NAME[int(engine_id)]}"

    def created_location_names(self, options):
        """All sixteen checks when the toggle is on, otherwise none."""
        if options is None:
            return []
        toggle = getattr(options, "hit_character", None)
        if toggle is None:
            return []
        value = getattr(toggle, "value", toggle)
        if not bool(value):
            return []
        return list(self.names())


#: The registered Hit Character class. `Locations.py` registers this instance.
HIT_CHARACTER_CLASS = HitCharacterLocationClass()


# ---------------------------------------------------------------------------
# Deterministic resolution
# ---------------------------------------------------------------------------

def enabled(world) -> bool:
    """Whether this seed enables Hit Character encounters."""
    return bool(world.options.hit_character.value)


def _rotate(ids: Tuple[int, ...], offset: int) -> List[int]:
    """Left-rotate `ids` by `offset` places (modulo the list length)."""
    amount = offset % len(ids)
    return list(ids[amount:]) + list(ids[:amount])


def _pinned_guests(level_id: int) -> List[int]:
    """Guest engine ids pinned to an ordinary destination level id, sorted."""
    return sorted(cid for cid, (levels, _codes, _kind) in PIN_GUESTS.items()
                  if level_id in levels)


def _candidate_lists(level_id: int, seed: int) -> Dict[str, List[int]]:
    """The resolved `{base, pinned, reserve}` lists for one destination.

    `base` is the eight default racer ids and `reserve` the eight guest ids,
    each left-rotated by `(seed + level_id) % 8`. The arithmetic is
    mathematical integer addition before the modulo, which is identical to
    uint32 overflow for this modulus. `pinned` carries the guest pin, at most
    one per destination.
    """
    offset = (seed + level_id) % 8
    return {
        "base": _rotate(DEFAULT_RACER_IDS, offset),
        "pinned": _pinned_guests(level_id),
        "reserve": _rotate(GUEST_RACER_IDS, offset),
    }


def build_encounters(seed: int) -> Dict[str, object]:
    """Build the `hit_character_encounters` block for a resolved uint32 seed."""
    locations = {
        str(cid): HIT_CHARACTER_CODE_BASE + cid
        for cid in sorted(characters.CHARACTER_ID_TO_NAME)
    }
    tracks = {str(lid): _candidate_lists(lid, seed) for lid in TRACK_LEVEL_IDS}
    cups = {str(cup): _candidate_lists(cup, seed) for cup in CUP_IDS}
    triggers: Dict[str, Dict[str, object]] = {}
    for guest in GUEST_RACER_IDS:
        _levels, codes, kind = PIN_GUESTS[guest]
        triggers[str(guest)] = {"kind": kind, "any_of": list(codes)}
    bosses = {str(code): opponent
              for code, opponent in sorted(BOSS_WIN_OPPONENTS.items())}
    return {
        "schema": HIT_CHARACTER_SCHEMA,
        "locations": locations,
        "policy": {
            "seed": seed,
            "self_character": POLICY_SELF_CHARACTER,
            "boss_eligible_after_clear": True,
            "guest_slots": 1,
        },
        "tracks": tracks,
        "cups": cups,
        "unlock_triggers": triggers,
        "bosses": bosses,
    }


def resolve_for_generation(world) -> Dict[str, object] | None:
    """Draw the roster seed once, build and cache the block.

    Returns None (and consumes no RNG) when the option is off. A second call
    returns the cached block rather than re-drawing.
    """
    if not enabled(world):
        return None
    cached = getattr(world, "ctr_hit_character_encounters", None)
    if cached is not None:
        return cached
    seed = int(world.random.getrandbits(32))
    world.ctr_hit_character_seed = seed
    block = build_encounters(seed)
    _validate_block(block)
    world.ctr_hit_character_encounters = block
    return block


def slot_data(world) -> Dict[str, object] | None:
    """The top-level `hit_character_encounters` block, or None when disabled.

    A fresh world cached its block in `generate_early`; a Universal Tracker
    re-generation cached the connected seed's block verbatim. The fallback
    build exists only so a caller that skipped `generate_early` still gets the
    deterministic block instead of `None`.
    """
    if not enabled(world):
        return None
    cached = getattr(world, "ctr_hit_character_encounters", None)
    if cached is not None:
        return cached
    return resolve_for_generation(world)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _fail(message: str) -> None:
    raise OptionError(f"CTR hit_character_encounters: {message}")


def _as_mapping(value, label: str) -> Dict[str, object]:
    """Return a JSON object, or refuse a malformed non-mapping.

    `None` reads as an absent object (the legacy shape); anything else that is
    not a `dict` is malformed wire data and raises `OptionError` here rather
    than surfacing an `AttributeError` from a later `.get`.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object, got {type(value).__name__}")
    return value


def _is_uint32(value) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFFFFFF


def _is_positive_code(value) -> bool:
    """A positive AP code, bounded to the unsigned 32-bit wire range."""
    return type(value) is int and 0 < value <= 0xFFFFFFFF


def _validate_engine_list(value, label: str, *, expected_set=None,
                          exact_length=None) -> None:
    if not isinstance(value, list):
        _fail(f"{label} must be a list of engine ids, got {type(value).__name__}")
    if any(type(v) is not int or not 0 <= v <= 15 for v in value):
        _fail(f"{label} must contain only engine ids 0..15")
    if len(set(value)) != len(value):
        _fail(f"{label} contains a duplicate engine id")
    if exact_length is not None and len(value) != exact_length:
        _fail(f"{label} must hold exactly {exact_length} engine ids")
    if expected_set is not None and set(value) != set(expected_set):
        _fail(f"{label} must be a permutation of {sorted(expected_set)}, "
              f"got {value}")


def _validate_lists(entry, label: str, expected_pins) -> None:
    if not isinstance(entry, dict):
        _fail(f"{label} must be an object with base/pinned/reserve lists")
    if set(entry) != {"base", "pinned", "reserve"}:
        _fail(f"{label} must carry exactly base, pinned and reserve")
    _validate_engine_list(entry["base"], f"{label}.base",
                          expected_set=DEFAULT_RACER_IDS, exact_length=8)
    _validate_engine_list(entry["reserve"], f"{label}.reserve",
                          expected_set=GUEST_RACER_IDS, exact_length=8)
    _validate_engine_list(entry["pinned"], f"{label}.pinned")
    if entry["pinned"] != list(expected_pins):
        _fail(f"{label}.pinned must be exactly {list(expected_pins)}, "
              f"got {entry['pinned']}")


def _validate_block(block) -> None:
    """Strictly validate a `hit_character_encounters` block.

    Every structural commitment of the frozen contract is enforced exactly:
    exact integer types (bool is rejected even where it compares equal to 0/1),
    the canonical location mapping, base/reserve permutations of the default
    and guest id sets, the approved per-track pins, empty cup pins, the six
    canonical boss-win keys with engine-id values, and the guest trigger kinds
    and authoritative any-of win-code sets. Valid candidate ORDERING is not
    constrained -- any permutation of the correct sets is accepted and
    preserved verbatim -- so a tracker can round-trip a reordered block.
    """
    if not isinstance(block, dict):
        _fail("block must be an object")
    if set(block) != {"schema", "locations", "policy", "tracks", "cups",
                      "unlock_triggers", "bosses"}:
        _fail("block must carry exactly schema, locations, policy, tracks, "
              "cups, unlock_triggers and bosses")
    schema = block.get("schema")
    if type(schema) is not int or schema != HIT_CHARACTER_SCHEMA:
        _fail(f"unknown schema {schema!r}; expected integer "
              f"{HIT_CHARACTER_SCHEMA}")

    locations = block.get("locations")
    if not isinstance(locations, dict) or set(locations) != {
            str(cid) for cid in range(16)}:
        _fail("locations must map exactly engine ids 0..15 to AP codes")
    codes = []
    for cid in range(16):
        code = locations[str(cid)]
        if type(code) is not int or code != HIT_CHARACTER_CODE_BASE + cid:
            _fail(f"locations[{cid!r}] must be the canonical AP code "
                  f"{HIT_CHARACTER_CODE_BASE + cid}")
        codes.append(code)
    if len(set(codes)) != 16:
        _fail("locations must map to sixteen distinct AP codes")

    policy = block.get("policy")
    if not isinstance(policy, dict):
        _fail("policy must be an object")
    if set(policy) != {"seed", "self_character", "boss_eligible_after_clear",
                       "guest_slots"}:
        _fail("policy must carry exactly seed, self_character, "
              "boss_eligible_after_clear and guest_slots")
    if not _is_uint32(policy.get("seed")):
        _fail("policy.seed must be an unsigned 32-bit integer")
    if policy.get("self_character") != POLICY_SELF_CHARACTER:
        _fail("policy.self_character must be "
              f"{POLICY_SELF_CHARACTER!r}")
    if (type(policy.get("boss_eligible_after_clear")) is not bool
            or policy["boss_eligible_after_clear"] is not True):
        _fail("policy.boss_eligible_after_clear must be true")
    if type(policy.get("guest_slots")) is not int \
            or policy["guest_slots"] != 1:
        _fail("policy.guest_slots must be the integer 1")

    tracks = block.get("tracks")
    if not isinstance(tracks, dict) or set(tracks) != {
            str(lid) for lid in TRACK_LEVEL_IDS}:
        _fail("tracks must map exactly level ids 0..17")
    for lid in TRACK_LEVEL_IDS:
        _validate_lists(tracks[str(lid)], f"tracks[{lid!r}]",
                        _pinned_guests(lid))

    cups = block.get("cups")
    if not isinstance(cups, dict) or set(cups) != {
            str(cup) for cup in CUP_IDS}:
        _fail("cups must map exactly cup ids 100..104")
    for cup in CUP_IDS:
        _validate_lists(cups[str(cup)], f"cups[{cup!r}]", [])

    triggers = block.get("unlock_triggers")
    if not isinstance(triggers, dict) or set(triggers) != {
            str(cid) for cid in GUEST_RACER_IDS}:
        _fail("unlock_triggers must map exactly guest engine ids 8..15")
    for cid in GUEST_RACER_IDS:
        entry = triggers[str(cid)]
        if not isinstance(entry, dict) or set(entry) != {"kind", "any_of"}:
            _fail(f"unlock_triggers[{cid!r}] must carry exactly kind and "
                  "any_of")
        _levels, expected_codes, expected_kind = PIN_GUESTS[cid]
        if entry.get("kind") != expected_kind:
            _fail(f"unlock_triggers[{cid!r}].kind must be {expected_kind!r}")
        any_of = entry.get("any_of")
        if not isinstance(any_of, list) or not any_of:
            _fail(f"unlock_triggers[{cid!r}].any_of must be a non-empty list")
        if any(not _is_positive_code(code) for code in any_of):
            _fail(f"unlock_triggers[{cid!r}].any_of must hold positive "
                  "bounded integer AP codes")
        if len(set(any_of)) != len(any_of):
            _fail(f"unlock_triggers[{cid!r}].any_of contains a duplicate code")
        if set(any_of) != set(expected_codes):
            _fail(f"unlock_triggers[{cid!r}].any_of must be exactly "
                  f"{sorted(expected_codes)}")

    bosses = block.get("bosses")
    canonical_boss_keys = {str(code) for code in BOSS_WIN_OPPONENTS}
    if not isinstance(bosses, dict) or set(bosses) != canonical_boss_keys:
        _fail("bosses must map exactly the six canonical boss-win AP codes "
              f"{sorted(canonical_boss_keys)}")
    for code, opponent in bosses.items():
        if type(opponent) is not int or not 0 <= opponent <= 15:
            _fail(f"bosses[{code!r}] must be an engine id 0..15")


# ---------------------------------------------------------------------------
# Universal Tracker restore
# ---------------------------------------------------------------------------

def restore_from_wire(world, passthrough: Dict[str, object]) -> None:
    """Pin the connected seed's Hit Character block instead of re-drawing.

    The scalar, the global schema and the block must agree, and every malformed
    shape is refused rather than silently re-rolled:

      * an enabled scalar with no block is a contradiction (a fresh enabled
        seed always emits the block);
      * a false or absent scalar with ANY present block -- including an
        explicit null -- is a contradiction;
      * an enabled feature whose global `ctr_options.schema_version` is
        missing, a non-integer/bool, below the schema-16 boundary, or above the
        signed 32-bit ceiling native's int32 reader can represent is refused:
        the native legacy early return would otherwise admit the scalar while
        ignoring the block, so the apworld refuses instead of accepting a block
        that can never be activated or one that a truncating reader could
        misread. An integer global schema in 16..2147483647 is accepted as long
        as the block's own known version 1 validates;
      * a present block with an unknown schema or a malformed shape is refused.

    A pre-feature wire (neither scalar nor block) restores to off, which is the
    correct reading of a seed that has no encounters, regardless of the global
    schema. `ctr_options.hit_character`, when present, must be an actual JSON
    boolean. The restored block is kept verbatim: no seed and no array is
    redrawn. Any previously cached block is cleared before validation so a
    refused restore never leaves a stale valid seed active.
    """
    world.ctr_hit_character_encounters = None
    world.ctr_hit_character_seed = None

    passthrough = _as_mapping(passthrough, "slot_data passthrough")
    co = _as_mapping(passthrough.get("ctr_options"), "ctr_options")

    scalar_present = "hit_character" in co
    raw_scalar = co.get("hit_character")
    if scalar_present and type(raw_scalar) is not bool:
        raise OptionError(
            "CTR hit_character_encounters: ctr_options.hit_character must be "
            f"a boolean, got {type(raw_scalar).__name__}.")
    enabled = raw_scalar is True

    if "hit_character_encounters" not in passthrough:
        if enabled:
            raise OptionError(
                "CTR hit_character_encounters: this seed reports "
                "ctr_options.hit_character enabled but carries no "
                "hit_character_encounters block. Refusing to re-roll the "
                "encounter data; the seed and tracker disagree.")
        return

    if not enabled:
        raise OptionError(
            "CTR hit_character_encounters: this seed carries an encounter "
            "block but ctr_options.hit_character is false or absent. Refusing "
            "to guess which is authoritative.")

    block = passthrough.get("hit_character_encounters")
    if block is None:
        raise OptionError(
            "CTR hit_character_encounters: the encounter block is present but "
            "null; refusing a malformed block.")

    global_schema = co.get("schema_version")
    if (type(global_schema) is not int
            or not GLOBAL_SCHEMA_MIN <= global_schema <= GLOBAL_SCHEMA_MAX):
        raise OptionError(
            "CTR hit_character_encounters: ctr_options.hit_character is "
            "enabled but ctr_options.schema_version is "
            f"{global_schema!r}; an enabled encounter block requires an "
            f"integer global schema_version in {GLOBAL_SCHEMA_MIN}.."
            f"{GLOBAL_SCHEMA_MAX}.")

    # A server's JSON slot_data carries lists, but slot_data read back from a
    # packed .archipelago (the tracker fuzz hook does this) carries tuples.
    # Both are the same wire value, so normalize before the strict list checks.
    # A JSON block is kept as the same object (restore is verbatim).
    if _has_tuple(block):
        block = _tuples_to_lists(block)
    _validate_block(block)
    world.ctr_hit_character_encounters = block
    world.ctr_hit_character_seed = int(block["policy"]["seed"])


def _has_tuple(value) -> bool:
    """Whether `value` contains a tuple anywhere, recursively."""
    if isinstance(value, tuple):
        return True
    if isinstance(value, dict):
        return any(_has_tuple(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_tuple(item) for item in value)
    return False


def _tuples_to_lists(value):
    """Copy `value` with every tuple turned into a list, recursively."""
    if isinstance(value, dict):
        return {key: _tuples_to_lists(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_tuples_to_lists(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Generation-time option guard
# ---------------------------------------------------------------------------

def raise_if_required_trial_modes_disabled(world) -> None:
    """Refuse an enabled seed whose trial Trophy races are not available.

    N. Tropy's guaranteed ordinary pins are Slide Coliseum (level 16) and
    Turbo Track (level 17), and their authoritative triggers are those two
    tracks' Trophy Races (35016200/35016201). If either trial Trophy mode is
    off, that opportunity cannot exist, so an enabled seed would advertise a
    check the player can never reach. Fail clearly instead of silently
    enabling another option or omitting the pin.
    """
    if not enabled(world):
        return
    missing = []
    if int(world.options.slide_coliseum_races.value) < 1:
        missing.append("slide_coliseum_races")
    if int(world.options.turbo_track_races.value) < 1:
        missing.append("turbo_track_races")
    if not missing:
        return
    raise OptionError(
        "CTR: 'hit_character' is enabled, but N. Tropy's guaranteed "
        "encounters are on the Slide Coliseum and Turbo Track Trophy Races, "
        "and this YAML disables "
        + " and ".join(f"'{name}'" for name in missing)
        + ". Set both 'slide_coliseum_races' and 'turbo_track_races' to at "
        "least 'trophy_race' (or turn 'hit_character' off).")


def raise_if_required_boss_encounters_disabled(world) -> None:
    """Refuse an enabled seed whose Nitros Oxide route is removed outright.

    Oxide's Hit check is proved by its ordinary pin (Oxide Station, gated on
    the Oxide win trigger) or by one of its two boss encounters. With
    `oxide_goal: disabled` both Oxide races are removed from the seed, so no
    authoritative trigger and no enabled boss encounter remains and the
    mandatory check could never be reached. This is the early, actionable
    companion to the trial-mode guard; the `set_rules` structural error stays
    as the backstop for lock-based impossibilities that are only decided in
    `create_regions`.
    """
    if not enabled(world):
        return
    from .Options import OxideGoal
    if OxideGoal.oxide_content_present(int(world.options.oxide_goal.value)):
        return
    raise OptionError(
        "CTR: 'hit_character' is enabled, but 'oxide_goal' is 'disabled', "
        "which removes both N. Oxide races from the seed. Nitros Oxide's "
        "mandatory Hit check would then be unreachable (no created trigger "
        "win and no enabled boss encounter). Set 'oxide_goal' to 'none', "
        "'any_percent' or '101_percent', or turn 'hit_character' off.")


# ---------------------------------------------------------------------------
# Encounter predicates and all-sixteen reachability (tickets 07 / 08)
# ---------------------------------------------------------------------------
#
# Every enabled Hit check gets a real rule here. The rule is an OR over the
# target's structurally available encounter routes, ANDed with the seed's hit
# method. A route proves four things, exactly as the contract's reachability
# section requires:
#
#   1. the route is enabled and available (a retail ordinary track or an
#      enabled boss race; missing or custom-displaced content is dropped);
#   2. the route is accessible (the physical pad's hub and final entrance rule
#      for an ordinary route, the boss race location's region and rule for a
#      boss route), respecting racer-locked pads through the seed's
#      destination -> physical pad map;
#   3. the target actually appears there for SOME obtainable, selectable player
#      racer, never the target itself (`never_seat_player`). Owning the target's
#      playable unlock item is never an appearance proof, and the starting
#      racer is never assumed to be the only choice;
#   4. a player-attributable hit method exists (Bomb / Missile / Bomb x3 /
#      Missile x3 while Itemsanity models weapons; ordinary vanilla supply when
#      it does not).
#
# ORDINARY PIN ROUTES (guests). A guest's guaranteed pins are the only required
# ordinary opportunities; reserve appearances and cups are extra and are not
# modelled as required logic. A pin route additionally requires the guest's
# authoritative any-of trigger (a reachable completed win), captured once after
# every Trophy rule is installed. A boss's ordinary pin is therefore eligible
# only after its clear.
#
# BOSS ROUTES. A boss-kind guest can be hit during its boss race whether or not
# the boss is cleared. The route comes from the emitted `bosses` identity table
# (the shared resolved-identity source), so a resolved identity substitution
# moves the route with the table. A boss race removed by options (for example
# `oxide_goal: disabled`) simply produces no boss route.
#
# DEFAULT RACERS. A default racer appears through the deterministic base list,
# never through an invented trigger. The contract reserves the one possible
# guest seat, so only the first `field_size - 1` non-player base IDs are
# guaranteed; the player being a default inside that prefix shifts the next base
# ID in by one seat. This conservative subset does not change as guests unlock,
# which is what preserves the availability invariant for default targets.
#
# STRUCTURAL FAILURES RAISE. A target with no structurally available route at
# all -- every retail route missing/displaced, every pin trigger absent, every
# route pad locked to the target itself, or no level that can seat a default --
# is a configuration error, not an inventory state, and raises a clear
# `OptionError`. Ordinary missing inventory stays a False predicate, because
# receiving the missing items can resolve it. No target is ever omitted.

#: The player-attributed hit methods accepted while Itemsanity models weapons.
#: Turbo and N. Tropy Clock alone are deliberately insufficient; the contract
#: records no boss-race exception, so the same rule applies to boss routes.
HIT_METHOD_ITEMS: Tuple[str, ...] = (
    "Bomb", "Missile", "Bomb x3", "Missile x3",
)

#: AI opponents in an ordinary/trial race: eight drivers including the player.
ORDINARY_FIELD_SIZE = 7
#: AI opponents in the retail Purple cup: five drivers including the player.
#: Cups are optional extra opportunities, so required logic never uses this.
PURPLE_CUP_FIELD_SIZE = 4


@dataclass(frozen=True)
class HitRoute:
    """One structurally-resolved encounter route for a target.

    `appearance_players` is the precomputed set of player racers that make the
    target actually appear on this route. An empty set means the route proves no
    appearance and is never installed. `triggers` carries the captured
    `(region, rule)` proofs for a guest pin and is empty for default racers and
    for boss routes. `boss_region`/`boss_rule` are set only for boss routes.
    """

    target_id: int
    kind: str                       # "ordinary" | "boss"
    track: str = ""
    level_id: int = -1
    hub: object = None
    entrance_rule: object = None
    pad_lock: Optional[str] = None
    appearance_players: Tuple[str, ...] = ()
    triggers: Tuple[Tuple[object, object], ...] = ()
    boss_region: object = None
    boss_rule: object = None


def _location_name_by_code(world) -> Dict[int, str]:
    """Invert the world's frozen location name -> code table."""
    return {int(code): name for name, code in world.location_name_to_id.items()}


def trigger_proofs(world, player: int,
                   target_id: int) -> List[Tuple[object, object]]:
    """Capture `(parent_region, access_rule)` for a guest's trigger races.

    Reads the authoritative codes from the resolved wire block rather than
    retyping them, and captures each trigger's FINAL region and rule exactly
    once. Called after every Trophy rule is installed, so a difficulty gate on
    the trigger race is retained. A code with no created location is dropped --
    that trigger simply cannot fire.

    The proof never queries a Hit location, calls a Hit rule, or inspects a
    placed item; it only asks whether a real trigger win is reachable.
    """
    block = getattr(world, "ctr_hit_character_encounters", None)
    if not block:
        return []
    entry = block.get("unlock_triggers", {}).get(str(target_id))
    if not entry:
        return []
    names = _location_name_by_code(world)
    cache = world.multiworld.regions.location_cache[player]
    proofs: List[Tuple[object, object]] = []
    for code in entry.get("any_of", ()):
        name = names.get(int(code))
        if name is None:
            continue
        location = cache.get(name)
        if location is None:
            continue
        proofs.append((location.parent_region, location.access_rule))
    return proofs


def trigger_rule(proofs):
    """The any-of unlock proof over captured triggers.

    `any(region.can_reach(state) and captured_rule(state) for each trigger)`.
    Generic Trophy ownership is not the trigger and is never consulted here.
    """
    def rule(state):
        return any(region.can_reach(state) and access(state)
                   for region, access in proofs)
    return rule


def _track_name_by_level_id(world) -> Dict[int, str]:
    """Destination level id -> the track/region name its pad loads."""
    out: Dict[int, str] = {}
    for pad_name, meta in getattr(world, "warp_pad_ids", {}).items():
        if pad_name.endswith(" Warp Pad"):
            out[int(meta["level_id"])] = pad_name[: -len(" Warp Pad")]
    return out


def retail_route(world, player: int, track: str):
    """Resolve the physical pad that loads retail `track`, or None.

    Returns `(pad_name, hub_region, entrance_rule)` captured once, after all
    pad and racer-lock rules are installed. The pad is resolved through the
    seed's destination -> physical pad map, never by track name. The entrance
    must still lead to the retail region: a missing pad, or one retargeted to
    displaced custom content, is unavailable rather than silently substituted.
    """
    by_dest = getattr(world, "ctr_pad_by_destination", None) or {}
    pad_name = by_dest.get(track, f"{track} Warp Pad")
    try:
        entrance = world.multiworld.get_entrance(pad_name, player)
    except KeyError:
        return None
    destination = entrance.connected_region
    if destination is None or destination.name != track:
        return None
    return (pad_name, entrance.parent_region, entrance.access_rule)


def _selectable(world, state, player: int, racer: str) -> bool:
    """The shared ownership/selectability filter for one player racer."""
    return progressive_capability.gate_satisfied(
        world, state, player, required_character=racer)


def _default_appearance_players(target_id: int, base: Tuple[int, ...],
                                field_size: int,
                                pad_lock: Optional[str]) -> Tuple[str, ...]:
    """Player racers under which `target_id` is guaranteed to be seated.

    One guest seat is reserved, so only the first `field_size - 1` base IDs
    after removing the player are guaranteed. The player being a default inside
    that prefix shifts the next base ID in by exactly one seat, so the single
    seat after the guaranteed prefix is also reachable when the player is drawn
    from the prefix. The final base ID can never be shifted in by one removal.
    """
    limit = field_size - 1
    target_name = characters.CHARACTER_ID_TO_NAME[target_id]
    if pad_lock is not None:
        if pad_lock == target_name:
            return ()
        pid = characters.ROSTER_CHARACTER_ID[pad_lock]
        pruned = [b for b in base if b != pid]
        return (pad_lock,) if target_id in pruned[:limit] else ()
    if target_id in base[:limit]:
        return tuple(name for name in progressive_capability.ROSTER
                     if name != target_name)
    if target_id in base[:field_size]:
        return tuple(characters.CHARACTER_ID_TO_NAME[b] for b in base[:limit])
    return ()


def _guest_appearance_players(target_name: str,
                              pad_lock: Optional[str]) -> Tuple[str, ...]:
    """Player racers under which a pinned guest actually appears.

    A guaranteed pin seats the guest as long as the player is a different,
    selectable racer; a racer-locked pad narrows that to the one locked racer.
    """
    if pad_lock == target_name:
        return ()
    if pad_lock is not None:
        return (pad_lock,)
    return tuple(name for name in progressive_capability.ROSTER
                 if name != target_name)


def _build_ordinary_routes(world, player: int, target_id: int,
                           block) -> List[HitRoute]:
    """Structurally resolve every retail ordinary route for `target_id`.

    Default racers scan all eighteen destination levels through the base list;
    guests scan only their guaranteed pin levels. A route whose pad is missing,
    displaced to custom content, or locked to the target itself is dropped.
    """
    target_name = characters.CHARACTER_ID_TO_NAME[target_id]
    tracks = block["tracks"]
    by_level = _track_name_by_level_id(world)
    is_default = target_id in DEFAULT_RACER_IDS
    levels = TRACK_LEVEL_IDS if is_default else PIN_GUESTS[target_id][0]
    routes: List[HitRoute] = []
    for level_id in levels:
        track = by_level.get(level_id)
        if track is None:
            continue
        resolved = retail_route(world, player, track)
        if resolved is None:
            continue
        _pad_name, hub, entrance_rule = resolved
        pad_lock = progressive_capability.track_required_character(world, track)
        if is_default:
            base = tuple(tracks[str(level_id)]["base"])
            players = _default_appearance_players(
                target_id, base, ORDINARY_FIELD_SIZE, pad_lock)
        else:
            players = _guest_appearance_players(target_name, pad_lock)
        if not players:
            continue
        routes.append(HitRoute(
            target_id=target_id, kind="ordinary", track=track,
            level_id=level_id, hub=hub, entrance_rule=entrance_rule,
            pad_lock=pad_lock, appearance_players=players))
    return routes


def _build_boss_routes(world, player: int, target_id: int,
                       block) -> List[HitRoute]:
    """Resolve the enabled boss encounters whose identity is `target_id`.

    The identity comes from the emitted `bosses` table, never from a retyped
    mapping, so a resolved-identity substitution moves the route with the wire
    data. A boss race removed by options yields no route.
    """
    names = _location_name_by_code(world)
    cache = world.multiworld.regions.location_cache[player]
    routes: List[HitRoute] = []
    for code_str, opponent in block.get("bosses", {}).items():
        if int(opponent) != target_id:
            continue
        name = names.get(int(code_str))
        if name is None:
            continue
        location = cache.get(name)
        if location is None:
            continue
        routes.append(HitRoute(
            target_id=target_id, kind="boss",
            boss_region=location.parent_region,
            boss_rule=location.access_rule))
    return routes


def _ordinary_predicate(world, player: int, route: HitRoute):
    """The state predicate for one ordinary route."""
    def predicate(state):
        if not route.hub.can_reach(state) or not route.entrance_rule(state):
            return False
        return any(_selectable(world, state, player, racer)
                   for racer in route.appearance_players)
    return predicate


def _boss_predicate(route: HitRoute):
    """The state predicate for one boss route (no trigger, no clear needed)."""
    def predicate(state):
        return route.boss_region.can_reach(state) and route.boss_rule(state)
    return predicate


def _install_target(world, player: int, target_id: int, block,
                    itemsanity_on: bool) -> None:
    """Build and install one target's rule, raising on structural impossibility."""
    target_name = characters.CHARACTER_ID_TO_NAME[target_id]
    location = world.multiworld.regions.location_cache[player].get(
        HIT_CHARACTER_CLASS.location_name(target_id))
    if location is None:
        _fail(f"the Hit check for {target_name!r} was not created. Refusing "
              "to silently advertise an unreachable check or omit a target.")

    triggers: Tuple[Tuple[object, object], ...] = ()
    if target_id in DEFAULT_RACER_IDS:
        ordinary = _build_ordinary_routes(world, player, target_id, block)
        boss: List[HitRoute] = []
        if not ordinary:
            _fail(f"default racer {target_name!r} has no structurally "
                  "reachable ordinary appearance on any created retail track "
                  "(missing/displaced pads, or every route locked to the "
                  "target). Refusing to advertise an unreachable check.")
    else:
        triggers = tuple(trigger_proofs(world, player, target_id))
        ordinary = (_build_ordinary_routes(world, player, target_id, block)
                    if triggers else [])
        boss = _build_boss_routes(world, player, target_id, block)
        if not ordinary and not boss:
            if not triggers:
                reason = ("no created authoritative trigger win and no enabled "
                          "boss encounter")
            else:
                reason = ("every guaranteed pin route is missing, displaced to "
                          "custom content, or locked to the target, and no "
                          "enabled boss encounter exists")
            _fail(f"guest {target_name!r} has no reachable encounter route: "
                  f"{reason}. Refusing to advertise an unreachable check.")

    ordinary_preds = tuple(_ordinary_predicate(world, player, route)
                           for route in ordinary)
    boss_preds = tuple(_boss_predicate(route) for route in boss)

    def rule(state, ordinary_preds=ordinary_preds, boss_preds=boss_preds,
             triggers=triggers):
        if itemsanity_on and not state.has_any(HIT_METHOD_ITEMS, player):
            return False
        if boss_preds and any(predicate(state) for predicate in boss_preds):
            return True
        if not ordinary_preds:
            return False
        if triggers and not any(region.can_reach(state) and access(state)
                                for region, access in triggers):
            return False
        return any(predicate(state) for predicate in ordinary_preds)

    location.access_rule = rule


def install_rules(world, player: int) -> None:
    """Install the real rule for every enabled Hit check (tickets 07 / 08).

    Called LAST from `Rules.set_rules`, after every Trophy, warp-pad and racer-
    lock rule is installed, so each guest's trigger capture sees the final
    rules. All sixteen checks are mandatory; a target that cannot be encountered
    under any structurally available route raises a clear `OptionError` instead
    of being omitted or silently left unreachable.
    """
    if not enabled(world):
        return
    block = getattr(world, "ctr_hit_character_encounters", None)
    if not block:
        _fail("the enabled encounter block is missing; refusing to install "
              "silently unreachable Hit checks.")
    itemsanity_on = bool(world.options.itemsanity.value)
    for target_id in sorted(characters.CHARACTER_ID_TO_NAME):
        _install_target(world, player, target_id, block, itemsanity_on)
