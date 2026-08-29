"""Tests for the `custom_tracks` descriptor (Baby T Park event spike, rung 2b).

Ruled behaviour (Wayfinder session, 2026-08-28): the option is an early instance
of the self-describing `custom_tracks` descriptor -- id, per-file SHA-256s and
the track's measured capability flags -- and it DISPLACES the destination it
names. Option on, the Purple Gem Cup keeps its region, its single
"Purple Gem Cup: Gem" location and its four-Purple-CTR-Token pad rule, but it
no longer runs four retail leg tracks: it is one 7-lap race on the custom
track, and winning that race awards the Gem. Option off leaves the block absent
while Alpha6's unconditional schema 8 declaration remains.

These tests lock in the apworld half:

- descriptor validation: exactly one known entry, every field present and
  well-typed, a clean OptionError on everything else, reached identically from
  a rolled YAML and from a programmatically built world;
- normalization: defaults filled once, digests case-folded once;
- displacement: the displaced cup legs nothing in LOGIC while the complete
  five-cup table the wire serializes stays intact, and the podium-rung
  entrances follow;
- option-off neutrality and determinism: no RNG is consumed either way, and an
  option-off seed has no custom_tracks block or displaced destination;
- the `custom_tracks` slot_data block: shape, the unconditional schema 8 gate,
  and a round trip through AP's real wire pipeline;
- Universal Tracker: an option-on seed's displacement is pinned from the wire
  rather than re-read from the tracking player's own YAML.

The paired native candidate independently checks the same registry, manages and
hashes the local files, gates cup entry, and redirects the displaced cup.
"""

import copy
import json
import random
import unittest
from argparse import Namespace

from BaseClasses import CollectionState, MultiWorld
from Generate import get_seed_name
from NetUtils import convert_to_base_types
from Options import OptionError
from test.general import gen_steps
from worlds import AutoWorld
from worlds.AutoWorld import call_all

from ..custom_tracks import (
    BABY_T_PARK_EXAMPLE,
    CUSTOM_TRACKS_WIRE_VERSION,
    DEFAULT_HOST_LEVEL_ID,
    apply_displacement,
    custom_tracks_to_wire,
    displaced_cups,
    normalize_custom_tracks,
    reconstruct_custom_tracks_from_wire,
    resolve_custom_tracks,
    validate_custom_tracks,
)
from ..gem_cup_legs import load_vanilla_cup_legs
from ..podium import TROPHY_TRACKS
from . import CTRTestBase

#: The event descriptor as a YAML would carry it.
BABY_T_PARK = {"baby-t-park": copy.deepcopy(BABY_T_PARK_EXAMPLE)}

#: The four tracks the retail Purple Gem Cup legs (data/gem_cup_legs.json).
PURPLE_LEGS = ("Roo's Tubes", "Papu's Pyramid", "Dragon Mines", "Hot Air Skyway")

#: Any fixed seed; nothing here depends on which one, only on it being equal
#: across the A/B pairs that prove neutrality.
SEED = 20260828


def _entry(**overrides):
    """The event descriptor with one or more entry fields replaced. A key set
    to `None` is REMOVED, which is how the missing-key cases are written."""
    entry = copy.deepcopy(BABY_T_PARK_EXAMPLE)
    for key, value in overrides.items():
        if value is None:
            entry.pop(key, None)
        else:
            entry[key] = value
    return {"baby-t-park": entry}


def _flags(**overrides):
    """The event descriptor with one or more measured FLAGS replaced or, for
    a `None` value, removed."""
    entry = copy.deepcopy(BABY_T_PARK_EXAMPLE)
    for key, value in overrides.items():
        if value is None:
            entry["flags"].pop(key, None)
        else:
            entry["flags"][key] = value
    return {"baby-t-park": entry}


