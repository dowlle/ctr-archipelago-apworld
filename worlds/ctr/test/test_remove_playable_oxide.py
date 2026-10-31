"""Remove Playable Oxide (dowlle/ctr-native-ap#426).

A toggle, off by default. With Character Unlocks on it takes Nitros Oxide out
of the racers you can play:

  * his unlock item is not created, and the filler top-up keeps the pool the
    same size, so one more filler or trap appears;
  * Starting Character `random_any` never picks him (`random_starter` already
    could not: it draws from the eight retail Adventure starters);
  * Racer-Locked Warp Pads never locks a pad to him;
  * he stays an opponent, and his Hit Character check stays reachable;
  * `starting_character: nitros_oxide` together with the option refuses the
    seed with a message that names both options.

With Character Unlocks off the option does nothing and says so once.
"""
import logging
import unittest
from collections import Counter
from pathlib import Path

import yaml

from BaseClasses import CollectionState, ItemClassification
from Fill import distribute_items_restrictive
from Options import OptionError
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import characters, ctrAPWorld
from ..hit_character import HIT_CHARACTER_CLASS

PLAYER = 1
OXIDE = characters.OXIDE
OXIDE_HIT = HIT_CHARACTER_CLASS.location_name(
    characters.ROSTER_CHARACTER_ID[OXIDE])
EARLY = ("generate_early",)
THROUGH_ITEMS = ("generate_early", "create_regions", "create_items",
                 "set_rules")
SEEDS = (1, 2, 3, 17, 404)
TRIAL = {"slide_coliseum_races": "trophy_race",
         "turbo_track_races": "trophy_race"}


def _build(seed=1, steps=THROUGH_ITEMS, **options):
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


def _generate(seed, **options):
    """A fresh filled seed at accessibility: full."""
    opts = dict(options)
    opts["accessibility"] = "full"
    mw = setup_multiworld(ctrAPWorld, gen_steps, seed=seed, options=opts)
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    return mw


def _reached_names(mw):
    """Sphere-reachable location names from the starting inventory."""
    remaining = list(mw.get_locations(PLAYER))
    state = CollectionState(mw)
    reached = set()
    while remaining:
        sphere = [loc for loc in remaining if loc.can_reach(state)]
        if not sphere:
            break
        for loc in sphere:
            remaining.remove(loc)
            reached.add(loc.name)
        for loc in sphere:
            if loc.item:
                state.collect(loc.item, True, loc)
    return reached, remaining


def _pool_names(mw):
    return [item.name for item in mw.itempool if item.player == PLAYER]


class _Collector(logging.Handler):
    def __init__(self, sink):
        super().__init__(logging.DEBUG)
        self.sink = sink

    def emit(self, record):
        self.sink.append(record.getMessage())


def _messages_for(seed=1, **options):
    messages = []
    log = logging.getLogger("worlds.ctr.forced_options")
    handler = _Collector(messages)
    log.addHandler(handler)
    try:
        mw = _build(seed, steps=EARLY, **options)
    finally:
        log.removeHandler(handler)
    return mw, messages


