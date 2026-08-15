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
    """
    from . import characters

    stat_mins = stat_mins or {}
    boost_mode = int(world.options.progressive_boost.value)
    stats_mode = int(world.options.progressive_stats.value)

    if required_character is not None:
        candidates = (required_character,)
    else:
        candidates = ROSTER

    unlocks_on = characters.unlocks_enabled(world)
    start = world.ctr_starting_character
    for character in candidates:
        if unlocks_on and character != start \
                and not state.has(characters.unlock_item_name(character), player):
            continue

        boost_name = (boost_item_name(character)
                      if boost_mode == 2 else boost_item_name())
        if boost_min and boost_mode and state.count(boost_name, player) < boost_min:
            continue

        stats_ok = True
        if stats_mode:
            for chain, minimum in stat_mins.items():
                name = (stat_item_name(chain, character)
                        if stats_mode == 2 else stat_item_name(chain))
                if state.count(name, player) < minimum:
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
