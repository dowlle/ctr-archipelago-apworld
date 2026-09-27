"""Relic-race perfect checks -- "break every time crate in the relic race" (#49).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. One check per relic
race, earned by breaking every time crate in it. The engine already computes the
signal: it counts a level's time crates into `gGT->timeCratesInLEV` at load and
the driver's broken count into `driver->numTimeCrates` (it renders the "NN/MM"
counter from them), so "broke every crate" is `numTimeCrates == timeCratesInLEV`
at the end of a relic race -- the same comparison retail uses for its
ten-second bonus in RR_EndEvent_UnlockAward. Per the ruling (2026-07-20,
Feature Triage Register) this is a location class, NOT a reward gate: it never
changes whether a relic is awarded, and it pays whichever relic tier (or none)
the adjusted time reaches. The stricter `rr_require_perfects` variant is a
DIFFERENT mechanic, backlogged, and deliberately does not share a name with
this one.

WHO OWNS THE SEMANTICS. The apworld owns the names, the per-seed subset (the
`relic_perfect_checks` option), the logic rule (Rules.add_time_trial_and_ctr_
requirements) and the `relic_perfect_checks` wire block. Native owns the
detection at the relic race end and the send.

The 18 relic tracks are the 16 adventure trophy tracks plus the two trial tracks
(Slide Coliseum, Turbo Track), exactly the set that carries Time Trial locations.
A seed creates one check per relic race that exists in it: all 18 with the
option on, minus the destination the Cortex Vortex pad track dropped. The
relic-tier draw (#171) does not remove any: it decides which relic TIERS are
checks, while the relic race itself stays playable on every pad.

DATAPACKAGE STABILITY. This class claims the additive block 35012400, stride 1 in
RELIC_TRACKS order, and registers all 18 names UNCONDITIONALLY. The block is
clear of every shipped block: the trophy/boss/gem 35011xxx family, the
trial+token 35012000..35012315 family this one extends, the crystal 35013xxx
family, and the podium 35015000 / 35015100 blocks. Nothing shipped is renumbered
(the 35015000 precedent: additive blocks never move). These names rode the
0.2.0 datapackage bump (#177) and are frozen; building the option changed no
name and no id.

CORTEX VORTEX AND CUSTOM TRACKS. `Cortex Vortex: Relic Race Perfect`
(35026005) is reserved but not minted, and the custom-track perfect family
(`Custom Track N: Relic Race Perfect`, 35024000 + N - 1) is reserved in
custom_check_namespace but not registered. Neither is created here. The
custom-track side is prepared by `relic_capable_custom_slots` below, which
enumerates the packages whose measured capability says they carry relic time
crates; creation stays off (`CUSTOM_PERFECT_CREATION_ENABLED`) until the
identity is minted and a custom Relic Race mode is admitted.
"""
import json
import pkgutil

from .location_class import LocationClass

# Additive block for the 18 relic-perfect checks, stride 1 in RELIC_TRACKS order.
RELIC_PERFECT_CODE_BASE = 35012400

# Location-name suffix. Deliberately NOT ending in "Time Trial": the sphere-search
# vanilla reward map (warp_pad_logic._reward_for) and the stage-2 bookkeeping key
# off that suffix, and a perfect check yields no relic, so it must stay
# reward-neutral there.
RELIC_PERFECT_SUFFIX = "Relic Race Perfect"


def _relic_tracks():
    """The 18 relic-race tracks in canonical (Sapphire-trial code) order, read
    from data/locations.json so this block's codes/order can never drift from the
    relic block they parallel."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": Sapphire Time Trial") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 18 entries. Each entry is
# BOTH the track name and its AP region name: data/locations.json gives every
# Sapphire trial the region of its own track (the 16 trophy tracks and the two
# trial tracks are all regions), so a perfect check parents to the same region as
# the relic races it belongs to without a second lookup table.
RELIC_TRACKS = _relic_tracks()


class RelicPerfectLocationClass(LocationClass):
    """The 18 relic-race perfect checks as a `LocationClass` (#176)."""

    key = "relic_perfect"
    display_name = "Relic Race Perfect Checks"
    code_blocks = (RELIC_PERFECT_CODE_BASE,)

    def all_locations(self):
        return [(self.location_name(track), RELIC_PERFECT_CODE_BASE + ti, track)
                for ti, track in enumerate(RELIC_TRACKS)]

    def location_name(self, track: str) -> str:
        """AP location name for a track's perfect check, e.g.
        'Crash Cove: Relic Race Perfect'."""
        return f"{track}: {RELIC_PERFECT_SUFFIX}"

    def created_location_names(self, options):
        """One check per relic race this seed has, when the option is on.

        Off (or an options object without the option, e.g. a stub) creates
        nothing and takes no random number. The Cortex Vortex pad track's
        dropped destination has no pad, so its relic race does not exist and
        its check is left out rather than moved: Cortex Vortex's own perfect
        identity is not minted."""
        opt = getattr(options, "relic_perfect_checks", None)
        if options is None or opt is None or not bool(opt.value):
            return []
        from .cortex_vortex_track import dropped_track
        dropped = dropped_track(options)
        return [self.location_name(track) for track in RELIC_TRACKS
                if track != dropped]

    def wire_block(self, options):
        """The `relic_perfect_checks` slot_data block for an enabled seed.

        `locations` maps each relic race's engine LevelID (canonical decimal
        string) to a one-slot code array, the shared location-class family
        shape (Contract 7a). Only created checks appear; a destination this
        seed does not have is simply absent."""
        created = set(self.created_location_names(options))
        lids = track_level_ids()
        return {
            "enabled": bool(created),
            "locations": {
                str(lids[track]): [self.code_for(track)]
                for track in RELIC_TRACKS
                if self.location_name(track) in created
            },
        }


#: The registered relic-perfect class. `Locations.py` registers this instance.
RELIC_PERFECT_CLASS = RelicPerfectLocationClass()


def track_level_ids():
    """Relic track name -> engine LevelID, from data/warp_pad_ids.json.

    A pad is named after the track it loads in the unshuffled game, so its
    `level_id` IS that track's LevelID (Crash Cove 3, Slide Coliseum 16, ...).
    Destination shuffle moves which pad loads a track, never the track's own
    LevelID, and native keys the relic race by the LevelID it is racing."""
    pads = json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8")
    )["pads"]
    return {name[:-len(" Warp Pad")]: meta["level_id"]
            for name, meta in pads.items()
            if name[:-len(" Warp Pad")] in RELIC_TRACKS}


