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
import copy
import unittest
from unittest import mock

from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld, custom_tracks

from ..custom_tracks import BABY_T_PARK_EXAMPLE, WUMPA_COLLECTIBLE_FLAG
from ..item_boxes import BOX_TRACKS, TRACK_LEVEL_IDS
from ..wumpa_checks import (
    CUSTOM_DESTINATION_ROLES,
    WUMPA_CLASS,
    WUMPA_CODE_BASE,
    WUMPA_CUSTOM_CODE_BASE,
    WUMPA_GLOBAL,
    WUMPA_OFF,
    WUMPA_PER_TRACK,
    WUMPA_TEN_LOCATION,
    eligible_custom_roles,
    eligible_retail_tracks,
    retail_location_name,
)
from ..trial_trophy import TRIAL_TROPHY_CLASS
from . import CTRTestBase

#: The generation steps a UT restore needs run before it: options exist after
#: generate_early, and nothing later is consulted by `_ut_restore_options`.
_UT_STEPS = ("generate_early",)

BABY_T_PARK = {"baby-t-park": copy.deepcopy(BABY_T_PARK_EXAMPLE)}

#: The custom destination slot Alpha6 supports, spelled out rather than indexed
#: so a reordering of CUSTOM_DESTINATION_ROLES fails here instead of silently
#: renumbering a permanent code.
CUSTOM_ROLE = "purple_gem_cup"
CUSTOM_LOCATION = "Purple Gem Cup Custom Race: Reach 10 Wumpa"


def _no_wumpa_collectible():
    """A descriptor whose measured wumpa capability says NO.

    Not the real package: the actual Baby T Park v1.0.0 files measure true. This
    is the shape the eligibility rule has to refuse, and the shape a genuinely
    fruitless future package would arrive in.
    """
    entry = copy.deepcopy(BABY_T_PARK_EXAMPLE)
    entry["flags"][WUMPA_COLLECTIBLE_FLAG] = False
    return {"baby-t-park": entry}


def _registry_measuring_no_wumpa():
    """Patch the release registry to measure this package as fruitless.

    Alpha6 pins generation to ONE release-approved package identity, so a
    descriptor whose flags disagree with the registry is refused before
    eligibility is ever consulted -- which is the correct fail-closed behaviour
    and is asserted separately below. To exercise the eligibility rule itself,
    the registry has to be the thing that says "this package has no route to ten
    fruit". That is the state a future package genuinely arrives in, and it is
    what this patch stands in for.
    """
    return mock.patch.object(custom_tracks, "BABY_T_PARK_EXAMPLE",
                             _no_wumpa_collectible()["baby-t-park"])


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

    def test_the_wire_joins_the_same_trial_track_and_no_other(self):
        slide_trophy = TRIAL_TROPHY_CLASS.location_name("Slide Coliseum")
        options = _FakeOptions(WUMPA_PER_TRACK)
        with mock.patch.object(
                TRIAL_TROPHY_CLASS, "created_location_names",
                return_value=[slide_trophy]):
            mapping = WUMPA_CLASS.wire_block(options)["retail_tracks"]
        self.assertIn(str(TRACK_LEVEL_IDS["Slide Coliseum"]), mapping)
        self.assertNotIn(str(TRACK_LEVEL_IDS["Turbo Track"]), mapping)

    def test_trial_and_custom_track_eligibility_are_additive(self):
        """A bound custom race neither enables nor suppresses a trial race.

        Each contributes its own destination check when its own capability is
        present in the seed.
        """
        slide_trophy = TRIAL_TROPHY_CLASS.location_name("Slide Coliseum")
        options = _FakeOptions(WUMPA_PER_TRACK, BABY_T_PARK)
        with mock.patch.object(
                TRIAL_TROPHY_CLASS, "created_location_names",
                return_value=[slide_trophy]):
            names = WUMPA_CLASS.created_location_names(options)
            block = WUMPA_CLASS.wire_block(options)
        self.assertEqual(len(names), 18)
        self.assertIn(retail_location_name("Slide Coliseum"), names)
        self.assertIn(CUSTOM_LOCATION, names)
        self.assertNotIn(retail_location_name("Turbo Track"), names)
        self.assertIn(str(TRACK_LEVEL_IDS["Slide Coliseum"]),
                      block["retail_tracks"])
        self.assertIn(CUSTOM_ROLE, block["custom_destinations"])

    def test_an_eligible_custom_track_adds_exactly_one_location(self):
        names = WUMPA_CLASS.created_location_names(
            _FakeOptions(WUMPA_PER_TRACK, BABY_T_PARK))
        self.assertEqual(len(names), 17)
        self.assertEqual(names[-1], CUSTOM_LOCATION)

    def test_a_custom_track_adds_nothing_in_global_mode(self):
        self.assertEqual(
            WUMPA_CLASS.created_location_names(
                _FakeOptions(WUMPA_GLOBAL, BABY_T_PARK)),
            [WUMPA_TEN_LOCATION])


