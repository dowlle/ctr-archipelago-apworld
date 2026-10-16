"""Four ordered firsts are independent of the existing Cup points reward."""
import copy
import unittest
from NetUtils import convert_to_base_types
from Options import OptionError
from BaseClasses import CollectionState
from .test_content_plan import make_world, profile_options
from ..cup_checks import CUP_SWEEP_CLASS, GEM_CUPS
from ..gem_cup_legs import cup_legs_to_wire
from ..cup_sweeps import install_rules


class TestCupSweeps(unittest.TestCase):
    def test_default_off_and_five_minted_identities_on(self):
        off=make_world({})
        on=make_world({'cup_sweep_checks':True})
        wire=on.fill_slot_data()
        self.assertNotIn('cup_sweep_checks',off.fill_slot_data())
        self.assertNotIn('cup_sweep_checks',off.fill_slot_data()['ctr_options'])
        self.assertEqual(len(on.multiworld.get_locations(1)),len(off.multiworld.get_locations(1))+5)
        for i,cup in enumerate(GEM_CUPS):
            loc=on.multiworld.get_location(CUP_SWEEP_CLASS.location_name(cup),1)
            gem=on.multiworld.get_location(cup+': Gem',1)
            self.assertIs(loc.parent_region,gem.parent_region)
            self.assertEqual(loc.address,35028300+i)
            self.assertEqual(wire['cup_sweep_checks']['cups'][str(100+i)]['location'],loc.address)
        self.assertEqual(len(on.multiworld.itempool),len(on.multiworld.get_unfilled_locations(1)))

    def test_exported_win_logic_matches_server_rules(self):
        import random
        from .test_win_logic_parity import check_seed
        for boost in ('off','shared_global','per_character'):
            w=make_world({'cup_sweep_checks':True,'progressive_boost':boost,
                          'randomize_gem_cup_tracks':True,'racer_locked_pads':True},seed=19)
            wire=w.fill_slot_data()
            for code in range(35028300,35028305):
                self.assertEqual(wire['win_logic']['checks'][str(code)]['kind'],'gem')
            self.assertEqual(check_seed(w.multiworld,random.Random(42),states_per_seed=20),[])

    def test_cortex_dropped_cup_has_no_unreachable_sweep(self):
        from .test_cortex_vortex_track import _build, _ut_regen
        for i,cup in enumerate(GEM_CUPS):
            with self.subTest(cup=cup):
                mw=_build(dropped=100+i,cup_sweep_checks=True)
                names={loc.name for loc in mw.get_locations(1)}
                self.assertNotIn(CUP_SWEEP_CLASS.location_name(cup),names)
                wire=mw.worlds[1].fill_slot_data()
                self.assertEqual(len(wire['cup_sweep_checks']['cups']),4)
                self.assertNotIn(str(100+i),wire['cup_sweep_checks']['cups'])
                self.assertEqual(len(mw.itempool),len(mw.get_unfilled_locations(1)))
                tracker=_ut_regen(convert_to_base_types(wire))
                self.assertEqual(tracker.worlds[1].fill_slot_data()['cup_sweep_checks'],wire['cup_sweep_checks'])

    def test_displaced_cup_has_no_sweep(self):
        from .test_custom_tracks import BABY_T_PARK
        w=make_world({'cup_sweep_checks':True,'custom_tracks':BABY_T_PARK})
        names={loc.name for loc in w.multiworld.get_locations(1)}
        self.assertNotIn('Purple Gem Cup: Win All Legs',names)
        self.assertEqual(len(w.fill_slot_data()['cup_sweep_checks']['cups']),4)
        self.assertEqual(len(w.multiworld.itempool),len(w.multiworld.get_unfilled_locations(1)))

    def test_randomized_legs_and_one_lap_cups_keep_exact_order(self):
        options={'cup_sweep_checks':True,'randomize_gem_cup_tracks':True}
        a=make_world(options,seed=19)
        b=make_world(dict(options,one_lap_cups=True),seed=19)
        self.assertEqual(a.fill_slot_data()['cup_sweep_checks'],b.fill_slot_data()['cup_sweep_checks'])
        legs=cup_legs_to_wire(a.gem_cup_legs_table)
        for key,row in a.fill_slot_data()['cup_sweep_checks']['cups'].items():
            self.assertEqual(row['legs'],legs[key])

    def test_tracker_roundtrip_through_real_room_persistence(self):
        w=make_world({'cup_sweep_checks':True,'randomize_gem_cup_tracks':True},seed=19)
        wire=w.fill_slot_data()
        other=make_world({},seed=987,passthrough=convert_to_base_types(wire))
        self.assertEqual(other.fill_slot_data()['cup_sweep_checks'],wire['cup_sweep_checks'])
        self.assertEqual({l.address for l in other.multiworld.get_locations(1)},
                         {l.address for l in w.multiworld.get_locations(1)})
        # An old seed must override a tracker's local enabled option.
        old=make_world({}).fill_slot_data()
        tracker=make_world({'cup_sweep_checks':True},passthrough=old)
        self.assertFalse(tracker.options.cup_sweep_checks.value)

    def test_saved_block_rejects_forged_identity_leg_and_flag(self):
        wire=make_world({'cup_sweep_checks':True}).fill_slot_data()
        for mutation in range(5):
            bad=copy.deepcopy(wire)
            if mutation==0: bad['cup_sweep_checks']['cups']['100']['location']+=1
            if mutation==1: bad['cup_sweep_checks']['cups']['100']['legs'][0]=999
            if mutation==2: bad['cup_sweep_checks']['version']=True
            if mutation==3: bad['ctr_options']['cup_sweep_checks']=1
            if mutation==4: del bad['cup_sweep_checks']
            with self.subTest(mutation=mutation),self.assertRaises(OptionError):
                make_world({},passthrough=bad)

    def test_finish_rule_is_bound_to_cup_racer_not_standalone_track(self):
        from ..progressive_capability import destination_pad_name
        w=make_world({'cup_sweep_checks':True,'progressive_boost':'per_character','character_unlocks':False,'itemsanity':False,
                      'logic_difficulty':'easy'})
        cup=GEM_CUPS[0]
        # Repeated logical tracks still occupy four ordered slots. This Cup
        # needs USF, owned by its own selected racer even if another track's
        # pad is locked to a different racer.
        w.gem_cup_legs[cup]=['Hot Air Skyway']*4
        w.ctr_racer_locks={destination_pad_name(w,cup):'Crash Bandicoot',
                           destination_pad_name(w,'Hot Air Skyway'):'Coco Bandicoot'}
        loc=w.multiworld.get_location(CUP_SWEEP_CLASS.location_name(cup),1)
        # Reinstall only the new rule on a clean location rule.
        loc.access_rule=lambda state:True
        install_rules(w,1)
        state=CollectionState(w.multiworld)
        self.assertFalse(loc.access_rule(state))
        from ..progressive_capability import boost_item_name
        for _ in range(2): state.collect(w.create_item(boost_item_name('Coco Bandicoot')),True)
        self.assertFalse(loc.access_rule(state))
        for _ in range(2): state.collect(w.create_item(boost_item_name('Crash Bandicoot')),True)
        self.assertTrue(loc.access_rule(state))
        self.assertEqual(loc.parent_region.name,cup)

    def test_profile_without_cups_is_unchanged(self):
        opts=profile_options()
        baseline=make_world(opts).fill_slot_data()
        opts['cup_sweep_checks']=True
        self.assertEqual(make_world(opts).fill_slot_data(),baseline)
