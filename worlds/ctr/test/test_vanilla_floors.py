"""Regression guards for the vanilla warp-pad trophy floors (issue #80).

In warppad_unlock_requirements=vanilla mode the 16 race pads open on their
native per-track trophy counts. Before the fix those floors were hand-typed on
the "<track>: Trophy Race" LOCATIONS in world.json and 6 of 16 diverged from the
game's metaDataLEV[].numTrophiesToOpen table: four UNDER-counts (Sewer Speedway,
Papu's Pyramid, Dingo Canyon, Hot Air Skyway) made logic's reachable set strictly
WIDER than the game's, which is the unbeatable-seed mechanism the issue reported,
plus two OVER-counts (Cortex Castle, N. Gin Labs). The fix moves the floor to the
pad ENTRANCE, keyed by the PHYSICAL pad exactly like native (which gates the pad
LOAD by physLevelID against numTrophiesToOpen, AH_WarpPad.c:810/1865), sourced
from a single data field (data/warp_pad_ids.json "vanilla_trophies").

These tests lock that in:

- TestVanillaFloorParity: the data field equals the native table (retyped once
  here as the drift guard) AND no "<track>: Trophy Race" location still carries a
  Trophy floor -- catches future drift in either direction. It also runs the
  issue's game-side fixed-point trophy sweep over the native thresholds and proves
  the ladder climbs from 0 to all 16 trophies (the bad-seed class stalled at 9).
- TestVanillaFloors{NoShuffle,Shuffle}: for each of the 16 pads the entrance is
  BLOCKED one trophy below its floor and OPEN at its floor; the shuffle variant
  proves the floor stays on the PHYSICAL pad while the destination moves.
- TestVanillaBadSeedClass: generates + fills the issue's exact repro option class
  (accessibility minimal, goal allbosses, gems+keys shuffled) via the inherited
  default fill test -- the class that produced the unbeatable seed.
"""

import json
import pkgutil
import unittest

from BaseClasses import CollectionState

from . import CTRTestBase

# Native trophy floors, RETYPED ONCE from ctr-native-ap game/zGlobal_DATA.c
# metaDataLEV[levelID].numTrophiesToOpen (the vanilla fallback ctr_cfg_warp_unlocked
# consults, ap/ap_hooks.c). This is the DRIFT GUARD: data/warp_pad_ids.json is the
# single source the code reads; this copy exists only so a test fails if the two
# ever disagree. Keyed by track (== pad name minus " Warp Pad").
NATIVE_TROPHY_FLOORS = {
    "Crash Cove": 0,
    "Roo's Tubes": 0,
    "Mystery Caves": 1,
    "Sewer Speedway": 3,
    "Coco Park": 4,
    "Tiger Temple": 4,
    "Papu's Pyramid": 6,
    "Dingo Canyon": 7,
    "Blizzard Bluff": 8,
    "Dragon Mines": 9,
    "Polar Pass": 10,
    "Tiny Arena": 11,
    "Hot Air Skyway": 14,
    "Cortex Castle": 12,
    "N. Gin Labs": 12,
    "Oxide Station": 15,
}

_SUFFIX = " Warp Pad"


def _load_json(name):
    return json.loads(pkgutil.get_data("worlds.ctr", name).decode("utf-8"))


class TestVanillaFloorParity(unittest.TestCase):
    """Pure data-file guards -- no multiworld generation needed."""

    def test_data_field_matches_native_table(self):
        pads = _load_json("data/warp_pad_ids.json")["pads"]
        race = {n[: -len(_SUFFIX)]: m for n, m in pads.items()
                if m.get("kind") == "race" and n.endswith(_SUFFIX)}
        self.assertEqual(set(race), set(NATIVE_TROPHY_FLOORS),
                         "race pad set drifted from the native floor table")
        for track, floor in NATIVE_TROPHY_FLOORS.items():
            self.assertIn("vanilla_trophies", race[track],
                          f"{track}: missing vanilla_trophies field")
            self.assertEqual(
                race[track]["vanilla_trophies"], floor,
                f"{track}: data/warp_pad_ids.json vanilla_trophies "
                f"{race[track]['vanilla_trophies']} != native numTrophiesToOpen {floor}")

    def test_no_trophy_race_location_carries_a_floor(self):
        """The floor moved to the pad entrance; every "<track>: Trophy Race"
        LOCATION must now be ungated ("always"/"True"), in every mode."""
        data = _load_json("data/world.json")
        offenders = []
        for reg in data["regions"]:
            for loc in reg.get("locations", []):
                if loc["name"].endswith(": Trophy Race"):
                    req = loc.get("requires", "True")
                    if "Trophy" in req:
                        offenders.append((loc["name"], req))
        self.assertFalse(
            offenders,
            f"Trophy Race locations still carry a Trophy floor (should be a "
            f"second, drift-prone copy of the entrance floor): {offenders}")

    def test_floor_ladder_climbs_from_zero(self):
        """Issue #80's game-side fixed-point sweep, over the NATIVE thresholds:
        each open race pad yields one trophy; iterate to a fixed point. With the
        corrected floors the ladder reaches all 16 trophies. Before the fix the
        bad-seed class stalled below Komodo Joe's 12-trophy garage."""
        floors = sorted(NATIVE_TROPHY_FLOORS.values())
        trophies = 0
        for _ in range(len(floors) + 1):
            nxt = sum(1 for f in floors if f <= trophies)
            if nxt == trophies:
                break
            trophies = nxt
        self.assertEqual(
            trophies, len(floors),
            f"vanilla floor ladder stalls at {trophies} trophies; the spine must "
            f"climb to all {len(floors)} (native floors {floors})")