class TestCustomEligibility(unittest.TestCase):
    """All four of the specification's conditions, each shown load-bearing."""

    def test_the_baby_t_park_descriptor_is_eligible(self):
        roles = eligible_custom_roles(
            _FakeOptions(WUMPA_PER_TRACK, BABY_T_PARK))
        self.assertEqual([role for role, _l, _r, _e in roles], [CUSTOM_ROLE])

    def test_absent_from_the_yaml_is_ineligible(self):
        self.assertEqual(eligible_custom_roles(_FakeOptions(WUMPA_PER_TRACK)), [])

    def test_wumpa_collectible_false_is_ineligible(self):
        """The gate the whole capability exists for. A package that measured no
        route to ten fruit creates no location, whatever else it declares."""
        with _registry_measuring_no_wumpa():
            self.assertEqual(
                eligible_custom_roles(
                    _FakeOptions(WUMPA_PER_TRACK, _no_wumpa_collectible())),
                [])

    def test_wumpa_collectible_false_creates_no_location(self):
        with _registry_measuring_no_wumpa():
            names = WUMPA_CLASS.created_location_names(
                _FakeOptions(WUMPA_PER_TRACK, _no_wumpa_collectible()))
        self.assertEqual(len(names), 16)
        self.assertNotIn(CUSTOM_LOCATION, names)

    def test_it_is_not_inferred_from_the_broad_crates_flag(self):
        """`crates` stays true in the refused descriptor. If eligibility ever
        starts reading `crates`, this test is what catches it -- a track can
        carry crate instances with no route to ten fruit."""
        refused = _no_wumpa_collectible()
        self.assertTrue(refused["baby-t-park"]["flags"]["crates"])
        with _registry_measuring_no_wumpa():
            self.assertEqual(
                eligible_custom_roles(_FakeOptions(WUMPA_PER_TRACK, refused)),
                [])

    def test_a_capability_disagreeing_with_the_registry_fails_closed(self):
        """The first line of defence, ahead of eligibility: Alpha6 pins
        generation to one release-approved package identity, so a YAML claiming
        a different measured capability for that package is refused outright
        rather than quietly believed."""
        with self.assertRaises(OptionError) as caught:
            eligible_custom_roles(
                _FakeOptions(WUMPA_PER_TRACK, _no_wumpa_collectible()))
        self.assertIn("package registry", str(caught.exception))

    def test_a_missing_capability_is_a_descriptor_error_not_a_default(self):
        """The flag is REQUIRED. An entry that omits it fails validation rather
        than defaulting either way -- a silently defaulted capability is the
        plausible-but-wrong state the descriptor contract exists to prevent."""
        entry = copy.deepcopy(BABY_T_PARK_EXAMPLE)
        del entry["flags"][WUMPA_COLLECTIBLE_FLAG]
        with self.assertRaises(OptionError) as caught:
            eligible_custom_roles(
                _FakeOptions(WUMPA_PER_TRACK, {"baby-t-park": entry}))
        self.assertIn(WUMPA_COLLECTIBLE_FLAG, str(caught.exception))

    def test_only_roles_that_can_reach_ten_fruit_participate(self):
        """The fourth condition. Alpha6's one role runs a full multi-lap race so
        it qualifies; the table exists so a future role that cannot is refused at
        the apworld rather than discovered at runtime."""
        from ..wumpa_checks import ROLE_OFFERS_TEN_WUMPA
        self.assertTrue(ROLE_OFFERS_TEN_WUMPA[CUSTOM_ROLE])
        for role, _label, _region in CUSTOM_DESTINATION_ROLES:
            with self.subTest(role=role):
                self.assertIn(role, ROLE_OFFERS_TEN_WUMPA)


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

    def test_sixteen_locations_exist_and_the_global_one_does_not(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        for track in eligible_retail_tracks(self.world.options):
            with self.subTest(track=track):
                self.assertIn(retail_location_name(track), names)
        for track in ("Slide Coliseum", "Turbo Track"):
            self.assertNotIn(retail_location_name(track), names)
        self.assertNotIn(WUMPA_TEN_LOCATION, names)

    def test_each_location_is_parented_to_its_joint_wumpa_region(self):
        for track in eligible_retail_tracks(self.world.options):
            with self.subTest(track=track):
                location = self.multiworld.get_location(
                    retail_location_name(track), self.player)
                self.assertEqual(location.parent_region.name, f"{track}: Wumpa")

    def test_it_supplies_locations_rather_than_spending_them(self):
        items = [i for i in self.multiworld.itempool if i.player == self.player]
        locations = self.multiworld.get_unfilled_locations(self.player)
        self.assertEqual(len(items), len(locations))

    def test_the_wire_mapping_is_keyed_by_engine_level_id(self):
        block = self.world.fill_slot_data()["wumpa_checks"]
        self.assertEqual(block["mode"], WUMPA_PER_TRACK)
        self.assertEqual(block["global"], -1)
        self.assertEqual(
            block["retail_tracks"],
            {str(TRACK_LEVEL_IDS[track]): WUMPA_CLASS.retail_code(track)
             for track in eligible_retail_tracks(self.world.options)})
        self.assertEqual(block["custom_destinations"], {})

    def test_the_wire_omits_the_two_relic_only_destinations(self):
        mapping = self.world.fill_slot_data()["wumpa_checks"]["retail_tracks"]
        self.assertNotIn(str(TRACK_LEVEL_IDS["Slide Coliseum"]), mapping)
        self.assertNotIn(str(TRACK_LEVEL_IDS["Turbo Track"]), mapping)

    def test_the_scalar_is_emitted_alongside_the_block(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["ctr_options"]["wumpa_check"],
                         WUMPA_PER_TRACK)


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

    def test_no_cup_region_exit_reaches_a_track_region(self):
        cups = [r for r in self.multiworld.get_regions(self.player)
                if r.name.endswith(" Gem Cup")]
        self.assertTrue(cups, "the seed built no gem cup regions")
        track_regions = set(BOX_TRACKS)
        for cup in cups:
            for exit_ in cup.exits:
                target = exit_.connected_region
                with self.subTest(cup=cup.name, exit=exit_.name):
                    self.assertNotIn(
                        target.name if target else None, track_regions,
                        "a Gem Cup exit reaches a track region directly, which "
                        "would hand the cup that track's Wumpa check without "
                        "the track's own pad being accessible")

    def test_every_track_and_legging_cup_reaches_the_joint_wumpa_region(self):
        from ..gem_cup_legs import track_to_cups

        track_cups = track_to_cups(self.world.gem_cup_legs)
        for track in eligible_retail_tracks(self.world.options):
            with self.subTest(track=track):
                location = self.multiworld.get_location(
                    retail_location_name(track), self.player)
                region = location.parent_region
                self.assertEqual(region.name, f"{track}: Wumpa")
                sources = {entrance.parent_region.name
                           for entrance in region.entrances}
                self.assertIn(track, sources)
                self.assertEqual(sources - {track}, set(track_cups.get(track, [])))

    def test_joint_wumpa_region_contains_only_its_track_check(self):
        for track in eligible_retail_tracks(self.world.options):
            region = self.multiworld.get_region(f"{track}: Wumpa", self.player)
            with self.subTest(track=track):
                self.assertEqual([loc.name for loc in region.locations],
                                 [retail_location_name(track)])


class TestPerTrackWithCustomTrack(CTRTestBase):
    run_default_tests = False
    options = {
        "wumpa_check": "per_track",
        "include_gem_cups": True,
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
    }

    def test_the_custom_destination_location_exists(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        self.assertIn(CUSTOM_LOCATION, names)

    def test_it_lives_in_the_displaced_cup_region(self):
        location = self.multiworld.get_location(CUSTOM_LOCATION, self.player)
        self.assertEqual(location.parent_region.name, "Purple Gem Cup")

    def test_the_wire_carries_the_package_identity_and_the_capability(self):
        block = self.world.fill_slot_data()["wumpa_checks"]
        self.assertEqual(
            block["custom_destinations"],
            {CUSTOM_ROLE: {
                "code": WUMPA_CUSTOM_CODE_BASE,
                "package_uuid": BABY_T_PARK_EXAMPLE["package_uuid"],
                WUMPA_COLLECTIBLE_FLAG: True,
            }})

    def test_the_custom_code_is_never_a_retail_code(self):
        """A custom destination must never be served a displaced or host retail
        track's identity. The slot's code is outside the retail block entirely,
        which is what makes that impossible rather than merely unlikely."""
        block = self.world.fill_slot_data()["wumpa_checks"]
        code = block["custom_destinations"][CUSTOM_ROLE]["code"]
        self.assertEqual(code, WUMPA_CUSTOM_CODE_BASE)
        self.assertNotIn(code, set(block["retail_tracks"].values()))
        self.assertNotEqual(code, WUMPA_CODE_BASE)

    def test_the_retail_mapping_is_unchanged_by_the_custom_binding(self):
        block = self.world.fill_slot_data()["wumpa_checks"]
        self.assertEqual(len(block["retail_tracks"]), 16)


class TestPerTrackWithIneligibleCustomTrack(CTRTestBase):
    """A whole generated seed whose bound package measured no route to ten fruit.

    The registry patch is what makes this reachable: with the real Alpha6
    registry a descriptor like this is refused at option validation, so the seed
    below stands in for the release where a second package genuinely measures
    false. Everything else -- the 16 currently raceable retail checks, the cup,
    the fill -- is
    unaffected, which is the property that matters.
    """

    run_default_tests = False
    options = {
        "wumpa_check": "per_track",
        "include_gem_cups": True,
        "custom_tracks": _no_wumpa_collectible(),
    }

    def setUp(self):
        self._registry = _registry_measuring_no_wumpa()
        self._registry.start()
        self.addCleanup(self._registry.stop)
        super().setUp()

    def test_no_custom_location_is_created(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        self.assertNotIn(CUSTOM_LOCATION, names)

    def test_the_sixteen_retail_locations_are_unaffected(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        for track in eligible_retail_tracks(self.world.options):
            with self.subTest(track=track):
                self.assertIn(retail_location_name(track), names)

    def test_the_wire_carries_no_custom_destination(self):
        block = self.world.fill_slot_data()["wumpa_checks"]
        self.assertEqual(block["custom_destinations"], {})
        self.assertEqual(len(block["retail_tracks"]), 16)


class TestOffSeed(CTRTestBase):
    run_default_tests = False
    options = {"wumpa_check": "off"}

    def test_no_block_but_the_scalar_is_still_emitted(self):
        """Off-parity for the block, always-on for the scalar. Without the
        scalar a tracker would have to infer a three-way setting from block
        shape, which is the inference the convention exists to prevent."""
        slot_data = self.world.fill_slot_data()
        self.assertNotIn("wumpa_checks", slot_data)
        self.assertEqual(slot_data["ctr_options"]["wumpa_check"], WUMPA_OFF)

    def test_no_wumpa_location_is_created(self):
        names = {l.name for l in self.multiworld.get_locations(self.player)}
        self.assertNotIn(WUMPA_TEN_LOCATION, names)
        for track in BOX_TRACKS:
            with self.subTest(track=track):
                self.assertNotIn(retail_location_name(track), names)


# ---------------------------------------------------------------------------
# Universal Tracker


class _RestoreCase(unittest.TestCase):
    """Shared helper: run the world's own UT restore over a wire and rebuild.

    Uses the real `_ut_restore_options` on a real generated world, the same way
    the lettersanity and composable-goal UT gates do, so what is under test is
    the shipped restore path rather than a transcription of it.
    """

    def _restore(self, slot_data):
        world = setup_multiworld(ctrAPWorld, _UT_STEPS, seed=20260829,
                                 options={}).worlds[1]
        passthrough = {"warp_pad_unlock": {}, "podium_checks": {}}
        passthrough.update(slot_data)
        world._ut_restore_options(passthrough)
        return world.options


class TestUniversalTrackerReconstruction(_RestoreCase):
    """The spec's "reconstructs mode and code mapping byte-for-byte from slot
    data" gate. Rebuilt through the same `wire_block` the seed emitted, so the
    two can only agree if the restore recovered every input it reads."""

    def _round_trip(self, wire_options):
        block = WUMPA_CLASS.wire_block(wire_options)
        slot_data = {
            "ctr_options": {"wumpa_check": block["mode"]},
            "wumpa_checks": block,
        }
        if getattr(wire_options, "custom_tracks", None) is not None:
            from ..custom_tracks import (custom_tracks_to_wire,
                                         normalize_custom_tracks)
            slot_data["custom_tracks"] = custom_tracks_to_wire(
                normalize_custom_tracks(wire_options.custom_tracks.value))
        restored = self._restore(slot_data)
        return block, WUMPA_CLASS.wire_block(restored)

    def test_global_round_trips(self):
        original, rebuilt = self._round_trip(_FakeOptions(WUMPA_GLOBAL))
        self.assertEqual(original, rebuilt)

    def test_per_track_round_trips(self):
        original, rebuilt = self._round_trip(_FakeOptions(WUMPA_PER_TRACK))
        self.assertEqual(original, rebuilt)
        self.assertEqual(len(rebuilt["retail_tracks"]), 16)

    def test_per_track_with_a_custom_destination_round_trips(self):
        original, rebuilt = self._round_trip(
            _FakeOptions(WUMPA_PER_TRACK, copy.deepcopy(BABY_T_PARK)))
        self.assertEqual(original, rebuilt)
        self.assertEqual(list(rebuilt["custom_destinations"]), [CUSTOM_ROLE])

    def test_an_ineligible_custom_destination_round_trips_as_absent(self):
        with _registry_measuring_no_wumpa():
            original, rebuilt = self._round_trip(
                _FakeOptions(WUMPA_PER_TRACK, _no_wumpa_collectible()))
        self.assertEqual(original, rebuilt)
        self.assertEqual(rebuilt["custom_destinations"], {})

    def test_a_pre_widening_seed_restores_to_global(self):
        """No scalar, but a `wumpa_checks` block: that is any seed rolled before
        2026-08-29, and every one of them meant the single global check."""
        restored = self._restore({
            "ctr_options": {},
            "wumpa_checks": {"enabled": True, "locations": [WUMPA_CODE_BASE]},
        })
        self.assertEqual(int(restored.wumpa_check.value), WUMPA_GLOBAL)

    def test_a_seed_with_no_wumpa_anything_restores_to_off(self):
        restored = self._restore({"ctr_options": {}})
        self.assertEqual(int(restored.wumpa_check.value), WUMPA_OFF)
