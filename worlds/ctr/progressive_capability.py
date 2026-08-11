"""Progressive Boost / Progressive Stats item packs (issues #12, #13).

Both packs are staged, ruled shape-for-shape: `off` (no items, byte-identical
to a pre-#12/#13 seed) / `shared_global` (one set of chains for every
character) / `per_character` (a separate set of chains per racer, issue #71
blocked -- see PER_CHARACTER_BLOCKED_MESSAGE below).

ROSTER is the 16 playable racers, source-verified against
`ctr-native-ap`/`ctr-native-spike` decomp (`game/zGlobal_DATA.c`, the
`characterID_Champion` enum values across the grand-prix hub table) rather
than assumed from memory -- the project's own verify-first rule
(CTR Archipelago -- Lessons Learned #1/#16). There is no in-repo character
roster anywhere else (the character-swap feature itself is still an unfiled
parent issue), so this module is the first place one is written down; keep it
in sync if that future work settles a different canonical list.

ITEM SUPPLY (0.2.0 spine-1 order scope: apworld-only, pool/fill correctness
only -- no track logic reads a tier yet, and none of these items are
`progression`; they ride as `useful` filler-replacement content, the same
classification shape trap items use, so a location's own access rule can
never depend on receiving one).

  * shared_global: Progressive Boost (up to 3 copies) + 3 stat chains x4
    copies (12) = up to 15 new pool items. Verified against CTR's own
    location ceiling (101 static + up to 80 podium rungs = 181; existing
    fixed item count is 99) -- fits with podium checks on, can overflow the
    101-location floor with podium fully off AND both packs maxed, so
    `raise_if_capability_items_exceed_location_supply` below guards that
    combination with a clean OptionError instead of a raw FillError.
  * per_character: 16x the shared_global pool (Boost up to 48, stats 192) --
    up to 240 new items against the SAME <=181-location ceiling. Structurally
    infeasible without new locations (issue #71's own "size the rung budget
    to the item pool" is exactly the unbuilt reconciliation this needs), so
    `raise_if_per_character_mode_selected` rejects the option value outright
    at generate_early rather than emitting a world that can never generate.
    The item names + #168 codes are minted now anyway (data/items.json) so
    the eventual #71 fix does not force a second naming/manifest pass.
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

PER_CHARACTER_BLOCKED_MESSAGE = (
    "CTR '{option_name}' 'per_character' is not generatable yet: CTR's "
    "live location supply cannot place the 192-240 additional per-character "
    "items without real item-box locations. Adaptive podium sizing is live, "
    "but #109 must first seat box locations before this mode can be checked "
    "against their per-seed supply. Use 'shared_global' instead, or wait for "
    "#109.")


def boost_item_name(character: str = None) -> str:
    return BOOST_CHAIN if character is None else f"{BOOST_CHAIN} ({character})"


def stat_item_name(chain: str, character: str = None) -> str:
    assert chain in STAT_CHAINS
    return chain if character is None else f"{chain} ({character})"


def raise_if_per_character_mode_selected(world) -> None:
    """RAISE guard (issue #178 shape): reject `per_character` outright until
    #109 provides real item-box supply. Runs in generate_early, before pool math."""
    o = world.options
    if o.progressive_boost.value == 2:  # ProgressiveBoostMode.option_per_character
        raise OptionError(PER_CHARACTER_BLOCKED_MESSAGE.format(
            option_name="progressive_boost"))
    if o.progressive_stats.value == 2:  # ProgressiveStatsMode.option_per_character
        raise OptionError(PER_CHARACTER_BLOCKED_MESSAGE.format(
            option_name="progressive_stats"))


def created_item_counts(world) -> Dict[str, int]:
    """{item name: count to create THIS seed} for both packs, shared_global
    only (per_character never reaches here -- generate_early already raised).
    Empty dict when both packs are off (byte-identical to a pre-#12/#13
    seed: no entry means create_items adds nothing and takes no RNG draw for
    this feature)."""
    o = world.options
    out: Dict[str, int] = {}
    if o.progressive_boost.value == 1:  # shared_global
        n = BOOST_COPIES_BLUE_FIRE if o.progressive_boost_blue_fire.value \
            else BOOST_COPIES_NO_BLUE_FIRE
        out[boost_item_name()] = n
    if o.progressive_stats.value == 1:  # shared_global
        for chain in STAT_CHAINS:
            out[stat_item_name(chain)] = STAT_COPIES_PER_CHAIN
    return out


def raise_if_capability_items_exceed_location_supply(world, *, available_supply: int) -> None:
    """RAISE guard: the shared_global pack(s) must fit in THIS seed's actual
    location supply alongside everything else already in the pool. Scoped to
    shared_global only (per_character already raises earlier). `available_supply`
    is the caller's live count (mirrors elastic_bounds.py's own convention of
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
        raise OptionError(
            f"CTR: Progressive Boost / Progressive Stats would add {added} "
            f"item(s) to the pool ({', '.join(f'{v}x {k}' for k, v in counts.items())}), "
            f"but this seed has only {available_supply} unfilled location(s) "
            f"left for them. Turn on Podium Placement Checks (adds up to 80 "
            f"more locations), turn off Progressive Boost: Blue Fire, or set "
            f"Progressive Boost / Progressive Stats to 'off'.")


def fill_slot_data(world) -> Dict[str, object]:
    """The three additive ctr_options keys this pack contributes: boost_mode,
    boost_blue_fire, stats_mode. No schema_version bump (Q28 standing
    ruling already makes 7 unconditional on every 0.2.0 seed regardless of
    any one feature's own needs); native ignores unknown keys by explicit
    named lookup (slot_data Contract Sec.3), so a pre-this-feature native
    simply never reads them -- no native consumer exists yet (apworld-only
    order scope), which is honest and forward-compatible: the day a native
    consumer lands it reads exactly these three keys, unchanged."""
    o = world.options
    return {
        "boost_mode": o.progressive_boost.value,
        "boost_blue_fire": bool(o.progressive_boost_blue_fire.value),
        "stats_mode": o.progressive_stats.value,
    }
