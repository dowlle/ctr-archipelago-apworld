"""Character phase (issues #54 / #209): starting character, the 15 character
unlock items, racer-locked warp pads, Penta PAL/NTSC stats, editable stats.

Everything the ruled Route A character phase needs on the apworld side lives
here, so the native consumer has exactly one apworld module to read and the
rest of the world never re-derives any of it. That single-resolver discipline
is copied deliberately from `podium.created_rung_keys_from_options` and the
2026-08-08 feasibility note's section 7 recommendation ("put the precedence in
one resolver ... nothing else in the world may re-derive it").

WHAT IS RULED, AND WHERE
------------------------
Design source is the 2026-07-23 character-phase wayfarer (R2-R5, R7, R8, R15,
R17) plus the 2026-08-08 picker clarification. The parent issue #209 body is
the public scope statement. Concretely:

  * R2/R3  all 16 racers are playable in Adventure; a YAML option picks the
           one you start as, defaulting to a random pick from the 8 vanilla
           Adventure starters.
  * R4     the other 15 are multiworld unlock items. They add ZERO locations.
  * R8/R17 a YAML toggle turns on racer-locked warp pads. Locks ON makes the
           unlock items `progression` (a pad can demand one); locks OFF makes
           them `useful` and nothing in logic ever names a character, so the
           seed plans around the guaranteed starting character only.
  * R15    `penta_stats: ntsc | pal`, NTSC default. The 2026-07-23 wayfarer
           wrote the two labels the wrong way round; corrected 2026-08-21.
           NTSC-U Penta reuses Polar and Pura's ordinary TURN class, and the
           fifth MAX class is the PAL/JP one. The wire numbers did not move:
           0 is still the ordinary table and 1 is still MAX.

ROSTER ORDER IS THE WIRE ORDER, AND IT IS NOT THE ENGINE'S ORDER
----------------------------------------------------------------
`progressive_capability.ROSTER` is the apworld's canonical 16-racer order and
`data/items.json` mints both the per-character capability chains (indices
31..94) and the 16 character unlock items (indices 123..138) in exactly that
order. The engine's own `enum Characters`
(`ctr-native-ap/include/namespace_Vehicle.h:38-56`) numbers the same sixteen
racers in a COMPLETELY different order, and native already carries the
reconciliation table for the capability block
(`ap/ap_capability.c` `AP_CAP_ROSTER_CHARACTER`).

`ROSTER_CHARACTER_ID` below is the apworld's copy of that same mapping, written
name-by-name for the same reason native writes it name-by-name: getting it
wrong would not crash or warn, it would silently lock a pad to the wrong racer.
Anything that leaves this module on the wire carries the ENGINE character id,
because that is the number native can use directly without a second mapping.

WHY RACER LOCKS ARE THEIR OWN WIRE BLOCK AND NOT A 10th `Req` TYPE
------------------------------------------------------------------
The 2026-07-25 Tier-1 source read proposed encoding a racer lock as
`{"type": 9, "count": 1, "colour": <characterID>}` inside the existing `Req`
struct, on the grounds that it is the cheapest possible plumbing. This module
deliberately does NOT do that, for two reasons that both post-date the
proposal:

  1. A `Req` REPLACES the pad's stage-1 requirement. A racer lock is supposed
     to sit ON TOP of whatever the sphere search already assigned ("capture the
     base rule, AND onto it, never replace it" -- the one idiom `Rules.py`
     uses). Overwriting stage 1 with a character would silently delete the
     trophy/key gate the sphere search proved reachable at that pad.
  2. slot_data Contract Sec.2 puts every new requirement type under the
     six-consumer lockstep rule, which is the rule BUG-E was born from
     violating. A new top-level block has no such fan-out: a native that does
     not know the block simply does not see it, rather than hitting a `switch`
     default on a type it cannot evaluate.

So racer locks travel as `racer_locks` (Sec.7h), and the nine `Req` types are
untouched.

SELF-LOCK PREVENTION
--------------------
The named hazard (#209's third "what is still needed" bullet) is a fill that
places character X's unlock item behind a pad that requires character X. With
locks ON the unlock items are `progression`, so AP's own fill only ever seats
them in locations reachable from the current state, and a pad requiring X is
by construction not reachable until X is received -- the deadlock cannot be
constructed. That is an argument, not a proof, so `verify_no_self_lock` below
re-derives it from the FILLED multiworld and raises if it is ever false. It is
wired into `post_fill`, and the test suite drives it directly.
"""
from typing import Dict, List, Optional, Tuple

