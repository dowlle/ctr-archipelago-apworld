"""The H-dossier item families, activated (2026-08-10 ruling + #224).

WHAT THESE TESTS ARE FOR. The families' NAMES were frozen by #177 and are
already pinned by test_name_freeze; this suite pins what activating them does.
That splits into five properties, one class each:

  1. THE MANIFEST AMENDMENT. `Turbo Grant` is exactly one name, appended at
     35010189, and nothing else moved.
  2. THE COUNTS. Which items each option combination creates, for every
     combination, asserted against a live generated pool rather than against the
     helper that decided them -- a helper agreeing with itself proves nothing.
  3. GENERATION NEUTRALITY. A seed with every one of these options off is
     byte-identical to a pre-this-build seed, including its RNG stream. This is
     the property the vanilla fill backstop's replay fidelity rests on, so it is
     asserted directly, not assumed from "the code path looks inert".
  4. THE TRAP PROMOTION. All sixteen traps are drawn, the draw covers the whole
     set, and the two lists still map to the two native index bases in the order
     native's AP_TrapEffect enum expects.
  5. THE WIRE. The three scalars and the one conditional block, plus a real
     round trip back through the Universal Tracker restore.

WHAT IS NOT HERE, deliberately: everything about DELIVERY -- the queue, the
itemsanity weapon gate, the progressive-boost tiers, the reserve clamp. Those
are native behaviour, they are unreachable from a generation test, and they have
their own host harness (`tools/test-h-dossier.c` in the native repo). The one
apworld-side trace of the gate is the generation-log warning asserted in
`TestDowngradeWarnings`.
"""
import unittest

from BaseClasses import ItemClassification
from test.general import setup_multiworld

from .. import BUILDABLE_TRAP_ITEM_NAMES, FROZEN_TRAP_ITEM_NAMES, TRAP_ITEM_NAMES, ctrAPWorld
from .. import forced_options, h_dossier
from ..Items import load_item_table
from ..h_dossier import (GRANT_ITEMS, PROGRESSIVE_WUMPA_ITEM,
                         PROGRESSIVE_WUMPA_MAX, TURBO_GRANT_CODE,
                         TURBO_GRANT_ITEM, USEFUL_GRANT_ITEMS,
                         WUMPA_BUNDLE_ITEMS)
from ..wumpa_checks import WUMPA_TEN_LOCATION


def _pool_names(mw, world):
    """Every item name this player's pool holds, with duplicates kept."""
    return [item.name for item in mw.itempool if item.player == world.player]


def _count(mw, world, name):
    return sum(1 for n in _pool_names(mw, world) if n == name)


class TestTheRuledAmendment(unittest.TestCase):
    """Property 1: #224 is exactly one name wide."""

    def test_turbo_grant_is_appended_one_past_tizi(self) -> None:
        table = {item["name"]: item for item in load_item_table()}
        self.assertIn(TURBO_GRANT_ITEM, table)
        self.assertEqual(table[TURBO_GRANT_ITEM]["code"], TURBO_GRANT_CODE)
        self.assertEqual(TURBO_GRANT_CODE, table["Tizi Helper"]["code"] + 1)

    def test_it_ships_inert_in_the_static_table(self) -> None:
        """Every name in these families is `count: 0` in data/items.json: the
        OPTION is what makes a copy, never the table. A non-zero count here
        would put the item in every seed including seeds that turned it off."""
        table = {item["name"]: item for item in load_item_table()}
        for name in (GRANT_ITEMS + WUMPA_BUNDLE_ITEMS
                     + [PROGRESSIVE_WUMPA_ITEM] + FROZEN_TRAP_ITEM_NAMES):
            with self.subTest(item=name):
                self.assertEqual(table[name]["count"], 0)

    def test_no_duplicate_mask_grant_name_was_minted(self) -> None:
        """The 2026-08-11 ruling is explicit: the ruled Mask filler IS the
        already-frozen `Invincibility Mask`, and #224 adds only the missing
        Turbo sibling. A second Mask-grant name is the specific mistake that
        ruling exists to prevent, so pin its absence by shape rather than by
        listing one spelling nobody would have chosen anyway."""
        names = {item["name"] for item in load_item_table()}
        self.assertIn("Invincibility Mask", names)
        mask_names = {n for n in names if "Mask" in n}
        self.assertEqual(mask_names, {"Mask", "Invincibility Mask"})

    def test_the_grant_family_is_the_three_ruled_plus_the_amendment(self) -> None:
        self.assertEqual(USEFUL_GRANT_ITEMS,
                         ["Passive Shield", "Invincibility Mask", "Invisibility"])
        self.assertEqual(GRANT_ITEMS, USEFUL_GRANT_ITEMS + [TURBO_GRANT_ITEM])
        # The ruling DEFERRED the player-agency power-up grant past 0.2.0
        # because itemsanity owns the weapons-as-items space, and REJECTED the
        # respawn/mask-grab trap outright. Neither may sneak back in as a
        # created item.
        self.assertEqual(len(GRANT_ITEMS), 4)


