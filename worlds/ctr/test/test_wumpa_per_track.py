"""Per-race-destination Reach 10 Wumpa checks (2026-08-29 specification, Lane A).

The specification's acceptance list, one test per line, plus the identity
properties the approved datapackage unfreeze rests on.

What is deliberately NOT tested here: the crossing signal, runtime destination
identity and pad re-entry lifecycle. Those are native's half and are pinned in
the paired client candidate. What IS tested is everything the apworld owns: the
mode, which locations a seed creates, every standalone/Cup route to them,
custom-destination eligibility, the resolved wire mapping and Universal
Tracker reconstruction.

THE GEM CUP RULE IS STRUCTURAL, NOT A LOCATION RULE TERM. A retail track's check
lives in a dead-end "<track>: Wumpa" region reached from its track region and
every Gem Cup that legs it. The region holds only that one track-owned location,
so Cup access can emit Wumpa without exposing the track's Trophy, relic, token
or box families. Repeated occurrences remain alternative routes to one check.
"""
import json
import unittest
from unittest import mock

from . import setup_multiworld

from .. import ctrAPWorld
from ..destinations import boss_garage_tracks
from ..item_boxes import BOX_TRACKS
from ..wumpa_checks import (
    WUMPA_CLASS,
    WUMPA_GLOBAL,
    WUMPA_OFF,
    WUMPA_PER_TRACK,
    WUMPA_TEN_LOCATION,
    eligible_retail_tracks,
    retail_location_name,
)
from ..destinations import TRIAL_TROPHY_CLASS
from . import CTRTestBase

BOSS_WUMPA_TRACKS = boss_garage_tracks()

#: The generation steps a UT restore needs run before it: options exist after
#: generate_early, and nothing later is consulted by `_ut_restore_options`.
_UT_STEPS = ("generate_early",)


#: The custom destination slot Alpha6 supports, spelled out rather than indexed
#: so a reordering of CUSTOM_DESTINATION_ROLES fails here instead of silently
#: renumbering a permanent code.
CUSTOM_ROLE = "purple_gem_cup"
CUSTOM_LOCATION = "Purple Gem Cup Custom Race: Reach 10 Wumpa"
#: Since #133 a track with a named block owns its Wumpa check in that block:
#: Baby T Park is block 8, offset 14. The role identity above is the generic
#: path, exercised with `without_named_block()`.
NAMED_LOCATION = "Baby T Park: Reach 10 Wumpa"
NAMED_CODE = 35201614


def without_named_block():
    """A build where baby-t-park has no named block (test only)."""
    from .. import destinations
    return mock.patch.dict(destinations.NAMED_BY_KEY, {}, clear=True)


class _FakeOption:
    def __init__(self, value):
        self.value = value


class _FakeOptions:
    """Just enough of an options object for the creation predicate.

    The location-class infrastructure drives every class with stand-ins like
    this, so the predicate has to read defensively -- including answering "off"
    for an options object that carries no `wumpa_check` at all.
    """

    def __init__(self, mode=None, custom_tracks=None):
        if mode is not None:
            self.wumpa_check = _FakeOption(mode)
        if custom_tracks is not None:
            self.custom_tracks = _FakeOption(custom_tracks)


# ---------------------------------------------------------------------------
# Option shape and the retired Boolean


class TestOptionCompatibility(unittest.TestCase):
    """Spec gate: old YAML Boolean false is off, old true is global."""

    def setUp(self):
        from ..Options import WumpaCheck
        self.option = WumpaCheck

    def test_the_three_modes_have_the_ruled_values(self):
        self.assertEqual(
            (self.option.option_off, self.option.option_global,
             self.option.option_per_track),
            (0, 1, 2))
        self.assertEqual(self.option.default, self.option.option_off)

    def test_a_boolean_false_yaml_is_off(self):
        self.assertEqual(self.option.from_any(False).value,
                         self.option.option_off)

    def test_a_boolean_true_yaml_is_global(self):
        self.assertEqual(self.option.from_any(True).value,
                         self.option.option_global)

    def test_the_mode_words_still_work(self):
        for word, value in (("off", 0), ("global", 1), ("per_track", 2)):
            with self.subTest(word=word):
                self.assertEqual(self.option.from_any(word).value, value)

    def test_a_nonsense_value_is_still_refused(self):
        with self.assertRaises(KeyError):
            self.option.from_any("per-track")


# ---------------------------------------------------------------------------
# Creation counts and identity, out of a generated world


