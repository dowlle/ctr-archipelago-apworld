"""Binding capability rulings in one machine-readable inventory.

This module is the bridge between field evidence and executable logic. Production
rules and parity tests consume the same records so a confirmed track cannot be
added to one handwritten set while being omitted from another.

Only ``confirmed`` records may gate locations. Preliminary and unmeasured matrix
rows belong in the vault evidence, not in this executable contract.
"""
from dataclasses import dataclass
from typing import FrozenSet


STATUS_CONFIRMED = "confirmed"


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
