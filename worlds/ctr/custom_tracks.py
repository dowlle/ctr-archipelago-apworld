"""Custom-track descriptors and Alpha6 placement policy.

Ruled 2026-08-28 (Wayfinder session): the option shape is an early instance of
the self-describing `custom_tracks` descriptor -- id, per-file SHA-256s and
the track's MEASURED capability flags -- not a throwaway toggle. When the
option is active, the Purple Gem Cup DESTINATION is displaced: instead of four
retail leg tracks it becomes a single 7-lap race on the custom track. Its AP
check is the frozen generic `Custom Track 1: Trophy Race` identity, plus the
seed's enabled podium rungs. The removed retail `Purple Gem Cup: Gem` identity
never coexists with it. Native still records the cup's ordinary adventure Gem
bit for presentation and progression bookkeeping, but sends the generic Trophy
location; therefore `shuffle_gems: true` leaves the Purple Gem in the normal
item pool. Option off is the default and leaves the block absent. Alpha6 still
declares slot-data schema 8 on every seed.

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
    it carries the approved registry descriptor to native, which hashes the
    real bytes and refuses to arm on any mismatch. Alpha6 accepts only the
    compiled Baby T Park package identity. A retuned package therefore needs
    coordinated apworld and client support rather than an arbitrary YAML edit;
  * the host arcade slot's own race. Native serves the custom bytes only for
    the redirected cup race, so the host slot's retail track is unaffected
    in the same seed. `host_level_id` is a vehicle, not a destination, and
    it is a FIXED default rather than an RNG draw precisely so that turning
    this option on cannot disturb any other seed decision;
  * AP boxes, CTR letters and relic checks ON the custom track. This Alpha6
    slice creates the geometry-independent Trophy and podium family only; see
    `boxes` below and docs/SLOT_DATA_CUSTOM_TRACKS_DRAFT.md for why the box rung
    remains blocked.

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
#:
#: 3 (2026-08-29) adds the required measured `wumpa_collectible` flag. A version-2
#: entry carries no such measurement, and per-track Wumpa checks must never guess
#: one, so an Alpha6 client reading a version-2 block and a version-3 build
#: reading a version-2 block both refuse rather than default the flag.
#: 4 (2026-08-30) composes that flag with the frozen generic custom slot and
#: exact Trophy/podium location codes. Native must know which stable AP
#: identities the selected package serves; neither field may be inferred from
#: a mutable title or array position.
CUSTOM_TRACKS_WIRE_VERSION = 4

#: Track ids this build knows how to bind. Each id selects one complete,
#: release-approved identity below. Native independently enforces the same
#: registry before it arms any files.
KNOWN_TRACK_IDS: Tuple[str, ...] = ("baby-t-park",)

#: Player-facing package titles for the spoiler, keyed by the same stable
#: track id the registry uses. Package titles are mutable community metadata,
#: so they live in this presentation-only table rather than in the descriptor
#: or on the wire; the spoiler reads them by resolved track id and nothing
#: else does.
TRACK_DISPLAY_NAMES: Dict[str, str] = {
    "baby-t-park": "Baby T Park",
}

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

#: The measured capability that decides whether a bound custom destination earns
#: a per-track Reach 10 Wumpa check (spec 2026-08-29, Lane A). Named here rather
#: than spelled out at each use site because four layers read it: manager-light
#: measures and exports it, this module validates it, `wumpa_checks` gates
#: creation on it, and native verifies it against the installed package.
#:
#: It is DELIBERATELY not derived from `crates`. A track can carry crate
#: instances -- weapon boxes, TNT, relic time crates -- without offering any
#: route to ten fruit, and the descriptor contract requires measured
#: capabilities rather than optimistic inference.
WUMPA_COLLECTIBLE_FLAG = "wumpa_collectible"

#: Measured capability flags, the describe-step output. Every one is REQUIRED:
#: a descriptor that omits a flag is not self-describing, and a silently
#: defaulted flag is exactly the "plausible but wrong" state hash verification
#: exists to prevent.
BOOLEAN_FLAGS: Tuple[str, ...] = (
    "crates", "ctr_letters", "relic_crates", "ai_nav", "minimap", "ghosts",
    WUMPA_COLLECTIBLE_FLAG,
)
#: Counted flags -> their inclusive legal range. `spawns` is the populated
#: driver-spawn count (8 is a full grid); `checkpoints` is the restart-point
#: count the lap logic feeds from.
COUNT_FLAGS: Dict[str, Tuple[int, int]] = {
    "spawns": (1, 8),
    "checkpoints": (1, 255),
}

_REQUIRED_ENTRY_KEYS: FrozenSet[str] = frozenset({
    "package_uuid", "package_version", "minimum_client_version",
    "minimum_apworld_version", "lev_sha256", "vrm_sha256", "navigation",
    "laps", "replaces", "flags",
})
_OPTIONAL_ENTRY_KEYS: FrozenSet[str] = frozenset({"host_level_id", "boxes"})
_ALL_ENTRY_KEYS: FrozenSet[str] = _REQUIRED_ENTRY_KEYS | _OPTIONAL_ENTRY_KEYS

_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")
_UUID_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")

#: The measured and release-approved Baby T Park descriptor (evidence note
#: 2026-08-27, the actual downloaded v1.0.0 files). Alpha6 validates every
#: generation-affecting field against this registry entry. This keeps the
#: apworld and native acceptance sets identical.
BABY_T_PARK_EXAMPLE: Dict[str, object] = {
    "package_uuid": "60d5a8a8-b69a-4f6a-a0d8-9a43d91e3f2e",
    "package_version": "1.0.0",
    "minimum_client_version": "0.2.0-alpha6",
    "minimum_apworld_version": "0.2.0-alpha6",
    "lev_sha256":
        "96ad9f74f51a02eafcc207cd02c97052d674c950e0f24b6440a227494a705fe8",
    "vrm_sha256":
        "2dcaa0fe93359c7ae00fb93842a581210e0dcc2db73f4de43508375834092e83",
    "navigation": {
        "uuid": "898a9315-693f-4ed3-b6a0-fbe50db8bc40",
        "revision": 1,
    },
    "laps": 7,
    "replaces": "purple_gem_cup",
    "flags": {
        "crates": True,
        "ctr_letters": True,
        "relic_crates": True,
        "ai_nav": True,
        "minimap": False,
        "ghosts": False,
        # MEASURED against the v1.0.0 LEV whose digest is above (2026-08-29):
        # its instance table carries 8 instances of modelID 7 (PU_FRUIT_CRATE)
        # and 0 loose PU_WUMPA_FRUIT. RB_Crate.c pays a fruit crate 5..8 fruit,
        # so the guaranteed floor is 40 in one lap of a 7-lap race -- far above
        # the 10 this capability asks about. Manager-light derives the same
        # answer from the same bytes; see native_custom_track_manager.c.
        "wumpa_collectible": True,
        "spawns": 8,
        "checkpoints": 35,
    },
    "boxes": False,
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
    for key in ("package_uuid",):
        value = entry[key]
        if not isinstance(value, str) or not _UUID_RE.match(value):
            _fail(f"entry '{track_id}' key '{key}' is {value!r}. It must be "
                  f"a canonical UUID.")
    for key in ("package_version", "minimum_client_version",
                "minimum_apworld_version"):
        value = entry[key]
        if not isinstance(value, str) or not value or any(
                ord(ch) < 0x20 or ch in '\"\\' for ch in value):
            _fail(f"entry '{track_id}' key '{key}' is not a plain non-empty "
                  f"version string.")
    navigation = entry["navigation"]
    if not isinstance(navigation, Mapping) or set(navigation) != {"uuid", "revision"}:
        _fail(f"entry '{track_id}' key 'navigation' must contain exactly "
              f"'uuid' and 'revision'.")
    if (not isinstance(navigation["uuid"], str)
            or not _UUID_RE.match(navigation["uuid"])):
        _fail(f"entry '{track_id}' navigation.uuid must be a canonical UUID.")
    if not _is_int(navigation["revision"]) or navigation["revision"] < 1:
        _fail(f"entry '{track_id}' navigation.revision must be a positive "
              f"whole number.")
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
    if entry.get("boxes", False):
        _fail(f"entry '{track_id}' enables AP boxes, but Alpha6 has no "
              f"package-bound AP-box placement identity. Use boxes: false.")
    _validate_flags(track_id, entry["flags"])

    # Alpha6 ships one release-owned package registry entry. Generation must
    # never create a seed that a matching Alpha6 client will correctly refuse.
    expected = BABY_T_PARK_EXAMPLE
    for key in ("package_uuid", "package_version", "minimum_client_version",
                "minimum_apworld_version", "lev_sha256", "vrm_sha256",
                "navigation", "laps", "flags"):
        actual = entry[key]
        wanted = expected[key]
        if key in ("lev_sha256", "vrm_sha256"):
            actual = actual.lower()
            wanted = wanted.lower()
        if actual != wanted:
            _fail(f"entry '{track_id}' key '{key}' does not match the "
                  f"Alpha6 package registry.")


def validate_custom_tracks(mapping) -> None:
    """Reject an unusable `custom_tracks` descriptor with a clear OptionError.

    An empty mapping is the option being off and is always valid. Anything
    else may contain entries up to the frozen 32-slot datapackage capacity, but
    every entry must be known to this build and complete. Alpha6's approved
    registry currently contains only Baby T Park and only the Purple cup
    assignment; accepting more packages and destination roles is later policy,
    not something the generic identity reservation silently enables. A partly
    described custom track is not a smaller feature, it is a seed whose
    generation logic and whose game disagree about its assigned destination.

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
    from .custom_track_locations import CUSTOM_TRACK_SLOT_COUNT
    if len(mapping) > CUSTOM_TRACK_SLOT_COUNT:
        _fail(f"has {len(mapping)} entries, but the frozen datapackage reserves "
              f"{CUSTOM_TRACK_SLOT_COUNT} generic custom-track slots.")
    claimed_destinations = {}
    for track_id, entry in mapping.items():
        if track_id not in KNOWN_TRACK_IDS:
            _fail(f"has unknown track id {track_id!r}. This build knows: "
                  f"{', '.join(KNOWN_TRACK_IDS)}.")
        _validate_entry(track_id, entry)
        replaces = entry["replaces"]
        prior = claimed_destinations.get(replaces)
        if prior is not None:
            _fail(f"entries '{prior}' and '{track_id}' both replace "
                  f"{replaces!r}. Custom packages need distinct destination "
                  f"assignments.")
        claimed_destinations[replaces] = track_id


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
    normalized = {}
    for slot, track_id in enumerate(sorted(mapping), start=1):
        entry = mapping[track_id]
        normalized[track_id] = {
            "slot": slot,
            "package_uuid": entry["package_uuid"].lower(),
            "package_version": entry["package_version"],
            "minimum_client_version": entry["minimum_client_version"],
            "minimum_apworld_version": entry["minimum_apworld_version"],
            "lev_sha256": entry["lev_sha256"].lower(),
            "vrm_sha256": entry["vrm_sha256"].lower(),
            "navigation": {
                "uuid": entry["navigation"]["uuid"].lower(),
                "revision": int(entry["navigation"]["revision"]),
            },
            "laps": int(entry["laps"]),
            "replaces": entry["replaces"],
            "host_level_id": int(entry.get("host_level_id",
                                           DEFAULT_HOST_LEVEL_ID)),
            # Fail closed until a package-bound AP-box placement identity is
            # part of the same descriptor contract.
            "boxes": bool(entry.get("boxes", False)),
            "flags": {
                **{k: bool(entry["flags"][k]) for k in BOOLEAN_FLAGS},
                **{k: int(entry["flags"][k]) for k in COUNT_FLAGS},
            },
        }
    return normalized


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


