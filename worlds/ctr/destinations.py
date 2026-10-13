"""The one destination table.

Every consumer that names a track, a gem cup, a pad destination or a custom
slot reads its keys from here instead of retyping them. A destination key is
the name the rest of the apworld already uses (the region name of a retail
track, the pad track key of a gem cup such as "Red Cup", or "Cortex Vortex"),
so no item name, location name, id or slot_data value changes.

WHAT LIVES HERE (identity and hub facts shared by several modules)

  * the key, its kind, the Gem Cup region it maps to (cups only);
  * the native LevelID, read from data/warp_pad_ids.json (the single LevelID
    source) and never retyped;
  * the static hub Key gate, the vanilla CTR Token colour, the boss hub a race
    belongs to and the boss garage that launches it;
  * the custom-track generic slot count and region naming.

WHAT STAYS WITH ITS OWNER

Subsystem facts (item box counts and rules, finish capabilities, difficulty
groups, USF relic tiers, podium and letter code blocks) stay in their own
modules. They reference a destination by key and are checked against this
table at import (`require`, `require_all`, `check_keys`), so a rename or a
membership change that one consumer misses fails at import or test collection
instead of silently diverging.

ORDER

`DESTINATIONS` is in the order the hub table has always been iterated
(sphere search and pad exits depend on it). Code-block orders (box, podium,
letter tracks) are read from data/locations.json by `tracks_with_suffix`.

This module must stay a leaf: it imports nothing from the rest of the package.
"""
import json
import pkgutil
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

KIND_RACE = "race"        # the 16 retail trophy-race tracks
KIND_ARENA = "arena"      # the 4 battle-arena crystal pads
KIND_TRIAL = "trial"      # Slide Coliseum, Turbo Track
KIND_CUP = "cup"          # the 5 Gem Cups
KIND_PAD_TRACK = "pad_track"  # Cortex Vortex, a destination with no pad of its own

BOSS_ROO = "ripper_roo"
BOSS_PAPU = "papu_papu"
BOSS_JOE = "komodo_joe"
BOSS_PINSTRIPE = "pinstripe"

CORTEX_VORTEX = "Cortex Vortex"
#: Virtual destination ID, outside {0..27, 100..104}.
CORTEX_VORTEX_LEVEL_ID = 110


@dataclass(frozen=True)
class Destination:
    key: str
    kind: str
    hub_keys: Optional[int] = None
    token_colour: Optional[str] = None
    boss: Optional[str] = None
    garage: Optional[str] = None
    region: Optional[str] = None
    level_id_override: Optional[int] = None

    @property
    def region_name(self) -> str:
        return self.region or self.key

    @property
    def pad_name(self) -> str:
        return f"{self.key} Warp Pad"

    @property
    def level_id(self) -> int:
        if self.level_id_override is not None:
            return self.level_id_override
        return _PAD_LEVEL_IDS[self.key]


def _load_pads() -> Dict[str, Dict]:
    data = json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8"))
    return data["pads"]


_PADS = _load_pads()
_PAD_LEVEL_IDS = {name[: -len(" Warp Pad")]: meta["level_id"]
                  for name, meta in _PADS.items()}

_R, _A, _T, _C = KIND_RACE, KIND_ARENA, KIND_TRIAL, KIND_CUP

