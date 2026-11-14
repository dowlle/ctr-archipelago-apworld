"""The 27 normal pads as one budget (A4-83, maintainer ruling 2026-11-14 about
15:16 CET): over it, `cup_count` and `crystal_challenge_count` act as weights
(pad_budget). A seed that fits is untouched."""
import io
import json
import unittest
from types import SimpleNamespace

from Options import OptionError

from .. import content_cups, content_plan, pad_budget
from .test_content_plan import make_world


def counts(plan):
    kinds = [e["kind"] for e in plan["entries"]]
    return kinds.count(content_cups.KIND), sum(1 for e in plan["entries"] if e["kind"] == "crystal")


def track_pads(plan):
    return sum(1 for e in plan["entries"] if e["kind"] == "track")


class TestShare(unittest.TestCase):
    def test_fit_is_unchanged(self):
        self.assertEqual(pad_budget.share(27, [5, 4], [0, 0]), [5, 4])
        self.assertEqual(pad_budget.share(26, [22, 4], [0, 0]), [22, 4])
        self.assertEqual(pad_budget.share(27, [0, 0], [0, 0]), [0, 0])

    def test_largest_remainder(self):
        # The worked example of the option text: 26 pads for 27 + 4.
        self.assertEqual(pad_budget.share(26, [27, 4], [0, 0]), [23, 3])
        # 27 pads for 27 + 4: 23.52 and 3.48.
        self.assertEqual(pad_budget.share(27, [27, 4], [0, 0]), [24, 3])
        # 26 pads for 23 + 4: 22.15 and 3.85, the spare pad goes to the crystals.
        self.assertEqual(pad_budget.share(26, [23, 4], [0, 0]), [22, 4])
        self.assertEqual(pad_budget.share(26, [27, 0], [0, 0]), [26, 0])

    def test_tie_goes_to_cups(self):
        self.assertEqual(pad_budget.share(3, [2, 2], [0, 0]), [2, 1])
        self.assertEqual(pad_budget.share(1, [1, 1], [0, 0]), [1, 0])

    def test_never_above_request_and_sums_to_budget(self):
        for available in range(0, 28):
            for cups in range(0, 28):
                for crystals in range(0, 8):
                    out = pad_budget.share(available, [cups, crystals], [0, 0])
                    self.assertLessEqual(out[0], cups)
                    self.assertLessEqual(out[1], crystals)
                    self.assertEqual(sum(out), min(available, cups + crystals))
                    self.assertEqual(out, pad_budget.share(available, [cups, crystals], [0, 0]))

    def test_floors(self):
        # Four required arenas hold the crystals at 4: the cups take the rest.
        self.assertEqual(pad_budget.share(27, [27, 4], [0, 4]), [23, 4])
        # A floor above the request is the request.
        self.assertEqual(pad_budget.share(10, [2, 20], [5, 0]), [2, 8])
        # A Gem goal of 5 keeps five cups.
        self.assertEqual(pad_budget.share(6, [6, 7], [5, 0]), [5, 1])
        self.assertIsNone(pad_budget.share(3, [5, 4], [2, 2]))


def fake_world(cups, crystals, gems=0, gauntlet=False):
    value = lambda v: SimpleNamespace(value=v)
    options = SimpleNamespace(cup_count=value(cups), crystal_challenge_count=value(crystals),
                              gems_required_goal=value(gems), purple_cup_boss_gauntlet=value(int(gauntlet)))
    return SimpleNamespace(options=options, player=1, multiworld=SimpleNamespace(player_name={1: "P"}))


class TestResolve(unittest.TestCase):
    def test_fit_touches_nothing(self):
        world = fake_world(22, 4)
        self.assertEqual(pad_budget.resolve(world, 1, 0), (22, 4))
        self.assertFalse(hasattr(world, "ctr_pad_budget"))

    def test_over_budget_warns_and_writes_back(self):
        world = fake_world(27, 4)
        with self.assertLogs("CTR", "WARNING") as logs:
            self.assertEqual(pad_budget.resolve(world, 1, 0), (23, 3))
        self.assertIn("27 cups and 4 Crystal Challenges", logs.output[0])
        self.assertIn("23 cups and 3 Crystal Challenges", logs.output[0])
        self.assertEqual((world.options.cup_count.value, world.options.crystal_challenge_count.value), (23, 3))
        self.assertEqual(world.ctr_pad_budget, dict(requested=(27, 4), final=(23, 3), required_tracks=1))

    def test_goal_floors(self):
        world = fake_world(5, 7, gems=5)
        self.assertEqual(pad_budget.resolve(world, 21, 0), (5, 1))
        world = fake_world(1, 7, gauntlet=True)
        self.assertEqual(pad_budget.resolve(world, 26, 0), (1, 0))

    def test_hard_needs_that_do_not_fit_are_refused(self):
        with self.assertRaisesRegex(OptionError, "28 required track pads"):
            pad_budget.resolve(fake_world(0, 0), 28, 0)
        with self.assertRaisesRegex(OptionError, "cannot hold what must have a pad"):
            pad_budget.resolve(fake_world(3, 4, gems=3), 26, 0)


