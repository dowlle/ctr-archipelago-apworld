"""Named id blocks for custom tracks the apworld knows (#306, path C).

A known custom track gets its own permanent block of location and item ids,
the way Cortex Vortex has one, so Universal Tracker, hints, the server log,
the room tracker and the spoiler all show its real name. Tracks the apworld
does not know keep the generic `Custom Track N` slot ids (path B+).

WHERE THE ROWS COME FROM

`destinations.NAMED_TRACKS`, read from data/named_tracks.json. That file is
generated from one pinned commit of the public track registry; the registry
assigns `block_index` when a track is promoted, so the apworld only reads it
and never invents one (tools/build_named_tracks.py). Tests use
test/fixtures/named_tracks_fixture.json, which is test data and never a
shipped name.

ID MATH (codes are computed, never stored by hand)

    location = NAMED_LOCATION_BASE + block_index * LOCATION_BUDGET + offset
    item     = NAMED_ITEM_BASE     + block_index * ITEM_BUDGET     + offset

Bases and budgets were ruled on 2026-10-13: locations from 35200000 with 200
per track (35200000..37199999 for 10,000 tracks), items from 35100000 with 5
per track (35100000..35149999).

NAMES

Location `<ap_name>: <suffix>` and item `Letter <C/T/R> (<ap_name>)`, the
same spellings Cortex Vortex uses. `ap_name` is frozen from the first release
that ships the block; a later title change is display only.

MINTED (0.3.0 id step, 2026-10-15): data/named_tracks.json holds the 82 `mint`
entries of registry commit e01959af45848777e11508e8bf357fd143f9f68b, written
by tools/build_named_tracks.py. Blocks 14 and 68 (reserved until a race mode is
confirmed) and 16 (cortex-vortex, builtin: it maps to the hard-coded Cortex
Vortex block) are not minted and their numbers are never reused.

DATAPACKAGE STABILITY

Every row's complete family registers unconditionally (all LOCATION_OFFSETS
and ITEM_OFFSETS), whatever a seed creates. The offset tables are append only:
an offset, once shipped, keeps its family and spelling forever. The 0.3.0 step
added 15 Cup Leg Victory, 16 Complete One Lap and 20 to 34 Item Box 1 to 15;
RESERVED_LOCATION_OFFSETS lists the rest of the ruled layout. Item offsets 3
and 4 are unassigned. New offsets are minted only through the unfreeze
register. FROZEN-NAME WARNING: once a block ships, its ids and names are
permanent; freeze_violations() and test_named_tracks.py enforce that.
The rule is checked against an independent baseline: the lock file
(test/fixtures/named_tracks_lock.json) as last published. CI fetches the PR
base's copy (the previous commit on a push) into CTR_NAMED_LOCK_BASELINE; a
local run reads it from git (origin/dev/custom-pad-0.3.0, then origin/main).
Regenerating the lock in the same branch therefore cannot hide a changed
ap_name, block_index, name or id. Only appending is accepted.
"""
import json
import pkgutil
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from BaseClasses import ItemClassification

from . import destinations
from .destinations import NamedTrack
from .location_class import LocationClass

NAMED_ITEM_BASE = 35100000
NAMED_LOCATION_BASE = 35200000
LOCATION_BUDGET = 200
ITEM_BUDGET = 5
NAMED_TRACK_LIMIT = destinations.NAMED_TRACK_LIMIT

#: (key, offset, name suffix). APPEND ONLY. The podium rungs follow
#: podium.SLOT_ORDER; the relic tiers and letters follow Cortex Vortex.
LOCATION_OFFSETS: Tuple[Tuple[str, int, str], ...] = (
    ("trophy", 0, "Trophy Race"),
    ("held_1st", 1, "Held 1st"),
    ("held_3rd", 2, "Held 3rd"),
    ("held_5th", 3, "Held 5th"),
    ("finish_podium", 4, "Finish on Podium"),
    ("finish_any", 5, "Finish (Any Position)"),
    ("relic_sapphire", 6, "Sapphire Time Trial"),
    ("relic_gold", 7, "Gold Time Trial"),
    ("relic_platinum", 8, "Platinum Time Trial"),
    ("ctr_token", 9, "CTR Token Challenge"),
    ("relic_perfect", 10, "Relic Race Perfect"),
    ("letter_c", 11, "Letter C"),
    ("letter_t", 12, "Letter T"),
    ("letter_r", 13, "Letter R"),
    ("wumpa", 14, "Reach 10 Wumpa"),
    # 0.3.0 minting step (ruled 2026-10-13 22:02 CEST, register answer 7).
    # 17 to 19 stay spare for later per-track race checks.
    ("cup_leg_victory", 15, "Cup Leg Victory"),
    ("lap", 16, "Complete One Lap"),
) + tuple((f"item_box_{n}", 19 + n, f"Item Box {n}") for n in range(1, 16))
#: Offsets reserved in the 0.3.0 layout and not minted: 17 to 19 spare race
#: checks, Item Box 16 to 100 at 35 to 119, 120 to 140 certified custom arenas
#: (crystals and completion; a race block never carries them), 141 to 199 spare.
RESERVED_LOCATION_OFFSETS: Tuple[Tuple[int, int, str], ...] = (
    (17, 19, "spare per-track race checks"),
    (35, 119, "Item Box 16 to Item Box 100"),
    (120, 140, "certified custom arenas only"),
    (141, 199, "spare"),
)
#: (key, offset, letter). APPEND ONLY.
ITEM_OFFSETS: Tuple[Tuple[str, int, str], ...] = (
    ("letter_c", 0, "C"),
    ("letter_t", 1, "T"),
    ("letter_r", 2, "R"),
)
_LOCATION_OFFSET = {key: (offset, suffix) for key, offset, suffix in LOCATION_OFFSETS}
_ITEM_OFFSET = {key: (offset, letter) for key, offset, letter in ITEM_OFFSETS}

