"""The `win_logic` slot_data block (Contract 7m): every win check's logic as
data, for native's race-loss DeathLink stakes.

Ruling (2026-10-01 14:31 CEST): a race loss, RESTART or EXIT TO MAP
sends a DeathLink only when that race's win is in logic and not yet
collected. Option A (14:33): the apworld emits each race's win requirements
and native evaluates them against received items, so the game and Universal
Tracker never disagree.

Nothing here restates logic. The win-check layers in `Rules.py`,
`usf_finish.py` and the goal predicates install `logic_terms` terms, and this
module only serialises what is installed:

* each win check's location rule (`logic_terms.term_of`), and
* its region access, the OR over every simple entrance path from the origin
  region of the AND of the entrances' installed terms. This is exactly
  Archipelago's region reachability, because every entrance rule is a pure
  function of received items.

A win check or entrance whose rule is not term-backed (someone installed a
plain lambda) raises `WinLogicExportError` rather than exporting stale
logic. `test_win_logic_parity` evaluates the emitted JSON with an
independent reference evaluator and compares it with `location.can_reach`.

Wire format: the slot_data Contract section 7m, the native implementation
contract (`SCHEMA.md`).
"""
import json
from typing import Dict, List, Optional

from .logic_terms import term_of

WIN_LOGIC_VERSION = 1

#: Nesting limit promised to native, `ref` expansion included.
MAX_DEPTH = 16

#: (location-name suffix, kind), first match wins. Ticket 01 ruling: the win
#: of each race mode. `Relic Race Perfect`, podium rungs and letters are not
#: wins and are deliberately absent.
_KIND_SUFFIXES = (
    (": Trophy Race", "trophy"),
    (": Sapphire Time Trial", "sapphire"),
    (": Gold Time Trial", "gold"),
    (": Platinum Time Trial", "platinum"),
    (": CTR Token Challenge", "ctr"),
    (": Boss Race", "boss"),
    (" Gem Cup: Gem", "gem"),
    (": Crystal Bonus Round", "crystal"),
    (": N. Oxide's Final Challenge", "oxide_final"),
    (": N. Oxide's Challenge", "oxide"),
)

_TOKENS = ("Red CTR Token", "Green CTR Token", "Blue CTR Token",
           "Yellow CTR Token", "Purple CTR Token")
_RELICS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")
_GEMS = ("Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem")

#: The 15 gate items as Contract section 2 `Req` (type, colour).
_GATE_REQ = {"Trophy": (1, -1), "Key": (2, -1)}
_GATE_REQ.update({name: (3, c) for c, name in enumerate(_TOKENS)})
_GATE_REQ.update({name: (4, c) for c, name in enumerate(_RELICS)})
_GATE_REQ.update({name: (5, c) for c, name in enumerate(_GEMS)})


class WinLogicExportError(RuntimeError):
    """A win check or an entrance on its path has no term-backed rule."""


def win_kind(location_name: str) -> Optional[str]:
    """The `win_logic` kind of a location name, or None for a non-win."""
    for suffix, kind in _KIND_SUFFIXES:
        if location_name.endswith(suffix):
            return kind
    return None


def weapon_families():
    from .itemsanity import USEFUL_WEAPON_FAMILIES
    return tuple(tuple(f) for f in USEFUL_WEAPON_FAMILIES)


class _Encoder:
    """Resolves names to wire ids for `Term.wire`."""

    def __init__(self, world):
        self.world = world
        self.refs = set()

    def _item_id(self, name: str) -> int:
        try:
            return int(self.world.item_name_to_id[name])
        except KeyError:
            raise WinLogicExportError(
                f"CTR win_logic: rule names {name!r}, which has no item id")

    def has(self, item: str, count: int):
        if item in _GATE_REQ:
            t, c = _GATE_REQ[item]
            return ["req", t, int(count), c]
        return ["items", "sum", int(count), [self._item_id(item)]]

    def item_sum(self, items, count: int):
        names = set(items)
        if len(names) != len(tuple(items)):
            raise WinLogicExportError(f"CTR win_logic: duplicate items in sum {items!r}")
        if names == set(_TOKENS):
            return ["req", 6, int(count), -1]
        if names == set(_TOKENS) - {"Purple CTR Token"}:
            return ["tokens_no_purple", int(count)]
        if names == set(_RELICS):
            return ["req", 7, int(count), -1]
        if names == set(_GEMS):
            return ["req", 8, int(count), -1]
        if len(names) == 1:
            return self.has(next(iter(names)), count)
        return self.items("sum", count, items)

    def items(self, mode: str, count: int, items):
        ids = sorted({self._item_id(n) for n in items})
        if mode == "sum" and len(ids) != len(tuple(items)):
            raise WinLogicExportError(f"CTR win_logic: duplicate items in sum {items!r}")
        return ["items", mode, int(count), ids]

    def cap(self, boost: int, racer: Optional[str]):
        from .characters import ROSTER_CHARACTER_ID
        return ["cap", int(boost), -1 if racer is None else ROSTER_CHARACTER_ID[racer]]

    def families(self, families, count: int):
        if tuple(tuple(f) for f in families) != weapon_families():
            raise WinLogicExportError(
                "CTR win_logic: a families term uses a table other than "
                "USEFUL_WEAPON_FAMILIES")
        return ["families", int(count)]

    def ref(self, location: str):
        loc = self.world.multiworld.get_location(location, self.world.player)
        if loc.address is None:
            raise WinLogicExportError(f"CTR win_logic: ref to event {location!r}")
        self.refs.add(int(loc.address))
        return ["ref", int(loc.address)]