class TestCreationCounts(unittest.TestCase):
    """The per-mode subsets, driven directly off the predicate.

    Direct rather than through a generated seed so all three modes and the
    two custom arms are covered in one cheap test; the generated seeds below
    then prove the predicate and the real world agree.
    """

    def test_off_creates_nothing(self):
        self.assertEqual(
            WUMPA_CLASS.created_location_names(_FakeOptions(WUMPA_OFF)), [])

    def test_an_options_object_without_the_key_is_off(self):
        self.assertEqual(WUMPA_CLASS.created_location_names(_FakeOptions()), [])

    def test_global_creates_only_the_global_check(self):
        self.assertEqual(
            WUMPA_CLASS.created_location_names(_FakeOptions(WUMPA_GLOBAL)),
            [WUMPA_TEN_LOCATION])

    def test_per_track_creates_the_sixteen_regular_trophy_destinations(self):
        names = WUMPA_CLASS.created_location_names(_FakeOptions(WUMPA_PER_TRACK))
        self.assertEqual(len(names), 16)
        self.assertEqual(names,
                         [retail_location_name(t)
                          for t in eligible_retail_tracks(
                              _FakeOptions(WUMPA_PER_TRACK))])

    def test_per_track_does_not_also_create_the_global_check(self):
        """The modes are alternatives, not layers: the specification rules out
        keeping the global check as a bonus."""
        self.assertNotIn(
            WUMPA_TEN_LOCATION,
            WUMPA_CLASS.created_location_names(_FakeOptions(WUMPA_PER_TRACK)))

    def test_the_two_relic_only_trial_tracks_are_not_created(self):
        """Their registered identities are not enough: the retail Adventure
        pads still launch relic races, which cannot award these checks."""
        names = WUMPA_CLASS.created_location_names(_FakeOptions(WUMPA_PER_TRACK))
        self.assertNotIn(retail_location_name("Slide Coliseum"), names)
        self.assertNotIn(retail_location_name("Turbo Track"), names)

    def test_a_trial_track_joins_when_its_trophy_race_is_in_the_seed(self):
        """#203's future option is the proof of an AI/arcade race surface. The
        two trial tracks activate independently rather than as an assumed pair."""
        slide_trophy = TRIAL_TROPHY_CLASS.location_name("Slide Coliseum")
        with mock.patch.object(
                TRIAL_TROPHY_CLASS, "created_location_names",
                return_value=[slide_trophy]):
            names = WUMPA_CLASS.created_location_names(
                _FakeOptions(WUMPA_PER_TRACK))
        self.assertEqual(len(names), 17)
        self.assertIn(retail_location_name("Slide Coliseum"), names)
        self.assertNotIn(retail_location_name("Turbo Track"), names)


# ---------------------------------------------------------------------------
# Region placement -- the structural half of the Gem Cup ruling


class TestRegionPlacement(unittest.TestCase):
    def test_each_retail_check_sits_in_its_own_destination_track_region(self):
        by_name = {name: region for name, _c, region
                   in WUMPA_CLASS.all_locations()}
        for track in BOX_TRACKS:
            with self.subTest(track=track):
                self.assertEqual(by_name[retail_location_name(track)], track)

    def test_the_global_check_stays_in_menu(self):
        by_name = {name: region for name, _c, region
                   in WUMPA_CLASS.all_locations()}
        self.assertEqual(by_name[WUMPA_TEN_LOCATION], "Menu")

    def test_the_custom_check_sits_in_its_destination_role_region(self):
        by_name = {name: region for name, _c, region
                   in WUMPA_CLASS.all_locations()}
        self.assertEqual(by_name[CUSTOM_LOCATION], "Purple Gem Cup")


class TestPerTrackSeed(CTRTestBase):
    """A generated `per_track` seed with no custom track."""

    run_default_tests = False
    options = {"wumpa_check": "per_track"}


    def test_it_supplies_locations_rather_than_spending_them(self):
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(items), len(locations))


class TestPerTrackGemCupSeed(CTRTestBase):
    """Standalone races and Gem Cups are alternative Wumpa routes.

    The joint dead-end region must expose only the Wumpa location. A Cup must
    never gain a direct entrance to the whole track region.
    """

    run_default_tests = False
    options = {
        "wumpa_check": "per_track",
        "include_gem_cups": True,
        "podium_placement_checks": True,
        "podium_finish_rungs": True,
    }


class TestBossGarageRoutes(unittest.TestCase):
    """Boss races are additional routes to their destination Wumpa check."""

    def test_retail_boss_track_table_is_exact(self):
        self.assertEqual(BOSS_WUMPA_TRACKS, {
            "Ripper Roo Garage": "Roo's Tubes",
            "Papu Papu Garage": "Papu's Pyramid",
            "Komodo Joe Garage": "Dragon Mines",
            "Pinstripe Garage": "Hot Air Skyway",
            "N. Oxide Garage": "Oxide Station",
        })


    def test_global_mode_region_graph_is_byte_identical(self):
        """The new table is consulted only while per-track regions exist."""
        options = {"wumpa_check": "global"}
        current = setup_multiworld(ctrAPWorld, seed=20260902, options=options)
        with mock.patch.dict(BOSS_WUMPA_TRACKS, {}, clear=True):
            legacy = setup_multiworld(ctrAPWorld, seed=20260902, options=options)

        def graph_bytes(mw):
            rows = []
            for region in mw.get_regions(1):
                rows.append({
                    "name": region.name,
                    "type": getattr(region, "type", None),
                    "locations": [location.name for location in region.locations],
                    "exits": [
                        [entrance.name,
                         entrance.connected_region.name
                         if entrance.connected_region else None,
                         getattr(entrance, "access_rule_text", None)]
                        for entrance in region.exits
                    ],
                })
            return json.dumps(rows, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")

        self.assertEqual(graph_bytes(current), graph_bytes(legacy))


class TestOffSeed(CTRTestBase):
    run_default_tests = False
    options = {"wumpa_check": "off"}


    def test_no_wumpa_location_is_created(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        self.assertNotIn(WUMPA_TEN_LOCATION, names)
        for track in BOX_TRACKS:
            with self.subTest(track=track):
                self.assertNotIn(retail_location_name(track), names)


# ---------------------------------------------------------------------------
# Universal Tracker