from BaseClasses import ItemClassification
from Options import OptionError

from .progressive_capability import ROSTER

# ---------------------------------------------------------------------------
# Roster <-> engine identity
# ---------------------------------------------------------------------------

# Wire roster slot -> engine `enum Characters` value. Mirrors native's
# ap/ap_capability.c AP_CAP_ROSTER_CHARACTER exactly; see the module docstring.
ROSTER_CHARACTER_ID: Dict[str, int] = {
    "Crash Bandicoot": 0,   # CRASH_BANDICOOT
    "Coco Bandicoot": 3,    # COCO_BANDICOOT
    "Polar": 6,             # POLAR
    "Pura": 7,              # PURA
    "Neo Cortex": 1,        # NEO_CORTEX
    "N. Tropy": 12,         # N_TROPY
    "Ripper Roo": 10,       # RIPPER_ROO
    "Papu Papu": 9,         # PAPU_PAPU
    "Komodo Joe": 11,       # KOMODO_JOE
    "Pinstripe": 8,         # PINSTRIPE
    "Dingodile": 5,         # DINGODILE
    "Tiny Tiger": 2,        # TINY_TIGER
    "N. Gin": 4,            # N_GIN
    "Fake Crash": 14,       # FAKE_CRASH
    "Nitros Oxide": 15,     # NITROS_OXIDE
    "Penta Penguin": 13,    # PENTA_PENGUIN
}

CHARACTER_ID_TO_NAME: Dict[int, str] = {
    cid: name for name, cid in ROSTER_CHARACTER_ID.items()}

# Structural invariants. A 17th racer, a renamed roster entry or a duplicated
# engine id has to break here rather than mis-lock a pad in a live seed.
assert set(ROSTER_CHARACTER_ID) == set(ROSTER), \
    "characters.ROSTER_CHARACTER_ID and progressive_capability.ROSTER disagree"
assert sorted(ROSTER_CHARACTER_ID.values()) == list(range(16)), \
    "characters.ROSTER_CHARACTER_ID must be a bijection onto engine ids 0..15"

# The 8 racers vanilla CTR lets you take into Adventure = engine ids 0..7
# (Crash, Cortex, Tiny, Coco, N. Gin, Dingodile, Polar, Pura). Anchored on the
# enum, not on memory: `UNLOCK_CHARACTERS` in native's namespace_Main.h is the
# complementary set (Tropy, Penta, Roo, Papu, Joe, Pinstripe, Fake Crash) and
# Oxide is 15.
ADVENTURE_STARTERS: Tuple[str, ...] = tuple(
    name for name, cid in ROSTER_CHARACTER_ID.items() if cid <= 7)
assert len(ADVENTURE_STARTERS) == 8

# The unlock item for a racer IS the racer's name. data/items.json mints all 16
# at codes 35010123..35010138 with count 0 (registered in the frozen #177
# datapackage superset, created per seed) -- the same
# superset-then-per-seed-creation shape podium rungs use.
def unlock_item_name(character: str) -> str:
    assert character in ROSTER_CHARACTER_ID, character
    return character


# ---------------------------------------------------------------------------
# Starting character
# ---------------------------------------------------------------------------

def resolve_starting_character(world) -> str:
    """This seed's starting racer, as a roster name.

    Drawn ONCE, in generate_early, and stashed on the world; every other
    consumer reads `world.ctr_starting_character`. Two option values roll:
    `random_starter` (the ruled default -- uniform over the 8 vanilla
    Adventure starters) and `random_any` (uniform over all 16). Both draw from
    `world.random`, so a seed reproduces.
    """
    key = world.options.starting_character.current_key
    if key == "random_starter":
        return world.random.choice(list(ADVENTURE_STARTERS))
    if key == "random_any":
        return world.random.choice(list(ROSTER))
    name = OPTION_KEY_TO_CHARACTER.get(key)
    if name is None:  # unreachable via AP's own option validation
        raise OptionError(
            f"CTR 'starting_character': unknown value {key!r}. Valid values are "
            f"'random_starter', 'random_any', or one of: "
            f"{', '.join(sorted(OPTION_KEY_TO_CHARACTER))}.")
    return name


