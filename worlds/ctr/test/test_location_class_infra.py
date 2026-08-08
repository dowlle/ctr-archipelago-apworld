"""Shared location-class infrastructure (issue #176).

#176 extracts the shape that podium rungs, relic perfects (#49), item boxes
(#109), itemsanity (#145) and lettersanity (#148) all wear: a frozen name
superset registered unconditionally into the datapackage, plus a per-seed subset
created from options. It adds no locations, changes no behaviour, and settles no
design question about the classes themselves, so most of what is worth testing
is what must NOT have moved.

The suites below lock in the invariants the extraction has to preserve:

- deterministic registration and ordering: the registry's contribution to the
  datapackage is registration order then superset order, stable across calls,
  and `created_locations` re-imposes superset order whatever order a class
  returned its created names in;
- option-gated active sets: a class is active exactly when it creates at least
  one location, so a master toggle that is ON with every sub-toggle OFF is NOT
  active (podium's real behaviour, and the property callers want);
- duplicate and collision handling: within a class, across classes, and against
  the static data/locations.json table, every collision is a hard failure at
  registration rather than a silently overwritten id;
- groups: the seam exists for the classes that want one, group names cannot be
  claimed twice, members must belong to the declaring class, and podium declares
  none -- so the live datapackage's location_name_groups stays empty and its AP
  checksum does not move;
- append-only id stability: every location code the class registry owned at
  v0.1.5 still resolves to the same id and in the same relative order, the
  location-side sibling of #168's item guard.

Fixture provenance: `fixtures/location_class_id_stability_v0_1_5.json` was
generated from `origin/main` @ 98164405a (the pre-extraction tree), taking the
112 entries of `location_name_to_id` that the location classes own -- i.e. every
name NOT in data/locations.json -- in datapackage order.
"""
import json
import pathlib
import unittest

from worlds.AutoWorld import AutoWorldRegister

from . import CTRTestBase
from ..location_class import LocationClass, LocationClassRegistry
from ..Locations import CTR_LOCATION_CLASSES, CTR_LOCATION_IDS
from ..podium import (NEW_RUNGS, PODIUM_CLASS, SHIPPED_RUNGS, SLOT_ORDER,
                      TROPHY_TRACKS, all_podium_locations,
                      created_rung_keys_from_options, location_name,
                      podium_slot_codes)

FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures"
    / "location_class_id_stability_v0_1_5.json"
)

PODIUM_TOGGLES = (
    "podium_placement_checks",
    "podium_held_rungs",
    "podium_held_fifth_rung",
    "podium_finish_rungs",
    "podium_any_position_rung",
)


class _Toggle:
    def __init__(self, value):
        self.value = int(bool(value))


class _StubOptions:
    """Just enough of an options object for the podium creation predicate."""

    def __init__(self, **flags):
        for name in PODIUM_TOGGLES:
            setattr(self, name, _Toggle(flags.get(name, False)))


# The podium creation subsets worth covering: the master gate, each rung family
# on its own, and the sub-toggles that add a rung inside a family.
ARMS = {
    "master_off": (
        dict(podium_held_rungs=True, podium_finish_rungs=True,
             podium_any_position_rung=True, podium_held_fifth_rung=True),
        [],
    ),
    "master_on_no_subtoggles": (
        dict(podium_placement_checks=True),
        [],
    ),
    "held_only": (
        dict(podium_placement_checks=True, podium_held_rungs=True),
        ["held_1st", "held_3rd"],
    ),
    "held_with_fifth": (
        dict(podium_placement_checks=True, podium_held_rungs=True,
             podium_held_fifth_rung=True),
        ["held_1st", "held_3rd", "held_5th"],
    ),
    "finish_only": (
        dict(podium_placement_checks=True, podium_finish_rungs=True),
        ["finish_podium"],
    ),
    "finish_with_any": (
        dict(podium_placement_checks=True, podium_finish_rungs=True,
             podium_any_position_rung=True),
        ["finish_podium", "finish_any"],
    ),
    "all_rungs": (
        dict(podium_placement_checks=True, podium_held_rungs=True,
             podium_held_fifth_rung=True, podium_finish_rungs=True,
             podium_any_position_rung=True),
        ["held_1st", "held_3rd", "held_5th", "finish_podium", "finish_any"],
    ),
    # the fifth-rung sub-toggle is inert without its family
    "fifth_without_held": (
        dict(podium_placement_checks=True, podium_held_fifth_rung=True),
        [],
    ),
    "any_without_finish": (
        dict(podium_placement_checks=True, podium_any_position_rung=True),
        [],
    ),
}


