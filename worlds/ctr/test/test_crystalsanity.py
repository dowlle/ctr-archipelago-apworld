"""Crystal position checks inherit entry gates and retain the completion check."""
from . import CTRTestBase
from ..crystal_checks import CRYSTAL_CLASS, CRYSTAL_ARENAS, ARENA_LEVELS, INSTANCE_BASES
import unittest
from .test_content_plan import make_world, profile_options
from Options import OptionError


class TestCrystalsanity(CTRTestBase):
    run_default_tests = False
    options = {"crystalsanity": True, "accessibility": "full"}


    def test_pickups_use_the_same_entry_as_completion(self):
        state=self.multiworld.state.copy()
        for arena in CRYSTAL_ARENAS:
            complete=self.multiworld.get_location(f"{arena}: Crystal Challenge",self.player)
            for n in range(1,21):
                loc=self.multiworld.get_location(CRYSTAL_CLASS.location_name(arena,n),self.player)
                self.assertIs(loc.parent_region,complete.parent_region)
                self.assertTrue(loc.access_rule(state)) # no guessed weapon/boost/stat term
                self.assertEqual(loc.can_reach(state),complete.can_reach(state))

    def test_pool_balanced(self):
        self.assertEqual(len(self.multiworld.itempool),len(self.multiworld.get_unfilled_locations(self.player)))


class TestCrystalsanityOff(CTRTestBase):
    run_default_tests = False
    options = {"crystalsanity": False}



class TestCrystalsanityArenasOff(CTRTestBase):
    run_default_tests = False
    options = {"crystalsanity": True,"include_battle_arenas":False}



class TestCrystalReconstruction(unittest.TestCase):

    def test_content_profile_without_arenas_keeps_wire_shape(self):
        options = profile_options()
        options['crystalsanity'] = True
        world = make_world(options)
        self.assertEqual(world.fill_slot_data(), make_world(profile_options()).fill_slot_data())
