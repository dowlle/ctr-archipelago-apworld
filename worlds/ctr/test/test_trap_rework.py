"""The 0.2.0 trap rework (issue #280): renamed identities and weighted fill.

Two halves, and each one guards a different way the rework can go wrong.

  1. THE NAMES. The rework renamed 16 traps and minted 3 more while 0.2.0 is
     still unpublished. A rename is only safe because no id moved with it, so
     the full name -> id table is pinned here verbatim. It is written out
     rather than imported from traps.TRAP_REGISTRY on purpose: a test that
     reads the same constant the code reads proves nothing.
  2. THE DRAW. `trap_weights` replaced the uniform pick, so the properties a
     player can actually observe are asserted directly on the draw: the ratios
     over a large fixed sample, exact exclusion at weight 0, the
     one-effect-left case, and determinism for one seed and YAML. The rejection
     cases (unknown key, all-zero table with trap fill above 0) run through
     generate_early, which is where a player meets them.

The draw tests use test.general.setup_multiworld with generate_early only,
like test_requirement_weights: WorldTestBase.setUp would run a full generation
per case and cannot host an assertRaises, and the draw needs nothing beyond a
world's options and its seeded self.random.
"""
import unittest

import yaml
from collections import Counter

from Options import OptionError

from test.general import setup_multiworld

from .. import ctrAPWorld, traps
from ..Items import load_item_table
from ..Options import TrapWeights

# Only generate_early has to run: it holds the raise guards, and it leaves a
# world whose options and self.random are exactly what create_items would draw
# against.
EARLY = ("generate_early",)

#: Every trap name the datapackage registers after the rework, with the id it
#: carries, in id order. The five renamed shipped traps keep the ids v0.1.5
#: published; the eleven renamed frozen traps keep the ids #177 minted; only
#: the four new identities take new codes.
EXPECTED_TRAP_IDS = {
    # native AP_TrapEffect 0-4
    "Icy Road": 35010016,
    "Low Gravity": 35010017,
    "Forced USF": 35010018,
    "Forced Boost": 35010019,
    "First Person": 35010020,
    # native AP_TrapEffect 5-15, frozen by #177
    "Wumpa Wipeout": 35010106,
    "Flatten": 35010107,
    "Item Reroll": 35010108,
    "Forced Use": 35010109,
    "Empty Crates": 35010110,
    "Weakened Kart": 35010111,
    "Boost Blocker": 35010112,
    "Wireframe": 35010113,
    "Nitro Drop": 35010114,
    "Reverse Steering": 35010115,
    "Red Potion": 35010116,
    # native AP_TrapEffect 16-18, minted by #280
    "Upside Down": 35010190,
    "Mirror Mode": 35010191,
    "Warpball Ambush": 35010192,
    "Demo Camera": 35010193,
}

#: What #280 renamed, old -> new. Every one of these keeps the id the old name
#: held, which is the whole reason the rename was allowed to happen at all.
RENAMED_BY_280 = {
    "Icy Road Trap": "Icy Road",
    "Low Gravity Trap": "Low Gravity",
    "No Brakes Trap": "Forced USF",
    "Forced Boost Trap": "Forced Boost",
    "First Person Trap": "First Person",
    "Wumpa Reset Trap": "Wumpa Wipeout",
    "Flatten Trap": "Flatten",
    "Item Reroll Trap": "Item Reroll",
    "Auto-Use Trap": "Forced Use",
    "Empty Crates Trap": "Empty Crates",
    "Weakened Kart Trap": "Weakened Kart",
    "No Boost Trap": "Boost Blocker",
    "Wireframe Trap": "Wireframe",
    "Nitro Trap": "Nitro Drop",
    "Reverse Controls Trap": "Reverse Steering",
    "Red Potion Trap": "Red Potion",
}

#: Approved after the 0.2.0 name freeze by the 2026-09-02 datapackage-unfreeze
#: ruling. The identity keeps its frozen code; this explicit map records the
#: one permitted post-freeze rename instead of weakening the freeze tests.
RENAMED_AFTER_FREEZE = {
    "Nitro": "Nitro Drop",
}

