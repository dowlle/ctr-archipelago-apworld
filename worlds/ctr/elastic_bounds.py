"""Host-side bounds for elastic options (issue #179).

Every option CTR ships today has a fixed semantic ceiling: percentages cap at
100, the podium toggles mint a known number of rungs. 0.2.0 introduces the
first ELASTIC options -- ones sized by a per-seed count where a small knob
value means a large number of created locations/items -- starting with the
item-box per-seed activation count (#109) and a lettersanity bundle-size knob
(#148). Neither has landed yet (spine-1 content-class work, unbuilt on
`main`), so this module is infrastructure only: the mechanism a future
elastic option plugs into, not a concrete bound for one. Picking a
friendly_minimum/friendly_maximum for #109 or #148 belongs to whichever
session builds those options, against their own issue and the #71 ceiling
measurement -- not here.

Modelled directly on two upstream worlds' own conventions (there is no
core-AP mechanism for this -- verified by grep against Options.py/settings.py
in the pinned AP 0.6.7 checkout, zero hits):

  * Jak and Daxter's `friendly_minimum` / `friendly_maximum` class attributes
    on its Range options, clamped in `generate_early` when the host's
    `enforce_friendly_options` setting (a `settings.Group` Bool, host.yaml,
    default True) is on (`worlds/jakanddaxter/rules.py`,
    `worlds/jakanddaxter/__init__.py:62-84,240-274`).
  * Stardew Valley's per-option `Allow<Thing>: Bool` host settings
    (`worlds/stardew_valley/options/settings.py`), each documented as either
    "generation fails" or "replaced with <cheaper thing>" when refused
    (`worlds/stardew_valley/options/forced_options.py`).

Invariants (issue #179's ruled scope + the #71 ceiling measurement's binding
context, both apply to every elastic option that plugs in here):

1. Deterministic per seed. Every function below is a pure function of
   (option value, host settings, an optional caller-supplied dynamic
   ceiling) -- nothing here reads randomness or per-seed state beyond what
   the caller passes in.
2. Never invalidates a legal YAML. `Range.__init__` (Options.py) already
   raises if a YAML value falls outside `range_start`/`range_end` -- THAT is
   the absolute, always-enforced bound. Friendly bounds only tighten
   behaviour within that already-legal range, and only by clamping
   (silently narrowing to the nearest bound), never by rejecting a value the
   option itself accepted. The one place this module raises is the veto
   path (`apply_elastic_veto` with `on_refuse="raise"`), and that is an
   explicit, opt-in, per-option, host-controlled choice -- never automatic.
3. Composes with #178's raise/downgrade convention (`worlds/ctr/
   forced_options.py`, unmerged as of this branch's base) without
   contradicting it. #178's DOWNGRADE-WITH-WARNING is deliberately
   mutation-free (its own docstring: "does NOT mean mutating the option's
   own stored value"), scoped to cases where a downstream reader already
   resolves the real shape itself. Friendly-bound clamping is a different
   thing: it MUST mutate the stored value, because the value itself is what
   controls how many locations/items get created. Calling that
   "downgrade" would contradict #178's own definition, so this module uses
   its own vocabulary -- CLAMP (friendly bounds) and VETO-RAISE /
   VETO-REPLACE (the host veto) -- deliberately distinct from RAISE /
   DOWNGRADE-WITH-WARNING. Folding both modules behind one `apply(world)`
   entry point is a reasonable follow-up once #178 lands, and is left as an
   open question rather than decided here.
4. Reserves filler for `LocationProgressType.EXCLUDED` locations. The #71
   ceiling measurement (2026-08-08) found a legal YAML can FillError if a
   sizer drives filler to zero: CTR always excludes its own goal location
   (issue #27, `_exclude_goal_location`) for goals `oxide`/`oxidefinal`
   (verified at source: `_install_goal` calls it in exactly those two
   branches, NOT `allbosses`/`allgemcups` -- the #71 note's "always 1" is
   the default-goal case, not a universal constant, so this module derives
   the true count per goal rather than restating "1"), and a player's own
   `exclude_locations` adds one more reserved slot per name (conservatively
   -- some may name a location this seed never creates, issue #28's
   "excluded but never created" finding, which only makes the reserve
   slightly larger than strictly necessary, never smaller). See
   `estimated_filler_reserve` / `exact_filler_reserve` below.
5. Composes with #141 (the only ruled item that *subtracts* location
   supply) for free, by construction: nothing below hardcodes a location
   count. `elastic_supply_ceiling` takes the seed's current supply as a
   caller-supplied live number, so when #141 lands and shrinks it, no
   change is needed here.
"""
from typing import ClassVar, List, Literal, Optional, Tuple