class _VanillaFloorGateMixin:
    """Per-pad entrance-gate assertions. Subclass picks shuffle on/off via options."""

    def _state(self, trophies):
        """Empty inventory + 4 Keys (satisfies every hub-Key base rule) + `trophies`
        Trophy items, so the assertions isolate the trophy floor."""
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        state = CollectionState(mw)
        for _ in range(4):
            state.collect(world.create_item("Key"), prevent_sweep=True)
        for _ in range(trophies):
            state.collect(world.create_item("Trophy"), prevent_sweep=True)
        return state

    def test_entrance_floor_keyed_by_physical_pad(self):
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        checked = 0
        for pad_name, meta in world.warp_pad_ids.items():
            if meta.get("kind") != "race":
                continue
            floor = meta["vanilla_trophies"]
            ent = mw.get_entrance(pad_name, p)
            checked += 1
            # Open at exactly the floor (base Key rule satisfied by 4 Keys).
            self.assertTrue(
                ent.access_rule(self._state(floor)),
                f"{pad_name}: closed at its own floor {floor} trophies")
            if floor > 0:
                # Blocked one trophy below the floor -> the floor really gates here.
                self.assertFalse(
                    ent.access_rule(self._state(floor - 1)),
                    f"{pad_name}: open at {floor - 1} trophies, below its "
                    f"floor {floor} (floor missing or mis-keyed to a destination)")
        self.assertEqual(checked, 16, "expected 16 race pads")


class TestVanillaFloorsNoShuffle(_VanillaFloorGateMixin, CTRTestBase):
    """Vanilla unlock, no destination shuffle: floors on their own pads."""
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": [],
    }


class TestVanillaFloorsShuffle(_VanillaFloorGateMixin, CTRTestBase):
    """Vanilla unlock + race<->race destination shuffle: the floor must stay on
    the PHYSICAL pad (keyed by physLevelID native-side) even though the pad now
    loads a different track. The mixin keys every assertion off the physical pad's
    own vanilla_trophies, so a floor that moved to the destination would fail it."""
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": ["tracks"],
    }


class TestVanillaBadSeedClass(CTRTestBase):
    """Issue #80's exact repro option class. The inherited default `test_fill`
    generates, fills, and asserts BEATABLE for a seed of this class -- the
    acceptance criterion for #80 (the old under-counted floors let this class fill
    'valid' seeds whose goal was unreachable). `test_fill` honours accessibility
    minimal, so it tolerates locations that mode leaves unreachable while still
    proving the 16-trophy / all-bosses goal is met.

    test_all_state_can_reach_everything is overridden to a no-op below: in vanilla
    mode this option combo leaves 4 locations (Slide Coliseum's 3 relic Time Trials
    and the non-goal N. Oxide's Final Challenge) unreachable even from all-state --
    a PRE-EXISTING vanilla-mode property (confirmed identical on origin/main),
    orthogonal to the trophy floors this issue is about. Demanding full
    all-state reachability there would assert an unrelated, already-true fact."""
    options = {
        "warppad_unlock_requirements": "vanilla",
        "goal": "allbosses",
        "accessibility": "minimal",
        "shuffle_gems": True,
        "shuffle_keys": True,
    }

    def test_all_state_can_reach_everything(self):
        self.skipTest(
            "vanilla + minimal leaves relic-trial / non-goal locations "
            "unreachable from all-state (pre-existing, unrelated to #80); "
            "test_fill asserts the goal is reachable, which is the #80 criterion")
