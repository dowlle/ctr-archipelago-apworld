"""Custom-track descriptors (Baby T Park event spike, rung 2b).

Ruled 2026-08-28 (Wayfinder session): the option shape is an early instance of
the self-describing `custom_tracks` descriptor -- id, per-file SHA-256s and
the track's MEASURED capability flags -- not a throwaway toggle. When the
option is active, the Purple Gem Cup DESTINATION is displaced: instead of
four retail leg tracks it becomes a single 7-lap race on the custom track,
and winning that race awards the Purple Gem through the cup's own gem path
(native does the awarding). The retail Purple cup experience is absent from
such a seed. Option off (the default, an empty descriptor) leaves generation
byte-identical to a build without this module.

WHAT THIS MODULE OWNS

  * the descriptor's shape, and its validation (a clean OptionError on
    anything malformed, following the `traps.validate_trap_weights`
    precedent so a rolled YAML and a programmatically built world fail
    identically);
  * the DISPLACEMENT rule -- which cup a descriptor entry takes over, and
    what that does to the seed's gem-cup leg map;
  * the `custom_tracks` slot_data block and its Universal Tracker
    reconstruction.

WHAT IT DELIBERATELY DOES NOT OWN

  * asset delivery and hash VERIFICATION. The apworld never sees the files;
    it carries the descriptor's digests to native, which hashes the real
    bytes and refuses to arm on any mismatch. The descriptor is therefore
    the authority on what the seed expects, which is exactly what makes it
    self-describing -- a retuned v1.0.1 of a track needs a new YAML, not a
    new apworld release. The apworld validates SHAPE (64 hex digits), never
    content;
  * the host arcade slot's own race. Native serves the custom bytes only for
    the redirected cup race, so the host slot's retail track is unaffected
    in the same seed. `host_level_id` is a vehicle, not a destination, and
    it is a FIXED default rather than an RNG draw precisely so that turning
    this option on cannot disturb any other seed decision;
  * AP boxes, CTR letters and relic checks ON the custom track. The event
    seed's check set is the Purple Gem alone -- see `boxes` below and
    docs/SLOT_DATA_CUSTOM_TRACKS_DRAFT.md for why the box rung is blocked.

DISPLACEMENT AND THE LEG MAP

`Regions.create_regions` resolves the seed's gem-cup leg map exactly once
(`gem_cup_legs.resolve_gem_cup_legs`) and stashes it. That map has two
consumers with genuinely different needs, so this module splits them:

  * `world.gem_cup_legs_table` -- the COMPLETE five-cup table, what native's
    `advCupTrackIDs` holds. `fill_slot_data`'s `gem_cup_legs` block
    serializes this, so the wire keeps its "always all five cups, always
    four legs" invariant no matter what is displaced;
  * `world.gem_cup_legs` -- the LOGIC map, the table with every displaced
    cup's legs emptied. A displaced cup runs one race on a custom track, so
    it legs no trophy track, so it justifies no trophy track's podium rungs.
    `Regions`' podium-region cup entrances, `Rules.add_podium_placement_rules`
    and `usf_finish.UsfFinishGate` all read this one.

Emptying a cup's legs is always SAFE for solvability: the 2026-08-07 dossier
established that a cup leg is only ever an ADDITIVE path to a track's podium
rungs (the track's own warp pad stays an independent path), so removing legs
can never orphan a rung. It is also the correct direction for the USF finish
gate: a displaced Purple cup no longer includes a USF-gated leg, so its Gem
correctly stops carrying that term -- the player really can finish the cup
without the boost chain, because the cup is now one race on the custom track.

Displacement consumes NO RNG. `resolve_gem_cup_legs` still makes the same 20
draws in the same order when `randomize_gem_cup_tracks` is on, and none at
all when it is off; the displacement is a pure filter applied afterwards.
"""
import logging
import re
from typing import Dict, FrozenSet, List, Mapping, Tuple

from Options import OptionError

logger = logging.getLogger(__name__)

#: Wire-block version, independent of the seed's `schema_version`. Bump this
#: when the SHAPE of an entry changes; native refuses a version it does not
#: know rather than reading fields it cannot interpret.
CUSTOM_TRACKS_WIRE_VERSION = 1

#: Track ids this build knows how to bind. An id is an allowlist entry, not a
#: content claim: the descriptor still carries every fact about the track, and
#: native still verifies the bytes. The allowlist exists so a typo becomes a
#: clean generation error instead of a seed nothing can play.
KNOWN_TRACK_IDS: Tuple[str, ...] = ("baby-t-park",)

