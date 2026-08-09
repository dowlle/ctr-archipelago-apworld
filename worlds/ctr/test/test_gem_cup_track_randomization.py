"""Tests for issue #166: randomized Gem Cup tracks (apworld + UT half).

Ruled behaviour (2026-08-07 wayfarer ruling, R-K dossier section 8): exactly
two states -- vanilla (default), or completely random, every cup leg drawn
independently WITH REPLACEMENT from the 16 trophy-race tracks (LevelIDs
0..15). Repeats are allowed, a track may be absent from every cup, and the
Purple Gem Cup keeps no special boss-track handling. Slide Coliseum / Turbo
Track (16/17) are never drawn (the ruled pool clamp).

Wire shape: a top-level `gem_cup_legs` block {"<cupLevelID 100..104>":
[trackLevelID x4]}, emitted ONLY when the option is on. The `schema_version`
BUMP to 7 is unconditional (Q28 ruling, #152 dossier: "ALWAYS BUMP...no
conditional emission"), every 0.2.0 seed declares 7 whether or not this
option is on; only the block's presence is conditional. An old native on a
leg-randomized seed would silently load vanilla legs while the logic follows
the shuffled map -- the golden-rule desync class of the v3 cup destination
bump -- so the #8 newer-schema warning fires on every 0.2.0 seed for a
pre-0.2.0 client, honestly, per the ruling.

Native parsing, cup loading and the native verifier are a separate package;
these tests lock in the apworld half:

- vanilla parity: option off reproduces the static table exactly, draws no
  RNG, emits no key, and schema is still 7 (the unconditional bump);
- determinism: same seed, same map;
- the draw's ruled properties: repeats, all-same-track, absent tracks,
  Purple without boss tracks, pool clamped to the 16 trophy tracks;
- slot_data round-trip of the wire block;
- regions/rules follow the generated map (podium-region cup entrances);
- Universal Tracker re-generation pins the seed's map instead of re-drawing.
"""

import json
import random
import unittest
from argparse import Namespace
from types import SimpleNamespace

from BaseClasses import CollectionState, MultiWorld
from Generate import get_seed_name
from NetUtils import convert_to_base_types
from test.general import gen_steps
from worlds import AutoWorld
from worlds.AutoWorld import call_all

from ..gem_cup_legs import (
    CUP_LEVEL_IDS,
    cup_legs_to_wire,
    load_vanilla_cup_legs,
    reconstruct_gem_cup_legs_from_wire,
    resolve_gem_cup_legs,
    track_level_ids,
    track_to_cups,
)
from ..podium import TROPHY_TRACKS
from . import CTRTestBase

# The four tracks that host a boss race (native characterID_Boss cross-
# reference, R-K dossier section 1.2): Dragon Mines 1 (Komodo Joe),
# Papu's Pyramid 5 (Papu Papu), Roo's Tubes 6 (Ripper Roo),
# Hot Air Skyway 7 (Pinstripe). Vanilla Purple runs exactly these.
BOSS_TRACK_IDS = {1, 5, 6, 7}

CUP_NAMES = [cup for cup, _lid in CUP_LEVEL_IDS]

# Fixed generation seed for the integration classes. Verified on this
# apworld: its drawn map repeats tracks inside two cups (Green legs Hot Air
# Skyway twice, Purple legs Mystery Caves twice) and leaves Coco Park,
# Dingo Canyon, Polar Pass and Cortex Castle out of every cup, so one seed
# exercises the repeat and absent-track cases at full-generation level.
LEGS_SEED = 424242

TRACK_IDS = track_level_ids()  # name -> LevelID, from warp_pad_ids.json
ID_TRACKS = {lid: name for name, lid in TRACK_IDS.items()}


class _ScriptedRNG:
    """randrange pops scripted values, so the degenerate draws (all four
    legs identical, Purple dodging every boss track) are proven directly
    instead of trusted to a Mersenne sequence."""

    def __init__(self, values):
        self._values = list(values)

    def randrange(self, n):
        assert self._values, "script exhausted"
        value = self._values.pop(0)
        assert 0 <= value < n, f"scripted value {value} out of range"
        return value


def _stub_world(rng, enabled=True):
    """The minimal world surface resolve_gem_cup_legs reads."""
    return SimpleNamespace(
        options=SimpleNamespace(
            randomize_gem_cup_tracks=SimpleNamespace(value=int(enabled))),
        random=rng)