DESTINATIONS: Tuple[Destination, ...] = (
    # N. Sanity Beach -- no hub gate (Skull Rock crystal at hub floor 0)
    Destination("Crash Cove", _R, 0, "Red", BOSS_ROO),
    Destination("Roo's Tubes", _R, 0, "Green", BOSS_ROO,
                garage="Ripper Roo Garage"),
    Destination("Mystery Caves", _R, 0, "Red", BOSS_ROO),
    Destination("Sewer Speedway", _R, 0, "Blue", BOSS_ROO),
    Destination("Skull Rock", _A, 0),
    # Lost Ruins -- Key 1 (Rampage Ruins crystal at hub floor Key 1)
    Destination("Coco Park", _R, 1, "Green", BOSS_PAPU),
    Destination("Tiger Temple", _R, 1, "Blue", BOSS_PAPU),
    Destination("Papu's Pyramid", _R, 1, "Red", BOSS_PAPU,
                garage="Papu Papu Garage"),
    Destination("Dingo Canyon", _R, 1, "Yellow", BOSS_PAPU),
    Destination("Rampage Ruins", _A, 1),
    # Glacier Park -- Key 2 (Rocky Road crystal at hub floor Key 2)
    Destination("Blizzard Bluff", _R, 2, "Red", BOSS_JOE),
    Destination("Dragon Mines", _R, 2, "Blue", BOSS_JOE,
                garage="Komodo Joe Garage"),
    Destination("Polar Pass", _R, 2, "Green", BOSS_JOE),
    Destination("Tiny Arena", _R, 2, "Yellow", BOSS_JOE),
    Destination("Rocky Road", _A, 2),
    # Citadel City -- Key 3 (Nitro Court crystal at hub floor Key 3)
    Destination("Hot Air Skyway", _R, 3, "Yellow", BOSS_PINSTRIPE,
                garage="Pinstripe Garage"),
    Destination("Cortex Castle", _R, 3, "Green", BOSS_PINSTRIPE),
    Destination("N. Gin Labs", _R, 3, "Blue", BOSS_PINSTRIPE),
    Destination("Oxide Station", _R, 3, "Yellow", BOSS_PINSTRIPE,
                garage="N. Oxide Garage"),
    Destination("Nitro Court", _A, 3),
    # Gem Stone Valley TRIAL pads -- behind Key 1. Slide Coliseum and Turbo
    # Track have no trophy race and no CTR Token challenge in the vanilla graph:
    # only the 3 relic Time Trials. They are single-stage (no stage 2) but do
    # get a randomized stage-1 entry requirement (the open model); their vanilla
    # relic gate is replaced by it in Rules.add_warp_pad_unlock_rules, keeping
    # only the Key 1 hub gate.
    Destination("Slide Coliseum", _T, 1),
    Destination("Turbo Track", _T, 1),
    # Gem Stone Valley GEM-CUP pads -- behind Key 2 (the Cups Room hub gate:
    # 'Gem Stone Valley <-> Cups Room' = has('Key', 2) in data/world.json). Like
    # the trials they are single-stage with a randomized stage-1 requirement
    # ANDed on top of the Key 2 gate. The pad track key is "<Colour> Cup" (so
    # the pad exit is "<Colour> Cup Warp Pad"); the destination region is
    # "<Colour> Gem Cup". Gem cups are destination-shuffle-eligible
    # (CATEGORY_POOLS['cups']) when the 'cups' category is selected AND
    # include_gem_cups puts their content in the seed.
    Destination("Red Cup", _C, 2, region="Red Gem Cup"),
    Destination("Green Cup", _C, 2, region="Green Gem Cup"),
    Destination("Blue Cup", _C, 2, region="Blue Gem Cup"),
    Destination("Yellow Cup", _C, 2, region="Yellow Gem Cup"),
    Destination("Purple Cup", _C, 2, region="Purple Gem Cup"),
)

#: Cortex Vortex: a destination with no pad of its own (kept out of
#: DESTINATIONS because the hub table and pad exits iterate that one).
CORTEX_VORTEX_DESTINATION = Destination(
    CORTEX_VORTEX, KIND_PAD_TRACK, level_id_override=CORTEX_VORTEX_LEVEL_ID)

BY_KEY: Dict[str, Destination] = {d.key: d for d in DESTINATIONS}
BY_KEY[CORTEX_VORTEX] = CORTEX_VORTEX_DESTINATION
assert len(BY_KEY) == len(DESTINATIONS) + 1, "duplicate destination key"

# Every pad in the LevelID file must have exactly one destination, and the other
# way round, so a pad added to one place cannot be missed by the other.
assert set(_PAD_LEVEL_IDS) == {d.key for d in DESTINATIONS}, \
    "data/warp_pad_ids.json and the destination table disagree"
assert all(_PADS[d.pad_name]["kind"] == {_R: "race", _A: "crystal",
                                         _T: "trial", _C: "cup"}[d.kind]
           for d in DESTINATIONS), "pad kind disagrees with destination kind"


def of_kind(*kinds: str) -> Tuple[Destination, ...]:
    return tuple(d for d in DESTINATIONS if d.kind in kinds)