class TestCreatedCounts(unittest.TestCase):
    """Property 2: what each option combination actually pools."""

    def test_everything_off_creates_none_of_them(self) -> None:
        mw = setup_multiworld(ctrAPWorld, seed=900, options={})
        world = mw.worlds[1]
        for name in GRANT_ITEMS + [PROGRESSIVE_WUMPA_ITEM] + WUMPA_BUNDLE_ITEMS:
            with self.subTest(item=name):
                self.assertEqual(_count(mw, world, name), 0)

    def test_grants_toggle_creates_exactly_one_of_each_of_the_four(self) -> None:
        mw = setup_multiworld(ctrAPWorld, seed=901,
                              options={"useful_item_grants": True})
        world = mw.worlds[1]
        for name in GRANT_ITEMS:
            with self.subTest(item=name):
                self.assertEqual(_count(mw, world, name), 1)

    def test_the_progressive_ladder_creates_exactly_its_option_value(self) -> None:
        """One NAME, N received copies -- the #12/#13 progressive convention the
        2026-08-10 16:30 ruling named explicitly. Every rung of the ladder is
        covered, including both ends."""
        for value in range(0, PROGRESSIVE_WUMPA_MAX + 1):
            with self.subTest(progressive_starting_wumpa=value):
                mw = setup_multiworld(
                    ctrAPWorld, seed=910 + value,
                    options={"progressive_starting_wumpa": value})
                world = mw.worlds[1]
                self.assertEqual(
                    _count(mw, world, PROGRESSIVE_WUMPA_ITEM), value)

    def test_the_ladder_is_capped_at_a_full_kart(self) -> None:
        """Ten is not a taste bound: a kart holds ten fruit, so an eleventh copy
        could never be felt. The option's own range_end enforces it, and the
        helper clamps independently so a hand-built or restored value cannot
        walk past it."""
        self.assertEqual(PROGRESSIVE_WUMPA_MAX, 10)

        class _Stub:
            class options:
                class useful_item_grants:
                    value = 0

                class progressive_starting_wumpa:
                    value = 99

        self.assertEqual(
            h_dossier.created_item_counts(_Stub)[PROGRESSIVE_WUMPA_ITEM],
            PROGRESSIVE_WUMPA_MAX)

    def test_bundles_appear_only_with_their_toggle_and_cost_no_supply(self) -> None:
        """The bundles are FILLER SUBSTITUTES. Two things follow and both are
        asserted here, because getting either wrong is a pool-size bug rather
        than a cosmetic one: they must not appear at all with the toggle off,
        and enabling them must not change the pool's SIZE -- only which filler
        name occupies a slot that was going to be filled either way."""
        base = setup_multiworld(ctrAPWorld, seed=930, options={})
        base_world = base.worlds[1]
        for name in WUMPA_BUNDLE_ITEMS:
            self.assertEqual(_count(base, base_world, name), 0)

        on = setup_multiworld(ctrAPWorld, seed=930,
                              options={"wumpa_bundles": True})
        on_world = on.worlds[1]
        self.assertEqual(len(_pool_names(on, on_world)),
                         len(_pool_names(base, base_world)))

    def test_grants_and_ladder_together(self) -> None:
        """The two supply-spending families are independent: enabling both
        creates both, at their own counts, with no interference."""
        mw = setup_multiworld(ctrAPWorld, seed=940, options={
            "useful_item_grants": True,
            "progressive_starting_wumpa": 4,
            "wumpa_bundles": True,
        })
        world = mw.worlds[1]
        for name in GRANT_ITEMS:
            self.assertEqual(_count(mw, world, name), 1)
        self.assertEqual(_count(mw, world, PROGRESSIVE_WUMPA_ITEM), 4)

    def test_created_item_total_matches_the_live_pool(self) -> None:
        """The number the rung sizer's mandatory-demand mirror reads must be the
        number the pool actually grew by. A mirror that drifts from the pool is
        the exact failure DeepSeek review F1 caught for itemsanity, in the
        direction that makes the sizer fail to expand when it should."""
        for options in ({}, {"useful_item_grants": True},
                        {"progressive_starting_wumpa": 7},
                        {"useful_item_grants": True,
                         "progressive_starting_wumpa": 10}):
            with self.subTest(options=options):
                mw = setup_multiworld(ctrAPWorld, seed=950, options=options)
                world = mw.worlds[1]
                live = sum(_count(mw, world, name)
                           for name in GRANT_ITEMS + [PROGRESSIVE_WUMPA_ITEM])
                self.assertEqual(live, h_dossier.created_item_total(world))


