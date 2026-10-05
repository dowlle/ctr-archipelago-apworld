"""Logic terms: one definition for an access rule and its `slot_data` export.

Race-loss DeathLink stakes (0.2.4, ruling 2026-10-01, option A): native decides
whether a race has stakes by evaluating each win check's logic against the
items it has received. That logic must be the logic Archipelago fills and
Universal Tracker tracks with, not a hand-written copy (Lessons Learned #12,
and research 02, where a hand-written mirror drifted on its first pass).

So the rule layers that touch a win check build TERM objects instead of bare
lambdas. A term has two faces:

* `compile()` returns the `state -> bool` access rule. It is built once and
  cached on the term, and has the same shape the hand-written layers had: an
  `And` is `lambda state, previous=..., extra=...: previous(state) and
  extra(state)`, so the wrapper-chain idiom (`__defaults__[0]` is the rule it
  wraps) and rule sharing by reference keep working. Captured values are
  default arguments, never closure cells.
* `wire(enc)` returns the JSON form of the `win_logic` block (slot_data
  Contract 7m, `SCHEMA.md`). `enc` resolves item and location names to ids.

`set_term` installs a term on a location or entrance and marks it, and
`and_term` ANDs a term onto whatever is installed. A rule that someone later
replaces with a plain lambda loses the mark, and the exporter refuses to
export it (`win_logic.WinLogicExportError`) instead of emitting stale logic.
"""
from typing import Callable, Iterable, Optional, Sequence, Tuple

_TERM_ATTR = "ctr_term"
_RULE_ATTR = "_ctr_term_rule"


class Term:
    """Base class. Subclasses implement `_build` and `wire`."""

    _compiled: Optional[Callable] = None

    def compile(self) -> Callable:
        if self._compiled is None:
            self._compiled = self._build()
        return self._compiled

    def _build(self) -> Callable:  # pragma: no cover - abstract
        raise NotImplementedError

    def wire(self, enc):  # pragma: no cover - abstract
        raise NotImplementedError


def _always_true(state):
    return True


def _always_false(state):
    return False


class _Const(Term):
    def __init__(self, value: bool):
        self.value = value

    def _build(self):
        return _always_true if self.value else _always_false

    def wire(self, enc):
        return self.value

    def __repr__(self):
        return "TRUE" if self.value else "FALSE"


TRUE = _Const(True)
FALSE = _Const(False)


class And(Term):
    """Binary AND, left evaluated first. Built left-nested by `all_of` so a
    term ANDed onto an installed rule compiles to a wrapper whose first
    default argument IS the installed rule object."""

    def __init__(self, left: Term, right: Term):
        self.left = left
        self.right = right

    def _build(self):
        return (lambda state, previous=self.left.compile(), extra=self.right.compile():
                previous(state) and extra(state))

    def wire(self, enc):
        return ["all", self.left.wire(enc), self.right.wire(enc)]


def all_of(*terms: Term) -> Term:
    """Left-nested AND of `terms`; a single term is returned as is."""
    assert terms
    out = terms[0]
    for term in terms[1:]:
        out = And(out, term)
    return out


class Or(Term):
    def __init__(self, *children: Term):
        assert len(children) >= 2
        self.children = tuple(children)

    def _build(self):
        fns = tuple(c.compile() for c in self.children)
        if len(fns) == 2:
            return (lambda state, first=fns[0], second=fns[1]:
                    first(state) or second(state))
        return lambda state, fns=fns: any(f(state) for f in fns)

    def wire(self, enc):
        return ["any"] + [c.wire(enc) for c in self.children]


class Has(Term):
    """`state.has(item, player, count)`."""

    def __init__(self, item: str, count: int, player: int):
        self.item = item
        self.count = count
        self.player = player

    def _build(self):
        return (lambda state, i=self.item, p=self.player, n=self.count:
                state.has(i, p, n))

    def wire(self, enc):
        return enc.has(self.item, self.count)


class TextRule(Term):
    """A world.json / Regions text rule (`has('Key', 2) and ...`), already
    parsed into (item, count) pairs by `Rules.make_rule`. Compiles to exactly
    the closure `make_rule` always returned."""

    def __init__(self, requirements: Sequence[Tuple[str, int]], player: int):
        self.requirements = tuple(requirements)
        self.player = player

    def _build(self):
        if not self.requirements:
            return lambda state: True

        def rule(state, requirements=self.requirements, player=self.player):
            for item, count in requirements:
                if not state.has(item, player, count):
                    return False
            return True
        return rule

    def wire(self, enc):
        if not self.requirements:
            return True
        return ["all"] + [enc.has(i, n) for i, n in self.requirements]


class ItemSum(Term):
    """The received counts of `items`, summed, reach `count` (the any-of
    aggregate, `Rules._agg_has`)."""

    def __init__(self, items: Iterable[str], count: int, player: int):
        self.items = tuple(items)
        self.count = count
        self.player = player

    def _build(self):
        return (lambda state, ns=self.items, p=self.player, n=self.count:
                sum(state.count(i, p) for i in ns) >= n)

    def wire(self, enc):
        return enc.item_sum(self.items, self.count)


class HasAny(Term):
    """`state.has_any(items, player)`."""

    def __init__(self, items: Iterable[str], player: int):
        self.items = tuple(items)
        self.player = player

    def _build(self):
        return (lambda state, ns=self.items, p=self.player:
                state.has_any(ns, p))

    def wire(self, enc):
        return enc.items("sum", 1, self.items)