class TestCupLegDataParity(unittest.TestCase):
    """The module constants can never drift from the data files they index."""

    def test_cup_level_ids_match_warp_pad_ids(self):
        import pkgutil
        pads = json.loads(pkgutil.get_data(
            "worlds.ctr", "data/warp_pad_ids.json").decode("utf-8"))["pads"]
        for cup, lid in CUP_LEVEL_IDS:
            pad = f"{cup.replace(' Gem Cup', '')} Cup Warp Pad"
            self.assertIn(pad, pads)
            self.assertEqual(pads[pad]["level_id"], lid)
            self.assertEqual(pads[pad]["kind"], "cup")

    def test_cup_order_matches_vanilla_table(self):
        self.assertEqual(list(load_vanilla_cup_legs()), CUP_NAMES)

    def test_race_pads_cover_the_whole_pool(self):
        self.assertEqual(sorted(TRACK_IDS.values()), list(range(16)))
        self.assertEqual(sorted(TRACK_IDS), sorted(TROPHY_TRACKS))

    def test_vanilla_purple_is_exactly_the_boss_tracks(self):
        # Premise of the "Purple needs no special case" ruling: its vanilla
        # legs ARE the four boss tracks, a content fact, not a mechanism.
        purple = load_vanilla_cup_legs()["Purple Gem Cup"]
        self.assertEqual({TRACK_IDS[t] for t in purple}, BOSS_TRACK_IDS)


class TestDrawProperties(unittest.TestCase):
    """Draw-level properties of the ruled completely-random mode."""

    def test_option_off_makes_no_draws(self):
        rng = _ScriptedRNG([])
        legs = resolve_gem_cup_legs(_stub_world(rng, enabled=False))
        self.assertEqual(legs, load_vanilla_cup_legs())
        self.assertEqual(rng._values, [])  # not a single draw consumed

    def test_pool_clamped_to_trophy_tracks(self):
        for seed in range(100):
            with self.subTest(seed=seed):
                legs = resolve_gem_cup_legs(_stub_world(random.Random(seed)))
                for cup in CUP_NAMES:
                    self.assertEqual(len(legs[cup]), 4)
                    for track in legs[cup]:
                        self.assertIn(track, TRACK_IDS)
                        self.assertLess(TRACK_IDS[track], 16)

    def test_determinism(self):
        first = resolve_gem_cup_legs(_stub_world(random.Random(1701)))
        second = resolve_gem_cup_legs(_stub_world(random.Random(1701)))
        self.assertEqual(first, second)

    def test_draw_order_is_cup_major(self):
        # The first 4 draws land in Red, the next 4 in Green, and so on:
        # the consumption order is fixed, which is what makes the map
        # reproducible from the seed.
        script = [i % 16 for i in range(20)]  # draw i -> LevelID i % 16
        legs = resolve_gem_cup_legs(_stub_world(_ScriptedRNG(script)))
        for i, cup in enumerate(CUP_NAMES):
            self.assertEqual(
                [TRACK_IDS[t] for t in legs[cup]],
                [(i * 4 + j) % 16 for j in range(4)])

    def test_repeats_allowed(self):
        legs = resolve_gem_cup_legs(_stub_world(_ScriptedRNG([7, 7, 7, 3] * 5)))
        for cup in CUP_NAMES:
            self.assertEqual([TRACK_IDS[t] for t in legs[cup]], [7, 7, 7, 3])

    def test_all_same_track_cup(self):
        legs = resolve_gem_cup_legs(_stub_world(_ScriptedRNG([5] * 20)))
        for cup in CUP_NAMES:
            self.assertEqual(legs[cup], ["Papu's Pyramid"] * 4)
        # The map is still complete and serializes to a full 5x4 wire block.
        wire = cup_legs_to_wire(legs)
        self.assertEqual(set(wire), {"100", "101", "102", "103", "104"})
        self.assertTrue(all(len(v) == 4 for v in wire.values()))

    def test_absent_tracks(self):
        # Every leg the same track: 15 trophy tracks leg no cup at all, and
        # the map is still complete (each absent track's own warp pad stays
        # its independent path, so nothing is orphaned).
        legs = resolve_gem_cup_legs(_stub_world(_ScriptedRNG([3] * 20)))
        flat = [t for cup_legs in legs.values() for t in cup_legs]
        self.assertEqual(set(flat), {"Crash Cove"})
        self.assertEqual(len(flat), 20)

    def test_purple_cup_without_boss_tracks(self):
        # Red..Yellow draw 0; Purple draws four non-boss tracks.
        legs = resolve_gem_cup_legs(
            _stub_world(_ScriptedRNG([0] * 16 + [0, 2, 3, 4])))
        purple_ids = {TRACK_IDS[t] for t in legs["Purple Gem Cup"]}
        self.assertTrue(purple_ids.isdisjoint(BOSS_TRACK_IDS))
        self.assertEqual(len(legs["Purple Gem Cup"]), 4)

    def test_track_to_cups_dedupes_a_repeated_leg(self):
        # A cup legging the same track twice must yield ONE (cup, track)
        # pair: Regions builds an entrance per pair and duplicate entrance
        # names would collide in the entrance cache. Every cup here legs
        # Hot Air Skyway twice, so it must appear exactly once per cup.
        legs = resolve_gem_cup_legs(_stub_world(_ScriptedRNG([7, 7, 9, 2] * 5)))
        self.assertEqual(track_to_cups(legs)["Hot Air Skyway"], CUP_NAMES)


