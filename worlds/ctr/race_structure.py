"""Adventure race structure and the pad race type menu (#208, 0.3.0).

Design: `0.3.0 design - race type selector, Trophy Race-free structure, boss
randomization (#208 #169) - 2026-10-13`, with the rulings of 2026-10-13
21:15 CEST (selector opens on every enterable race pad, Done pads open it,
the `Trophy Race` names stay frozen).

TWO OPTIONS.

* `adventure_structure` (`classic` | `ctr_first`). `classic` is the retail
  order and changes nothing. `ctr_first` makes a track's CTR Challenge its
  first race: a qualifying CTR win (first place with the letters) sends both
  the existing `<Track>: CTR Token Challenge` and `<Track>: Trophy Race`
  checks, and a plain Trophy Race win sends neither. No name, id or item
  count changes; only the event that earns the Trophy location moves.
* `race_type_selector` (`productive` | `always`). Presentation only: when
  native opens the race type menu. No rule reads it.

LOGIC UNDER `ctr_first` (`install_rules`), per destination with both checks:

* The CTR Challenge leaves stage 2. It no longer references the Trophy Race
  location or the physical pad's stage-2 requirement; its entry is the
  destination region, which already carries the physical pad's stage-1 rule
  and racer lock (entrances, `add_warp_pad_unlock_rules`,
  `add_racer_lock_rules`). The letter locations share that stage-1 entry,
  as they share the token entry in `classic`.
* The CTR win and the Trophy check are one event, so both locations get the
  same term: the Trophy Race's own finish terms (difficulty capability, USF
  finish gate) AND the CTR Challenge's own terms (boost floor, letter items
  in Lettersanity modes 2 and 3, Oxide's USF, Tiger Temple's door opener).
* Relic Time Trials and Relic Race perfect checks keep `Ref(Trophy Race)`
  AND the stage-2 requirement, so stage 2 is still "Trophy location checked
  and the physical pad's stage-2 item", now reached through a CTR win.
* Podium rungs keep the pre-change Trophy rule they captured: a plain Trophy
  Race stays enterable at stage 1 and still fires placement checks.

A destination with a Trophy Race check but no CTR Challenge check cannot
serve `ctr_first`, so generation refuses it (`raise_if_unservable`). The
content plan is refused outright: its executable profile is Trophy-only and
its schema, validator and native verifier have no `ctr_first` mode yet.

WIRE (schema 18 running section). `ctr_options.adventure_structure` and
`ctr_options.race_type_selector` are always emitted on an ordinary room as
strings. The `race_structure` block exists only under `ctr_first`: its
`stage1_awards` pairs list every CTR Challenge code whose qualifying win also
sends a Trophy Race code. Native uses that list as the authority and refuses
an unknown version. Content-plan rooms carry neither key (the plan is refused
under `ctr_first`, and the closed envelope stays as it is).
"""
from typing import Dict, List, Tuple

from Options import OptionError

from .logic_terms import TRUE, all_of, set_term, term_of

CLASSIC = 0
CTR_FIRST = 1

STRUCTURE_NAMES = {CLASSIC: "classic", CTR_FIRST: "ctr_first"}
SELECTOR_NAMES = {0: "productive", 1: "always"}

RACE_STRUCTURE_VERSION = 1

TROPHY_SUFFIX = ": Trophy Race"
CTR_SUFFIX = ": CTR Token Challenge"


def ctr_first(world) -> bool:
    return int(world.options.adventure_structure.value) == CTR_FIRST


def raise_if_content_plan(options) -> None:
    """The content plan has no `ctr_first` mode yet (design, "Generation and
    logic": schema, validator and native verifier grow together first)."""
    if int(options.adventure_structure.value) == CTR_FIRST and options.content_pool.value:
        raise OptionError(
            "adventure_structure: ctr_first is not available with a content_pool "
            "yet. The content plan's tracks have no CTR Challenge stage 1. Use "
            "adventure_structure: classic with a content plan.")


def stage1_pairs(world) -> List[Tuple[str, str]]:
    """(Trophy Race name, CTR Token Challenge name) per destination that has
    both, in location creation order (deterministic)."""
    names = [loc.name for loc in world.multiworld.get_locations(world.player)]
    present = set(names)
    pairs = []
    for name in names:
        if name.endswith(TROPHY_SUFFIX):
            ctr = name[:-len(TROPHY_SUFFIX)] + CTR_SUFFIX
            if ctr in present:
                pairs.append((name, ctr))
    return pairs