import settings as ap_settings
from Options import OptionError, Range

import logging

logger = logging.getLogger(__name__)


class CTRSettings(ap_settings.Group):
    """CTR's host.yaml settings group (issue #179)."""

    class EnforceFriendlyOptions(ap_settings.Bool):
        """Clamp CTR's elastic per-seed counts (options whose value scales how
        many locations or pool items a seed creates) to friendly bounds meant
        to keep generation safe and multiplayer non-disruptive. Disabling
        this allows the full absolute range an elastic option's own YAML
        legality already permits, which may raise generation time or lower
        fill success. This setting has no effect on CTR's existing options:
        none of them are elastic, they all already have a fixed semantic
        ceiling (percentages, toggle-shaped counts). Use at your own risk.
        """
        description = "CTR Enforce Friendly Elastic-Option Bounds"

    enforce_friendly_options: "EnforceFriendlyOptions | bool" = True

    class AllowRungSizing(ap_settings.Bool):
        """Deprecated compatibility setting from the pre-0.2.0 adaptive rung
        experiment. CTR 0.2.0 never overrides disabled player YAML options;
        insufficient location capacity raises a clear OptionError instead.
        """
        description = "CTR Allow Adaptive Podium Rung Sizing"

    allow_rung_sizing: "AllowRungSizing | bool" = False


class ElasticCountOption(Range):
    """Base for CTR's elastic per-seed count options (issue #179): a Range
    option whose value scales how many locations or pool items a seed
    creates, as opposed to every option CTR ships today, which has a fixed
    semantic ceiling.

    `range_start` / `range_end` (inherited from `Range`) stay the ABSOLUTE
    bounds -- AP itself already rejects a YAML value outside them, so they
    are never re-checked here. Subclasses MAY additionally declare
    `friendly_minimum` / `friendly_maximum`: a host-recommended, generally
    tighter range applied only when the host's `enforce_friendly_options`
    setting is on (default True). Leaving either at `None` (the default)
    means "no extra restriction on that side" -- the friendly bound falls
    back to the absolute one. Concrete values are the owning option's own
    call (#109, #148, ...), justified against that issue and the #71 ceiling
    measurement; this base class supplies no values and picks none.
    """
    friendly_minimum: ClassVar[Optional[int]] = None
    friendly_maximum: ClassVar[Optional[int]] = None

    @classmethod
    def resolved_minimum(cls, friendly: bool) -> int:
        if friendly and cls.friendly_minimum is not None:
            return max(cls.range_start, cls.friendly_minimum)
        return cls.range_start

    @classmethod
    def resolved_maximum(cls, friendly: bool) -> int:
        if friendly and cls.friendly_maximum is not None:
            return min(cls.range_end, cls.friendly_maximum)
        return cls.range_end