#: The destinations a descriptor entry may claim, and what claiming one means:
#: `replaces` value -> (cup region name, cup LevelID). The binding is EXPLICIT
#: in the YAML rather than implied by the track id, so a second custom track
#: never inherits a rule it never asked for. Only the Purple Gem Cup is ruled
#: today; any other value is refused.
REPLACEABLE_DESTINATIONS: Dict[str, Tuple[str, int]] = {
    "purple_gem_cup": ("Purple Gem Cup", 104),
}

#: The arcade slot the custom bytes borrow when the descriptor does not say.
#: 6 matches the native loader's own documented default (tools/CUSTOM-TRACK-SPIKE.md),
#: so a native falling back to its config default and a native reading this
#: block agree. Any 0..17 slot works: native serves custom bytes only for the
#: redirected cup race, so the host slot's retail race is untouched in-seed.
DEFAULT_HOST_LEVEL_ID = 6

#: Engine bound on a mappable arcade slot: `data.ArcadeDifficulty` is
#: `Difficulty[18]` indexed by levelID with no range check, and
#: `data.metaDataLEV` must have a real entry for the slot.
HOST_LEVEL_ID_RANGE = (0, 17)

#: Native writes `gGT->numLaps` directly for the event race and restores 3 on
#: every exit; its own config clamps to 1..7.
LAP_RANGE = (1, 7)

#: Measured capability flags, the describe-step output. Every one is REQUIRED:
#: a descriptor that omits a flag is not self-describing, and a silently
#: defaulted flag is exactly the "plausible but wrong" state hash verification
#: exists to prevent.
BOOLEAN_FLAGS: Tuple[str, ...] = (
    "crates", "ctr_letters", "relic_crates", "ai_nav", "minimap", "ghosts",
)
#: Counted flags -> their inclusive legal range. `spawns` is the populated
#: driver-spawn count (8 is a full grid); `checkpoints` is the restart-point
#: count the lap logic feeds from.
COUNT_FLAGS: Dict[str, Tuple[int, int]] = {
    "spawns": (1, 8),
    "checkpoints": (1, 255),
}

_REQUIRED_ENTRY_KEYS: FrozenSet[str] = frozenset(
    {"lev_sha256", "vrm_sha256", "laps", "replaces", "flags"})
_OPTIONAL_ENTRY_KEYS: FrozenSet[str] = frozenset({"host_level_id", "boxes"})
_ALL_ENTRY_KEYS: FrozenSet[str] = _REQUIRED_ENTRY_KEYS | _OPTIONAL_ENTRY_KEYS

_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")

#: The measured Baby T Park descriptor (evidence note 2026-08-27, the actual
#: downloaded v1.0.0 files). Not used to validate a player's descriptor -- the
#: descriptor is the authority -- but it IS the option's documented example and
#: the value the tests and the event YAML use.
BABY_T_PARK_EXAMPLE: Dict[str, object] = {
    "lev_sha256":
        "96ad9f74f51a02eafcc207cd02c97052d674c950e0f24b6440a227494a705fe8",
    "vrm_sha256":
        "2dcaa0fe93359c7ae00fb93842a581210e0dcc2db73f4de43508375834092e83",
    "laps": 7,
    "replaces": "purple_gem_cup",
    "flags": {
        "crates": True,
        "ctr_letters": True,
        "relic_crates": True,
        "ai_nav": True,
        "minimap": False,
        "ghosts": False,
        "spawns": 8,
        "checkpoints": 35,
    },
}


def _is_int(value) -> bool:
    """True for a real integer. `bool` is an `int` subclass in Python and
    `laps: true` is never a lap count, so booleans are excluded explicitly --
    the same trap `traps.validate_trap_weights` guards."""
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(message: str) -> None:
    raise OptionError(f"CTR 'custom_tracks' {message}")