class TestDescriptorValidation(unittest.TestCase):
    """Every malformed descriptor is a clean OptionError naming the field."""

    def test_absent_and_empty_are_the_option_being_off(self):
        for value in ({}, None):
            with self.subTest(value=value):
                self.assertEqual(normalize_custom_tracks(value or {}), {})

    def test_the_event_descriptor_is_valid(self):
        validate_custom_tracks(BABY_T_PARK)

    def test_two_entries_are_refused(self):
        two = dict(BABY_T_PARK)
        two["some-other-track"] = copy.deepcopy(BABY_T_PARK_EXAMPLE)
        with self.assertRaises(OptionError) as ctx:
            validate_custom_tracks(two)
        self.assertIn("exactly one custom track", str(ctx.exception))

    def test_unknown_track_id_is_refused(self):
        with self.assertRaises(OptionError) as ctx:
            validate_custom_tracks(
                {"baby-t-parkk": copy.deepcopy(BABY_T_PARK_EXAMPLE)})
        self.assertIn("unknown track id", str(ctx.exception))

    def test_non_mapping_descriptor_is_refused(self):
        for bad in ([], "baby-t-park", 7):
            with self.subTest(bad=bad):
                with self.assertRaises(OptionError):
                    validate_custom_tracks(bad)

    def test_missing_required_entry_key_is_refused(self):
        for key in ("package_uuid", "package_version",
                    "minimum_client_version", "minimum_apworld_version",
                    "lev_sha256", "vrm_sha256", "navigation", "laps",
                    "replaces", "flags"):
            with self.subTest(key=key):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(**{key: None}))
                self.assertIn(key, str(ctx.exception))
                self.assertIn("missing required key", str(ctx.exception))

    def test_unknown_entry_key_is_refused(self):
        with self.assertRaises(OptionError) as ctx:
            validate_custom_tracks(_entry(lap=7))
        self.assertIn("unknown key", str(ctx.exception))

    def test_malformed_digests_are_refused(self):
        for bad in ("", "deadbeef", "9" * 63, "9" * 65, "z" * 64, 96,
                    ["9" * 64]):
            for key in ("lev_sha256", "vrm_sha256"):
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(OptionError) as ctx:
                        validate_custom_tracks(_entry(**{key: bad}))
                    self.assertIn("64 hexadecimal", str(ctx.exception))

    def test_digest_case_is_accepted_and_folded(self):
        upper = BABY_T_PARK_EXAMPLE["lev_sha256"].upper()
        resolved = normalize_custom_tracks(_entry(lev_sha256=upper))
        self.assertEqual(resolved["baby-t-park"]["lev_sha256"],
                         BABY_T_PARK_EXAMPLE["lev_sha256"])

    def test_package_and_navigation_identity_shape_is_strict(self):
        cases = (
            ("package_uuid", "not-a-uuid", "canonical UUID"),
            ("package_version", "", "version string"),
            ("minimum_client_version", 'alpha6"bad', "version string"),
            ("minimum_apworld_version", 6, "version string"),
            ("navigation", {}, "exactly 'uuid' and 'revision'"),
            ("navigation", {"uuid": "bad", "revision": 1},
             "canonical UUID"),
            ("navigation", {
                "uuid": BABY_T_PARK_EXAMPLE["navigation"]["uuid"],
                "revision": 0}, "positive whole number"),
        )
        for key, bad, expected in cases:
            with self.subTest(key=key, bad=bad):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(**{key: bad}))
                self.assertIn(expected, str(ctx.exception))

    def test_alpha6_registry_rejects_well_formed_identity_drift(self):
        cases = (
            ("package_uuid", "00000000-0000-4000-8000-000000000000"),
            ("package_version", "1.0.1"),
            ("minimum_client_version", "0.2.0-alpha7"),
            ("minimum_apworld_version", "0.2.0-alpha7"),
            ("lev_sha256", "0" * 64),
            ("vrm_sha256", "0" * 64),
            ("navigation", {
                "uuid": BABY_T_PARK_EXAMPLE["navigation"]["uuid"],
                "revision": 2}),
        )
        for key, bad in cases:
            with self.subTest(key=key):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(**{key: bad}))
                self.assertIn("Alpha6 package registry", str(ctx.exception))

    def test_alpha6_registry_rejects_capability_drift(self):
        for key, bad in (("crates", False), ("minimap", True),
                         ("spawns", 7), ("checkpoints", 34)):
            with self.subTest(key=key):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_flags(**{key: bad}))
                self.assertIn("Alpha6 package registry", str(ctx.exception))

    def test_lap_count_out_of_range_is_refused(self):
        for bad in (0, 8, -1, 7.0, "7", True):
            with self.subTest(bad=bad):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(laps=bad))
                self.assertIn("'laps'", str(ctx.exception))

    def test_only_the_registry_lap_count_is_accepted(self):
        self.assertEqual(
            normalize_custom_tracks(_entry(laps=7))["baby-t-park"]["laps"],
            7)
        for laps in range(1, 7):
            with self.subTest(laps=laps):
                with self.assertRaises(OptionError) as ctx:
                    normalize_custom_tracks(_entry(laps=laps))
                self.assertIn("package registry", str(ctx.exception))

    def test_unsupported_replaces_target_is_refused(self):
        for bad in ("red_gem_cup", "purple gem cup", "purple_gem_cup ", 104,
                    None):
            with self.subTest(bad=bad):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(
                        _entry(replaces=bad) if bad is not None
                        else _entry(replaces="oxide_station"))
                self.assertIn("'replaces'", str(ctx.exception))

    def test_host_level_id_out_of_range_is_refused(self):
        for bad in (-1, 18, 104, "6", 6.0, True):
            with self.subTest(bad=bad):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(host_level_id=bad))
                self.assertIn("'host_level_id'", str(ctx.exception))

    def test_host_level_id_defaults_and_is_overridable(self):
        self.assertEqual(
            normalize_custom_tracks(BABY_T_PARK)["baby-t-park"]
            ["host_level_id"], DEFAULT_HOST_LEVEL_ID)
        self.assertEqual(
            normalize_custom_tracks(_entry(host_level_id=17))["baby-t-park"]
            ["host_level_id"], 17)

    def test_boxes_default_off_and_alpha6_refuses_on(self):
        self.assertIs(
            normalize_custom_tracks(BABY_T_PARK)["baby-t-park"]["boxes"], False)
        self.assertIs(
            normalize_custom_tracks(_entry(boxes=False))["baby-t-park"]
            ["boxes"], False)
        for bad in (True, 1):
            with self.subTest(bad=bad):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_entry(boxes=bad))
                self.assertIn("boxes", str(ctx.exception))

    def test_every_measured_flag_is_required(self):
        for key in ("crates", "ctr_letters", "relic_crates", "ai_nav",
                    "minimap", "ghosts", "spawns", "checkpoints"):
            with self.subTest(key=key):
                with self.assertRaises(OptionError) as ctx:
                    validate_custom_tracks(_flags(**{key: None}))
                self.assertIn("missing measured flag", str(ctx.exception))
                self.assertIn(key, str(ctx.exception))

    def test_unknown_flag_is_refused(self):
        with self.assertRaises(OptionError) as ctx:
            validate_custom_tracks(_flags(music=True))
        self.assertIn("unknown flag", str(ctx.exception))

    def test_boolean_flags_reject_non_booleans(self):
        for key in ("crates", "ctr_letters", "relic_crates", "ai_nav",
                    "minimap", "ghosts"):
            for bad in (1, 0, "true", []):
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(OptionError) as ctx:
                        validate_custom_tracks(_flags(**{key: bad}))
                    self.assertIn(f"flag '{key}'", str(ctx.exception))

    def test_counted_flags_reject_out_of_range_and_non_integers(self):
        for key, bad_values in (("spawns", (0, 9, -1, "8", 8.0, True)),
                                ("checkpoints", (0, 256, -1, "35", 35.0, True))):
            for bad in bad_values:
                with self.subTest(key=key, bad=bad):
                    with self.assertRaises(OptionError) as ctx:
                        validate_custom_tracks(_flags(**{key: bad}))
                    self.assertIn(f"flag '{key}'", str(ctx.exception))

    def test_flags_must_be_a_mapping(self):
        with self.assertRaises(OptionError) as ctx:
            validate_custom_tracks(_entry(flags=["crates"]))
        self.assertIn("'flags'", str(ctx.exception))

    def test_normalization_does_not_mutate_the_input(self):
        given = copy.deepcopy(BABY_T_PARK)
        normalize_custom_tracks(given)
        self.assertEqual(given, BABY_T_PARK)


