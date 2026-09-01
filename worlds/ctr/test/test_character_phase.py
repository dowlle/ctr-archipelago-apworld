"""Tests for the 0.2.0 character phase (issues #54 / #209).

Ruled behaviour, from the 2026-07-23 character-phase wayfarer (R2-R5, R7, R8,
R15, R17), the 2026-08-08 picker clarification, and the #209 parent body:

  * all 16 racers are playable in Adventure; a YAML option picks the one you
    start as, defaulting to a random pick from the 8 vanilla starters;
  * the other 15 are multiworld unlock items that add ZERO locations;
  * racer-locked pads are a maximum COUNT (2026-08-29 Lane B specification;
    Alpha 6 and earlier spelled it as a toggle). Locks ON -- the resolved pad
    map is non-empty -- makes the unlock items `progression` (a pad can demand
    one); locks OFF makes them `useful` and nothing in logic names a racer;
  * a fill can never place racer X's unlock item behind a pad requiring X;
  * `penta_stats: ntsc | pal`, NTSC default (labels corrected 2026-08-21;
    the wire numbers 0 ordinary / 1 MAX did not move);
  * `editable_stats` is a separate option from `progressive_stats`, and when
    both are set progressive wins with no edit control, without rejecting the
    seed.

These tests lock in the apworld half. The native consumer (hub picker, roster
enforcement, per-slot persistence, the stat panel) is a separate package.

The all-unlocked comfort mode (`character_unlocks: false`, wayfarer gap 7a) is
covered here too, because it is the ruled answer to the AP items-==-locations
invariant on a deliberately reduced seed: 15 unlock items bring no locations of
their own, so a podium-off seed cannot hold them and generation says so rather
than shipping a partial roster.
"""

import json
import logging
import pkgutil
import unittest

from BaseClasses import ItemClassification
from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..characters import (
    ADVENTURE_STARTERS,
    CHARACTER_ID_TO_NAME,
    OPTION_KEY_TO_CHARACTER,
    PHYSICAL_PAD_COUNT,
    ROSTER_CHARACTER_ID,
    STAT_OWNER_GLOBAL,
    STAT_OWNER_NONE,
    STAT_OWNER_PER_CHARACTER,
    STAT_SOURCE_EDITABLE,
    STAT_SOURCE_PROGRESSIVE,
    STAT_SOURCE_VANILLA,
    effective_stat_config,
    eligible_lock_pads,
    racer_lock_counts,
    raise_if_unlocks_exceed_location_supply,
    reconstruct_racer_locks_from_wire,
    requested_lock_count,
    verify_no_self_lock,
)
from ..item_boxes import ITEM_BOX_CLASS
from ..itemsanity import ITEMSANITY_CLASS
from ..lettersanity import LETTERSANITY_CLASS
from ..Options import RacerLockedPads
from ..progressive_capability import ROSTER
from ..relic_perfect import RELIC_PERFECT_CLASS
from . import CTRTestBase

# Seeds used wherever a property has to hold across draws rather than on one
# lucky roll. Small and fixed so a failure is reproducible.
SEEDS = (1, 2, 3, 17, 404, 999999)


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, seed=seed, options=options)


class _WarningCollector(logging.Handler):
    """Collects forced_options' own warnings for a single build. `assertLogs`
    cannot express "and nothing else was said", which is half of what the Alpha
    6 normalization ruling asks for."""

    def __init__(self, sink):
        super().__init__(logging.WARNING)
        self.sink = sink

    def emit(self, record):
        self.sink.append(record.getMessage())


def _build_with_warnings(seed=1, **options):
    messages = []
    log = logging.getLogger("worlds.ctr.forced_options")
    handler = _WarningCollector(messages)
    log.addHandler(handler)
    try:
        multiworld = _build(seed, **options)
    finally:
        log.removeHandler(handler)
    return multiworld, messages


def _forced_option_warnings(seed=1, **options):
    return _build_with_warnings(seed, **options)[1]


# ---------------------------------------------------------------------------
# Roster identity
# ---------------------------------------------------------------------------

class TestRosterIdentity(unittest.TestCase):
    """The roster order is the WIRE order and is NOT the engine's order. Every
    assertion here exists because getting the mapping wrong would not crash or
    warn -- it would silently lock a pad to the wrong racer."""

    def test_mapping_is_a_bijection_onto_engine_ids(self):
        self.assertEqual(sorted(ROSTER_CHARACTER_ID.values()), list(range(16)))
        self.assertEqual(len(CHARACTER_ID_TO_NAME), 16)

    def test_mapping_covers_exactly_the_capability_roster(self):
        # progressive_capability.ROSTER is the one canonical order and
        # data/items.json mints both the capability chains and the character
        # unlocks in it. A divergence here means the unlock item at index N
        # belongs to a different racer than the chain block at index N.
        self.assertEqual(set(ROSTER_CHARACTER_ID), set(ROSTER))

    def test_matches_the_native_reconciliation_table(self):
        """Transcribed from ctr-native-ap ap/ap_capability.c
        AP_CAP_ROSTER_CHARACTER, the only other place these two orders are
        reconciled. Written out name-by-name here for the same reason it is
        written out name-by-name there."""
        native = {
            "Crash Bandicoot": 0, "Coco Bandicoot": 3, "Polar": 6, "Pura": 7,
            "Neo Cortex": 1, "N. Tropy": 12, "Ripper Roo": 10, "Papu Papu": 9,
            "Komodo Joe": 11, "Pinstripe": 8, "Dingodile": 5, "Tiny Tiger": 2,
            "N. Gin": 4, "Fake Crash": 14, "Nitros Oxide": 15,
            "Penta Penguin": 13,
        }
        self.assertEqual(ROSTER_CHARACTER_ID, native)

    def test_the_eight_adventure_starters_are_engine_ids_zero_to_seven(self):
        self.assertEqual(len(ADVENTURE_STARTERS), 8)
        self.assertEqual(
            sorted(ROSTER_CHARACTER_ID[name] for name in ADVENTURE_STARTERS),
            list(range(8)))
        self.assertEqual(
            set(ADVENTURE_STARTERS),
            {"Crash Bandicoot", "Neo Cortex", "Tiny Tiger", "Coco Bandicoot",
             "N. Gin", "Dingodile", "Polar", "Pura"})

    def test_option_keys_are_unique_and_cover_the_roster(self):
        self.assertEqual(len(OPTION_KEY_TO_CHARACTER), 16)
        self.assertEqual(set(OPTION_KEY_TO_CHARACTER.values()), set(ROSTER))


