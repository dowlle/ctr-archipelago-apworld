"""All-sixteen Hit Character reachability and eligibility growth (tickets 07/08).

This file owns the generation-level obligations of ticket 08:

  * all sixteen enabled Hit checks are created and mandatory, each with a real
    rule (the fifteen ticket-06 scaffolds are gone);
  * a fresh `accessibility: full` seed proves every one reachable across the
    option shapes the ticket names;
  * eligibility growth is monotone: acquiring items or triggers never removes a
    target's last feasible encounter;
  * early and late unlock order and a self-character conflict are covered
    directly, not only by a green seed;
  * an adversarial seed whose target cannot appear fails clearly.

Direct predicate tests live in test_hit_character_route.py.
"""
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import characters, ctrAPWorld
from ..hit_character import HIT_CHARACTER_CLASS

PLAYER = 1
ALL_TARGETS = tuple(range(16))
TRIAL = {"slide_coliseum_races": "trophy_race",
         "turbo_track_races": "trophy_race"}

#: Seeds fixed so a failure is reproducible. The generation matrix is run
#: separately by the manager; these are the fresh-seed accessibility proofs.
SEEDS = (1, 2, 3)

#: The option shapes ticket 08 names.
SHAPES = {
    "default": {},
    "tracks_shuffle": {"warp_pad_shuffle_categories": ["tracks"]},
    "no_shuffle": {"warp_pad_shuffle_categories": []},
    "unlocks_off": {"character_unlocks": False},
    "itemsanity": {"itemsanity": True},
    "start_fake_crash": {"starting_character": "fake_crash"},
    "start_oxide": {"starting_character": "nitros_oxide"},
}


def _build(seed=1, steps=("generate_early", "create_regions", "create_items",
                          "set_rules"), **overrides):
    options = dict(TRIAL)
    options.update(overrides)
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


def _hit_rule(mw, cid):
    return mw.get_location(
        HIT_CHARACTER_CLASS.location_name(cid), PLAYER).access_rule


def _reached_names(mw):
    """The sphere-reachable location names from an empty inventory."""
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


def _generate(seed, **options):
    opts = dict(TRIAL)
    opts.update(options)
    opts["hit_character"] = True
    opts["accessibility"] = "full"
    mw = setup_multiworld(ctrAPWorld, gen_steps, seed=seed, options=opts)
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    return mw


