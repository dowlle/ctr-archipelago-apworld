"""Binding capability rulings in one machine-readable inventory.

This module is the bridge between field evidence and executable logic. Production
rules and parity tests consume the same records so a confirmed track cannot be
added to one handwritten set while being omitted from another.

Only ``confirmed`` records may gate locations ON THEIR OWN EVIDENCE. Preliminary
and unmeasured matrix rows belong in the vault evidence, not in this executable
contract.

``ruled`` is the one exception, and it is deliberately narrow. A ruled record
carries no field measurement; it exists because a design decision ADDS a
requirement to tracks nobody has measured. Adding a requirement can only ever
shrink what logic believes reachable, so a wrong ruling costs sphere depth and
cannot strand progression -- which is why it is allowed to gate while an
unmeasured *confirmed* claim is not. The two statuses stay distinct so nobody
later reads a design preference as evidence.
"""
from dataclasses import dataclass
from typing import FrozenSet


STATUS_CONFIRMED = "confirmed"
STATUS_RULED = "ruled"


@dataclass(frozen=True)
class FinishCapability:
    """A confirmed capability boundary for crossing a track's finish line."""

    track: str
    boost_count: int
    hard_shortcut_escape: bool
    gate_held_first: bool
    source: str
    status: str = STATUS_CONFIRMED


CONFIRMED_FINISH_CAPABILITIES = (
    FinishCapability(
        track="Cortex Castle",
        boost_count=2,
        hard_shortcut_escape=False,
        gate_held_first=False,
        source="Capability Matrix Field Notes, 2026-08-09 21:31-22:18 CEST",
    ),
    FinishCapability(
        track="Hot Air Skyway",
        boost_count=2,
        hard_shortcut_escape=False,
        gate_held_first=False,
        source="Live v3 test session, 2026-08-12 21:33-21:36 CEST",
    ),
    FinishCapability(
        track="Oxide Station",
        boost_count=2,
        hard_shortcut_escape=True,
        gate_held_first=True,
        source="Live pre1 test session, 2026-08-14 17:15 CEST",
    ),
)

CONFIRMED_FINISH_BY_TRACK = {
    record.track: record for record in CONFIRMED_FINISH_CAPABILITIES
}
assert len(CONFIRMED_FINISH_BY_TRACK) == len(CONFIRMED_FINISH_CAPABILITIES)
assert all(record.status == STATUS_CONFIRMED
           for record in CONFIRMED_FINISH_CAPABILITIES)


@dataclass(frozen=True)
class DifficultyTrackGroup:
    """Tracks sharing one confirmed option-aware placement rule."""

    name: str
    tracks: FrozenSet[str]
    source: str
    status: str = STATUS_CONFIRMED


EASY_TROPHY_GROUP = DifficultyTrackGroup(
    name="easy_trophy_group",
    tracks=frozenset({
        "Crash Cove",
        "Roo's Tubes",
        "Tiger Temple",
        "Coco Park",
        "Mystery Caves",
        "Blizzard Bluff",
        "Sewer Speedway",
    }),
    source="Capability Matrix Field Notes, rulings 2026-08-09 21:33-22:08 CEST",
)

#: The tracks that carried NO capability requirement at any difficulty, brought
#: under the same rule by design ruling rather than by measurement.
#:
#: Before this, the sixteen trophy races split three ways: seven measured into
#: the easy group, three gated by USF geometry, and these six gated by nothing
#: at all. That last group was not a finding that they are free -- nobody had
#: driven them for the matrix -- so logic was treating "unmeasured" as "no
#: requirement", which is the permissive reading of silence.
#:
#: N. Gin Labs is the clearest reason to distrust that: eight of its box slots
#: are already ruled at `boost >= 2`, so parts of the track are believed to need
#: USF while winning its trophy race was free at every difficulty.
#:
#: Status is `ruled`, not `confirmed`, and it must stay that way until someone
#: actually drives these for the matrix. If a later field pass measures one, it
#: moves into EASY_TROPHY_GROUP with a real source line and leaves here.
RULED_TROPHY_GROUP = DifficultyTrackGroup(
    name="ruled_trophy_group",
    tracks=frozenset({
        "Papu's Pyramid",
        "Dingo Canyon",
        "Dragon Mines",
        "Polar Pass",
        "Tiny Arena",
        "N. Gin Labs",
    }),
    source="Design ruling 2026-08-17: unmeasured tracks take the easy-group "
           "requirement rather than none",
    status=STATUS_RULED,
)

assert not (EASY_TROPHY_GROUP.tracks & RULED_TROPHY_GROUP.tracks), \
    "a track cannot be both measured and ruled"


def difficulty_gated_tracks() -> FrozenSet[str]:
    """Every track the logic_difficulty rule gates, whatever its provenance.

    Production reads THIS rather than either group directly, so a track cannot
    be gated by one consumer and skipped by another -- the same reason the
    finish helpers below exist.
    """
    return EASY_TROPHY_GROUP.tracks | RULED_TROPHY_GROUP.tracks


def unconditional_usf_finish_tracks() -> FrozenSet[str]:
    return frozenset(
        record.track for record in CONFIRMED_FINISH_CAPABILITIES
        if not record.hard_shortcut_escape
    )


def usf_or_hard_finish_tracks() -> FrozenSet[str]:
    return frozenset(
        record.track for record in CONFIRMED_FINISH_CAPABILITIES
        if record.hard_shortcut_escape
    )


def held_first_gated_tracks() -> FrozenSet[str]:
    return frozenset(
        record.track for record in CONFIRMED_FINISH_CAPABILITIES
        if record.gate_held_first
    )
