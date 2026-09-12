"""Focused gates for the 0.2.1 Hit Character encounter registration and wire.

Covers the bounded ticket scope only:

  * the sixteen frozen location identities and their additive code block;
  * off creates nothing / on creates sixteen, in the Menu region;
  * the deterministic rotation, the guest pins and the boss identity table;
  * the single cached uint32 roster seed (off consumes no RNG, on draws once);
  * the top-level block and the always-emitted scalar;
  * Universal Tracker restore: exact round-trip, legacy absence/off, and the
    malformed/conflicting/unknown-schema refusals.

Native dispatch, model loading, reachability and the all-sixteen runtime
behaviour are explicitly out of scope for this ticket.
"""
import copy
import unittest

from Options import OptionError
from test.general import setup_multiworld

from .. import characters, ctrAPWorld
from ..hit_character import (
    BOSS_WIN_OPPONENTS,
    CUP_IDS,
    DEFAULT_RACER_IDS,
    GLOBAL_SCHEMA_MAX,
    GUEST_RACER_IDS,
    HIT_CHARACTER_CLASS,
    HIT_CHARACTER_CODE_BASE,
    HIT_CHARACTER_SCHEMA,
    PIN_GUESTS,
    TRACK_LEVEL_IDS,
    _validate_block,
    build_encounters,
    resolve_for_generation,
    restore_from_wire,
    slot_data,
)

#: Sentinel meaning "omit the global schema_version key entirely".
_ABSENT = object()

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
TRIAL = {"slide_coliseum_races": "trophy_race",
         "turbo_track_races": "trophy_race"}


def _options(**overrides):
    opts = dict(TRIAL)
    opts.update(overrides)
    return opts


def _build(seed=1, steps=STEPS, **overrides):
    return setup_multiworld(ctrAPWorld, steps, seed=seed,
                            options=_options(**overrides))


def _rotate(ids, offset):
    amount = offset % len(ids)
    return list(ids[amount:]) + list(ids[:amount])


class TestLocationClassIdentity(unittest.TestCase):
    def test_sixteen_names_in_engine_id_order(self):
        entries = HIT_CHARACTER_CLASS.all_locations()
        self.assertEqual(len(entries), 16)
        for engine_id, (name, code, region) in enumerate(entries):
            with self.subTest(engine_id=engine_id):
                self.assertEqual(
                    name,
                    f"Hit {characters.CHARACTER_ID_TO_NAME[engine_id]}")
                self.assertEqual(code, HIT_CHARACTER_CODE_BASE + engine_id)
                self.assertEqual(region, "Menu")

    def test_names_are_the_canonical_roster_names(self):
        names = set(HIT_CHARACTER_CLASS.names())
        expected = {f"Hit {name}"
                    for name in characters.CHARACTER_ID_TO_NAME.values()}
        self.assertEqual(names, expected)

    def test_off_creates_nothing_and_on_creates_all_sixteen(self):
        class _Toggle:
            def __init__(self, value):
                self.value = value

        class _Opts:
            pass

        off = _Opts()
        off.hit_character = _Toggle(0)
        on = _Opts()
        on.hit_character = _Toggle(1)
        self.assertEqual(HIT_CHARACTER_CLASS.created_location_names(off), [])
        self.assertFalse(HIT_CHARACTER_CLASS.is_enabled(off))
        self.assertEqual(len(HIT_CHARACTER_CLASS.created_location_names(on)), 16)
        self.assertTrue(HIT_CHARACTER_CLASS.is_enabled(on))
        self.assertEqual(HIT_CHARACTER_CLASS.created_location_names(None), [])

    def test_code_block_is_disjoint_from_every_other_class(self):
        others = {}
        from ..Locations import CTR_LOCATION_CLASSES
        for location_class in CTR_LOCATION_CLASSES:
            if location_class is HIT_CHARACTER_CLASS:
                continue
            for _name, code, _region in location_class.all_locations():
                others[code] = location_class.key
        for _name, code, _region in HIT_CHARACTER_CLASS.all_locations():
            self.assertNotIn(code, others)