# ---------------------------------------------------------------------------
# Starting character
# ---------------------------------------------------------------------------

class TestStartingCharacter(unittest.TestCase):

    def test_default_draws_from_the_eight_adventure_starters(self):
        seen = set()
        for seed in SEEDS:
            world = _build(seed).worlds[1]
            self.assertIn(world.ctr_starting_character, ADVENTURE_STARTERS)
            seen.add(world.ctr_starting_character)
        # Not a distribution test -- just proof the default is a real draw and
        # not a constant dressed up as one.
        self.assertGreater(len(seen), 1)

    def test_random_any_can_reach_beyond_the_starters(self):
        seen = {_build(seed, starting_character="random_any")
                .worlds[1].ctr_starting_character
                for seed in range(1, 40)}
        self.assertTrue(seen - set(ADVENTURE_STARTERS),
                        "random_any never drew a non-starter across 39 seeds")
        self.assertTrue(seen <= set(ROSTER))

    def test_named_choice_is_honoured_including_a_non_starter(self):
        world = _build(1, starting_character="ripper_roo").worlds[1]
        self.assertEqual(world.ctr_starting_character, "Ripper Roo")
        world = _build(1, starting_character="nitros_oxide").worlds[1]
        self.assertEqual(world.ctr_starting_character, "Nitros Oxide")

    def test_the_starter_is_precollected_and_never_pooled(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                mw = _build(seed)
                start = mw.worlds[1].ctr_starting_character
                pooled = [i.name for i in mw.itempool if i.player == 1]
                self.assertNotIn(start, pooled)
                precollected = {i.name for i in mw.precollected_items[1]}
                self.assertIn(start, precollected)

    def test_exactly_fifteen_unlock_items_enter_the_pool(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                mw = _build(seed)
                start = mw.worlds[1].ctr_starting_character
                pooled = [i.name for i in mw.itempool
                          if i.player == 1 and i.name in ROSTER_CHARACTER_ID]
                self.assertEqual(len(pooled), 15)
                self.assertEqual(set(pooled), set(ROSTER) - {start})
                # One copy each -- a racer is a unique single, not a count.
                self.assertEqual(len(set(pooled)), 15)


# ---------------------------------------------------------------------------
# Classification (R17)
# ---------------------------------------------------------------------------

class TestUnlockClassification(unittest.TestCase):

    def _classes(self, **options):
        mw = _build(1, **options)
        return {i.name: i.classification for i in mw.itempool
                if i.player == 1 and i.name in ROSTER_CHARACTER_ID}

    def test_locks_off_leaves_the_unlocks_useful(self):
        classes = self._classes(racer_locked_pads=False)
        self.assertEqual(len(classes), 15)
        for name, cls in classes.items():
            with self.subTest(name=name):
                self.assertEqual(cls, ItemClassification.useful)

    def test_locks_on_promotes_the_unlocks_to_progression(self):
        classes = self._classes(racer_locked_pads=True)
        self.assertEqual(len(classes), 15)
        for name, cls in classes.items():
            with self.subTest(name=name):
                self.assertEqual(cls, ItemClassification.progression)

    def test_locks_off_means_no_access_rule_names_a_racer(self):
        """R17's soundness condition, stated as a property rather than as
        prose: with locks off the seed must plan around the starting racer
        only, which is exactly 'no rule reads a character item'."""
        mw = _build(1, racer_locked_pads=False)
        world = mw.worlds[1]
        self.assertEqual(world.ctr_racer_locks, {})
        state = mw.get_all_state(False)
        for name in ROSTER_CHARACTER_ID:
            state.remove_item = None  # guard against accidental API drift
            break
        # Removing every character item from an all-items state must not close
        # any entrance, i.e. nothing depends on one.
        full = mw.get_all_state(False)
        reachable_with = {e.name for e in mw.get_entrances()
                          if e.access_rule(full)}
        stripped = mw.get_all_state(False)
        for item in list(stripped.prog_items[1]):
            if item in ROSTER_CHARACTER_ID:
                del stripped.prog_items[1][item]
        reachable_without = {e.name for e in mw.get_entrances()
                             if e.access_rule(stripped)}
        self.assertEqual(reachable_with, reachable_without)


# ---------------------------------------------------------------------------
# All-unlocked comfort mode (wayfarer gap 7a)
# ---------------------------------------------------------------------------

class TestAllUnlockedMode(unittest.TestCase):

    def test_no_unlock_items_are_created(self):
        mw = _build(1, character_unlocks=False)
        pooled = [i.name for i in mw.itempool
                  if i.player == 1 and i.name in ROSTER_CHARACTER_ID]
        self.assertEqual(pooled, [])

    def test_the_starter_is_still_precollected(self):
        mw = _build(1, character_unlocks=False)
        start = mw.worlds[1].ctr_starting_character
        self.assertIn(start, {i.name for i in mw.precollected_items[1]})

    def test_racer_locks_are_forced_off(self):
        mw = _build(1, character_unlocks=False, racer_locked_pads=True)
        self.assertEqual(mw.worlds[1].ctr_racer_locks, {})
        block = mw.worlds[1].fill_slot_data()["racer_locks"]
        self.assertFalse(block["enabled"])
        self.assertEqual(block["pads"], {})

    def test_it_is_what_makes_a_podium_off_seed_generate(self):
        """The AP invariant, exercised in both directions rather than argued.
        A podium-off seed has ~101 locations against ~99 fixed items; the 15
        unlock items do not fit, and the ruled answer is all-unlocked mode."""
        with self.assertRaises(OptionError):
            _build(1, podium_placement_checks=False)
        # Same seed, same option, plus the named fix -> generates.
        mw = _build(1, podium_placement_checks=False, character_unlocks=False)
        self.assertEqual(len(mw.itempool),
                         len(mw.get_unfilled_locations(1)))

    def test_the_error_names_both_concrete_fixes(self):
        with self.assertRaises(OptionError) as ctx:
            _build(1, podium_placement_checks=False)
        message = str(ctx.exception)
        self.assertIn("character_unlocks", message)
        self.assertIn("Podium Placement Checks", message)


# ---------------------------------------------------------------------------
# Racer-locked pads (R8)
# ---------------------------------------------------------------------------

class TestRacerLocks(unittest.TestCase):

    def test_locks_exist_and_name_real_racers(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = _build(seed, racer_locked_pads=True).worlds[1]
                locks = world.ctr_racer_locks
                self.assertTrue(locks, "racer locks on produced no locks")
                for pad, racer in locks.items():
                    self.assertIn(racer, ROSTER_CHARACTER_ID)
                    self.assertIn(pad, world.warp_pad_ids)

    def test_a_lock_never_names_the_starting_racer(self):
        """A lock on the racer you already have is satisfied at spawn and
        spends an eligible pad on nothing."""
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = _build(seed, racer_locked_pads=True).worlds[1]
                self.assertNotIn(world.ctr_starting_character,
                                 set(world.ctr_racer_locks.values()))

    def test_locks_never_land_on_a_bootstrap_or_free_pad(self):
        """The solvability backbone: the always-open N. Sanity Beach starters
        and this seed's free subset are what guarantee sphere 0 is non-empty.
        Locking one behind a unique single-copy item would collapse it."""
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = _build(seed, racer_locked_pads=True).worlds[1]
                eligible = set(eligible_lock_pads(world))
                for pad in world.ctr_racer_locks:
                    self.assertIn(pad, eligible)
                    self.assertFalse(world.warp_pad_ids[pad].get("bootstrap"))
                    req = world.warp_pad_unlock.get(pad)
                    self.assertIsNotNone(req)
                    free = req["type"] == 0 or (
                        req["type"] == 1 and req["count"] <= 0)
                    self.assertFalse(free, f"{pad} was a free pad")

    def test_a_lock_is_ANDed_on_top_of_the_existing_requirement(self):
        """The lock must not replace the sphere search's own gate. Proven by
        showing the pad is still closed to a state that holds the racer but
        nothing else."""
        world = _build(1, racer_locked_pads=True).worlds[1]
        mw = world.multiworld
        for pad, racer in world.ctr_racer_locks.items():
            with self.subTest(pad=pad):
                ent = mw.get_entrance(pad, 1)
                # State with the racer and nothing else must not open a pad
                # whose stage 1 also demands trophies/keys/tokens.
                state = mw.get_all_state(False)
                for item in list(state.prog_items[1]):
                    if item != racer:
                        del state.prog_items[1][item]
                req = world.warp_pad_unlock[pad]
                if req["type"] != 0 and req["count"] > 0:
                    self.assertFalse(
                        ent.access_rule(state),
                        f"{pad}'s original requirement was replaced, not ANDed")

    def test_removing_the_required_racer_closes_the_pad(self):
        world = _build(1, racer_locked_pads=True).worlds[1]
        mw = world.multiworld
        for pad, racer in world.ctr_racer_locks.items():
            with self.subTest(pad=pad):
                ent = mw.get_entrance(pad, 1)
                full = mw.get_all_state(False)
                self.assertTrue(ent.access_rule(full))
                without = mw.get_all_state(False)
                del without.prog_items[1][racer]
                self.assertFalse(ent.access_rule(without))

    def test_slot_data_block_shape(self):
        world = _build(1, racer_locked_pads=True).worlds[1]
        block = world.fill_slot_data()["racer_locks"]
        self.assertTrue(block["enabled"])
        self.assertEqual(len(block["pads"]), len(world.ctr_racer_locks))
        for level_id, character_id in block["pads"].items():
            self.assertIsInstance(level_id, str)
            self.assertTrue(level_id.isdigit())
            self.assertIn(character_id, range(16))
        # Keys are physical pad LevelIDs, values are ENGINE character ids.
        by_pad = {str(world.warp_pad_ids[pad]["level_id"]):
                  ROSTER_CHARACTER_ID[racer]
                  for pad, racer in world.ctr_racer_locks.items()}
        self.assertEqual(block["pads"], by_pad)

    def test_block_is_emitted_even_when_the_option_is_off(self):
        """Same convention as `itemsanity` / `shortcut_knowledge`: a tracker
        must be able to tell 'locks off' from 'seed predates the feature'."""
        world = _build(1, racer_locked_pads=False).worlds[1]
        block = world.fill_slot_data()["racer_locks"]
        self.assertFalse(block["enabled"])
        self.assertEqual(block["pads"], {})
        self.assertEqual(block["requested_count"], 0)

    def test_determinism(self):
        a = _build(7, racer_locked_pads=True).worlds[1].ctr_racer_locks
        b = _build(7, racer_locked_pads=True).worlds[1].ctr_racer_locks
        self.assertEqual(a, b)

    def test_ut_reconstruction_round_trips_the_wire_block(self):
        world = _build(11, racer_locked_pads=True).worlds[1]
        wire = world.fill_slot_data()
        self.assertEqual(
            reconstruct_racer_locks_from_wire(world, wire),
            world.ctr_racer_locks)

    def test_ut_reconstruction_of_an_older_wire_is_empty_not_an_error(self):
        world = _build(11).worlds[1]
        self.assertEqual(reconstruct_racer_locks_from_wire(world, {}), {})
        self.assertEqual(
            reconstruct_racer_locks_from_wire(world, {"racer_locks": {}}), {})


class TestRacerLockCount(unittest.TestCase):
    """`racer_locked_pads` is a MAXIMUM lock count (2026-08-29 specification,
    Lane B), not the Alpha 6 toggle. The number the player writes is a request;
    the seed takes `min(requested, eligible)` and never violates an eligibility
    rule to reach the number.
    """

    # Every count case shares one seed so the eligible set is the same set in
    # all of them and the only variable is the request.
    SEED = 5150

    @classmethod
    def setUpClass(cls):
        # The eligible set does not depend on the requested count (it is
        # resolved from the sphere search's pad requirements), so one build is
        # enough to learn this seed's ceiling.
        world = _build(cls.SEED, racer_locked_pads=1).worlds[1]
        cls.eligible = len(eligible_lock_pads(world))
        assert cls.eligible >= 5, "seed no longer has enough eligible pads"

    def _locks(self, requested):
        return _build(self.SEED, racer_locked_pads=requested).worlds[1]

    def test_range_ceiling_is_the_physical_pad_census(self):
        """The ceiling must BE the pad census, not a literal that happens to
        match it today: a pad added to data/warp_pad_ids.json must move the
        option's maximum with it."""
        census = json.loads(
            pkgutil.get_data("worlds.ctr", "data/warp_pad_ids.json")
            .decode("utf-8"))["pads"]
        self.assertEqual(PHYSICAL_PAD_COUNT, len(census))
        self.assertEqual(RacerLockedPads.range_end, len(census))
        self.assertEqual(RacerLockedPads.range_start, 0)
        self.assertEqual(RacerLockedPads.default, 0)
        # Every pad the option could ever be asked to lock is in that file, so
        # a request at the ceiling can never be short of physical pads.
        self.assertGreaterEqual(RacerLockedPads.range_end, self.eligible)

    def test_zero_disables(self):
        world = self._locks(0)
        self.assertEqual(world.ctr_racer_locks, {})
        self.assertEqual(world.fill_slot_data()["racer_locks"]["pads"], {})

    def test_one_lock(self):
        self.assertEqual(len(self._locks(1).ctr_racer_locks), 1)

    def test_an_ordinary_middle_value(self):
        self.assertEqual(len(self._locks(4).ctr_racer_locks), 4)

    def test_exactly_the_eligible_count(self):
        world = self._locks(self.eligible)
        self.assertEqual(len(world.ctr_racer_locks), self.eligible)
        self.assertEqual(set(world.ctr_racer_locks),
                         set(eligible_lock_pads(world)))

    def test_above_the_eligible_count_clamps_instead_of_failing(self):
        """The help text's promise: asking for more than the seed can give is
        not an error, it is a smaller number of locks."""
        for requested in (self.eligible + 1, PHYSICAL_PAD_COUNT):
            with self.subTest(requested=requested):
                world = self._locks(requested)
                self.assertEqual(len(world.ctr_racer_locks), self.eligible)
                requested_count, eligible_count = racer_lock_counts(world)
                self.assertEqual(requested_count, requested)
                self.assertEqual(eligible_count, self.eligible)

    def test_the_count_never_exceeds_the_request(self):
        for requested in (0, 1, 4, self.eligible, PHYSICAL_PAD_COUNT):
            with self.subTest(requested=requested):
                world = self._locks(requested)
                self.assertLessEqual(len(world.ctr_racer_locks), requested)

    def test_selection_is_deterministic_for_a_seed_and_a_count(self):
        for requested in (1, 4, PHYSICAL_PAD_COUNT):
            with self.subTest(requested=requested):
                self.assertEqual(self._locks(requested).ctr_racer_locks,
                                 self._locks(requested).ctr_racer_locks)

    def test_the_pads_are_distinct(self):
        world = self._locks(4)
        self.assertEqual(len(set(world.ctr_racer_locks)), 4)

    def test_exclusions_hold_at_every_count(self):
        """Raising the requested count may not buy a lock by breaking an
        eligibility rule: no bootstrap pad, no free pad, no pad this seed did
        not randomize, and never the starting racer."""
        for requested in (1, 4, PHYSICAL_PAD_COUNT):
            for seed in (1, 2, 3):
                with self.subTest(requested=requested, seed=seed):
                    world = _build(seed,
                                   racer_locked_pads=requested).worlds[1]
                    eligible = set(eligible_lock_pads(world))
                    self.assertNotIn(world.ctr_starting_character,
                                     set(world.ctr_racer_locks.values()))
                    for pad in world.ctr_racer_locks:
                        self.assertIn(pad, eligible)
                        self.assertFalse(
                            world.warp_pad_ids[pad].get("bootstrap"))
                        req = world.warp_pad_unlock.get(pad)
                        self.assertIsNotNone(req)
                        self.assertFalse(
                            req["type"] == 0
                            or (req["type"] == 1 and req["count"] <= 0),
                            f"{pad} was a free pad")

    def test_destination_shuffle_does_not_change_how_many_locks_you_get(self):
        """The count applies to PHYSICAL pads, so rewiring where a pad leads
        cannot change it."""
        plain = _build(21, racer_locked_pads=4).worlds[1]
        shuffled = _build(21, racer_locked_pads=4,
                          warp_pad_shuffle_categories="all").worlds[1]
        self.assertEqual(len(plain.ctr_racer_locks), 4)
        self.assertEqual(len(shuffled.ctr_racer_locks), 4)

    # -- classification --------------------------------------------------

    def _unlock_classes(self, **options):
        mw = _build(1, **options)
        return {i.classification for i in mw.itempool
                if i.player == 1 and i.name in ROSTER_CHARACTER_ID}

    def test_a_positive_count_promotes_the_unlocks_to_progression(self):
        self.assertEqual(self._unlock_classes(racer_locked_pads=4),
                         {ItemClassification.progression})

    def test_an_inert_request_leaves_the_unlocks_useful(self):
        """Progression exactly when the EFFECTIVE map is non-empty. A vanilla
        pad seed randomizes no pad, so a request for 4 locks produces none, and
        charging the fill for a feature the seed does not have would be the
        #145-class inflation R17 exists to avoid."""
        world = _build(1, racer_locked_pads=4,
                       warppad_unlock_requirements="vanilla").worlds[1]
        self.assertEqual(eligible_lock_pads(world), [])
        self.assertEqual(world.ctr_racer_locks, {})
        self.assertEqual(
            self._unlock_classes(racer_locked_pads=4,
                                 warppad_unlock_requirements="vanilla"),
            {ItemClassification.useful})

    def test_unlocks_off_forces_an_empty_map_and_says_so_once(self):
        mw, messages = _build_with_warnings(
            1, character_unlocks=False, racer_locked_pads=4)
        world = mw.worlds[1]
        self.assertEqual(world.ctr_racer_locks, {})
        block = world.fill_slot_data()["racer_locks"]
        self.assertFalse(block["enabled"])
        self.assertEqual(block["pads"], {})
        self.assertEqual(block["requested_count"], 0)
        forced = [m for m in messages
                  if "Racer-Locked Warp Pads" in m
                  and "Character Unlocks is off" in m]
        self.assertEqual(len(forced), 1, messages)

    # -- wire ------------------------------------------------------------

    def test_slot_data_reports_requested_and_eligible(self):
        world = self._locks(4)
        block = world.fill_slot_data()["racer_locks"]
        self.assertTrue(block["enabled"])
        self.assertEqual(block["requested_count"], 4)
        self.assertEqual(block["eligible_count"], self.eligible)
        self.assertEqual(len(block["pads"]), 4)

    def test_the_scalar_is_the_requested_integer(self):
        """`ctr_options.racer_locked_pads` carries the request, and an older
        native reading it as a Boolean still sees 0 as off and any positive
        count as on."""
        for requested in (0, 1, 4, PHYSICAL_PAD_COUNT):
            with self.subTest(requested=requested):
                wire = self._locks(requested).fill_slot_data()
                self.assertEqual(wire["ctr_options"]["racer_locked_pads"],
                                 requested)

    def test_ut_reconstructs_the_map_and_the_counts_without_redrawing(self):
        world = self._locks(4)
        wire = world.fill_slot_data()
        expected_counts = racer_lock_counts(world)
        # Wipe the stored counts so a passing assertion cannot be the ones
        # generation already left behind.
        world.ctr_racer_lock_counts = None
        self.assertEqual(reconstruct_racer_locks_from_wire(world, wire),
                         world.ctr_racer_locks)
        self.assertEqual(racer_lock_counts(world), expected_counts)

    def test_ut_falls_back_when_a_wire_predates_the_counts(self):
        world = self._locks(4)
        block = dict(world.fill_slot_data()["racer_locks"])
        block.pop("requested_count")
        block.pop("eligible_count")
        world.ctr_racer_lock_counts = None
        locks = reconstruct_racer_locks_from_wire(world, {"racer_locks": block})
        self.assertEqual(locks, world.ctr_racer_locks)
        self.assertEqual(racer_lock_counts(world), (4, self.eligible))


class TestAlpha6BooleanCompatibility(unittest.TestCase):
    """A YAML written against Alpha 6 says `racer_locked_pads: true`. `bool` is
    an `int` subclass, so the stock Range reading of that is 1 -- one lock,
    where Alpha 6 gave a quarter of the eligible pads. The 2026-08-29 ruling
    forbids that silent reinterpretation: `true` keeps its Alpha 6 meaning and
    the run says so once."""

    def test_boolean_true_is_flagged_rather_than_read_as_one(self):
        option = RacerLockedPads.from_any(True)
        self.assertTrue(option.legacy_boolean_auto)
        self.assertNotEqual(option.value, 1)

    def test_boolean_false_is_zero(self):
        option = RacerLockedPads.from_any(False)
        self.assertFalse(option.legacy_boolean_auto)
        self.assertEqual(option.value, 0)

    def test_the_integer_one_is_still_one_lock(self):
        option = RacerLockedPads.from_any(1)
        self.assertFalse(option.legacy_boolean_auto)
        self.assertEqual(option.value, 1)
        self.assertEqual(len(_build(5150, racer_locked_pads=1)
                             .worlds[1].ctr_racer_locks), 1)

    def test_quoted_true_and_false_normalize_the_same_way(self):
        self.assertTrue(RacerLockedPads.from_any("true").legacy_boolean_auto)
        self.assertTrue(RacerLockedPads.from_any("on").legacy_boolean_auto)
        self.assertEqual(RacerLockedPads.from_any("false").value, 0)
        self.assertFalse(RacerLockedPads.from_any("false").legacy_boolean_auto)

    def test_true_reproduces_the_alpha6_automatic_density(self):
        """A quarter of the eligible pads, clamped 1..6 -- the exact policy the
        Alpha 6 toggle used, so an Alpha 6 YAML keeps generating Alpha 6
        seeds."""
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = _build(seed, racer_locked_pads=True).worlds[1]
                eligible = len(eligible_lock_pads(world))
                expected = max(1, min(6, int(eligible * 0.25)))
                self.assertEqual(len(world.ctr_racer_locks),
                                 min(expected, eligible))
                self.assertEqual(requested_lock_count(world, eligible),
                                 expected)

    def test_the_normalization_is_logged_exactly_once(self):
        messages = _forced_option_warnings(1, racer_locked_pads=True)
        said = [m for m in messages if "maximum lock COUNT" in m]
        self.assertEqual(len(said), 1, messages)
        message = said[0]
        # It must name what it did and what to write instead, not merely warn.
        self.assertIn("Alpha 6 way", message)
        self.assertIn("0 turns racer locks off", message)

    def test_false_says_nothing_because_off_means_the_same_thing(self):
        said = [m for m in _forced_option_warnings(1, racer_locked_pads=False)
                if "maximum lock COUNT" in m]
        self.assertEqual(said, [])

    def test_an_integer_request_says_nothing_either(self):
        said = [m for m in _forced_option_warnings(1, racer_locked_pads=4)
                if "maximum lock COUNT" in m]
        self.assertEqual(said, [])

    def test_a_boolean_seed_still_survives_a_real_fill(self):
        from Fill import distribute_items_restrictive
        mw = _build(3, racer_locked_pads=True)
        distribute_items_restrictive(mw)
        verify_no_self_lock(mw.worlds[1])


class TestSelfLockInvariant(CTRTestBase):
    """Issue #209's named hazard: a fill that places racer X's unlock item
    behind a pad requiring racer X. `verify_no_self_lock` re-derives the
    invariant from the FILLED multiworld; these drive a real fill so the check
    runs against real placements rather than a constructed example."""

    options = {"racer_locked_pads": True}

    def test_a_real_fill_satisfies_the_invariant(self):
        self.assertTrue(self.world.ctr_racer_locks)
        verify_no_self_lock(self.world)  # raises on violation

    def test_the_verifier_actually_catches_a_violation(self):
        """A verifier that cannot fail proves nothing.

        Runs a REAL fill (WorldTestBase stops before it, so the base fixture
        has no placements to inspect), then forcibly re-points a lock at a
        racer whose unlock item is seated behind that very pad and confirms
        the check raises. This is the deadlock #209 names, constructed by
        hand because generation cannot produce it.
        """
        from Fill import distribute_items_restrictive
        mw = _build(3, racer_locked_pads=True)
        world = mw.worlds[1]
        distribute_items_restrictive(mw)
        pad = next(iter(world.ctr_racer_locks))
        ent = mw.get_entrance(pad, 1)

        victim = next(
            (loc for loc in mw.get_filled_locations()
             if loc.item is not None and loc.item.player == 1
             and loc.item.name in ROSTER_CHARACTER_ID),
            None)
        self.assertIsNotNone(victim, "no character unlock was placed locally")
        racer = victim.item.name

        # Make the pad require exactly that racer, and put the victim location
        # behind the pad. Both are local monkeypatches on this throwaway
        # multiworld; nothing else reads them.
        world.ctr_racer_locks = {pad: racer}
        ent.access_rule = (lambda state, i=racer: state.has(i, 1))
        victim.access_rule = (lambda state, e=ent: e.access_rule(state))

        with self.assertRaises(OptionError) as ctx:
            verify_no_self_lock(world)
        self.assertIn(racer, str(ctx.exception))


class TestRacerLockedSeedsFill(unittest.TestCase):
    """The rulings are explicit that racer-lock solvability must be PROVEN by
    generation, never asserted (ticket 5). These run full fills."""

    def test_locked_seeds_fill_across_seeds(self):
        from Fill import distribute_items_restrictive
        for seed in SEEDS:
            with self.subTest(seed=seed):
                mw = _build(seed, racer_locked_pads=True)
                distribute_items_restrictive(mw)  # raises FillError on a starve
                verify_no_self_lock(mw.worlds[1])

    def test_locked_seeds_fill_with_full_accessibility(self):
        from Fill import distribute_items_restrictive
        for seed in SEEDS[:3]:
            with self.subTest(seed=seed):
                mw = _build(seed, racer_locked_pads=True, accessibility="full")
                distribute_items_restrictive(mw)
                state = mw.get_all_state(False)
                unreachable = [loc.name for loc in mw.get_locations()
                               if not loc.can_reach(state)]
                self.assertEqual(unreachable, [])


# ---------------------------------------------------------------------------
# Stat ownership precedence and Penta (2026-08-08 ruling, R15)
# ---------------------------------------------------------------------------

class TestStatPrecedence(unittest.TestCase):
    """The precedence lives in ONE resolver. Native receives the resolved
    outcome and must not re-implement the rule."""

    def _config(self, **options):
        return effective_stat_config(_build(1, **options).worlds[1])

    def test_both_off_is_vanilla_read_only(self):
        self.assertEqual(self._config(),
                         (STAT_SOURCE_VANILLA, STAT_OWNER_NONE, False))

    def test_editable_alone_grants_editing_at_its_own_granularity(self):
        self.assertEqual(self._config(editable_stats="global"),
                         (STAT_SOURCE_EDITABLE, STAT_OWNER_GLOBAL, True))
        self.assertEqual(self._config(editable_stats="per_character"),
                         (STAT_SOURCE_EDITABLE, STAT_OWNER_PER_CHARACTER, True))

    def test_progressive_alone_is_read_only(self):
        self.assertEqual(self._config(progressive_stats="shared_global"),
                         (STAT_SOURCE_PROGRESSIVE, STAT_OWNER_GLOBAL, False))

    def test_progressive_wins_outright_when_both_are_set(self):
        for editable in ("global", "per_character"):
            with self.subTest(editable=editable):
                source, owner, can_edit = self._config(
                    progressive_stats="shared_global", editable_stats=editable)
                self.assertEqual(source, STAT_SOURCE_PROGRESSIVE)
                self.assertEqual(owner, STAT_OWNER_GLOBAL)
                self.assertFalse(can_edit)

    def test_setting_both_does_not_reject_the_seed(self):
        """The 2026-08-08 ruling is explicit: 'this simple combination does not
        invalidate or reject a seed'."""
        mw = _build(1, progressive_stats="shared_global",
                    editable_stats="per_character")
        self.assertTrue(mw.itempool)

    def test_the_resolved_outcome_is_what_goes_on_the_wire(self):
        world = _build(1, progressive_stats="shared_global",
                       editable_stats="global").worlds[1]
        options = world.fill_slot_data()["ctr_options"]
        self.assertEqual(options["stat_source"], STAT_SOURCE_PROGRESSIVE)
        self.assertEqual(options["stat_owner"], STAT_OWNER_GLOBAL)
        self.assertFalse(options["stat_editing_allowed"])
        # The raw option is still on the wire for trackers; native must read
        # the resolved trio, not this.
        self.assertEqual(options["editable_stats"], 1)


class TestCharacterSlotData(unittest.TestCase):

    def test_every_scalar_is_emitted_unconditionally(self):
        options = _build(1).worlds[1].fill_slot_data()["ctr_options"]
        for key in ("starting_character", "starting_stat_class",
                    "character_unlocks", "racer_locked_pads", "penta_stats",
                    "editable_stats", "stat_source", "stat_owner",
                    "stat_editing_allowed"):
            self.assertIn(key, options)

    def test_ut_restores_the_two_logic_relevant_character_options(self):
        """Regression for the check-ut fuzz red: a UT re-generation that falls
        back to the tracking player's own `character_unlocks` rebuilds a
        different item pool than the seed has, and on a reduced seed the
        re-generation raises outright."""
        world = _build(1, podium_placement_checks=False,
                       character_unlocks=False).worlds[1]
        wire = world.fill_slot_data()["ctr_options"]
        self.assertFalse(wire["character_unlocks"])

        # Restore into a world whose own YAML says the opposite.
        other = _build(2, character_unlocks=True,
                       racer_locked_pads=True).worlds[1]
        other._ut_restore_options({"ctr_options": wire})
        self.assertFalse(other.options.character_unlocks.value)
        self.assertFalse(other.options.racer_locked_pads.value)

    def test_starting_character_travels_as_an_engine_id(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = _build(seed).worlds[1]
                options = world.fill_slot_data()["ctr_options"]
                self.assertEqual(
                    options["starting_character"],
                    ROSTER_CHARACTER_ID[world.ctr_starting_character])
                self.assertIn(options["starting_character"], range(16))

    def test_penta_stats_defaults_to_ntsc_the_ordinary_table(self):
        """The DEFAULT SEED IS UNCHANGED ON THE WIRE by the 2026-08-21 relabel.

        The labels were inverted until then: NTSC-U Penta reuses Polar and
        Pura's ordinary TURN class, and the fifth MAX class is the PAL/JP one.
        Only the names moved. 0 was and remains the ordinary table and the
        default, 1 was and remains MAX, which is what native reads
        (ap_charswap.c ap_cs_pentaUsesMaxClass). This test pins the numbers,
        not the words, so it would fail if a future relabel moved them.
        """
        options = _build(1).worlds[1].fill_slot_data()["ctr_options"]
        self.assertEqual(options["penta_stats"], 0)
        options = _build(1, penta_stats="ntsc").worlds[1] \
            .fill_slot_data()["ctr_options"]
        self.assertEqual(options["penta_stats"], 0)
        options = _build(1, penta_stats="pal").worlds[1] \
            .fill_slot_data()["ctr_options"]
        self.assertEqual(options["penta_stats"], 1)

    def test_no_schema_bump(self):
        """Every key here is additive under the current unconditional schema 8
        (Q28), and native reads ctr_options by explicit named key."""
        self.assertEqual(_build(1).worlds[1].fill_slot_data()["ctr_options"]
                         ["schema_version"], 8)

    def test_ut_restores_the_starting_character_rather_than_redrawing(self):
        from ..characters import restore_starting_character
        world = _build(5).worlds[1]
        wire = world.fill_slot_data()["ctr_options"]
        self.assertEqual(restore_starting_character(world, wire),
                         world.ctr_starting_character)

    def test_ut_restore_of_an_older_wire_falls_back_to_a_draw(self):
        from ..characters import restore_starting_character
        world = _build(5).worlds[1]
        self.assertIn(restore_starting_character(world, {}), ROSTER)


# ---------------------------------------------------------------------------
# Net-capacity across every enabled location and item family (Stef's 00:51
# ruling: "Count every location actually created by all enabled families
# against the complete item demand; fail cleanly when demand exceeds supply;
# fill surplus with normal filler.")
# ---------------------------------------------------------------------------

def _pool_supply(mw, player=1):
    """(pool items, unfilled locations) for the player, both live counts."""
    return len(mw.itempool), len(mw.get_unfilled_locations(player))


class TestNetCapacityAcrossLocationAndItemFamilies(unittest.TestCase):
    """The single authoritative accounting point in create_items must balance
    pool == locations for every combination of enabled families, and the
    character-supply guard must fire with needed/available counts and generic
    guidance rather than pretending one family is mandatory.

    Each family contributes BOTH sides of the ledger that the guard is
    supposed to count exactly once:
      * podium rungs   -- locations only (16 tracks x rung categories)
      * #109 boxes     -- locations only (229 at easy knowledge)
      * lettersanity   -- locations only, currently INERT (registered, not
        created) in this branch
      * relic-perfect  -- locations only, currently INERT
      * itemsanity     -- 22 locations AND 11 weapon items
      * progressive    -- items only (3 boost + 12 stats)
      * character      -- 15 unlock items, ZERO locations
    """

    def test_default_balance(self):
        mw = _build(1)
        self.assertEqual(*_pool_supply(mw))

    def test_itemsanity_balance(self):
        mw = _build(1, itemsanity=True)
        self.assertEqual(*_pool_supply(mw))

    def test_box_locations_balance(self):
        mw = _build(1, box_locations=True)
        self.assertEqual(*_pool_supply(mw))

    def test_itemsanity_and_boxes_balance(self):
        mw = _build(1, itemsanity=True, box_locations=True)
        self.assertEqual(*_pool_supply(mw))

    def test_progressive_packs_balance(self):
        mw = _build(1, progressive_boost="shared_global",
                    progressive_boost_blue_fire=True,
                    progressive_stats="shared_global")
        self.assertEqual(*_pool_supply(mw))

    def test_everything_together_balance(self):
        mw = _build(1, itemsanity=True, box_locations=True,
                    progressive_boost="shared_global",
                    progressive_boost_blue_fire=True,
                    progressive_stats="shared_global")
        self.assertEqual(*_pool_supply(mw))

    def test_everything_together_all_unlocked_balance(self):
        mw = _build(1, itemsanity=True, box_locations=True,
                    character_unlocks=False,
                    progressive_boost="shared_global",
                    progressive_boost_blue_fire=True,
                    progressive_stats="shared_global")
        self.assertEqual(*_pool_supply(mw))

    def test_itemsanity_adds_both_locations_and_items_and_balances(self):
        """Itemsanity contributes 22 locations AND 11 weapon items; the pool
        still balances (filler absorbs the +11 net supply)."""
        base_pool, base_unfilled = _pool_supply(_build(1))
        mw = _build(1, itemsanity=True)
        pool, unfilled = _pool_supply(mw)
        self.assertEqual(pool, unfilled)
        created = len(ITEMSANITY_CLASS.created_locations(
            mw.worlds[1].options))
        self.assertEqual(created, 22)
        # locations grew by the class's 22; items grew by the class's 11.
        self.assertEqual(unfilled - base_unfilled, 22)
        self.assertEqual(pool - base_pool, 22)

    def test_boxes_add_locations_only(self):
        base_pool, base_unfilled = _pool_supply(_build(1))
        pool, unfilled = _pool_supply(_build(1, box_locations=True))
        self.assertEqual(pool - base_pool, unfilled - base_unfilled)
        self.assertEqual(unfilled - base_unfilled,
                         len(ITEM_BOX_CLASS.created_locations(
                             _build(1, box_locations=True).worlds[1].options)))

    def test_lettersanity_and_relic_perfect_are_inert_this_branch(self):
        """Both classes are registered but create no locations yet (#148,
        #49 build); they must not disturb the pool balance."""
        for cls in (LETTERSANITY_CLASS, RELIC_PERFECT_CLASS):
            with self.subTest(cls=cls.key):
                options = _build(1).worlds[1].options
                self.assertEqual(cls.created_location_names(options), [])

    def test_fill_surplus_with_filler_under_heavy_families(self):
        """The pool/location balance survives a real fill, not just the
        create_items arithmetic."""
        from Fill import distribute_items_restrictive
        mw = _build(1, itemsanity=True, box_locations=True,
                    progressive_boost="shared_global",
                    progressive_boost_blue_fire=True,
                    progressive_stats="shared_global")
        distribute_items_restrictive(mw)  # must not raise FillError

    def test_exclusions_do_not_break_the_net_capacity_accounting(self):
        """Excluding locations keeps pool == locations: the excluded slots are
        still live unfilled locations that normal filler seats into, so the
        single authoritative accounting point must still balance after
        Main.py's exclusion_rules applies the player's set."""
        from Fill import distribute_items_restrictive
        from worlds.generic.Rules import exclusion_rules
        mw = _build(1)
        excluded = {loc.name for loc in mw.get_unfilled_locations(1)[:5]}
        exclusion_rules(mw, 1, excluded)
        pool, unfilled = _pool_supply(mw)
        self.assertEqual(pool, unfilled)
        distribute_items_restrictive(mw)  # must not raise FillError

    def test_all_unlocked_with_exclusions_balances(self):
        from worlds.generic.Rules import exclusion_rules
        mw = _build(1, character_unlocks=False)
        excluded = {loc.name for loc in mw.get_unfilled_locations(1)[:5]}
        exclusion_rules(mw, 1, excluded)
        self.assertEqual(*_pool_supply(mw))

    def test_character_guard_reports_needed_and_available_counts(self):
        world = _build(1).worlds[1]
        needed = len(ROSTER) - 1  # 15
        with self.assertRaises(OptionError) as ctx:
            raise_if_unlocks_exceed_location_supply(
                world, available_supply=needed - 1)
        message = str(ctx.exception)
        self.assertIn(str(needed), message)
        self.assertIn(str(needed - 1), message)

    def test_character_guard_does_not_pretend_one_family_is_mandatory(self):
        world = _build(1).worlds[1]
        with self.assertRaises(OptionError) as ctx:
            raise_if_unlocks_exceed_location_supply(
                world, available_supply=0)
        message = str(ctx.exception)
        # The old text forced Podium Placement Checks + all-unlocked as the
        # ONLY fixes. The corrected text must not claim a single family is
        # mandatory: it should offer both more location checks and fewer
        # item-producing options, and name at least one non-podium family.
        self.assertIn("location checks", message)
        self.assertIn("item-producing options", message)
        self.assertIn("Item Box Checks", message)
        self.assertIn("character_unlocks", message)

    def test_character_guard_is_a_noop_in_all_unlocked_mode(self):
        world = _build(1, character_unlocks=False).worlds[1]
        raise_if_unlocks_exceed_location_supply(world, available_supply=0)

    def test_podium_off_shortfall_still_raises_cleanly(self):
        """Regression for the reachable shortfall: a reduced seed raises a
        clean OptionError (the rung sizer names Character Unlocks; the guard
        names counts), never a raw FillError."""
        with self.assertRaises(OptionError):
            _build(1, podium_placement_checks=False)


if __name__ == "__main__":
    unittest.main()