def a4_80_options(**extra):
    options = dict(cup_count=27, cortex_vortex_track="own_pad", accessibility="full")
    options.update(extra)
    return options


class TestPadBudgetSeeds(unittest.TestCase):
    def test_27_cups_own_pad_and_4_crystals_generate(self):
        """A4-80: refused before, now 23 cups, 3 Crystal Challenges and Cortex Vortex's pad."""
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                world = make_world(a4_80_options(), seed=seed)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                self.assertEqual(counts(plan), (23, 3))
                self.assertEqual(track_pads(plan), 1)
                self.assertIn("cortex_vortex", {e.get("track_id") for e in plan["entries"]})
                self.assertEqual(world.ctr_pad_budget["final"], (23, 3))
                self.assertEqual(int(world.options.cup_count.value), 23)
                # The plan restores as any other (Universal Tracker).
                wire = json.loads(json.dumps(world.fill_slot_data()))
                self.assertEqual(make_world({}, passthrough=wire).ctr_content_plan, plan)

    def test_23_cups_own_pad(self):
        """A4-80: 23 cups were refused; 26 pads for 23 + 4 give 22 cups and 4 crystals."""
        plan = make_world(a4_80_options(cup_count=23), seed=4).ctr_content_plan
        self.assertEqual(counts(plan), (22, 4))

    def test_27_cups_default_crystals(self):
        """No required track: 27 pads for 27 + 4 give 24 cups and 3 crystals."""
        plan = make_world(dict(cup_count=27, accessibility="full"), seed=1).ctr_content_plan
        self.assertEqual(counts(plan), (24, 3))
        self.assertEqual(track_pads(plan), 0)

    def test_required_arenas_keep_their_crystals(self):
        arenas = ["Skull Rock", "Nitro Court", "Rocky Road", "Rampage Ruins"]
        plan = make_world(dict(cup_count=27, required_entries=arenas, accessibility="full"), seed=2).ctr_content_plan
        self.assertEqual(counts(plan), (23, 4))
        names = {e["id"] for e in plan["entries"] if e["kind"] == "crystal"}
        self.assertEqual(len(names), 4)

    def test_required_tracks_keep_their_pads(self):
        required = ["Crash Cove", "Roo's Tubes", "Tiger Temple"]
        plan = make_world(a4_80_options(required_entries=required), seed=5).ctr_content_plan
        # 4 required tracks, 23 pads for 27 + 4: 20.03 and 2.97, so 20 and 3.
        self.assertEqual(counts(plan), (20, 3))
        self.assertEqual(track_pads(plan), 4)

    def test_one_track_named_twice_takes_one_pad(self):
        """A custom track listed by title and by key is one required pad: 22 cups,
        4 Crystal Challenges and one required track fit the 27 pads exactly."""
        from .. import content_plan as plan_module
        package = plan_module.PACKAGES[1]
        world = make_world(dict(cup_count=22, custom_tracks=[package], accessibility="full",
                                required_entries=[package["display_name"], package["content_id"]]), seed=7)
        self.assertEqual(counts(world.ctr_content_plan), (22, 4))
        self.assertFalse(hasattr(world, "ctr_pad_budget"))

    def test_fitting_seeds_draw_as_before(self):
        """22 cups with own_pad (A4-80's largest fit) and 26 with no crystals stay as asked."""
        for options, want in ((a4_80_options(cup_count=22), (22, 4)),
                              (a4_80_options(cup_count=26, crystal_challenge_count=0), (26, 0))):
            with self.subTest(want=want):
                world = make_world(options, seed=6)
                self.assertEqual(counts(world.ctr_content_plan), want)
                self.assertFalse(hasattr(world, "ctr_pad_budget"))


FOUR = ["Rocky Road", "Rampage Ruins", "Skull Rock", "Nitro Court"]


def spoiler_text(world):
    out = io.StringIO()
    world.write_spoiler(out)
    return out.getvalue()


def budget_lines(world):
    return [line for line in spoiler_text(world).splitlines() if line.startswith("CTR pad budget:")]