# --- simplification (equivalence-preserving) ------------------------------

def _mono(term):
    """(key, value) for a leaf that is monotone in one integer, else None.
    Two leaves with the same key differ only in that integer: the larger one
    implies the smaller one."""
    if not isinstance(term, list):
        return None
    tag = term[0]
    if tag == "req":
        return ("req", term[1], term[3]), term[2]
    if tag in ("tokens_no_purple", "bosses", "families"):
        return (tag,), term[1]
    if tag == "items":
        return ("items", term[1], tuple(term[3])), term[2]
    if tag == "cap":
        return ("cap", term[2]), term[1]
    return None


def _with_value(term, value):
    out = list(term)
    if term[0] in ("req", "items"):
        out[2] = value
    else:
        out[1] = value
    return out


def _is(term, tag):
    return isinstance(term, list) and term[0] == tag


def _implies(x, y) -> bool:
    """A sound (not complete) test that x implies y."""
    if y is True or x is False or x == y:
        return True
    if _is(y, "all"):
        return all(_implies(x, c) for c in y[1:])
    if _is(x, "any"):
        return all(_implies(c, y) for c in x[1:])
    if _is(x, "all") and any(_implies(c, y) for c in x[1:]):
        return True
    if _is(y, "any") and any(_implies(x, c) for c in y[1:]):
        return True
    mx, my = _mono(x), _mono(y)
    if mx is not None and my is not None:
        if mx[0] == my[0]:
            return mx[1] >= my[1]
        # A bound racer meeting the boost means some racer meets it.
        if (mx[0][0] == "cap" == my[0][0] and my[0][1] == -1
                and mx[1] >= my[1]):
            return True
        # Four colours summed never exceed all five summed.
        if (mx[0] == ("tokens_no_purple",) and my[0] == ("req", 6, -1)
                and mx[1] >= my[1]):
            return True
    return False


def simplify(term):
    """Flatten, fold constants, merge same-key leaves and drop implied
    branches. Pure and deterministic (children keep first-seen order)."""
    if isinstance(term, bool):
        return term
    tag = term[0]
    if tag not in ("all", "any"):
        mono = _mono(term)
        if mono is not None and mono[1] <= 0 and tag != "cap":
            return True
        if tag == "cap" and term[1] <= 0 and term[2] == -1:
            return True
        return term
    is_all = tag == "all"
    kids = []
    for child in term[1:]:
        child = simplify(child)
        if _is(child, tag):
            kids.extend(child[1:])
        else:
            kids.append(child)
    merged: List = []
    slot: Dict = {}
    for child in kids:
        if child is is_all:
            continue  # identity element
        if child is (not is_all):
            return not is_all  # absorbing element
        mono = _mono(child)
        if mono is None:
            if child not in merged:
                merged.append(child)
            continue
        key, value = mono
        if key in slot:
            i = slot[key]
            old = _mono(merged[i])[1]
            merged[i] = _with_value(child, max(old, value) if is_all
                                    else min(old, value))
        else:
            slot[key] = len(merged)
            merged.append(child)
    dropped = [False] * len(merged)
    for i, x in enumerate(merged):
        for j, y in enumerate(merged):
            if i == j or dropped[j]:
                continue
            # all: x is redundant when another child implies it.
            # any: x is redundant when it implies another child.
            if (_implies(y, x) if is_all else _implies(x, y)):
                dropped[i] = True
                break
    result = [c for c, d in zip(merged, dropped) if not d]
    if not result:
        return is_all
    if len(result) == 1:
        return result[0]
    return [tag] + result


def depth(term) -> int:
    if not isinstance(term, list) or term[0] not in ("all", "any"):
        return 1
    return 1 + max((depth(c) for c in term[1:]), default=0)


