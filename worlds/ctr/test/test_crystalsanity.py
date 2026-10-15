"""Crystal position checks inherit entry gates and retain the completion check."""
from . import CTRTestBase
from ..crystal_checks import CRYSTAL_CLASS, CRYSTAL_ARENAS, ARENA_LEVELS, INSTANCE_BASES
import unittest
from .test_cortex_vortex_track import _build, _ut_regen
from .test_content_plan import make_world, profile_options
from Options import OptionError


class TestCrystalsanity(CTRTestBase):
    run_default_tests = False
    options = {"crystalsanity": True, "accessibility": "full"}

    def test_exact_subset_and_wire(self):
        names={l.name for l in self.multiworld.get_locations(self.player)}
        self.assertEqual(len(set(CRYSTAL_CLASS.names()) & names),80)
        wire=self.world.fill_slot_data()
        self.assertIs(wire["ctr_options"]["crystalsanity"],True)
        self.assertEqual(wire["crystal_checks"]["version"],1)
        for ai,arena in enumerate(CRYSTAL_ARENAS):
            self.assertIn(f"{arena}: Crystal Challenge",names)
            row=wire["crystal_checks"]["arenas"][str(ARENA_LEVELS[ai])]
            self.assertEqual(row["instance_bases"],list(INSTANCE_BASES[ai]))
            self.assertEqual(row["locations"],[CRYSTAL_CLASS.code_for(arena,n) for n in range(1,21)])

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

    def test_off_preserves_wire_shape(self):
        names={l.name for l in self.multiworld.get_locations(self.player)}
        self.assertFalse(set(CRYSTAL_CLASS.names()) & names)
        wire=self.world.fill_slot_data()
        self.assertNotIn("crystal_checks",wire)
        self.assertNotIn("crystalsanity",wire["ctr_options"])


class TestCrystalsanityArenasOff(CTRTestBase):
    run_default_tests = False
    options = {"crystalsanity": True,"include_battle_arenas":False}

    def test_no_crystals_but_purple_items_remain(self):
        names={l.name for l in self.multiworld.get_locations(self.player)}
        self.assertFalse(set(CRYSTAL_CLASS.names()) & names)
        self.assertEqual(self.world.fill_slot_data()["crystal_checks"]["arenas"],{})
        self.assertEqual(sum(i.name=="Purple CTR Token" for i in self.multiworld.itempool),4)


class TestCrystalReconstruction(unittest.TestCase):
    def test_dropped_arena_has_neither_pickups_nor_wire_row(self):
        for level, arena in zip(ARENA_LEVELS, CRYSTAL_ARENAS):
            with self.subTest(arena=arena):
                mw = _build(dropped=level, crystalsanity=True)
                names = {loc.name for loc in mw.get_locations(1)}
                self.assertEqual(len(set(CRYSTAL_CLASS.names()) & names), 60)
                self.assertFalse(set(CRYSTAL_CLASS.location_name(arena,n) for n in range(1,21)) & names)
                wire = mw.worlds[1].fill_slot_data()
                self.assertNotIn(str(level), wire['crystal_checks']['arenas'])
                tracker = _ut_regen(wire)
                self.assertEqual({loc.name for loc in tracker.get_locations(1)}, names)
                self.assertEqual(tracker.worlds[1].fill_slot_data()['crystal_checks'], wire['crystal_checks'])

    def test_pending_content_profile_refuses_the_option(self):
        options = profile_options()
        options['crystalsanity'] = True
        with self.assertRaisesRegex(OptionError, 'crystalsanity'):
            make_world(options)
