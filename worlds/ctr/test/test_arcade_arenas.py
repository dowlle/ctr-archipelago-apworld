"""Arena selection, fixed identities, entry logic and Tracker reconstruction."""
import copy
import json
import unittest
from Options import OptionError
from BaseClasses import CollectionState
from .test_content_plan import make_world, profile_options
from .. import arena_content as ac
from ..Locations import CTR_LOCATION_IDS

def arena_options(count=7, pickups=True):
    o=profile_options()
    o['include_arcade_arenas']=True
    o['crystalsanity']=pickups
    o['content_pool']['crystals']={'pool':'all','count':count}
    return o

class TestArcadeArenas(unittest.TestCase):
    def test_full_pool_stable_identity_and_balance(self):
        w=make_world(arena_options())
        p=w.ctr_content_plan
        self.assertEqual(len(p['entries']),26)
        self.assertEqual(len(p['checks']),166)
        self.assertEqual(len(w.multiworld.itempool),166)
        self.assertEqual(len({c['location'] for c in p['checks']}),166)
        self.assertEqual({e['arena_id'] for e in p['entries'] if e['kind']=='crystal'},set(range(18,25)))
        for e in p['entries']:
            if e['kind']!='crystal':continue
            lid=e['arena_id']
            checks=[c for c in p['checks'] if c['owner']==f'arena:{lid}']
            self.assertEqual([c['location'] for c in checks],[ac.completion_code(lid)]+[ac.pickup_code(lid,n) for n in range(1,21)])
            for c in checks:self.assertEqual(CTR_LOCATION_IDS[c['display_name']],c['location'])
        self.assertEqual(sum(i.name=='Purple CTR Token' for i in w.multiworld.itempool),0)
        self.assertEqual(p['required_features'],['content_plan_v1','crystal_entries_v1','crystal_pickups_v1','arcade_crystals_v1','surface_items_v1','pad_requirements_v1','pad_client_v1'])

    def test_added_arena_timers(self):
        # Decision 6, 2026-10-29: Parking Lot 1:05, Lab Basement 0:50, The North Bowl 1:30 (960 ticks per second).
        self.assertEqual({lid:ac.TIMERS[lid] for lid in (20,22,24)},{20:62400,22:86400,24:48000})
        self.assertEqual(ac.TIMERS[20]//960,65)
        self.assertEqual(ac.TIMERS[24]//960,50)
        self.assertEqual(ac.TIMERS[22]//960,90)

    def test_completion_only_and_retail_only(self):
        o=arena_options(pickups=False)
        w=make_world(o)
        self.assertEqual(len(w.ctr_content_plan['checks']),26)
        self.assertNotIn('crystal_pickups_v1',w.ctr_content_plan['required_features'])
        o['include_arcade_arenas']=False;o['content_pool']['crystals']['count']=4
        w=make_world(o)
        self.assertEqual({e['arena_id'] for e in w.ctr_content_plan['entries'] if e['kind']=='crystal'},set(ac.ARENAS)-set(ac.ARCADE))
        self.assertFalse(w.fill_slot_data()['ctr_options']['include_arcade_arenas'])

    def test_arenas_off_suppresses_subset(self):
        o=arena_options();o['include_battle_arenas']=False
        w=make_world(o)
        self.assertEqual(len(w.ctr_content_plan['checks']),19)
        self.assertNotIn('include_arcade_arenas',w.fill_slot_data()['ctr_options'])

    def test_tracker_uses_exact_plan_and_gates(self):
        w=make_world(arena_options())
        wire=json.loads(json.dumps(w.fill_slot_data()))
        tracker=make_world({},seed=999,passthrough=wire)
        self.assertEqual(tracker.fill_slot_data(),wire)
        for keys in range(5):
            reached=[]
            for world in (w,tracker):
                state=CollectionState(world.multiworld)
                for _ in range(keys):state.collect(world.create_item('Key'),True)
                reached.append({l.address for l in world.multiworld.get_reachable_locations(state,1)})
                for level in ac.ARENAS:
                    complete=world.multiworld.get_location(ac.ARENAS[level]+': Crystal Challenge',1)
                    for n in range(1,21):
                        pickup=world.multiworld.get_location(f'{ac.ARENAS[level]}: Crystal {n:02d}',1)
                        self.assertIs(pickup.parent_region,complete.parent_region)
                        self.assertEqual(pickup.can_reach(state),complete.can_reach(state))
            self.assertEqual(*reached)

    def test_tracker_restores_persisted_room_arrays(self):
        from NetUtils import convert_to_base_types
        wire=make_world(arena_options()).fill_slot_data()
        persisted=convert_to_base_types(wire)
        self.assertIs(type(persisted['content_plan']['packages']),tuple)
        tracker=make_world({},seed=999,passthrough=persisted)
        self.assertEqual(tracker.fill_slot_data(),wire)
        # Normalization must not coerce forged scalar types into valid values.
        forged=copy.deepcopy(wire)
        next(e for e in forged['content_plan']['entries'] if e['kind']=='crystal')['target']=20.0
        with self.assertRaises(OptionError):make_world({},passthrough=convert_to_base_types(forged))

    def test_pool_count_required_entries_and_invalid_requests(self):
        o=arena_options(2);o['content_pool']['crystals']={'pool':[20,22,24],'count':{'min':2,'max':2}}
        o['content_pool']['required_entries'].append('arena:24')
        for seed in range(10):
            w=make_world(o,seed=seed)
            levels={e['arena_id'] for e in w.ctr_content_plan['entries'] if e['kind']=='crystal'}
            self.assertEqual(len(levels),2);self.assertIn(24,levels);self.assertTrue(levels<={20,22,24})
        invalids=[{'pool':[20,20],'count':1},{'pool':[17],'count':1},{'count':True},
                  {'count':8},{'count':{'min':3,'max':2}}]
        for request in invalids:
            bad=arena_options();bad['content_pool']['crystals']=request
            with self.subTest(request=request),self.assertRaises(OptionError):make_world(bad)
        bad=arena_options(1);bad['include_arcade_arenas']=False;bad['content_pool']['crystals']['pool']=[20]
        with self.assertRaises(OptionError):make_world(bad)
        with self.assertRaises(OptionError):make_world({'include_arcade_arenas':True})

    def test_refuses_forged_runtime_contract(self):
        original=make_world(arena_options()).fill_slot_data()
        def arena(w):return next(e for e in w['content_plan']['entries'] if e['kind']=='crystal')
        mutations=[lambda w:arena(w).__setitem__('target',19),
                   lambda w:arena(w).__setitem__('time_limit_ticks',1),
                   lambda w:w['content_plan']['required_features'].remove('arcade_crystals_v1'),
                   lambda w:w['content_plan']['checks'].pop(),
                   lambda w:w['ctr_options'].__setitem__('crystalsanity',False),
                   lambda w:w['ctr_options'].__setitem__('include_arcade_arenas',False)]
        for i,mutate in enumerate(mutations):
            wire=copy.deepcopy(original);mutate(wire)
            with self.subTest(mutation=i),self.assertRaises(OptionError):make_world({},passthrough=wire)
