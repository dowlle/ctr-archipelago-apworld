"""Cortex Vortex as a full warp-pad track (design 2026-09-13, contract frozen
10:12 CEST).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. With the
`cortex_vortex_track` option on, Cortex Vortex (the Lockheart package already
pinned for the Oxide 2 venue) becomes an ordinary pad destination: a Trophy
Race at stage 1, then the three relic Time Trials and a CTR Token Challenge at
stage 2, like a retail trophy track. It has no origin pad. One of the 27
existing destinations is drawn per seed to go without a pad (the "dropped
destination"); Cortex Vortex takes its place in the pad set BEFORE destination
shuffle, and every location owned by the dropped destination is removed from
the seed. Native serves the destination under the virtual ID 110 on host
LevelID 13 and sends the codes below directly.

WHO OWNS THE SEMANTICS. The apworld owns the option, the dropped-destination
draw, the names, the logic and the `cortex_vortex_track` slot_data block. Native
owns the serving state, the virtual destination load, the relic targets and the
reward dispatch. Neither half re-derives the other's decisions: every code
native sends is on the wire.

THE POOL MODEL, and where each piece lives.

  * The draw (`draw_dropped_destination`) runs first in `generate_early`, before
    lettersanity selection and the relic-tier draw, because both read it. It is
    uniform over `eligible_dropped_destinations`. With the option off it draws
    nothing, so an option-off seed keeps the identical RNG stream.
  * The pad set: `home_destinations` maps the dropped destination's physical
    pad to 110. `warp_pad_logic.build_warp_pad_map` permutes the pool with that
    substitution, and places 110 on the dropped pad when that pad takes part in
    no shuffle pool.
  * Removal: every per-destination family asks `dropped_track(options)` and
    skips it (podium, lettersanity, Wumpa, item boxes, trial races), the relic
    tier pool is scoped by `active_time_trial_tracks`, and `Regions` skips the
    dropped region's static locations.

DATAPACKAGE STABILITY. This class claims the block 35026000 and registers its
eight names UNCONDITIONALLY: Trophy 35026000, Sapphire/Gold/Platinum Time Trial
35026001-003, CTR Token Challenge 35026004 and Letter C/T/R 35026006-008.
35026005 is RESERVED for a later `Cortex Vortex: Relic Race Perfect` and is not
minted. The five podium rungs 35026010-014 ride the podium class, which already
owns every rung name (the trial-track rung precedent). The three letter ITEMS
35010200-202 live in `LETTER_ITEM_DATA` below, outside the positional
`data/items.json` table, because that table is documented as the closed shipped
0..199 index range (see custom_lettersanity.CUSTOM_LETTER_ITEM_DATA, the same
choice for the same reason). The Wumpa check reuses 35016121.

FROZEN-NAME WARNING. These names were approved through the considered
datapackage unfreeze of 2026-09-13. They are permanent; their ids never move.
"""
import json
import pkgutil
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from BaseClasses import ItemClassification

from .location_class import LocationClass

CORTEX_VORTEX = "Cortex Vortex"

#: Virtual destination ID, outside {0..27, 100..104}.
DESTINATION_ID = 110
#: Host LevelID native loads the pinned package on (retail Oxide Station).
HOST_LEVEL_ID = 13
#: The pinned Lockheart LEV/VRM pair, the same hashes as `oxide_final_venue`.
LEV_SHA256 = "4e3a2daf56c67be3ac645d3bb5375e516c828a0bca24c35ac69b3366c466fe13"
VRM_SHA256 = "4131444b9d1d53971befcfd11349efceaf887c20b795c8890fdcb2c36bdff07d"
WIRE_VERSION = 1

TROPHY_CODE = 35026000
RELIC_CODES = (35026001, 35026002, 35026003)
CTR_TOKEN_CODE = 35026004
#: Reserved for `Cortex Vortex: Relic Race Perfect`; deliberately NOT minted.
RELIC_PERFECT_RESERVED_CODE = 35026005
LETTER_CODES = (35026006, 35026007, 35026008)
#: The five podium rungs, registered by the podium class in SLOT_ORDER.
PODIUM_CODE_BASE = 35026010
LETTER_ITEM_CODES = (35010200, 35010201, 35010202)

LETTERS = ("C", "T", "R")
RELIC_TIER_LABELS = ("Sapphire", "Gold", "Platinum")

TROPHY_NAME = f"{CORTEX_VORTEX}: Trophy Race"
CTR_TOKEN_NAME = f"{CORTEX_VORTEX}: CTR Token Challenge"