class TestOptionSurface(unittest.TestCase):
    """The option class reaches the same validator the world does."""

    def test_option_verify_keys_raises_on_a_malformed_descriptor(self):
        from ..Options import CustomTracks
        with self.assertRaises(OptionError):
            CustomTracks(_entry(laps=99)).verify_keys()

    def test_option_default_is_off(self):
        from ..Options import CustomTracks
        self.assertEqual(CustomTracks.default, {})
        self.assertFalse(CustomTracks.supports_weighting)

    def test_resolve_never_touches_the_seed_rng(self):
        # Turning this option on must not move the RNG stream, so resolution
        # is asked for on a world whose `random` explodes on any access.
        class _Exploding:
            def __getattr__(self, name):
                raise AssertionError(
                    f"custom-track resolution consumed RNG (random.{name})")

        class _World:
            random = _Exploding()

            class options:
                class custom_tracks:
                    value = copy.deepcopy(BABY_T_PARK)

        self.assertEqual(set(resolve_custom_tracks(_World())), {"baby-t-park"})


class TestDisplacement(unittest.TestCase):
    """The pure displacement rule, out of world."""

    def test_no_descriptor_leaves_the_table_alone(self):
        table = load_vanilla_cup_legs()
        self.assertEqual(apply_displacement(table, {}), table)

    def test_the_named_cup_is_emptied_and_no_other(self):
        table = load_vanilla_cup_legs()
        logic = apply_displacement(table, normalize_custom_tracks(BABY_T_PARK))
        self.assertEqual(logic["Purple Gem Cup"], [])
        for cup in ("Red Gem Cup", "Green Gem Cup", "Blue Gem Cup",
                    "Yellow Gem Cup"):
            with self.subTest(cup=cup):
                self.assertEqual(logic[cup], table[cup])

    def test_the_complete_table_is_not_mutated_or_aliased(self):
        table = load_vanilla_cup_legs()
        before = copy.deepcopy(table)
        logic = apply_displacement(table, normalize_custom_tracks(BABY_T_PARK))
        self.assertEqual(table, before)
        logic["Red Gem Cup"].append("Crash Cove")
        self.assertEqual(table, before)

    def test_displaced_cups_names_the_ruled_binding(self):
        self.assertEqual(displaced_cups(normalize_custom_tracks(BABY_T_PARK)),
                         {"Purple Gem Cup": "baby-t-park"})


