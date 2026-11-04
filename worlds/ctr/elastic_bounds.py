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
from typing import ClassVar, List, Optional, Tuple

import settings as ap_settings
from Options import Range

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