class TestOffIsInert(unittest.TestCase):
    def test_no_locations_scalar_false_no_block(self):
        mw = _build(hit_character=False)
        world = mw.worlds[1]
        names = {loc.name for loc in mw.get_locations(1)}
        self.assertEqual(
            names & set(HIT_CHARACTER_CLASS.names()), set())
        wire = world.fill_slot_data()
        self.assertFalse(wire["ctr_options"]["hit_character"])
        self.assertNotIn("hit_character_encounters", wire)

    def test_resolve_returns_none_and_consumes_no_rng(self):
        mw = _build(hit_character=False, steps=())
        world = mw.worlds[1]
        before = world.random.getstate()
        self.assertIsNone(resolve_for_generation(world))
        self.assertIsNone(slot_data(world))
        self.assertEqual(world.random.getstate(), before)
        self.assertFalse(hasattr(world, "ctr_hit_character_encounters")
                         and world.ctr_hit_character_encounters)


class TestOnCreatesAndEmits(unittest.TestCase):
    def test_sixteen_locations_and_wire_block(self):
        mw = _build(hit_character=True)
        world = mw.worlds[1]
        names = {loc.name for loc in mw.get_locations(1)}
        self.assertTrue(set(HIT_CHARACTER_CLASS.names()) <= names)
        wire = world.fill_slot_data()
        self.assertTrue(wire["ctr_options"]["hit_character"])
        self.assertEqual(wire["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["schema_version"], 16)
        block = wire["hit_character_encounters"]
        self.assertEqual(block["schema"], HIT_CHARACTER_SCHEMA)
        self.assertEqual(block["locations"], {
            str(cid): HIT_CHARACTER_CODE_BASE + cid for cid in range(16)})

    def test_seed_is_cached_and_not_redrawn(self):
        mw = _build(hit_character=True, steps=())
        world = mw.worlds[1]
        first = resolve_for_generation(world)
        seed = world.ctr_hit_character_seed
        state_after_first = world.random.getstate()
        second = resolve_for_generation(world)
        self.assertEqual(first, second)
        self.assertEqual(world.random.getstate(), state_after_first)
        self.assertEqual(seed, first["policy"]["seed"])

    def test_same_seed_generates_identical_blocks(self):
        a = _build(seed=17, hit_character=True).worlds[1]
        b = _build(seed=17, hit_character=True).worlds[1]
        self.assertEqual(a.ctr_hit_character_encounters,
                         b.ctr_hit_character_encounters)

    def test_total_locations_increases_by_exactly_sixteen(self):
        off = _build(seed=1, hit_character=False).worlds[1]
        on = _build(seed=1, hit_character=True).worlds[1]
        self.assertEqual(
            on.fill_slot_data()["TotalLocations"]
            - off.fill_slot_data()["TotalLocations"], 16)


class TestDeterministicLayout(unittest.TestCase):
    def test_rotation_for_every_track_and_cup(self):
        for seed in (0, 1, 123456789, 0xFFFFFFFF):
            block = build_encounters(seed)
            for level_id in TRACK_LEVEL_IDS:
                entry = block["tracks"][str(level_id)]
                offset = (seed + level_id) % 8
                self.assertEqual(entry["base"],
                                 _rotate(DEFAULT_RACER_IDS, offset))
                self.assertEqual(entry["reserve"],
                                 _rotate(GUEST_RACER_IDS, offset))
            for cup in CUP_IDS:
                entry = block["cups"][str(cup)]
                offset = (seed + cup) % 8
                self.assertEqual(entry["base"],
                                 _rotate(DEFAULT_RACER_IDS, offset))
                self.assertEqual(entry["reserve"],
                                 _rotate(GUEST_RACER_IDS, offset))

    def test_uint32_boundaries_are_accepted(self):
        for seed in (0, 0xFFFFFFFF):
            block = build_encounters(seed)
            self.assertEqual(block["policy"]["seed"], seed)
            self.assertEqual(block["tracks"]["0"]["base"],
                             _rotate(DEFAULT_RACER_IDS, seed % 8))

    def test_lists_have_no_duplicates_and_bounded_pins(self):
        block = build_encounters(0xDEADBEEF)
        for group in ("tracks", "cups"):
            for key, entry in block[group].items():
                with self.subTest(group=group, key=key):
                    for list_name in ("base", "pinned", "reserve"):
                        values = entry[list_name]
                        self.assertEqual(len(set(values)), len(values))
                    self.assertLessEqual(len(entry["pinned"]), 1)


class TestPinsAndBosses(unittest.TestCase):
    def test_pin_guests_land_on_their_exact_destinations(self):
        expected = {
            8: (7,), 9: (5,), 10: (6,), 11: (1,),
            12: (16, 17), 13: (2, 12), 14: (3, 8), 15: (13,),
        }
        self.assertEqual({cid: levels for cid, (levels, _c, _k)
                          in PIN_GUESTS.items()}, expected)
        block = build_encounters(42)
        for guest, (levels, _codes, _kind) in PIN_GUESTS.items():
            for level_id in levels:
                with self.subTest(guest=guest, level=level_id):
                    self.assertEqual(block["tracks"][str(level_id)]["pinned"],
                                     [guest])
        pinned_levels = {lid for levels, _c, _k in PIN_GUESTS.values()
                         for lid in levels}
        for level_id in TRACK_LEVEL_IDS:
            if level_id not in pinned_levels:
                self.assertEqual(
                    block["tracks"][str(level_id)]["pinned"], [])

    def test_unlock_triggers_carry_codes_not_names(self):
        block = build_encounters(7)
        expected = {
            8: ("boss", [35011103]),
            9: ("boss", [35011101]),
            10: ("boss", [35011100]),
            11: ("boss", [35011102]),
            12: ("track", [35016200, 35016201]),
            13: ("track", [35011008, 35011010]),
            14: ("track", [35011000, 35011003]),
            15: ("boss", [35011104, 35011105]),
        }
        self.assertEqual(set(block["unlock_triggers"]),
                         {str(cid) for cid in GUEST_RACER_IDS})
        for guest, (kind, any_of) in expected.items():
            with self.subTest(guest=guest):
                self.assertEqual(block["unlock_triggers"][str(guest)],
                                 {"kind": kind, "any_of": any_of})
                self.assertTrue(all(type(c) is int
                                    for c in block["unlock_triggers"][str(guest)]["any_of"]))

    def test_boss_table_maps_both_oxide_codes_to_oxide(self):
        block = build_encounters(0)
        self.assertEqual(block["bosses"],
                         {str(code): opponent
                          for code, opponent in sorted(BOSS_WIN_OPPONENTS.items())})
        self.assertEqual(block["bosses"]["35011104"], 15)
        self.assertEqual(block["bosses"]["35011105"], 15)
        self.assertEqual(len(block["bosses"]), 6)


class TestUTRestore(unittest.TestCase):
    def _restore(self, passthrough, **overrides):
        mw = _build(steps=(), **overrides)
        world = mw.worlds[1]
        world._ut_restore_options(passthrough)
        return world

    def _world(self):
        return _build(steps=()).worlds[1]

    def _restore_block(self, world, block, scalar=True, schema=16):
        co = {"hit_character": scalar}
        if schema is not _ABSENT:
            co["schema_version"] = schema
        return restore_from_wire(
            world, {"ctr_options": co,
                    "hit_character_encounters": block})

    def test_round_trip_preserves_block_and_ordering(self):
        source = _build(hit_character=True).worlds[1]
        wire = source.fill_slot_data()
        block = copy.deepcopy(wire["hit_character_encounters"])
        world = self._restore(wire)
        self.assertTrue(world.options.hit_character.value)
        self.assertEqual(world.ctr_hit_character_encounters, block)
        self.assertEqual(world.ctr_hit_character_seed, block["policy"]["seed"])
        # Re-emitting the restored world reproduces the exact same ordering.
        self.assertEqual(slot_data(world), block)

    def test_legacy_absence_restores_to_off(self):
        world = self._restore({"ctr_options": {}, "warp_pad_unlock": {},
                               "podium_checks": {}})
        self.assertFalse(world.options.hit_character.value)
        self.assertIsNone(world.ctr_hit_character_encounters)

    def test_absent_ctr_options_restores_to_off(self):
        world = self._world()
        restore_from_wire(world, {"warp_pad_unlock": {}, "podium_checks": {}})
        self.assertIsNone(world.ctr_hit_character_encounters)
        self.assertIsNone(world.ctr_hit_character_seed)

    def test_reordered_candidates_are_preserved_verbatim(self):
        """Any valid permutation of the correct candidate sets is accepted and
        round-tripped without reordering, re-drawing or rebuilding."""
        block = build_encounters(1)
        for group in ("tracks", "cups"):
            for entry in block[group].values():
                entry["base"] = list(reversed(entry["base"]))
                entry["reserve"] = list(reversed(entry["reserve"]))
        block["unlock_triggers"]["12"]["any_of"] = list(
            reversed(block["unlock_triggers"]["12"]["any_of"]))
        world = self._restore(
            {"ctr_options": {"hit_character": True, "schema_version": 16},
             "hit_character_encounters": block,
             "warp_pad_unlock": {}, "podium_checks": {}})
        self.assertIs(world.ctr_hit_character_encounters, block)
        self.assertIs(slot_data(world), block)

    def test_boss_identity_substitution_is_allowed(self):
        """The boss values are resolved identities, not a frozen literal: a
        fixture may substitute any valid engine id 0..15."""
        block = build_encounters(1)
        block["bosses"]["35011100"] = 3
        world = self._world()
        self._restore_block(world, block)
        self.assertEqual(
            world.ctr_hit_character_encounters["bosses"]["35011100"], 3)

    def test_scalar_must_be_an_actual_bool(self):
        for bad in (1, 0, "true", None):
            with self.subTest(scalar=bad):
                world = self._world()
                with self.assertRaises(OptionError):
                    self._restore_block(world, build_encounters(1), scalar=bad)

    def test_present_null_block_is_refused(self):
        world = self._world()
        with self.assertRaises(OptionError):
            restore_from_wire(
                world, {"ctr_options": {"hit_character": True},
                        "hit_character_encounters": None})

    def test_enabled_scalar_without_block_is_refused(self):
        world = self._world()
        with self.assertRaises(OptionError):
            restore_from_wire(world, {"ctr_options": {"hit_character": True}})

    def test_block_without_enabled_scalar_is_refused(self):
        block = build_encounters(1)
        for co in ({}, {"hit_character": False}):
            with self.subTest(ctr_options=co):
                world = self._world()
                with self.assertRaises(OptionError):
                    restore_from_wire(
                        world, {"ctr_options": co,
                                "hit_character_encounters": block})

    def test_absent_scalar_with_present_null_block_is_refused(self):
        world = self._world()
        with self.assertRaises(OptionError):
            restore_from_wire(
                world, {"ctr_options": {},
                        "hit_character_encounters": None})

    def test_block_top_level_keys_are_exact(self):
        """The block carries exactly the seven frozen top-level keys; an extra
        or missing key is refused (native enforces the same set)."""
        for extra in ("extra", "schema_version", "policy_extra"):
            block = build_encounters(1)
            block[extra] = 1
            with self.subTest(extra=extra):
                with self.assertRaises(OptionError):
                    _validate_block(block)
        for missing in ("schema", "locations", "policy", "tracks", "cups",
                        "unlock_triggers", "bosses"):
            block = build_encounters(1)
            block.pop(missing)
            with self.subTest(missing=missing):
                with self.assertRaises(OptionError):
                    _validate_block(block)

    def test_enabled_feature_requires_global_schema_16(self):
        """An enabled feature on an absent, old, or non-integer global schema
        is refused rather than accepted-but-never-activated."""
        for schema in (0, 13, 14, 15, _ABSENT, True, False, 1.0, "16", None):
            with self.subTest(schema=schema):
                world = self._world()
                with self.assertRaises(OptionError):
                    self._restore_block(world, build_encounters(1),
                                        schema=schema)
                self.assertIsNone(world.ctr_hit_character_encounters)
                self.assertIsNone(world.ctr_hit_character_seed)

    def test_global_schema_signed32_upper_bound(self):
        """An enabled block accepts global schemas 16..2147483647 only; above
        the signed 32-bit ceiling native's int32 reader can represent is a
        clear refusal, not a truncated activation."""
        world = self._world()
        block = build_encounters(1)
        self._restore_block(world, block, schema=GLOBAL_SCHEMA_MAX)
        self.assertIs(world.ctr_hit_character_encounters, block)
        for schema in (GLOBAL_SCHEMA_MAX + 1, 2 ** 31, 0xFFFFFFFF,
                       0xFFFFFFFF + 1):
            with self.subTest(schema=schema):
                world = self._world()
                with self.assertRaises(OptionError):
                    self._restore_block(world, build_encounters(1),
                                        schema=schema)
                self.assertIsNone(world.ctr_hit_character_encounters)
                self.assertIsNone(world.ctr_hit_character_seed)

    def test_future_global_schema_with_known_block_is_accepted(self):
        world = self._world()
        block = build_encounters(1)
        self._restore_block(world, block, schema=17)
        self.assertIs(world.ctr_hit_character_encounters, block)
        self.assertEqual(world.ctr_hit_character_seed, block["policy"]["seed"])

    def test_malformed_ctr_options_are_refused(self):
        """A non-mapping ctr_options or passthrough is refused as OptionError,
        never an AttributeError from a later .get."""
        block = build_encounters(1)
        for co in ([], "ctr_options", 14, True):
            with self.subTest(ctr_options=co):
                world = self._world()
                with self.assertRaises(OptionError):
                    restore_from_wire(
                        world, {"ctr_options": co,
                                "hit_character_encounters": block})
        for passthrough in ("not-an-object", [1, 2, 3], 7):
            with self.subTest(passthrough=passthrough):
                world = self._world()
                with self.assertRaises(OptionError):
                    restore_from_wire(world, passthrough)

    def test_restore_transitions_clear_stale_state(self):
        """valid -> invalid -> legacy absence -> valid: a refused restore
        clears the previously cached valid block, and a later valid restore
        activates the new one."""
        world = self._world()

        valid = build_encounters(1)
        self._restore_block(world, valid, schema=16)
        self.assertIs(world.ctr_hit_character_encounters, valid)
        self.assertEqual(world.ctr_hit_character_seed, valid["policy"]["seed"])

        bad = build_encounters(2)
        bad["schema"] = 99
        with self.assertRaises(OptionError):
            self._restore_block(world, bad, schema=16)
        self.assertIsNone(world.ctr_hit_character_encounters)
        self.assertIsNone(world.ctr_hit_character_seed)

        restore_from_wire(world, {"ctr_options": {}})
        self.assertIsNone(world.ctr_hit_character_encounters)
        self.assertIsNone(world.ctr_hit_character_seed)

        fresh = build_encounters(3)
        self._restore_block(world, fresh, schema=16)
        self.assertIs(world.ctr_hit_character_encounters, fresh)
        self.assertEqual(world.ctr_hit_character_seed, fresh["policy"]["seed"])

    def test_unknown_schema_is_refused(self):
        for bad_schema in (2, "1", 1.0, None, True):
            with self.subTest(schema=bad_schema):
                block = build_encounters(1)
                block["schema"] = bad_schema
                world = self._world()
                with self.assertRaises(OptionError):
                    self._restore_block(world, block)

    def test_manager_reported_invalid_blocks_are_refused(self):
        """The four blocks the manager reproduced as accepted: schema=True,
        guest_slots=True, a guest substituted into base, and bosses keyed '1'
        through '6'."""
        world = self._world()

        b = build_encounters(1)
        b["schema"] = True
        with self.assertRaises(OptionError):
            self._restore_block(world, b)

        b = build_encounters(1)
        b["policy"]["guest_slots"] = True
        with self.assertRaises(OptionError):
            self._restore_block(world, b)

        b = build_encounters(1)
        b["tracks"]["3"]["base"][0] = 15
        with self.assertRaises(OptionError):
            self._restore_block(world, b)

        b = build_encounters(1)
        b["bosses"] = {str(i): i for i in range(1, 7)}
        with self.assertRaises(OptionError):
            self._restore_block(world, b)

    def test_malformed_blocks_are_refused(self):
        world = self._world()

        arms = {}
        b = build_encounters(1)
        b["tracks"].pop("17")
        arms["missing_track"] = b

        b = build_encounters(1)
        b["tracks"]["3"]["base"] = [0, 0, 1, 2, 3, 4, 5, 6]
        arms["duplicate_base"] = b

        b = build_encounters(1)
        b["tracks"]["0"]["reserve"] = list(range(8))  # base ids, not guests
        arms["reserve_not_guest_permutation"] = b

        b = build_encounters(1)
        b["tracks"]["3"]["pinned"] = [8, 9]
        arms["two_pins"] = b

        b = build_encounters(1)
        b["tracks"]["3"]["pinned"] = [13]  # wrong guest for Crash Cove
        arms["wrong_track_pin"] = b

        b = build_encounters(1)
        b["cups"]["100"]["pinned"] = [8]
        arms["cup_pin_nonempty"] = b

        b = build_encounters(1)
        b["policy"]["seed"] = 2 ** 32
        arms["seed_out_of_range"] = b

        b = build_encounters(1)
        b["policy"]["guest_slots"] = 2
        arms["bad_guest_slots"] = b

        b = build_encounters(1)
        b["policy"]["boss_eligible_after_clear"] = 1
        arms["bool_eligible"] = b

        b = build_encounters(1)
        b["policy"]["extra"] = 1
        arms["policy_extra_key"] = b

        b = build_encounters(1)
        b["unlock_triggers"]["8"]["any_of"] = []
        arms["empty_trigger"] = b

        b = build_encounters(1)
        b["unlock_triggers"]["8"]["kind"] = "track"
        arms["wrong_trigger_kind"] = b

        b = build_encounters(1)
        b["unlock_triggers"]["8"]["any_of"] = [35011100]
        arms["wrong_trigger_codes"] = b

        b = build_encounters(1)
        b["unlock_triggers"]["12"]["any_of"] = [35016200, 35016200]
        arms["duplicate_trigger_code"] = b

        b = build_encounters(1)
        b["unlock_triggers"]["8"]["any_of"] = [True]
        arms["bool_trigger_code"] = b

        b = build_encounters(1)
        b["bosses"]["35011100"] = 99
        arms["bad_boss_engine_id"] = b

        b = build_encounters(1)
        b["bosses"]["35011199"] = 10
        arms["extra_boss_key"] = b

        for arm, block in arms.items():
            with self.subTest(arm=arm):
                with self.assertRaises(OptionError):
                    self._restore_block(world, block)


class TestTrialTrophyModeGuard(unittest.TestCase):
    def test_enabled_without_trial_modes_raises(self):
        for overrides in (
            {"slide_coliseum_races": 0, "turbo_track_races": 0},
            {"slide_coliseum_races": 0},
            {"turbo_track_races": 0},
        ):
            with self.subTest(**overrides):
                with self.assertRaises(OptionError) as ctx:
                    _build(steps=("generate_early",),
                           hit_character=True, **overrides)
                self.assertIn("hit_character", str(ctx.exception))

    def test_enabled_with_both_trial_modes_generates(self):
        mw = _build(steps=("generate_early",), hit_character=True)
        self.assertTrue(mw.worlds[1].options.hit_character.value)

    def test_disabled_ignores_trial_modes(self):
        mw = _build(steps=("generate_early",), hit_character=False,
                    slide_coliseum_races=0, turbo_track_races=0)
        self.assertFalse(mw.worlds[1].options.hit_character.value)


class TestBuildIdentity(unittest.TestCase):
    """The internal ticket-06 staging badge, without moving the pair identity."""

    def test_internal_slice_build_badge_and_numeric_versions(self):
        from ..version import BUILD_VERSION
        self.assertEqual(BUILD_VERSION, "0.2.1-hit-slice1")
        mw = _build(hit_character=True)
        wire = mw.worlds[1].fill_slot_data()
        co = wire["ctr_options"]
        self.assertEqual(co["build_version"], "0.2.1-hit-slice1")
        # Numeric identities this internal staging must not move.
        self.assertEqual(co["world_version"], "0.2.1")
        self.assertEqual(co["schema_version"], 16)
        self.assertEqual(wire["schema_version"], 16)


if __name__ == "__main__":
    unittest.main()