def resolve_elastic_bounds(
    option_cls: "type[ElasticCountOption]",
    *,
    friendly: bool,
    dynamic_ceiling: Optional[int] = None,
) -> Tuple[int, int]:
    """The `(minimum, maximum)` this option should be clamped into.

    `dynamic_ceiling`, when given, additionally caps the maximum (e.g. from
    `elastic_supply_ceiling` below) -- it can never raise it above the
    option's own static bound. The pair can come back inverted
    (`maximum < minimum`) if the dynamic ceiling is tighter than the
    resolved minimum; that is a genuine per-seed infeasibility (the elastic
    option cannot fit even at its friendliest floor), and deciding what to
    do about it -- raise, or fall back to the absolute floor and accept the
    risk -- is the owning option's call, not this function's. This function
    only resolves the numbers; it never mutates or raises.
    """
    lo = option_cls.resolved_minimum(friendly)
    hi = option_cls.resolved_maximum(friendly)
    if dynamic_ceiling is not None:
        hi = min(hi, dynamic_ceiling)
    return lo, hi


def clamp_elastic_option(
    world,
    option_name: str,
    *,
    friendly: Optional[bool] = None,
    dynamic_ceiling: Optional[int] = None,
) -> Optional[str]:
    """Clamp `world.options.<option_name>` into its resolved friendly bounds,
    mutating the stored value in place (CLAMP, per this module's docstring
    point 3 -- distinct from #178's mutation-free DOWNGRADE-WITH-WARNING).

    `friendly` defaults to `world.settings.enforce_friendly_options` (the
    host.yaml toggle); pass it explicitly to bypass the host lookup (unit
    tests do this so they do not depend on process-global host settings
    state). Returns a log message describing what changed (already logged
    at WARNING), or `None` if the stored value was already in bounds.
    """
    option = getattr(world.options, option_name)
    option_cls = type(option)
    if friendly is None:
        friendly = bool(world.settings.enforce_friendly_options)
    lo, hi = resolve_elastic_bounds(option_cls, friendly=friendly, dynamic_ceiling=dynamic_ceiling)
    old = option.value
    if lo > hi:
        # Genuine per-seed infeasibility at the resolved bounds (see
        # resolve_elastic_bounds) -- surface it rather than silently picking
        # a number outside the range the caller asked for.
        raise OptionError(
            f"CTR '{option_name}' has no value that satisfies both its "
            f"friendly bounds and this seed's available supply "
            f"({lo} > {hi}). This is a per-seed capacity conflict, not a "
            f"bad YAML value; lower another option that consumes the same "
            f"supply, or disable friendly-bound enforcement in host.yaml.")
    if old < lo:
        option.value = lo
    elif old > hi:
        option.value = hi
    else:
        return None
    message = (
        f"CTR '{option_name}' for player {world.player} "
        f"({world.multiworld.player_name[world.player]}) was {old}, clamped "
        f"to {option.value} (friendly bounds {'on' if friendly else 'off'}, "
        f"resolved range {lo}-{hi}).")
    logger.warning(message)
    return message


def apply_elastic_veto(
    world,
    *,
    allowed: bool,
    is_active: bool,
    option_name: str,
    on_refuse: Literal["raise", "replace"],
    reason: str,
    replacement=None,
) -> Optional[str]:
    """Enforce a host veto over one elastic option, Stardew-style
    (`force_change_options_if_banned`). `allowed` is the host.yaml switch
    (e.g. `world.settings.allow_box_activation`); `is_active` is whatever
    the OWNING option defines as "this seed is using the feature at all"
    (left to the caller -- #179 does not decide what "active" means for a
    box count or a letter knob). A no-op when `allowed` is true or the
    option is not active.

    `on_refuse` has no default, on purpose: issue #179 explicitly leaves
    "raise vs. replace" as a per-veto choice ("which of those two CTR picks
    per veto matters less than picking one and saying so where the host can
    read it") -- the owning option's session must choose, and document the
    choice on the setting itself (the `EnforceFriendlyOptions`-style
    docstring convention above).

    "raise" aborts generation with `reason`. "replace" sets the option to
    `replacement` (required for that mode) and logs a warning built from
    `reason`.
    """
    if allowed or not is_active:
        return None
    if on_refuse == "raise":
        raise OptionError(
            f"CTR '{option_name}' for player {world.player} "
            f"({world.multiworld.player_name[world.player]}) is disallowed "
            f"from host.yaml. {reason}")
    if on_refuse == "replace":
        if replacement is None:
            raise ValueError(
                "apply_elastic_veto(on_refuse='replace') requires a "
                "replacement value")
        option = getattr(world.options, option_name)
        option.value = replacement
        message = (
            f"CTR '{option_name}' for player {world.player} "
            f"({world.multiworld.player_name[world.player]}) disallowed "
            f"from host.yaml, replaced with {replacement!r}. {reason}")
        logger.warning(message)
        return message
    raise ValueError(f"apply_elastic_veto: unknown on_refuse={on_refuse!r}")