def effective_custom_destinations(tracks: Mapping[str, Mapping],
                                  titles: Mapping[str, str] = None
                                  ) -> Dict[int, Tuple[str, str]]:
    """{displaced cup LevelID: (track id, track title)}.

    This is the spoiler's effective-destination representation for a custom
    replacement. A displaced cup's destination still reads as the cup LevelID
    on the wire -- native serves the custom bytes for that race -- so the
    spoiler translates every resolved cup destination back into the custom
    track the player actually loads. Keying by cup LevelID keeps each physical
    pad honest independently: two packages displacing two different cups can
    never collapse onto the wrong track.

    ``titles`` defaults to the compiled ``TRACK_DISPLAY_NAMES`` and is
    overridable so spoiler fixtures can exercise generic entries without
    touching the registry.
    """
    resolved_titles = titles if titles is not None else TRACK_DISPLAY_NAMES
    out: Dict[int, Tuple[str, str]] = {}
    for track_id, entry in tracks.items():
        _cup_region, cup_lid = REPLACEABLE_DESTINATIONS[entry["replaces"]]
        out[cup_lid] = (track_id, resolved_titles.get(track_id, track_id))
    return out


def replacement_trophy_location(tracks: Mapping[str, Mapping],
                                vanilla_location: str) -> str:
    """Return the generic custom Trophy identity replacing a cup Gem check.

    Non-displaced names pass through unchanged.  This lets every pinned-Gem
    path share one redirect and prevents a removed ``<Colour> Gem Cup: Gem``
    Location from being looked up after custom-region creation.
    """
    from .custom_track_locations import CUSTOM_TRACK_LOCATION_CLASS
    for cup_region, track_id in displaced_cups(tracks).items():
        if vanilla_location == f"{cup_region}: Gem":
            return CUSTOM_TRACK_LOCATION_CLASS.trophy_name(
                int(tracks[track_id]["slot"]))
    return vanilla_location


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


