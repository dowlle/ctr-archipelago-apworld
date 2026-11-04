"""Manual warp pad entry rules (`warp_pad_rules`, issue #463).

A player names a physical hub pad in the YAML and sets the item and count that
open its first stage. This module owns the whole contract for that option:

  * `parse` reads the YAML shape and names (no world needed);
  * `resolve` checks the parsed rules against the seed (unlock mode, which
    pads exist, how many of each item the seed has) and stores them on the
    world as `world._ctr_pad_rules`;
  * `fixed` hands the resolved rules to the sphere search, which installs them
    before it assigns anything to the unlisted pads and never relaxes them.

A rule is `(item, count)` for a counted requirement or `None` for a pad the
player made free. `None` is the same value the sphere search already uses for
a free bootstrap pad, so a free pad reaches the wire as the explicit
Trophy x 0 requirement (`warp_pad_logic.to_slot_req`).

Every failure is an `OptionError` that names the pad, item and count. Nothing
here draws from the random stream, and an empty map changes nothing.
"""
from typing import Dict, Optional, Tuple

from Options import OptionError

from . import destinations
from .Items import load_item_table

Rule = Optional[Tuple[str, int]]

TOKENS = ("Red CTR Token", "Green CTR Token", "Blue CTR Token",
          "Yellow CTR Token", "Purple CTR Token")
RELICS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")
GEMS = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")

#: Aggregate rule -> the concrete items it sums. Same families the native
#: `Req` gate evaluates (types 6, 7 and 8).
ANY_ITEMS = {"AnyCtrToken": TOKENS, "AnyRelic": RELICS, "AnyGem": GEMS}

FREE = "free"

#: Every item name a rule may use, in the order the error message lists them.
ALLOWED_ITEMS = ("Trophy", "Key") + TOKENS + RELICS + GEMS + tuple(ANY_ITEMS)

_ITEM_BY_NORM = {" ".join(n.split()).casefold(): n for n in ALLOWED_ITEMS}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _pad_names() -> Dict[str, str]:
    return {_norm(d.key): d.key for d in destinations.DESTINATIONS}


def _fail(message: str):
    raise OptionError("CTR warp_pad_rules: " + message)


def _unknown_pad(name: str):
    norm = _norm(name)
    if norm.endswith(" warp pad") and norm[:-len(" warp pad")] in _pad_names():
        _fail(f"{name!r}: write the pad name without 'Warp Pad' "
              f"({_pad_names()[norm[:-len(' warp pad')]]!r}).")
    if norm in {_norm(d.garage) for d in destinations.DESTINATIONS if d.garage}:
        _fail(f"{name!r} is a boss garage; this option sets hub warp pads only.")
    if norm == _norm(destinations.CORTEX_VORTEX):
        _fail("'Cortex Vortex' has no warp pad of its own; name the pad that "
              "hosts it.")
    _fail(f"{name!r} is not a warp pad. Pads: "
          + ", ".join(d.key for d in destinations.DESTINATIONS) + ".")


def parse(raw) -> Dict[str, Rule]:
    """Shape and name check of the YAML map. Returns {pad key -> rule} with the
    pad key exactly as `destinations` spells it and the item in its canonical
    spelling. Raises OptionError on any malformed entry."""
    if not isinstance(raw, dict):
        _fail("must be a mapping of pad name to {item, count}.")
    pads = _pad_names()
    out: Dict[str, Rule] = {}
    for name, value in raw.items():
        if not isinstance(name, str):
            _fail(f"pad name {name!r} must be text.")
        key = pads.get(_norm(name))
        if key is None:
            _unknown_pad(name)
        if key in out:
            _fail(f"{key!r} is listed twice.")
        if not isinstance(value, dict) or set(value) != {"item", "count"}:
            _fail(f"{key!r}: the value must have exactly 'item' and 'count'.")
        item, count = value["item"], value["count"]
        if not isinstance(item, str):
            _fail(f"{key!r}: item must be text, one of {FREE}, "
                  + ", ".join(ALLOWED_ITEMS) + ".")
        if type(count) is not int:
            _fail(f"{key!r}: count must be a whole number "
                  f"(got {count!r}).")
        if _norm(item) == FREE:
            if count != 0:
                _fail(f"{key!r}: item free needs count 0 (got {count}).")
            out[key] = None
            continue
        canonical = _ITEM_BY_NORM.get(_norm(item))
        if canonical is None:
            _fail(f"{key!r}: item {item!r} is not allowed. Use {FREE}, "
                  + ", ".join(ALLOWED_ITEMS) + ".")
        if count < 1:
            _fail(f"{key!r}: {canonical} needs a count of at least 1 "
                  f"(got {count}); use item free for an open pad.")
        out[key] = (canonical, count)
    return out


def supply(world) -> Dict[str, int]:
    """How many of each countable item this seed creates as base items. Extra
    items and extra starting items do not raise it, so a rule can never ask
    for more than the base pool holds."""
    counts = {row["name"]: row["count"] for row in load_item_table()}
    created = getattr(world, "_ctr_relic_created", {}) or {}
    out = {name: counts.get(name, 0) for name in ("Trophy", "Key") + TOKENS + GEMS}
    for tier in RELICS:
        out[tier] = created.get(tier, counts.get(tier, 0))
    return out


def check_supply(pad: str, rule: Rule, available: Dict[str, int]) -> None:
    """Refuse a rule the seed's base items cannot meet."""
    if rule is None:
        return
    item, count = rule
    members = ANY_ITEMS.get(item)
    have = sum(available[m] for m in members) if members else available[item]
    if have == 0:
        _fail(f"{pad!r}: {item} x {count}, but this seed has no "
              + (f"{item} items." if not members else "items of that kind."))
    if count > have:
        _fail(f"{pad!r}: {item} x {count}, but this seed has only {have} "
              f"{'in total' if members else 'of them'}.")


def resolve(world) -> None:
    """Validate the option against this seed and store the resolved rules on
    the world. Runs once in generate_early (never for a Universal Tracker
    re-generation, which pins the requirements from the wire instead)."""
    o = world.options
    world._ctr_pad_rules = {}
    raw = o.warp_pad_rules.value
    if not raw:
        return
    rules = parse(raw)
    mode = int(o.warppad_unlock_requirements.value)
    if mode == 0:
        _fail("this option needs warppad_unlock_requirements randomized or "
              "random_without_4_keys. With vanilla, pads keep their retail "
              "requirements; remove warp_pad_rules or change the mode.")
    present = {d.key: d for d in destinations.DESTINATIONS}
    available = supply(world)
    for pad, rule in rules.items():
        kind = present[pad].kind
        if kind == destinations.KIND_ARENA and not o.include_battle_arenas.value:
            _fail(f"{pad!r}: this seed has no battle arena pads "
                  "(include_battle_arenas is off).")
        if kind == destinations.KIND_CUP and not o.include_gem_cups.value:
            _fail(f"{pad!r}: this seed has no gem cup pads "
                  "(include_gem_cups is off).")
        if mode == 2 and rule is not None and rule[0] == "Key" and rule[1] >= 4:
            _fail(f"{pad!r}: Key x {rule[1]} is not allowed with "
                  "random_without_4_keys.")
        check_supply(pad, rule, available)
    world._ctr_pad_rules = rules


def fixed(world) -> Dict[str, Rule]:
    """The resolved manual rules, {physical pad key -> rule}. Empty when the
    option is unused or the world never resolved one."""
    return getattr(world, "_ctr_pad_rules", None) or {}


def describe(rule: Rule) -> str:
    return "free" if rule is None else f"{rule[0]} x {rule[1]}"
