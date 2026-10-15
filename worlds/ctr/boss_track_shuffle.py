"""Boss track shuffle (#169 tier 1, 0.3.0, schema 18).

WHAT THE OPTION DOES. With `boss_track_shuffle` on, each of the four ordinary
boss garages (Ripper Roo, Papu Papu, Komodo Joe, Pinstripe) races its boss on
a track drawn at generation. The garage keeps everything else: its physical
`<Boss> Garage: Boss Race` check and code, its Key reward, its door
requirement, its personal-win event, its opponent, the boss's driving profile
and the boss's retail attack schedule. N. Oxide's two encounters are not part
of the draw. Purple Gem Cup legs follow `randomize_gem_cup_tracks`, never a
boss draw.

Design: the 0.3.0 #169 design with independent switches, ruled
2026-10-13. Tier 1 is the track switch only; the opponent and kit switches
are tiers 2 and 3.

THE DRAW. One record per physical garage, drawn once in `generate_early`
before anything reads it (`draw`) and pinned from the wire under Universal
Tracker (`restore_from_wire`). Native never redraws it. With the option off
nothing is drawn, so an option-off seed keeps its RNG stream and its output.

  * The venue pool is `all_compatible`: every retail race track whose static
    boss compatibility evidence is recorded in `VENUES` below, narrowed by
    `boss_track_allowlist` (empty = no narrowing) and then
    `boss_track_blocklist`.
  * A garage keeps its retail attack schedule (kit shuffle is off). Native
    maps each attack segment's checkpoint onto the drawn track by its relative
    lap position. A venue is certified for a garage only when that mapping
    keeps every segment distinct and in order (`inherited_attack_certified`),
    so a venue that cannot carry the inherited attack is rejected, as ruled.
  * `boss_encounter_repeats: disallow` (default) draws four distinct venues,
    uniformly over every valid four-way assignment. The whole assignment is
    tested, so filters that look sufficient garage by garage but admit no
    matching fail generation instead of falling back to a repeat. `allow`
    draws each garage independently. A track that also appears on an ordinary
    pad or a Gem Cup leg never counts as a repeat.

THE STATIC EVIDENCE. `VENUES` records, per retail race track, the restart
point (checkpoint) count of its 1P LEV, read from the NTSC-U disc
(SCUS_944.26) with the retail editor's levtool on 2026-10-15. Every one of the
18 tracks also has its three AI navigation paths. The four garages' retail
attack schedules are copied from the decompiled `data.BossWeapon*` tables.
Runtime acceptance is the Steam row set in the Rolling Testing List; native
also re-checks the loaded track's count against this table and refuses a
mismatch rather than racing on a geometry the certification did not see.

LOGIC. A shuffled venue moves two things in the apworld, and only those: the
boss win rule's finish capability term (`Rules.add_boss_garage_rules`) and the
garage's race route onto that venue's `<Track>: Reach 10 Wumpa` check
(`Regions`, `wumpa_checks.dropped_boss_wumpa_track`). Native awards that
Wumpa check by the loaded LevelID, which is the drawn venue. Garage entry,
Key counts and item-box routes are unchanged: AP boxes stay behind the
venue's own pad, as ruled 2026-09-12.
"""
from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from Options import OptionError

from . import destinations

#: Wire block version of `boss_encounters`.
BLOCK_VERSION = 1

#: The four ordinary garages in hub order: (wire key, garage region, frozen
#: Boss Race location code, retail home track). The wire key is the boss key
#: `boss_garage_req` already uses. Oxide is not drawn.
GARAGES: Tuple[Tuple[str, str, int, str], ...] = (
    (destinations.BOSS_ROO, "Ripper Roo Garage", 35011100, "Roo's Tubes"),
    (destinations.BOSS_PAPU, "Papu Papu Garage", 35011101, "Papu's Pyramid"),
    (destinations.BOSS_JOE, "Komodo Joe Garage", 35011102, "Dragon Mines"),
    (destinations.BOSS_PINSTRIPE, "Pinstripe Garage", 35011103, "Hot Air Skyway"),
)