def restore_starting_character(world, ctr_options: Dict[str, object]) -> str:
    """Universal Tracker: take the connected seed's starting racer off the wire.

    `ctr_options.starting_character` carries the ENGINE character id. A wire
    from before this feature has no such key, in which case there is nothing to
    restore and the normal draw runs -- that older seed had no character items
    and no racer locks, so whichever racer we pick changes nothing about its
    graph.
    """
    raw = ctr_options.get("starting_character")
    if raw is None:
        return resolve_starting_character(world)
    name = CHARACTER_ID_TO_NAME.get(int(raw))
    if name is None:
        return resolve_starting_character(world)
    return name


def _option_key(character: str) -> str:
    """Roster name -> the snake_case key its Choice option uses.

    'N. Gin' -> 'n_gin', 'Crash Bandicoot' -> 'crash_bandicoot'. Derived rather
    than hand-listed so a roster edit cannot leave the two tables out of step.
    """
    return character.lower().replace(". ", "_").replace(".", "").replace(" ", "_")


OPTION_KEY_TO_CHARACTER: Dict[str, str] = {
    _option_key(name): name for name in ROSTER_CHARACTER_ID}
assert len(OPTION_KEY_TO_CHARACTER) == 16, "option keys collided"


# ---------------------------------------------------------------------------
# Item creation + classification
# ---------------------------------------------------------------------------

def unlocks_enabled(world) -> bool:
    """Whether the 15 unlock items exist this seed (the ruled all-unlocked
    comfort mode, wayfarer gap 7a, is this option turned off)."""
    return bool(world.options.character_unlocks.value)


def racer_locks_enabled(world) -> bool:
    """Racer locks require the unlock items to exist.

    With all-unlocked mode on there is no item that could gate a pad, so a lock
    would either be unsatisfiable or trivially free. `forced_options` logs the
    downgrade; this is the single place that resolves it, so Rules.py,
    create_item and fill_slot_data cannot disagree about whether locks are
    live.
    """
    return bool(world.options.racer_locked_pads.value) and unlocks_enabled(world)


def unlock_classification(world) -> ItemClassification:
    """R17. Locks ON -> a pad can demand a specific racer, so the unlock items
    genuinely gate reachability and MUST be progression (logic state does not
    track useful items, which is the same root cause as the #145 FillError).
    Locks OFF -> nothing in this seed's logic ever names a character, so the
    items gate nothing and `useful` is the correct AP semantics: it relaxes the
    ordered fill instead of inflating an already ~98%-progression pool.

    `useful` rather than pure `filler` is deliberate and is R17's own caveat:
    a character still opens options (and, under per_character capability modes,
    access to that racer's chains), so it is not dead padding.
    """
    from . import progressive_capability
    return (ItemClassification.progression
            if (racer_locks_enabled(world)
                or progressive_capability.unlock_items_are_logic_inputs(world))
            else ItemClassification.useful)


def created_unlock_names(world) -> List[str]:
    """The 15 unlock items this seed puts in the pool: the whole roster minus
    the starting character (which the player already has, and which
    `create_items` pushes as precollected instead).

    Empty in all-unlocked mode -- and empty means EMPTY, not "trimmed": the
    seed either carries the whole family or none of it, the same atomic
    all-or-nothing rule the #14/#15 comfort pack follows. A partial roster
    would be a silent cap on a core feature.
    """
    if not unlocks_enabled(world):
        return []
    start = world.ctr_starting_character
    return [name for name in ROSTER if name != start]


def raise_if_unlocks_exceed_location_supply(world, *, available_supply: int) -> None:
    """RAISE guard: the 15 unlock items must fit in THIS seed's real location
    supply (#178 convention, and the same shape as
    `progressive_capability.raise_if_capability_items_exceed_location_supply`).

    The unlock items bring ZERO locations of their own, so on a deliberately
    reduced seed (Podium Placement Checks off, heavy `exclude_locations`) they
    genuinely do not fit -- the AP invariant the 2026-07-23 wayfarer restated
    as "items == locations, in EVERY mode". Raise rather than dropping items:
    silently shipping 9 of 15 racers would be exactly the kind of unannounced
    cap this project forbids, and it would also strand any racer lock pointing
    at a racer that never got created.

    `available_supply` is the caller's LIVE net-capacity figure (the seed's
    final post-creation unfilled count minus every non-unlock item in the
    COMPLETE current pool -- character unlocks, the comfort pack, itemsanity
    weapons and the progressive packs all included), never a predicted
    constant. The message reports needed vs available and tells the player to
    enable more location checks (ANY enabled location class can supply
    capacity: podium rungs, item boxes, itemsanity checks, ...) or reduce
    item-producing options, without pretending one family is mandatory.
    """
    needed = len(created_unlock_names(world))
    if needed <= 0:
        return
    if available_supply >= needed:
        return
    raise OptionError(
        f"CTR: the character phase adds {needed} character unlock item(s) to "
        f"the pool, but this seed has only {available_supply} unfilled "
        f"location(s) left for them. Character unlocks add no locations of "
        f"their own. Enable more location checks (e.g. Podium Placement "
        f"Checks, Item Box Checks, Itemsanity, or another location family) or "
        f"reduce item-producing options (e.g. set 'character_unlocks' to "
        f"false for all-unlocked mode, which makes every racer available "
        f"from the start and creates no unlock items at all).")