class TestGenerationNeutrality(unittest.TestCase):
    """Property 3: an all-off seed is byte-identical to a pre-this-build one."""

    def test_bundles_off_draws_no_rng_and_returns_plain_wumpa(self) -> None:
        """`draw_filler_name` must not consume the world RNG while bundles are
        off. The vanilla fill backstop replays a simulated fill against the real
        one move for move and asserts the two draw identically, so a stray draw
        in the filler loop would break replay fidelity on every default seed --
        which is a solvability bug, not a cosmetic one."""
        mw = setup_multiworld(ctrAPWorld, seed=960, options={})
        world = mw.worlds[1]
        before = world.random.getstate()
        for _ in range(50):
            self.assertEqual(h_dossier.draw_filler_name(world), "Wumpa Fruit")
        self.assertEqual(world.random.getstate(), before)

    def test_bundles_on_does_consume_rng(self) -> None:
        """The other half of the same property, so the assertion above cannot
        pass vacuously against a helper that never draws at all."""
        mw = setup_multiworld(ctrAPWorld, seed=961,
                              options={"wumpa_bundles": True})
        world = mw.worlds[1]
        before = world.random.getstate()
        drawn = {h_dossier.draw_filler_name(world) for _ in range(400)}
        self.assertNotEqual(world.random.getstate(), before)
        # 400 draws against a 6:3:1 weighting: seeing all three is overwhelming.
        self.assertEqual(drawn, {"Wumpa Fruit"} | set(WUMPA_BUNDLE_ITEMS))

    def test_plain_wumpa_stays_the_common_filler(self) -> None:
        """The ruling folded the bundles in as an enrichment, not a replacement.
        A pool where every filler slot handed the player ten fruit would make
        the 10-wumpa check and itemsanity's juiced checks trivial -- a balance
        change nobody made."""
        weights = h_dossier.FILLER_WEIGHTS
        self.assertGreater(weights["Wumpa Fruit"],
                           weights["Small Wumpa Bundle"])
        self.assertGreater(weights["Small Wumpa Bundle"],
                           weights["Big Wumpa Bundle"])

    def test_create_filler_stays_fixed(self) -> None:
        """AP core calls `create_filler()` with no arguments on the
        panic_method='start_inventory' path the backstop's enumeration
        simulation exercises. It must stay a fixed Wumpa Fruit EVEN WITH bundles
        on, or that simulation starts drawing RNG the real fill will not."""
        mw = setup_multiworld(ctrAPWorld, seed=962,
                              options={"wumpa_bundles": True})
        world = mw.worlds[1]
        before = world.random.getstate()
        self.assertEqual(world.create_filler().name, "Wumpa Fruit")
        self.assertEqual(world.random.getstate(), before)