def relic_name(tier_label: str) -> str:
    return f"{CORTEX_VORTEX}: {tier_label} Time Trial"


def letter_location_name(letter: str) -> str:
    return f"{CORTEX_VORTEX}: Letter {letter}"


def letter_item_name(letter: str) -> str:
    """Same convention as `lettersanity.item_name`."""
    return f"Letter {letter} ({CORTEX_VORTEX})"


#: The three letter items, registered beside the positional item table.
LETTER_ITEM_DATA = tuple({
    "name": letter_item_name(letter),
    "code": code,
    "count": 0,
    "classification": ItemClassification.progression,
} for letter, code in zip(LETTERS, LETTER_ITEM_CODES))


# ---------------------------------------------------------------------------
# The 27 destinations a seed can drop
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def destination_table() -> Dict[int, Tuple[str, str, str]]:
    """{destination LevelID: (pad exit name, destination region, kind)} for
    the 27 retail destinations, from data/warp_pad_ids.json and the pad-exit
    targets in data/world.json (never retyped: a cup pad's region is
    "<Colour> Gem Cup", not its pad name minus " Warp Pad")."""
    pads = json.loads(pkgutil.get_data(
        __package__, "data/warp_pad_ids.json").decode("utf-8"))["pads"]
    world = json.loads(pkgutil.get_data(
        __package__, "data/world.json").decode("utf-8"))
    targets = {ex["name"]: ex["target"]
               for region in world["regions"]
               for ex in region.get("exits", []) if ex["name"] in pads}
    return {meta["level_id"]: (pad, targets[pad], meta["kind"])
            for pad, meta in pads.items()}


def track_key(pad_name: str) -> str:
    """HUB_STATIC / warp_pad_logic track key of a pad exit ("Red Cup")."""
    return pad_name[: -len(" Warp Pad")]


# ---------------------------------------------------------------------------
# Per-seed state, read from the options object
# ---------------------------------------------------------------------------
#
# LocationClass subclasses only see `options`, so the drawn destination lives
# there as `options._cortex_vortex_dropped` (the lettersanity-selection
# precedent). The two-stage fill probe shares the real world's options object,
# so it sees the same destination.

def track_on(options) -> bool:
    toggle = getattr(options, "cortex_vortex_track", None)
    if toggle is None:
        return False
    try:
        return int(toggle.value) == 1
    except (AttributeError, TypeError, ValueError):
        return False


def dropped_level_id(options) -> Optional[int]:
    if not track_on(options):
        return None
    return getattr(options, "_cortex_vortex_dropped", None)


def dropped_region(options) -> Optional[str]:
    lid = dropped_level_id(options)
    return None if lid is None else destination_table()[lid][1]


def dropped_pad(options) -> Optional[str]:
    lid = dropped_level_id(options)
    return None if lid is None else destination_table()[lid][0]


def dropped_track(options) -> Optional[str]:
    """The dropped destination's track key, which is also its region name for
    every race, trial and crystal destination (the per-track families only ever
    key on those)."""
    pad = dropped_pad(options)
    return None if pad is None else track_key(pad)


def home_destinations(options) -> Dict[int, int]:
    """{physical pad LevelID: destination LevelID} for every pad whose
    unshuffled destination is not its own LevelID. Empty with the option off;
    otherwise the dropped destination's pad maps to 110."""
    lid = dropped_level_id(options)
    return {} if lid is None else {lid: DESTINATION_ID}


def active_time_trial_tracks(options, retail_tracks) -> List[str]:
    """The tracks whose Time Trials exist in this seed: the retail relic
    tracks minus a dropped one, plus Cortex Vortex when the option is on."""
    dropped = dropped_track(options)
    out = [t for t in retail_tracks if t != dropped]
    if track_on(options):
        out.append(CORTEX_VORTEX)
    return out


def selected_letters(options) -> Tuple[str, ...]:
    return tuple(getattr(options, "_lettersanity_selected", {}).get(
        CORTEX_VORTEX, ()))


def created_letter_item_names(options) -> List[str]:
    """Letter items this seed pools for Cortex Vortex: the selected letters
    in `locations_and_items`, all three in `items_only`, none otherwise."""
    if not track_on(options):
        return []
    mode = int(getattr(getattr(options, "lettersanity", None), "value", 0) or 0)
    if mode == 3:
        return [letter_item_name(letter) for letter in LETTERS]
    if mode == 2:
        chosen = selected_letters(options)
        return [letter_item_name(letter) for letter in LETTERS if letter in chosen]
    return []