#: Every key with a working native effect, in AP_TrapEffect order.
BUILDABLE_KEYS = (
    "icy_road", "low_gravity", "forced_usf", "forced_boost",
    "first_person", "wumpa_wipeout", "flatten", "item_reroll",
    "forced_use", "empty_crates", "weakened_kart", "boost_blocker",
    "wireframe", "nitro", "reverse_steering", "red_potion",
    "upside_down", "mirror_mode", "warpball_ambush",
    "demo_camera",
)


def _world(seed=1, weights=None, trap_fill=10, steps=EARLY):
    options = {"trap_fill_percentage": trap_fill}
    if weights is not None:
        options["trap_weights"] = weights
    return setup_multiworld(ctrAPWorld, steps, seed=seed,
                            options=options).worlds[1]


class TestTrapNames(unittest.TestCase):
    """Half 1: the datapackage after the rename."""

    def test_the_trap_family_is_exactly_the_pinned_name_and_id_table(self):
        table = {item["name"]: item["code"] for item in load_item_table()
                 if item["classification"].name == "trap"}
        self.assertEqual(table, EXPECTED_TRAP_IDS)

    def test_no_old_trap_name_survives_anywhere_in_the_item_table(self):
        """A leftover old name would be a second, duplicate identity for an
        effect that already has one."""
        names = {item["name"] for item in load_item_table()}
        for old, new in RENAMED_BY_280.items():
            with self.subTest(renamed=old):
                self.assertNotIn(old, names)
                self.assertIn(new, names)

    def test_the_renames_moved_no_id(self):
        """The v0.1.5 and #177 fixtures were re-keyed to the new names in
        place; this restates the property they exist for, from the ids the old
        names held rather than from the fixture files."""
        old_ids = {
            "Icy Road Trap": 35010016, "Low Gravity Trap": 35010017,
            "No Brakes Trap": 35010018, "Forced Boost Trap": 35010019,
            "First Person Trap": 35010020, "Wumpa Reset Trap": 35010106,
            "Flatten Trap": 35010107, "Item Reroll Trap": 35010108,
            "Auto-Use Trap": 35010109, "Empty Crates Trap": 35010110,
            "Weakened Kart Trap": 35010111, "No Boost Trap": 35010112,
            "Wireframe Trap": 35010113, "Nitro Trap": 35010114,
            "Reverse Controls Trap": 35010115, "Red Potion Trap": 35010116,
        }
        for old, code in old_ids.items():
            with self.subTest(renamed=old):
                self.assertEqual(EXPECTED_TRAP_IDS[RENAMED_BY_280[old]], code)

    def test_the_approved_post_freeze_rename_moved_no_id(self):
        old_ids = {"Nitro": 35010114}
        names = {item["name"] for item in load_item_table()}
        for old, new in RENAMED_AFTER_FREEZE.items():
            with self.subTest(renamed=old):
                self.assertNotIn(old, names)
                self.assertIn(new, names)
                self.assertEqual(EXPECTED_TRAP_IDS[new], old_ids[old])

    def test_the_three_new_identities_are_registered_and_buildable(self):
        """Their authored count stays 0 because weighted fill creates them."""
        by_name = {item["name"]: item for item in load_item_table()}
        for name in ("Upside Down", "Mirror Mode", "Warpball Ambush"):
            with self.subTest(item=name):
                self.assertEqual(by_name[name]["count"], 0)
                self.assertEqual(by_name[name]["classification"].name, "trap")
                self.assertIn(name, traps.TRAP_ITEM_NAMES)

    def test_demo_camera_is_registered_and_buildable(self):
        by_name = {item["name"]: item for item in load_item_table()}
        self.assertEqual(by_name["Demo Camera"]["code"], 35010193)
        self.assertEqual(by_name["Demo Camera"]["count"], 0)
        self.assertEqual(by_name["Demo Camera"]["classification"].name, "trap")
        self.assertIn("Demo Camera", traps.TRAP_ITEM_NAMES)
        self.assertIn("demo_camera", traps.TRAP_WEIGHT_KEYS)

    def test_the_weight_keys_cover_every_trap_exactly_once(self):
        self.assertEqual(len(traps.TRAP_WEIGHT_KEYS), 20)
        self.assertEqual(len(set(traps.TRAP_WEIGHT_KEYS)), 20)
        self.assertEqual(set(traps.DEFAULT_TRAP_WEIGHTS),
                         set(traps.TRAP_WEIGHT_KEYS))
        self.assertEqual(sorted(traps.ALL_TRAP_ITEM_NAMES),
                         sorted(EXPECTED_TRAP_IDS))


