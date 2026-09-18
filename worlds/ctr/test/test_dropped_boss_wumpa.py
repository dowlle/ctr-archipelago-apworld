"""A dropped destination that still hosts a boss race keeps its Wumpa check.

RULED 2026-09-18. `cortex_vortex_track` takes one destination's warp pad and
removes every location that destination owns. A boss race launches from its
garage rather than from a pad, so dropping one of the five boss tracks does not
stop that race. Per-track `wumpa_check` therefore keeps
`<Track>: Reach 10 Wumpa` on a dropped boss track, reachable only through the
boss race. Nothing else the dropped destination owns comes back, and AP item
boxes keep their unchanged pad-open rule, so a dropped track still has none.

Oxide Station is the one boss track whose race can leave the seed:
`oxide_goal: disabled` removes both N. Oxide races and shuts the garage (issue
#320), and the check goes with them. Every other `oxide_goal` keeps N. Oxide's
Challenge, which is raced on Oxide Station whatever `oxide_final_track` says.
"""
import json
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..Regions import BOSS_WUMPA_TRACKS

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"

#: Destination LevelIDs, spelled out (data/warp_pad_ids.json).
DRAGON_MINES, PAPU_PYRAMID, ROOS_TUBES = 1, 5, 6
HOT_AIR_SKYWAY, OXIDE_STATION = 7, 13
CRASH_COVE, TIGER_TEMPLE = 3, 4

#: The four ordinary boss tracks, as (garage, track, destination LevelID).
BOSS_CASES = (
    ("Ripper Roo Garage", "Roo's Tubes", ROOS_TUBES),
    ("Papu Papu Garage", "Papu's Pyramid", PAPU_PYRAMID),
    ("Komodo Joe Garage", "Dragon Mines", DRAGON_MINES),
    ("Pinstripe Garage", "Hot Air Skyway", HOT_AIR_SKYWAY),
)


def _build(dropped, seed=1, **options):
    options.setdefault("cortex_vortex_track", True)
    options.setdefault("wumpa_check", "per_track")
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    mw.worlds[PLAYER].options._cortex_vortex_dropped = dropped
    for step in STEPS:
        call_all(mw, step)
    return mw


def _names(mw):
    return {loc.name for loc in mw.get_locations(PLAYER)}


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _everything(mw, boost=0):
    """Every item at a generous count, minus the boost chain."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item == BOOST or item.startswith(f"{BOOST} ("):
            continue
        state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


def _entrance_sources(mw, region_name):
    return {ent.parent_region.name
            for ent in mw.get_region(region_name, PLAYER).entrances}


class TestDroppedBossTrackKeepsItsCheck(unittest.TestCase):
    """The four ordinary boss tracks, one seed each."""

    def test_the_check_stays_and_is_on_the_wire(self):
        for garage, track, lid in BOSS_CASES:
            with self.subTest(track=track):
                mw = _build(lid)
                self.assertIn(f"{track}: Reach 10 Wumpa", _names(mw))
                retail = _wire(mw)["wumpa_checks"]["retail_tracks"]
                self.assertEqual(retail[str(lid)],
                                 ctrAPWorld.location_name_to_id[
                                     f"{track}: Reach 10 Wumpa"])
                self.assertEqual(BOSS_WUMPA_TRACKS[garage], track)

    def test_the_garage_is_the_only_route_into_its_wumpa_region(self):
        """No pad, so the track's own region is not a source. A vanilla Gem Cup
        leg may still race it; a randomized draw never can, so pin the
        randomized case where the garage has to stand alone."""
        for garage, track, lid in BOSS_CASES:
            with self.subTest(track=track):
                mw = _build(lid, randomize_gem_cup_tracks=True)
                self.assertEqual(_entrance_sources(mw, f"{track}: Wumpa"),
                                 {garage})

    def test_everything_else_the_dropped_track_owned_is_still_gone(self):
        for _garage, track, lid in BOSS_CASES:
            with self.subTest(track=track):
                mw = _build(lid, box_locations=True,
                            lettersanity="locations_only", letters_per_track=3)
                leftovers = {name for name in _names(mw)
                             if name.startswith(f"{track}: ")
                             and name != f"{track}: Reach 10 Wumpa"}
                self.assertEqual(leftovers, set())
                wire = _wire(mw)
                self.assertNotIn(str(lid), wire["podium_checks"]["locations"])
                self.assertNotIn(str(lid), wire["lettersanity_checks"]["locations"])
                self.assertEqual(
                    set(wire["item_box_checks"]["locations"][str(lid)]), {-1})

    def test_the_check_needs_the_boss_garage_and_nothing_else_opens_it(self):
        """Reachable exactly when the garage door's Trophy threshold is met.
        Held mid-race, so it does not take the boss race's own finish term."""
        for garage, track, lid in BOSS_CASES:
            with self.subTest(track=track):
                mw = _build(lid, randomize_gem_cup_tracks=True)
                name = f"{track}: Reach 10 Wumpa"
                empty = CollectionState(mw)
                self.assertFalse(empty.can_reach(name, "Location", PLAYER))
                self.assertTrue(
                    _everything(mw).can_reach(name, "Location", PLAYER))


