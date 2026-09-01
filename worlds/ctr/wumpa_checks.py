"""The wumpa family's own check -- reaching 10 wumpa in a race (R-H dossier 3.4).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. Crossing 10 wumpa in a
race. `RB_Player_ModifyWumpa` already has an exact, named transition for it --
`if (numWumpaOriginal < 10 && driver->numWumpas == 10)` -- which today plays the
"juiced up" jingle and starts `BattleHUD.juicedUpCooldown`. A check-emit call
slots into that existing branch with no new engine state and no new hook. It is
the cleanest signal in the whole R-H dossier.

WHO OWNS THE SEMANTICS. The apworld owns the names, the codes, the option, the
per-seed subset and the resolved wire mapping; native owns the emit call and the
runtime destination identity. Neither half is built here.

GLOBAL OR PER-TRACK (ruled 2026-08-10 16:28, WIDENED 2026-08-29). The original
ruling made this one global location per seed. The 2026-08-29 specification
keeps that mode and adds a second one: `wumpa_check` is now a three-way choice,
`off` / `global` / `per_track`. `per_track` creates one check per selected RACE
DESTINATION where the seed actually provides a race that can award it, plus one
destination-slot check for an eligible bound custom track, and does NOT also
create the global one. The two modes are alternatives, not layers.

TRIAL TRACKS NEED A RACE SURFACE. Slide Coliseum and Turbo Track are registered
retail identities, but their ordinary Adventure pads are relic-only. A relic
race has no supported route to this check, so those two names stay uncreated
until the same seed activates their optional Trophy/arcade-style race locations
through `TRIAL_TROPHY_CLASS`. This deliberately follows location membership
rather than a second option guess: once #203 activates either race, its Wumpa
check and wire code become live in the same seed automatically.

RELATIONSHIP TO ITEMSANITY. Both this check and itemsanity's juiced checks read
the same `numWumpas >= 10` signal, but they are different events -- this one
fires on REACHING 10, itemsanity's fire on FIRING a weapon while at 10 -- so they
coexist without double-counting. Informational #178 row, not a conflict.

DATAPACKAGE STABILITY. This class claims three additive blocks in the 35016xxx
family and registers every name UNCONDITIONALLY:

  * 35016100          the global check, permanently `Wumpa: Reach 10 Wumpa`.
                      Never renamed, moved or reinterpreted.
  * 35016101..118     the 18 retail race destinations, one code per destination
                      in the canonical retail track order -- the Sapphire Time
                      Trial code order that `item_boxes.BOX_TRACKS` already reads
                      out of `data/locations.json`, which is also the order the
                      item-box track mapping uses. Contiguous behind the global
                      code so the family reads as one block.
  * 35016120+         the custom DESTINATION SLOTS, one per supported custom
                      destination role. Alpha6 supports exactly one role,
                      `purple_gem_cup`, at 35016120. Future roles take 35016121
                      and up; a new PACKAGE in an already-supported role needs no
                      code at all, which is the point of keying the identity to
                      the destination slot rather than to a package id or title.

The gap between 118 and 120 is deliberate slack, and 35016200 (trial_trophy)
bounds the family from above.

APPROVED UNFREEZE (2026-08-29). The 18 retail names and the custom-slot name were
minted through the considered-datapackage-unfreeze process and approved on
2026-08-29. They are permanent from that point exactly as the 0.2.0
freeze names are: the manifest, the stability fixture and the name-freeze census
all carry them, and none of these ids can ever move.

CUSTOM DESTINATION ELIGIBILITY. A custom track earns its destination-slot check
only when all four of the specification's conditions hold: the track is present
in the submitted `custom_tracks` descriptor, generation accepted its destination
binding, its MEASURED descriptor declares `wumpa_collectible` true, and the
destination role provides a race mode in which reaching 10 wumpa is possible.
`wumpa_collectible` is its own required measured capability -- deliberately NOT
inferred from the broad `crates` flag, because a track can carry crate instances
without offering a real path to ten fruit.
"""
from typing import Dict, List, Tuple

from .custom_tracks import (REPLACEABLE_DESTINATIONS, WUMPA_COLLECTIBLE_FLAG,
                            normalize_custom_tracks)
from .item_boxes import BOX_TRACKS, TRACK_LEVEL_IDS
from .location_class import LocationClass
from .trial_trophy import TRIAL_TRACKS, TRIAL_TROPHY_CLASS

# ── option modes ────────────────────────────────────────────────────────────
#: `wumpa_check` Choice values. The order preserves the retired Boolean
#: naturally: false == 0 == off, true == 1 == global.
WUMPA_OFF, WUMPA_GLOBAL, WUMPA_PER_TRACK = 0, 1, 2

# ── code blocks ─────────────────────────────────────────────────────────────
#: The original single-code block. Permanent, never moves.
WUMPA_CODE_BASE = 35016100

#: The 18 retail race destinations, contiguous behind the global code, in
#: `BOX_TRACKS` order.
WUMPA_RETAIL_CODE_BASE = 35016101