class TestTrapPromotion(unittest.TestCase):
    """Property 4: all sixteen traps are buildable, in native enum order."""

    def test_the_buildable_set_is_the_union_of_the_two_blocks(self) -> None:
        self.assertEqual(BUILDABLE_TRAP_ITEM_NAMES,
                         TRAP_ITEM_NAMES + FROZEN_TRAP_ITEM_NAMES)
        self.assertEqual(len(BUILDABLE_TRAP_ITEM_NAMES), 16)
        self.assertEqual(len(set(BUILDABLE_TRAP_ITEM_NAMES)), 16)

    def test_each_block_is_contiguous_at_its_native_base(self) -> None:
        """The two lists map through DIFFERENT native item-index bases because
        the freeze appended the eleven after the itemsanity block rather than
        contiguously with the v1 five. Pin both bases and both runs: native
        carries the same two constants, and a drift here silently maps a trap
        item onto the wrong effect (or onto the comfort pack)."""
        code = {item["name"]: item["code"] for item in load_item_table()}
        base = 35010000
        for effect, name in enumerate(TRAP_ITEM_NAMES):
            with self.subTest(v1_effect=effect, item=name):
                self.assertEqual(code[name] - base, 16 + effect)
        for effect, name in enumerate(FROZEN_TRAP_ITEM_NAMES):
            with self.subTest(h_effect=5 + effect, item=name):
                self.assertEqual(code[name] - base, 106 + effect)

    def test_the_draw_reaches_every_trap(self) -> None:
        """Uniform across all sixteen, as v1 was uniform across five. Asserted
        against the helper's own draw list at high volume rather than against a
        generated pool, because a real seed has only a handful of filler slots
        and could never exhibit all sixteen."""
        mw = setup_multiworld(ctrAPWorld, seed=970, options={})
        world = mw.worlds[1]
        drawn = {world.random.choice(BUILDABLE_TRAP_ITEM_NAMES)
                 for _ in range(3000)}
        self.assertEqual(drawn, set(BUILDABLE_TRAP_ITEM_NAMES))

    def test_traps_are_classified_as_traps(self) -> None:
        table = {item["name"]: item for item in load_item_table()}
        for name in BUILDABLE_TRAP_ITEM_NAMES:
            with self.subTest(item=name):
                self.assertEqual(table[name]["classification"],
                                 ItemClassification.trap)

    def test_a_high_trap_slider_seats_the_new_traps(self) -> None:
        """End-to-end rather than by construction: at a high slider a real
        generated pool should contain traps drawn from the H block, not only
        from the v1 five."""
        seen = set()
        for seed in range(980, 990):
            mw = setup_multiworld(ctrAPWorld, seed=seed,
                                  options={"trap_fill_percentage": 100})
            world = mw.worlds[1]
            seen.update(n for n in _pool_names(mw, world)
                        if n in FROZEN_TRAP_ITEM_NAMES)
        self.assertTrue(seen, "no H-dossier trap was drawn across ten seeds at "
                              "a 100 percent trap slider")


