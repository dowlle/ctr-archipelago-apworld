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

# Wire encoding (content_playthrough.to_slot_req): type 2 = Keys, colour -1.
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



    def _state_without_keys(self):
        state = CollectionState(self.multiworld)
        for item in self.multiworld.itempool:
            if item.player == self.player and item.name != "Key":
                state.collect(item, True)
        return state

    def _loc(self, name):
        return self.multiworld.get_location(name, self.player)



class TestVanillaDensityOffKeepsOldBehaviour(_VanillaBase):
    options = {
        "warppad_unlock_requirements": "vanilla",
        "two_stage_density": "off",
        "warp_pad_shuffle_categories": [],
    }



class TestVanillaWithDestinationShuffle(_VanillaBase):
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": ["tracks"],
    }

