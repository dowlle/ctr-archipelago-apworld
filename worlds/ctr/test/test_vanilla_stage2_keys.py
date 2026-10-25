"""Vanilla unlock mode gates each track's stage 2 on its hub Keys (issue #499).

The retail game opens a track's CTR Token Challenge and relic Time Trials only
after that hub's boss is beaten. world.json records that as has('Key', N) on
those locations, but Rules.add_time_trial_and_ctr_requirements replaces their
rule with the Trophy Race reference, and vanilla mode sent no stage 2, so
native opened the menu with the trophy. Vanilla mode now emits the hub Key
count as a real stage 2: slot_data on the physical pad, the logic term on the
destination track, so game and logic read the same requirement.
"""

from BaseClasses import CollectionState

from . import CTRTestBase

# Wire encoding (warp_pad_logic.to_slot_req): type 2 = Keys, colour -1.
_TYPE_KEY = 2

# Retail hub of each trophy track, as Keys needed for its stage 2.
_EXPECTED_KEYS = {
    "Crash Cove": 1, "Roo's Tubes": 1, "Mystery Caves": 1, "Sewer Speedway": 1,
    "Coco Park": 2, "Tiger Temple": 2, "Papu's Pyramid": 2, "Dingo Canyon": 2,
    "Blizzard Bluff": 3, "Dragon Mines": 3, "Polar Pass": 3, "Tiny Arena": 3,
    "N. Gin Labs": 4, "Cortex Castle": 4, "Hot Air Skyway": 4,
    "Oxide Station": 4,
}


class _VanillaBase(CTRTestBase):
    run_default_tests = False
    auto_construct = False

    def _wire(self):
        return self.world.fill_slot_data()["warp_pad_unlock"]


class TestVanillaStage2Keys(_VanillaBase):
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": [],
    }

    def setUp(self):
        super().setUp()
        self.world_setup(seed=499)

    def test_concrete_terms_match_retail_hubs(self):
        self.assertEqual(
            dict(self.world.warp_pad_unlock_stage2_concrete),
            {t: ("Key", n) for t, n in _EXPECTED_KEYS.items()})

    def test_wire_rows_carry_the_same_keys(self):
        wire = self._wire()
        for track, n in _EXPECTED_KEYS.items():
            lid = self.world.warp_pad_ids[f"{track} Warp Pad"]["level_id"]
            with self.subTest(track=track):
                self.assertEqual(
                    wire[str(lid)]["stage2"],
                    {"type": _TYPE_KEY, "count": n, "colour": -1})
                # Stage 1 stays type 0: native keeps its vanilla trophy floor.
                self.assertEqual(wire[str(lid)]["stage1"]["type"], 0)

    def _state_without_keys(self):
        state = CollectionState(self.multiworld)
        for item in self.multiworld.itempool:
            if item.player == self.player and item.name != "Key":
                state.collect(item, True)
        return state

    def _loc(self, name):
        return self.multiworld.get_location(name, self.player)

    def test_stage2_locations_need_the_keys(self):
        state = self._state_without_keys()
        # Hub 1: the Trophy Race is open, its stage 2 waits for the first Key.
        self.assertTrue(self._loc("Crash Cove: Trophy Race").can_reach(state))
        self.assertFalse(
            self._loc("Crash Cove: CTR Token Challenge").can_reach(state))
        self.assertFalse(
            self._loc("Crash Cove: Sapphire Time Trial").can_reach(state))
        state.collect(self.world.create_item("Key"), True)
        self.assertTrue(
            self._loc("Crash Cove: CTR Token Challenge").can_reach(state))
        # Hub 2: one Key opens the hub and its Trophy Races, the second Key
        # opens their stage 2.
        self.assertTrue(self._loc("Coco Park: Trophy Race").can_reach(state))
        self.assertFalse(
            self._loc("Coco Park: CTR Token Challenge").can_reach(state))
        state.collect(self.world.create_item("Key"), True)
        self.assertTrue(
            self._loc("Coco Park: CTR Token Challenge").can_reach(state))


class TestVanillaDensityOffKeepsOldBehaviour(_VanillaBase):
    options = {
        "warppad_unlock_requirements": "vanilla",
        "two_stage_density": "off",
        "warp_pad_shuffle_categories": [],
    }

    def test_no_stage2_with_density_off(self):
        self.world_setup(seed=499)
        self.assertEqual(dict(self.world.warp_pad_unlock_stage2_concrete), {})
        for lid, row in self._wire().items():
            with self.subTest(lid=lid):
                self.assertEqual(row["stage2"]["type"], 0)


class TestVanillaWithDestinationShuffle(_VanillaBase):
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": ["tracks"],
    }

    def test_physical_pad_carries_its_destination_hub(self):
        for seed in (1, 2, 3, 499):
            with self.subTest(seed=seed):
                self.world_setup(seed=seed)
                world = self.world
                wire = self._wire()
                id_to_track = {m["level_id"]: n[: -len(" Warp Pad")]
                               for n, m in world.warp_pad_ids.items()
                               if n.endswith(" Warp Pad")}
                for pad_name, dest_lid in world.warp_pad_map.items():
                    meta = world.warp_pad_ids.get(pad_name)
                    if not meta or meta.get("kind") != "race":
                        continue
                    dest = id_to_track.get(dest_lid)
                    n = _EXPECTED_KEYS.get(dest)
                    row = wire[str(meta["level_id"])]["stage2"]
                    if n is None:
                        self.assertEqual(row["type"], 0)
                    else:
                        self.assertEqual(
                            row, {"type": _TYPE_KEY, "count": n, "colour": -1})
                        self.assertEqual(
                            world.warp_pad_unlock_stage2_concrete[dest],
                            ("Key", n))