# ---------------------------------------------------------------------------
# Racer-locked warp pads
# ---------------------------------------------------------------------------

# How many of the eligible pads get a racer lock, as a fraction of the eligible
# set. Deliberately conservative and deliberately NOT a YAML knob: the ruled
# surface is one toggle (R8), and CTR's item pool is ~98% progression in every
# config, so an aggressive lock density is exactly the #75-class fill-fragility
# the project has already been bitten by. One extra unique, single-copy
# progression gate per ~4 eligible pads keeps the frontier wide while still
# making the feature visible on every seed that enables it.
_LOCK_FRACTION = 0.25
_LOCK_MIN = 1
_LOCK_MAX = 6


def _pad_is_free(req: Optional[dict]) -> bool:
    """True for a pad the sphere search left open at spawn.

    The free-pad convention is load-bearing (slot_data Contract Sec.4): a free
    stage 1 is emitted as `{type:1, count:0}` (Trophy x0), and `type:0` means
    the pad is not randomized at all. Both are sphere-0 backbone and neither
    may take a lock -- see `eligible_lock_pads`.
    """
    if req is None:
        return True
    t = int(req.get("type", 0))
    if t == 0:
        return True
    return t == 1 and int(req.get("count", 0)) <= 0


def eligible_lock_pads(world) -> List[str]:
    """Pad exit names that may carry a racer lock, in a stable order.

    Excluded, each for a stated reason:

      * `bootstrap` pads (data/warp_pad_ids.json) -- the always-open N. Sanity
        Beach starters that MUST stay reachable from an empty inventory so
        trophies can be earned. That flag is the file's own description of the
        solvability backbone.
      * any pad whose resolved stage 1 is FREE -- the per-seed free subset is
        what guarantees sphere 0 is non-empty (`warp_pad_logic.run_sphere_search`
        step 1). Locking one behind a unique single-copy item would collapse
        sphere-0 breadth to whatever the fill happens to seat first.
      * pads outside `world.warp_pad_unlock` -- a pad kind this seed does not
        randomize (arenas with `include_battle_arenas` off, cups with
        `include_gem_cups` off) keeps its vanilla gate untouched.
    """
    unlock = getattr(world, "warp_pad_unlock", {}) or {}
    pad_ids = getattr(world, "warp_pad_ids", {}) or {}
    out: List[str] = []
    for pad_name in sorted(unlock):
        meta = pad_ids.get(pad_name)
        if meta is None:
            continue
        if meta.get("bootstrap"):
            continue
        if _pad_is_free(unlock.get(pad_name)):
            continue
        out.append(pad_name)
    return out


def resolve_racer_locks(world) -> Dict[str, str]:
    """{pad exit name -> roster name required to enter it}.

    Resolved ONCE per seed, in `Regions.create_regions` right after the sphere
    search has produced `world.warp_pad_unlock`, and stashed on the world. This
    is the same "draw once, store on the world, never recompute" rule
    `gem_cup_legs` and the #109 active box slots follow, and for the same
    reason: Rules.py, `fill_slot_data` and the spoiler must not be able to
    disagree about which pads are locked.

    The required racer is never the starting character. A lock on the racer you
    already have would be satisfied at spawn and would spend an eligible pad on
    nothing.
    """
    if not racer_locks_enabled(world):
        return {}
    pads = eligible_lock_pads(world)
    if not pads:
        return {}
    n = max(_LOCK_MIN, min(_LOCK_MAX, int(len(pads) * _LOCK_FRACTION)))
    n = min(n, len(pads))
    chosen_pads = world.random.sample(pads, n)
    candidates = [c for c in ROSTER if c != world.ctr_starting_character]
    return {pad: world.random.choice(candidates) for pad in sorted(chosen_pads)}