def raise_if_unservable(world) -> None:
    """Every created Trophy Race needs its CTR Challenge under `ctr_first`.

    Trial tracks set to `trophy_race` and custom tracks whose package has no
    admitted CTR Challenge are the cases that reach this. A Tracker
    regeneration instead checks the room's saved block against the rebuilt
    one (`raise_if_restored_block_differs`)."""
    passthrough = getattr(world.multiworld, "re_gen_passthrough", {}).get(world.game)
    if passthrough:
        raise_if_restored_block_differs(world, passthrough)
        return
    if not ctr_first(world):
        return
    names = {loc.name for loc in world.multiworld.get_locations(world.player)}
    missing = sorted(name[:-len(TROPHY_SUFFIX)] for name in names
                     if name.endswith(TROPHY_SUFFIX)
                     and name[:-len(TROPHY_SUFFIX)] + CTR_SUFFIX not in names)
    if missing:
        raise OptionError(
            "adventure_structure: ctr_first needs a CTR Challenge on every track "
            "with a Trophy Race check, but these have none: "
            + ", ".join(missing)
            + ". Set the trial track options to trophy_and_ctr_challenge, use "
              "custom tracks with a CTR Challenge, or use classic.")


def install_rules(world, player) -> None:
    """Make the Trophy Race check and the CTR Challenge one stage-1 event.

    Runs at the end of `set_rules`, after every layer that ANDs onto either
    location and before the Hit Character capture, so that capture sees the
    final Trophy rule. `add_time_trial_and_ctr_requirements` already left the
    CTR Challenge (and its letters) on the stage-1 entry under `ctr_first`."""
    if not ctr_first(world):
        return
    mw = world.multiworld
    for trophy_name, ctr_name in stage1_pairs(world):
        trophy = mw.get_location(trophy_name, player)
        ctr = mw.get_location(ctr_name, player)
        trophy_term = term_of(trophy)
        ctr_term = term_of(ctr)
        if trophy_term is None or ctr_term is None:
            raise RuntimeError(
                f"CTR ctr_first: {trophy_name!r} or {ctr_name!r} has no term-backed "
                "rule, so the shared stage-1 rule cannot be built")
        both = all_of(trophy_term, ctr_term)
        set_term(trophy, both)
        set_term(ctr, both)


def ctr_entry_rule(world):
    """The CTR Challenge's base entry rule under `ctr_first`: the destination
    region alone (stage 1). None in `classic`, where the caller keeps the
    Trophy reference and stage 2."""
    return TRUE if ctr_first(world) else None


def fill_slot_data(world) -> Dict[str, object]:
    """The two always-emitted `ctr_options` scalars."""
    o = world.options
    return {
        "adventure_structure": STRUCTURE_NAMES[int(o.adventure_structure.value)],
        "race_type_selector": SELECTOR_NAMES[int(o.race_type_selector.value)],
    }


def race_structure_block(world):
    """The `race_structure` block, or None in `classic`."""
    if not ctr_first(world):
        return None
    mw = world.multiworld
    return {
        "version": RACE_STRUCTURE_VERSION,
        "stage1_awards": [[mw.get_location(ctr, world.player).address,
                           mw.get_location(trophy, world.player).address]
                          for trophy, ctr in stage1_pairs(world)],
    }


def raise_if_restored_block_differs(world, passthrough) -> None:
    """Universal Tracker: the room's `race_structure` block must be exactly
    what this build emits for the restored seed. Native refuses a ctr_first
    room without a valid block, so a Tracker that tracked it anyway would
    show checks the client never lets the player race. Refuse instead."""
    saved = passthrough.get("race_structure")
    rebuilt = race_structure_block(world)
    if saved is None and rebuilt is None:
        return
    if rebuilt is None:
        raise OptionError("CTR Tracker: the room has a race_structure block but is not ctr_first")
    if not isinstance(saved, dict) or saved.get("version") != RACE_STRUCTURE_VERSION:
        raise OptionError("CTR Tracker: the ctr_first room has no race_structure block "
                          "this build understands")
    pairs = saved.get("stage1_awards")
    if (not isinstance(pairs, list)
            or [list(p) if isinstance(p, (list, tuple)) else p for p in pairs]
            != rebuilt["stage1_awards"]):
        raise OptionError("CTR Tracker: the room's race_structure award pairs differ "
                          "from the regenerated seed")


def restore_slot_data(options, co) -> None:
    """Universal Tracker restore. Absent keys are a pre-#208 room: classic,
    and the 0.3.0 menu default."""
    by_name = {v: k for k, v in STRUCTURE_NAMES.items()}
    options.adventure_structure.value = by_name.get(
        co.get("adventure_structure", "classic"), CLASSIC)
    sel = {v: k for k, v in SELECTOR_NAMES.items()}
    options.race_type_selector.value = sel.get(
        co.get("race_type_selector", "always"), 1)