#: The custom destination slots. One per supported destination role.
WUMPA_CUSTOM_CODE_BASE = 35016120

#: The one global location name. Spelled out rather than clever: a player reading
#: it in a tracker with itemsanity switched off has no "(Juiced)" vocabulary to
#: lean on, so the name says what to do.
WUMPA_TEN_LOCATION = "Wumpa: Reach 10 Wumpa"

#: The 18 retail race destinations, in canonical order. Read from `item_boxes`
#: rather than re-derived so this block's order can never drift from the
#: Sapphire-relic / item-box canon it was minted against.
WUMPA_RETAIL_TRACKS: Tuple[str, ...] = tuple(BOX_TRACKS)

#: The ordinary trophy tracks always have a race surface. The two trial-track
#: identities are frozen in ``WUMPA_RETAIL_TRACKS`` too, but are created only
#: when their optional Trophy/arcade-style race is active in this seed.
WUMPA_ALWAYS_RACEABLE_TRACKS: Tuple[str, ...] = tuple(
    track for track in WUMPA_RETAIL_TRACKS if track not in TRIAL_TRACKS
)

#: Supported custom destination roles, in code order:
#: `(replaces word, datapackage label, AP region)`.
#:
#: The datapackage label is the DESTINATION's name, not the package's. Slot data
#: and the client may present the selected package's title (Baby T Park), but the
#: registered location name and its code stay put when a different package later
#: occupies the same role -- which is what lets a creator ship a package without
#: waiting for an apworld release.
CUSTOM_DESTINATION_ROLES: Tuple[Tuple[str, str, str], ...] = (
    ("purple_gem_cup", "Purple Gem Cup Custom Race", "Purple Gem Cup"),
)

#: Roles whose race mode can actually reach ten fruit. The Purple Gem Cup's
#: custom binding runs a full multi-lap race, so it can. A future role that is,
#: say, a single-lap time trial would be listed false here and would create no
#: check however the package's own capability reads.
ROLE_OFFERS_TEN_WUMPA: Dict[str, bool] = {
    "purple_gem_cup": True,
}


def retail_location_name(track: str) -> str:
    return f"{track}: Reach 10 Wumpa"


def custom_location_name(label: str) -> str:
    return f"{label}: Reach 10 Wumpa"


def eligible_retail_tracks(options) -> Tuple[str, ...]:
    """Retail destinations with a supported Wumpa-awarding race this seed.

    The 16 ordinary trophy tracks always qualify. Slide Coliseum and Turbo
    Track qualify independently only when the seed creates their optional
    Trophy Race location. That location is the apworld-owned proof that native
    exposes the AI/arcade-style race instead of the retail relic-only launch.
    """
    trial_trophies = set(TRIAL_TROPHY_CLASS.created_location_names(options))
    return tuple(
        track for track in WUMPA_RETAIL_TRACKS
        if (track in WUMPA_ALWAYS_RACEABLE_TRACKS
            or TRIAL_TROPHY_CLASS.location_name(track) in trial_trophies)
    )


def _mode(options) -> int:
    """This seed's `wumpa_check` mode, read defensively.

    `LocationClass` instances are also driven by the location-class
    infrastructure tests with stand-in option objects carrying only the options
    under test, so an absent toggle must answer "off" rather than raise. A plain
    Boolean-valued stand-in still reads correctly: `int(False)` is off and
    `int(True)` is global, which is the retired option's meaning.
    """
    toggle = getattr(options, "wumpa_check", None)
    if toggle is None:
        return WUMPA_OFF
    try:
        value = int(toggle.value)
    except (AttributeError, TypeError, ValueError):
        return WUMPA_OFF
    if value not in (WUMPA_OFF, WUMPA_GLOBAL, WUMPA_PER_TRACK):
        return WUMPA_OFF
    return value


def _descriptor(options) -> Dict[str, Dict[str, object]]:
    """This seed's normalized `custom_tracks` descriptor, or `{}`.

    Normalized through the option validator rather than read raw, so the
    eligibility question below and the rest of generation are looking at exactly
    the same descriptor. A stand-in options object without the key answers `{}`.
    """
    raw = getattr(getattr(options, "custom_tracks", None), "value", None)
    if not raw:
        return {}
    return normalize_custom_tracks(raw)