class TestWireBlock(unittest.TestCase):
    """The `custom_tracks` slot_data block, out of world."""

    def test_shape(self):
        wire = json.loads(json.dumps(
            custom_tracks_to_wire(normalize_custom_tracks(BABY_T_PARK))))
        self.assertIs(wire["enabled"], True)
        self.assertEqual(wire["version"], CUSTOM_TRACKS_WIRE_VERSION)
        self.assertEqual(len(wire["tracks"]), 1)
        entry, = wire["tracks"]
        self.assertEqual(entry["id"], "baby-t-park")
        self.assertEqual(entry["package_uuid"],
                         BABY_T_PARK_EXAMPLE["package_uuid"])
        self.assertEqual(entry["package_version"], "1.0.0")
        self.assertEqual(entry["navigation"],
                         BABY_T_PARK_EXAMPLE["navigation"])
        self.assertEqual(entry["lev_sha256"],
                         BABY_T_PARK_EXAMPLE["lev_sha256"])
        self.assertEqual(entry["vrm_sha256"],
                         BABY_T_PARK_EXAMPLE["vrm_sha256"])
        self.assertEqual(entry["laps"], 7)
        self.assertEqual(entry["host_level_id"], DEFAULT_HOST_LEVEL_ID)
        # The cup travels as a LevelID, the currency warp_pad_map,
        # warp_pad_unlock and gem_cup_legs already use.
        self.assertEqual(entry["replaces_cup_level_id"], 104)
        self.assertIs(entry["boxes"], False)
        self.assertEqual(entry["flags"], BABY_T_PARK_EXAMPLE["flags"])

    def test_round_trips_back_to_the_descriptor(self):
        descriptor = normalize_custom_tracks(BABY_T_PARK)
        wire = json.loads(json.dumps(custom_tracks_to_wire(descriptor)))
        self.assertEqual(
            reconstruct_custom_tracks_from_wire({"custom_tracks": wire}),
            descriptor)

    def test_round_trips_through_aps_real_wire_pipeline(self):
        # AP runs slot_data through NetUtils.convert_to_base_types before
        # pickling it into multidata, which turns every list into a tuple.
        # The gem_cup_legs reconstructor shipped broken on exactly this and a
        # json round trip could never show it, because JSON has no tuples.
        descriptor = normalize_custom_tracks(BABY_T_PARK)
        wire = convert_to_base_types(custom_tracks_to_wire(descriptor))
        self.assertIsInstance(wire["tracks"], tuple,
                              "test fixture no longer reproduces the real "
                              "wire shape -- convert_to_base_types changed")
        self.assertEqual(
            reconstruct_custom_tracks_from_wire({"custom_tracks": wire}),
            descriptor)

    def test_absent_block_reconstructs_to_off_silently(self):
        with self.assertNoLogs("worlds.ctr.custom_tracks", level="WARNING"):
            self.assertEqual(reconstruct_custom_tracks_from_wire({}), {})

    def test_unreadable_block_reconstructs_to_off_with_a_warning(self):
        good = json.loads(json.dumps(
            custom_tracks_to_wire(normalize_custom_tracks(BABY_T_PARK))))

        def _mangled(**changes):
            block = copy.deepcopy(good)
            block.update(changes)
            return block

        def _entry_mangled(**changes):
            block = copy.deepcopy(good)
            block["tracks"][0].update(changes)
            return block

        cases = (
            [], "baby-t-park", 7,
            _mangled(version=CUSTOM_TRACKS_WIRE_VERSION + 1),
            _mangled(version=None),
            _mangled(tracks=[]),
            _mangled(tracks=[copy.deepcopy(good["tracks"][0])] * 2),
            _mangled(tracks="baby-t-park"),
            _mangled(tracks=["baby-t-park"]),
            _entry_mangled(id="not-a-track"),
            _entry_mangled(package_uuid="00000000-0000-4000-8000-000000000000"),
            _entry_mangled(package_version="1.0.1"),
            _entry_mangled(minimum_client_version="0.2.0-alpha7"),
            _entry_mangled(navigation={
                "uuid": BABY_T_PARK_EXAMPLE["navigation"]["uuid"],
                "revision": 2}),
            _entry_mangled(replaces_cup_level_id=100),
            _entry_mangled(flags=None),
            _entry_mangled(laps=99),
            _entry_mangled(lev_sha256="deadbeef"),
            _entry_mangled(host_level_id=None),
        )
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertLogs("worlds.ctr.custom_tracks",
                                     level="WARNING"):
                    self.assertEqual(
                        reconstruct_custom_tracks_from_wire(
                            {"custom_tracks": bad}), {})


