"""Tracks whose FINISH LINE is gated behind Ultra Sacred Fire (USF).

Ruling, 2026-08-12 21:33-21:36, from the live v3 test session on seed
89642014421032427840: **Hot Air Skyway cannot be finished at all without USF**
-- the mid-track climb is impassable on vanilla/level-1 boost, so the lap never
completes. Before the ruling, logic and Universal Tracker put `Finish (Any
Position)`, `Finish on Podium` and `Trophy Race` in logic from an empty boost
inventory and all three were unreachable in game.

USF is the SECOND rank of the boost ladder, so the state term is two received
`Progressive Boost` copies (`progressive_capability`: rank 0 no boost, 1 boost,
2 USF, 3 blue fire). The same tier the `Progressive Boost >= 2` entries in
`item_boxes.BOX_RULES` already encode for the boxes past that climb.

WHAT THE GATE IS NOT. It gates FINISHING, not LOADING the track. Everything
reachable before the finish line stays reachable without USF:

  * the pre-climb item boxes -- empirically checked without USF in that same
    session (Hot Air Skyway boxes 1, 2, 6, 7). `BOX_RULES` still carries all of
    HAS 1-7 at `>= 2`; those rows are over-restricted in the safe direction and
    are left alone here, pending their own in-game marking pass;
  * the live-position podium rungs (`Held 1st` / `Held 3rd` / `Held 5th`), which
    fire from the placement listener DURING the race -- `Held 3rd` was likewise
    checked without USF in that session. Only `podium.FINISH_RUNG_KEYS` cross
    the line, so only those carry the term.

WHERE IT PROPAGATES (all installed from `Rules.py`):

  1. `<track>: Trophy Race` -- the finish itself;
  2. `<track>: * Time Trial` / `: CTR Token Challenge` -- for free, because
     `add_time_trial_and_ctr_requirements` gates them on `can_reach` of that
     Trophy Race LOCATION, which now carries the term;
  3. the track's finish rungs -- both their trophy path (via the same
     `can_reach`) and their cup-leg path (below);
  4. every Gem Cup that runs the track as a LEG: completing the cup includes
     finishing that leg, so the cup's own `<Colour> Gem Cup: Gem` and the
     cup-leg branch of EVERY track's rung rule carry the term when that cup
     legs a USF track. Under `randomize_gem_cup_tracks` the leg map is per-seed
     (`gem_cup_legs`), so which cups are gated is a per-seed question.

The cup-leg propagation is deliberately coarse: it gates the whole cup path
rather than modelling leg ORDER (a leg raced before the USF leg needs no USF).
Over-restriction on a rung path can only shrink an early sphere, never make a
seed unbeatable, and the leg order native actually races has not been verified
here -- see the 2026-08-13 build note.

VACUITY (seating spec 2.2, the #145 FillError class). With `progressive_boost`
off no `Progressive Boost` item exists and every kart has vanilla boost
including USF from the start, so the term must resolve to True rather than to a
requirement nothing can satisfy. `usf_term` returns the always-True callable in
that case, exactly as `Rules.add_item_box_rules` treats its own boost terms.

The term reads a `progression` item only because `ctrAPWorld.create_item`
upgrades the boost chain in every randomized-boost seed. That upgrade used to be
conditional on itemsanity or box locations being on; this gate is the reader
that made it unconditional.

UNIVERSAL TRACKER: the seed's `boost_mode` is restored from slot_data before
rules are rebuilt, so a tracker session evaluates the identical gate. The
`shortcut_knowledge` escape below is likewise restored (`_ut_restore_options`).

OXIDE STATION (ruling 2026-08-14 17:15, live pre1 test session): on an
empty boost chain at easy/medium shortcut knowledge, Oxide Station is not
realistically finishable and holding 1st is not realistic either -- but a
player who declared HARD shortcut knowledge knows routes that make it work
bare. So Oxide Station's finish (and, unlike Hot Air Skyway, its `Held 1st`
rung) carries `USF OR shortcut_knowledge == hard`, while `Held 3rd`/`Held 5th`
stay free (holdable mid-race without finishing). The escape is an OPTION, not
a state term: at hard knowledge the whole gate is vacuous for this track.
"""
from typing import Dict, List

from .progressive_capability import BOOST_CHAIN

#: Received `Progressive Boost` copies that put a player at the USF rank.
USF_BOOST_COUNT = 2

#: Track region names whose finish line needs USF unconditionally. The shape is
#: a set because the marking pass may find more (N. Gin Labs is the standing
#: suspect) and every consumer already iterates.
USF_FINISH_TRACKS = frozenset({"Hot Air Skyway"})

#: Tracks whose finish needs USF UNLESS the seed declared hard shortcut
#: knowledge (see OXIDE STATION above). These also gate their `Held 1st` rung.
USF_OR_HARD_SK_FINISH_TRACKS = frozenset({"Oxide Station"})

