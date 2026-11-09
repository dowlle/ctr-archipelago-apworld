"""Refuse a 0.2.x CTR YAML with one readable message.

Archipelago drops an option name the world no longer has with only a log
warning, so the world never sees it. The one place that does see the whole
game section is Generate.handle_option, which calls an option's from_any with
`game_weights` in its frame. RetailTracks, the first option rolled, calls
check_caller() so a 0.2.x YAML is refused once, before any other option can
throw its own error, and the message names every offending option.
"""
import sys
from typing import Any, Dict, List

# Option names that existed in 0.2.x and are gone in 0.3.0, with what replaces
# them (the table in the 0.3.0 YAML upgrade guide).
REMOVED_OPTIONS: Dict[str, str] = {
    "requirement_variety": "set the weights in requirement_weights",
    "warp_pad_shuffle_categories": "use pad_placement",
    "warp_pad_shuffle_grouping": "use pad_placement",
    "bossgarage_unlock_requirements": "removed",
    "include_gem_cups": "use cup_count",
    "randomize_gem_cup_tracks": "use cup_tracks",
    "include_battle_arenas": "use crystal_challenge_count",
    "slide_coliseum_races": "use track_modes",
    "turbo_track_races": "use track_modes",
    "podium_placement_checks": "use podium_rungs",
    "podium_finish_rungs": "use podium_rungs",
    "podium_any_position_rung": "use podium_rungs",
    "podium_held_rungs": "use podium_rungs",
    "podium_held_fifth_rung": "use podium_rungs",
    "sapphire_relic_count": "set relic counts in item_pool",
    "gold_relic_count": "set relic counts in item_pool",
    "platinum_relic_count": "set relic counts in item_pool",
}

# Options that still exist but whose 0.2.x value is refused: option -> (the
# lower-case values that mark the old form, what to do instead).
REMOVED_VALUES: Dict[str, Any] = {
    "death_link": (("any_hit",), "use weapon_hit or mask_reset"),
    "cortex_vortex_track": (("true",), "use off, in_pool or own_pad"),
}

CUSTOM_TRACKS_MAPPING = ("custom_tracks (the Purple Gem Cup mapping; "
                         "use a list of track packages)")

GUIDE = "see the 0.3.0 release notes for the YAML upgrade guide"


def _selected_values(raw: Any) -> List[str]:
    """Lower-case values a raw YAML setting can pick: a plain value, or the
    keys of a weight table that have a weight above 0."""
    if isinstance(raw, dict):
        picked = []
        for key, weight in raw.items():
            try:
                if float(weight) <= 0:
                    continue
            except (TypeError, ValueError):
                pass
            picked.append(str(key).lower())
        return picked
    return [str(raw).lower()]


def find_legacy_options(game_weights: Any) -> List[str]:
    """Each 0.2.x leftover in a game section, as 'name (what to do)'."""
    if not isinstance(game_weights, dict):
        return []
    found = [f"{name} ({advice})" for name, advice in REMOVED_OPTIONS.items()
             if name in game_weights]
    tracks = game_weights.get("custom_tracks")
    if isinstance(tracks, dict) and tracks:
        found.append(CUSTOM_TRACKS_MAPPING)
    for name, (values, advice) in REMOVED_VALUES.items():
        if name in game_weights:
            bad = [v for v in _selected_values(game_weights[name]) if v in values]
            if bad:
                found.append(f"{name}: {bad[0]} ({advice})")
    return found


def refusal_message(found: List[str]) -> str:
    return ("CTR: this YAML is from 0.2.x and does not work in 0.3.0. "
            "Old options in it: " + "; ".join(found) + ". "
            "Make a new YAML (the YAML Builder has 0.3.0) or edit this one: "
            + GUIDE + ". Rooms made on 0.2.x need the v0.2.4 client.")


def check_game_weights(game_weights: Any) -> None:
    from Options import OptionError
    found = find_legacy_options(game_weights)
    if found:
        raise OptionError(refusal_message(found))


def check_caller() -> None:
    """Called from an option's from_any. Does nothing unless the caller is
    Generate.handle_option with the game section in `game_weights`."""
    try:
        frame = sys._getframe(2)
    except ValueError:
        return
    if frame.f_code.co_name != "handle_option":
        return
    game_weights = frame.f_locals.get("game_weights")
    if isinstance(game_weights, dict):
        check_game_weights(game_weights)


def box_count_caller():
    """Read Generate's per-roll options, never mutate its shared weights.

    The deprecated switch precedes the count in the options dataclass. Its
    already-rolled value preserves weighted/random legacy choices exactly.
    """
    try:
        frame = sys._getframe(2)
    except ValueError:
        return False, None
    try:
        if frame.f_code.co_name != "handle_option":
            return False, None
        weights = frame.f_locals.get("game_weights", {})
        if "item_box_count" in weights:
            return True, None
        legacy = getattr(frame.f_locals.get("ret"), "box_locations", None)
        value = legacy.value if legacy is not None else -1
        return False, value if value in (0, 1) else None
    finally:
        del frame


def migrate_box_count(section):
    """Preview the old box switch on a caller-owned copy, keeping its weights.

    An explicit count wins when both names are present. Keep no visible second
    switch. Generate reads the already-rolled legacy option instead, because
    its input weights are shared between slots. Play Solo uses this preview.
    """
    if "box_locations" not in section:
        return section
    from Options import Toggle
    old = section.pop("box_locations")
    if "item_box_count" not in section:
        def count(value):
            return 15 if Toggle.from_any(value).value else 0
        if isinstance(old, dict):
            weights = {}
            for key, weight in old.items():
                if str(key).lower() == "random":
                    for value in (0, 15):
                        weights[value] = weights.get(value, 0) + weight / 2
                else:
                    value = count(key)
                    weights[value] = weights.get(value, 0) + weight
            section["item_box_count"] = weights
        elif str(old).lower() == "random":
            section["item_box_count"] = {0: 1, 15: 1}
        else:
            section["item_box_count"] = count(old)
    return section