class TestOptionOffNeutrality(CTRTestBase):
    """Option off: the seed a build without this module would produce."""

    run_default_tests = False
    options = {
        "podium_placement_checks": True,
        "include_gem_cups": True,
    }

    def test_world_carries_no_descriptor(self):
        self.assertEqual(self.world.custom_tracks, {})

    def test_logic_map_and_table_are_the_same_vanilla_content(self):
        self.assertEqual(self.world.gem_cup_legs, load_vanilla_cup_legs())
        self.assertEqual(self.world.gem_cup_legs_table, load_vanilla_cup_legs())

    def test_schema_is_8_and_no_block_is_emitted(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertNotIn("custom_tracks", slot_data)
        self.assertEqual(slot_data["schema_version"], 8)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 8)

    def test_purple_still_legs_its_four_retail_tracks(self):
        for track in PURPLE_LEGS:
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertIn("Purple Gem Cup",
                              {e.parent_region.name for e in podium.entrances})


class TestOptionOffIsIdenticalToNoDescriptor(unittest.TestCase):
    """The determinism half of neutrality: with the option off, an explicit
    empty descriptor and no descriptor at all produce the same seed, byte for
    byte, including the RNG-dependent parts.

    This is the in-repo half of the neutrality gate. The other half -- that
    the same seed also matches a worktree WITHOUT this module -- is an A/B run
    against `main`, recorded in the branch's build notes; a test cannot import
    two versions of its own world.
    """

    game = "Crash Team Racing"
    player = 1

    def _generate(self, seed, options):
        multiworld = MultiWorld(1)
        multiworld.game[self.player] = self.game
        multiworld.player_name = {self.player: "Tester"}
        multiworld.set_seed(seed)
        random.seed(multiworld.seed)
        multiworld.seed_name = get_seed_name(random)
        args = Namespace()
        world_type = AutoWorld.AutoWorldRegister.world_types[self.game]
        for name, option in world_type.options_dataclass.type_hints.items():
            setattr(args, name,
                    {self.player: option.from_any(
                        options.get(name, option.default))})
        multiworld.set_options(args)
        multiworld.state = CollectionState(multiworld)
        for step in gen_steps:
            call_all(multiworld, step)
        world = multiworld.worlds[self.player]
        placements = sorted(
            (loc.name, loc.item.name if loc.item else None,
             loc.item.player if loc.item else None)
            for loc in multiworld.get_locations(self.player))
        return json.dumps(world.fill_slot_data(), sort_keys=True), placements

    def test_empty_descriptor_matches_an_absent_one(self):
        base = {"podium_placement_checks": True, "include_gem_cups": True,
                "randomize_gem_cup_tracks": True}
        absent_wire, absent_placements = self._generate(SEED, base)
        empty_wire, empty_placements = self._generate(
            SEED, {**base, "custom_tracks": {}})
        self.assertEqual(absent_wire, empty_wire)
        self.assertEqual(absent_placements, empty_placements)

    def test_turning_the_option_on_consumes_no_rng(self):
        # Displacement is a pure filter over an already-drawn map, so the
        # world RNG must be in the identical state after every generation
        # step whether the option is on or off. Measured per step rather than
        # once at the end: an off-by-one draw that cancelled out later would
        # pass an end-state check and still mean the graph was built from a
        # different stream. Only the fill step legitimately diverges, which is
        # why the trace stops before it -- a different logic graph really does
        # make fill take different decisions.
        base = {"podium_placement_checks": True, "include_gem_cups": True,
                "randomize_gem_cup_tracks": True}
        off = self._rng_trace(SEED, base)
        on = self._rng_trace(
            SEED, {**base, "custom_tracks": copy.deepcopy(BABY_T_PARK)})
        self.assertEqual(off, on)

    def _rng_trace(self, seed, options):
        multiworld = MultiWorld(1)
        multiworld.game[self.player] = self.game
        multiworld.player_name = {self.player: "Tester"}
        multiworld.set_seed(seed)
        random.seed(multiworld.seed)
        multiworld.seed_name = get_seed_name(random)
        args = Namespace()
        world_type = AutoWorld.AutoWorldRegister.world_types[self.game]
        for name, option in world_type.options_dataclass.type_hints.items():
            setattr(args, name,
                    {self.player: option.from_any(
                        options.get(name, option.default))})
        multiworld.set_options(args)
        multiworld.state = CollectionState(multiworld)
        trace = []
        for step in gen_steps:
            call_all(multiworld, step)
            trace.append(
                (step, repr(multiworld.worlds[self.player].random.getstate())))
        return trace

    def test_the_same_seed_twice_is_the_same_seed(self):
        # Guards the comparison above: if generation were not deterministic
        # for a fixed seed in the first place, the equality it asserts would
        # be meaningless.
        base = {"podium_placement_checks": True, "include_gem_cups": True,
                "randomize_gem_cup_tracks": True,
                "custom_tracks": copy.deepcopy(BABY_T_PARK)}
        first = self._generate(SEED, base)
        second = self._generate(SEED, base)
        self.assertEqual(first, second)