assert all(0 <= o < LOCATION_BUDGET for _k, o, _s in LOCATION_OFFSETS)
assert all(0 <= o < ITEM_BUDGET for _k, o, _s in ITEM_OFFSETS)
assert len({o for _k, o, _s in LOCATION_OFFSETS}) == len(LOCATION_OFFSETS)
assert len({o for _k, o, _s in ITEM_OFFSETS}) == len(ITEM_OFFSETS)
assert not {o for _k, o, _s in LOCATION_OFFSETS} & {
    o for lo, hi, _l in RESERVED_LOCATION_OFFSETS for o in range(lo, hi + 1)}

#: The two named ranges, inclusive.
NAMED_LOCATION_RANGE = (NAMED_LOCATION_BASE,
                        NAMED_LOCATION_BASE + NAMED_TRACK_LIMIT * LOCATION_BUDGET - 1)
NAMED_ITEM_RANGE = (NAMED_ITEM_BASE, NAMED_ITEM_BASE + NAMED_TRACK_LIMIT * ITEM_BUDGET - 1)

#: Every other CTR id range, minted or only reserved, inclusive. Mirrors the
#: register in "CTR Archipelago - Considered datapackage unfreezes" so a named
#: block can never land on an approved reservation that is not minted yet.
#: Minted ids are also checked one by one against the live datapackage.
RESERVED_ID_RANGES: Tuple[Tuple[int, int, str], ...] = (
    (35010000, 35010999, "items: positional table, letters, Cortex Vortex letters"),
    (35011000, 35015999, "retail locations, relic perfect, lettersanity, AP boxes, podium"),
    (35016000, 35016099, "itemsanity"),
    (35016100, 35016131, "Reach 10 Wumpa: global, retail, custom roles"),
    (35016200, 35016299, "trial trophy"),
    (35016300, 35016559, "custom race family v1 (32 slots)"),
    (35016600, 35016731, "custom Reach 10 Wumpa, slot owned"),
    (35016800, 35016951, "Cup Leg Victory, retail and generic custom"),
    (35017000, 35018979, "AP boxes on custom tracks"),
    (35019000, 35019791, "custom race family v2 (35019000..191 never used)"),
    (35020000, 35020395, "custom letter locations"),
    (35021000, 35021395, "custom letter items"),
    (35022000, 35022395, "custom relic tiers"),
    (35023000, 35023131, "custom CTR Token Challenge"),
    (35024000, 35024131, "custom Relic Race Perfect"),
    (35025000, 35025015, "Hit Character encounters"),
    (35026000, 35026014, "Cortex Vortex named block"),
    (35027000, 35027027, "cup points wins and Cortex Vortex Cup Leg Victory"),
    (35027100, 35027199, "cup points wins, later names (reserved)"),
    (35027200, 35027226, "cup sweeps, named cups"),
    (35027300, 35027399, "cup sweeps, later names (reserved)"),
    (35028000, 35028017, "lap completion, retail"),
    (35028100, 35028231, "lap completion, generic custom"),
    (35028300, 35028304, "cup sweeps, Gem Cups"),
    (35028400, 35028479, "crystals, retail arenas"),
    (35028500, 35028599, "arcade arena checks and expansion"),
    (35028600, 35028799, "Wumpa Shop (reserved)"),
)
for _first, _last, _label in RESERVED_ID_RANGES:
    for _lo, _hi in (NAMED_LOCATION_RANGE, NAMED_ITEM_RANGE):
        assert _last < _lo or _first > _hi, f"named block overlaps {_label}"