OXIDE_GARAGE = "N. Oxide Garage"
OXIDE_TRACK = "Oxide Station"

#: Retail race tracks with recorded static boss compatibility evidence:
#: {track -> 1P LEV restart point count}. LevelIDs come from the destination
#: table. Slide Coliseum and Turbo Track are race tracks with full AI
#: navigation; they host a boss race without their trial-pad races.
VENUES: Dict[str, int] = {
    "Dingo Canyon": 103,
    "Dragon Mines": 84,
    "Blizzard Bluff": 90,
    "Crash Cove": 72,
    "Tiger Temple": 110,
    "Papu's Pyramid": 102,
    "Roo's Tubes": 78,
    "Hot Air Skyway": 175,
    "Sewer Speedway": 160,
    "Mystery Caves": 123,
    "Cortex Castle": 135,
    "N. Gin Labs": 138,
    "Polar Pass": 167,
    "Oxide Station": 190,
    "Coco Park": 83,
    "Tiny Arena": 194,
    "Slide Coliseum": 121,
    "Turbo Track": 117,
}
destinations.require_all(VENUES)

#: {track -> LevelID}, the wire currency.
VENUE_LEVEL_IDS: Dict[str, int] = destinations.level_ids_for(VENUES)
_VENUE_BY_LEVEL_ID: Dict[int, str] = {lid: t for t, lid in VENUE_LEVEL_IDS.items()}

#: Each garage's retail attack schedule, as the starting checkpoint of every
#: segment on its home track (`data.BossWeaponRoo` etc., terminator dropped).
RETAIL_ATTACK_CHECKPOINTS: Dict[str, Tuple[int, ...]] = {
    destinations.BOSS_ROO: (0x00, 0x10, 0x21, 0x2F, 0x46),
    destinations.BOSS_PAPU: (0x00, 0x0F, 0x22, 0x53, 0x5D),
    destinations.BOSS_JOE: (0x00, 0x10, 0x2A, 0x39, 0x46),
    destinations.BOSS_PINSTRIPE: (0x00, 0x10, 0x21, 0x2F, 0x46),
}

#: The opponent, AI profile and attack identities tier 1 can emit. Tier 1
#: never changes them; the fields exist so tiers 2 and 3 extend the same rows.
OPPONENT_RETAIL = {key: key for key, _g, _c, _h in GARAGES}
AI_PROFILE_RETAIL = "retail"
ATTACK_INHERITED = "inherited"

ROW_KEYS = ("location", "home_track", "track", "opponent", "ai_profile",
            "attack", "packages")


def translate_checkpoint(checkpoint: int, home_last: int, venue_last: int) -> int:
    """The venue checkpoint a retail segment start maps to: the same relative
    lap position, rounded down. Native `AP_BossVenueCheckpoint` is the twin."""
    if checkpoint <= 0:
        return 0
    if checkpoint >= home_last:
        return venue_last
    return (checkpoint * venue_last) // home_last


def translated_schedule(garage: str, track: str) -> Tuple[int, ...]:
    home = _home_track(garage)
    home_last = VENUES[home] - 1
    venue_last = VENUES[track] - 1
    return tuple(translate_checkpoint(cp, home_last, venue_last)
                 for cp in RETAIL_ATTACK_CHECKPOINTS[garage])


def inherited_attack_certified(garage: str, track: str) -> bool:
    """Can `track` carry `garage`'s retail attack schedule? Every translated
    segment must start on a real checkpoint and strictly after the previous
    one; a collapsed or reordered segment would drop or reorder an attack."""
    if track not in VENUES:
        return False
    mapped = translated_schedule(garage, track)
    return (all(0 <= cp < VENUES[track] for cp in mapped)
            and all(a < b for a, b in zip(mapped, mapped[1:])))


def _home_track(garage: str) -> str:
    for key, _region, _code, home in GARAGES:
        if key == garage:
            return home
    raise KeyError(garage)


def _garage_region(garage: str) -> str:
    for key, region, _code, _home in GARAGES:
        if key == garage:
            return region
    raise KeyError(garage)


def enabled(options) -> bool:
    return bool(getattr(options, "boss_track_shuffle", None)
                and options.boss_track_shuffle.value)