def custom_tracks_to_wire(tracks: Mapping[str, Mapping], options=None) -> Dict[str, object]:
    """Serialize the normalized descriptor for slot_data.

    A LIST of self-describing entries rather than an id-keyed object: native's
    seed-config reader looks fields up by name and does not enumerate unknown
    keys, so it finds its track by scanning for the `replaces_cup_level_id` it
    cares about. The cup is emitted as a LevelID (104), the same currency
    `warp_pad_map`, `warp_pad_unlock` and `gem_cup_legs` already use, rather
    than the YAML's human-facing `replaces` word.
    """
    from .custom_track_locations import CUSTOM_TRACK_LOCATION_CLASS
    from .podium import created_rung_keys_from_options
    created_rungs = (created_rung_keys_from_options(options)
                     if options is not None else [])
    return {
        "enabled": True,
        "version": CUSTOM_TRACKS_WIRE_VERSION,
        "tracks": [
            {
                "id": track_id,
                "slot": entry["slot"],
                "package_uuid": entry["package_uuid"],
                "package_version": entry["package_version"],
                "minimum_client_version": entry["minimum_client_version"],
                "minimum_apworld_version": entry["minimum_apworld_version"],
                "lev_sha256": entry["lev_sha256"],
                "vrm_sha256": entry["vrm_sha256"],
                "navigation": dict(entry["navigation"]),
                "laps": entry["laps"],
                "host_level_id": entry["host_level_id"],
                "replaces_cup_level_id":
                    REPLACEABLE_DESTINATIONS[entry["replaces"]][1],
                "boxes": entry["boxes"],
                "flags": dict(entry["flags"]),
                "locations": {
                    "trophy": CUSTOM_TRACK_LOCATION_CLASS.code_for(
                        entry["slot"], "trophy"),
                    "podium": CUSTOM_TRACK_LOCATION_CLASS.slot_codes(
                        entry["slot"], created_rungs),
                },
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
    from .custom_track_locations import CUSTOM_TRACK_SLOT_COUNT
    if (not isinstance(entries, (list, tuple)) or not entries
            or len(entries) > CUSTOM_TRACK_SLOT_COUNT):
        return _give_up("does not hold between one and 32 track entries")
    rebuilt = {}
    seen_slots = set()
    for wire_entry in entries:
        if not isinstance(wire_entry, Mapping):
            return _give_up("holds a track entry that is not an object")
        track_id = wire_entry.get("id")
        cup_lid = wire_entry.get("replaces_cup_level_id")
        slot = wire_entry.get("slot")
        if track_id not in KNOWN_TRACK_IDS or cup_lid not in _CUP_LID_TO_REPLACES:
            return _give_up(f"names track {track_id!r} replacing cup {cup_lid!r}, "
                            f"which this build does not know")
        if (not isinstance(slot, int) or isinstance(slot, bool)
                or not 1 <= slot <= CUSTOM_TRACK_SLOT_COUNT or slot in seen_slots):
            return _give_up(f"assigns invalid or duplicate generic slot {slot!r}")
        seen_slots.add(slot)
        flags = wire_entry.get("flags")
        if not isinstance(flags, Mapping):
            return _give_up("holds a track entry without a flags object")
        rebuilt[track_id] = {
            "package_uuid": wire_entry.get("package_uuid"),
            "package_version": wire_entry.get("package_version"),
            "minimum_client_version": wire_entry.get("minimum_client_version"),
            "minimum_apworld_version": wire_entry.get("minimum_apworld_version"),
            "lev_sha256": wire_entry.get("lev_sha256"),
            "vrm_sha256": wire_entry.get("vrm_sha256"),
            "navigation": wire_entry.get("navigation"),
            "laps": wire_entry.get("laps"),
            "replaces": _CUP_LID_TO_REPLACES[cup_lid],
            "host_level_id": wire_entry.get("host_level_id"),
            "boxes": wire_entry.get("boxes"),
            "flags": dict(flags),
        }
    try:
        # Re-run the option validator on the rebuilt descriptor. The wire and
        # the YAML then have exactly one definition of "well formed", so a
        # tracker can never reconstruct a seed shape generation would have
        # refused.
        normalized = normalize_custom_tracks(rebuilt)
        if any(normalized[k]["slot"] != next(
                int(e["slot"]) for e in entries if e.get("id") == k)
               for k in normalized):
            return _give_up("does not use the canonical sorted generic-slot assignment")
        return normalized
    except OptionError as exc:
        return _give_up(f"fails descriptor validation ({exc})")
