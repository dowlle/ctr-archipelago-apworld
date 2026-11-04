"""Option interactions the content plan still resolves (issue #178 convention).

RAISE when a combination has no reading the player would recognise as their
own seed; WARN once, through notices.say_once, when an old spelling is
translated. One generator row 12 deleted the original generator's entries;
the plan owns its own refusals (content_plan.generate). What stays:

- `resolve_death_link_off_when_send_conditions_set`: no one-way DeathLink
  (ruling 2026-09-30).
- `raise_if_starting_as_removed_oxide`: Remove Playable Oxide with Starting
  Character Nitros Oxide (#426).
- `warn_racer_locked_pads_boolean_normalized`: the Alpha 6 `true` spelling of
  Racer-Locked Warp Pads (ruling 2026-08-29).
- `_warn`, which content_bosses also uses.
"""
import logging

from Options import OptionError

from . import characters

logger = logging.getLogger(__name__)


def _who(world):
    return f"player {world.player} ({world.multiworld.player_name[world.player]})"


def _name(world):
    from .notices import slot_label
    return slot_label(world)


def _warn(world, key: str, message: str) -> None:
    """Log `message` once per slot (`notices.say_once`).

    Anything that runs `generate_early` again on the same option objects
    reaches every warning in this module again. The player generated one seed
    and asked one question; telling them the same thing twice reads like two
    different problems."""
    from .notices import say_once
    say_once(world, key, message, logger)


def resolve_death_link_off_when_send_conditions_set(world):
    """No one-way DeathLink (ruling of 2026-09-30): when the resolved
    `death_link_send` bitmask is non-zero while `death_link` is off, the
    effective `death_link` becomes mask_reset (the mildest receive effect), so
    a player who sends deaths also takes them. Receive-only (DeathLink on,
    send nothing) stays allowed.

    Mutates the option's stored value, so the slot_data emit reads the resolved value and needs no second rule.
    Only an explicit `death_link_send` list can trigger it: the default
    (follow_death_link) resolves to 0 while death_link is off. Re-entry is a
    no-op (the condition is false once death_link is on), so a second
    generate_early pass warns nothing. Universal Tracker re-generation
    does not call this; it restores nothing from either key."""
    o = world.options
    if o.death_link.value == 0 \
            and o.death_link_send.send_mask(o.death_link.value) != 0:
        o.death_link.value = o.death_link.option_mask_reset


def raise_if_starting_as_removed_oxide(world):
    """Remove Playable Oxide (#426) with Starting Character set to Nitros
    Oxide. The option takes Oxide out of the racers you can play, and the other
    option seats you as him: the two ask for opposite things, and there is no
    reading of the seed that honours both. Picking a different starter for the
    player would quietly change a choice they typed by name, so refuse with a
    message that names both options (#178 RAISE convention).

    Only while Character Unlocks is on: with it off the option does nothing,
    so starting as Oxide is an ordinary seed."""
    if not characters.oxide_removed(world):
        return
    if world.options.starting_character.current_key != "nitros_oxide":
        return
    raise OptionError(
        f"CTR: 'remove_playable_oxide' is on for {_who(world)}, but "
        f"'starting_character' is 'nitros_oxide'. Oxide cannot be removed from "
        f"the playable racers and also be the racer you start as. Turn "
        f"remove_playable_oxide off, or pick another starting_character "
        f"(random_starter and random_any never pick Oxide with it on).")


def warn_racer_locked_pads_boolean_normalized(world):
    """`racer_locked_pads` was a toggle up to and including Alpha 6 and is now
    a maximum lock COUNT. A YAML that still says `true` cannot be read as a
    number without changing what it asked for: `bool` is an `int` subclass, so
    it would land on 1 -- a single lock, where Alpha 6 gave a quarter of the
    eligible pads. The 2026-08-29 ruling forbids that silent reinterpretation,
    so `true` keeps its Alpha 6 meaning and says so, exactly once.
    Not a downgrade: nothing is lost, the old spelling is simply translated."""
    if not characters.legacy_boolean_request(world):
        return
    _warn(world, "warn_racer_locked_pads_boolean_normalized",
          f"CTR ({_name(world)}): Racer-Locked Warp Pads 'true' is read the "
          f"Alpha 6 way, as a quarter of the eligible pads (1 to 6); write a "
          f"number instead, where 0 turns racer locks off.")