assert NAMED_ITEM_RANGE[1] < NAMED_LOCATION_RANGE[0]
assert NAMED_LOCATION_RANGE[1] < 2 ** 31, "keep named ids in a signed 32-bit range"


# -- id math and names --------------------------------------------------------

def _block(block_index: int) -> int:
    if type(block_index) is not int or not 0 <= block_index < NAMED_TRACK_LIMIT:
        raise ValueError(f"block_index must be an integer in 0..{NAMED_TRACK_LIMIT - 1}")
    return block_index


def location_code(block_index: int, key: str) -> int:
    return NAMED_LOCATION_BASE + _block(block_index) * LOCATION_BUDGET + _LOCATION_OFFSET[key][0]


def item_code(block_index: int, key: str) -> int:
    return NAMED_ITEM_BASE + _block(block_index) * ITEM_BUDGET + _ITEM_OFFSET[key][0]


def location_name(ap_name: str, key: str) -> str:
    return f"{ap_name}: {_LOCATION_OFFSET[key][1]}"


def item_name(ap_name: str, key: str) -> str:
    return f"Letter {_ITEM_OFFSET[key][1]} ({ap_name})"


def block_of_location(code: int) -> Optional[Tuple[int, int]]:
    """(block_index, offset) for a code inside the named location range."""
    if type(code) is not int or not NAMED_LOCATION_RANGE[0] <= code <= NAMED_LOCATION_RANGE[1]:
        return None
    return divmod(code - NAMED_LOCATION_BASE, LOCATION_BUDGET)


def track_locations(track: NamedTrack) -> List[Tuple[str, int]]:
    return [(location_name(track.ap_name, key), location_code(track.block_index, key))
            for key, _offset, _suffix in LOCATION_OFFSETS]


def track_items(track: NamedTrack) -> List[Tuple[str, int]]:
    return [(item_name(track.ap_name, key), item_code(track.block_index, key))
            for key, _offset, _letter in ITEM_OFFSETS]


# -- validation ---------------------------------------------------------------

def validate_tracks(tracks: Sequence[NamedTrack],
                    other_location_ids: Mapping[str, int] = None,
                    other_item_ids: Mapping[str, int] = None) -> None:
    """Fail on a name that is not stable under sanitizing, or on any name or
    id that collides with the rest of the CTR datapackage."""
    from .custom_track_titles import is_sanitized, reserved_stems
    for track in tracks:
        if not is_sanitized(track.ap_name):
            raise ValueError(f"named tracks: {track.track_key}: ap_name "
                             f"{track.ap_name!r} is not a sanitized title")
        if other_location_ids is not None and track.ap_name.casefold() in reserved_stems():
            raise ValueError(f"named tracks: {track.track_key}: ap_name "
                             f"{track.ap_name!r} is a retail name; it needs \"(Custom)\"")
    for other, own in ((other_location_ids, [p for t in tracks for p in track_locations(t)]),
                       (other_item_ids, [p for t in tracks for p in track_items(t)])):
        if other is None:
            continue
        codes = {code: name for name, code in other.items() if code is not None}
        for name, code in own:
            if name in other:
                raise ValueError(f"named tracks: {name!r} is already a CTR name")
            if code in codes:
                raise ValueError(f"named tracks: {name!r} takes code {code}, "
                                 f"already {codes[code]!r}")
        stray = [n for n, c in other.items() if c is not None and (
            NAMED_LOCATION_RANGE[0] <= c <= NAMED_LOCATION_RANGE[1]
            or NAMED_ITEM_RANGE[0] <= c <= NAMED_ITEM_RANGE[1])]
        if stray:
            raise ValueError(f"named tracks: {stray[:3]} sit inside a named block range")


# -- freeze (append only) -------------------------------------------------------

def lock_rows(tracks: Iterable[NamedTrack]) -> List[Dict[str, object]]:
    """The freeze record of shipped blocks: identity plus every name and code."""
    return [{"track_key": t.track_key, "block_index": t.block_index, "ap_name": t.ap_name,
             "locations": dict(track_locations(t)), "items": dict(track_items(t))}
            for t in sorted(tracks, key=lambda t: t.block_index)]