class _FakeClass(LocationClass):
    """A synthetic class for the registry's guard rails, so the podium class
    never has to be deliberately broken to test them."""

    def __init__(self, key, entries, created=None, groups=None,
                 display_name="Fake"):
        self.key = key
        self.display_name = display_name
        self._entries = list(entries)
        self._created = created
        self._groups = groups or {}

    def all_locations(self):
        return list(self._entries)

    def created_location_names(self, options):
        if self._created is None:
            return [name for name, _c, _r in self._entries]
        return list(self._created)

    def location_name_groups(self):
        return {k: set(v) for k, v in self._groups.items()}


def _entries(prefix, base, count, region="Nowhere"):
    return [(f"{prefix} {i}", base + i, region) for i in range(count)]


class TestPodiumClassIdentity(unittest.TestCase):
    """The extraction moved podium onto the base without moving podium."""

    def test_superset_is_16_tracks_x_7_entries(self) -> None:
        entries = PODIUM_CLASS.all_locations()
        self.assertEqual(len(TROPHY_TRACKS), 16)
        self.assertEqual(len(entries), 16 * (len(SHIPPED_RUNGS) + len(NEW_RUNGS)))
        self.assertEqual(len(entries), 112)

    def test_module_facade_delegates_to_the_class(self) -> None:
        """Regions.py and Rules.py still call the module functions; they must be
        the class, not a second implementation of it."""
        self.assertEqual(all_podium_locations(), PODIUM_CLASS.all_locations())
        track = TROPHY_TRACKS[0]
        self.assertEqual(location_name(track, "held_1st"),
                         PODIUM_CLASS.location_name(track, "held_1st"))
        opts = _StubOptions(podium_placement_checks=True, podium_held_rungs=True)
        self.assertEqual(created_rung_keys_from_options(opts),
                         PODIUM_CLASS.created_rung_keys(opts))
        self.assertEqual(podium_slot_codes(track, ["held_1st"]),
                         PODIUM_CLASS.slot_codes(track, ["held_1st"]))

    def test_finish_any_reuses_the_shipped_name_and_code(self) -> None:
        """finish_any IS the shipped 'Finish (Any Position)' entry -- the class's
        name/code helpers must not mint a second one."""
        for track in TROPHY_TRACKS:
            self.assertEqual(PODIUM_CLASS.location_name(track, "finish_any"),
                             PODIUM_CLASS.location_name(track, "any"))
            self.assertEqual(PODIUM_CLASS.code_for(track, "finish_any"),
                             PODIUM_CLASS.code_for(track, "any"))

    def test_code_blocks_match_the_codes_actually_registered(self) -> None:
        """The declared blocks are the freeze's documentation (#177); a code
        outside them means the docstring lies."""
        blocks = PODIUM_CLASS.code_blocks
        self.assertEqual(len(blocks), 2)
        for _name, code, _region in PODIUM_CLASS.all_locations():
            self.assertTrue(
                any(base <= code < base + 100 for base in blocks),
                f"code {code} sits outside the declared blocks {blocks}",
            )

    def test_class_codes_agree_with_the_merged_location_table(self) -> None:
        for name, code in PODIUM_CLASS.name_to_code().items():
            self.assertIn(name, CTR_LOCATION_IDS)
            self.assertEqual(CTR_LOCATION_IDS[name], code)


