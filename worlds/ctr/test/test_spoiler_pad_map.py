"""H6-01: the spoiler's effective custom destination for a displaced cup.

`write_spoiler` fed only the resolved wire map and pad ids to
`changed_pad_destination_rows`; the custom replacement travelled separately in
the resolved `custom_tracks` descriptor. The exact Hypnoshark Alpha6 spoiler
therefore said the physical Hot Air Skyway pad loads the displaced Purple Cup
destination even though native serves Baby T Park there.

These tests pin the effective-destination representation and the row builder,
then exercise `write_spoiler` through a fixture shaped exactly like the
Hypnoshark seed. They run against the resolved seed state, never against the
seed id, a specific physical pad, a specific title or slot, so they stay valid
for the generic placement packet that follows Alpha6.
"""

import copy
import io
import json
import unittest
import pkgutil

from ..custom_tracks import (
    BABY_T_PARK_EXAMPLE,
    effective_custom_destinations,
    normalize_custom_tracks,
)
from ..spoiler_pad_map import changed_pad_destination_rows
from . import CTRTestBase

#: The event descriptor as a YAML would carry it.
BABY_T_PARK = {"baby-t-park": copy.deepcopy(BABY_T_PARK_EXAMPLE)}

#: Physical pad LevelIDs relevant to the fixtures below.
HOT_AIR_SKYWAY = 7
POLAR_PASS = 12
PURPLE_CUP = 104


def _pad_ids():
    return json.loads(pkgutil.get_data(
        "worlds.ctr", "data/warp_pad_ids.json").decode("utf-8"))["pads"]


def _resolved_map(overrides):
    """Identity over the in-range pads and cups, then apply ``overrides``
    ({physical LevelID: destination LevelID}), mirroring how
    ``CTRWorld._resolve_warp_pad_map`` builds its wire map."""
    pads = _pad_ids()
    resolved = {str(i): i for i in range(28)}
    for _name, meta in pads.items():
        if meta.get("kind") == "cup":
            resolved[str(meta["level_id"])] = meta["level_id"]
    for physical, destination in overrides.items():
        resolved[str(physical)] = destination
    return resolved


class TestEffectiveCustomDestinations(unittest.TestCase):
    """The representation itself: resolved seed state maps a displaced cup to
    the effective custom track plus the displaced pad name for auditability."""

    def test_derived_from_the_resolved_descriptor(self):
        self.assertEqual(
            effective_custom_destinations(normalize_custom_tracks(BABY_T_PARK)),
            {PURPLE_CUP: ("baby-t-park", "Baby T Park")})

    def test_no_descriptor_yields_no_effective_destinations(self):
        self.assertEqual(effective_custom_destinations({}), {})


