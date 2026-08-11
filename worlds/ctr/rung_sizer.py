"""Adaptive podium-rung sizing (issue #71).

Podium's four sub-toggles are a parent/child ladder, not a scalar.  This
module chooses the smallest *upward-only* layout that gives the generated
pool a spare location.  It deliberately does not implement the downward half
of #71: until #109 supplies real item-box locations, no live seed can exercise
that behaviour.  It also never enables the master ``podium_placement_checks``
toggle, which is an explicit player opt-out rather than a sizing preference.

The nine effective layouts are listed in ``RUNG_LADDER``.  When a YAML enables
a child while its parent is off, candidate selection expands the current raw
toggle state instead of normalising it, so sizing never turns a player-enabled
toggle off.  Ties prefer the layout that creates the fewest new names and then
held-position rungs over finish rungs, as ruled on 2026-08-10.
"""
from dataclasses import dataclass
from itertools import product
import logging
from typing import Iterable, Optional, Tuple

from Options import OptionError

from .Items import load_item_table
from .Locations import CTR_LOCATION_CLASSES, _LOCATION_DATA
from .elastic_bounds import predicted_goal_excluded_reserve
from .podium import PODIUM_CLASS, TROPHY_TRACKS, created_rung_keys
from .relic_tiers import RELIC_TIERS
from . import progressive_capability

logger = logging.getLogger(__name__)


_TOGGLE_NAMES = (
    "podium_finish_rungs",
    "podium_any_position_rung",
    "podium_held_rungs",
    "podium_held_fifth_rung",
)
_GEM_NAMES = frozenset({"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"})
_SURFACE_ITEM_NAMES = frozenset({
    "Ignore Grass", "Ignore Dirt", "Ignore Snow", "Ignore Water", "Ignore Ice",
})


@dataclass(frozen=True)
class RungLayout:
    """One canonical effective layout, in finish/any/held/fifth order."""

    finish: bool
    any_position: bool
    held: bool
    held_fifth: bool

    @property
    def categories(self) -> int:
        return len(self.keys)

    @property
    def keys(self) -> Tuple[str, ...]:
        return tuple(created_rung_keys(
            self.finish, self.any_position, self.held, self.held_fifth))


# Nine reachable category shapes once each child is collapsed against its
# parent. Their order is only documentation; selection has explicit sort keys.
RUNG_LADDER: Tuple[RungLayout, ...] = (
    RungLayout(False, False, False, False),
    RungLayout(True, False, False, False),
    RungLayout(True, True, False, False),
    RungLayout(False, False, True, False),
    RungLayout(False, False, True, True),
    RungLayout(True, False, True, False),
    RungLayout(True, True, True, False),
    RungLayout(True, False, True, True),
    RungLayout(True, True, True, True),
)
assert tuple(sorted({row.categories for row in RUNG_LADDER})) == (0, 1, 2, 3, 4, 5)


def _raw_values(options) -> Tuple[bool, bool, bool, bool]:
    return tuple(bool(getattr(options, name).value) for name in _TOGGLE_NAMES)


def _layout_from_values(values: Tuple[bool, bool, bool, bool]) -> RungLayout:
    return RungLayout(*values)


def category_count(options) -> int:
    """Number of active rung categories for these resolved options."""
    if not bool(options.podium_placement_checks.value):
        return 0
    return _layout_from_values(_raw_values(options)).categories


def rows_reachable_from(options) -> Tuple[RungLayout, ...]:
    """Every raw-toggle superset of the player's selection.

    The effective ladder has nine rows, but preserving an inert child toggle
    requires considering its raw value while selecting a row.  This produces
    at most sixteen candidates and returns each effective layout once.
    """
    current = _raw_values(options)
    rows = {
        _layout_from_values(values)
        for values in product((False, True), repeat=4)
        if all(not old or new for old, new in zip(current, values))
    }
    return tuple(sorted(rows, key=lambda row: (
        row.categories, row.held is False, row.finish is False,
        row.any_position is False, row.held_fifth is False)))


def _base_location_supply(world) -> int:
    """Live non-podium location count before adding rung categories.

    Static Time Trial slots are represented by ``_ctr_relic_created`` rather
    than their frozen full table. Any optional class that becomes live before
    #71's next touch contributes automatically through the #176 registry.
    """
    static_without_trials = sum(
        1 for loc in _LOCATION_DATA if not loc["name"].endswith(" Time Trial"))
    relics = sum(world._ctr_relic_created.values())
    other_classes = sum(
        len(location_class.created_locations(world.options))
        for location_class in CTR_LOCATION_CLASSES
        if location_class is not PODIUM_CLASS)
    return static_without_trials + relics + other_classes