class TestTrapWeightResolution(unittest.TestCase):
    """Defaults in, defaults out: what a partial or absent mapping means."""

    def test_an_absent_mapping_is_the_reviewed_default_table(self):
        world = _world()
        self.assertEqual(traps.effective_trap_weights(world),
                         traps.DEFAULT_TRAP_WEIGHTS)

    def test_an_empty_mapping_is_also_the_default_table(self):
        world = _world(weights={})
        self.assertEqual(traps.effective_trap_weights(world),
                         traps.DEFAULT_TRAP_WEIGHTS)

    def test_a_partial_mapping_keeps_the_default_of_every_omitted_key(self):
        world = _world(weights={"icy_road": 42, "first_person": 0})
        effective = traps.effective_trap_weights(world)
        self.assertEqual(effective["icy_road"], 42)
        self.assertEqual(effective["first_person"], 0)
        for key, default in traps.DEFAULT_TRAP_WEIGHTS.items():
            if key not in ("icy_road", "first_person"):
                with self.subTest(key=key):
                    self.assertEqual(effective[key], default)

    def test_every_registered_trap_can_reach_the_draw(self):
        weights = {key: 0 for key in BUILDABLE_KEYS}
        weights.update({"flatten": 100, "warpball_ambush": 100})
        world = _world(weights=weights)
        self.assertEqual(set(traps.selectable_trap_weights(world)),
                         {"flatten", "warpball_ambush"})