class TestDisplacementIntegration(CTRTestBase):
    """Option on at full generation: the graph, the wire and the schema."""

    run_default_tests = False
    auto_construct = False
    options = {
        "podium_placement_checks": True,
        "include_gem_cups": True,
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
    }

    def setUp(self):
        self.world_setup(seed=SEED)

    def test_descriptor_is_resolved_onto_the_world(self):
        self.assertEqual(self.world.custom_tracks,
                         normalize_custom_tracks(BABY_T_PARK))

    def test_purple_legs_nothing_in_logic_but_its_table_row_survives(self):
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"], [])
        self.assertEqual(self.world.gem_cup_legs_table["Purple Gem Cup"],
                         list(PURPLE_LEGS))

    def test_the_cup_keeps_its_identity_and_its_one_reward(self):
        # The ruling displaces the DESTINATION, not the cup: the region and
        # its single Gem check are untouched. The pad RULE is checked
        # separately, in TestDisplacedCupKeepsItsVanillaPadRule, where the
        # vanilla unlock mode makes the rule a fixed, readable requirement
        # instead of this seed's randomized draw.
        region = self.multiworld.get_region("Purple Gem Cup", self.player)
        self.assertEqual([loc.name for loc in region.locations],
                         ["Purple Gem Cup: Gem"])
        self.assertEqual(
            len([e for e in self.multiworld.get_entrances(self.player)
                 if e.connected_region is region]), 1)

    def test_no_podium_region_is_entered_from_the_displaced_cup(self):
        for track in TROPHY_TRACKS:
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertNotIn(
                    "Purple Gem Cup",
                    {e.parent_region.name for e in podium.entrances})

    def test_the_four_retail_purple_legs_keep_every_other_path(self):
        # Displacement removes the Purple branch and nothing else: each of the
        # four retail Purple legs keeps its own track region, and the two that
        # another cup also legs keep that cup too.
        expected = {
            "Roo's Tubes": {"Roo's Tubes", "Green Gem Cup"},
            "Papu's Pyramid": {"Papu's Pyramid", "Red Gem Cup"},
            "Dragon Mines": {"Dragon Mines", "Blue Gem Cup"},
            "Hot Air Skyway": {"Hot Air Skyway", "Yellow Gem Cup"},
        }
        for track, sources in expected.items():
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertEqual(
                    {e.parent_region.name for e in podium.entrances}, sources)

    def test_schema_bumps_to_8_and_the_block_is_emitted(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(slot_data["schema_version"], 8)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 8)
        self.assertEqual(
            slot_data["custom_tracks"],
            json.loads(json.dumps(custom_tracks_to_wire(
                normalize_custom_tracks(BABY_T_PARK)))))

    def test_the_gem_cup_legs_block_is_absent_without_leg_randomization(self):
        # Displacement is not leg randomization: with randomize_gem_cup_tracks
        # off there is still no gem_cup_legs block, and native keeps its
        # vanilla table -- whose Purple row it simply never reads, because the
        # custom_tracks block told it that cup was handed over.
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertNotIn("gem_cup_legs", slot_data)


