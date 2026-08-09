"""Gem Cup leg composition (issue #166): which four tracks each Gem Cup runs.

The vanilla composition lives in data/gem_cup_legs.json, transcribed verbatim
from the native engine table data.advCupTrackIDs[5*4] (game/zGlobal_DATA.c).
The ruled behaviour (2026-08-07 wayfarer ruling) is exactly two states:

  * off (default): every cup runs its vanilla four legs, byte-identical to
    the pre-#166 table;
  * on: every leg of every cup is drawn independently, with replacement,
    from the 16 trophy-race tracks (LevelIDs 0..15). A track may leg several
    cups, several legs of one cup, or no cup at all. Slide Coliseum and
    Turbo Track (LevelIDs 16/17) are never drawn -- the ruled pool clamp;
    they are relic-race tracks, not trophy tracks.

The resolved map is stashed on the world as `world.gem_cup_legs`
({cup region name: [4 track names]}) by Regions.create_regions and feeds
three consumers:

  * Regions.create_regions -- a "<track>: Podium" dead-end region gets a
    rule-True entrance from every cup that legs the track (issue #86);
  * Rules.add_podium_placement_rules -- the rung OR rule (the track's Trophy
    Race reachable OR a legging cup reachable);
  * ctrAPWorld.fill_slot_data -- the top-level `gem_cup_legs` wire block,
    keyed by cup LevelID "100".."104" with the four leg track LevelIDs.

Solvability (dossier 2026-08-07, section 3): a cup leg is only ever an
ADDITIVE path to a track's podium rungs -- the track's own warp pad stays an
independent path regardless of the draw -- so no leg map can orphan a rung,
including the degenerate all-same-track and absent-track draws. The Purple
Gem Cup is deliberately NOT special-cased: its vanilla all-boss-track
line-up is a content fact, not a mechanism, and dissolves into the random
pool like any other cup.

Universal Tracker: the draw is re-pinned from the seed's slot_data during
re-generation (reconstruct_gem_cup_legs_from_wire), the same divergence
class as issue #29's warp-pad re-roll. A pre-#166 seed carries no
`gem_cup_legs` key and falls back to the vanilla table, which is exactly
what its generation used.
"""
import json
import logging
import pkgutil
from typing import Dict, List

logger = logging.getLogger(__name__)

# The five Gem Cup regions in their native LevelID order (cup LevelID ==
# 100 + colour index), matching data/warp_pad_ids.json ("<Colour> Cup Warp
# Pad" entries 100..104) and the cup order of data/gem_cup_legs.json, which
# itself mirrors the native advCupTrackIDs row order. Draw order is
# load-bearing for determinism: legs are drawn cup by cup in THIS order.
CUP_LEVEL_IDS = (
    ("Red Gem Cup", 100),
    ("Green Gem Cup", 101),
    ("Blue Gem Cup", 102),
    ("Yellow Gem Cup", 103),
    ("Purple Gem Cup", 104),
)

# The eligible leg pool (ruled clamp): the 16 trophy-race track LevelIDs.
TROPHY_TRACK_ID_POOL = tuple(range(16))


def load_vanilla_cup_legs() -> Dict[str, List[str]]:
    """cup region name -> its 4 vanilla leg track names, from
    data/gem_cup_legs.json (the verbatim advCupTrackIDs transcription)."""
    return json.loads(
        pkgutil.get_data(__package__, "data/gem_cup_legs.json").decode("utf-8")
    )["cup_legs"]


def track_level_ids() -> Dict[str, int]:
    """trophy-track name -> native LevelID (0..15), from
    data/warp_pad_ids.json (kind "race" pads; never retyped here)."""
    pads = json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8")
    )["pads"]
    return {
        name[: -len(" Warp Pad")]: meta["level_id"]
        for name, meta in pads.items()
        if meta["kind"] == "race"
    }