class TestOptionOff(unittest.TestCase):
    """Off is the default and leaves Oxide's item where it always was."""

    def test_default_is_off(self):
        world = _build(1, steps=EARLY).worlds[PLAYER]
        self.assertFalse(world.options.remove_playable_oxide.value)
        self.assertFalse(characters.oxide_removed(world))

    def test_off_still_creates_the_oxide_unlock(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertIn(OXIDE, _pool_names(_build(seed)))

    def test_explicit_off_matches_the_default_pool(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(
                    Counter(_pool_names(_build(seed))),
                    Counter(_pool_names(
                        _build(seed, remove_playable_oxide=False))))

    def test_random_any_draw_is_unchanged_when_off(self):
        # Off draws from the full roster, so Oxide is still a possible start.
        starts = {_build(seed, steps=EARLY, starting_character="random_any")
                  .worlds[PLAYER].ctr_starting_character
                  for seed in range(200)}
        self.assertIn(OXIDE, starts)


class TestOptionOn(unittest.TestCase):

    def test_no_oxide_unlock_item_is_created_or_precollected(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                mw = _build(seed, remove_playable_oxide=True)
                self.assertNotIn(OXIDE, _pool_names(mw))
                self.assertNotIn(
                    OXIDE, [i.name for i in mw.precollected_items[PLAYER]])
                world = mw.worlds[PLAYER]
                self.assertNotIn(OXIDE, characters.created_unlock_names(world))
                self.assertEqual(
                    len(characters.created_unlock_names(world)), 14)

    def test_pool_size_is_unchanged_and_the_slot_becomes_filler(self):
        for traps in (0, 50):
            for seed in SEEDS:
                with self.subTest(seed=seed, traps=traps):
                    off = _build(seed, trap_fill_percentage=traps)
                    on = _build(seed, trap_fill_percentage=traps,
                                remove_playable_oxide=True)
                    self.assertEqual(len(_pool_names(off)),
                                     len(_pool_names(on)))
                    self.assertEqual(len(on.get_unfilled_locations(PLAYER)),
                                     len(_pool_names(on)))
                    # Same locations, same starter; only Oxide's slot moved.
                    self.assertEqual(
                        on.worlds[PLAYER].ctr_starting_character,
                        off.worlds[PLAYER].ctr_starting_character)
                    added = Counter(_pool_names(on)) - Counter(_pool_names(off))
                    removed = Counter(_pool_names(off)) - Counter(_pool_names(on))
                    self.assertEqual(removed.get(OXIDE), 1, removed)
                    self.assertEqual(sum(added.values()),
                                     sum(removed.values()))
                    world = on.worlds[PLAYER]
                    for name in added:
                        classification = world.create_item(name).classification
                        self.assertFalse(
                            classification & (ItemClassification.progression
                                              | ItemClassification.useful),
                            f"{name} is {classification!r}")

    def test_random_any_never_picks_oxide(self):
        starts = Counter(
            _build(seed, steps=EARLY, starting_character="random_any",
                   remove_playable_oxide=True).worlds[PLAYER]
            .ctr_starting_character
            for seed in range(300))
        self.assertNotIn(OXIDE, starts)
        # Still the wide draw, not the retail eight.
        self.assertTrue(set(starts) - set(characters.ADVENTURE_STARTERS))

    def test_random_starter_never_picks_oxide(self):
        for seed in range(50):
            world = _build(seed, steps=EARLY,
                           remove_playable_oxide=True).worlds[PLAYER]
            self.assertIn(world.ctr_starting_character,
                          characters.ADVENTURE_STARTERS)

    def test_racer_locks_never_name_oxide(self):
        for seed in SEEDS + (5, 6, 7, 8, 9):
            with self.subTest(seed=seed):
                world = _build(seed, remove_playable_oxide=True,
                               racer_locked_pads=27).worlds[PLAYER]
                locks = world.ctr_racer_locks
                self.assertTrue(locks)
                self.assertNotIn(OXIDE, locks.values())
                self.assertNotIn(
                    characters.ROSTER_CHARACTER_ID[OXIDE],
                    world.fill_slot_data()["racer_locks"]["pads"].values())
                # The spread still covers every other non-starter racer once
                # before any of them locks a second pad.
                if len(locks) >= 14:
                    self.assertEqual(
                        set(locks.values()),
                        set(characters.ROSTER_CHARACTER_ID)
                        - {OXIDE, world.ctr_starting_character})

    def test_named_non_oxide_start_is_honoured(self):
        world = _build(1, starting_character="ripper_roo",
                       remove_playable_oxide=True).worlds[PLAYER]
        self.assertEqual(world.ctr_starting_character, "Ripper Roo")
        self.assertNotIn(OXIDE, _pool_names(world.multiworld))

    def test_slot_data_starting_character_is_never_oxide(self):
        for seed in range(40):
            world = _build(seed, steps=EARLY, starting_character="random_any",
                           remove_playable_oxide=True).worlds[PLAYER]
            self.assertNotEqual(
                characters.ROSTER_CHARACTER_ID[world.ctr_starting_character],
                characters.ROSTER_CHARACTER_ID[OXIDE])


class TestStartingAsOxideIsRefused(unittest.TestCase):

    def test_nitros_oxide_start_with_the_option_raises(self):
        with self.assertRaises(OptionError) as ctx:
            _build(1, steps=EARLY, starting_character="nitros_oxide",
                   remove_playable_oxide=True)
        message = str(ctx.exception)
        self.assertIn("remove_playable_oxide", message)
        self.assertIn("nitros_oxide", message)

    def test_nitros_oxide_start_without_the_option_generates(self):
        world = _build(1, starting_character="nitros_oxide").worlds[PLAYER]
        self.assertEqual(world.ctr_starting_character, OXIDE)


class TestCharacterUnlocksOff(unittest.TestCase):
    """With Character Unlocks off the option is a no-op, noted once."""

    def test_option_does_nothing(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                on = _build(seed, character_unlocks=False,
                            remove_playable_oxide=True)
                off = _build(seed, character_unlocks=False)
                self.assertFalse(characters.oxide_removed(on.worlds[PLAYER]))
                self.assertEqual(Counter(_pool_names(on)),
                                 Counter(_pool_names(off)))

    def test_random_any_can_still_pick_oxide(self):
        for seed in range(200):
            on = _build(seed, steps=EARLY, character_unlocks=False,
                        starting_character="random_any",
                        remove_playable_oxide=True).worlds[PLAYER]
            off = _build(seed, steps=EARLY, character_unlocks=False,
                         starting_character="random_any").worlds[PLAYER]
            self.assertEqual(on.ctr_starting_character,
                             off.ctr_starting_character)
            if on.ctr_starting_character == OXIDE:
                break
        else:
            self.fail("random_any never drew Oxide in 200 seeds")

    def test_starting_as_oxide_is_allowed(self):
        world = _build(1, character_unlocks=False,
                       starting_character="nitros_oxide",
                       remove_playable_oxide=True).worlds[PLAYER]
        self.assertEqual(world.ctr_starting_character, OXIDE)

    def test_one_note_says_why(self):
        _mw, messages = _messages_for(1, character_unlocks=False,
                                      remove_playable_oxide=True)
        hits = [m for m in messages
                if "Remove Playable Oxide (Character Unlocks off)" in m]
        self.assertEqual(len(hits), 1, messages)

    def test_no_note_with_unlocks_on(self):
        _mw, messages = _messages_for(1, remove_playable_oxide=True)
        self.assertFalse([m for m in messages if "Remove Playable Oxide" in m],
                         messages)


class TestHitCharacterOxide(unittest.TestCase):
    """Oxide stays an opponent: his Hit check never reads his unlock item."""

    def test_oxide_hit_check_is_reachable_at_accessibility_full(self):
        shapes = {
            "default": {},
            "racer_locks": {"racer_locked_pads": 6},
            # No Oxide race in the seed: his Hit check falls back to Keys.
            "oxide_disabled": {"oxide_goal": "disabled",
                               "bosses_required_goal": 4},
        }
        for shape, options in shapes.items():
            for seed in (1, 2, 3):
                with self.subTest(shape=shape, seed=seed):
                    opts = dict(TRIAL)
                    opts.update(options)
                    mw = _generate(seed, hit_character=True,
                                   remove_playable_oxide=True, **opts)
                    self.assertNotIn(OXIDE, _pool_names(mw))
                    reached, remaining = _reached_names(mw)
                    self.assertIn(OXIDE_HIT, reached)
                    self.assertEqual(
                        [loc.name for loc in remaining], [],
                        f"{shape}/{seed}: unreached locations")


class TestAccessibilityFull(unittest.TestCase):
    """Fresh filled seeds with the option on reach every location."""

    def test_every_location_reachable(self):
        shapes = {
            "default": {},
            "random_any": {"starting_character": "random_any"},
            "racer_locks": {"racer_locked_pads": 10},
            "per_character_boost": {"progressive_boost": "per_character"},
        }
        for shape, options in shapes.items():
            for seed in (1, 2):
                with self.subTest(shape=shape, seed=seed):
                    mw = _generate(seed, remove_playable_oxide=True, **options)
                    self.assertNotIn(OXIDE, _pool_names(mw))
                    _reached, remaining = _reached_names(mw)
                    self.assertEqual([loc.name for loc in remaining], [])


class TestUniversalTracker(unittest.TestCase):
    """The wire carries the effective option and UT restores it (the
    character_unlocks precedent): absent means off, the tracking player's own
    YAML never wins."""

    STEPS = ("generate_early", "create_regions", "create_items", "set_rules")

    def _rebuild(self, wire, **local):
        tracker = setup_multiworld(ctrAPWorld, steps=(), seed=99,
                                   options=local)
        tracker.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in self.STEPS:
            call_all(tracker, step)
        return tracker

    def _assert_same_pool(self, original, tracker):
        self.assertEqual(Counter(
            name for name in _pool_names(original)
            if name in characters.ROSTER_CHARACTER_ID), Counter(
            name for name in _pool_names(tracker)
            if name in characters.ROSTER_CHARACTER_ID))
        self.assertEqual(len(_pool_names(original)), len(_pool_names(tracker)))
        self.assertEqual(len(tracker.get_unfilled_locations(PLAYER)),
                         len(_pool_names(tracker)))

    def test_wire_carries_the_effective_value(self):
        cases = (
            ({}, False),
            ({"remove_playable_oxide": True}, True),
            ({"remove_playable_oxide": True, "character_unlocks": False},
             False),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                wire = _build(1, **options).worlds[PLAYER].fill_slot_data()
                value = wire["ctr_options"]["remove_playable_oxide"]
                self.assertIs(type(value), bool)
                self.assertEqual(value, expected)

    def test_round_trip_restores_the_option_and_the_pool(self):
        for seed_value in (True, False):
            for local in ({}, {"remove_playable_oxide": not seed_value}):
                with self.subTest(seed_value=seed_value, local=local):
                    original = _build(4, starting_character="random_any",
                                      racer_locked_pads=8,
                                      remove_playable_oxide=seed_value)
                    world = original.worlds[PLAYER]
                    tracker = self._rebuild(world.fill_slot_data(), **local)
                    rebuilt = tracker.worlds[PLAYER]
                    self.assertEqual(
                        bool(rebuilt.options.remove_playable_oxide.value),
                        seed_value)
                    self.assertEqual(rebuilt.ctr_starting_character,
                                     world.ctr_starting_character)
                    self.assertEqual(rebuilt.ctr_racer_locks,
                                     world.ctr_racer_locks)
                    self._assert_same_pool(original, tracker)

    def test_absent_key_restores_off_whatever_the_local_yaml_says(self):
        wire = _build(1).worlds[PLAYER].fill_slot_data()
        del wire["ctr_options"]["remove_playable_oxide"]
        tracker = self._rebuild(wire, remove_playable_oxide=True)
        self.assertFalse(
            tracker.worlds[PLAYER].options.remove_playable_oxide.value)
        self.assertIn(OXIDE, _pool_names(tracker))

    def test_tight_pool_seed_from_check_ut_round_trips(self):
        # The CI check-ut failure: podium checks off and 95% traps, so the
        # seed only fits 14 unlock items. Off, the same options are refused;
        # on, UT must rebuild the same 14-racer pool instead of refusing.
        options = yaml.safe_load(
            (Path(__file__).parent
             / "fixtures/remove_oxide_tight_pool_check_ut.yaml").read_text()
        )[ctrAPWorld.game]
        off = dict(options, remove_playable_oxide=False)
        with self.assertRaises(OptionError):
            _build(3, **off)
        original = _build(3, **options)
        wire = original.worlds[PLAYER].fill_slot_data()
        self.assertTrue(wire["ctr_options"]["remove_playable_oxide"])
        tracker = self._rebuild(wire)
        self._assert_same_pool(original, tracker)
        self.assertNotIn(OXIDE, _pool_names(tracker))

    def test_tracker_starting_as_oxide_does_not_raise(self):
        original = _build(1, starting_character="nitros_oxide")
        self._rebuild(original.worlds[PLAYER].fill_slot_data(),
                      remove_playable_oxide=True)


if __name__ == "__main__":
    unittest.main()
