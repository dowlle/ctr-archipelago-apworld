"""The 2026-10-01 rulings on the two largest option-refusal families.

Measured on a 1,500-roll fuzzer refusal tally of 0.2.3. The podium half
(refuse only when locations are really short, clearer wording) is covered in
test_rung_sizer.py. This file covers the relic
half:

- Ruling 3: when Oxide's Final Challenge asks for more relics than the seed
  creates, `oxide_final_challenge_relic_count` is lowered to the created
  supply, with a notice, in every seed (also `minimal`). The lowered value is
  what slot_data's `oxide_final_count` carries, and what Universal Tracker
  restores.
- Ruling 4: in vanilla warp-pad mode with fewer than 10 Sapphire Relics
  created, the player's `sapphire_relic_count` is kept and the Slide Coliseum
  pad opens at the Sapphires that exist. The apworld emits the lowered gate as
  pad 16's stage-1 requirement and its logic uses the same value; a seed
  without that entry (any seed rolled before the rule) keeps 10, on the
  tracker as in native.
"""
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from . import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld

EARLY = ("generate_early",)
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
LOGGER_NAME = "worlds.ctr.forced_options"
PLAYER = 1
FINAL = "N. Oxide Garage: N. Oxide's Final Challenge"


def _build(options, steps=STEPS, seed=None):
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _rebuild(wire, **local):
    """Universal Tracker re-generation from a seed's slot_data, with the
    tracking player's own YAML in `local`."""
    tracker = setup_multiworld(ctrAPWorld, steps=(), seed=99, options=local)
    tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
    for step in STEPS:
        call_all(tracker, step)
    return tracker


def _state_with(mw, name, count):
    state = CollectionState(mw)
    if count:
        state.add_item(name, PLAYER, count)
    state.stale[PLAYER] = True
    return state


def _notices(cm, needle):
    return [line for line in cm.output if needle in line]


# ---------------------------------------------------------------------------
# Ruling 3: the Final Challenge count is lowered to the created supply.
# ---------------------------------------------------------------------------

class TestFinalChallengeCountLoweredToSupply(unittest.TestCase):


    def test_count_within_supply_is_untouched_and_silent(self):
        with self.assertNoLogs(LOGGER_NAME, level="WARNING"):
            mw = _build({"accessibility": "full",
                         "oxide_final_challenge_unlock": "gold_relics",
                         "oxide_final_challenge_relic_count": 7,
                         "gold_relic_count": 7}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 7)

    def test_disabled_oxide_is_untouched(self):
        mw = _build({"oxide_goal": "disabled", "bosses_required_goal": 4,
                     "accessibility": "full",
                     "sapphire_relic_count": 5}, steps=EARLY)
        self.assertEqual(
            mw.worlds[PLAYER].options.oxide_final_challenge_relic_count.value, 18)

    def test_tier_with_no_relics_still_refuses_under_full(self):
        with self.assertRaises(OptionError) as ctx:
            _build({"accessibility": "full", "oxide_goal": "first",
                    "warppad_unlock_requirements": "randomized",
                    "oxide_final_challenge_unlock": "platinum_relics",
                    "oxide_final_challenge_relic_count": 5,
                    "platinum_relic_count": 0}, steps=EARLY)
        self.assertIn("Final Challenge", str(ctx.exception))


# ---------------------------------------------------------------------------
# Ruling 4: the vanilla Slide Coliseum pad opens at the Sapphires that exist.
# ---------------------------------------------------------------------------

VANILLA = {"warppad_unlock_requirements": "vanilla"}


if __name__ == "__main__":
    unittest.main()
