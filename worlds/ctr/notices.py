"""One generator message per slot.

Most Archipelago games print at most once during generation, so a CTR slot
prints at most one message too: a single summary of every option the generator
adjusted, in plain player language. A YAML that needs no adjustment
prints nothing. Errors that stop generation (`OptionError`) keep their own
message and are not routed through here.

Code that changes an option, or finds one it must ignore, records it here with
`adjusted` or `note_ignored`. It never logs on its own. `emit_summary` prints
the lot once, at the end of `generate_early`.

The option object is the carrier for the record, so a step re-run on the same
option objects (a plan redraw, a second `generate_early`) replaces its own entry
instead of adding a second one, and the summary is printed once.
"""
import logging

logger = logging.getLogger("CTR")


def _state(world) -> dict:
    options = world.options
    state = getattr(options, "_ctr_notices", None)
    if state is None:
        state = {"adjusted": {}, "ignored": [], "emitted": False}
        options._ctr_notices = state
    return state


def slot_label(world) -> str:
    try:
        return world.multiworld.player_name[world.player]
    except Exception:
        return f"player {getattr(world, 'player', '?')}"


def adjusted(world, key: str, text: str) -> None:
    """Record one adjustment for the slot's summary. `text` starts with the
    option's display name and says what was changed and why, e.g.
    `Cup Count: lowered from 27 to 23, ...`. The same `key` again replaces the
    earlier text (a redraw); it never adds a second line."""
    _state(world)["adjusted"][key] = text


def note_ignored(world, label: str) -> None:
    """Record an option this slot's seed ignores, for the debug log only.

    `label` names the option and, in brackets, why it has no effect. An ignored
    option changed nothing, so it is not part of the summary (a randomly rolled
    YAML ignores some on purpose, ruling 2026-10-15)."""
    ignored = _state(world)["ignored"]
    if label not in ignored:
        ignored.append(label)


def summary_lines(world) -> list:
    return list(_state(world)["adjusted"].values())


def emit_summary(world) -> bool:
    """Print the slot's one summary, if there is anything to say. Returns
    whether it was printed. A second call prints nothing."""
    if getattr(world.multiworld, "generation_is_fake", False):
        return False  # Universal Tracker rebuilds a seed that already generated
    state = _state(world)
    if state["emitted"]:
        return False
    if state["ignored"]:
        logger.debug("CTR (%s): ignored options: %s", slot_label(world), ", ".join(state["ignored"]))
    lines = summary_lines(world)
    if not lines:
        return False
    state["emitted"] = True
    noun = "setting" if len(lines) == 1 else "settings"
    logger.warning("CTR (%s): the generator changed %d %s for this slot:\n%s",
                   slot_label(world), len(lines), noun,
                   "\n".join("  - " + line for line in lines))
    return True