class TestWeightedDraw(unittest.TestCase):
    """Half 2: what the draw actually produces."""

    #: One fixed large sample. Big enough that a 2-vs-5 weight difference
    #: cannot pass by luck, and seeded, so this can never flake.
    SAMPLE = 20000
    #: Absolute tolerance on each share. The worst-case standard error at this
    #: sample size is about 0.0035, so 0.02 is roughly six sigma: it fails a
    #: genuinely wrong ratio and passes ordinary sampling noise.
    TOLERANCE = 0.02

    def _shares(self, world, count=None):
        drawn = traps.draw_trap_names(world, count or self.SAMPLE)
        counted = Counter(drawn)
        return {name: hits / len(drawn) for name, hits in counted.items()}

    def test_default_weights_produce_their_documented_ratios(self):
        # The reviewed 20-effect table totals 75 relative-weight points.
        world = _world(seed=280)
        shares = self._shares(world)
        expected_weights = {
            "Icy Road": 5, "Low Gravity": 5, "Forced USF": 2,
            "Forced Boost": 4, "First Person": 3, "Wumpa Wipeout": 4,
            "Flatten": 6, "Item Reroll": 5, "Forced Use": 4,
            "Empty Crates": 3, "Weakened Kart": 3, "Boost Blocker": 3,
            "Wireframe": 2, "Nitro Drop": 5, "Reverse Steering": 4,
            "Red Potion": 3, "Upside Down": 2, "Mirror Mode": 3,
            "Warpball Ambush": 3,
            "Demo Camera": 3,
        }
        expected = {name: weight / 75
                    for name, weight in expected_weights.items()}
        self.assertEqual(set(shares), set(expected))
        for name, share in expected.items():
            with self.subTest(trap=name):
                self.assertAlmostEqual(shares[name], share,
                                       delta=self.TOLERANCE)

    def test_custom_weights_renormalize_over_the_traps_left_enabled(self):
        """Weights are relative and need no total: 30/10 over two enabled traps
        is 75/25 of the draw, not 30% and 10% of something."""
        weights = {key: 0 for key in BUILDABLE_KEYS}
        weights.update({"icy_road": 30, "low_gravity": 10})
        world = _world(seed=281, weights=weights)
        shares = self._shares(world)
        self.assertEqual(set(shares), {"Icy Road", "Low Gravity"})
        self.assertAlmostEqual(shares["Icy Road"], 0.75, delta=self.TOLERANCE)
        self.assertAlmostEqual(shares["Low Gravity"], 0.25,
                               delta=self.TOLERANCE)

    def test_a_zero_weight_is_exact_exclusion_not_rarity(self):
        world = _world(seed=282, weights={"first_person": 0, "forced_usf": 0})
        drawn = set(traps.draw_trap_names(world, self.SAMPLE))
        self.assertNotIn("First Person", drawn)
        self.assertNotIn("Forced USF", drawn)
        self.assertEqual(drawn, set(traps.TRAP_ITEM_NAMES)
                         - {"First Person", "Forced USF"})

    def test_one_enabled_trap_fills_every_trap_slot(self):
        world = _world(seed=283, weights={
            key: (7 if key == "low_gravity" else 0) for key in BUILDABLE_KEYS})
        self.assertEqual(set(traps.draw_trap_names(world, 500)),
                         {"Low Gravity"})

    def test_identical_yaml_and_seed_draw_identically(self):
        weights = {"icy_road": 9, "first_person": 0}
        first = traps.draw_trap_names(_world(seed=284, weights=weights), 500)
        second = traps.draw_trap_names(_world(seed=284, weights=weights), 500)
        self.assertEqual(first, second)

    def test_a_different_seed_draws_differently(self):
        """The other half of determinism: the draw is seeded, not fixed."""
        weights = {"icy_road": 9, "first_person": 0}
        first = traps.draw_trap_names(_world(seed=284, weights=weights), 500)
        other = traps.draw_trap_names(_world(seed=285, weights=weights), 500)
        self.assertNotEqual(first, other)


class TestTrapWeightsRejected(unittest.TestCase):
    """The configs generation must refuse, and refuse readably."""

    def test_an_unknown_key_is_rejected_with_the_valid_keys_in_the_message(self):
        with self.assertRaises(OptionError) as caught:
            _world(weights={"icyroad": 5})
        message = str(caught.exception)
        self.assertIn("icyroad", message)
        self.assertIn("icy_road", message)
        self.assertIn("trap_weights", message)

    def test_an_unknown_key_is_rejected_even_with_traps_switched_off(self):
        """A misspelling is a misspelling: trap_fill_percentage 0 does not make
        the player's intent for that key any more achievable."""
        with self.assertRaises(OptionError):
            _world(trap_fill=0, weights={"first_persson": 0})

    def test_a_yaml_is_rejected_at_option_verification_too(self):
        """The rolled-YAML path (Generate.py verifies every option) fails on
        the same message, not just the generate_early path."""
        from ..Options import TrapWeights
        with self.assertRaises(OptionError):
            TrapWeights({"mirror-mode": 3}).verify_keys()

    def test_a_non_integer_or_out_of_range_weight_is_rejected(self):
        for bad in ({"icy_road": 101}, {"icy_road": -1}, {"icy_road": 2.5},
                    {"icy_road": "5"}):
            with self.subTest(weights=bad):
                with self.assertRaises(OptionError):
                    _world(weights=bad)

    def test_all_zero_with_trap_fill_above_zero_is_rejected(self):
        with self.assertRaises(OptionError) as caught:
            _world(trap_fill=10, weights={key: 0 for key in BUILDABLE_KEYS})
        self.assertIn("trap_fill_percentage", str(caught.exception))

    def test_one_nonzero_shipped_trap_rescues_the_draw(self):
        weights = {key: 0 for key in BUILDABLE_KEYS}
        weights["warpball_ambush"] = 50
        world = _world(trap_fill=10, weights=weights)
        self.assertEqual(traps.selectable_trap_weights(world),
                         {"warpball_ambush": 50})

    def test_all_zero_with_trap_fill_zero_is_harmless(self):
        """No draw ever happens, so an all-zero table is a legal way to park
        weights while traps are off."""
        world = _world(trap_fill=0,
                       weights={key: 0 for key in traps.TRAP_WEIGHT_KEYS})
        self.assertEqual(traps.selectable_trap_weights(world), {})