def _contains_ref(term) -> bool:
    if not isinstance(term, list):
        return False
    if term[0] == "ref":
        return True
    return term[0] in ("all", "any") and any(_contains_ref(c) for c in term[1:])


# --- region access -----------------------------------------------------------

def _region_wire(world, enc, region, stack, memo):
    """OR over every simple entrance path from the origin region into
    `region` of the AND of the entrances' terms (unsimplified)."""
    if region.name == world.origin_region_name:
        return True
    key = (region.name, stack)
    if key in memo:
        return memo[key]
    inner = stack | {region.name}
    alternatives = []
    for ent in region.entrances:
        parent = ent.parent_region
        if (parent is None or parent.player != world.player
                or parent.name in inner):
            continue
        term = term_of(ent)
        if term is None:
            raise WinLogicExportError(
                f"CTR win_logic: entrance {ent.name!r} has no term-backed rule")
        upstream = _region_wire(world, enc, parent, inner, memo)
        if upstream is False:
            continue
        alternatives.append(simplify(["all", upstream, term.wire(enc)]))
    out = simplify(["any"] + alternatives)
    memo[key] = out
    return out


# --- the block ---------------------------------------------------------------

def win_locations(world):
    """[(location, kind)] for this slot's win checks, ordered by id."""
    out = []
    for loc in world.multiworld.get_locations(world.player):
        if loc.address is None:
            continue
        kind = win_kind(loc.name)
        if kind is not None:
            out.append((loc, kind))
    return sorted(out, key=lambda pair: int(pair[0].address))


def start_counts(world) -> Dict[str, int]:
    """Precollected copies that Archipelago's logic counts, by AP item id.

    `CollectionState` collects every precollected item whose classification
    is progression (YAML `start_inventory`, `start_inventory_from_pool` and
    the tight-fill backstop's precollect). The server sends those copies as
    `NetworkItem(id, -2, 0)`: location -2 and flags 0, so native cannot tell
    from the wire which of them logic counts. This table is that answer;
    native adds it to its progression-flagged received counts and ignores
    every received entry with location -2 (SCHEMA.md "Received count")."""
    counts: Dict[int, int] = {}
    for item in world.multiworld.precollected_items[world.player]:
        if item.code is not None and item.advancement:
            counts[int(item.code)] = counts.get(int(item.code), 0) + 1
    return {str(code): counts[code] for code in sorted(counts)}


def wire_block(world) -> Dict[str, object]:
    """Build the `win_logic` block for this slot from the installed terms."""
    enc = _Encoder(world)
    memo: Dict = {}
    regions: List = []
    region_index: Dict[str, int] = {}
    checks: Dict[str, Dict[str, object]] = {}
    for loc, kind in win_locations(world):
        term = term_of(loc)
        if term is None:
            raise WinLogicExportError(
                f"CTR win_logic: win check {loc.name!r} has no term-backed rule")
        region = loc.parent_region
        if region.name not in region_index:
            region_index[region.name] = len(regions)
            regions.append(simplify(_region_wire(world, enc, region,
                                                 frozenset(), memo)))
        checks[str(int(loc.address))] = {
            "kind": kind,
            "region": region_index[region.name],
            "rule": simplify(term.wire(enc)),
        }
    for index, region_term in enumerate(regions):
        if _contains_ref(region_term):
            raise WinLogicExportError(
                f"CTR win_logic: region term {index} contains a ref")
    for target in enc.refs:
        entry = checks.get(str(target))
        if entry is None:
            raise WinLogicExportError(
                f"CTR win_logic: ref to location {target}, which has no entry")
        if _contains_ref(entry["rule"]):
            raise WinLogicExportError(
                f"CTR win_logic: ref target {target} itself contains a ref")
    ref_depth = max((depth(checks[str(t)]["rule"]) for t in enc.refs), default=0)
    for key, entry in checks.items():
        d = max(depth(regions[entry["region"]]),
                depth(entry["rule"]) + (ref_depth if _contains_ref(entry["rule"]) else 0))
        if d > MAX_DEPTH:
            raise WinLogicExportError(
                f"CTR win_logic: check {key} nests {d} levels (limit {MAX_DEPTH})")
    return {
        "version": WIN_LOGIC_VERSION,
        "families": [sorted(int(world.item_name_to_id[n]) for n in fam)
                     for fam in weapon_families()],
        "regions": regions,
        "checks": checks,
        "start": start_counts(world),
    }


def wire_size(block) -> int:
    """Compact JSON size in bytes, as the server would send it."""
    return len(json.dumps(block, separators=(",", ":")))
