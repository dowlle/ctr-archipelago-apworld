"""A boss race is a Hit route as soon as the player can enter it (Rulebook,
Characters and stats, Logic for Hit checks: the player does not need to beat
the boss first). With Progressive Boost the boss win needs a boost rank; the
Hit check on the racer the garage seats must not wait for it. A tester report
(alpha1) showed a random garage boss whose Hit check the Tracker left out of
logic while the player stood in that boss race."""
import unittest

from BaseClasses import CollectionState

from .. import content_bosses, hit_character
from .test_content_bosses import boss_options
from .test_content_plan import make_world


def _gaps(world):
    """(entered-but-Hit-closed cases, cases where the win was still closed)
    while the slot's progression arrives one item at a time."""
    plan = world.ctr_content_plan
    mw, player = world.multiworld, world.player
    entries = {e["id"]: e for e in plan["entries"]}
    items = [i for i in mw.get_items() if i.player == player and i.advancement]
    world.random.shuffle(items)
    state = CollectionState(mw)
    gaps, win_closed = [], 0
    for item in items:
        state.collect(item, prevent_sweep=True)
        for enc in plan["encounters"]:
            cid = entries[enc["entry_id"]]["opponent"]["character_id"]
            if not mw.get_region(enc["entry_id"], player).can_reach(state):
                continue
            win = mw.get_location(content_bosses.CTR_LOCATION_ID_NAMES[enc["completion_location"]], player)
            win_closed += not win.can_reach(state)
            hit = mw.get_location(hit_character.HIT_CHARACTER_CLASS.location_name(cid), player)
            if not hit.can_reach(state):
                gaps.append((enc["pad_id"], cid))
    return gaps, win_closed


class TestHitBossEntry(unittest.TestCase):
    def check(self, seeds, **extra):
        win_closed = 0
        for seed in seeds:
            world = make_world(boss_options(boss_opponent_shuffle=True, hit_character=True, **extra), seed=seed)
            gaps, closed = _gaps(world)
            self.assertEqual(gaps, [], f"seed {seed}: in the boss race but its Hit check is out of logic")
            win_closed += closed
        # The case the fix is about: the race open, its win not yet.
        self.assertGreater(win_closed, 0)

    def test_shared_boost(self):
        self.check(range(4), progressive_boost="shared_global")

    def test_shared_boost_on_drawn_tracks(self):
        self.check(range(4, 8), progressive_boost="shared_global", boss_track_shuffle=True)


if __name__ == "__main__":
    unittest.main()