class TestCapCrystals(unittest.TestCase):
    """A4-83b (maintainer ruling 2026-11-14, "Scale down"): a Crystal Challenge
    count above the arenas listed is the number of arenas, before the sharing."""

    def test_unit(self):
        world = fake_world(5, 7)
        pad_budget.cap_crystals(world, 4)
        self.assertEqual(world.options.crystal_challenge_count.value, 4)
        self.assertEqual(world.ctr_crystal_cap, dict(requested=7, arenas=4))
        for count, arenas in ((4, 4), (3, 4), (0, 0)):
            world = fake_world(5, count)
            pad_budget.cap_crystals(world, arenas)
            self.assertEqual(world.options.crystal_challenge_count.value, count)
            self.assertFalse(hasattr(world, "ctr_crystal_cap"))

    def test_scales_down_with_one_spoiler_line_and_no_warning(self):
        world = make_world(dict(crystal_challenge_count=7, crystal_arenas=FOUR, accessibility="full"), seed=3)
        self.assertEqual(counts(world.ctr_content_plan)[1], 4)
        self.assertEqual(int(world.options.crystal_challenge_count.value), 4)
        self.assertEqual(budget_lines(world), [
            "CTR pad budget: asked for 7 Crystal Challenges, but crystal_arenas lists 4 arenas, so the seed has "
            "4 Crystal Challenges."])
        self.assertFalse(hasattr(world, "ctr_pad_budget"))

    def test_no_new_console_warning(self):
        import logging
        with self.assertNoLogs("CTR", logging.WARNING):
            make_world(dict(crystal_challenge_count=6, crystal_arenas=FOUR, accessibility="full"), seed=3)

    def test_same_seed_as_asking_for_the_arenas(self):
        """The capped YAML is the YAML that asked for 4: same plan, same slot_data."""
        capped = make_world(dict(crystal_challenge_count=7, crystal_arenas=FOUR, accessibility="full"), seed=9)
        asked = make_world(dict(crystal_challenge_count=4, crystal_arenas=FOUR, accessibility="full"), seed=9)
        self.assertEqual(json.dumps(capped.fill_slot_data(), sort_keys=True),
                         json.dumps(asked.fill_slot_data(), sort_keys=True))
        self.assertEqual(budget_lines(asked), [])

    def test_fitting_yaml_has_no_line(self):
        world = make_world(dict(crystal_challenge_count=4, crystal_arenas=FOUR, accessibility="full"), seed=3)
        self.assertFalse(hasattr(world, "ctr_crystal_cap"))
        self.assertEqual(budget_lines(world), [])

    def test_no_arenas_means_no_crystal_challenges(self):
        world = make_world(dict(crystal_challenge_count=3, crystal_arenas=[], accessibility="full"), seed=3)
        self.assertEqual(counts(world.ctr_content_plan)[1], 0)
        self.assertEqual(len(budget_lines(world)), 1)

    def test_cap_then_sharing_is_one_line(self):
        """27 cups and 7 asked with 4 arenas and own_pad: capped to 4, then 26 pads for 27 + 4 give 23 + 3."""
        world = make_world(a4_80_options(crystal_challenge_count=7, crystal_arenas=FOUR), seed=2)
        self.assertEqual(counts(world.ctr_content_plan), (23, 3))
        self.assertEqual(budget_lines(world), [
            "CTR pad budget: asked for 27 cups and 7 Crystal Challenges, crystal_arenas lists 4 arenas so the "
            "Crystal Challenges are capped at 4, 26 of the 27 normal pads left after required tracks, shared out "
            "as 23 cups and 3 Crystal Challenges."])

    def test_sharing_alone_keeps_its_line(self):
        world = make_world(a4_80_options(), seed=2)
        self.assertEqual(budget_lines(world), [
            "CTR pad budget: asked for 27 cups and 4 Crystal Challenges, 26 of the 27 normal pads left after "
            "required tracks, shared out as 23 cups and 3 Crystal Challenges."])

    def test_required_arena_inside_a_capped_count(self):
        world = make_world(dict(crystal_challenge_count=7, crystal_arenas=FOUR, required_entries=["Skull Rock"],
                                accessibility="full"), seed=4)
        self.assertEqual(counts(world.ctr_content_plan)[1], 4)

    def test_universal_tracker_restore(self):
        world = make_world(dict(crystal_challenge_count=7, crystal_arenas=FOUR, accessibility="full"), seed=5)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        self.assertEqual(make_world({}, passthrough=wire).ctr_content_plan, world.ctr_content_plan)

    def test_yaml_text_states_the_cap(self):
        from ..Options import CrystalArenas, CrystalChallengeCount
        doc = " ".join(CrystalChallengeCount.__doc__.split())
        self.assertIn("not refused: the seed uses as many Crystal Challenges as there are arenas", doc)
        self.assertNotIn("cannot be higher", " ".join(CrystalArenas.__doc__.split()))
        from ..Options import CupCount
        self.assertIn("first lowered to the number of arenas in Crystal Arenas", " ".join(CupCount.__doc__.split()))


class TestPadBudgetText(unittest.TestCase):
    def test_yaml_text_states_the_budget_and_the_example(self):
        from ..Options import CortexVortexTrack, CrystalChallengeCount, CupCount, RequiredEntries
        cup = " ".join(CupCount.__doc__.split())
        self.assertIn("the hub has 27 normal warp pads; the boss garages are extra", cup)
        self.assertIn("act as weights", cup)
        self.assertIn("so the seed gets 23 cups and 3 Crystal Challenges", cup)
        self.assertEqual(pad_budget.share(26, [27, 4], [0, 0]), [23, 3])
        for option in (CrystalChallengeCount, RequiredEntries, CortexVortexTrack):
            self.assertIn("27", option.__doc__)


if __name__ == "__main__":
    unittest.main()