def freeze_violations(frozen: Sequence[Mapping], tracks: Sequence[NamedTrack]) -> List[str]:
    """Everything that breaks the freeze between a lock and the current rows.

    Allowed: appending a track with a block_index above every frozen one, and
    appending offsets to the layout (new names inside an existing block).
    Refused: a missing track, any changed block_index, ap_name, name or code.
    """
    problems: List[str] = []
    current = {t.track_key: t for t in tracks}
    by_index = {t.block_index: t for t in tracks}
    highest = max((int(row["block_index"]) for row in frozen), default=-1)
    for row in frozen:
        key, index = row["track_key"], row["block_index"]
        track = current.get(key)
        if track is None:
            problems.append(f"{key}: frozen block {index} was removed")
            continue
        if track.block_index != index:
            problems.append(f"{key}: block_index changed {index} -> {track.block_index}")
        if track.ap_name != row["ap_name"]:
            problems.append(f"{key}: ap_name changed {row['ap_name']!r} -> {track.ap_name!r}")
        now = lock_rows([track])[0]
        for family in ("locations", "items"):
            for name, code in row[family].items():
                if now[family].get(name) != code:
                    problems.append(f"{key}: {family[:-1]} {name!r} no longer has code {code}")
        if by_index.get(index) not in (None, track):
            problems.append(f"block {index} now belongs to {by_index[index].track_key}")
    frozen_keys = {row["track_key"] for row in frozen}
    for track in tracks:
        if track.track_key not in frozen_keys and track.block_index <= highest:
            problems.append(f"{track.track_key}: new block {track.block_index} is not "
                            f"above the highest frozen block {highest} (append only)")
    return problems


def layout_violations(frozen_layout: Mapping[str, Sequence]) -> List[str]:
    """The offset tables may only grow at the end."""
    problems = []
    for label, live in (("locations", LOCATION_OFFSETS), ("items", ITEM_OFFSETS)):
        pinned = [tuple(row) for row in frozen_layout[label]]
        if list(live[:len(pinned)]) != pinned:
            problems.append(f"{label} offset layout changed; it is append only")
    return problems


# -- datapackage registration ---------------------------------------------------

class NamedTrackLocationClass(LocationClass):
    """Every named track's complete location family, registered unconditionally.

    On the content-plan path creation is decided by the plan's check
    registry, which picks a named code when a package's track key has a block.
    On the legacy `custom_tracks` path (#133) a track with a block creates its
    Trophy Race, podium rungs, letters, CTR Token Challenge and Reach 10 Wumpa
    from the block; `created_location_names` lists those.
    """
    key = "named_track"
    display_name = "Named Custom Track Checks"

    def __init__(self, tracks: Sequence[NamedTrack]):
        self.tracks = tuple(tracks)
        self.code_blocks = tuple(sorted({code - code % 1000
                                         for t in self.tracks
                                         for _n, code in track_locations(t)}))

    def all_locations(self):
        return [(name, code, track.ap_name)
                for track in self.tracks for name, code in track_locations(track)]

    def created_location_names(self, options) -> List[str]:
        from .custom_track_ids import created_named_location_names
        return created_named_location_names(options)

    def location_name(self, track_key: str, key: str = "trophy") -> str:
        for track in self.tracks:
            if track.track_key == track_key:
                return location_name(track.ap_name, key)
        raise KeyError(track_key)


def item_data(tracks: Sequence[NamedTrack]) -> Tuple[Dict[str, object], ...]:
    """Letter items for every named track, count 0 until a feature pools them."""
    return tuple({"name": name, "code": code, "count": 0,
                  "classification": ItemClassification.progression}
                 for track in tracks for name, code in track_items(track))


NAMED_TRACKS = destinations.NAMED_TRACKS
NAMED_TRACK_CLASS = NamedTrackLocationClass(NAMED_TRACKS)
NAMED_TRACK_ITEM_DATA = item_data(NAMED_TRACKS)


def lock_document_text(tracks: Sequence[NamedTrack]) -> str:
    """test/fixtures/named_tracks_lock.json for `tracks`: the freeze record.

    Regenerate after a minting step with
    `python -m worlds.ctr.named_tracks --print-lock`.
    """
    def rows(table):
        return ",\n".join("      " + json.dumps(list(r), ensure_ascii=False) for r in table)
    tracks_text = json.dumps(lock_rows(tracks), indent=2, ensure_ascii=False).replace("\n", "\n  ")
    return ("{\n  \"format\": 1,\n  \"tracks\": " + tracks_text + ",\n  \"layout\": {\n"
            "    \"locations\": [\n" + rows(LOCATION_OFFSETS) + "\n    ],\n"
            "    \"items\": [\n" + rows(ITEM_OFFSETS) + "\n    ]\n  }\n}\n")


def load_fixture_document(name: str = "named_tracks_fixture.json") -> Mapping:
    """Test data only: the fixture rows under test/fixtures."""
    return json.loads(pkgutil.get_data(__package__, f"test/fixtures/{name}").decode("utf-8"))


if __name__ == "__main__":  # pragma: no cover - maintenance helper
    import sys
    if sys.argv[1:] == ["--print-lock"]:
        print(lock_document_text(NAMED_TRACKS), end="")