class TestAllSixteenCreated(unittest.TestCase):
    """Every enabled check exists, is mandatory, and has a real rule."""

    def test_all_sixteen_created(self):
        mw = _build(seed=1, hit_character=True)
        names = {loc.name for loc in mw.get_locations(PLAYER)}
        for cid in ALL_TARGETS:
            with self.subTest(engine_id=cid):
                self.assertIn(HIT_CHARACTER_CLASS.location_name(cid), names)

    def test_rules_are_not_the_always_true_scaffold(self):
        mw = _build(seed=1, hit_character=True)
        empty = CollectionState(mw)
        reachable = {cid for cid in ALL_TARGETS if _hit_rule(mw, cid)(empty)}
        # Not the placeholder: an empty inventory cannot satisfy every target,
        # yet some real starter routes are open.
        self.assertNotEqual(reachable, set(ALL_TARGETS))
        self.assertTrue(reachable)

    def test_all_sixteen_reachable_from_all_items(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.player == PLAYER:
                state.collect(world.create_item(item.name), prevent_sweep=True)
        for item in mw.precollected_items.get(PLAYER, ()):
            state.collect(item, prevent_sweep=True)
        state.update_reachable_regions(PLAYER)
        unreachable = [cid for cid in ALL_TARGETS if not _hit_rule(mw, cid)(state)]
        self.assertEqual(unreachable, [])


class TestAccessibilityFullSeeds(unittest.TestCase):
    """Fresh accessibility:full seeds reach all sixteen across option shapes."""

    def test_all_sixteen_reachable_per_shape_and_seed(self):
        for shape, options in SHAPES.items():
            for seed in SEEDS:
                with self.subTest(shape=shape, seed=seed):
                    mw = _generate(seed, **options)
                    reached, remaining = _reached_names(mw)
                    missing = [
                        HIT_CHARACTER_CLASS.location_name(cid)
                        for cid in ALL_TARGETS
                        if HIT_CHARACTER_CLASS.location_name(cid) not in reached]
                    self.assertEqual(
                        missing, [],
                        f"{shape}/{seed}: unreachable Hit checks {missing}; "
                        f"unreached locations: {[loc.name for loc in remaining]}")


class TestEligibilityGrowth(unittest.TestCase):
    """Eligibility growth is monotone and never strands an unchecked target."""

    def test_reachability_is_monotone_as_items_arrive(self):
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        rules = {cid: _hit_rule(mw, cid) for cid in ALL_TARGETS}
        state = CollectionState(mw)
        previous = set()
        items = [item for item in mw.itempool if item.player == PLAYER]
        items += list(mw.precollected_items.get(PLAYER, ()))
        for item in items:
            state.collect(world.create_item(item.name), prevent_sweep=True)
            state.update_reachable_regions(PLAYER)
            current = {cid for cid in ALL_TARGETS if rules[cid](state)}
            with self.subTest(after=item.name):
                self.assertTrue(
                    previous <= current,
                    f"lost reachable targets {sorted(previous - current)} "
                    f"after {item.name!r}")
            previous = current
        self.assertEqual(previous, set(ALL_TARGETS))

    def test_unlocking_guests_does_not_displace_default_targets(self):
        """The conservative base subset is independent of guest eligibility."""
        mw = _build(seed=1, hit_character=True)
        world = mw.worlds[PLAYER]
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.player == PLAYER and item.name not in characters.ROSTER_CHARACTER_ID:
                state.collect(world.create_item(item.name), prevent_sweep=True)
        state.update_reachable_regions(PLAYER)
        before = {cid for cid in range(8) if _hit_rule(mw, cid)(state)}
        for racer in characters.ROSTER_CHARACTER_ID:
            state.collect(world.create_item(racer), prevent_sweep=True)
        state.update_reachable_regions(PLAYER)
        after = {cid for cid in range(8) if _hit_rule(mw, cid)(state)}
        self.assertTrue(before <= after)
        self.assertEqual(after, set(range(8)))


class TestUnlockOrder(unittest.TestCase):
    """Early and late alternative unlocks both resolve a self-conflict."""

    def _state(self, mw):
        world = mw.worlds[PLAYER]
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.player == PLAYER and item.name not in characters.ROSTER_CHARACTER_ID:
                state.collect(world.create_item(item.name), prevent_sweep=True)
        state.update_reachable_regions(PLAYER)
        return state

    def test_any_single_alternative_unlock_resolves_the_conflict(self):
        for alternative in ("Coco Bandicoot", "N. Tropy", "Penta Penguin",
                            "Nitros Oxide"):
            with self.subTest(alternative=alternative):
                mw = _build(seed=1, hit_character=True,
                            starting_character="crash_bandicoot")
                world = mw.worlds[PLAYER]
                state = self._state(mw)
                self.assertFalse(_hit_rule(mw, 0)(state))
                state.collect(world.create_item(alternative),
                              prevent_sweep=True)
                state.update_reachable_regions(PLAYER)
                self.assertTrue(_hit_rule(mw, 0)(state))

    def test_late_unlock_does_not_retroactively_strand_the_target(self):
        """Receiving the alternative last still resolves the conflict."""
        mw = _build(seed=1, hit_character=True,
                    starting_character="crash_bandicoot")
        world = mw.worlds[PLAYER]
        state = self._state(mw)
        for racer in ("Polar", "Pura", "Dingodile", "Tiny Tiger", "N. Gin",
                      "Neo Cortex"):
            state.collect(world.create_item(racer), prevent_sweep=True)
            state.update_reachable_regions(PLAYER)
        self.assertTrue(_hit_rule(mw, 0)(state))


class TestAdversarialSeed(unittest.TestCase):
    """A target that cannot appear at all fails generation clearly; a target
    whose unlock win is merely absent now falls back to Keys."""

    def test_disabled_oxide_goal_generates_with_oxide_on_keys(self):
        """`oxide_goal: disabled` used to be an early guard failure. Oxide now
        falls back to 4 Keys and every Hit check stays reachable."""
        mw = _build(seed=1, hit_character=True, oxide_goal="disabled",
                    bosses_required_goal=2, accessibility="full")
        self.assertEqual(mw.worlds[PLAYER].ctr_hit_character_fallback, {15: 4})
        state = mw.get_all_state(False)
        for name in HIT_CHARACTER_CLASS.names():
            self.assertTrue(mw.get_location(name, PLAYER).can_reach(state),
                            name)

    def test_set_rules_structural_error_remains_the_backstop(self):
        """A boss-kind guest has no Key fallback, so removing its only route
        still reaches the set_rules backstop."""
        mw = _build(seed=1, steps=("generate_early", "create_regions",
                                   "create_items"), hit_character=True)
        cache = mw.regions.location_cache[PLAYER]
        cache.pop("Ripper Roo Garage: Boss Race", None)
        with self.assertRaises(OptionError) as ctx:
            call_all(mw, "set_rules")
        self.assertIn("Ripper Roo", str(ctx.exception))

    def test_disabled_trial_modes_generate_with_n_tropy_on_keys(self):
        """The default-settings case: both trial race options off used to be a
        hard guard failure and now puts N. Tropy on 3 Keys."""
        mw = _build(seed=1, hit_character=True, slide_coliseum_races=0,
                    turbo_track_races=0, accessibility="full")
        self.assertEqual(mw.worlds[PLAYER].ctr_hit_character_fallback, {12: 3})
        state = mw.get_all_state(False)
        for name in HIT_CHARACTER_CLASS.names():
            self.assertTrue(mw.get_location(name, PLAYER).can_reach(state),
                            name)


class TestUniversalTrackerParity(unittest.TestCase):
    """UT regeneration restores the emitted block and matches reachability."""

    def _reconstruct(self, wire, seed=2):
        mw = setup_multiworld(ctrAPWorld, steps=(), seed=seed)
        mw.re_gen_passthrough = {ctrAPWorld.game: wire}
        for step in ("generate_early", "create_regions", "create_items",
                     "set_rules"):
            call_all(mw, step)
        return mw

    def _hit_vector(self, mw, items):
        world = mw.worlds[PLAYER]
        state = CollectionState(mw)
        for name in items:
            state.collect(world.create_item(name), prevent_sweep=True)
        state.update_reachable_regions(PLAYER)
        return tuple(_hit_rule(mw, cid)(state) for cid in ALL_TARGETS)

    def test_reconstruction_restores_block_and_matches_reachability(self):
        source = _build(seed=1, hit_character=True)
        original = source.worlds[PLAYER]
        wire = original.fill_slot_data()
        rebuilt_mw = self._reconstruct(wire)
        rebuilt = rebuilt_mw.worlds[PLAYER]

        # Verbatim block and seed, restored rather than re-drawn.
        self.assertEqual(rebuilt.ctr_hit_character_encounters,
                         original.ctr_hit_character_encounters)
        self.assertEqual(
            rebuilt.ctr_hit_character_seed,
            wire["hit_character_encounters"]["policy"]["seed"])

        # No extra roster draw: re-resolving returns the cached block untouched.
        from ..hit_character import resolve_for_generation
        before = rebuilt.random.getstate()
        self.assertIs(resolve_for_generation(rebuilt),
                      rebuilt.ctr_hit_character_encounters)
        self.assertEqual(rebuilt.random.getstate(), before)

        # Reachability parity on identical controlled states.
        for items in ((), ("Key",) * 4, ("Key",) * 4 + ("Trophy",) * 16):
            with self.subTest(items=items):
                self.assertEqual(self._hit_vector(source, items),
                                 self._hit_vector(rebuilt_mw, items))
        self.assertEqual(
            tuple(_hit_rule(source, cid)(source.get_all_state(False))
                  for cid in ALL_TARGETS),
            tuple(_hit_rule(rebuilt_mw, cid)(rebuilt_mw.get_all_state(False))
                  for cid in ALL_TARGETS))

    def test_reconstruction_restores_a_fallback_guest_from_the_wire(self):
        """A UT regeneration has no option values or displacement draws to
        re-derive the fallback from, so it must read it back out of the block
        and install the same Key rule the generated seed installed."""
        source = _build(seed=1, hit_character=True, slide_coliseum_races=0,
                        turbo_track_races=0, oxide_goal="disabled",
                        bosses_required_goal=2)
        original = source.worlds[PLAYER]
        self.assertEqual(original.ctr_hit_character_fallback, {12: 3, 15: 4})
        wire = original.fill_slot_data()
        rebuilt_mw = self._reconstruct(wire)
        rebuilt = rebuilt_mw.worlds[PLAYER]
        self.assertTrue(rebuilt.ctr_hit_character_restored)
        self.assertEqual(rebuilt.ctr_hit_character_fallback, {12: 3, 15: 4})
        self.assertEqual(rebuilt.ctr_hit_character_encounters,
                         original.ctr_hit_character_encounters)
        for items in ((), ("Key",) * 3, ("Key",) * 4,
                      ("Key",) * 4 + ("Trophy",) * 16):
            with self.subTest(items=items):
                self.assertEqual(self._hit_vector(source, items),
                                 self._hit_vector(rebuilt_mw, items))

    def test_reconstruction_matches_across_option_shapes(self):
        for shape, options in SHAPES.items():
            with self.subTest(shape=shape):
                source = _build(seed=1, hit_character=True, **options)
                wire = source.worlds[PLAYER].fill_slot_data()
                rebuilt_mw = self._reconstruct(wire)
                self.assertEqual(
                    self._hit_vector(source, ("Key",) * 4),
                    self._hit_vector(rebuilt_mw, ("Key",) * 4))


if __name__ == "__main__":
    unittest.main()