def _validate_flags(track_id: str, flags) -> None:
    if not isinstance(flags, Mapping):
        _fail(f"entry '{track_id}' has a 'flags' value that is not a mapping "
              f"({type(flags).__name__}). 'flags' holds the track's measured "
              f"capabilities, one key per capability.")
    expected = set(BOOLEAN_FLAGS) | set(COUNT_FLAGS)
    missing = sorted(expected - set(flags))
    if missing:
        _fail(f"entry '{track_id}' is missing measured flag(s): "
              f"{', '.join(missing)}. Every flag is required -- a descriptor "
              f"that omits one is not self-describing, and a silently "
              f"defaulted capability is exactly the wrong-content state the "
              f"hash check exists to prevent.")
    unknown = sorted(set(flags) - expected)
    if unknown:
        _fail(f"entry '{track_id}' has unknown flag(s): "
              f"{', '.join(repr(k) for k in unknown)}. Valid flags: "
              f"{', '.join(sorted(expected))}.")
    for key in BOOLEAN_FLAGS:
        if not isinstance(flags[key], bool):
            _fail(f"entry '{track_id}' flag '{key}' is {flags[key]!r}. "
                  f"It must be true or false.")
    for key, (low, high) in COUNT_FLAGS.items():
        value = flags[key]
        if not _is_int(value) or not low <= value <= high:
            _fail(f"entry '{track_id}' flag '{key}' is {value!r}. It must be "
                  f"a whole number from {low} to {high}.")


def _validate_entry(track_id: str, entry) -> None:
    if not isinstance(entry, Mapping):
        _fail(f"entry '{track_id}' is not a mapping ({type(entry).__name__}). "
              f"Each entry describes one track: its two file digests, its lap "
              f"count, what it replaces, and its measured flags.")
    missing = sorted(_REQUIRED_ENTRY_KEYS - set(entry))
    if missing:
        _fail(f"entry '{track_id}' is missing required key(s): "
              f"{', '.join(missing)}.")
    unknown = sorted(set(entry) - _ALL_ENTRY_KEYS)
    if unknown:
        _fail(f"entry '{track_id}' has unknown key(s): "
              f"{', '.join(repr(k) for k in unknown)}. Valid keys: "
              f"{', '.join(sorted(_ALL_ENTRY_KEYS))}.")
    for key in ("lev_sha256", "vrm_sha256"):
        value = entry[key]
        if not isinstance(value, str) or not _SHA256_RE.match(value):
            _fail(f"entry '{track_id}' key '{key}' is {value!r}. It must be a "
                  f"SHA-256 digest: exactly 64 hexadecimal characters. The "
                  f"apworld never reads the files -- it carries this digest to "
                  f"the game, which hashes the real bytes and refuses to load "
                  f"the track on any mismatch.")
    laps = entry["laps"]
    if not _is_int(laps) or not LAP_RANGE[0] <= laps <= LAP_RANGE[1]:
        _fail(f"entry '{track_id}' key 'laps' is {laps!r}. It must be a whole "
              f"number from {LAP_RANGE[0]} to {LAP_RANGE[1]}.")
    replaces = entry["replaces"]
    if replaces not in REPLACEABLE_DESTINATIONS:
        _fail(f"entry '{track_id}' key 'replaces' is {replaces!r}. The only "
              f"destination this build can hand to a custom track is "
              f"{', '.join(sorted(REPLACEABLE_DESTINATIONS))}. The binding is "
              f"written out rather than implied by the track id, so a track "
              f"never inherits a destination it did not ask for.")
    if "host_level_id" in entry:
        host = entry["host_level_id"]
        low, high = HOST_LEVEL_ID_RANGE
        if not _is_int(host) or not low <= host <= high:
            _fail(f"entry '{track_id}' key 'host_level_id' is {host!r}. It "
                  f"must be a whole number from {low} to {high}: a custom "
                  f"track always borrows an existing arcade slot, and the "
                  f"engine's difficulty and track-metadata tables are sized "
                  f"for exactly those {high + 1} slots. Leave it out for the "
                  f"default ({DEFAULT_HOST_LEVEL_ID}).")
    if "boxes" in entry and not isinstance(entry["boxes"], bool):
        _fail(f"entry '{track_id}' key 'boxes' is {entry['boxes']!r}. It must "
              f"be true or false.")
    _validate_flags(track_id, entry["flags"])