def track_to_cups(cup_legs: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Invert a cup->legs map into leg-track name -> [cup region names]. A
    track can leg more than one cup (vanilla: Roo's Tubes legs both Green and
    Purple), so the value is a list. A cup repeated across several legs of
    the SAME track (randomized mode allows repeats) is deduplicated here:
    every consumer keys off the (cup, track) pair -- Regions builds one
    entrance per pair and duplicate entrance names would collide in the
    entrance cache, and the Rules OR does not count multiplicity."""
    out: Dict[str, List[str]] = {}
    for cup, legs in cup_legs.items():
        for track in dict.fromkeys(legs):
            out.setdefault(track, []).append(cup)
    return out


def resolve_gem_cup_legs(world) -> Dict[str, List[str]]:
    """This seed's cup -> 4 leg track names.

    Option off: the vanilla table, unchanged (and NO random draws, so an
    option-off seed keeps the identical RNG stream, slot_data and spoiler as
    before the option existed). Option on: 20 independent draws with
    replacement from the 16 trophy tracks, cup by cup in CUP_LEVEL_IDS
    order, leg 1..4 within a cup -- a fixed consumption order on
    world.random, so the map is deterministic per seed.
    """
    vanilla = load_vanilla_cup_legs()
    if not world.options.randomize_gem_cup_tracks.value:
        return vanilla
    ids = track_level_ids()
    pool = [track for track, _lid in sorted(ids.items(), key=lambda kv: kv[1])]
    assert len(pool) == len(TROPHY_TRACK_ID_POOL), \
        "warp_pad_ids.json race pads no longer cover LevelIDs 0..15"
    return {
        cup: [pool[world.random.randrange(len(pool))] for _ in range(4)]
        for cup, _lid in CUP_LEVEL_IDS
    }


def resolved_gem_cup_legs(world) -> Dict[str, List[str]]:
    """world.gem_cup_legs, set exactly once per seed by
    Regions.create_regions. Raises instead of silently falling back to the
    vanilla table: a missing attribute here means create_regions never ran
    (a call-order bug), not "the option is off" (which resolve_gem_cup_legs
    already handles by returning the vanilla table itself, so world.gem_cup_legs
    is always a real, non-empty map by the time any consumer reads it)."""
    try:
        return world.gem_cup_legs
    except AttributeError:
        raise RuntimeError(
            "world.gem_cup_legs read before Regions.create_regions resolved "
            "it for this seed -- call order bug, not a missing-option case"
        ) from None


def cup_legs_to_wire(cup_legs: Dict[str, List[str]]) -> Dict[str, List[int]]:
    """Serialize the map for slot_data: {"<cupLevelID>": [trackLevelID x4]}.
    Always all five cups -- the smallest COMPLETE mapping (a partial map
    would force native to guess the rest)."""
    ids = track_level_ids()
    return {
        str(cup_lid): [ids[track] for track in cup_legs[cup]]
        for cup, cup_lid in CUP_LEVEL_IDS
    }


def reconstruct_gem_cup_legs_from_wire(
        passthrough: Dict[str, object]) -> Dict[str, List[str]]:
    """Universal Tracker re-generation: rebuild world.gem_cup_legs from the
    connected seed's slot_data instead of re-drawing (world.random is a
    different stream there). Absent key -> the vanilla table, silently --
    that is exactly what any pre-#166 seed generated with, not an error.
    A PRESENT but malformed key falls back to vanilla too (the emitter can
    never produce this shape), but logs a warning: unlike the absent-key
    case, this state means the seed DID randomize and the wire could not be
    trusted, so the tracker's map may not match the server's (N1, Opus
    review)."""
    wire = passthrough.get("gem_cup_legs")
    if wire is None:
        return load_vanilla_cup_legs()
    if not isinstance(wire, dict):
        logger.warning(
            "gem_cup_legs wire key present but not an object (%r) -- "
            "falling back to vanilla cup legs; this seed's UT map may not "
            "match the server's", type(wire).__name__)
        return load_vanilla_cup_legs()
    ids = track_level_ids()
    lid_to_track = {lid: track for track, lid in ids.items()}
    out: Dict[str, List[str]] = {}
    for cup, cup_lid in CUP_LEVEL_IDS:
        legs = wire.get(str(cup_lid))
        # AP's real slot_data pipeline runs every value through
        # NetUtils.convert_to_base_types before it is pickled into multidata
        # (Main.py), which turns every list into a tuple -- so a live/UT
        # wire block arrives as a tuple, not a list (json.loads/dumps in a
        # unit test masks this because JSON has no tuple type; the
        # relic_tiers.py precedent for the same reason never hard-checks
        # `isinstance(x, list)`). Accept both.
        if not (isinstance(legs, (list, tuple)) and len(legs) == 4
                and all(type(x) is int and x in lid_to_track for x in legs)):
            logger.warning(
                "gem_cup_legs wire key present but malformed for cup %s "
                "(%r) -- falling back to vanilla cup legs; this seed's UT "
                "map may not match the server's", cup, legs)
            return load_vanilla_cup_legs()
        out[cup] = [lid_to_track[x] for x in legs]
    return out