def required_letter_item_names(options) -> List[str]:
    """Letter items the CTR Token Challenge needs (modes 2 and 3)."""
    return created_letter_item_names(options)


# ---------------------------------------------------------------------------
# The location class
# ---------------------------------------------------------------------------

class CortexVortexTrackLocationClass(LocationClass):
    """Trophy, relic tiers, CTR Token Challenge and letters of the pad track."""

    key = "cortex_vortex_track"
    display_name = "Cortex Vortex Track"
    code_blocks = (TROPHY_CODE,)

    def all_locations(self):
        rows = [(TROPHY_NAME, TROPHY_CODE, CORTEX_VORTEX)]
        rows += [(relic_name(tier), code, CORTEX_VORTEX)
                 for tier, code in zip(RELIC_TIER_LABELS, RELIC_CODES)]
        rows.append((CTR_TOKEN_NAME, CTR_TOKEN_CODE, CORTEX_VORTEX))
        rows += [(letter_location_name(letter), code, CORTEX_VORTEX)
                 for letter, code in zip(LETTERS, LETTER_CODES)]
        return rows

    def location_name(self, kind: str, letter: str = "") -> str:
        if kind == "trophy":
            return TROPHY_NAME
        if kind == "ctr_token":
            return CTR_TOKEN_NAME
        if kind == "letter":
            return letter_location_name(letter)
        return relic_name(kind)

    def created_location_names(self, options):
        """Trophy Race, CTR Token Challenge and the selected letter checks.

        The three Time Trials are NOT listed: they belong to the relic-tier
        draw like every other Time Trial (`relic_tiers.draw_relic_tier_keep`,
        read by Regions), so listing them here would count them twice in the
        rung sizer's supply. The podium rungs belong to the podium class.
        """
        if not track_on(options):
            return []
        names = [TROPHY_NAME, CTR_TOKEN_NAME]
        mode = int(getattr(getattr(options, "lettersanity", None), "value", 0) or 0)
        if mode in (1, 2):
            chosen = selected_letters(options)
            names += [letter_location_name(letter) for letter in LETTERS
                      if letter in chosen]
        return names

    def created_letter_names(self, options) -> List[str]:
        return [name for name in self.created_location_names(options)
                if ": Letter " in name]


CORTEX_VORTEX_TRACK_CLASS = CortexVortexTrackLocationClass()


# ---------------------------------------------------------------------------
# The dropped-destination draw
# ---------------------------------------------------------------------------

def _statically_eligible(world) -> List[int]:
    """Destinations whose removal never conflicts with a vanilla pin or a
    content choice, in LevelID order (the draw order is load-bearing).

      * a Gem Cup only when its Gem is not pinned onto it: `shuffle_gems` on
        (off pins every Gem onto its cup, create_items / gemgoal) AND
        `include_gem_cups` on (off pins them back on, issue #50);
      * never a cup a custom track already displaced (that destination is the
        custom track's);
      * a crystal arena only with `include_battle_arenas` on (off pins the
        vanilla Purple Tokens onto the four Crystal Bonus Rounds, issue #50);
      * never Turbo Track while the comfort guard is active (vanilla unlock and
        Gems not shuffled): the pad keeps its vanilla five-Gem gate, and the
        guard's promise is that no check sits behind it.
    """
    from .custom_tracks import REPLACEABLE_DESTINATIONS, resolve_custom_tracks
    from .relic_tiers import resolve_comfort_guards
    o = world.options
    displaced = {REPLACEABLE_DESTINATIONS[entry["replaces"]][1]
                 for entry in resolve_custom_tracks(world).values()}
    _, force_vanilla_turbotrack = resolve_comfort_guards(o)
    out = []
    for lid, (pad, _region, kind) in sorted(destination_table().items()):
        if kind == "cup":
            if not bool(o.shuffle_gems.value) or not bool(o.include_gem_cups.value):
                continue
            if lid in displaced:
                continue
        if kind == "crystal" and not bool(o.include_battle_arenas.value):
            continue
        if pad == "Turbo Track Warp Pad" and force_vanilla_turbotrack:
            continue
        out.append(lid)
    return out