class HasEach(Term):
    """Every item in `items` held once. `style` keeps the exact call each
    layer always used: "each" is `all(state.has(n) for n in items)`,
    "has_all" is `state.has_all(items)`. Same truth value."""

    def __init__(self, items: Iterable[str], player: int, style: str = "each"):
        assert style in ("each", "has_all")
        self.items = tuple(items)
        self.player = player
        self.style = style

    def _build(self):
        if self.style == "has_all":
            return (lambda state, ns=self.items, p=self.player:
                    state.has_all(ns, p))
        return (lambda state, ns=self.items, p=self.player:
                all(state.has(n, p) for n in ns))

    def wire(self, enc):
        if not self.items:
            return True
        return enc.items("distinct", len(set(self.items)), self.items)


class Distinct(Term):
    """`state.has_from_list_unique(items, player, count)`."""

    def __init__(self, items: Iterable[str], count: int, player: int):
        self.items = tuple(items)
        self.count = count
        self.player = player

    def _build(self):
        return (lambda state, ns=self.items, p=self.player, n=self.count:
                state.has_from_list_unique(ns, p, n))

    def wire(self, enc):
        return enc.items("distinct", self.count, self.items)


class Cap(Term):
    """`progressive_capability.gate_satisfied` with a boost minimum and an
    optional bound racer (no stat terms). Callers that want the vacuous
    always-True form when the boost chain is off use `boost_cap`."""

    def __init__(self, world, boost: int, racer: Optional[str]):
        self.world = world
        self.boost = boost
        self.racer = racer

    def _build(self):
        from .progressive_capability import gate_satisfied
        return (lambda state, w=self.world, p=self.world.player, b=self.boost,
                r=self.racer, gate=gate_satisfied:
                gate(w, state, p, boost_min=b, required_character=r))

    def wire(self, enc):
        return enc.cap(self.boost, self.racer)


def boost_cap(world, racer: Optional[str], boost: int) -> Term:
    """The term behind `usf_finish.boost_term`: TRUE while the boost chain is
    not randomized (every kart has vanilla boost, seating spec 2.2), else
    `Cap(boost, racer)`."""
    if not bool(world.options.progressive_boost.value):
        return TRUE
    return Cap(world, boost, racer)


class BossWins(Term):
    """At least `count` of the boss-won companion flags are held: the
    `bosses_required_goal` predicate (`_install_goal`), native's
    `AP_ComposedBossesWon`."""

    def __init__(self, flags: Iterable[str], count: int, player: int):
        self.flags = tuple(flags)
        self.count = count
        self.player = player

    def _build(self):
        return (lambda state, fs=self.flags, n=self.count, player=self.player:
                sum(state.has(f, player) for f in fs) >= n)

    def wire(self, enc):
        return ["bosses", self.count]


class Families(Term):
    """At least `count` distinct useful weapon families are held
    (`itemsanity.family_count`). The family table travels once per block."""

    def __init__(self, families, count: int, player: int):
        self.families = tuple(tuple(f) for f in families)
        self.count = count
        self.player = player

    def _build(self):
        from .itemsanity import family_count
        return (lambda state, fam=self.families, n=self.count, p=self.player,
                fc=family_count: fc(state, p, fam) >= n)

    def wire(self, enc):
        return enc.families(self.families, self.count)


class Ref(Term):
    """`state.can_reach(<location>, "Location", player)`: region access AND
    that location's own rule. On the wire, a reference to that check's
    entry."""

    def __init__(self, location: str, player: int):
        self.location = location
        self.player = player

    def _build(self):
        return (lambda state, t=self.location, p=self.player:
                state.can_reach(t, "Location", p))

    def wire(self, enc):
        return enc.ref(self.location)


# --- installing terms on locations and entrances ---------------------------

def set_term(spot, term: Term) -> Callable:
    """Install `term` as `spot`'s access rule and mark it as term-backed."""
    rule = term.compile()
    setattr(spot, _TERM_ATTR, term)
    setattr(spot, _RULE_ATTR, rule)
    spot.access_rule = rule
    return rule


def term_of(spot) -> Optional[Term]:
    """The term behind `spot`'s CURRENT access rule, or None when the rule
    was installed some other way (or replaced after the term was set)."""
    term = getattr(spot, _TERM_ATTR, None)
    if term is None or spot.access_rule is not getattr(spot, _RULE_ATTR, None):
        return None
    return term


def and_term(spot, term: Term) -> Callable:
    """AND `term` onto `spot`'s current rule, keeping it term-backed when it
    was. A rule installed some other way is still wrapped, with the same
    `previous` / `extra` shape, but stays unexportable."""
    base = term_of(spot)
    if base is not None:
        return set_term(spot, And(base, term))
    previous = spot.access_rule
    rule = (lambda state, previous=previous, extra=term.compile():
            previous(state) and extra(state))
    spot.access_rule = rule
    return rule


def as_state_player(term: Term) -> Callable:
    """`(state, player) -> bool` view of a term, for the consumers that still
    call finish terms with a player argument (podium rungs, goal predicates).
    The player is the term's own; the argument is accepted and ignored, as the
    closures it replaces always received their own player."""
    fn = term.compile()
    return lambda state, player, fn=fn: fn(state)