def reconstruct_racer_locks_from_wire(world, passthrough: Dict[str, object]
                                      ) -> Dict[str, str]:
    """Universal Tracker: pin the connected seed's locks instead of re-drawing.

    `resolve_racer_locks` samples `world.random`, and a passthrough carries no
    RNG replay, so a re-draw would produce a DIFFERENT set of locked pads and
    UT would report a graph the server does not have. Read the wire block back
    instead. An absent or malformed block falls back to "no locks", which is
    the correct reading of a pre-character-phase seed.
    """
    block = (passthrough or {}).get("racer_locks") or {}
    pads = block.get("pads") or {}
    if not isinstance(pads, dict) or not pads:
        return {}
    pad_ids = getattr(world, "warp_pad_ids", {}) or {}
    by_level_id = {str(meta["level_id"]): name
                   for name, meta in pad_ids.items()}
    out: Dict[str, str] = {}
    for lid, character_id in pads.items():
        pad_name = by_level_id.get(str(lid))
        name = CHARACTER_ID_TO_NAME.get(int(character_id))
        if pad_name is not None and name is not None:
            out[pad_name] = name
    return out


def racer_lock_slot_data(world) -> Dict[str, object]:
    """The `racer_locks` wire block (slot_data Contract Sec.7h).

    Shape: {"enabled": bool, "pads": {"<physical pad LevelID>": <engine
    characterID 0..15>}}. Keys are physical pad LevelIDs as JSON strings, the
    same keying `warp_pad_unlock` uses, so native reads them through the parser
    it already has. Values are ENGINE character ids, not roster slots, so
    native's gate needs no second mapping table.

    `enabled` is emitted even when the option is off (with an empty `pads`), so
    a tracker can tell "locks off" from "old seed" without inferring from block
    absence -- the same reason `itemsanity` and `shortcut_knowledge` are always
    emitted as raw scalars.
    """
    pad_ids = getattr(world, "warp_pad_ids", {}) or {}
    locks = getattr(world, "ctr_racer_locks", {}) or {}
    pads: Dict[str, int] = {}
    for pad_name, character in locks.items():
        meta = pad_ids.get(pad_name)
        if meta is None:
            continue
        pads[str(meta["level_id"])] = ROSTER_CHARACTER_ID[character]
    return {"enabled": racer_locks_enabled(world), "pads": pads}


def verify_no_self_lock(world) -> None:
    """Post-fill proof that no racer's unlock item sits behind that racer's own
    lock (issue #209, "character-locked-pad solvability logic gets built and
    proven ... so a fill can never place a character's own unlock item behind a
    pad that requires that same character").

    Re-derived from the FILLED multiworld rather than argued: for every locked
    pad, walk to the location actually holding the required racer's unlock item
    and confirm that location is reachable in a state that does NOT hold it.
    With the unlock items as progression that is what AP's fill already
    guarantees, so this never fires -- which is the point. If the invariant is
    ever broken by a future change to the lock selection, this raises here at
    generation instead of shipping a seed nobody can finish.
    """
    locks = getattr(world, "ctr_racer_locks", {}) or {}
    if not locks:
        return
    mw = world.multiworld
    player = world.player
    needed = {unlock_item_name(c) for c in locks.values()}
    holders = {
        loc.item.name: loc
        for loc in mw.get_filled_locations()
        if loc.item is not None and loc.item.player == player
        and loc.item.name in needed
    }
    for pad_name, character in sorted(locks.items()):
        item_name = unlock_item_name(character)
        loc = holders.get(item_name)
        if loc is None:
            # Not placed in this multiworld's location set at all (start
            # inventory, or another world holds it under item links). Nothing
            # local can be behind the lock.
            continue
        state = mw.get_all_state(False)
        # Strip the item OUTRIGHT rather than calling `state.remove(loc.item)`.
        # `get_all_state` can end up holding more than one logical copy of a
        # single placed item (it collects the pool AND sweeps the placements),
        # so a single decrement leaves the count at 1 and the check silently
        # passes whatever the placement is -- a verifier that cannot fail. Set
        # the count to zero and invalidate the region caches, which is exactly
        # "a state that does not hold this racer".
        state.prog_items[player].pop(item_name, None)
        state.reachable_regions[player] = set()
        state.blocked_connections[player] = set()
        state.stale[player] = True
        if not loc.can_reach(state):
            raise OptionError(
                f"CTR racer-locked pads: '{item_name}' was placed at "
                f"'{loc.name}', which is not reachable without '{item_name}' "
                f"itself -- the pad '{pad_name}' requires that racer. This is "
                f"the self-lock deadlock issue #209 names; the seed would be "
                f"unfinishable. Re-roll, or set 'racer_locked_pads' to false.")