# --------------------------------------------------------------------- options

def validate_options(world) -> None:
    """Raise-guards for subordinate controls (design: reject a nonempty track
    filter while track shuffle is off). `boss_encounter_repeats: allow`
    without a draw is noted as ignored rather than refused: it narrows
    nothing and the design names no rejection for it."""
    o = world.options
    if enabled(o):
        return
    used = [name for name in ("boss_track_allowlist", "boss_track_blocklist")
            if getattr(o, name).value]
    if used:
        raise OptionError(
            f"CTR ({_who(world)}): {', '.join(used)} only apply with "
            "boss_track_shuffle on; turn it on or empty the list.")
    if o.boss_encounter_repeats.value:
        from .notices import note_ignored
        note_ignored(world, "Boss Encounter Repeats (no boss draw is on)")


def _who(world) -> str:
    from .notices import slot_label
    return slot_label(world)


def venue_pool(options) -> List[str]:
    """`all_compatible` narrowed by the allowlist, then the blocklist."""
    allow = set(options.boss_track_allowlist.value)
    block = set(options.boss_track_blocklist.value)
    return [t for t in VENUES
            if (not allow or t in allow) and t not in block]


def garage_candidates(options) -> Dict[str, List[str]]:
    pool = venue_pool(options)
    return {key: [t for t in pool if inherited_attack_certified(key, t)]
            for key, _r, _c, _h in GARAGES}


# ------------------------------------------------------------------------ draw

def draw(world) -> None:
    """Resolve and freeze the four garage venues on `world.options`.

    Off: pins the retail table and draws nothing. On: one `world.random` draw
    for the disallow policy (a uniform pick over every valid four-way
    assignment), or one per garage under `allow`. A table already on the
    options (preset by a test, or a re-run over the same options) is kept
    and only checked; the draw still happens so the RNG stream stays aligned
    with a fresh generation, as `cortex_vortex_track` does."""
    o = world.options
    validate_options(world)
    existing = getattr(o, "_boss_track_venues", None)
    if not enabled(o):
        o._boss_track_venues = dict(retail_venues())
        return
    candidates = garage_candidates(o)
    for key, region, _code, _home in GARAGES:
        if not candidates[key]:
            raise OptionError(
                f"CTR ({_who(world)}): boss_track_shuffle has no certified "
                f"track left for {region} after boss_track_allowlist and "
                "boss_track_blocklist.")
    keys = [key for key, _r, _c, _h in GARAGES]
    if int(o.boss_encounter_repeats.value) == 1:
        picked = [world.random.choice(candidates[key]) for key in keys]
    else:
        assignments = [combo for combo in
                       itertools.product(*(candidates[key] for key in keys))
                       if len(set(combo)) == len(combo)]
        if not assignments:
            raise OptionError(
                f"CTR ({_who(world)}): boss_track_shuffle cannot give the four "
                "boss garages four different tracks from the allowed pool ("
                + ", ".join(venue_pool(o)) + "). Allow more tracks or set "
                "boss_encounter_repeats: allow.")
        picked = list(world.random.choice(assignments))
    drawn = {key: track for key, track in zip(keys, picked)}
    if existing is None:
        o._boss_track_venues = drawn
        return
    if (sorted(existing) != sorted(keys)
            or any(existing[key] not in candidates[key] for key in keys)
            or (int(o.boss_encounter_repeats.value) == 0
                and len(set(existing.values())) != len(keys))):
        raise ValueError(f"CTR: preset boss venues {existing} are not a valid "
                         "draw for this option set")


def retail_venues() -> Dict[str, str]:
    return {key: home for key, _r, _c, home in GARAGES}


def venues(options) -> Dict[str, str]:
    """{garage key -> venue track} for this seed. Retail when the option is
    off; the frozen draw when on (it must already have run)."""
    if not enabled(options):
        return retail_venues()
    resolved = getattr(options, "_boss_track_venues", None)
    if resolved is None:
        raise RuntimeError("CTR: boss venues read before boss_track_shuffle.draw")
    return dict(resolved)


