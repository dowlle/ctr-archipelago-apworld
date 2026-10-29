"""Adventure race structure and the pad race type menu (#208, 0.3.0).

Design: `0.3.0 design - race type selector, Trophy Race-free structure, boss
randomization (#208 #169) - 2026-10-13`, with the rulings of 2026-10-13
21:15 CEST (selector opens on every enterable race pad, Done pads open it,
the `Trophy Race` names stay frozen) and the 0.3.0 rulings of 2026-10-28,
decisions 4 and 12 to 17 (cited by number below).

TWO OPTIONS.

* `adventure_structure` (`classic` | `ctr_first`). `classic` is the retail
  order and changes nothing. `ctr_first` makes a track's CTR Challenge its
  first race: a qualifying CTR win (first place with the letters) sends both
  the existing `<Track>: CTR Token Challenge` and `<Track>: Trophy Race`
  checks. Such a track offers no plain Trophy Race at all (decision 14):
  the CTR Challenge at stage 1, the Relic Race at stage 2. No name, id or
  item count changes; only the event that earns the Trophy location moves.
  A track without a CTR Challenge (a trial track on `trophy_race`, a legacy
  custom track without one) keeps the classic order inside a `ctr_first`
  seed (decision 4).
* `race_type_selector` (`productive` | `always`). Presentation only: when
  native opens the race type menu. The seed value is the starting value; the
  client's Options row can override it (decision 15). No rule reads it.

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
* Podium rungs keep the pre-change Trophy rule they captured: the CTR
  Challenge is the same track and field at the same stage-1 entry, and its
  finishing place earns the rungs with or without the letters (decision
  14). Boxes, Wumpa, Hit and Itemsanity checks keep their destination rules
  for the same reason: the CTR Challenge race is where they are earned.

A destination with a Trophy Race check but no CTR Challenge check keeps its
classic rules: `stage1_pairs` leaves it out, so `install_rules` does not
touch it and native, seeing its Trophy code in no pair, runs it in the
classic order (decision 4). Content plans carry `ctr_first` in the plan
itself (`content_plan.CTR_FIRST`, job J11) with the same rules per entry.

WIRE (schema 18 running section). `ctr_options.adventure_structure` and
`ctr_options.race_type_selector` are always emitted on an ordinary room as
strings. The `race_structure` block exists only under `ctr_first`: its
`stage1_awards` pairs list every CTR Challenge code whose qualifying win also
sends a Trophy Race code. Native uses that list as the authority and refuses
an unknown version; a Trophy code in no pair is a classic track. Content-plan rooms carry neither key: their plan's
`adventure_structure` and its routes say it (job J11), and the closed
envelope stays as it is.
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


def classic_fallbacks(world) -> List[str]:
    """Tracks with a Trophy Race check but no CTR Challenge check, sorted.
    Under `ctr_first` they keep the classic order (decision 4)."""
    names = {loc.name for loc in world.multiworld.get_locations(world.player)}
    return sorted(name[:-len(TROPHY_SUFFIX)] for name in names
                  if name.endswith(TROPHY_SUFFIX)
                  and name[:-len(TROPHY_SUFFIX)] + CTR_SUFFIX not in names)


def check_tracker_block(world) -> None:
    """A Universal Tracker regeneration checks the room's saved block against
    the rebuilt one (`raise_if_restored_block_differs`). A fresh generation
    has nothing to check: a track without a CTR Challenge falls back to the
    classic order instead of refusing (decision 4)."""
    passthrough = getattr(world.multiworld, "re_gen_passthrough", {}).get(world.game)
    if passthrough:
        raise_if_restored_block_differs(world, passthrough)


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
    version = saved.get("version") if isinstance(saved, dict) else None
    if type(version) is not int or version != RACE_STRUCTURE_VERSION:
        raise OptionError("CTR Tracker: the ctr_first room has no race_structure block "
                          "this build understands")
    # The Tracker may hand JSON arrays back as tuples; compare as lists.
    pairs = saved.get("stage1_awards")
    if (not isinstance(pairs, (list, tuple))
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