def goal_excluded_location_reserve(world) -> int:
    """How many of THIS seed's locations `_exclude_goal_location` (issue #27)
    has excluded so far. 0 until `_install_goal` runs (partway through
    `create_items`); as of this branch's base (`39db4898d`) that is exactly
    1 for goals `oxide`/`oxidefinal` and 0 for `allbosses`/`allgemcups` --
    derived from `world._goal_excluded_location_names`, populated at the
    exclusion call site itself, not restated as a constant here (the #71
    note's "the single excluded location" is the default-goal case, not a
    universal one -- verified against `_install_goal`'s four branches)."""
    return len(getattr(world, "_goal_excluded_location_names", ()))


def predicted_goal_excluded_reserve(options) -> int:
    """Goal-location filler reserve available during ``generate_early``.

    ``goal_excluded_location_reserve`` intentionally reads the actual exclusion
    list and is therefore correct only after ``_install_goal``. The rung sizer
    runs before regions and items exist, so it needs this pure-options twin.
    The composed goal model excludes exactly one real location when the Oxide
    condition is ``first`` or ``final`` and none when it is ``none``.
    """
    return int(options.oxide_goal.value != 0)


def player_exclude_locations_reserve(world) -> int:
    """How many names are in this player's own `exclude_locations` YAML
    option. Available from `generate_early` onward (it is a raw option
    value, not a resolved location state). Conservative: a name that turns
    out not to exist this seed (issue #28's "excluded but never created"
    finding) still counts here, which only makes the reserve larger than
    strictly necessary -- the safe direction for a ceiling, never the
    dangerous one."""
    return len(world.options.exclude_locations.value)


def estimated_filler_reserve(world) -> int:
    """The filler reserve an elastic sizer should subtract from its own
    ceiling BEFORE it creates locations (so during `create_items`, after
    `_install_goal` has run). Sum of the two reserves above. This is an
    ESTIMATE, not the final truth -- see `exact_filler_reserve` for why an
    exact count is not available yet at this point in generation."""
    return goal_excluded_location_reserve(world) + player_exclude_locations_reserve(world)


def exact_filler_reserve(world) -> int:
    """The EXACT number of this player's locations carrying
    `LocationProgressType.EXCLUDED`, counted directly. Only correct from
    `pre_fill` onward: AP core applies `exclude_locations` as location
    progress state in `Main.py` (`exclusion_rules`, right after `set_rules`)
    -- AFTER every world's `create_items`, so an elastic sizer computing its
    OWN ceiling during `create_items` cannot see this number yet and must
    use `estimated_filler_reserve` instead. This exact count exists for
    tests and for any logic that legitimately runs post-fill-prep."""
    from BaseClasses import LocationProgressType
    return sum(
        1 for loc in world.multiworld.get_locations(world.player)
        if loc.progress_type == LocationProgressType.EXCLUDED)


def elastic_supply_ceiling(world, *, available_supply: int) -> int:
    """`available_supply`, minus this seed's estimated filler reserve, floored
    at 0. `available_supply` is always a live, caller-supplied number (e.g.
    the #71 ceiling formula's `82 + 16*C + L_other`, recomputed for whatever
    the seed's actual supply is) -- never a constant restated here, so #141
    (the only ruled item that subtracts location supply) composes for free
    whenever it lands: nothing in this module needs to change."""
    return max(0, available_supply - estimated_filler_reserve(world))
