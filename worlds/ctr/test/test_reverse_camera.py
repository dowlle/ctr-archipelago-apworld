"""#248 uses the existing weighted filler path and stable trap identity."""
from BaseClasses import ItemClassification
from . import CTRTestBase
from ..traps import DEFAULT_TRAP_WEIGHTS, TRAP_WEIGHT_KEYS


class TestReverseOnly(CTRTestBase):
    run_default_tests = False
    options = {"box_locations": True, "trap_fill_percentage": 100,
               "trap_weights": {key: int(key == "reverse_camera") for key in TRAP_WEIGHT_KEYS}}

    def test_pool_and_identity(self):
        drawn = [item for item in self.multiworld.itempool
                 if item.classification == ItemClassification.trap]
        self.assertGreater(len(drawn), 20)
        self.assertEqual({(item.name, item.code) for item in drawn},
                         {("Reverse Camera", 35010207)})
        self.assertEqual(len(self.multiworld.itempool),
                         len(self.multiworld.get_unfilled_locations(self.player)))
        self.assertEqual(self.world.fill_slot_data()["trap_identities"]["items"]["35010207"],
                         "reverse_camera")
        self.assertEqual(DEFAULT_TRAP_WEIGHTS["reverse_camera"], 2)


class TestReverseDisabled(CTRTestBase):
    run_default_tests = False
    options = {"box_locations": True, "trap_fill_percentage": 100,
               "trap_weights": {"reverse_camera": 0}}

    def test_disabled_retains_receipt_identity(self):
        self.assertNotIn("Reverse Camera", {i.name for i in self.multiworld.itempool})
        self.assertEqual(self.world.fill_slot_data()["trap_identities"]["items"]["35010207"],
                         "reverse_camera")