def garage_tracks(options) -> Dict[str, str]:
    """{garage region -> race track} for all five garages, the per-seed
    replacement for the retail `Regions.BOSS_WUMPA_TRACKS` table. N. Oxide
    keeps Oxide Station (his Final venue is a separate option)."""
    v = venues(options)
    out = {_garage_region(key): v[key] for key, _r, _c, _h in GARAGES}
    out[OXIDE_GARAGE] = OXIDE_TRACK
    return out


# ------------------------------------------------------------------------ wire

def wire_block(options) -> Optional[Dict[str, object]]:
    """The `boss_encounters` slot_data block, or None with the option off
    (an absent block means retail encounters)."""
    if not enabled(options):
        return None
    v = venues(options)
    garages: Dict[str, Dict[str, object]] = {}
    for key, _region, code, home in GARAGES:
        garages[key] = {
            "location": code,
            "home_track": VENUE_LEVEL_IDS[home],
            "track": VENUE_LEVEL_IDS[v[key]],
            "opponent": OPPONENT_RETAIL[key],
            "ai_profile": AI_PROFILE_RETAIL,
            "attack": ATTACK_INHERITED,
            "packages": [],
        }
    return {"version": BLOCK_VERSION, "garages": garages}


def parse_wire(block) -> Dict[str, str]:
    """Validate a `boss_encounters` block and return {garage key -> track}.
    Raises ValueError on anything this build would not emit."""
    if not isinstance(block, Mapping) or block.get("version") != BLOCK_VERSION:
        raise ValueError("boss_encounters: missing block or unknown version")
    rows = block.get("garages")
    keys = [key for key, _r, _c, _h in GARAGES]
    if not isinstance(rows, Mapping) or sorted(rows) != sorted(keys):
        raise ValueError("boss_encounters: garages must be exactly " + ", ".join(keys))
    out: Dict[str, str] = {}
    for key, _region, code, home in GARAGES:
        row = rows[key]
        if not isinstance(row, Mapping) or sorted(row) != sorted(ROW_KEYS):
            raise ValueError(f"boss_encounters.{key}: unexpected fields")
        track_id = row["track"]
        if type(track_id) is not int or track_id not in _VENUE_BY_LEVEL_ID:
            raise ValueError(f"boss_encounters.{key}: unknown track {track_id!r}")
        track = _VENUE_BY_LEVEL_ID[track_id]
        if (row["location"] != code or row["home_track"] != VENUE_LEVEL_IDS[home]
                or row["opponent"] != OPPONENT_RETAIL[key]
                or row["ai_profile"] != AI_PROFILE_RETAIL
                or row["attack"] != ATTACK_INHERITED or row["packages"] != []
                or not inherited_attack_certified(key, track)):
            raise ValueError(f"boss_encounters.{key}: record this build cannot race")
        out[key] = track
    return out


def restore_from_wire(world, passthrough: Mapping) -> None:
    """Universal Tracker: pin the connected seed's venues; never redraw.
    The always-emitted `ctr_options.boss_track_shuffle` scalar is the option;
    a schema-18 seed without it is refused rather than guessed."""
    o = world.options
    co = passthrough.get("ctr_options", {}) or {}
    flag = co.get("boss_track_shuffle", False)
    if type(flag) is not bool:
        raise ValueError("ctr_options.boss_track_shuffle must be a boolean")
    block = passthrough.get("boss_encounters")
    if flag != (block is not None):
        raise ValueError("boss_track_shuffle and boss_encounters disagree")
    o.boss_track_shuffle.value = int(flag)
    # The filters and repeat policy shaped the draw only; the pinned table
    # is the whole answer. Clear them so the tracker's own YAML cannot trip
    # the subordinate-option guard.
    o.boss_track_allowlist.value = set()
    o.boss_track_blocklist.value = set()
    o.boss_encounter_repeats.value = 0
    o._boss_track_venues = parse_wire(block) if flag else dict(retail_venues())


def spoiler_lines(options) -> Iterable[str]:
    if not enabled(options):
        return ()
    v = venues(options)
    return tuple(f"{region}: {v[key]}" for key, region, _c, _h in GARAGES)