class TestDroppedOxideStation(unittest.TestCase):
    """Oxide Station's boss race is N. Oxide's Challenge, so the check follows
    `oxide_goal` rather than being unconditional."""

    def test_kept_on_the_default_goal_with_the_first_challenge_rule(self):
        mw = _build(OXIDE_STATION, randomize_gem_cup_tracks=True)
        self.assertIn("Oxide Station: Reach 10 Wumpa", _names(mw))
        self.assertEqual(_entrance_sources(mw, "Oxide Station: Wumpa"),
                         {"N. Oxide Garage"})
        self.assertEqual(
            _wire(mw)["wumpa_checks"]["retail_tracks"][str(OXIDE_STATION)],
            ctrAPWorld.location_name_to_id["Oxide Station: Reach 10 Wumpa"])

    def test_kept_when_oxide_station_is_also_the_final_venue(self):
        mw = _build(OXIDE_STATION, randomize_gem_cup_tracks=True,
                    oxide_final_track="oxide_station")
        self.assertIn("Oxide Station: Reach 10 Wumpa", _names(mw))

    def test_kept_when_oxide_is_not_the_goal_but_its_races_remain(self):
        mw = _build(OXIDE_STATION, randomize_gem_cup_tracks=True,
                    oxide_goal="none", bosses_required_goal=4)
        self.assertIn("Oxide Station: Reach 10 Wumpa", _names(mw))

    def test_removed_when_oxide_goal_disabled_removes_both_races(self):
        mw = _build(OXIDE_STATION, randomize_gem_cup_tracks=True,
                    oxide_goal="disabled", bosses_required_goal=4)
        self.assertNotIn("Oxide Station: Reach 10 Wumpa", _names(mw))
        self.assertNotIn(str(OXIDE_STATION),
                         _wire(mw)["wumpa_checks"]["retail_tracks"])

    def test_the_garage_route_carries_the_first_challenge_companions(self):
        """On an Any% goal with a Boss arm, N. Oxide's Challenge needs those
        bosses won, and the garage edge is now the check's only route, so it
        takes the same rule instead of the bare four-Key door."""
        mw = _build(OXIDE_STATION, randomize_gem_cup_tracks=True,
                    oxide_goal="any_percent", bosses_required_goal=4)
        name = "Oxide Station: Reach 10 Wumpa"
        keys_only = CollectionState(mw)
        keys_only.add_item("Key", PLAYER, 4)
        self.assertFalse(keys_only.can_reach(name, "Location", PLAYER))
        # The Boss arm reads the four "<Boss> Boss Race Won" EVENTS, so the
        # state has to sweep them in rather than hold items alone.
        everything = _everything(mw, boost=2)
        everything.sweep_for_advancements()
        self.assertTrue(everything.can_reach(name, "Location", PLAYER))


class TestNonBossDroppedTrack(unittest.TestCase):
    """A dropped destination with no boss race loses its check, unchanged."""

    def test_crash_cove_keeps_nothing(self):
        for lid in (CRASH_COVE, TIGER_TEMPLE):
            with self.subTest(destination=lid):
                mw = _build(lid, box_locations=True)
                track = {CRASH_COVE: "Crash Cove",
                         TIGER_TEMPLE: "Tiger Temple"}[lid]
                self.assertNotIn(f"{track}: Reach 10 Wumpa", _names(mw))
                wire = _wire(mw)
                self.assertNotIn(str(lid),
                                 wire["wumpa_checks"]["retail_tracks"])
                self.assertEqual(
                    set(wire["item_box_checks"]["locations"][str(lid)]), {-1})


class TestOptionOffAndGlobalModeAreUntouched(unittest.TestCase):
    def test_global_mode_still_creates_only_the_global_check(self):
        mw = _build(ROOS_TUBES, wumpa_check="global")
        names = _names(mw)
        self.assertIn("Wumpa: Reach 10 Wumpa", names)
        self.assertNotIn("Roo's Tubes: Reach 10 Wumpa", names)

    def test_wumpa_off_creates_nothing(self):
        names = _names(_build(ROOS_TUBES, wumpa_check="off"))
        self.assertEqual({n for n in names if n.endswith("Reach 10 Wumpa")},
                         set())