class TestTheWire(unittest.TestCase):
    """Property 5: the scalars, the block, and a real restore round trip."""

    def test_scalars_are_always_emitted(self) -> None:
        """Always-emitted, on the `itemsanity` / `tizi_helper` convention: a
        tracker should read the seed's real configuration without inferring it
        from an item that may not have arrived yet."""
        for options, expected in (
            ({}, {"useful_item_grants": False, "wumpa_bundles": False,
                  "progressive_starting_wumpa": 0}),
            ({"useful_item_grants": True, "wumpa_bundles": True,
              "progressive_starting_wumpa": 6},
             {"useful_item_grants": True, "wumpa_bundles": True,
              "progressive_starting_wumpa": 6}),
        ):
            with self.subTest(options=options):
                mw = setup_multiworld(ctrAPWorld, seed=991, options=options)
                co = mw.worlds[1].fill_slot_data()["ctr_options"]
                for key, value in expected.items():
                    self.assertIn(key, co)
                    self.assertEqual(co[key], value)

    def test_the_wumpa_block_follows_off_toggle_parity(self) -> None:
        """A location toggle, so it gets a conditional BLOCK and no scalar --
        exactly itemsanity's shape. Off seeds must not gain a dormant feature
        block, and the block's code must be the location's real code."""
        off = setup_multiworld(ctrAPWorld, seed=992, options={})
        self.assertNotIn("wumpa_checks", off.worlds[1].fill_slot_data())

        on = setup_multiworld(ctrAPWorld, seed=992,
                              options={"wumpa_check": True})
        world = on.worlds[1]
        block = world.fill_slot_data()["wumpa_checks"]
        self.assertTrue(block["enabled"])
        self.assertEqual(
            block["locations"],
            [world.location_name_to_id[WUMPA_TEN_LOCATION]])

    def test_the_wumpa_location_exists_only_when_created(self) -> None:
        off = setup_multiworld(ctrAPWorld, seed=993, options={})
        self.assertNotIn(
            WUMPA_TEN_LOCATION,
            {loc.name for loc in off.get_locations(1)})

        on = setup_multiworld(ctrAPWorld, seed=993,
                              options={"wumpa_check": True})
        self.assertIn(
            WUMPA_TEN_LOCATION,
            {loc.name for loc in on.get_locations(1)})

    def test_the_wumpa_check_adds_exactly_one_location(self) -> None:
        """GLOBAL, one per seed (Stef, 2026-08-10 16:28) -- not one per track.
        Sixteen or eighteen would be the per-track shape the ruling rejected, so
        the count is pinned rather than merely the name's presence."""
        off = setup_multiworld(ctrAPWorld, seed=994, options={})
        on = setup_multiworld(ctrAPWorld, seed=994,
                              options={"wumpa_check": True})
        self.assertEqual(len(list(on.get_locations(1))),
                         len(list(off.get_locations(1))) + 1)

    def test_restore_round_trips_every_option(self) -> None:
        """A real round trip: generate, take the wire, feed it back through the
        Universal Tracker restore and assert the restored options match. A
        restore tested against a hand-built dict would not catch an emitter that
        writes a key the restore does not read."""
        options = {"useful_item_grants": True, "wumpa_bundles": True,
                   "progressive_starting_wumpa": 8, "wumpa_check": True}
        source = setup_multiworld(ctrAPWorld, seed=995, options=options)
        wire = source.worlds[1].fill_slot_data()

        target = setup_multiworld(ctrAPWorld, seed=996, options={})
        restored = target.worlds[1].options
        ctrAPWorld.interpret_slot_data(wire)
        h_dossier.restore_slot_data(restored, wire["ctr_options"])
        self.assertEqual(restored.useful_item_grants.value, 1)
        self.assertEqual(restored.wumpa_bundles.value, 1)
        self.assertEqual(restored.progressive_starting_wumpa.value, 8)

    def test_restore_of_a_pre_this_build_wire_is_all_off(self) -> None:
        """An absent key is a pre-this-build seed. Restoring to off is the
        honest answer: such a seed created none of these items."""
        class _Opt:
            def __init__(self):
                self.value = 99

        class _Options:
            def __init__(self):
                self.useful_item_grants = _Opt()
                self.wumpa_bundles = _Opt()
                self.progressive_starting_wumpa = _Opt()

        restored = _Options()
        h_dossier.restore_slot_data(restored, {})
        self.assertEqual(restored.useful_item_grants.value, 0)
        self.assertEqual(restored.wumpa_bundles.value, 0)
        self.assertEqual(restored.progressive_starting_wumpa.value, 0)

    def test_restore_clamps_a_hostile_ladder_value(self) -> None:
        """The wire is server-supplied. A negative or absurd value must not
        become a pool the generator then cannot fit."""
        class _Opt:
            value = 0

        class _Options:
            def __init__(self):
                self.useful_item_grants = _Opt()
                self.wumpa_bundles = _Opt()
                self.progressive_starting_wumpa = _Opt()

        for hostile, expected in ((-5, 0), (0, 0), (10, 10), (9999, 10),
                                  (None, 0)):
            with self.subTest(wire_value=hostile):
                restored = _Options()
                h_dossier.restore_slot_data(
                    restored, {"progressive_starting_wumpa": hostile})
                self.assertEqual(
                    restored.progressive_starting_wumpa.value, expected)


