"""Exact-count relic tier removal (issue #171 conversion; issue #28 rulings
R1-R3, [[2026-08-09 -- Rulings -- 28 exclusion semantics + relic removal]]).

Each of the three relic tiers (Sapphire/Gold/Platinum) has exactly 18 Time
Trial locations in the frozen datapackage. Pre-#171, a per-location 0-100
percentage roll decided whether each of the 18 stayed progression-eligible or
got its vanilla relic PINNED there (`place_locked_item`) -- either way, the
location and its item both always existed (18 items per tier, always).

R3 replaces the percentage with an exact count (0-18): this seed creates
exactly N of that tier's 18 Time Trial locations, drawn uniformly at random.
R1 replaces pinning with REMOVAL: the other (18-N) locations are not created
at all this seed -- no Location object, no check, no item, no pinned vanilla
reward ("registered but not created", the #176 frozen-superset convention --
the datapackage name/id still exists forever; this module only decides
per-seed which of those names get a Location object).

This module owns exactly the roll (`draw_relic_tier_keep`) and its
UT-reconstruction counterpart (`restore_relic_tier_keep_from_wire`). It does
not create locations (`Regions.create_regions` reads its output to decide
which to build) and does not touch the item pool (`__init__.create_items`
reads `created` to size it) -- single source, two consumers, matching the
project's existing split between "what a seed creates" and "who acts on it".
"""
import logging
from typing import Dict, FrozenSet, List, Tuple

logger = logging.getLogger(__name__)

# (tier label as it appears in location names, relic item name, option field)
RELIC_TIERS: Tuple[Tuple[str, str, str], ...] = (
    ("Sapphire", "Sapphire Relic", "sapphire_relic_count"),
    ("Gold", "Gold Relic", "gold_relic_count"),
    ("Platinum", "Platinum Relic", "platinum_relic_count"),
)


def tier_location_pool(location_name_to_id, tier_label: str) -> List[str]:
    """All 18 Time Trial location names for one relic tier, sorted for a
    deterministic input sequence (`world.random.sample` below needs a stable
    ordering to be reproducible per seed -- a set or dict-iteration order is
    not guaranteed stable across processes)."""
    suffix = f": {tier_label} Time Trial"
    return sorted(n for n in location_name_to_id if n.endswith(suffix))


def resolve_comfort_guards(options) -> Tuple[bool, bool]:
    """(`comfort_guards`, `force_vanilla_turbotrack`) -- single source for the
    Icebound `force_vanilla_turbotrack` condition, read by the relic draw
    below, `Regions.create_regions` and `warp_pad_logic.resolve_shuffle_pools`.
    Previously computed inline in `Regions.create_regions`, which runs AFTER
    `generate_early`; the relic draw needs it BEFORE `create_regions`, so it
    moved here as the one place both callers read from (Lessons Learned #5:
    derive, never restate -- two inline copies of the same boolean expression
    would eventually drift)."""
    comfort_guards = True
    force_vanilla_turbotrack = (
        comfort_guards
        and options.warppad_unlock_requirements.value == 0
        and not bool(options.shuffle_gems.value))
    return comfort_guards, force_vanilla_turbotrack


def draw_relic_tier_keep(world) -> Tuple[Dict[str, FrozenSet[str]], Dict[str, int]]:
    """Roll which of each tier's 18 Time Trial locations this seed creates.

    Runs once, from `generate_early` -- before `create_regions` builds any
    location (so a below-count slot is never created as a Location object at
    all, R1) and before any generate_early guard that needs a tier's created
    count (R2/R5, e.g. the Oxide-final relic-count guards in
    `forced_options.py`).

    Turbo Track comfort guard (Icebound `force_vanilla_turbotrack`): under
    vanilla warp-pad unlock + gems not shuffled, Turbo Track keeps its
    vanilla 5-gem entry gate, so its 3 relic Time Trials must never hold a
    required item (pre-#171 this force-PINNED them regardless of the tier's
    roll; removal-not-pinning has no pin to reach for, so the equivalent
    safety move is excluding Turbo Track's own slot from the sample pool --
    it is simply never eligible to be created, which R1 already made
    inert-by-construction for any removed slot). This narrows that tier's
    achievable count by 1 while the guard is active; if the player's count
    exceeds what remains, it is clamped down with a loud warning (not a
    silent change, not a generation-aborting raise -- losing exactly one
    comfort-guarded location is not a solvability break, see the build note).

    Returns `(keep, created)`: `keep[relic_item_name]` is the frozen set of
    location names this seed creates for that tier; `created[relic_item_name]`
    is its size (the effective count after any comfort-guard clamp)."""
    keep: Dict[str, FrozenSet[str]] = {}
    created: Dict[str, int] = {}
    _, force_vanilla_tt = resolve_comfort_guards(world.options)
    for tier_label, relic_item, option_name in RELIC_TIERS:
        pool = tier_location_pool(world.location_name_to_id, tier_label)
        n = getattr(world.options, option_name).value
        if force_vanilla_tt:
            tt_name = f"Turbo Track: {tier_label} Time Trial"
            if tt_name in pool:
                pool = [name for name in pool if name != tt_name]
                if n > len(pool):
                    logger.warning(
                        f"CTR: player {world.player} "
                        f"({world.multiworld.player_name[world.player]})'s "
                        f"'{option_name}' asked for {n}, but the Turbo Track "
                        f"comfort guard (vanilla warp-pad unlock + gems not "
                        f"shuffled) keeps its {tier_label} Time Trial "
                        f"vanilla-inert, so at most {len(pool)} of this tier "
                        f"can be created this seed. Clamped to {len(pool)}.")
                    n = len(pool)
        chosen = world.random.sample(pool, n)
        keep[relic_item] = frozenset(chosen)
        created[relic_item] = n
    return keep, created


def restore_relic_tier_keep_from_wire(
    world, ctr_options: dict
) -> Tuple[Dict[str, FrozenSet[str]], Dict[str, int]]:
    """Universal Tracker re-generation (issue #29): rebuild the SAME keep-sets
    the real seed created, from the connected seed's slot_data, instead of
    re-rolling (`world.random.sample` would almost certainly choose different
    locations than the real seed did -- UT must reconstruct, not re-roll,
    exactly like `_ut_reconstruct_warp_pad_map` does for destination shuffle).

    Reads the additive `ctr_options.relic_tier_locations` wire key (issue
    #171 -- see the slot_data Contract): `{relic_item_name: [location code,
    ...]}`, exactly the codes this seed created for that tier.

    BACKWARDS COMPATIBILITY: a seed generated before this key existed carries
    no such block. Fall back to 'every tier's full 18' -- matching the
    `relic_progression` wire field's own documented fallback (all-progression,
    the historical pre-fix behaviour) and, for this key, also matching what a
    pre-#171 seed actually did (all 18 of a tier always existed, pinned or
    not)."""
    keep: Dict[str, FrozenSet[str]] = {}
    created: Dict[str, int] = {}
    wire = ctr_options.get("relic_tier_locations")
    for tier_label, relic_item, _option_name in RELIC_TIERS:
        pool = tier_location_pool(world.location_name_to_id, tier_label)
        if isinstance(wire, dict) and relic_item in wire:
            codes = set(wire[relic_item])
            names = frozenset(
                name for name in pool
                if world.location_name_to_id[name] in codes)
        else:
            names = frozenset(pool)
        keep[relic_item] = names
        created[relic_item] = len(names)
    return keep, created