class TestDisplacedCupKeepsItsVanillaPadRule(CTRTestBase):
    """Under the vanilla unlock mode the displaced cup's pad still asks for
    exactly what it always asked for: four Purple CTR Tokens. Displacement
    changes what is behind the pad, never what opens it."""

    run_default_tests = False
    auto_construct = False
    options = {
        "include_gem_cups": True,
        "warppad_unlock_requirements": "vanilla",
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
    }

    def setUp(self):
        self.world_setup(seed=SEED)

    def test_four_purple_tokens_still_open_the_cup(self):
        region = self.multiworld.get_region("Purple Gem Cup", self.player)
        entrance, = [e for e in self.multiworld.get_entrances(self.player)
                     if e.connected_region is region]
        state = CollectionState(self.multiworld)
        for _ in range(3):
            state.collect(self.world.create_item("Purple CTR Token"), True)
        self.assertFalse(entrance.access_rule(state))
        state.collect(self.world.create_item("Purple CTR Token"), True)
        self.assertTrue(entrance.access_rule(state))


class TestDisplacementWithRandomizedLegs(CTRTestBase):
    """Displacement composes with randomized cup legs: the wire keeps a
    complete five-cup table while the displaced cup legs nothing in logic."""

    run_default_tests = False
    auto_construct = False
    options = {
        "podium_placement_checks": True,
        "include_gem_cups": True,
        "randomize_gem_cup_tracks": True,
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
    }

    def setUp(self):
        self.world_setup(seed=SEED)

    def test_the_wire_table_is_still_complete(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        wire = slot_data["gem_cup_legs"]
        self.assertEqual(set(wire), {"100", "101", "102", "103", "104"})
        for cup, legs in wire.items():
            with self.subTest(cup=cup):
                self.assertEqual(len(legs), 4)
                self.assertTrue(all(type(lid) is int and 0 <= lid <= 15
                                    for lid in legs))

    def test_the_displaced_cup_still_legs_nothing_in_logic(self):
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"], [])
        self.assertEqual(len(self.world.gem_cup_legs_table["Purple Gem Cup"]), 4)

    def test_the_draw_is_still_made_so_the_rng_stream_does_not_move(self):
        # The Purple row is drawn and then ignored by logic. Dropping the draw
        # would shift every later use of world.random and change the seed.
        legs = self.world.gem_cup_legs_table
        self.assertEqual(sum(len(v) for v in legs.values()), 20)


class TestUTPinsTheDisplacement(CTRTestBase):
    """Universal Tracker re-generation must take the displacement from the
    connected seed's slot_data, not from the tracking player's own YAML."""

    run_default_tests = False
    auto_construct = False
    options = TestDisplacementIntegration.options

    def _setup_with_passthrough(self, seed, passthrough, options=None):
        self.multiworld = MultiWorld(1)
        self.multiworld.game[self.player] = self.game
        self.multiworld.player_name = {self.player: "Tester"}
        self.multiworld.set_seed(seed)
        random.seed(self.multiworld.seed)
        self.multiworld.seed_name = get_seed_name(random)
        args = Namespace()
        world_type = AutoWorld.AutoWorldRegister.world_types[self.game]
        chosen = self.options if options is None else options
        for name, option in world_type.options_dataclass.type_hints.items():
            setattr(args, name,
                    {1: option.from_any(chosen.get(name, option.default))})
        self.multiworld.set_options(args)
        self.multiworld.state = CollectionState(self.multiworld)
        self.multiworld.re_gen_passthrough = {self.game: passthrough}
        self.world = self.multiworld.worlds[self.player]
        for step in gen_steps:
            call_all(self.multiworld, step)

    def test_regen_pins_the_seeds_displacement(self):
        self.world_setup(seed=SEED)
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))

        self._setup_with_passthrough(SEED, slot_data)
        self.assertEqual(self.world.custom_tracks,
                         normalize_custom_tracks(BABY_T_PARK))
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"], [])
        ut_slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(ut_slot_data["custom_tracks"],
                         slot_data["custom_tracks"])
        self.assertEqual(ut_slot_data["schema_version"], 8)

    def test_regen_pins_it_through_aps_real_wire_pipeline(self):
        self.world_setup(seed=SEED)
        slot_data = convert_to_base_types(self.world.fill_slot_data())
        self.assertIsInstance(slot_data["custom_tracks"]["tracks"], tuple,
                              "test fixture no longer reproduces the real "
                              "wire shape -- convert_to_base_types changed")

        self._setup_with_passthrough(SEED, slot_data)
        self.assertEqual(self.world.custom_tracks,
                         normalize_custom_tracks(BABY_T_PARK))
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"], [])

    def test_the_seed_beats_the_tracking_players_own_yaml(self):
        # The tracking player's YAML has no custom track; the connected seed
        # does. The re-generated graph must be the seed's.
        self.world_setup(seed=SEED)
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))

        self._setup_with_passthrough(
            SEED, slot_data,
            options={"podium_placement_checks": True, "include_gem_cups": True})
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"], [])
        for track in PURPLE_LEGS:
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertNotIn(
                    "Purple Gem Cup",
                    {e.parent_region.name for e in podium.entrances})

    def test_a_pre_custom_tracks_seed_regenerates_without_displacement(self):
        # The other direction: the tracking player's YAML HAS a custom track
        # and the connected seed does not. The seed wins, and the retail
        # Purple cup legs are back.
        self.world_setup(seed=SEED)
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        del slot_data["custom_tracks"]
        slot_data["schema_version"] = 7
        slot_data["ctr_options"]["schema_version"] = 7

        self._setup_with_passthrough(SEED, slot_data)
        self.assertEqual(self.world.custom_tracks, {})
        self.assertEqual(self.world.options.custom_tracks.value, {})
        self.assertEqual(self.world.gem_cup_legs["Purple Gem Cup"],
                         list(PURPLE_LEGS))


class TestDisplacedSeedIsSolvable(CTRTestBase):
    """The default AP world tests (fill, empty-state and all-state
    reachability) on a displaced seed, with full accessibility -- the claim
    that removing a cup's legs never orphans a podium rung."""

    options = {
        "podium_placement_checks": True,
        "podium_held_fifth_rung": True,
        "podium_any_position_rung": True,
        "include_gem_cups": True,
        "custom_tracks": copy.deepcopy(BABY_T_PARK),
        "accessibility": "full",
    }
