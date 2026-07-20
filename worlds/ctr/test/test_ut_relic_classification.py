"""Regression guard for the Universal Tracker relic-classification divergence.

Symptom (real UT fuzz check, ~12.6% of seeds): UT reported
"Slide Coliseum: Sapphire/Gold/Platinum Time Trial" as in-logic while the
server's sphere never contained them. Every failing seed shared
warppad_unlock_requirements: vanilla + accessibility: minimal + a goal other
than oxidefinal.

Mechanism: in vanilla warp-pad mode with accessibility: minimal and a
non-oxidefinal goal, `_relic_progression_map` classifies Sapphire Relic as
USEFUL. `CollectionState.collect` ignores non-advancement items, so the
vanilla Slide Coliseum pad gate `has('Sapphire Relic', 10)`
(data/world.json) is unsatisfiable server-side. UT's re-generation used to
short-circuit `_relic_progression_map` to "every tier progression", so its
graph opened a pad the server never opens.

The fix puts the RESOLVED classification on the wire
(ctr_options.relic_progression) instead of trying to recompute it from
inputs that do not travel. These tests lock in:

- the classification the failing configuration actually produces,
- that fill_slot_data round-trips it,
- that a pre-fix seed (key absent) still degrades to the old all-progression
  behaviour rather than crashing or silently flipping tiers to useful.
"""

import json

from BaseClasses import ItemClassification

from . import CTRTestBase

RELIC_TIERS = ("Sapphire Relic", "Gold Relic", "Platinum Relic")

# The three locations UT wrongly reported in logic. They live behind the
# vanilla Slide Coliseum warp pad's has('Sapphire Relic', 10) gate.
SLIDE_COLISEUM_TRIALS = (
    "Slide Coliseum: Sapphire Time Trial",
    "Slide Coliseum: Gold Time Trial",
    "Slide Coliseum: Platinum Time Trial",
)


def _wire(world):
    """The relic_progression block as it travels in slot_data (JSON round-trip
    included, so key/value types are the ones UT actually receives)."""
    slot_data = json.loads(json.dumps(world.fill_slot_data()))
    return slot_data["ctr_options"]["relic_progression"]


def _passthrough(world, slot_data_options):
    """Put `slot_data_options` on multiworld.re_gen_passthrough exactly the way
    Universal Tracker does, then read back the resolved classification."""
    world.multiworld.re_gen_passthrough = {
        world.game: {"ctr_options": slot_data_options}
    }
    try:
        return world._relic_progression_map()
    finally:
        world.multiworld.re_gen_passthrough = {}