def eligible_custom_roles(options) -> List[Tuple[str, str, str, Dict[str, object]]]:
    """The custom destination roles that earn a Wumpa check this seed.

    Returns `(role, label, region, entry)` per eligible role, in
    `CUSTOM_DESTINATION_ROLES` order. Every one of the specification's four
    conditions is checked here, in one place, so creation, logic, the wire and
    the tests can never disagree about which roles are live.
    """
    tracks = _descriptor(options)
    if not tracks:
        return []
    # `replaces` -> the entry that claimed it. Validation already guarantees at
    # most one entry and a known destination, but resolving through the map
    # rather than assuming keeps this honest if that ever widens.
    by_role: Dict[str, Dict[str, object]] = {}
    for entry in tracks.values():
        role = entry.get("replaces")
        if role in REPLACEABLE_DESTINATIONS:
            by_role[role] = entry

    out = []
    for role, label, region in CUSTOM_DESTINATION_ROLES:
        entry = by_role.get(role)
        if entry is None:
            continue  # not present in the descriptor, or bound elsewhere
        if not ROLE_OFFERS_TEN_WUMPA.get(role, False):
            continue  # the role's race mode cannot reach ten fruit
        flags = entry.get("flags") or {}
        if not bool(flags.get(WUMPA_COLLECTIBLE_FLAG, False)):
            continue  # the package measured NO wumpa route
        out.append((role, label, region, entry))
    return out


class WumpaLocationClass(LocationClass):
    """The 10-wumpa checks as a `LocationClass` (#176)."""

    key = "wumpa"
    display_name = "Wumpa Checks"
    code_blocks = (WUMPA_CODE_BASE, WUMPA_RETAIL_CODE_BASE,
                   WUMPA_CUSTOM_CODE_BASE)

    #: The global check hangs off the world's root region: wumpa are collected
    #: wherever you race, so it belongs to no track.
    REGION = "Menu"

    def all_locations(self):
        entries = [(WUMPA_TEN_LOCATION, WUMPA_CODE_BASE, self.REGION)]
        # A retail destination's check belongs to that destination's TRACK
        # region, which is what hands it the track's own pad-access rule for
        # free -- the same region-membership mechanism the item-box checks use,
        # and therefore the same individual-pad rule a Gem Cup leg must obey.
        entries += [(retail_location_name(track),
                     WUMPA_RETAIL_CODE_BASE + index,
                     track)
                    for index, track in enumerate(WUMPA_RETAIL_TRACKS)]
        # A custom destination's check belongs to the DESTINATION's region and
        # inherits that destination's actual access rule.
        entries += [(custom_location_name(label),
                     WUMPA_CUSTOM_CODE_BASE + index,
                     region)
                    for index, (_role, label, region)
                    in enumerate(CUSTOM_DESTINATION_ROLES)]
        return entries

    def location_name(self) -> str:
        """The global check's name. Kept for callers that predate the widening;
        the per-destination names come from `retail_location_name` /
        `custom_location_name`, which take a key."""
        return WUMPA_TEN_LOCATION

    def created_location_names(self, options):
        """Off: nothing. Global: the one global check. Per-track: each retail
        destination with a supported race this seed plus one per eligible custom
        destination role, and NOT the global one -- the modes are alternatives,
        not layers."""
        mode = _mode(options)
        if mode == WUMPA_GLOBAL:
            return [WUMPA_TEN_LOCATION]
        if mode != WUMPA_PER_TRACK:
            return []
        names = [retail_location_name(track)
                 for track in eligible_retail_tracks(options)]
        names += [custom_location_name(label)
                  for _role, label, _region, _entry
                  in eligible_custom_roles(options)]
        return names

    # ------------------------------------------------------------------- wire

    def retail_code(self, track: str) -> int:
        return WUMPA_RETAIL_CODE_BASE + WUMPA_RETAIL_TRACKS.index(track)

    def custom_code(self, role: str) -> int:
        for index, (candidate, _label, _region) in enumerate(
                CUSTOM_DESTINATION_ROLES):
            if candidate == role:
                return WUMPA_CUSTOM_CODE_BASE + index
        raise KeyError(f"no custom Wumpa destination slot for role {role!r}")

    def wire_block(self, options) -> Dict[str, object]:
        """The self-describing `wumpa_checks` slot_data block (call only when the
        mode is not off).

        Native parses this rather than hardcoding the new range: the wire is the
        authority on which codes exist in this seed. `global` is -1 when the
        global check is not live, matching the -1 = absent sentinel the podium
        and item-box blocks already use. `retail_tracks` is keyed by engine
        LevelID as a decimal string, the same currency `warp_pad_map`,
        `gem_cup_legs` and `item_box_checks` use.
        """
        mode = _mode(options)
        block: Dict[str, object] = {
            "mode": mode,
            "global": WUMPA_CODE_BASE if mode == WUMPA_GLOBAL else -1,
            "retail_tracks": {},
            "custom_destinations": {},
        }
        if mode != WUMPA_PER_TRACK:
            return block
        block["retail_tracks"] = {
            str(TRACK_LEVEL_IDS[track]): self.retail_code(track)
            for track in eligible_retail_tracks(options)
        }
        block["custom_destinations"] = {
            role: {
                "code": self.custom_code(role),
                "package_uuid": entry["package_uuid"],
                WUMPA_COLLECTIBLE_FLAG: True,
            }
            for role, _label, _region, entry in eligible_custom_roles(options)
        }
        return block


#: The registered wumpa class. `Locations.py` registers this instance.
WUMPA_CLASS = WumpaLocationClass()
