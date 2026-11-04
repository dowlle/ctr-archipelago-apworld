"""Tracks whose FINISH LINE is gated behind Ultimate Sacred Fire (USF).

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
    the line, so only those carry the finish term. `Held 1st` is the one
    exception, by ruling rather than geometry: issue #329 (ruling 2026-09-27)
    reported that holding 1st before the climb is not realistic on a bare
    kart, so it carries the USF term too (see `held_first_term`). Cortex
    Castle's `Held 1st` joined by the 2026-09-28 ruling (a player report of
    many retries even with weapons). `Held 3rd` and `Held 5th` stay free.
    Separately, on easy and medium every track's `Held 1st` carries the
    first-boost-or-one-weapon floor (`Rules.held_first_minimum_term`, ruling
    2026-09-28, dropped on hard by the 2026-09-29 ruling); on these tracks the
    USF term is stricter, ANDs on top of it, and applies on hard too.

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

OXIDE STATION (ruling 2026-08-14 17:15, live pre1 test session; issue #55).
On an empty boost chain at easy/medium shortcut knowledge, Oxide Station is
not realistically finishable and holding 1st is not realistic either -- but a
player who declared HARD shortcut knowledge knows routes that make both work
bare. So this track's finish, and its `Held 1st` rung, carry
`USF OR shortcut_knowledge == hard`, while `Held 3rd`/`Held 5th` stay free.
Hot Air Skyway's `Held 1st` has carried the plain USF term (no escape) since
the 2026-09-27 ruling on issue #329, and Cortex Castle's since the
2026-09-28 ruling. The escape is an OPTION, not a state term: at hard knowledge the gate is
vacuous for this track alone, so a cup that legs both tracks keeps its Hot Air
Skyway half -- which is why the cup term is composed per LEG rather than being
one term per cup.

The game half of that ruling is `AP_CapabilityFireGrant`
(ctr-native-ap `ap/ap_capability.c`): below `AP_CAP_BOOST_USF` a super turbo
pad's grant is clamped to `AP_CAP_CAP_FIRELEVEL` and handed a normal pad's
reserves, so the super pad cannot carry a bare kart across Oxide's finish;
ordinary turbo pads still grant at every tier, which is what leaves the
hard-knowledge route drivable with no boost items at all. `AP_CAP_BOOST_USF`
is the second rank of that enum, which is `USF_BOOST_COUNT` here.

UNIVERSAL TRACKER: the seed's `boost_mode` is restored from slot_data before
rules are rebuilt, so a tracker session evaluates the identical gate. The
`shortcut_knowledge` escape is likewise restored (`_ut_restore_options`).
"""
from typing import Dict

from .capability_contract import (
    unconditional_usf_finish_tracks,
    usf_or_hard_finish_tracks,
)
from . import destinations

#: Received `Progressive Boost` copies that put a player at the USF rank.
USF_BOOST_COUNT = 2

#: Track region names whose finish line needs USF. One entry today; the shape is
#: a set because the marking pass may find more (N. Gin Labs is the standing
#: suspect) and every consumer already iterates.
USF_FINISH_TRACKS = unconditional_usf_finish_tracks()

#: Tracks whose finish needs USF UNLESS the seed declared hard shortcut
#: knowledge (see OXIDE STATION above). These also gate their `Held 1st` rung.
USF_OR_HARD_SK_FINISH_TRACKS = usf_or_hard_finish_tracks()

#: Every finish-gated track, whatever the term shape.
ALL_USF_FINISH_TRACKS = USF_FINISH_TRACKS | USF_OR_HARD_SK_FINISH_TRACKS

#: Received `Progressive Boost` copies that put a player at the first boost
#: rank (reserves at all; USF is the second rank above it).
FIRST_BOOST_COUNT = 1

#: CTR TOKEN CHALLENGE GATE (ruling 2026-09-20, 0.2.1-alpha3).
#: A CTR Token Challenge used to carry no capability term of its own: it was
#: gated only by `can_reach(<track>: Trophy Race)` plus any stage-2 warp-pad
#: requirement. The alpha2 stream report is that the challenge is harder
#: than the race it hangs off -- the three letters and the token have to be
#: taken inside one clean lap. So every CTR Token Challenge now ANDs the first
#: boost rank while the boost pack is on, at EVERY logic difficulty.
#: The Trophy Race prerequisite stays, so a track whose race needs MORE (the
#: USF finish tracks, the difficulty rule, a stage-2 pad requirement) still
#: inherits that higher requirement through `can_reach`; this constant is a
#: floor, never a ceiling. Installed in
#: `Rules.add_time_trial_and_ctr_requirements`, the one site every CTR Token
#: Challenge passes through (retail tracks, the two trial tracks, the Cortex
#: Vortex pad track and custom-track slots alike).
#: It lands on the token location ONLY. The ruling is about COMPLETING the
#: challenge; the letter locations that share the challenge's entry rule keep
#: their own earlier rulings for picking a single letter up (Papu's Pyramid C
#: and T accept Turbo or Mask instead of boost, Oxide Station C keeps the
#: hard-shortcut route, Tiger Temple R needs a door opener), so the floor is
#: installed after that sharing rather than through it.
CTR_CHALLENGE_BOOST_COUNT = FIRST_BOOST_COUNT