class TestTrapFillUsesTheWeights(unittest.TestCase):
    """The end-to-end half: a real generation, not just the draw helper."""

    def test_a_generated_pool_holds_only_enabled_traps(self):
        weights = {key: 0 for key in BUILDABLE_KEYS}
        weights.update({"icy_road": 5, "low_gravity": 5})
        multiworld = setup_multiworld(
            ctrAPWorld, seed=286,
            options={"trap_fill_percentage": 100, "trap_weights": weights})
        pooled = {item.name for item in multiworld.itempool
                  if item.name in traps.ALL_TRAP_ITEM_NAMES}
        self.assertTrue(pooled, "seed produced no traps to check")
        self.assertTrue(pooled <= {"Icy Road", "Low Gravity"}, pooled)

    def test_trap_fill_zero_still_puts_no_trap_in_the_pool(self):
        multiworld = setup_multiworld(
            ctrAPWorld, seed=287, options={"trap_fill_percentage": 0})
        pooled = {item.name for item in multiworld.itempool
                  if item.name in traps.ALL_TRAP_ITEM_NAMES}
        self.assertEqual(pooled, set())



class TestNonStringTrapWeightKeys(unittest.TestCase):
    """YAML 1.1 resolves bare 1, yes, no, on, off and null to non-string keys.
    They must reach the clear unknown-key OptionError, not a raw TypeError
    from sorting or joining mixed key types (review finding, 2026-08-19)."""

    def test_a_yaml_integer_key_is_rejected_readably(self):
        value = yaml.safe_load("1: 5\nicy_road: 5\n")
        self.assertEqual(set(map(type, value)), {int, str})
        with self.assertRaises(OptionError):
            TrapWeights(value).verify_keys()

    def test_a_yaml_boolean_key_is_rejected_readably(self):
        value = yaml.safe_load("no: 0\n")
        self.assertEqual(list(map(type, value)), [bool])
        with self.assertRaises(OptionError):
            TrapWeights(value).verify_keys()


class TestTrapWeightsAccessibilityHelpText(unittest.TestCase):
    """Issue #280 follow-up (pause accessibility): the native side now lets a
    pause menu suspend five camera/visual traps' effects while paused. This
    apworld's only stake in that is the generated `trap_weights` help text,
    which should tell a player up front that those five traps can be visually
    intense and that a weight of 0 turns one off entirely. Pinned verbatim so
    a future edit to the docstring cannot silently drop the warning; no
    option semantics/values are touched or asserted here."""

    def test_help_text_names_the_camera_and_visual_traps(self):
        self.assertIn(
            "Five traps change the camera or the screen itself and may be "
            "visually\n    intense or uncomfortable: First Person, "
            "Wireframe, Upside Down, Mirror\n    Mode, and Demo Camera.",
            TrapWeights.__doc__)

    def test_help_text_says_weight_zero_disables_the_effect(self):
        self.assertIn(
            "Set an individual trap's weight to 0 to disable\n    that "
            "effect entirely -- it becomes unpickable while every other "
            "trap\n    keeps its own weight.",
            TrapWeights.__doc__)

    def test_manual_yaml_limitation_note_is_still_present(self):
        # This warning predates #280; the accessibility text must not have
        # displaced or reworded it.
        self.assertIn(
            "The Archipelago website's options pages cannot show a mapping",
            TrapWeights.__doc__)


if __name__ == "__main__":
    unittest.main()