#: Every finish-gated track, whatever the term shape.
ALL_USF_FINISH_TRACKS = USF_FINISH_TRACKS | USF_OR_HARD_SK_FINISH_TRACKS


def usf_term(options):
    """The `(state, player) -> bool` term for "can finish a USF-gated track".

    Always-True when the boost chain is not randomized (see VACUITY above), so
    callers can AND it unconditionally instead of branching on the option.
    """
    if not bool(options.progressive_boost.value):
        return lambda state, player: True
    return lambda state, player: state.count(BOOST_CHAIN, player) >= USF_BOOST_COUNT


def track_finish_term(track, options):
    """The finish term for one gated track. Hot Air Skyway: the USF term.
    Oxide Station: vacuous at hard shortcut knowledge (the declared knowledge
    IS the alternative route), else the USF term. Only meaningful for members
    of ALL_USF_FINISH_TRACKS."""
    from .item_boxes import SK_HARD
    if (track in USF_OR_HARD_SK_FINISH_TRACKS
            and int(options.shortcut_knowledge.value) == SK_HARD):
        return lambda state, player: True
    return usf_term(options)


def usf_finish_cups(cup_legs: Dict[str, List[str]]) -> frozenset:
    """The cup region names whose completion includes finishing a gated track,
    for this seed's resolved `gem_cup_legs` map."""
    return frozenset(cup for cup, legs in cup_legs.items()
                     if ALL_USF_FINISH_TRACKS.intersection(legs))


def cup_finish_term(legs, options):
    """The AND of the finish terms of every gated leg in one cup. A cup that
    legs both Hot Air Skyway and Oxide Station needs both terms met; at hard
    shortcut knowledge Oxide's term is vacuous and the AND collapses to the
    USF term alone."""
    terms = [track_finish_term(t, options)
             for t in legs if t in ALL_USF_FINISH_TRACKS]
    return lambda state, player: all(t(state, player) for t in terms)


class UsfFinishGate:
    """This seed's USF finish gate: the term, the gated cups, and the
    pre-gate ("can load the track") rule of each gated Trophy Race.

    Built once in `Rules.set_rules` and passed to the consumers rather than
    stashed on the world, so the install-before-rungs order is a visible
    argument instead of a hidden attribute. `install` must run before
    `raceable_rule` is asked for anything -- that is where the pre-gate rules
    are captured.
    """

    def __init__(self, world):
        from .gem_cup_legs import resolved_gem_cup_legs
        legs = resolved_gem_cup_legs(world)
        self.term = usf_term(world.options)
        self.cups = usf_finish_cups(legs)
        self._track_terms = {t: track_finish_term(t, world.options)
                             for t in ALL_USF_FINISH_TRACKS}
        self._cup_terms = {c: cup_finish_term(legs[c], world.options)
                           for c in self.cups}
        self._raceable = {}

    def install(self, world, player):
        """AND each gated track's own term onto its finish LOCATION (Trophy
        Race), and each gated cup's composed term onto its Gem.

        Wraps the existing rule (the `add_warp_pad_unlock_rules` pattern) so a
        Trophy Race that ever grows a requirement of its own keeps it.
        """
        mw = world.multiworld
        names = {loc.name for loc in mw.get_locations(player)}
        for track in sorted(ALL_USF_FINISH_TRACKS):
            name = f"{track}: Trophy Race"
            if name not in names:
                continue
            loc = mw.get_location(name, player)
            base = loc.access_rule
            # "Raceable" = everything that location's reachability asked for
            # BEFORE the finish gate, i.e. Location.can_reach's own definition
            # minus the term. Captured rather than re-derived so the held rungs
            # cannot drift away from the trophy path they used to share.
            self._raceable[track] = (
                lambda state, r=loc.parent_region, b=base: r.can_reach(state) and b(state)
            )
            loc.access_rule = (
                lambda state, b=base, t=self._track_terms[track], p=player:
                b(state) and t(state, p)
            )
        for cup in sorted(self.cups):
            gem = f"{cup}: Gem"
            if gem not in names:
                continue
            loc = mw.get_location(gem, player)
            base = loc.access_rule
            loc.access_rule = (
                lambda state, b=base, t=self._cup_terms[cup], p=player:
                b(state) and t(state, p)
            )

    def raceable_rule(self, track):
        """The captured pre-gate rule for a gated track, or None for any track
        this gate does not cover. Used by the held podium rungs, which fire
        during the race and so must not inherit the finish term."""
        return self._raceable.get(track)

    def held_first_term(self, track):
        """The extra term `Held 1st` carries on tracks where holding 1st bare
        is ruled unrealistic (Oxide Station), or None everywhere else --
        including Hot Air Skyway, whose held rungs are empirically bare-
        reachable and stay free."""
        if track in USF_OR_HARD_SK_FINISH_TRACKS:
            return self._track_terms[track]
        return None

    def cup_term(self, cup):
        """The composed finish term for one gated cup (always-True callables
        collapse the AND where terms are vacuous)."""
        return self._cup_terms[cup]
