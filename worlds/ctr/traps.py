"""The CTR trap registry: canonical item names, YAML weight keys and the
weighted draw that trap fill uses (issue #280, the 0.2.0 trap rework).

ONE table owns three things that used to live apart, because every drift
between them is a player-visible bug:

  1. THE CANONICAL ITEM NAME. What the datapackage registers and what the
     server, trackers and hints show. The 0.2.0 rework renamed five of these
     before public 0.2.0 distribution (see the rename block below); the ids
     they carry in data/items.json did NOT move, and must not.
  2. THE MACHINE KEY. The stable lowercase key a player writes in
     `trap_weights`. It is deliberately independent of the item name, so a
     later name cleanup cannot silently invalidate everyone's YAML.
  3. THE BUILDABLE FLAG. Whether native has an effect for this identity in the
     shipped build. Only buildable traps are ever drawn into a pool -- a
     drawn name whose native effect does not exist would hand the player a
     trap that does nothing.

The buildable entries are ORDER-LOAD-BEARING: their order is native's
AP_TrapEffect enum order (ap/ap_traps.h), and native maps the received item
index (AP_TRAP_ITEM_FIRST_INDEX + effect, ap_hooks.c) straight onto that enum.
Reordering them here re-points every trap in the game.

RENAMES, 0.2.0 (ruled 2026-08-19 in the trap rework design
notebook). Names only; every id is unchanged:

    No Brakes Trap        -> Forced USF
    Wumpa Reset Trap      -> Wumpa Wipeout
    Auto-Use Trap         -> Forced Use
    No Boost Trap         -> Boost Blocker
    Reverse Controls Trap -> Reverse Steering

and the `Trap` suffix is dropped across the whole family: the Archipelago item
classification already tells a player the item is a trap, so the suffix only
cost readable names. Renaming canonical names is a datapackage-visible change
and is deliberate. The eleven reserved names were never published; the five
implemented names DID ship in v0.1.5, so a v0.1.5 YAML naming one of them in an
item option fails generation with Archipelago's did-you-mean pointing at the
new name. The release notes must carry the old-to-new table.
"""
from typing import Dict, List, NamedTuple, Tuple

from Options import OptionError


class TrapEntry(NamedTuple):
    """One trap identity: what it is called, how a YAML names it, how often it
    is drawn, and whether the shipped native build can actually run it."""
    #: Stable lowercase YAML key for `trap_weights`. Never renamed.
    key: str
    #: Canonical Archipelago item name, as registered in data/items.json.
    name: str
    #: Reviewed default draw weight (notebook table, 2026-08-19). 1 = very
    #: rare ... 6 = most frequent. Relative only; no total is required.
    weight: int
    #: True when native has a working effect for this identity today. False
    #: entries are registered names with count 0: real datapackage identities
    #: that fill never draws until their native effect lands.
    buildable: bool
    #: Which datapackage block minted the id, for the name-freeze census.
    #: "shipped" = v0.1.5, "freeze" = the #177 0.2.0 name freeze,
    #: "rework" = new in #280, appended after the freeze.
    origin: str


#: Every trap identity, in datapackage id order. The first five are the
#: buildable set in AP_TrapEffect order; the rest are registered and inert.
TRAP_REGISTRY: Tuple[TrapEntry, ...] = (
    # Buildable, native AP_TrapEffect 0-4, ids 35010016-35010020.
    TrapEntry("icy_road",         "Icy Road",         5, True,  "shipped"),
    TrapEntry("low_gravity",      "Low Gravity",      5, True,  "shipped"),
    TrapEntry("forced_usf",       "Forced USF",       2, True,  "shipped"),
    TrapEntry("forced_boost",     "Forced Boost",     4, True,  "shipped"),
    TrapEntry("first_person",     "First Person",     3, True,  "shipped"),
    # Minted by the #177 name freeze, ids 35010106-35010116. No native effect.
    TrapEntry("wumpa_wipeout",    "Wumpa Wipeout",    4, False, "freeze"),
    TrapEntry("flatten",          "Flatten",          6, False, "freeze"),
    TrapEntry("item_reroll",      "Item Reroll",      5, False, "freeze"),
    TrapEntry("forced_use",       "Forced Use",       4, False, "freeze"),
    TrapEntry("empty_crates",     "Empty Crates",     3, False, "freeze"),
    TrapEntry("weakened_kart",    "Weakened Kart",    3, False, "freeze"),
    TrapEntry("boost_blocker",    "Boost Blocker",    3, False, "freeze"),
    TrapEntry("wireframe",        "Wireframe",        2, False, "freeze"),
    TrapEntry("nitro",            "Nitro",            5, False, "freeze"),
    TrapEntry("reverse_steering", "Reverse Steering", 4, False, "freeze"),
    TrapEntry("red_potion",       "Red Potion",       3, False, "freeze"),
    # New identities minted by #280, ids 35010190-35010192. No native effect.
    # Demo Camera is deliberately NOT here: it is prototype-gated and gets its
    # identity only if it earns inclusion.
    TrapEntry("upside_down",      "Upside Down",      2, False, "rework"),
    TrapEntry("mirror_mode",      "Mirror Mode",      3, False, "rework"),
    TrapEntry("warpball_ambush",  "Warpball Ambush",  3, False, "rework"),
)