class TestDeterministicOrdering(unittest.TestCase):

    def test_superset_order_is_stable_across_calls(self) -> None:
        self.assertEqual(PODIUM_CLASS.all_locations(),
                         PODIUM_CLASS.all_locations())
        self.assertEqual(CTR_LOCATION_CLASSES.all_locations(),
                         CTR_LOCATION_CLASSES.all_locations())

    def test_registry_order_is_registration_order_then_superset_order(self) -> None:
        registry = LocationClassRegistry()
        first = _FakeClass("first", _entries("First", 90000000, 3))
        second = _FakeClass("second", _entries("Second", 90001000, 2))
        registry.register(first)
        registry.register(second)
        self.assertEqual(registry.all_locations(),
                         first.all_locations() + second.all_locations())
        self.assertEqual([c.key for c in registry.classes], ["first", "second"])

    def test_registry_contribution_is_the_tail_of_the_location_table(self) -> None:
        """Registration order IS datapackage order: the class entries must be
        the tail of CTR_LOCATION_IDS, in order, after the static table."""
        registry_names = [n for n, _c, _r in CTR_LOCATION_CLASSES.all_locations()]
        table_names = list(CTR_LOCATION_IDS)
        self.assertEqual(table_names[-len(registry_names):], registry_names)

    def test_created_locations_use_superset_order_not_call_order(self) -> None:
        entries = _entries("Shuffled", 90002000, 4)
        reversed_names = [name for name, _c, _r in entries][::-1]
        klass = _FakeClass("shuffled", entries, created=reversed_names)
        self.assertEqual(klass.created_locations(None), entries)

    def test_created_locations_are_deterministic_for_the_same_options(self) -> None:
        opts = _StubOptions(podium_placement_checks=True, podium_held_rungs=True,
                            podium_finish_rungs=True)
        self.assertEqual(PODIUM_CLASS.created_locations(opts),
                         PODIUM_CLASS.created_locations(opts))


class TestActiveAndInactiveClasses(unittest.TestCase):

    def test_master_gate_off_creates_nothing(self) -> None:
        opts = _StubOptions(podium_held_rungs=True, podium_finish_rungs=True)
        self.assertEqual(PODIUM_CLASS.created_rung_keys(opts), [])
        self.assertFalse(PODIUM_CLASS.is_enabled(opts))
        self.assertEqual(PODIUM_CLASS.created_locations(opts), [])
        self.assertEqual(CTR_LOCATION_CLASSES.active(opts), ())

    def test_master_gate_on_with_no_sub_toggles_is_not_active(self) -> None:
        """The option is on but the seed gets no locations, so the class is not
        active. Callers that key off the master toggle alone would be wrong."""
        opts = _StubOptions(podium_placement_checks=True)
        self.assertFalse(PODIUM_CLASS.is_enabled(opts))
        self.assertEqual(CTR_LOCATION_CLASSES.active(opts), ())

    def test_active_when_any_rung_is_created(self) -> None:
        opts = _StubOptions(podium_placement_checks=True, podium_held_rungs=True)
        self.assertTrue(PODIUM_CLASS.is_enabled(opts))
        self.assertEqual(CTR_LOCATION_CLASSES.active(opts), (PODIUM_CLASS,))

    def test_inactive_class_contributes_to_the_datapackage_anyway(self) -> None:
        """The whole point of the frozen superset: names stay registered even
        for a seed that creates none of them."""
        opts = _StubOptions()
        self.assertEqual(PODIUM_CLASS.created_locations(opts), [])
        self.assertEqual(len(PODIUM_CLASS.all_locations()), 112)
        for name, _code, _region in PODIUM_CLASS.all_locations():
            self.assertIn(name, CTR_LOCATION_IDS)