#: RELIC TIER GATES (ruling 2026-08-21, posting-pack fixing-pass session).
#: Every Gold and every Platinum Time Trial requires at least the first boost
#: rank: the retail Gold and Platinum targets are set for a kart that can
#: boost, so on an empty boost chain those times are not realistically
#: achievable and a progression item placed there can strand a seed in
#: practice. Sapphire stays free -- finishing the track is enough.
#:
#: On top of that floor, the USF-class tracks carry the full two-boost term:
#: Hot Air Skyway and Oxide Station for BOTH tiers (their targets assume
#: USF-grade pace; Hot Air Skyway's finish line needs USF anyway, and the
#: explicit term here is belt and braces over that finish gate), and
#: N. Gin Labs for Platinum only (the 2026-08-19 triage ruling, subsumed
#: here: without USF two of its item boxes cannot be reached in a Relic Race,
#: which removes the ten-second perfect-box bonus and USF speed together).
#:
#: NO tier gate has a hard-shortcut-knowledge escape, Oxide Station included,
#: unlike Oxide's FINISH gate: route knowledge does not substitute for the
#: missing boost reserves on a relic pace, and for N. Gin Labs it does not
#: restore the unreachable boxes either.
#:
#: Cortex Vortex (2026-09-13 contract) takes the USF tier for Gold and
#: Platinum like Oxide Station. Its relic targets are Oxide Station's retail
#: times as placeholders until the track author supplies real ones.
#: The 2026-09-17 review raises every Platinum target to rank 2 on Easy and
#: Medium. Easy with Blue Fire enabled requires rank 3. Hard keeps these
#: per-track minima. Gold and Sapphire are unchanged.
USF_RELIC_GOLD_TRACKS = frozenset(
    {"Hot Air Skyway", "Oxide Station", "Cortex Vortex"})
USF_RELIC_PLATINUM_TRACKS = frozenset(
    {"Hot Air Skyway", "Oxide Station", "N. Gin Labs", "Cortex Vortex"})


destinations.require_all(USF_RELIC_GOLD_TRACKS | USF_RELIC_PLATINUM_TRACKS)


def relic_tier_boost_min(track, tier, options=None):
    """Progressive Boost copies the `<tier> Time Trial` of `track` requires.

    0 for Sapphire (and anything that is not a relic tier name), so callers
    can feed every Time Trial location through without branching. Without
    options, return the original per-track minimum for compatibility.
    """
    if tier == "Gold":
        return (USF_BOOST_COUNT if track in USF_RELIC_GOLD_TRACKS
                else FIRST_BOOST_COUNT)
    if tier == "Platinum":
        if options is not None and int(options.logic_difficulty.value) <= 1:
            if (int(options.logic_difficulty.value) == 0
                    and bool(options.progressive_boost_blue_fire.value)):
                return 3
            return USF_BOOST_COUNT
        return (USF_BOOST_COUNT if track in USF_RELIC_PLATINUM_TRACKS
                else FIRST_BOOST_COUNT)
    return 0


#: RELIC RACE PERFECT CRATE TERMS (#49). A perfect check is paid by breaking
#: every time crate in the Relic Race, so it takes the Relic Race's entry rule
#: (what Sapphire gets) plus a crate term, and NO relic-time tier term.
#:
#: Ruling (2026-09-29, 0.2.2 player feedback): every
#: `<track>: Relic Race Perfect` requires USF (`USF_BOOST_COUNT` Progressive
#: Boost copies) at every logic difficulty, bound to the racer the track's pad
#: demands. A Hard-logic player had Blizzard Bluff's perfect in logic with no
#: boost, but a time crate in its lake shortcut needs boost. This supersedes
#: the narrower 2026-08-19 N. Gin Labs-only crate term, which it contains.
#: The term covers all 18 relic tracks, the two trial tracks included.
#:
#: Per-track lowering stays possible: `RELIC_PERFECT_BOOST_DEFAULT` applies
#: to every track, and `RELIC_PERFECT_BOOST_OVERRIDES` lowers (or raises) one
#: track. Add an override only with a ruling or measured route evidence.
RELIC_PERFECT_BOOST_DEFAULT = USF_BOOST_COUNT
RELIC_PERFECT_BOOST_OVERRIDES: Dict[str, int] = {}


def relic_perfect_boost_min(track) -> int:
    """Progressive Boost copies `<track>: Relic Race Perfect` requires on top
    of its Relic Race entry rule. USF on every track unless overridden
    (ruling 2026-09-29); 0 would mean no extra term."""
    return RELIC_PERFECT_BOOST_OVERRIDES.get(track, RELIC_PERFECT_BOOST_DEFAULT)