#: The BUILDABLE draw list, pinned to native's AP_TrapEffect enum order.
TRAP_ITEM_NAMES: List[str] = [e.name for e in TRAP_REGISTRY if e.buildable]

#: The 11 names the #177 freeze minted, in items.json append order.
FROZEN_TRAP_ITEM_NAMES: List[str] = [e.name for e in TRAP_REGISTRY
                                     if e.origin == "freeze"]

#: The 3 names #280 minted, in items.json append order.
REWORK_TRAP_ITEM_NAMES: List[str] = [e.name for e in TRAP_REGISTRY
                                     if e.origin == "rework"]

#: Every registered trap name, buildable or not. This is the "Traps" item
#: group: group membership is part of the checksummed datapackage payload, so
#: a trap added to its own group later would spend a second bump.
ALL_TRAP_ITEM_NAMES: List[str] = [e.name for e in TRAP_REGISTRY]

#: Machine keys in registry order -- the option's valid_keys and the order the
#: generated YAML template lists them in.
TRAP_WEIGHT_KEYS: Tuple[str, ...] = tuple(e.key for e in TRAP_REGISTRY)

#: The reviewed default weight table (notebook, 2026-08-19).
DEFAULT_TRAP_WEIGHTS: Dict[str, int] = {e.key: e.weight for e in TRAP_REGISTRY}

_KEY_TO_ENTRY: Dict[str, TrapEntry] = {e.key: e for e in TRAP_REGISTRY}

#: Highest legal weight. 0 disables an effect; the scale is relative, so the
#: ceiling exists only to catch a value that is obviously not a weight.
MAX_TRAP_WEIGHT = 100


def validate_trap_weights(mapping) -> None:
    """Reject an unusable `trap_weights` mapping with a clear OptionError.

    Two failures, both silent-until-surprising if they were tolerated:

    - an UNKNOWN KEY is almost always a misspelling ("icyroad", "Icy Road"),
      and ignoring it would leave the player convinced they retuned an effect
      they never touched;
    - a value that is not an integer 0-100 has no defined meaning in a
      weighted draw (a float weight silently works in random.choices, so it
      would ship as an accidental, undocumented feature).

    Raised on every generation path: the YAML roll calls it through
    Options.TrapWeights.verify_keys, and generate_early calls it again through
    forced_options for worlds built programmatically (tests, the fuzzer).
    """
    unknown = [k for k in mapping if k not in _KEY_TO_ENTRY]
    if unknown:
        raise OptionError(
            f"CTR 'trap_weights' has unknown key(s): "
            f"{', '.join(sorted(repr(k) for k in unknown))}. Keys are the stable lowercase trap "
            f"names, not the item names shown in game. Valid keys: "
            f"{', '.join(TRAP_WEIGHT_KEYS)}. Leave a trap out entirely to keep "
            f"its default weight.")
    for key, value in mapping.items():
        if isinstance(value, bool) or not isinstance(value, int) \
                or not 0 <= value <= MAX_TRAP_WEIGHT:
            raise OptionError(
                f"CTR 'trap_weights' value for '{key}' is {value!r}. Each "
                f"weight must be a whole number from 0 to {MAX_TRAP_WEIGHT}, "
                f"where 0 means the trap is never selected.")


def effective_trap_weights(world) -> Dict[str, int]:
    """The reviewed defaults overlaid with this player's `trap_weights`.

    An absent mapping keeps every default; a partial mapping keeps the default
    of every key it omits. Pure -- reads options, mutates nothing.
    """
    weights = dict(DEFAULT_TRAP_WEIGHTS)
    custom = getattr(getattr(world.options, "trap_weights", None),
                     "value", None) or {}
    validate_trap_weights(custom)
    weights.update(custom)
    return weights


def selectable_trap_weights(world) -> Dict[str, int]:
    """The weights trap fill can actually draw from: the effective table
    restricted to buildable traps, with the zero-weight ones dropped.

    This is the "renormalize over the enabled effects" step. Two filters, one
    result: a weight of 0 is the player disabling an effect, and a
    non-buildable entry is native not having the effect yet. Neither is
    compensated for elsewhere -- what is left simply shares 100% of the draw,
    which random.choices does by normalizing whatever relative weights it is
    handed.
    """
    weights = effective_trap_weights(world)
    return {e.key: weights[e.key] for e in TRAP_REGISTRY
            if e.buildable and weights[e.key] > 0}


def draw_trap_names(world, count: int) -> List[str]:
    """`count` trap item names drawn against the player's weights.

    Deterministic for a fixed seed and YAML: the only randomness is
    `world.random`, and the candidate list is built in registry order.
    """
    if count <= 0:
        return []
    selectable = selectable_trap_weights(world)
    if not selectable:
        # Unreachable in generation: forced_options rejects an all-zero table
        # while trap fill is above 0, which is the only way to get here.
        raise OptionError(
            "CTR trap fill has no trap left to draw: every buildable trap is "
            "at weight 0 in 'trap_weights'.")
    names = [_KEY_TO_ENTRY[key].name for key in selectable]
    return world.random.choices(names, weights=list(selectable.values()),
                                k=count)