class TestOptionCombinations(unittest.TestCase):

    def test_created_rung_keys_per_arm(self) -> None:
        for arm, (flags, expected) in ARMS.items():
            with self.subTest(arm=arm):
                self.assertEqual(
                    PODIUM_CLASS.created_rung_keys(_StubOptions(**flags)),
                    expected,
                )

    def test_created_location_count_per_arm(self) -> None:
        for arm, (flags, expected) in ARMS.items():
            with self.subTest(arm=arm):
                created = PODIUM_CLASS.created_locations(_StubOptions(**flags))
                self.assertEqual(len(created), 16 * len(expected))
                self.assertEqual({name for name, _c, _r in created},
                                 {PODIUM_CLASS.location_name(t, k)
                                  for t in TROPHY_TRACKS for k in expected})

    def test_slot_codes_place_minus_one_exactly_where_a_rung_is_absent(self) -> None:
        for arm, (flags, expected) in ARMS.items():
            with self.subTest(arm=arm):
                keys = PODIUM_CLASS.created_rung_keys(_StubOptions(**flags))
                for track in TROPHY_TRACKS:
                    arr = PODIUM_CLASS.slot_codes(track, keys)
                    self.assertEqual(len(arr), len(SLOT_ORDER))
                    for slot, code in zip(SLOT_ORDER, arr):
                        if slot in expected:
                            self.assertNotEqual(code, -1)
                            self.assertEqual(
                                code,
                                CTR_LOCATION_IDS[
                                    PODIUM_CLASS.location_name(track, slot)],
                            )
                        else:
                            self.assertEqual(code, -1)

    def test_every_emitted_slot_code_exists_in_the_datapackage(self) -> None:
        valid = set(CTR_LOCATION_IDS.values())
        for arm, (flags, _expected) in ARMS.items():
            keys = PODIUM_CLASS.created_rung_keys(_StubOptions(**flags))
            for track in TROPHY_TRACKS:
                for code in PODIUM_CLASS.slot_codes(track, keys):
                    if code != -1:
                        with self.subTest(arm=arm, track=track, code=code):
                            self.assertIn(code, valid)


class TestDuplicatesAndCollisions(unittest.TestCase):

    def setUp(self) -> None:
        self.registry = LocationClassRegistry()

    def test_duplicate_name_inside_one_class_is_rejected(self) -> None:
        klass = _FakeClass("dupname", [("Same", 90010000, "R"),
                                       ("Same", 90010001, "R")])
        with self.assertRaisesRegex(ValueError, "registers the name"):
            self.registry.register(klass)

    def test_duplicate_code_inside_one_class_is_rejected(self) -> None:
        klass = _FakeClass("dupcode", [("A", 90010000, "R"),
                                       ("B", 90010000, "R")])
        with self.assertRaisesRegex(ValueError, "registers code"):
            self.registry.register(klass)

    def test_two_classes_cannot_share_a_key(self) -> None:
        self.registry.register(_FakeClass("k", _entries("A", 90020000, 1)))
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.registry.register(_FakeClass("k", _entries("B", 90021000, 1)))

    def test_registering_the_same_instance_twice_is_a_no_op(self) -> None:
        klass = _FakeClass("once", _entries("A", 90030000, 2))
        self.registry.register(klass)
        self.registry.register(klass)
        self.assertEqual(len(self.registry), 1)
        self.assertEqual(len(self.registry.all_locations()), 2)

    def test_name_collision_across_classes_is_rejected(self) -> None:
        self.registry.register(_FakeClass("a", [("Shared", 90040000, "R")]))
        with self.assertRaisesRegex(ValueError, "claims the name"):
            self.registry.register(_FakeClass("b", [("Shared", 90041000, "R")]))

    def test_code_collision_across_classes_is_rejected(self) -> None:
        self.registry.register(_FakeClass("a", [("A", 90050000, "R")]))
        with self.assertRaisesRegex(ValueError, "claims code"):
            self.registry.register(_FakeClass("b", [("B", 90050000, "R")]))

    def test_a_failed_registration_leaves_the_registry_untouched(self) -> None:
        good = _FakeClass("good", _entries("Good", 90060000, 2))
        self.registry.register(good)
        with self.assertRaises(ValueError):
            self.registry.register(_FakeClass("bad", [("Good 0", 90061000, "R")]))
        self.assertEqual([c.key for c in self.registry.classes], ["good"])
        self.assertEqual(self.registry.all_locations(), good.all_locations())

    def test_missing_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            self.registry.register(_FakeClass("", _entries("A", 90070000, 1)))

    def test_name_collision_with_the_static_table_is_rejected(self) -> None:
        self.registry.register(_FakeClass("s", [("Crash Cove: Trophy Race",
                                                 90080000, "Crash Cove")]))
        with self.assertRaisesRegex(ValueError, "claims the name"):
            self.registry.assert_disjoint_from(CTR_LOCATION_IDS, "the static table")

    def test_code_collision_with_the_static_table_is_rejected(self) -> None:
        static_code = CTR_LOCATION_IDS["Crash Cove: Trophy Race"]
        self.registry.register(_FakeClass("s", [("Brand New Name", static_code,
                                                 "Crash Cove")]))
        with self.assertRaisesRegex(ValueError, "claims code"):
            self.registry.assert_disjoint_from(CTR_LOCATION_IDS, "the static table")

    def test_the_live_registry_is_disjoint_from_the_static_table(self) -> None:
        static = json.loads(
            (pathlib.Path(__file__).parents[1] / "data" / "locations.json")
            .read_text(encoding="utf-8")
        )
        static_by_name = {loc["name"]: loc["code"] for loc in static}
        self.assertEqual(len(static_by_name), 101)
        for name, code, _region in CTR_LOCATION_CLASSES.all_locations():
            self.assertNotIn(name, static_by_name)
            self.assertNotIn(code, set(static_by_name.values()))

    def test_creating_a_name_outside_the_superset_is_rejected(self) -> None:
        klass = _FakeClass("stray", _entries("Real", 90090000, 2),
                           created=["Real 0", "Not Registered"])
        with self.assertRaisesRegex(ValueError, "not in its frozen superset"):
            klass.created_locations(None)


