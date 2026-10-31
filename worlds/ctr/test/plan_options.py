"""Test inputs in the nested shape the plan tests were written in, as flat options.

The plan tests build their seeds from a `content_pool` and a `pad_layout`
mapping, which row 7 split into flat options. `plan_options` turns such a mapping
into the flat options, so a test keeps its short inputs and runs on the option
set a player writes. Options that merged the same way are turned over too.
"""
import copy

from ..arena_content import ARENAS, ARCADE
from ..boss_encounters import FAMILIES, GARAGE_FAMILIES, OPPONENT_NAMES, OXIDE_NAME, POOL_NAMES
from ..boss_track_shuffle import VENUES
from ..content_plan import MODES, RETAIL

ARCADE_NAMES = {ARENAS[level] for level in ARCADE}
PODIUM = ("podium_placement_checks", "podium_held_rungs", "podium_held_fifth_rung", "podium_finish_rungs",
          "podium_any_position_rung")
RELIC_COUNTS = {"sapphire_relic_count": "sapphire", "gold_relic_count": "gold", "platinum_relic_count": "platinum"}


def _count(value):
    """A flat count option holds one number: the top of an old {min, max} range."""
    return value["max"] if isinstance(value, dict) else value


def _track_name(track_id, packages):
    if track_id == "cortex_vortex":
        return "Cortex Vortex"
    if track_id.startswith("retail:"):
        return RETAIL[int(track_id.split(":")[1])]
    if track_id.startswith("arena:"):
        return ARENAS[int(track_id.split(":")[1])]
    return next((p["content_id"] for p in packages if track_id.endswith(f"{p['content_id']}/{p['revision']}")), track_id)


def _content(out, pool):
    tracks = pool.get("tracks", {})
    packages = tracks.get("custom", [])
    if tracks.get("retail", "all") != "all":
        out["retail_tracks"] = [RETAIL[i] for i in tracks["retail"]]
    out["custom_tracks"] = packages
    if tracks.get("cortex_vortex"):
        out["cortex_vortex_track"] = "in_pool"
    modes = {"default": tracks.get("modes", list(MODES))}
    modes.update({_track_name(key, packages): value for key, value in tracks.get("overrides", {}).items()})
    out["track_modes"] = modes
    required = list(pool.get("required_entries", ()))
    if "cortex_vortex" in required:
        required.remove("cortex_vortex")
        out["cortex_vortex_track"] = "own_pad"
    out["required_entries"] = [_track_name(entry, packages) for entry in required]
    cups = pool.get("cups", {})
    composition = cups.get("composition", {})
    out["cup_count"] = _count(cups.get("count", 0))
    if "tracks" in cups:
        out["cup_tracks"] = cups["tracks"]
    elif composition.get("repeats", {}).get("within_cup"):
        out["cup_tracks"] = "random"
    if "custom_legs" in composition:
        out["cup_custom_legs"] = composition["custom_legs"]["max"]
    crystals = pool.get("crystals", {})
    out["crystal_challenge_count"] = _count(crystals.get("count", 0))
    arenas = crystals.get("pool", "all")
    out["crystal_arenas"] = (list(ARENAS.values()) if arenas == "all" else [ARENAS[level] for level in arenas])
    if not out.pop("include_arcade_arenas", False):
        out["crystal_arenas"] = [name for name in out["crystal_arenas"] if name not in ARCADE_NAMES]
    bosses = pool.get("bosses", {})
    out["boss_garages"] = bosses.get("enabled", False)
    if "cups" in bosses:
        out["boss_cups"] = _count(bosses["cups"])
    if "requirement_level" in bosses:
        out["garage_requirement_level"] = bosses["requirement_level"]


def _pool(allow, block, every):
    allow = set(allow) or set(every)
    return sorted(allow - set(block))


def plan_options(options):
    out = copy.deepcopy(dict(options))
    if "content_pool" in out:
        _content(out, out.pop("content_pool"))
    if not out.pop("include_battle_arenas", True):
        out["crystal_challenge_count"] = 0
    layout = out.pop("pad_layout", {})
    if "placement" in layout:
        out["pad_placement"] = layout["placement"]
    if "mode_order" in layout:
        out["race_mode_order"] = layout["mode_order"]
    if layout.get("stages") == "single":
        out["two_stage_density"] = "off"
    if any(key in out for key in PODIUM):
        rungs = []
        if out.get("podium_placement_checks", True):
            if out.get("podium_held_rungs", True):
                rungs += ["held_1st", "held_3rd"] + (["held_5th"] if out.get("podium_held_fifth_rung", False) else [])
            if out.get("podium_finish_rungs", True):
                rungs += ["finish_on_podium"] + (["finish_any"] if out.get("podium_any_position_rung", True) else [])
        out["podium_rungs"] = rungs
        for key in PODIUM:
            out.pop(key, None)
    if "boss_track_allowlist" in out or "boss_track_blocklist" in out:
        out["boss_track_pool"] = _pool(out.pop("boss_track_allowlist", ()), out.pop("boss_track_blocklist", ()), VENUES)
    if {"boss_character_allowlist", "boss_character_blocklist", "boss_oxide_in_pool"} & set(out):
        with_oxide = out.pop("boss_oxide_in_pool", False)
        every = POOL_NAMES if with_oxide else OPPONENT_NAMES
        allow = out.pop("boss_character_allowlist", ())
        names = [name for name in _pool(allow, out.pop("boss_character_blocklist", ()), every) if name != OXIDE_NAME]
        out["boss_character_pool"] = names + ([OXIDE_NAME] if with_oxide else [])
    if "boss_powerup_blocklist" in out:
        out["boss_weapon_pool"] = _pool((), out.pop("boss_powerup_blocklist"), GARAGE_FAMILIES)
    if "oxide_powerup_blocklist" in out:
        out["oxide_weapon_pool"] = _pool((), out.pop("oxide_powerup_blocklist"), FAMILIES)
    for key, tier in RELIC_COUNTS.items():
        if key in out:
            relics = out.setdefault("item_pool", {}).setdefault("base", {}).setdefault("relics", {})
            relics[tier] = out.pop(key)
    out.pop("boss_encounter_repeats", None)
    return out
