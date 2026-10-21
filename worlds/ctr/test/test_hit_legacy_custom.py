"""Hit Character on legacy custom content (#133 PR 5c).

Ruling of 2026-10-21: the same Hit rule on custom tracks as on retail tracks,
in every room. On a normal (non-content-plan) room the Cortex Vortex pad track
and a custom track that took a Gem Cup over seat the encounter draw (native
LOAD_DriverMPK, AP_HitPadOpportunity), so both are Hit routes for every target,
guests included. A package whose measured `crates` flag is false rolls no
weapon and is no route.
"""
import copy
import unittest
from unittest import mock

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld, hit_character
from ..custom_tracks import BABY_T_PARK_EXAMPLE

PLAYER = 1
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=1, **options):
    options.setdefault("hit_character", True)
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _everything(mw):
    state = CollectionState(mw)
    for item in mw.itempool:
        state.collect(item, prevent_sweep=True)
    return state


def _rule(mw, cid):
    return mw.get_location(hit_character.HIT_CHARACTER_CLASS.location_name(cid), PLAYER).access_rule


class TestCortexVortexPadTrack(unittest.TestCase):
    def test_route_on_destination_110(self):
        mw = _build(cortex_vortex_track=True)
        world = mw.worlds[PLAYER]
        for cid in (0, 12):  # a default racer and a guest
            routes = hit_character._build_custom_routes(world, PLAYER, cid)
            self.assertEqual([(r.track, r.level_id) for r in routes], [("Cortex Vortex", 110)])
            pad = world.ctr_pad_by_destination["Cortex Vortex"]
            self.assertEqual(routes[0].hub, mw.get_entrance(pad, PLAYER).parent_region)

    def test_off_means_no_route(self):
        mw = _build(cortex_vortex_track=False)
        self.assertEqual(hit_character._build_custom_routes(mw.worlds[PLAYER], PLAYER, 3), [])

    def test_cortex_vortex_alone_carries_the_hit_checks(self):
        mw = _build(cortex_vortex_track=True)
        world = mw.worlds[PLAYER]
        with mock.patch.object(hit_character, "_build_ordinary_routes", return_value=[]):
            hit_character.install_rules(world, PLAYER)
        state = _everything(mw)
        for cid in (0, 9, 12, 15):
            self.assertTrue(_rule(mw, cid)(state), cid)
        cv = mw.get_region("Cortex Vortex", PLAYER)
        empty = CollectionState(mw)
        self.assertEqual(_rule(mw, 0)(empty), cv.can_reach(empty))


class TestCustomTrackOnACup(unittest.TestCase):
    def _world(self):
        return _build(custom_tracks={"baby-t-park": copy.deepcopy(BABY_T_PARK_EXAMPLE)}, include_gem_cups=True)

    def test_route_on_the_custom_region(self):
        mw = self._world()
        world = mw.worlds[PLAYER]
        entry = world.custom_tracks["baby-t-park"]
        from ..custom_track_ids import track_label
        for cid in (1, 13):
            routes = hit_character._build_custom_routes(world, PLAYER, cid)
            self.assertEqual([(r.track, r.level_id) for r in routes], [(track_label(entry), 104)])
        with mock.patch.object(hit_character, "_build_ordinary_routes", return_value=[]):
            hit_character.install_rules(world, PLAYER)
        state = _everything(mw)
        for cid in (1, 8, 13):
            self.assertTrue(_rule(mw, cid)(state), cid)

    def test_no_weapon_crates_no_route(self):
        # The release registry pins Baby T Park's flags, so a crateless
        # package is simulated on the resolved descriptor.
        mw = self._world()
        world = mw.worlds[PLAYER]
        world.custom_tracks["baby-t-park"]["flags"]["crates"] = False
        self.assertEqual(hit_character._build_custom_routes(world, PLAYER, 1), [])


class TestUnchangedWithoutCustomContent(unittest.TestCase):
    def test_plain_room_has_no_custom_route(self):
        mw = _build(cortex_vortex_track=False)
        self.assertEqual(hit_character._build_custom_routes(mw.worlds[PLAYER], PLAYER, 12), [])


if __name__ == "__main__":
    unittest.main()