def restore_from_wire(options, passthrough) -> None:
    """Universal Tracker: restore the option from the connected seed.

    The always-emitted `ctr_options.relic_perfect_checks` scalar is the
    authority. When it is true the block must be present and must be EXACTLY
    what this apworld would emit for the restored options (same LevelIDs, same
    frozen codes, the Cortex Vortex dropped destination absent). Anything else
    is refused rather than reinterpreted, so a tracker can never show a
    different set of perfect checks than the room has. A pre-#49 wire (no
    scalar, no block) restores to off.

    Must run after the Cortex Vortex dropped destination is restored, because
    the expected block depends on it."""
    from Options import OptionError
    co = passthrough.get("ctr_options", {}) or {}
    raw = co.get("relic_perfect_checks", False)
    if type(raw) is not bool:
        raise OptionError(
            "CTR relic_perfect_checks: ctr_options scalar must be a boolean")
    block = passthrough.get("relic_perfect_checks")
    options.relic_perfect_checks.value = int(raw)
    if not raw:
        if block is not None:
            raise OptionError(
                "CTR relic_perfect_checks: block present on a seed with the "
                "option off")
        return
    expected = RELIC_PERFECT_CLASS.wire_block(options)
    if block != expected:
        raise OptionError(
            "CTR relic_perfect_checks: block does not match the frozen "
            "LevelID/code set for this seed")


# ---------------------------------------------------------------------------
# Custom tracks (0.3.0 content plan). Safe hooks only.
# ---------------------------------------------------------------------------

#: Creation switch for custom-track perfect checks. Off, and must stay off,
#: until (1) the reserved family `perfect_location` (35024000 + slot - 1,
#: "Custom Track N: Relic Race Perfect") is minted into the datapackage by an
#: approved unfreeze, and (2) a custom Relic Race mode is admitted in the
#: custom_tracks descriptor (today `modes` admits only `ctr_challenge`), with
#: its own Time Trial family (`relic_location`, 35022000) minted alongside.
#: TODO(#49, custom tracks): flip only together with both of those.
CUSTOM_PERFECT_CREATION_ENABLED = False


def relic_capable_custom_slots(custom_tracks):
    """Seed slots whose package can host a perfect check once enabled.

    A package qualifies when its measured `flags.relic_crates` is true: the LEV
    carries relic time crates, which is what native's `timeCratesInLEV` counts.
    Capability alone never activates a mode (the custom-track specification:
    Relic additionally needs target times and an admitted mode), so this is an
    enumeration for design and tests, not a creation list. Sorted by slot."""
    out = []
    for entry in (custom_tracks or {}).values():
        flags = entry.get("flags") or {}
        if flags.get("relic_crates") is True:
            out.append(int(entry["slot"]))
    return sorted(out)


def custom_perfect_reserved_code(slot: int) -> int:
    """The RESERVED (unminted) code a custom slot's perfect check would use.
    Reservation only: this id is not in the datapackage and must never be
    sent or created while CUSTOM_PERFECT_CREATION_ENABLED is False."""
    from .custom_check_namespace import custom_check_code
    return custom_check_code("perfect_location", slot)


def created_custom_perfect_slots(custom_tracks):
    """Custom slots that get a perfect check THIS seed. Always empty today;
    see CUSTOM_PERFECT_CREATION_ENABLED."""
    if not CUSTOM_PERFECT_CREATION_ENABLED:
        return []
    raise NotImplementedError(
        "custom-track perfect checks need a minted identity and an admitted "
        "custom Relic Race mode")
