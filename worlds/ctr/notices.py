"""Once-per-slot generation notices.

A CTR slot's option notices can be reached more than once in one generation:
the two-stage fill probe (`__init__._probe_two_stage_fillable`) builds a mirror
of the room whose slots share the REAL option objects and runs every
generation step on them again. The option object is therefore the carrier for
"already said": the mirror shares it with the slot it predicts, so a notice the
real pass printed is never printed again for that slot, whichever pass reaches
it first.
"""
import logging


def _state(world) -> dict:
    options = world.options
    state = getattr(options, "_ctr_notices", None)
    if state is None:
        state = {"said": set()}
        options._ctr_notices = state
    return state


def slot_label(world) -> str:
    try:
        return world.multiworld.player_name[world.player]
    except Exception:
        return f"player {getattr(world, 'player', '?')}"


def say_once(world, key: str, message: str, logger: logging.Logger,
             level: int = logging.WARNING) -> bool:
    """Log `message` unless this slot already logged `key`. Returns whether it
    was logged."""
    said = _state(world)["said"]
    if key in said:
        return False
    said.add(key)
    logger.log(level, message)
    return True
