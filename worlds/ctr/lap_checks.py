"""Lap completion checks (#344): `<Track>: Complete One Lap`.

WHAT THIS CHECKS. The first accepted lap in any lap-based race mode on that
track, Cup legs included; one check per track across all its appearances
(ruled 2026-10-13 21:37 CEST, #344 answer 1). Finishing position does not
matter. A Crystal Challenge has no laps and earns nothing here.

WHO OWNS THE SEMANTICS. The apworld owns names, codes, the option
`lap_completion_checks` (default off), the per-seed subset and the routes; native
owns the lap crossing send in game/PlayLevel.c (ap/ap_hooks_laps.c).

WHICH TRACKS (normal rooms). A track gets its check when the seed races it on
a route the logic models:

  * its own destination region, reached through the pad that loads it (the 16
    race tracks, Slide Coliseum and Turbo Track, whose Relic Race is a lap race,
    and the Cortex Vortex pad track). A destination the Cortex Vortex pad track
    dropped has no pad, so its own region is no route;
  * every Gem Cup that legs it in the seed's logic leg map (`gem_cup_legs`,
    displaced Cups emptied, a dropped Cup skipped);
  * a legacy `custom_tracks` entry's own region.

Boss races are lap races too and native sends there as well, but they are not
modelled as routes here: a track raced only as a boss venue gets no check, and a
lap earned in a boss race is an early, out-of-logic send. This is the
conservative reading; adding the garages as routes later changes no name or code.
Content plans build their lap checks in content_laps.py.

LOGIC. Each route is a rule-carrying entrance into a dead-end `<track>: Lap`
region, the Podium and Wumpa shape: AP-core ANDs a location with its parent
region, and the region holds only the lap check, so a Cup exposes nothing else
of the track. A lap crosses the whole track once, so a route needs what
finishing that race needs and no more: the track's finish term where one is
ruled (usf_finish), on the own-pad route bound to that pad's racer, and on a Cup
route the finish of every leg up to and including the track's first leg in that
Cup, bound to the Cup pad's racer. No win, rank or difficulty term.

DATAPACKAGE STABILITY. Retail tracks `35028000 + i` in the canonical retail
order (BOX_TRACKS, the Reach 10 Wumpa order), Cortex Vortex at 35026009 (the
unused slot in its named block), generic custom slots `35028100 + N - 1` for
N in 1..132. Named custom tracks use offset 16 of their named block
(named_tracks.py). Every name registers unconditionally. Approved in the 0.3.0
minting register (ruled 2026-10-13 22:02 CEST).

FROZEN-NAME WARNING: once released these names and codes are permanent.
"""
import json
from typing import Dict, List, Tuple

from Options import OptionError

from . import destinations
from .custom_check_namespace import CUSTOM_SLOT_COUNT
from .item_boxes import BOX_TRACKS, TRACK_LEVEL_IDS
from .location_class import LocationClass

LAP_RETAIL_CODE_BASE = 35028000
LAP_CORTEX_VORTEX_CODE = 35026009
LAP_CUSTOM_CODE_BASE = 35028100
WIRE_VERSION = 1
#: The Cortex Vortex logical LevelID on the wire (gem_cup_legs and the cup
#: sweep block use the same alias).
CORTEX_VORTEX_KEY = destinations.CORTEX_VORTEX_LEVEL_ID


def lap_name(track: str) -> str:
    return f"{track}: Complete One Lap"


def region_name(track: str) -> str:
    return f"{track}: Lap"


class LapCompletionLocationClass(LocationClass):
    key = "lap_completion"
    display_name = "Lap Completion Checks"
    code_blocks = (LAP_RETAIL_CODE_BASE, 35026000)

    def all_locations(self):
        out = [(lap_name(track), LAP_RETAIL_CODE_BASE + i, track)
               for i, track in enumerate(BOX_TRACKS)]
        out.append((lap_name(destinations.CORTEX_VORTEX), LAP_CORTEX_VORTEX_CODE,
                    destinations.CORTEX_VORTEX))
        out += [(lap_name(destinations.custom_slot_region(slot)), LAP_CUSTOM_CODE_BASE + slot - 1,
                 destinations.custom_slot_region(slot))
                for slot in range(1, CUSTOM_SLOT_COUNT + 1)]
        return out

    def location_name(self, track: str) -> str:
        return lap_name(track)

    def created_location_names(self, options) -> List[str]:
        """The names create_locations made this seed, without the named-block
        ones (named_tracks registers those). Empty before create_regions."""
        if not getattr(getattr(options, "lap_completion_checks", None), "value", 0):
            return []
        own = set(self.names())
        return [name for name in getattr(options, "_lap_selected", ()) if name in own]


LAP_COMPLETION_CLASS = LapCompletionLocationClass()


def fail(message):
    raise OptionError("CTR lap completion checks: " + message)