class TestRelicClassificationVanillaMinimal(CTRTestBase):
    """The exact configuration shape every UT-check failure had."""

    # The generic WorldTestBase reachability tests demand that all_state reach
    # EVERY location; under accessibility: minimal with Sapphire demoted to
    # useful the Slide Coliseum trials are legitimately unreachable (that is the
    # bug's server-side truth, not a regression). The topology suite covers the
    # generic tests on configurations where they apply.
    run_default_tests = False
    options = {
        "warppad_unlock_requirements": "vanilla",
        "accessibility": "minimal",
        "goal": "oxide",
    }

    def test_sapphire_is_useful_not_progression(self):
        prog = self.world._relic_progression_map()
        self.assertFalse(
            prog["Sapphire Relic"],
            "vanilla + accessibility:minimal + non-oxidefinal must demote "
            "Sapphire Relic to useful; the Slide Coliseum gate is then "
            "unsatisfiable and UT must be told so")
        self.assertFalse(prog["Gold Relic"])
        self.assertFalse(prog["Platinum Relic"])

    def test_demoted_tier_is_created_as_useful(self):
        # The classification is not advisory: collect() skips non-advancement
        # items, which is precisely why the tracker must agree with it.
        item = self.world.create_item("Sapphire Relic")
        self.assertEqual(item.classification, ItemClassification.useful)
        self.assertFalse(item.advancement)

    def test_slot_data_carries_resolved_classification(self):
        wire = _wire(self.world)
        self.assertEqual(set(wire), set(RELIC_TIERS))
        self.assertEqual(wire, {t: False for t in RELIC_TIERS})
        for value in wire.values():
            self.assertIsInstance(value, bool)

    def test_slot_data_matches_create_item(self):
        wire = _wire(self.world)
        for tier in RELIC_TIERS:
            expected = self.world.create_item(tier).advancement
            self.assertEqual(
                wire[tier], expected,
                f"wire says {tier} progression={wire[tier]} but create_item "
                f"produced advancement={expected}")

    def test_ut_roundtrip_reproduces_server_classification(self):
        # UT re-generates with the seed's slot_data on re_gen_passthrough. The
        # map it resolves there must equal the one the SERVER used, or the two
        # disagree about which has() gates can ever open.
        server = self.world._relic_progression_map()
        tracker = _passthrough(self.world, {"relic_progression": _wire(self.world)})
        self.assertEqual(tracker, server)
        self.assertFalse(tracker["Sapphire Relic"])

    def test_ut_missing_key_falls_back_to_all_progression(self):
        # Seeds rolled before this key existed must keep working: no crash, and
        # the historical all-progression behaviour.
        tracker = _passthrough(self.world, {"goal": 0})
        self.assertEqual(tracker, {t: True for t in RELIC_TIERS})

    def test_ut_malformed_key_falls_back_to_all_progression(self):
        for bad in (None, [], "Sapphire Relic", 0):
            with self.subTest(value=bad):
                tracker = _passthrough(self.world, {"relic_progression": bad})
                self.assertEqual(tracker, {t: True for t in RELIC_TIERS})

    def test_ut_partial_key_defaults_missing_tiers_to_progression(self):
        tracker = _passthrough(
            self.world, {"relic_progression": {"Sapphire Relic": False}})
        self.assertEqual(
            tracker,
            {"Sapphire Relic": False, "Gold Relic": True, "Platinum Relic": True})

    def test_slide_coliseum_trials_are_gated_on_sapphire(self):
        # Anchors the premise of the whole bug: these are the locations UT
        # reported, and they sit behind a Sapphire count gate.
        for loc in SLIDE_COLISEUM_TRIALS:
            with self.subTest(location=loc):
                self.assertFalse(
                    self.can_reach_location(loc),
                    f"{loc} reachable from the empty state; the vanilla Slide "
                    f"Coliseum sapphire gate is missing")


class TestRelicClassificationVanillaFull(CTRTestBase):
    """accessibility: full keeps Sapphire progression -- the wire must say so."""

    run_default_tests = False
    options = {
        "warppad_unlock_requirements": "vanilla",
        "accessibility": "full",
        "goal": "oxide",
    }

    def test_sapphire_stays_progression(self):
        prog = self.world._relic_progression_map()
        self.assertTrue(prog["Sapphire Relic"])
        self.assertFalse(prog["Gold Relic"])
        self.assertFalse(prog["Platinum Relic"])

    def test_wire_and_roundtrip_agree(self):
        wire = _wire(self.world)
        self.assertTrue(wire["Sapphire Relic"])
        self.assertEqual(
            _passthrough(self.world, {"relic_progression": wire}),
            self.world._relic_progression_map())


class TestRelicClassificationRandomized(CTRTestBase):
    """Randomized pad modes keep every tier progression; unchanged behaviour."""

    run_default_tests = False
    options = {
        "warppad_unlock_requirements": "randomized",
        "accessibility": "minimal",
        "goal": "oxide",
    }

    def test_all_tiers_progression_on_the_wire(self):
        self.assertEqual(_wire(self.world), {t: True for t in RELIC_TIERS})

    def test_roundtrip_is_identity(self):
        self.assertEqual(
            _passthrough(self.world, {"relic_progression": _wire(self.world)}),
            {t: True for t in RELIC_TIERS})


class TestRelicClassificationNoSchemaBump(CTRTestBase):
    """relic_progression is ADDITIVE: it must not move schema_version."""

    run_default_tests = False
    options = {"warppad_unlock_requirements": "vanilla", "accessibility": "minimal"}

    def test_schema_version_unchanged(self):
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 6)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 6)
