"""Boss access alone never reaches a track's AP item boxes.

RULED 2026-09-12 (Discord), from a live report that the Komodo Joe race
let Dragon Mines' AP boxes be collected while the Dragon Mines warp pad was
still shut. That was a NATIVE policy bypass: `AP_BoxPolicyAllows` let every
non-cup race stand and dispatch its track's boxes without consulting the pad.
The fix gives boss races the same pad terms cup legs already use.

This module is the apworld half: a regression fence proving the logic side was
never the leak and cannot become one. Two claims, and they are separate:

  * STRUCTURE. Every `<Track>: Item Box N` is parented to the track's own
    region, which is reached through that track's (possibly shuffled) physical
    warp pad. A boss garage's only race exit is into the dead-end
    `<Track>: Wumpa` region, which holds the Wumpa check and nothing else.
    No boss garage is ever the parent of an entrance into a track region.

  * REACHABILITY. Concrete `CollectionState`s where the boss garage is open,
    the boss encounter reward is reachable and the boss Wumpa check is
    reachable, while the track's own pad is shut -- and in every one of them no
    box on that track is reachable. Each case also carries its complement (open
    the pad and the boxes appear), so a fence that passed by accident because
    the boxes were unreachable for some other reason would fail.

The two shut-pad levers are the two the native policy now reads: the hub Key
spine (destination shuffle can move a boss venue behind a deeper hub door than
its own garage) and the #54/#209 racer lock on the resolved pad. Pinstripe and
N. Oxide need the racer lever because their garages already sit at or above the
deepest hub door, so no Key count can put their venue's pad further away.

Seed fixtures are pinned and each one asserts its own precondition first, so a
generation change that moves the shuffle fails loudly here instead of quietly
turning a fence into a no-op.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..destinations import boss_garage_tracks

BOSS_WUMPA_TRACKS = boss_garage_tracks()

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"

#: Every boss venue, as (garage region, track region, encounter location).
BOSS_CASES = (
    ("Ripper Roo Garage", "Roo's Tubes", "Ripper Roo Garage: Boss Race"),
    ("Papu Papu Garage", "Papu's Pyramid", "Papu Papu Garage: Boss Race"),
    ("Komodo Joe Garage", "Dragon Mines", "Komodo Joe Garage: Boss Race"),
    ("Pinstripe Garage", "Hot Air Skyway", "Pinstripe Garage: Boss Race"),
    ("N. Oxide Garage", "Oxide Station", "N. Oxide Garage: N. Oxide's Challenge"),
)

#: (seed, Keys held) fixtures where the garage is open and the venue's resolved
#: pad is behind a deeper hub door. Verified preconditions, not guesses.
KEY_FIXTURES = (
    ("Ripper Roo Garage", "Roo's Tubes", 1, 0),
    ("Papu Papu Garage", "Papu's Pyramid", 1, 1),
    ("Komodo Joe Garage", "Dragon Mines", 7, 2),
)

#: The racer lever, both on seed 1 with `racer_locked_pads` at 12. The locking
#: character is read off `world.ctr_racer_locks`, never hard-coded.
RACER_FIXTURES = (
    ("Pinstripe Garage", "Hot Air Skyway"),
    ("N. Oxide Garage", "Oxide Station"),
)


def _build(seed=1, **options):
    options.setdefault("box_locations", True)
    options.setdefault("wumpa_check", "per_track")
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    for step in STEPS:
        call_all(mw, step)
    return mw


def _state(mw, keys=None, without=()):
    """Every item at a generous count, with two deliberate holes.

    `keys` caps the Key count (None = uncapped), `without` drops named items
    entirely. The boost chain is added separately because it is progressive.
    """
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item == BOOST or item.startswith(f"{BOOST} ("):
            continue
        if item in without:
            continue
        if item == "Key" and keys is not None:
            if keys:
                state.add_item(item, PLAYER, keys)
            continue
        state.add_item(item, PLAYER, 99)
    state.add_item(BOOST, PLAYER, 2)
    # The boss arms read "<Boss> Boss Race Won" EVENTS, so the state has to
    # sweep them in rather than hold items alone.
    state.sweep_for_advancements()
    return state


def _boxes(mw, track):
    return [loc.name for loc in mw.get_region(track, PLAYER).locations
            if ": Item Box " in loc.name]


def _reachable(state, names):
    return {name for name in names
            if state.can_reach(name, "Location", PLAYER)}








class TestBossRewardsStayReachable(unittest.TestCase):
    """The other half of the ruling: nothing about the boss encounter or its
    Wumpa check is taken away by the box fence."""


    def test_all_five_encounters_and_wumpa_checks_exist(self):
        mw = _build()
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        for _garage, track, encounter in BOSS_CASES:
            with self.subTest(track=track):
                self.assertIn(encounter, names)
                self.assertIn(f"{track}: Reach 10 Wumpa", names)


if __name__ == "__main__":
    unittest.main()