def _routes(world, region_lookup) -> List[Tuple[str, int, list]]:
    """[(stem, code, [(source region name, Cup legs prefix or None)])] for every
    track this seed races on a modelled route, in a stable order: the 18 retail
    destinations, Cortex Vortex, then the legacy custom tracks."""
    from .cortex_vortex_track import dropped_region, track_on
    o = world.options
    dropped = dropped_region(o)
    legs = getattr(world, "gem_cup_legs", {}) or {}

    def cup_routes(track):
        out = []
        for cup, cup_legs in legs.items():
            if cup == dropped or cup not in region_lookup or track not in cup_legs:
                continue
            out.append((cup, list(cup_legs[:cup_legs.index(track) + 1])))
        return out

    out = []
    for i, track in enumerate(BOX_TRACKS):
        routes = [] if track == dropped or track not in region_lookup else [(track, None)]
        routes += cup_routes(track)
        if routes:
            out.append((track, LAP_RETAIL_CODE_BASE + i, routes))
    cv = destinations.CORTEX_VORTEX
    if track_on(o) and cv in region_lookup:
        out.append((cv, LAP_CORTEX_VORTEX_CODE, [(cv, None)] + cup_routes(cv)))
    from . import custom_track_ids as ids
    for _track_id, entry in sorted((getattr(world, "custom_tracks", {}) or {}).items()):
        label = ids.track_label(entry)
        if label not in region_lookup:
            continue
        out.append((label, custom_code(entry), [(label, None)]))
    return out


def custom_code(entry) -> int:
    """A legacy custom entry's lap code: its named block's offset 16, else the
    generic `Custom Track N:` code."""
    from . import named_tracks
    if entry.get("named_block") is not None:
        return named_tracks.location_code(entry["named_block"], "lap")
    return LAP_CUSTOM_CODE_BASE + int(entry["slot"]) - 1


def create_locations(world, region_lookup):
    """Create the seed's lap checks and their dead-end regions (option on)."""
    from BaseClasses import Entrance, Region
    from .Locations import create_location
    o = world.options
    o._lap_selected = ()
    world._ctr_lap_routes = []
    if not o.lap_completion_checks.value:
        return
    player, mw = world.player, world.multiworld
    selected = []
    for stem, code, routes in _routes(world, region_lookup):
        name = lap_name(stem)
        region = Region(region_name(stem), player, mw)
        region.type = "lap"
        mw.regions.append(region)
        region_lookup[region.name] = region
        location = create_location(player, name, region)
        if location.address != code:
            fail(f"{name} resolves to {location.address}, expected the frozen {code}")
        location.type = "lap_completion"
        location.logic_text = "True"
        region.locations.append(location)
        mw.regions.location_cache[player][name] = location
        for source_name, prefix in routes:
            source = region_lookup[source_name]
            entrance = Entrance(player=player, name=f"{source.name} -> {region.name}", parent=source)
            entrance.connect(region)
            source.exits.append(entrance)
            mw.regions.entrance_cache[player][entrance.name] = entrance
            world._ctr_lap_routes.append((entrance, stem, source_name, prefix))
        selected.append(name)
    o._lap_selected = tuple(selected)
    if hasattr(o, "_lap_wire"):
        # Archipelago room persistence turns arrays into tuples; compare the
        # JSON form, which keeps exact integer tokens.
        try:
            same = json.dumps(o._lap_wire, sort_keys=True) == json.dumps(wire_block(world), sort_keys=True)
        except (TypeError, ValueError):
            same = False
        if not same:
            fail("the saved lap tracks or codes disagree with the selected content")


def install_rules(world, player):
    """Each route's finish term (module docstring, LOGIC). Installed after the
    JSON entrance rules, which would otherwise reset these entrances."""
    from .logic_terms import TRUE, set_term
    from .usf_finish import ALL_USF_FINISH_TRACKS, cup_finish_t, track_finish_t
    for entrance, stem, source, prefix in getattr(world, "_ctr_lap_routes", ()):
        if prefix is None:
            term = track_finish_t(stem, world) if stem in ALL_USF_FINISH_TRACKS else TRUE
        else:
            term = cup_finish_t(prefix, world, source)
        set_term(entrance, term)


def wire_block(world) -> Dict[str, object]:
    """`lap_checks`: {version, tracks: {"<LevelID>": code}, custom_slots:
    {"<slot>": code}}, only the tracks this seed created. Retail keys are the
    engine LevelID (0..17), Cortex Vortex is 110."""
    selected = set(getattr(world.options, "_lap_selected", ()))
    tracks, custom = {}, {}
    for i, track in enumerate(BOX_TRACKS):
        if lap_name(track) in selected:
            tracks[str(TRACK_LEVEL_IDS[track])] = LAP_RETAIL_CODE_BASE + i
    if lap_name(destinations.CORTEX_VORTEX) in selected:
        tracks[str(CORTEX_VORTEX_KEY)] = LAP_CORTEX_VORTEX_CODE
    from . import custom_track_ids as ids
    for _track_id, entry in sorted((getattr(world, "custom_tracks", {}) or {}).items()):
        if lap_name(ids.track_label(entry)) in selected:
            custom[str(int(entry["slot"]))] = custom_code(entry)
    return dict(version=WIRE_VERSION, tracks=dict(sorted(tracks.items(), key=lambda kv: int(kv[0]))),
                custom_slots=dict(sorted(custom.items(), key=lambda kv: int(kv[0]))))


def restore_options(options, wire):
    """Universal Tracker: the switch from the room, the block kept for the
    comparison in create_locations."""
    flag = wire.get("ctr_options", {}).get("lap_completion_checks", False)
    block = wire.get("lap_checks")
    if type(flag) is not bool or (flag and block is None) or (not flag and "lap_checks" in wire):
        fail("option and block disagree")
    options.lap_completion_checks.value = int(flag)
    if flag:
        options._lap_wire = block


def named_location_names(options) -> List[str]:
    """The named-block lap names create_locations made (named_tracks lists them)."""
    if not getattr(getattr(options, "lap_completion_checks", None), "value", 0):
        return []
    own = set(LAP_COMPLETION_CLASS.names())
    return [name for name in getattr(options, "_lap_selected", ()) if name not in own]
