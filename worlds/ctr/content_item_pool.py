"""Exact item supply for the content-plan generator.

Content determines capacity only. It never chooses, trims or precollects the
selected items. The immutable ledger is shared by generation and wire restore.
From-pool starts are granted by Main.py; the caller consumes its later depletion
request after materializing this post-start ledger, so subtraction happens once.
"""
from dataclasses import dataclass
from typing import Mapping

from Options import OptionError

from .Items import load_item_table

COLOURS = ("red", "green", "blue", "yellow", "purple")
TIERS = ("sapphire", "gold", "platinum")
FAMILIES = ("trophies", "relics", "tokens", "gems", "keys")
ITEMS = {item["name"]: item["code"] for item in load_item_table()}
COUNTED_NAMES = ("Trophy", *(f"{x.title()} Relic" for x in TIERS),
                 *(f"{x.title()} CTR Token" for x in COLOURS),
                 *(f"{x.title()} Gem" for x in COLOURS), "Key")
MAX_COUNT = 2147483647


def fail(message):
    raise OptionError("CTR item_pool: " + message)


def exact_count(value, path):
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        fail(f"{path} must be an exact nonnegative integer, at most {MAX_COUNT}.")
    return value


def fields(value, allowed, path):
    if not isinstance(value, dict):
        fail(f"{path} must be a mapping.")
    unknown = set(value) - set(allowed)
    if unknown:
        fail(f"unknown field in {path}: {sorted(unknown, key=str)!r}.")
    return value


def normalize(raw):
    """Return independent base/extra maps; defaults retain retail quantities."""
    fields(raw, ("base", "extra"), "item_pool")
    base, extra = {}, {}
    for side, output in (("base", base), ("extra", extra)):
        config = fields(raw.get(side, {}), FAMILIES, side)
        for family, name, default in (("trophies", "Trophy", 16), ("keys", "Key", 4)):
            output[name] = exact_count(config.get(family, default if side == "base" else 0),
                                       f"{side}.{family}")
        for family, parts, suffix, default in (("relics", TIERS, "Relic", 18),
                                                ("tokens", COLOURS, "CTR Token", 4)):
            nested = fields(config.get(family, {}), parts, f"{side}.{family}")
            for part in parts:
                output[f"{part.title()} {suffix}"] = exact_count(
                    nested.get(part, default if side == "base" else 0), f"{side}.{family}.{part}")
        if side == "base":
            gems = config.get("gems", list(COLOURS))
            if (not isinstance(gems, list) or any(type(x) is not str or x not in COLOURS for x in gems)
                    or len(set(gems)) != len(gems)):
                fail("base.gems must be a list of distinct red/green/blue/yellow/purple colours.")
            output.update({f"{x.title()} Gem": int(x in gems) for x in COLOURS})
        else:
            gems = fields(config.get("gems", {}), COLOURS, "extra.gems")
            output.update({f"{x.title()} Gem": exact_count(gems.get(x, 0), f"extra.gems.{x}")
                           for x in COLOURS})
    if base["Key"] != 4:
        fail("base.keys must be 4; all four hub Keys remain mandatory.")
    return base, extra


@dataclass(frozen=True)
class ItemRow:
    name: str
    item: int
    base: int
    extra: int
    start_from_pool: int
    start_additional: int
    locked_selected: int
    remaining: int
    receipt_cap: int
    requirement_ceiling: int

    def wire(self):
        return {key: value for key, value in vars(self).items() if key != "name"}


@dataclass(frozen=True)
class ItemPlan:
    rows: tuple[ItemRow, ...]
    coded_checks: int
    locked_checks: int
    filler_count: int
    trap_count: int

    def wire(self):
        return dict(rows=[row.wire() for row in self.rows], coded_checks=self.coded_checks,
                    locked_checks=self.locked_checks, filler_count=self.filler_count,
                    trap_count=self.trap_count)

    def selected_names(self):
        return [row.name for row in self.rows for _ in range(row.remaining)]


def resolve(raw, coded_checks, *, starts=None, additional=None, locked=None,
            locked_checks=0, trap_percentage=0, selected_packs=None):
    """Resolve B+E-S-Q and capacity, without changing caller options or RNG.

    `locked` describes selected copies already placed by their owner. Future
    framework plando must not be entered here: it consumes its copies later.
    `selected_packs` supplies exact registered identities from the existing
    capability/racer/weapon/letter controls; it never changes counted families.
    Filler includes traps; trap_count is the portion replaced with traps.
    """
    base, extra = normalize(raw)
    for name, count in (selected_packs or {}).items():
        if name not in ITEMS or name in base:
            fail(f"selected pack identity {name!r} is unknown or overlaps a counted family.")
        base[name] = exact_count(count, f"selected pack {name}")
        extra[name] = 0
    for label, values in (("starts", starts or {}), ("additional", additional or {}),
                          ("locked", locked or {})):
        if not isinstance(values, Mapping):
            fail(f"{label} must be a mapping.")
        for name, count in values.items():
            if name not in base:
                fail(f"{label} refers to unselected identity {name!r}.")
            exact_count(count, f"{label}.{name}")
    for label, value in (("coded_checks", coded_checks), ("locked_checks", locked_checks)):
        exact_count(value, label)
    if coded_checks > 4096 or locked_checks > coded_checks:
        fail("coded check capacity must be at most 4096 and cover every locked check.")
    exact_count(trap_percentage, "trap_percentage")
    if trap_percentage > 100:
        fail("trap_percentage must be at most 100.")
    if sum((locked or {}).values()) > locked_checks:
        fail("locked selected copies exceed realized locked checks.")
    rows = []
    for name in sorted(base, key=ITEMS.__getitem__):
        b, e = base[name], extra[name]
        s, a, q = (starts or {}).get(name, 0), (additional or {}).get(name, 0), (locked or {}).get(name, 0)
        remaining = b + e - s - q
        if remaining < 0:
            fail(f"{name}: base {b} + extras {e} cannot supply {s} from-pool starts "
                 f"and {q} locked selected copies. Your settings were not changed.")
        if b + e + a > MAX_COUNT:
            fail(f"{name}: total receipt count exceeds {MAX_COUNT}.")
        rows.append(ItemRow(name, ITEMS[name], b, e, s, a, q, remaining, b + e + a, b))
    demand = sum(row.remaining for row in rows)
    free = coded_checks - locked_checks
    if demand > free:
        fail(f"{demand} selected copies for {free} free checks. "
             f"Base {sum(r.base for r in rows)} + extras {sum(r.extra for r in rows)} "
             f"- from-pool starts {sum(r.start_from_pool for r in rows)} "
             f"- locked selected copies {sum(r.locked_selected for r in rows)} = {demand}. "
             f"Coded checks {coded_checks} - locked placements {locked_checks} = {free}. "
             f"Short by {demand - free} checks. Reduce selected counts/extras, choose explicit "
             "starts, or add content/checks. Your settings were not changed.")
    filler = free - demand
    return ItemPlan(tuple(rows), coded_checks, locked_checks, filler,
                    (filler * trap_percentage) // 100)
