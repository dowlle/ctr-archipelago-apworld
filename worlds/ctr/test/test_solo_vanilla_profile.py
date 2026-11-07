"""Standard in Play Solo with picked custom tracks (#89): the one generator's defaults.

18 race pads, 5 Gem Cups, 4 Crystal Challenges (the retail arenas), the boss
garages and the default item pool. Retail and picked custom tracks share one pool
for the pads and every cup leg; the pads stay 18, so a custom track on a pad
displaces a retail track."""
import collections
import copy
import unittest

from .. import content_plan
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN

LOOP = "fixture-loop"
BABY = "baby-t-park"
#: The default Crystal Challenge pool is all seven arenas since A3-8; the default count of 4 draws from it.
DEFAULT_ARENAS = {f"arena:{level}" for level in range(18, 25)}


def profile_options(custom, guaranteed):
    return dict(custom_tracks=custom, required_entries=guaranteed, accessibility="full", death_link="off")


class TestVanillaShapeProfile(unittest.TestCase):
    def cases(self):
        loop, baby = copy.deepcopy(UNKNOWN), copy.deepcopy(content_plan.PACKAGES[1])
        return ((0, [], []), (1, [loop], []), (1, [loop], [LOOP]), (2, [loop, baby], []),
                (2, [loop, baby], [LOOP, BABY]))

    def test_the_shape_holds_with_zero_one_and_two_tracks(self):
        for count, custom, guaranteed in self.cases():
            for seed in (1, 2, 3):
                with self.subTest(tracks=count, guaranteed=len(guaranteed), seed=seed):
                    world = make_world(profile_options(copy.deepcopy(custom), list(guaranteed)), seed=seed)
                    plan = world.ctr_content_plan
                    self.assertTrue(content_plan.validate(plan))
                    kinds = collections.Counter(e["kind"] for e in plan["entries"])
                    self.assertEqual(kinds["track"], 18)
                    self.assertEqual(kinds["cup"], 5)
                    self.assertEqual(kinds["crystal"], 4)
                    self.assertEqual(kinds["boss_race"], 6)  # four garages and two for Oxide
                    pads = [p for p in plan["pads"] if p["id"].startswith("pad:") and p["entry_id"]]
                    self.assertEqual(len(pads), 27)
                    arenas = {e["id"].split("/")[-1] for e in plan["entries"] if e["kind"] == "crystal"}
                    self.assertTrue(arenas <= DEFAULT_ARENAS, arenas)
                    on_pads = {e["id"] for e in plan["entries"] if e["kind"] == "track"}
                    for track_id in guaranteed:
                        self.assertTrue(any(track_id in entry_id for entry_id in on_pads), track_id)
                    custom_on_pads = [i for i in on_pads if "custom/" in i]
                    retail_on_pads = [i for i in on_pads if "retail:" in i]
                    # A custom track on a pad displaces a retail track: 18 pads either way.
                    self.assertEqual(len(retail_on_pads) + len(custom_on_pads), 18)
                    self.assertGreaterEqual(len(custom_on_pads), len(guaranteed))
                    self.assertLessEqual(len(custom_on_pads), count)

    def test_item_quantities_are_the_defaults(self):
        for count, custom, guaranteed in self.cases():
            with self.subTest(tracks=count, guaranteed=len(guaranteed)):
                world = make_world(profile_options(copy.deepcopy(custom), list(guaranteed)), seed=1)
                names = collections.Counter(item.name for item in world.multiworld.itempool)
                names.update(item.name for item in world.multiworld.precollected_items[1])
                self.assertEqual(names["Trophy"], 16)
                for tier in ("Sapphire", "Gold"):
                    self.assertEqual(names[f"{tier} Relic"], 18)
                self.assertEqual(names["Platinum Relic"], 0)
                for colour in ("Red", "Green", "Blue", "Yellow", "Purple"):
                    self.assertEqual(names[f"{colour} CTR Token"], 4)
                    self.assertEqual(names[f"{colour} Gem"], 1)
                self.assertEqual(names["Key"], 4)

    def test_an_in_pool_track_races_on_a_pad_and_in_cup_legs(self):
        # The content plan draws each cup's custom leg count uniformly (0 to the
        # number of custom tracks), so a track in the pool is raced in some cup
        # in nearly every seed; "neither" is possible but rare. The pad is a
        # plain sample of the 19 candidates, so a pad is likely but not certain.
        seen = collections.Counter()
        for seed in range(1, 25):
            plan = make_world(profile_options([copy.deepcopy(UNKNOWN)], []), seed=seed).ctr_content_plan
            on_pad = any(e["kind"] == "track" and LOOP in e["id"] for e in plan["entries"])
            in_cup = any(LOOP in leg["track_id"] for e in plan["entries"] if e["kind"] == "cup" for leg in e["legs"])
            seen[(on_pad, in_cup)] += 1
            self.assertEqual(sum(e["kind"] == "track" for e in plan["entries"]), 18)
        self.assertGreater(seen[(True, True)], 0)

    def test_a_track_twice_in_one_cup_gets_one_title(self):
        # Counted twice, the track clashed with itself and the plan check refused the seed.
        twice = 0
        for seed in range(1, 41):
            world = make_world(dict(profile_options([copy.deepcopy(UNKNOWN)], []), cup_tracks="random_repeats",
                                    cup_custom_legs=4), seed=seed)
            plan = world.ctr_content_plan
            twice += any(sum(LOOP in leg["track_id"] for leg in e["legs"]) > 1
                         for e in plan["entries"] if e["kind"] == "cup")
            track = next(t for t in plan["tracks"] if t["origin"] == "custom")
            self.assertEqual(track.get("room_title", track["display_name"]), track["display_name"])
        self.assertGreater(twice, 0)
