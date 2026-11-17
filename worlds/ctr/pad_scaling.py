"""Seed-local random pad caps, derived only from the ledger's base supply.

Random pads use a quarter of the family per physical hub, up to the whole
base pool in Citadel City and Gem Stone Valley. Extras and starts do not count.
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


def count_cap(item, base_cap, supply=None, hub=4):
    """Base family ceiling times the physical hub's quarter share, rounded up.

    None retains base_cap for the historical simulation API. A missing family has cap zero;
    its items cannot be drawn. Inventory ownership bounds each concrete draw.
    """
    if item == "Key":
        return 4
    if supply is None:
        return base_cap
    family = FAMILY_OF[item]
    total = sum(supply.get(name, 0) for name in FAMILIES[family])
    return (min(MAX_COUNT, total) * hub + 3) // 4


def hub_rank(title):
    """Retail physical hub order; Valley trials and cups share the fourth band.

    The reference graph names regions for physical pads even after placement
    shuffles, so destination and opening order never change this band.
    """
    from .destinations import BY_KEY, KIND_TRIAL, KIND_CUP
    destination = BY_KEY[title]
    if destination.kind in (KIND_TRIAL, KIND_CUP):
        return 4
    return (destination.hub_keys or 0) + 1


def predicate_cap(predicate, stage, rows):
    """Cap for a predicate whose counted-ledger identities were checked first."""
    names = {row.item: row.name for row in rows}
    supply = {row.name: row.requirement_ceiling for row in rows}
    item = names[predicate["item"]] if predicate["op"] == "count" else names[predicate["items"][0]]
    return count_cap(item, 8 if stage == 1 else 4, supply)


def admission_cap(predicate, stage, rows):
    """Also admit older rooms that used fixed or A6-5 proportional ceilings.

    Base-supply validation still applies. Admission has no hub band, so old
    early-hub rooms remain valid. New generation uses count_cap with its hub.
    """
    if predicate.get("item") == 35010014:
        return 4
    return max(8 if stage == 1 else 4, predicate_cap(predicate, stage, rows))