def validate_custom_tracks(mapping) -> None:
    """Reject an unusable `custom_tracks` descriptor with a clear OptionError.

    An empty mapping is the option being off and is always valid. Anything
    else must be exactly ONE known entry with a complete, well-typed body: a
    partly-described custom track is not a smaller feature, it is a seed whose
    generation logic and whose game disagree about what the Purple Gem Cup is.

    Called on every generation path: the YAML roll reaches it through
    `Options.CustomTracks.verify_keys`, and `generate_early` calls it again
    for worlds built programmatically (tests, the fuzzer), exactly as
    `traps.validate_trap_weights` is called from both.
    """
    if not isinstance(mapping, Mapping):
        _fail(f"must be a mapping of track id to descriptor, not "
              f"{type(mapping).__name__}. Leave it out entirely to play "
              f"without custom tracks.")
    if not mapping:
        return
    if len(mapping) > 1:
        _fail(f"has {len(mapping)} entries "
              f"({', '.join(sorted(repr(k) for k in mapping))}). This build "
              f"binds exactly one custom track per seed, because exactly one "
              f"destination can be handed over.")
    (track_id, entry), = mapping.items()
    if track_id not in KNOWN_TRACK_IDS:
        _fail(f"has unknown track id {track_id!r}. This build knows: "
              f"{', '.join(KNOWN_TRACK_IDS)}.")
    _validate_entry(track_id, entry)


def normalize_custom_tracks(mapping) -> Dict[str, Dict[str, object]]:
    """Validate, then return the descriptor with its defaults filled in and
    its digests lower-cased.

    Everything downstream -- logic, the wire, the tests -- reads the
    NORMALIZED form, so `host_level_id`, `boxes` and digest case are decided
    in exactly one place and two YAMLs that differ only in digest case produce
    the identical seed.
    """
    validate_custom_tracks(mapping)
    if not mapping:
        return {}
    (track_id, entry), = mapping.items()
    return {
        track_id: {
            "lev_sha256": entry["lev_sha256"].lower(),
            "vrm_sha256": entry["vrm_sha256"].lower(),
            "laps": int(entry["laps"]),
            "replaces": entry["replaces"],
            "host_level_id": int(entry.get("host_level_id",
                                           DEFAULT_HOST_LEVEL_ID)),
            # Ruled default: the event race allows AP boxes. See
            # docs/SLOT_DATA_CUSTOM_TRACKS_DRAFT.md -- the placement data
            # behind that permission does not exist yet, so this is a policy
            # bit travelling ahead of its content.
            "boxes": bool(entry.get("boxes", True)),
            "flags": {
                **{k: bool(entry["flags"][k]) for k in BOOLEAN_FLAGS},
                **{k: int(entry["flags"][k]) for k in COUNT_FLAGS},
            },
        }
    }


def resolve_custom_tracks(world) -> Dict[str, Dict[str, object]]:
    """This seed's normalized descriptor, or `{}` when the option is off.

    Pure: reads options, draws nothing, mutates nothing. Turning this option
    on therefore cannot move any other per-seed decision.
    """
    raw = getattr(getattr(world.options, "custom_tracks", None), "value", None)
    return normalize_custom_tracks(raw or {})


def resolved_custom_tracks(world) -> Dict[str, Dict[str, object]]:
    """`world.custom_tracks`, set exactly once per seed by
    `Regions.create_regions`. Raises rather than silently answering "off": a
    missing attribute means create_regions never ran (a call-order bug), not
    that the player left the option out -- which `resolve_custom_tracks`
    already expresses by returning an empty descriptor."""
    try:
        return world.custom_tracks
    except AttributeError:
        raise RuntimeError(
            "world.custom_tracks read before Regions.create_regions resolved "
            "it for this seed -- call order bug, not a missing-option case"
        ) from None


def displaced_cups(tracks: Mapping[str, Mapping]) -> Dict[str, str]:
    """cup region name -> the track id that took its destination over."""
    return {REPLACEABLE_DESTINATIONS[entry["replaces"]][0]: track_id
            for track_id, entry in tracks.items()}


def apply_displacement(cup_legs: Dict[str, List[str]],
                       tracks: Mapping[str, Mapping]) -> Dict[str, List[str]]:
    """The LOGIC leg map: the complete table with each displaced cup emptied.

    A displaced cup runs one race on a custom track, so it legs no trophy
    track and justifies no trophy track's podium rungs. Returns a fresh map
    (and fresh lists) so the caller's complete table -- the one the wire
    serializes -- is never aliased or mutated.
    """
    displaced = set(displaced_cups(tracks))
    return {cup: ([] if cup in displaced else list(legs))
            for cup, legs in cup_legs.items()}