def _predicted_relic_created(world) -> Dict[str, int]:
    """Created count per relic tier, the same arithmetic as
    `draw_relic_tier_keep` without drawing: the option count, clamped by the
    comfort guard to the scoped pool. The pool never shrinks below the
    option-off pool (a dropped track's three Time Trials are replaced by
    Cortex Vortex's), so this is also the count the real draw produces."""
    from .relic_tiers import RELIC_TIERS, resolve_comfort_guards, tier_location_pool
    _, force_vanilla_tt = resolve_comfort_guards(world.options)
    out = {}
    for tier_label, relic_item, option_name in RELIC_TIERS:
        pool = tier_location_pool(world.location_name_to_id, tier_label,
                                  world.options)
        if force_vanilla_tt:
            pool = [n for n in pool if n != f"Turbo Track: {tier_label} Time Trial"]
        out[relic_item] = min(getattr(world.options, option_name).value, len(pool))
    return out


def _supply_feasible(world, lid) -> bool:
    """Would the rung sizer accept this seed with `lid` dropped?

    Dropping a destination changes the location supply (a track's authored item
    boxes go with it; Cortex Vortex adds its own checks and, in `items_only`,
    three letter items). The sizer is the gate that refuses an overfull seed, so
    this asks it directly, with the per-seed inputs it needs predicted without
    RNG: relic counts from `_predicted_relic_created`, letter selections as
    counts, and a placeholder starting racer (only the unlock COUNT matters).
    Every temporary attribute is removed again; nothing here draws."""
    from . import rung_sizer
    from .characters import ROSTER
    o = world.options
    saved_selected = getattr(o, "_lettersanity_selected", None)
    had_selected = hasattr(o, "_lettersanity_selected")
    had_created = hasattr(world, "_ctr_relic_created")
    had_start = hasattr(world, "ctr_starting_character")
    had_dropped = hasattr(o, "_cortex_vortex_dropped")
    saved_dropped = getattr(o, "_cortex_vortex_dropped", None)
    o._cortex_vortex_dropped = lid
    try:
        if not had_selected:
            from . import lettersanity
            count = int(o.letters_per_track.value)
            mode = int(o.lettersanity.value)
            pick = LETTERS[:count] if mode in (1, 2) else LETTERS
            o._lettersanity_selected = {
                track: pick for track in lettersanity.eligible_letter_tracks(o)}
            o._lettersanity_selected[CORTEX_VORTEX] = pick
        if not had_created:
            world._ctr_relic_created = _predicted_relic_created(world)
        if not had_start:
            world.ctr_starting_character = ROSTER[0]
        target = rung_sizer.required_categories(world)
        if target is None:
            return False
        if rung_sizer.category_count(o) >= target:
            return True
        return False
    finally:
        if not had_selected:
            del o._lettersanity_selected
        elif saved_selected is not None:
            o._lettersanity_selected = saved_selected
        if not had_created:
            del world._ctr_relic_created
        if not had_start:
            del world.ctr_starting_character
        if had_dropped:
            o._cortex_vortex_dropped = saved_dropped
        else:
            del o._cortex_vortex_dropped


def eligible_dropped_destinations(world) -> List[int]:
    """The destinations this seed may drop, in LevelID order.

    Static pins first (`_statically_eligible`), then the location supply: a
    destination is kept only when the rung sizer would accept the seed without
    it. If no candidate passes the supply check the static list is returned
    unchanged, so an option set that is too full for every destination fails in
    the sizer with its usual message instead of here."""
    static = _statically_eligible(world)
    feasible = [lid for lid in static if _supply_feasible(world, lid)]
    return feasible or static


def draw_dropped_destination(world) -> Optional[int]:
    """Draw this seed's dropped destination (one `world.random.choice`).

    No draw at all with the option off. The two-stage fill probe runs this on a
    parallel world that shares the real world's options: it still draws, so its
    RNG stream stays aligned with the real one, and keeps the value already on
    the options object (the same seed draws the same value anyway)."""
    o = world.options
    if not track_on(o):
        return None
    eligible = eligible_dropped_destinations(world)
    if not eligible:
        from Options import OptionError
        raise OptionError(
            "CTR 'cortex_vortex_track' needs one destination it can leave "
            "without a pad, but every destination is pinned by this option set.")
    lid = world.random.choice(eligible)
    existing = getattr(o, "_cortex_vortex_dropped", None)
    if existing is None:
        o._cortex_vortex_dropped = lid
    elif existing not in eligible:
        raise ValueError(
            f"CTR: the preset dropped destination {existing} is not eligible "
            f"for this option set ({eligible})")
    return o._cortex_vortex_dropped