# ---------------------------------------------------------------------------
# Stat ownership: progressive vs editable vs vanilla, and Penta
# ---------------------------------------------------------------------------

# Resolved stat SOURCE, as it goes on the wire. Native must NOT re-implement
# the precedence rule -- it receives the outcome. (2026-08-08 note section 7
# recommendation 3, and Lessons Learned #12: the cheapest way for the text, the
# rules and the engine to agree is for only one of them to own the rule.)
STAT_SOURCE_VANILLA = 0
STAT_SOURCE_PROGRESSIVE = 1
STAT_SOURCE_EDITABLE = 2

# Resolved stat OWNERSHIP granularity.
STAT_OWNER_NONE = 0
STAT_OWNER_GLOBAL = 1
STAT_OWNER_PER_CHARACTER = 2

# 0 is the ordinary TURN-class table, 1 is the PAL/JP MAX table. The region
# labels were inverted until 2026-08-21; these numbers were always correct and
# are what native reads, so they did not move.
PENTA_NTSC = 0
PENTA_PAL = 1


def effective_stat_config(world) -> Tuple[int, int, bool]:
    """`(source, owner, editable)` -- THE resolver for the ruled precedence.

    The 2026-08-08 ruling, restated exactly:

      * progressive stats non-off wins outright. The panel is read-only and
        there is no edit control at all, whatever `editable_stats` says.
      * progressive off + editable non-off -> the editor is available at the
        editable option's own granularity.
      * both off -> vanilla class stats, read-only.

    Enabling both is explicitly NOT an error (the ruling: "this simple
    combination does not invalidate or reject a seed"). `forced_options` logs a
    downgrade-with-warning line for it, matching the #178 convention for a
    combination that only leaves an option with nothing to do.
    """
    prog = int(world.options.progressive_stats.value)
    edit = int(world.options.editable_stats.value)
    if prog:
        return (STAT_SOURCE_PROGRESSIVE, prog, False)
    if edit:
        return (STAT_SOURCE_EDITABLE, edit, True)
    return (STAT_SOURCE_VANILLA, STAT_OWNER_NONE, False)


def fill_slot_data(world) -> Dict[str, object]:
    """This module's contribution to `ctr_options`, plus nothing else.

    The `racer_locks` top-level block is emitted separately by
    `racer_lock_slot_data` because it is a block, not a scalar. Every scalar
    here is emitted UNCONDITIONALLY, on or off, so a tracker or a diagnostic
    reads the seed's real configuration without inferring it from the presence
    of other keys -- the convention `itemsanity` / `shortcut_knowledge` set.

    No `schema_version` bump: the Q28 standing ruling already makes 7
    unconditional on every 0.2.0 seed, and native reads `ctr_options` by
    explicit named key, so a native that does not know these keys never sees
    them (slot_data Contract Sec.3).
    """
    source, owner, editable = effective_stat_config(world)
    start = world.ctr_starting_character
    return {
        "starting_character": ROSTER_CHARACTER_ID[start],
        "starting_stat_class": int(world.options.starting_stat_class.value),
        # Logic-relevant, and therefore load-bearing for Universal Tracker: it
        # decides whether 15 unlock items exist at all. A UT re-generation that
        # falls back to the tracking player's own default here rebuilds a
        # DIFFERENT pool than the seed has -- and on a reduced seed it does not
        # even fit, which is how the #54/#209 fuzz found this.
        "character_unlocks": unlocks_enabled(world),
        "racer_locked_pads": racer_locks_enabled(world),
        "penta_stats": int(world.options.penta_stats.value),
        "editable_stats": int(world.options.editable_stats.value),
        # The RESOLVED outcome. Native reads these three and never re-derives
        # the precedence between progressive_stats and editable_stats.
        "stat_source": source,
        "stat_owner": owner,
        "stat_editing_allowed": bool(editable),
    }