def predicted_mandatory_pool(world) -> int:
    """Mandatory, non-comfort item count before filler.

    This mirrors the count adjustments in ``create_items`` without building
    locations. Locked vanilla rewards remove the same number of locations and
    pool items, so they remain balance-neutral. The five terrain comfort items
    are intentionally omitted: ``create_items`` trims that elastic pack when
    space is tight, while this function sizes only mandatory demand.
    """
    counts = {item["name"]: item["count"] for item in load_item_table()}
    for _label, relic_name, _option_name in RELIC_TIERS:
        counts[relic_name] = world._ctr_relic_created.get(relic_name, 0)

    gem_goal = world.options.gems_required_goal.value > 0
    if not world.options.shuffle_gems.value:
        for name in _GEM_NAMES:
            counts[name] = 0
    elif not world.options.include_gem_cups.value and not gem_goal:
        for name in _GEM_NAMES:
            counts[name] = 0
    if not world.options.shuffle_keys.value:
        counts["Key"] = 0
    if not world.options.include_battle_arenas.value:
        counts["Purple CTR Token"] = max(0, counts["Purple CTR Token"] - 4)

    mandatory = sum(
        count for name, count in counts.items()
        # Wumpa Fruit is CTR's generic filler. Its table entry supplies the
        # filler type, not one mandatory pool slot, so it must not consume
        # rung capacity here.
        if name != "Wumpa Fruit" and name not in _SURFACE_ITEM_NAMES and count > 0)
    mandatory += sum(progressive_capability.created_item_counts(world).values())
    return mandatory


def _capability_packs_active(world) -> bool:
    return bool(world.options.progressive_boost.value or world.options.progressive_stats.value)


def required_categories(world) -> Optional[int]:
    """Smallest rung-category count that leaves one spare location.

    ``None`` means the full five-category ladder cannot satisfy the current
    live registry and item pool. The extra category above the arithmetic
    minimum is the ruled working margin; the practical floor of three applies
    only while either capability pack is enabled.
    """
    demand = predicted_mandatory_pool(world)
    demand += predicted_goal_excluded_reserve(world.options)
    demand += len(world.options.exclude_locations.value)
    base = _base_location_supply(world)
    minimum = next((categories for categories in range(6)
                    if demand <= base + len(TROPHY_TRACKS) * categories), None)
    if minimum is None:
        return None
    if _capability_packs_active(world):
        # Capability packs are the only live consumers that need the ruled
        # working margin. With them off, preserve a player's legal zero-rung
        # seed when its mandatory pool already fits exactly.
        return max(min(minimum + 1, 5), 3)
    return minimum


def _new_name_count(current: RungLayout, candidate: RungLayout) -> int:
    return len(set(candidate.keys) - set(current.keys)) * len(TROPHY_TRACKS)


def _held_category_count(layout: RungLayout) -> int:
    return (2 if layout.held else 0) + (1 if layout.held and layout.held_fifth else 0)


def _select_layout(options, target: int) -> Optional[RungLayout]:
    current = _layout_from_values(_raw_values(options))
    candidates = [row for row in rows_reachable_from(options)
                  if row.categories >= target]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (
        row.categories,
        _new_name_count(current, row),
        -_held_category_count(row),
    ))


def apply_rung_sizing(world) -> Optional[str]:
    """Apply the ruled upward-only sizing policy, or raise clearly.

    This runs in ``generate_early`` before regions consume the podium toggles.
    A sufficient player layout is untouched and takes no random draw.
    """
    target = required_categories(world)
    current = category_count(world.options)
    if target is None:
        raise OptionError(
            "CTR: the current mandatory item pool exceeds the full five-category "
            "Podium Rung ladder. Disable an item-pool option or add a live "
            "location class; the rung sizer cannot create more than 80 locations.")
    if current >= target:
        return None
    if not bool(world.options.podium_placement_checks.value):
        raise OptionError(
            "CTR: this seed needs more Podium Rung capacity, but Podium Placement "
            "Checks is off. The adaptive sizer never enables that master toggle; "
            "turn it on or reduce Progressive Boost / Progressive Stats and other "
            "enabled item-pool options.")
    if not bool(world.settings.allow_rung_sizing):
        raise OptionError(
            "CTR: this seed needs more Podium Rung capacity, but host.yaml "
            "disables adaptive rung sizing. Enable ctr.allow_rung_sizing, turn on "
            "more podium rung subcategories, or reduce the enabled item-pool options.")
    selected = _select_layout(world.options, target)
    if selected is None:
        raise OptionError(
            "CTR: no upward-only Podium Rung layout can satisfy this seed's "
            "capacity requirement without disabling a player-selected toggle.")
    previous = _raw_values(world.options)
    for name, value in zip(_TOGGLE_NAMES, (selected.finish, selected.any_position,
                                            selected.held, selected.held_fifth)):
        if value:
            getattr(world.options, name).value = True
    current_names = category_count(world.options)
    message = (
        f"CTR: adaptive podium rung sizing raised player {world.player} from "
        f"{current} to {current_names} category(s) (target {target}; raw "
        f"subtoggles {previous} -> {_raw_values(world.options)}).")
    logger.warning(message)
    return message
