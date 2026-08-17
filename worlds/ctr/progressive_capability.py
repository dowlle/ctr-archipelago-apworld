"""Progressive Boost / Progressive Stats item packs (issues #12, #13).

Both packs are staged, ruled shape-for-shape: `off` (no items, byte-identical
to a pre-#12/#13 seed) / `shared_global` (one set of chains for every
character) / `per_character` (a separate set of chains per racer).

ROSTER is the 16 playable racers, source-verified against
`ctr-native-ap`/`ctr-native-spike` decomp (`game/zGlobal_DATA.c`, the
`characterID_Champion` enum values across the grand-prix hub table) rather
than assumed from memory -- the project's own verify-first rule
(CTR Archipelago -- Lessons Learned #1/#16). There is no in-repo character
roster anywhere else (the character-swap feature itself is still an unfiled
parent issue), so this module is the first place one is written down; keep it
in sync if that future work settles a different canonical list.

ITEM SUPPLY AND LOGIC
---------------------
The frozen table keeps these option-created items at count 0 and classification
`useful`. `ctrAPWorld.create_item` upgrades exactly the active chains that a
seed's capability rules read to `progression`.

  * shared_global: Progressive Boost (up to 3 copies) + 3 stat chains x4
    copies (12) = up to 15 new pool items. Verified against CTR's own
    location ceiling (101 static + up to 80 podium rungs = 181; existing
    fixed item count is 99) -- fits with podium checks on, can overflow the
    101-location floor with podium fully off AND both packs maxed, so
    `raise_if_capability_items_exceed_location_supply` below guards that
    combination with a clean OptionError instead of a raw FillError.
  * per_character: 16x the shared_global pool (Boost up to 48, stats 192),
    up to 240 new items. Authored item-box locations now provide enough supply
    for rich seeds; the same live per-seed supply guard rejects combinations
    that still cannot seat the selected packs.
"""
from typing import Dict, List, Tuple

from Options import OptionError

# Source-verified 16-racer roster -- see the module docstring.
ROSTER: Tuple[str, ...] = (
    "Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura", "Neo Cortex",
    "N. Tropy", "Ripper Roo", "Papu Papu", "Komodo Joe", "Pinstripe",
    "Dingodile", "Tiny Tiger", "N. Gin", "Fake Crash", "Nitros Oxide",
    "Penta Penguin",
)
assert len(ROSTER) == 16

STAT_CHAINS: Tuple[str, ...] = (
    "Progressive Top Speed", "Progressive Acceleration", "Progressive Turning",
)
STAT_COPIES_PER_CHAIN = 4  # five-rank ladder (VERY LOW..VERY HIGH), 08-07 ruling

BOOST_CHAIN = "Progressive Boost"
BOOST_COPIES_NO_BLUE_FIRE = 2   # no boost / boost / USF
BOOST_COPIES_BLUE_FIRE = 3      # + blue fire capstone

def boost_item_name(character: str = None) -> str:
    return BOOST_CHAIN if character is None else f"{BOOST_CHAIN} ({character})"


def stat_item_name(chain: str, character: str = None) -> str:
    assert chain in STAT_CHAINS
    return chain if character is None else f"{chain} ({character})"


# Per-character item names, built once. `gate_satisfied` runs inside AP's fill
# sweep and re-derived these f-strings 14.3 million times on one archived
# timing-out seed (2026-08-16 fuzz receipt, seed 1508); the tables make that a
# dict lookup. Same strings as the two helpers above, which stay the public
# spelling for every caller outside the hot loop.
BOOST_NAME_BY_CHARACTER: Dict[str, str] = {
    character: boost_item_name(character) for character in ROSTER
}
STAT_NAME_BY_CHARACTER: Dict[str, Dict[str, str]] = {
    character: {chain: stat_item_name(chain, character) for chain in STAT_CHAINS}
    for character in ROSTER
}
SHARED_STAT_NAME: Dict[str, str] = {chain: chain for chain in STAT_CHAINS}


def track_required_character(world, track: str):
    """Return the racer a player must be driving to be ON `track`, or None.

    ``ctr_racer_locks`` is keyed by pad EXIT name. The question every capability
    rule is really asking is "which racer does the pad that LOADS this track
    demand", and under destination shuffle that pad is not the one named after
    the track: `create_regions` keeps each exit's physical name and retargets it
    to a shuffled destination. So the lookup goes through
    ``ctr_pad_by_destination``, the seed's destination -> physical pad map,
    and only falls back to the same-name pad when there is no shuffle to
    resolve (the map is empty in vanilla, where the two coincide).

    Reading the lock by track name instead was wrong in all three directions at
    once, and all three were live in one seed on 2026-08-17: it invented a
    requirement on a track whose pad is free (over-restrictive), it named the
    wrong racer where both pads were locked, and -- the dangerous one -- it
    returned None for a track behind a locked pad, letting `gate_satisfied`
    fall through to its any-driveable-racer arm.
    """
    locks = getattr(world, "ctr_racer_locks", {}) or {}
    if not locks:
        return None
    by_dest = getattr(world, "ctr_pad_by_destination", None) or {}
    pad = by_dest.get(track, f"{track} Warp Pad")
    return locks.get(pad)


