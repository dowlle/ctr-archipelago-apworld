"""Location name groups (#536), built from the registries.

A group is a predicate over the registered location table: the part before the
first ": " is the TRACK (a retail destination region, Cortex Vortex, an arena or
a named custom-track block), the part after it is the CHECK KIND. Hit Character
names have no ": " and come from their class. Nothing here lists a location.

Groups add no id and no placement; they are part of the checksummed datapackage
payload. AutoWorld merges group names with location names, so
`build_location_name_groups` refuses a group named after a location.

DECISIONS (#536)
  * Track groups are named exactly like the track ("Crash Cove"). They cover
    every check family on the track: retail, Cortex Vortex, trials, arenas, the
    five Gem Cups and the named custom-track blocks, whose names are frozen in
    the datapackage. The generic "Custom Track N" slots get no group: a slot is
    not a track until a seed resolves it.
  * "Finish Podium" holds the finish-line podium rungs: "Finish on Podium" and
    the retired "Finish 1st" / "Finish 2nd or 3rd". "Finish (Any Position)" is
    not a podium finish and stays out; "Held Placements" is every "Held <n>".
  * "CTR Challenge" is the "CTR Token Challenge" check.
  * "Relic Race" is every relic check: the three time trials and Relic Race
    Perfect. "Relic Race Sapphire", "Relic Race Gold" and "Relic Race Platinum"
    split the time trials by tier ("Sapphire Relic" is an item name).
  * "Battle Arenas" is every check on the four retail and three authored
    arenas. "Gem Cups" is every check on the five Gem Cups. "Boss Races" is the
    four garage Boss Races and the N. Oxide Garage challenges.
"""
import re
from typing import Dict, Iterable, Mapping, Set

from . import destinations
from .arena_content import ARENAS
from .custom_check_namespace import RELIC_TIERS
from .hit_character import HIT_CHARACTER_CLASS
from .location_class import LocationClassRegistry
from .named_tracks import NAMED_TRACK_CLASS
from .podium import NEW_RUNGS, SHIPPED_RUNGS

SEPARATOR = ": "

_SHIPPED = dict(SHIPPED_RUNGS)
_NEW = dict(NEW_RUNGS)
HELD_SUFFIXES = frozenset(s for k, s in NEW_RUNGS if k.startswith("held_"))
FINISH_PODIUM_SUFFIXES = frozenset(
    {_SHIPPED["first"], _SHIPPED["podium"], _NEW["finish_podium"]})
TROPHY_RACE_SUFFIX = "Trophy Race"
CTR_CHALLENGE_SUFFIX = "CTR Token Challenge"
RELIC_PERFECT_SUFFIX = "Relic Race Perfect"
TIME_TRIAL_SUFFIX = {tier: f"{tier} Time Trial" for tier in RELIC_TIERS}
ITEM_BOX_SUFFIX = re.compile(r"Item Box \d+")


def track_names() -> Set[str]:
    """Every track that gets a group of its own."""
    return ({d.region_name for d in destinations.DESTINATIONS}
            | {destinations.CORTEX_VORTEX}
            | {t.ap_name for t in NAMED_TRACK_CLASS.tracks})


def build_location_name_groups(location_names: Iterable[str],
                               registry: LocationClassRegistry,
                               item_names: Iterable[str] = ()
                               ) -> Dict[str, Set[str]]:
    names = list(location_names)
    tracks = track_names()
    gem_cups = {d.region_name for d in destinations.of_kind(destinations.KIND_CUP)}
    arenas = set(ARENAS.values())
    boss_garages = set(destinations.boss_garage_tracks())

    groups: Dict[str, Set[str]] = {t: set() for t in sorted(tracks)}
    for g in ("Held Placements", "Finish Podium", "Trophy Race", "CTR Challenge",
              "Relic Race", "Battle Arenas", "Gem Cups", "Boss Races",
              "Hit Characters", "Item Boxes",
              *(f"Relic Race {tier}" for tier in RELIC_TIERS)):
        groups[g] = set()
    groups["Hit Characters"] = set(HIT_CHARACTER_CLASS.names())

    tier_of_suffix = {s: t for t, s in TIME_TRIAL_SUFFIX.items()}
    for name in names:
        track, sep, suffix = name.partition(SEPARATOR)
        if not sep:
            continue
        if track in tracks:
            groups[track].add(name)
        if track in arenas:
            groups["Battle Arenas"].add(name)
        if track in gem_cups:
            groups["Gem Cups"].add(name)
        if track in boss_garages:
            groups["Boss Races"].add(name)
        if suffix in HELD_SUFFIXES:
            groups["Held Placements"].add(name)
        elif suffix in FINISH_PODIUM_SUFFIXES:
            groups["Finish Podium"].add(name)
        elif suffix == TROPHY_RACE_SUFFIX:
            groups["Trophy Race"].add(name)
        elif suffix == CTR_CHALLENGE_SUFFIX:
            groups["CTR Challenge"].add(name)
        elif suffix == RELIC_PERFECT_SUFFIX:
            groups["Relic Race"].add(name)
        elif suffix in tier_of_suffix:
            groups["Relic Race"].add(name)
            groups[f"Relic Race {tier_of_suffix[suffix]}"].add(name)
        elif ITEM_BOX_SUFFIX.fullmatch(suffix):
            groups["Item Boxes"].add(name)

    declared = registry.location_name_groups()
    clash = set(declared) & set(groups)
    if clash:
        raise ValueError(f"location groups declared twice: {sorted(clash)}")
    groups.update(declared)

    taken = set(names) | set(item_names)
    for group, members in groups.items():
        if not members:
            raise ValueError(f"location group {group!r} is empty")
        if group in taken:
            raise ValueError(
                f"location group {group!r} collides with an item or location name")
    return groups