def keys_of_kind(*kinds: str) -> Tuple[str, ...]:
    return tuple(d.key for d in of_kind(*kinds))


def require(key: str) -> str:
    """Return `key` if it is a known destination, else fail loudly."""
    if key not in BY_KEY:
        raise KeyError(f"unknown destination key {key!r}")
    return key


def require_all(keys: Iterable[str]) -> Tuple[str, ...]:
    """Validate and return every key (order kept)."""
    return tuple(require(k) for k in keys)


def check_keys(mapping_keys: Iterable[str], expected: Iterable[str],
               what: str) -> None:
    """Fail when a per-destination table does not cover exactly `expected`."""
    have, want = set(mapping_keys), set(expected)
    if have != want:
        raise ValueError(
            f"{what}: keys differ from the destination table "
            f"(missing {sorted(want - have)}, unknown {sorted(have - want)})")


def level_ids_for(names: Iterable[str]) -> Dict[str, int]:
    """{destination key -> native LevelID} for `names`, in LevelID-file order."""
    wanted = set(names)
    unknown = wanted - set(BY_KEY)
    if unknown:
        raise KeyError(f"unknown destination keys {sorted(unknown)}")
    return {d.key: d.level_id for d in DESTINATIONS if d.key in wanted}


def tracks_with_suffix(suffix: str) -> List[str]:
    """Region names owning a location ending in `suffix`, in code order.

    The box, podium and letter families all read their canonical order from
    data/locations.json this way; every result is checked against the table.
    """
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8"))
    rows = [(loc["code"], loc["region"]) for loc in data
            if loc["name"].endswith(suffix) and loc["code"] is not None]
    return list(require_all(region for _code, region in sorted(rows)))


# -- derived views ----------------------------------------------------------

#: The 16 retail trophy-race tracks in hub order.
RACE_TRACKS: Tuple[str, ...] = keys_of_kind(KIND_RACE)
#: The two Gem Stone Valley trial tracks, in LevelID order.
TRIAL_TRACKS: Tuple[str, ...] = keys_of_kind(KIND_TRIAL)
assert TRIAL_TRACKS == ("Slide Coliseum", "Turbo Track")
ARENA_TRACKS: Tuple[str, ...] = keys_of_kind(KIND_ARENA)
CUP_PAD_TRACKS: Tuple[str, ...] = keys_of_kind(KIND_CUP)

#: Gem Cup region name -> cup LevelID, in LevelID order (draw order of the
#: gem-cup leg randomizer).
CUP_LEVEL_IDS: Tuple[Tuple[str, int], ...] = tuple(
    (d.region_name, d.level_id) for d in of_kind(KIND_CUP))


def hub_static() -> Dict[str, List[Tuple[str, int]]]:
    """Fresh {pad track -> static hub gate} (the sphere search's HUB_STATIC)."""
    return {d.key: ([("Key", d.hub_keys)] if d.hub_keys else [])
            for d in DESTINATIONS}


def token_colours() -> Dict[str, str]:
    return {d.key: d.token_colour for d in DESTINATIONS if d.token_colour}


def boss_garage_tracks() -> Dict[str, str]:
    """{boss garage -> retail boss-race destination}, hub order."""
    return {d.garage: d.key for d in DESTINATIONS if d.garage}


def boss_hub_level_ids() -> Dict[str, List[int]]:
    """{boss -> LevelIDs of the four tracks in that boss's hub}."""
    out: Dict[str, List[int]] = {}
    for d in DESTINATIONS:
        if d.boss:
            out.setdefault(d.boss, []).append(d.level_id)
    return out


# -- custom tracks ----------------------------------------------------------

#: Generic custom-track slots: one per destination surface. Named custom
#: blocks for known tracks belong beside this, keyed by track id.
CUSTOM_TRACK_SLOT_COUNT = 32


def custom_slot_region(slot: int) -> str:
    return f"Custom Track {slot}"


def cup_destination(region: str) -> Tuple[str, int]:
    """(cup region name, cup LevelID) of a Gem Cup region, validated."""
    for name, lid in CUP_LEVEL_IDS:
        if name == region:
            return name, lid
    raise KeyError(f"unknown gem cup region {region!r}")