class TestLocationNameGroups(unittest.TestCase):

    def test_a_class_declares_no_groups_by_default(self) -> None:
        klass = _FakeClass("plain", _entries("A", 90100000, 2))
        self.assertEqual(klass.location_name_groups(), {})

    def test_podium_declares_no_groups_so_the_datapackage_is_unchanged(self) -> None:
        """#176 is behaviour-neutral. location_name_groups is part of the payload
        AP checksums, so a group added here would move the datapackage checksum
        and the #177 manifest with it."""
        self.assertEqual(PODIUM_CLASS.location_name_groups(), {})
        self.assertEqual(CTR_LOCATION_CLASSES.location_name_groups(), {})
        # AP injects "Everywhere" itself (AutoWorld.py:70-72); CTR declares none
        # of its own, and that is what must not move.
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        declared = {name: group for name, group
                    in world_type.location_name_groups.items()
                    if name != "Everywhere"}
        self.assertEqual(declared, {})

    def test_declared_groups_merge_into_the_registry(self) -> None:
        registry = LocationClassRegistry()
        registry.register(_FakeClass("g1", _entries("A", 90110000, 3),
                                     groups={"Alpha": ["A 0", "A 1"]}))
        registry.register(_FakeClass("g2", _entries("B", 90112000, 2),
                                     groups={"Beta": ["B 0"]}))
        self.assertEqual(registry.location_name_groups(),
                         {"Alpha": {"A 0", "A 1"}, "Beta": {"B 0"}})

    def test_two_classes_cannot_declare_the_same_group_name(self) -> None:
        registry = LocationClassRegistry()
        registry.register(_FakeClass("g1", _entries("A", 90120000, 2),
                                     groups={"Shared": ["A 0"]}))
        with self.assertRaisesRegex(ValueError, "already declared by"):
            registry.register(_FakeClass("g2", _entries("B", 90122000, 2),
                                         groups={"Shared": ["B 0"]}))

    def test_a_group_cannot_contain_another_class_s_locations(self) -> None:
        registry = LocationClassRegistry()
        registry.register(_FakeClass("g1", _entries("A", 90130000, 2)))
        with self.assertRaisesRegex(ValueError, "not in its own superset"):
            registry.register(_FakeClass("g2", _entries("B", 90132000, 2),
                                         groups={"Beta": ["A 0"]}))