class TestVanillaLegParity(CTRTestBase):
    """Option OFF (the default): the pre-#166 behaviour, bit for bit."""

    run_default_tests = False
    options = {
        "podium_placement_checks": True,
        "include_gem_cups": True,
    }

    def test_world_map_is_the_vanilla_table(self):
        self.assertEqual(self.world.gem_cup_legs, load_vanilla_cup_legs())

    def test_no_wire_key_but_schema_bumps_to_7(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertNotIn("gem_cup_legs", slot_data)
        self.assertEqual(slot_data["schema_version"], 7)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 7)

    def test_podium_wiring_matches_vanilla_legs(self):
        # Hot Air Skyway legs the Yellow and Purple cups in vanilla; its
        # podium region must be entered from exactly those plus its own
        # track region (issue #86's joint-region shape, unchanged).
        podium = self.multiworld.get_region("Hot Air Skyway: Podium", self.player)
        self.assertEqual(
            {e.parent_region.name for e in podium.entrances},
            {"Hot Air Skyway", "Yellow Gem Cup", "Purple Gem Cup"})


class TestRandomizedLegsIntegration(CTRTestBase):
    """Option ON at full generation: wire shape, schema gate, and the
    reachability graph following the drawn map."""

    run_default_tests = False
    auto_construct = False
    options = {
        "podium_placement_checks": True,
        "include_gem_cups": True,
        "randomize_gem_cup_tracks": True,
    }

    def setUp(self):
        self.world_setup(seed=LEGS_SEED)

    def test_wire_block_round_trips(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        wire = slot_data["gem_cup_legs"]
        self.assertEqual(set(wire), {"100", "101", "102", "103", "104"})
        for legs in wire.values():
            self.assertEqual(len(legs), 4)
            for lid in legs:
                self.assertIs(type(lid), int)
                self.assertIn(lid, ID_TRACKS)
        self.assertEqual(wire, cup_legs_to_wire(self.world.gem_cup_legs))

    def test_schema_bumped_to_7(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(slot_data["schema_version"], 7)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 7)

    def test_seed_exhibits_repeats_and_absent_tracks(self):
        # Documents the LEGS_SEED choice: if generation-internal RNG
        # consumption ever changes this map, this test fails first and the
        # seed comment above must be re-derived.
        legs = self.world.gem_cup_legs
        flat = [t for cup_legs in legs.values() for t in cup_legs]
        self.assertTrue(any(len(set(v)) < 4 for v in legs.values()),
                        "expected a repeated leg inside at least one cup")
        self.assertTrue(any(t not in flat for t in TROPHY_TRACKS),
                        "expected at least one track absent from every cup")

    def test_podium_wiring_follows_the_drawn_map(self):
        t2c = track_to_cups(self.world.gem_cup_legs)
        for track in TROPHY_TRACKS:
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertEqual(
                    {e.parent_region.name for e in podium.entrances},
                    {track} | set(t2c.get(track, [])))

    def test_repeated_leg_builds_a_single_entrance(self):
        # Green legs Hot Air Skyway twice on this seed; exactly one entrance
        # may run from the Green Gem Cup into its podium region.
        self.assertEqual(
            self.world.gem_cup_legs["Green Gem Cup"].count("Hot Air Skyway"), 2)
        podium = self.multiworld.get_region("Hot Air Skyway: Podium", self.player)
        self.assertEqual(
            [e.name for e in podium.entrances
             if e.parent_region.name == "Green Gem Cup"],
            ["Green Gem Cup -> Hot Air Skyway: Podium"])

    def test_absent_track_podium_has_only_its_own_entrance(self):
        # Coco Park legs no cup on this seed: its rungs hang off its own
        # track region alone -- the additive-cup-path guarantee.
        flat = [t for v in self.world.gem_cup_legs.values() for t in v]
        self.assertNotIn("Coco Park", flat)
        podium = self.multiworld.get_region("Coco Park: Podium", self.player)
        self.assertEqual(
            {e.parent_region.name for e in podium.entrances}, {"Coco Park"})


class TestUTRegenParity(CTRTestBase):
    """Universal Tracker re-generation must rebuild the seed's exact leg map
    from slot_data instead of re-drawing it (issue #29's divergence class)."""

    run_default_tests = False
    auto_construct = False
    options = TestRandomizedLegsIntegration.options

    def _setup_with_passthrough(self, seed, passthrough):
        # test.bases.world_setup with multiworld.re_gen_passthrough injected
        # before the generation steps -- exactly where UT places the
        # connected room's slot_data.
        self.multiworld = MultiWorld(1)
        self.multiworld.game[self.player] = self.game
        self.multiworld.player_name = {self.player: "Tester"}
        self.multiworld.set_seed(seed)
        random.seed(self.multiworld.seed)
        self.multiworld.seed_name = get_seed_name(random)
        args = Namespace()
        world_type = AutoWorld.AutoWorldRegister.world_types[self.game]
        for name, option in world_type.options_dataclass.type_hints.items():
            setattr(args, name,
                    {1: option.from_any(self.options.get(name, option.default))})
        self.multiworld.set_options(args)
        self.multiworld.state = CollectionState(self.multiworld)
        self.multiworld.re_gen_passthrough = {self.game: passthrough}
        self.world = self.multiworld.worlds[self.player]
        for step in gen_steps:
            call_all(self.multiworld, step)

    def test_ut_regen_pins_the_seeded_map(self):
        self.world_setup(seed=LEGS_SEED)
        server_legs = dict(self.world.gem_cup_legs)
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))

        self._setup_with_passthrough(LEGS_SEED, slot_data)
        ut_world = self.world

        self.assertEqual(ut_world.gem_cup_legs, server_legs)
        self.assertEqual(ut_world.options.randomize_gem_cup_tracks.value, 1)
        ut_slot_data = json.loads(json.dumps(ut_world.fill_slot_data()))
        self.assertEqual(ut_slot_data["gem_cup_legs"], slot_data["gem_cup_legs"])
        self.assertEqual(ut_slot_data["schema_version"], 7)

        # The re-generated reachability graph follows the pinned map too.
        t2c = track_to_cups(server_legs)
        for track in TROPHY_TRACKS:
            with self.subTest(track=track):
                podium = self.multiworld.get_region(
                    f"{track}: Podium", self.player)
                self.assertEqual(
                    {e.parent_region.name for e in podium.entrances},
                    {track} | set(t2c.get(track, [])))

    def test_ut_regen_pins_the_map_through_the_real_wire_pipeline(self):
        # Regression for the 2026-08-09 fuzz gate (check-ut, 28/500): a
        # json.loads(json.dumps(...)) round-trip (used by every other test
        # in this class) can never expose this, because JSON has no tuple
        # type. AP's REAL slot_data pipeline runs every value through
        # NetUtils.convert_to_base_types (Main.py) before pickling into
        # multidata, which turns every list into a tuple -- so the
        # reconstructor must accept tuples, not just lists, or a live UT
        # session silently falls back to vanilla on every randomized seed.
        self.world_setup(seed=LEGS_SEED)
        server_legs = dict(self.world.gem_cup_legs)
        slot_data = convert_to_base_types(self.world.fill_slot_data())
        self.assertIsInstance(slot_data["gem_cup_legs"]["100"], tuple,
                               "test fixture no longer reproduces the real "
                               "wire shape -- convert_to_base_types changed")

        self._setup_with_passthrough(LEGS_SEED, slot_data)
        ut_world = self.world

        self.assertEqual(ut_world.gem_cup_legs, server_legs)
        self.assertEqual(ut_world.options.randomize_gem_cup_tracks.value, 1)

    def test_ut_regen_without_key_falls_back_to_vanilla(self):
        # A pre-#166 seed carries no gem_cup_legs key: the re-generation must
        # restore option off + the vanilla table, not crash and not draw.
        self.world_setup(seed=LEGS_SEED)
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        del slot_data["gem_cup_legs"]
        slot_data["schema_version"] = slot_data["ctr_options"]["schema_version"] = 6

        self._setup_with_passthrough(LEGS_SEED, slot_data)
        self.assertEqual(self.world.gem_cup_legs, load_vanilla_cup_legs())
        self.assertEqual(self.world.options.randomize_gem_cup_tracks.value, 0)

    def test_reconstruct_rejects_malformed_wire(self):
        for bad in (None, [], "Red Gem Cup",
                    {"100": [0, 1, 2]},                # incomplete block
                    {"100": [0, 1, 2, 16], "101": [0, 1, 2, 3],  # id 16
                     "102": [0, 1, 2, 3], "103": [0, 1, 2, 3],
                     "104": [0, 1, 2, 3]},
                    {"100": [0, 1, 2, 3], "101": [0, 1, 2, 3],  # missing 104
                     "102": [0, 1, 2, 3], "103": [0, 1, 2, 3]}):
            with self.subTest(value=bad):
                passthrough = {} if bad is None else {"gem_cup_legs": bad}
                self.assertEqual(
                    reconstruct_gem_cup_legs_from_wire(passthrough),
                    load_vanilla_cup_legs())