def custom_tracks_to_wire(tracks: Mapping[str, Mapping]) -> Dict[str, object]:
    """Serialize the normalized descriptor for slot_data.

    A LIST of self-describing entries rather than an id-keyed object: native's
    seed-config reader looks fields up by name and does not enumerate unknown
    keys, so it finds its track by scanning for the `replaces_cup_level_id` it
    cares about. The cup is emitted as a LevelID (104), the same currency
    `warp_pad_map`, `warp_pad_unlock` and `gem_cup_legs` already use, rather
    than the YAML's human-facing `replaces` word.
    """
    return {
        "enabled": True,
        "version": CUSTOM_TRACKS_WIRE_VERSION,
        "tracks": [
            {
                "id": track_id,
                "lev_sha256": entry["lev_sha256"],
                "vrm_sha256": entry["vrm_sha256"],
                "laps": entry["laps"],
                "host_level_id": entry["host_level_id"],
                "replaces_cup_level_id":
                    REPLACEABLE_DESTINATIONS[entry["replaces"]][1],
                "boxes": entry["boxes"],
                "flags": dict(entry["flags"]),
            }
            for track_id, entry in sorted(tracks.items())
        ],
    }


#: LevelID -> the `replaces` word, for reading a wire block back.
_CUP_LID_TO_REPLACES: Dict[int, str] = {
    lid: word for word, (_name, lid) in REPLACEABLE_DESTINATIONS.items()}


def reconstruct_custom_tracks_from_wire(
        passthrough: Mapping[str, object]) -> Dict[str, Dict[str, object]]:
    """Universal Tracker re-generation: rebuild the seed's descriptor from its
    slot_data instead of reading the tracking player's own YAML.

    An absent block means the seed had no custom track, which is exactly what
    every pre-custom-tracks seed generated with, so it restores silently to
    off. A PRESENT but unreadable block falls back to off with a warning: that
    state means the seed DID displace a cup and the tracker cannot tell which,
    so its podium-rung map may be more permissive than the server's -- the
    same honesty rule `gem_cup_legs.reconstruct_gem_cup_legs_from_wire`
    follows.

    Lists arrive as tuples here: AP runs every slot_data value through
    `NetUtils.convert_to_base_types` before pickling it into multidata, so a
    live wire block's `tracks` is a tuple. Both are accepted.
    """
    block = passthrough.get("custom_tracks")
    if block is None:
        return {}

    def _give_up(reason: str) -> Dict[str, Dict[str, object]]:
        logger.warning(
            "custom_tracks wire block present but %s -- falling back to no "
            "custom tracks; this seed's tracker map may be more permissive "
            "than the server's", reason)
        return {}

    if not isinstance(block, Mapping):
        return _give_up(f"not an object ({type(block).__name__})")
    version = block.get("version")
    if version != CUSTOM_TRACKS_WIRE_VERSION:
        return _give_up(f"carries version {version!r}, and this build reads "
                        f"version {CUSTOM_TRACKS_WIRE_VERSION}")
    entries = block.get("tracks")
    if not isinstance(entries, (list, tuple)) or len(entries) != 1:
        return _give_up("does not hold exactly one track entry")
    (wire_entry,) = entries
    if not isinstance(wire_entry, Mapping):
        return _give_up("holds a track entry that is not an object")
    track_id = wire_entry.get("id")
    cup_lid = wire_entry.get("replaces_cup_level_id")
    if track_id not in KNOWN_TRACK_IDS or cup_lid not in _CUP_LID_TO_REPLACES:
        return _give_up(f"names track {track_id!r} replacing cup {cup_lid!r}, "
                        f"which this build does not know")
    flags = wire_entry.get("flags")
    if not isinstance(flags, Mapping):
        return _give_up("holds a track entry without a flags object")
    rebuilt = {
        track_id: {
            "lev_sha256": wire_entry.get("lev_sha256"),
            "vrm_sha256": wire_entry.get("vrm_sha256"),
            "laps": wire_entry.get("laps"),
            "replaces": _CUP_LID_TO_REPLACES[cup_lid],
            "host_level_id": wire_entry.get("host_level_id"),
            "boxes": wire_entry.get("boxes"),
            "flags": dict(flags),
        }
    }
    try:
        # Re-run the option validator on the rebuilt descriptor. The wire and
        # the YAML then have exactly one definition of "well formed", so a
        # tracker can never reconstruct a seed shape generation would have
        # refused.
        return normalize_custom_tracks(rebuilt)
    except OptionError as exc:
        return _give_up(f"fails descriptor validation ({exc})")