def created_item_counts(world) -> Dict[str, int]:
    """{item name: count to create THIS seed} for both ownership modes."""
    o = world.options
    out: Dict[str, int] = {}
    if o.progressive_boost.value == 1:  # shared_global
        n = BOOST_COPIES_BLUE_FIRE if o.progressive_boost_blue_fire.value \
            else BOOST_COPIES_NO_BLUE_FIRE
        out[boost_item_name()] = n
    elif o.progressive_boost.value == 2:  # per_character
        n = BOOST_COPIES_BLUE_FIRE if o.progressive_boost_blue_fire.value \
            else BOOST_COPIES_NO_BLUE_FIRE
        for character in ROSTER:
            out[boost_item_name(character)] = n
    if o.progressive_stats.value == 1:  # shared_global
        for chain in STAT_CHAINS:
            out[stat_item_name(chain)] = STAT_COPIES_PER_CHAIN
    elif o.progressive_stats.value == 2:  # per_character
        for character in ROSTER:
            for chain in STAT_CHAINS:
                out[stat_item_name(chain, character)] = STAT_COPIES_PER_CHAIN
    return out


def gate_satisfied(world, state, player, *, boost_min: int = 0,
                   stat_mins: Dict[str, int] = None,
                   required_character: str = None) -> bool:
    """Evaluate one capability gate under the #252 single-racer ruling.

    A locked gate tests only its required racer. An unlocked gate existentially
    tests every currently driveable racer. All boost and stat requirements are
    checked inside that single racer iteration, so they cannot be split across
    characters.

    SHARED-MODE COLLAPSE. When neither pack is `per_character`, every candidate
    reads the SAME item names, so the sixteen iterations are sixteen identical
    evaluations. The existential then collapses to "the shared counts hold" AND
    "some candidate is driveable" -- and the starting character is never skipped
    by the unlock filter, so an unlocked gate always has one. Evaluating the
    counts once is an identity, not a relaxation: the loop below returns exactly
    the same answer. It matters because this function is on AP's fill sweep.
    """
    from . import characters

    stat_mins = stat_mins or {}
    boost_mode = int(world.options.progressive_boost.value)
    stats_mode = int(world.options.progressive_stats.value)
    check_boost = bool(boost_min and boost_mode)
    check_stats = bool(stats_mode and stat_mins)

    if not check_boost and not check_stats:
        # Nothing to test per racer; the loop below would return True on its
        # first driveable candidate, and the start racer always is one.
        if required_character is None:
            return True

    unlocks_on = characters.unlocks_enabled(world)
    start = world.ctr_starting_character

    if required_character is None and boost_mode != 2 and stats_mode != 2:
        if check_boost and state.count(BOOST_CHAIN, player) < boost_min:
            return False
        if check_stats:
            for chain, minimum in stat_mins.items():
                if state.count(SHARED_STAT_NAME[chain], player) < minimum:
                    return False
        return True

    candidates = (required_character,) if required_character is not None else ROSTER
    for character in candidates:
        if unlocks_on and character != start \
                and not state.has(characters.unlock_item_name(character), player):
            continue

        if check_boost:
            boost_name = (BOOST_NAME_BY_CHARACTER[character]
                          if boost_mode == 2 else BOOST_CHAIN)
            if state.count(boost_name, player) < boost_min:
                continue

        stats_ok = True
        if check_stats:
            names = (STAT_NAME_BY_CHARACTER[character]
                     if stats_mode == 2 else SHARED_STAT_NAME)
            for chain, minimum in stat_mins.items():
                if state.count(names[chain], player) < minimum:
                    stats_ok = False
                    break
        if stats_ok:
            return True
    return False


def unlock_items_are_logic_inputs(world) -> bool:
    """Whether per-character gates can make racer ownership progression."""
    if not getattr(world, "ctr_starting_character", None):
        return False
    if not bool(world.options.character_unlocks.value):
        return False
    if int(world.options.progressive_boost.value) == 2:
        return True  # static USF finish gates always read boost
    return (int(world.options.progressive_stats.value) == 2
            and bool(world.options.box_locations.value)
            and int(world.options.shortcut_knowledge.value) == 2)


def raise_if_capability_items_exceed_location_supply(world, *, available_supply: int) -> None:
    """RAISE guard: the selected capability pack(s) must fit in THIS seed's actual
    location supply alongside everything else already in the pool. Scoped to
    `available_supply` is the caller's live count (mirrors elastic_bounds.py's convention of
    never restating a location count as a local constant) -- pass the seed's
    real `len(mw.get_unfilled_locations(player))` from create_items."""
    counts = created_item_counts(world)
    if not counts:
        return
    added = sum(counts.values())
    if added <= 0:
        return
    # This check runs from create_items, after the base 99-fixed-item pool and
    # any pinned/locked adjustments are known to the caller; the caller passes
    # the CURRENT pool size so this stays accurate under every other option
    # combination (arenas off, gems pinned, relic counts lowered, ...) instead
    # of restating CTR's ~99-fixed baseline here.
    if available_supply < added:
        boost_mode = world.options.progressive_boost.current_key
        stats_mode = world.options.progressive_stats.current_key
        raise OptionError(
            f"CTR: Progressive Boost / Progressive Stats would add {added} "
            f"item(s) to the pool (boost={boost_mode}, stats={stats_mode}), "
            f"but this seed has only {available_supply} unfilled location(s) "
            f"left for them. Turn on Item Box Locations or Podium Placement "
            f"Checks, turn off Progressive Boost: Blue Fire, or set "
            f"Progressive Boost / Progressive Stats to 'off'.")


def fill_slot_data(world) -> Dict[str, object]:
    """The three additive ctr_options keys this pack contributes: boost_mode,
    boost_blue_fire, stats_mode. No schema_version bump (Q28 standing
    ruling already makes 7 unconditional on every 0.2.0 seed regardless of
    any one feature's own needs); native ignores unknown keys by explicit
    named lookup (slot_data Contract Sec.3). The native per-character consumer
    already reads these unchanged scalar modes, so no new wire field is needed."""
    o = world.options
    return {
        "boost_mode": o.progressive_boost.value,
        "boost_blue_fire": bool(o.progressive_boost_blue_fire.value),
        "stats_mode": o.progressive_stats.value,
    }