def draw_letters(world) -> Tuple[str, ...]:
    """Cortex Vortex's letter selection, the retail rule: a random
    `letters_per_track` subset in the two location modes, all three
    otherwise. Called after the retail selection so an option-off seed draws
    exactly what it drew before."""
    o = world.options
    mode = int(o.lettersanity.value)
    if mode in (1, 2):
        return tuple(world.random.sample(LETTERS, int(o.letters_per_track.value)))
    return LETTERS


# ---------------------------------------------------------------------------
# slot_data
# ---------------------------------------------------------------------------

def wire_block(world) -> Dict[str, object]:
    """The conditional `cortex_vortex_track` slot_data block (option on only).

    Every code is either its exact frozen value or -1 when this seed did not
    create that location. `letter_items` always names the three item codes; the
    CTR Token Challenge requires them only in lettersanity modes 2 and 3, which
    `ctr_options.lettersanity` already says."""
    from .podium import PODIUM_CLASS, SLOT_ORDER
    from .wumpa_checks import WUMPA_CORTEX_VORTEX_CODE, WUMPA_CORTEX_VORTEX_LOCATION
    o = world.options
    created = set(world.multiworld.regions.location_cache[world.player])

    def code(name, value):
        return value if name in created else -1

    podium = {key: code(PODIUM_CLASS.location_name(CORTEX_VORTEX, key),
                        PODIUM_CLASS.code_for(CORTEX_VORTEX, key))
              for key in SLOT_ORDER}
    return {
        "version": WIRE_VERSION,
        "destination_id": DESTINATION_ID,
        "host_level_id": HOST_LEVEL_ID,
        "lev_sha256": LEV_SHA256,
        "vrm_sha256": VRM_SHA256,
        "dropped_destination": int(dropped_level_id(o)),
        "locations": {
            "trophy": code(TROPHY_NAME, TROPHY_CODE),
            "relic": [code(relic_name(tier), c)
                      for tier, c in zip(RELIC_TIER_LABELS, RELIC_CODES)],
            "ctr_token": code(CTR_TOKEN_NAME, CTR_TOKEN_CODE),
            "podium": podium,
            "letters": [code(letter_location_name(letter), c)
                        for letter, c in zip(LETTERS, LETTER_CODES)],
            "wumpa": code(WUMPA_CORTEX_VORTEX_LOCATION, WUMPA_CORTEX_VORTEX_CODE),
        },
        "letter_items": list(LETTER_ITEM_CODES),
    }


def restore_from_wire(options, passthrough) -> None:
    """Universal Tracker: pin the option, the dropped destination and the
    letter selection from the connected room instead of re-drawing.

    The scalar decides the option (absent on any older room, which restores
    to off). With it on, the block must carry the frozen identity fields and a
    valid dropped destination; anything else raises, the lettersanity-restore
    precedent, because a guessed destination would rebuild a different graph
    from the server's."""
    co = (passthrough or {}).get("ctr_options", {}) or {}
    on = co.get("cortex_vortex_track", 0)
    options.cortex_vortex_track.value = 1 if on == 1 else 0
    if on != 1:
        if hasattr(options, "_cortex_vortex_dropped"):
            del options._cortex_vortex_dropped
        return
    block = passthrough.get("cortex_vortex_track")
    if not isinstance(block, dict):
        raise ValueError("cortex_vortex_track is on but its block is missing")
    for key, value in (("version", WIRE_VERSION),
                       ("destination_id", DESTINATION_ID),
                       ("host_level_id", HOST_LEVEL_ID),
                       ("lev_sha256", LEV_SHA256),
                       ("vrm_sha256", VRM_SHA256)):
        if block.get(key) != value:
            raise ValueError(f"cortex_vortex_track.{key} does not match this apworld")
    dropped = block.get("dropped_destination")
    if type(dropped) is not int or dropped not in destination_table():
        raise ValueError("cortex_vortex_track.dropped_destination is not a destination")
    options._cortex_vortex_dropped = dropped
    letters = (block.get("locations") or {}).get("letters")
    if not (isinstance(letters, (list, tuple)) and len(letters) == 3):
        raise ValueError("cortex_vortex_track.locations.letters must hold three codes")
    chosen = []
    for letter, expected, value in zip(LETTERS, LETTER_CODES, letters):
        if value == expected:
            chosen.append(letter)
        elif value != -1:
            raise ValueError("cortex_vortex_track letter code does not belong to it")
    mode = co.get("lettersanity", 0)
    options._cortex_vortex_letters = tuple(chosen) if mode in (1, 2) else LETTERS
