"""#455 activates the minted identity through the existing weighted filler draw."""
from BaseClasses import ItemClassification
from . import CTRTestBase
from ..traps import TRAP_WEIGHT_KEYS,DEFAULT_TRAP_WEIGHTS

class TestClockOnly(CTRTestBase):
    run_default_tests=False
    options={'box_locations':True,'trap_fill_percentage':100,
             'trap_weights':{key:int(key=='clocked_out') for key in TRAP_WEIGHT_KEYS}}

    def test_minted_identity_is_drawn_and_pool_balances(self):
        drawn=[item for item in self.multiworld.itempool if item.classification==ItemClassification.trap]
        self.assertGreater(len(drawn),20)
        self.assertEqual({(item.name,item.code) for item in drawn},{('Clocked Out',35010206)})
        self.assertEqual(len(self.multiworld.itempool),len(self.multiworld.get_unfilled_locations(self.player)))
        self.assertEqual(self.world.fill_slot_data()['trap_identities']['items']['35010206'],'clocked_out')

class TestClockDisabled(CTRTestBase):
    run_default_tests=False
    options={'box_locations':True,'trap_fill_percentage':100,'trap_weights':{'clocked_out':0}}

    def test_zero_weight_excludes_clock_but_keeps_identity_for_received_items(self):
        self.assertNotIn('Clocked Out',{i.name for i in self.multiworld.itempool})
        self.assertEqual(self.world.fill_slot_data()['trap_identities']['items']['35010206'],'clocked_out')

class TestClockDefault(CTRTestBase):
    run_default_tests=False
    options={'box_locations':True,'trap_fill_percentage':100}

    def test_default_weight_is_positive_and_can_draw_clock(self):
        self.assertEqual(DEFAULT_TRAP_WEIGHTS['clocked_out'],3)
        self.assertIn('Clocked Out',{i.name for i in self.multiworld.itempool})