class TestLocationClassIdStability(unittest.TestCase):
    """Append-only guard for the location codes the classes own (#168's item
    guard, on the location side).

    Appends pass silently, exactly as #168 intends: a new class registered at the
    END of Locations.CTR_LOCATION_CLASSES mints new codes without moving any of
    these. When 0.2.0's frozen manifest (#177) lands, extend this fixture with
    the new classes' entries rather than editing the existing ones.
    """

    def _frozen(self):
        def reject_duplicates(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError(
                        f"Duplicate key in location id stability fixture: {key!r}")
                out[key] = value
            return out

        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"),
                          object_pairs_hook=reject_duplicates)

    def test_fixture_covers_every_class_owned_location(self) -> None:
        frozen = self._frozen()
        self.assertEqual(len(frozen), 112)
        current = {name for name, _c, _r in CTR_LOCATION_CLASSES.all_locations()}
        missing = set(frozen) - current
        self.assertEqual(
            missing, set(),
            "location(s) vanished from the class registry. A shipped location "
            "name must stay registered forever even when it is retired from "
            "creation (see podium.py's two retired v0.1.x rungs).",
        )

    def test_every_frozen_location_keeps_its_id(self) -> None:
        frozen = self._frozen()
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        current = world_type.location_name_to_id
        for name, frozen_id in frozen.items():
            with self.subTest(location=name):
                self.assertIn(name, current)
                self.assertEqual(
                    current[name], frozen_id,
                    f"{name!r} moved from id {frozen_id} to {current[name]}. "
                    "Location codes are explicit per class, so this means a code "
                    "block base, a stride, or the canonical track order moved. "
                    "New locations must be appended in a new block; if this move "
                    "is genuinely intentional, update this fixture in the same "
                    "commit and say so in the PR description.",
                )

    def test_frozen_locations_keep_their_relative_datapackage_order(self) -> None:
        """Registration order is datapackage order. Reordering would not renumber
        anything (codes are explicit), but it would churn a manifest diff (#177)
        for no reason, so it is pinned."""
        frozen = self._frozen()
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        live_order = [name for name in world_type.location_name_to_id
                      if name in frozen]
        self.assertEqual(live_order, list(frozen))


class _CreatedMatchesGenerationMixin:
    """The class's per-seed subset must be exactly what generation created.

    This is the property the whole extraction rests on: `Regions.py` creates the
    locations, `Rules.py` puts them in logic and `fill_slot_data` describes them
    to native, all from the same predicate. If `created_locations` and the real
    world ever disagree, one of those three is describing a seed that does not
    exist.
    """

    def test_created_locations_match_the_generated_world(self) -> None:
        predicted = {name for name, _c, _r
                     in PODIUM_CLASS.created_locations(self.world.options)}
        class_names = {name for name, _c, _r in PODIUM_CLASS.all_locations()}
        actual = {loc.name for loc
                  in self.multiworld.get_locations(self.player)
                  if loc.name in class_names}
        self.assertEqual(predicted, actual)

    def test_active_set_matches_the_generated_world(self) -> None:
        active = CTR_LOCATION_CLASSES.active(self.world.options)
        expected = (PODIUM_CLASS,) if self.expected_rungs else ()
        self.assertEqual(active, expected)

    def test_slot_data_codes_come_from_the_class(self) -> None:
        block = self.world.fill_slot_data()["podium_checks"]
        keys = PODIUM_CLASS.created_rung_keys(self.world.options)
        lid_to_track = {
            str(meta["level_id"]): pad_name[: -len(" Warp Pad")]
            for pad_name, meta in getattr(self.world, "warp_pad_ids", {}).items()
            if pad_name.endswith(" Warp Pad")
        }
        for lid, arr in block["locations"].items():
            with self.subTest(level_id=lid):
                self.assertEqual(
                    arr, PODIUM_CLASS.slot_codes(lid_to_track[lid], keys))


class TestGeneratedDefaults(_CreatedMatchesGenerationMixin, CTRTestBase):
    options = {}
    expected_rungs = True


class TestGeneratedPodiumOff(_CreatedMatchesGenerationMixin, CTRTestBase):
    options = {"podium_placement_checks": False}
    expected_rungs = False


class TestGeneratedAllRungs(_CreatedMatchesGenerationMixin, CTRTestBase):
    options = {
        "podium_placement_checks": True,
        "podium_held_rungs": True,
        "podium_held_fifth_rung": True,
        "podium_finish_rungs": True,
        "podium_any_position_rung": True,
    }
    expected_rungs = True


class TestGeneratedMasterOnNoSubToggles(_CreatedMatchesGenerationMixin,
                                        CTRTestBase):
    """The master toggle is on and every sub-toggle is off: the class registers
    its 112 names but creates none of them, and must report itself inactive."""

    options = {
        "podium_placement_checks": True,
        "podium_held_rungs": False,
        "podium_held_fifth_rung": False,
        "podium_finish_rungs": False,
        "podium_any_position_rung": False,
    }
    expected_rungs = False


if __name__ == "__main__":
    unittest.main()
