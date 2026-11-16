"""Seed-local random pad caps, derived only from the ledger's base supply.

Default pools retain the original 8/4 caps and beta5 any-of limits. Extra
copies and starts do not raise requirements. The native pad display holds 99.
"""
from . import warp_pad_rules

MAX_COUNT = 99
FAMILIES = {
    "Trophy": ("Trophy",),
    "Key": ("Key",),
    "AnyCtrToken": warp_pad_rules.TOKENS,
    "AnyRelic": warp_pad_rules.RELICS,
    "AnyGem": warp_pad_rules.GEMS,
}
DEFAULT_SUPPLY = {"Trophy": 16, "Key": 4, "AnyCtrToken": 20,
                  "AnyRelic": 36, "AnyGem": 5}
FAMILY_OF = {name: family for family, names in FAMILIES.items() for name in (*names, family)}


def count_cap(item, base_cap, supply=None):
    """Proportional family cap, rounded up, without RNG or mutable globals.

    None retains the historical simulation API. A missing family has cap zero;
    its items cannot be drawn. Inventory ownership bounds each concrete draw.
    """
    if item == "Key":
        return 4
    if supply is None:
        return base_cap
    family = FAMILY_OF[item]
    total = sum(supply.get(name, 0) for name in FAMILIES[family])
    default = DEFAULT_SUPPLY[family]
    return min(MAX_COUNT, (base_cap * total + default - 1) // default)


def predicate_cap(predicate, stage, rows):
    """The same cap on a restored plan, including sums over a family subset."""
    names = {row.item: row.name for row in rows}
    supply = {row.name: row.requirement_ceiling for row in rows}
    item = names[predicate["item"]] if predicate["op"] == "count" else names[predicate["items"][0]]
    return count_cap(item, 8 if stage == 1 else 4, supply)


def admission_cap(predicate, stage, rows):
    """Also admit older small-pool rooms that used the fixed 8/4 ceilings.

    Base-supply validation still applies. New generation uses count_cap alone.
    """
    if predicate.get("item") == 35010014:
        return 4
    return max(8 if stage == 1 else 4, predicate_cap(predicate, stage, rows))
