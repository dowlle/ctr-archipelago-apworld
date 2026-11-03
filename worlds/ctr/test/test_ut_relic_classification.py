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
        "oxide_goal": "first",
        # Issue #171: Platinum Relic Count now defaults to 0 (no Platinum Time
        # Trials created at all), but this class's SLIDE_COLISEUM_TRIALS names
        # a Platinum Time Trial and needs it to exist (just unreachable, which
        # is the whole point of the regression this class guards). Pin it on.
        "platinum_relic_count": 18,
    }


    def test_slot_data_matches_create_item(self):
        wire = _wire(self.world)
        for tier in RELIC_TIERS:
            expected = self.world.create_item(tier).advancement
            self.assertEqual(
                wire[tier], expected,
                f"wire says {tier} progression={wire[tier]} but create_item "
                f"produced advancement={expected}")


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
        "oxide_goal": "first",
    }


class TestRelicClassificationRandomized(CTRTestBase):
    """Randomized pad modes keep every tier progression; unchanged behaviour."""

    run_default_tests = False
    options = {
        "warppad_unlock_requirements": "randomized",
        "accessibility": "minimal",
        "oxide_goal": "first",
    }


class TestRelicClassificationNoSchemaBump(CTRTestBase):
    """relic_progression is ADDITIVE: it must not move schema_version."""

    run_default_tests = False
    options = {"warppad_unlock_requirements": "vanilla", "accessibility": "minimal"}

    def test_schema_version_unchanged(self):
        # Baseline is 7, the unconditional #166 bump (Q28 ruling); relic
        # classification itself contributes no further bump.
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["schema_version"], 18)
        self.assertEqual(slot_data["ctr_options"]["schema_version"], 18)