class TestChangedPadDestinationRows(unittest.TestCase):
    """The row builder: custom replacements name the effective load while
    ordinary shuffle rows stay byte-identical to the pre-custom spoiler."""

    def setUp(self):
        self.pads = _pad_ids()
        self.custom = effective_custom_destinations(
            normalize_custom_tracks(BABY_T_PARK))

    def test_hypnoshark_shape_names_the_effective_custom_track(self):
        # Purple/Baby T lands on the physical Hot Air Skyway pad; the Purple
        # Cup pad itself takes the track the shuffle moved onto it (Polar Pass).
        rows = changed_pad_destination_rows(
            _resolved_map({HOT_AIR_SKYWAY: PURPLE_CUP,
                           PURPLE_CUP: POLAR_PASS}),
            self.pads, self.custom)
        self.assertIn(
            (HOT_AIR_SKYWAY, "Hot Air Skyway Warp Pad",
             "Baby T Park (replaces Purple Cup Warp Pad)"), rows)
        self.assertIn(
            (PURPLE_CUP, "Purple Cup Warp Pad", "Polar Pass Warp Pad"), rows)

    def test_identity_destination_still_names_the_effective_custom_track(self):
        # No destination shuffle: the displaced cup's own pad reads identity on
        # the wire, but native still serves the custom track there, so the
        # effective row must appear anyway.
        rows = changed_pad_destination_rows(
            _resolved_map({}), self.pads, self.custom)
        self.assertIn(
            (PURPLE_CUP, "Purple Cup Warp Pad",
             "Baby T Park (replaces Purple Cup Warp Pad)"), rows)

    def test_no_custom_tracks_preserves_the_exact_pre_custom_output(self):
        resolved = _resolved_map({HOT_AIR_SKYWAY: PURPLE_CUP})
        expected = [(HOT_AIR_SKYWAY, "Hot Air Skyway Warp Pad",
                     "Purple Cup Warp Pad")]
        self.assertEqual(changed_pad_destination_rows(resolved, self.pads),
                         expected)
        self.assertEqual(
            changed_pad_destination_rows(resolved, self.pads, None), expected)
        self.assertEqual(
            changed_pad_destination_rows(resolved, self.pads, {}), expected)

    def test_non_displaced_shuffle_rows_are_unchanged(self):
        # A pad loading an ordinary track is untouched by a custom replacement
        # that displaces a different cup.
        rows = changed_pad_destination_rows(
            _resolved_map({HOT_AIR_SKYWAY: POLAR_PASS}),
            self.pads, self.custom)
        self.assertIn(
            (HOT_AIR_SKYWAY, "Hot Air Skyway Warp Pad", "Polar Pass Warp Pad"),
            rows)
        hot_air_row = next(
            row for row in rows if row[0] == HOT_AIR_SKYWAY)
        self.assertNotIn("Baby T Park", hot_air_row[2])

    def test_multiple_descriptor_entries_do_not_collapse_onto_the_wrong_pad(self):
        # Generic entries, as the post-Alpha6 placement packet allows: two
        # packages displace two different cups, and each physical pad must name
        # its own effective track. Synthetic titles exercise the override seam.
        two = {PURPLE_CUP: ("baby-t-park", "Baby T Park"),
               103: ("other-track", "Some Track")}
        rows = changed_pad_destination_rows(
            _resolved_map({HOT_AIR_SKYWAY: PURPLE_CUP,
                           3: 103,
                           PURPLE_CUP: POLAR_PASS,
                           103: POLAR_PASS}),
            self.pads, two)
        self.assertIn(
            (HOT_AIR_SKYWAY, "Hot Air Skyway Warp Pad",
             "Baby T Park (replaces Purple Cup Warp Pad)"), rows)
        self.assertIn(
            (3, "Crash Cove Warp Pad",
             "Some Track (replaces Yellow Cup Warp Pad)"), rows)
        # Every displaced cup still keeps its own row; no cross-mapping.
        self.assertEqual(
            sum("replaces" in name for _, _name, name in rows), 2)


class TestWriteSpoilerHypnosharkShape(CTRTestBase):
    """`write_spoiler` on a generated world forced into the Hypnoshark shape:
    Baby T Park displacing the Purple Cup on the physical Hot Air Skyway pad."""

    run_default_tests = False
    auto_construct = False
    options = {
        "oxide_goal": "any_percent",
        "podium_placement_checks": True,
        "include_gem_cups": True,
        "shuffle_gems": False,
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
    }

    def setUp(self):
        self.world_setup(seed=20260830)
        # The inherited WorldTestBase default tests skip world construction in
        # this class, so only shape the map for the fixture's own tests.
        world = getattr(self, "world", None)
        if world is not None:
            world.warp_pad_map = {
                "Hot Air Skyway Warp Pad": PURPLE_CUP,
                "Purple Cup Warp Pad": POLAR_PASS,
            }

    def _spoiler_text(self):
        handle = io.StringIO()
        self.world.write_spoiler(handle)
        return handle.getvalue()

    def test_section_names_baby_t_park_and_keeps_the_displaced_purple_cup(self):
        text = self._spoiler_text()
        self.assertIn(
            "  Hot Air Skyway Warp Pad: loads Baby T Park "
            "(replaces Purple Cup Warp Pad)\n", text)
        self.assertIn(
            "  Purple Cup Warp Pad: loads Polar Pass Warp Pad\n", text)

    def test_identity_fixture_names_the_effective_track_too(self):
        self.world.warp_pad_map = {}
        text = self._spoiler_text()
        self.assertIn(
            "  Purple Cup Warp Pad: loads Baby T Park "
            "(replaces Purple Cup Warp Pad)\n", text)
