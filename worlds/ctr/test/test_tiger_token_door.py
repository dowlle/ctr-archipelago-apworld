"""Full-token door dependency and physical-letter independence, issue 335."""
import unittest
from .test_lettersanity import _build, _collect_all, STEPS
from ..item_boxes import TIGER_TEMPLE_DOOR_OPENERS
from ..lettersanity import LETTERSANITY_CLASS
from .. import ctrAPWorld
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

TOKEN = 'Tiger Temple: CTR Token Challenge'


class TestTigerTokenDoor(unittest.TestCase):
    def check_world(self, mw):
        world = mw.worlds[1]
        mode = int(world.options.lettersanity.value)
        selected = world.options._lettersanity_selected.get('Tiger Temple', ())
        physical_requirements = {0: {'C', 'T', 'R'}, 1: {'C', 'T', 'R'},
                                 2: set(selected), 3: {'C', 'T', 'R'}}
        gated = bool(world.options.itemsanity.value) and 'R' in physical_requirements[mode]
        state = _collect_all(mw, exclude=set(TIGER_TEMPLE_DOOR_OPENERS))
        self.assertTrue(all(state.count(x, 1) == 0 for x in TIGER_TEMPLE_DOOR_OPENERS))
        self.assertEqual(state.can_reach(TOKEN, 'Location', 1), not gated)
        for letter in selected if mode in (1, 2) else ():
            name = LETTERSANITY_CLASS.location_name('Tiger Temple', letter)
            self.assertEqual(state.can_reach(name, 'Location', 1),
                             not (world.options.itemsanity.value and letter == 'R'))
        for opener in TIGER_TEMPLE_DOOR_OPENERS:
            control = _collect_all(mw, exclude=set(TIGER_TEMPLE_DOOR_OPENERS))
            control.add_item(opener, 1, 1)
            self.assertTrue(control.can_reach(TOKEN, 'Location', 1))

    def test_modes_counts_itemsanity_and_tracker(self):
        for mode in ('off', 'locations_only', 'locations_and_items', 'items_only'):
            for count in (1, 2, 3):
                for itemsanity in (False, True):
                    for seed in (335, 336, 342):
                        with self.subTest(mode=mode, count=count, itemsanity=itemsanity, seed=seed):
                            mw = _build(seed=seed, lettersanity=mode, letters_per_track=count,
                                        itemsanity=itemsanity)
                            self.check_world(mw)
                            tracker = setup_multiworld(ctrAPWorld, steps=(), seed=999)
                            tracker.re_gen_passthrough = {ctrAPWorld.game: mw.worlds[1].fill_slot_data()}
                            for step in STEPS:
                                call_all(tracker, step)
                            for option in ('lettersanity', 'itemsanity'):
                                self.assertEqual(getattr(tracker.worlds[1].options, option).value,
                                                 getattr(mw.worlds[1].options, option).value)
                            # Only modes 1/2 encode selected physical checks.
                            # Off omits the block; mode 3 encodes inactive slots.
                            if mode in ('locations_only', 'locations_and_items'):
                                self.assertEqual(tracker.worlds[1].options.letters_per_track.value, count)
                                self.assertEqual(
                                    {t: set(v) for t, v in tracker.worlds[1].options._lettersanity_selected.items()},
                                    {t: set(v) for t, v in mw.worlds[1].options._lettersanity_selected.items()})
                            self.check_world(tracker)