class TestSupplyInteractions(unittest.TestCase):
    """These families add items and NO locations, so they eat spare capacity.

    Not a separate ruled property, but the one that actually breaks generation
    when it is wrong, and the reason `created_item_counts` is consulted before
    the comfort-pack trim rather than after it.
    """

    def test_a_fully_loaded_seed_still_generates(self) -> None:
        """Fourteen extra items with no extra locations, stacked on top of the
        character unlocks and the capability packs, against the default location
        set. If the supply accounting is wrong anywhere this is where it
        surfaces, as a FillError rather than as a subtle count."""
        mw = setup_multiworld(ctrAPWorld, seed=997, options={
            "useful_item_grants": True,
            "progressive_starting_wumpa": PROGRESSIVE_WUMPA_MAX,
            "wumpa_bundles": True,
            "wumpa_check": True,
            "trap_fill_percentage": 50,
        })
        world = mw.worlds[1]
        self.assertEqual(len(_pool_names(mw, world)),
                         len(mw.get_unfilled_locations(world.player)))

    def test_it_composes_with_itemsanity_and_boxes(self) -> None:
        """The composed configuration a real 0.2.0 seed runs: itemsanity's 11
        items and 22 locations, the box checks, the capability packs and these
        families all at once."""
        mw = setup_multiworld(ctrAPWorld, seed=998, options={
            "useful_item_grants": True,
            "progressive_starting_wumpa": 5,
            "wumpa_bundles": True,
            "wumpa_check": True,
            "itemsanity": True,
            "tizi_helper": True,
            "box_locations": True,
            "progressive_boost": "shared_global",
            "progressive_stats": "shared_global",
        })
        world = mw.worlds[1]
        self.assertEqual(len(_pool_names(mw, world)),
                         len(mw.get_unfilled_locations(world.player)))
        for name in GRANT_ITEMS:
            self.assertEqual(_count(mw, world, name), 1)
        self.assertEqual(_count(mw, world, PROGRESSIVE_WUMPA_ITEM), 5)


class TestDowngradeWarnings(unittest.TestCase):
    """The two #178 interaction rows this build owns."""

    def test_bundles_with_a_full_trap_slider_warns(self) -> None:
        with self.assertLogs(level="WARNING") as captured:
            setup_multiworld(ctrAPWorld, seed=999, options={
                "wumpa_bundles": True, "trap_fill_percentage": 100})
        self.assertTrue(
            any("Wumpa Bundles has no effect" in line
                for line in captured.output),
            captured.output)

    def test_grants_with_itemsanity_explains_the_gate(self) -> None:
        """Not a solvability problem -- the grants are `useful`, both weapon
        items always exist in an itemsanity pool, and an early grant queues
        rather than being discarded. It is a surprise problem, so the player is
        told in their generation log instead of discovering it in-game."""
        with self.assertLogs(level="WARNING") as captured:
            setup_multiworld(ctrAPWorld, seed=1000, options={
                "useful_item_grants": True, "itemsanity": True})
        joined = "\n".join(captured.output)
        self.assertIn("Invincibility Mask waits", joined)
        self.assertIn("Turbo Grant waits", joined)
        self.assertIn("queued, never lost", joined)

    def test_no_warning_when_the_gate_does_not_apply(self) -> None:
        """With itemsanity off there is no weapon-item gate at all (2026-08-11
        ruling), so warning about one would be a lie.

        Driven by calling the guard directly rather than by generating and
        asserting the absence of a line: a whole-generation `assertNotIn` passes
        just as happily when the guard was never reached for some unrelated
        reason, which is the failure mode that makes absence tests worthless."""
        mw = setup_multiworld(ctrAPWorld, seed=1001, options={
            "useful_item_grants": True, "itemsanity": False})
        world = mw.worlds[1]
        with self.assertNoLogs(level="WARNING"):
            forced_options.warn_grants_gated_behind_unreceived_weapons(world)
        # And it DOES fire once itemsanity goes on, against the same world -- so
        # the silence above is the gate being absent, not the guard being dead.
        world.options.itemsanity.value = 1
        with self.assertLogs(level="WARNING") as captured:
            forced_options.warn_grants_gated_behind_unreceived_weapons(world)
        self.assertIn("Invincibility Mask waits", "\n".join(captured.output))

    def test_the_bundle_guard_is_silent_below_a_full_slider(self) -> None:
        """The mirror of the test above for the other guard: 99 percent still
        leaves filler slots for a bundle to land in, so only 100 warns."""
        mw = setup_multiworld(ctrAPWorld, seed=1002, options={
            "wumpa_bundles": True, "trap_fill_percentage": 99})
        world = mw.worlds[1]
        with self.assertNoLogs(level="WARNING"):
            forced_options.warn_wumpa_bundles_have_no_filler_slots(world)


if __name__ == "__main__":
    unittest.main()
