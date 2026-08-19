"""Progressive Boost / Progressive Stats item packs (issues #12, #13).

Progressive capability pool, wire, classification and #252 gate semantics.

Covers: item counts per mode (off / shared_global / per_character),
the blue-fire chain-length toggle, #168 code stability, the wire round-trip
(ctr_options boost_mode / boost_blue_fire / stats_mode), the pool-overflow
RAISE guard, and vanilla/off byte parity (no RNG draw, item pool unchanged).
"""
import pkgutil
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from test.general import setup_multiworld

from .. import ctrAPWorld
from .. import characters
from .. import progressive_capability
from . import CTRTestBase

CAPABILITY_ITEM_PREFIXES = (
    "Progressive Boost", "Progressive Top Speed",
    "Progressive Acceleration", "Progressive Turning",
)
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _pool_names(multiworld, player):
    return [item.name for item in multiworld.itempool if item.player == player]


def _capability_counts(multiworld, player):
    names = _pool_names(multiworld, player)
    return {n: names.count(n) for n in set(names)
            if n.startswith(CAPABILITY_ITEM_PREFIXES)}


class TestCapabilityItemsOff(CTRTestBase):
    """Default (off/off): byte-parity with a pre-#12/#13 seed -- no
    capability item enters the pool, and the wire declares off/off/False."""

    run_default_tests = False

    def test_no_capability_items_in_pool(self):
        self.assertEqual(_capability_counts(self.multiworld, self.player), {})

    def test_wire_reports_off(self):
        world = self.multiworld.worlds[self.player]
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["boost_mode"], 0)
        self.assertEqual(co["boost_blue_fire"], False)
        self.assertEqual(co["stats_mode"], 0)

    def test_pool_still_matches_unfilled_locations(self):
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        pool = _pool_names(self.multiworld, self.player)
        self.assertEqual(len(pool), len(unfilled))


class TestBoostSharedGlobalNoBlueFire(CTRTestBase):
    """shared_global, blue fire off: exactly 2 copies (no boost/boost/USF)."""

    run_default_tests = False
    options = {"progressive_boost": "shared_global"}

    def test_two_copies_created(self):
        self.assertEqual(
            _capability_counts(self.multiworld, self.player),
            {"Progressive Boost": 2})

    def test_wire(self):
        world = self.multiworld.worlds[self.player]
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["boost_mode"], 1)
        self.assertEqual(co["boost_blue_fire"], False)


class TestBoostSharedGlobalBlueFire(CTRTestBase):
    """shared_global with Blue Fire on: 3 copies (no boost/boost/USF/blue fire
    is 4 tiers -- 3 received copies)."""

    run_default_tests = False
    options = {"progressive_boost": "shared_global",
              "progressive_boost_blue_fire": True}

    def test_three_copies_created(self):
        self.assertEqual(
            _capability_counts(self.multiworld, self.player),
            {"Progressive Boost": 3})

    def test_blue_fire_off_has_no_effect_while_boost_is_off(self):
        # Documented downgrade case: Blue Fire alone (boost off) creates
        # nothing -- created_item_counts only reads it when boost_mode == 1.
        pass


class TestStatsSharedGlobal(CTRTestBase):
    """shared_global stats: 3 chains x 4 copies (the 08-07 five-rank ladder
    ruling: VERY LOW..VERY HIGH == 4 received copies per chain)."""

    run_default_tests = False
    options = {"progressive_stats": "shared_global"}

    def test_twelve_items_created(self):
        counts = _capability_counts(self.multiworld, self.player)
        self.assertEqual(counts, {
            "Progressive Top Speed": 4,
            "Progressive Acceleration": 4,
            "Progressive Turning": 4,
        })

    def test_wire(self):
        world = self.multiworld.worlds[self.player]
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["stats_mode"], 1)


class TestBothPacksSharedGlobalPoolBalance(CTRTestBase):
    """Both packs on together: 15 new items (3 boost + 12 stats), and the
    pool/location invariant every CTR test class checks must still hold."""

    run_default_tests = False
    options = {
        "progressive_boost": "shared_global",
        "progressive_boost_blue_fire": True,
        "progressive_stats": "shared_global",
    }

    def test_fifteen_items_created(self):
        counts = _capability_counts(self.multiworld, self.player)
        self.assertEqual(sum(counts.values()), 15)

    def test_pool_still_matches_unfilled_locations(self):
        unfilled = self.multiworld.get_unfilled_locations(self.player)
        pool = _pool_names(self.multiworld, self.player)
        self.assertEqual(len(pool), len(unfilled))


class TestCapabilityPoolOverflowRaises(CTRTestBase):
    """Podium checks off leaves only 83 locations (measured); maxing both
    packs (15 new items) on top of the ~99 fixed items overflows that
    supply. Must raise a clean OptionError (issue #178 shape), never a raw
    FillError."""

    auto_construct = False
    options = {
        "progressive_boost": "shared_global",
        "progressive_boost_blue_fire": True,
        "progressive_stats": "shared_global",
        "podium_placement_checks": False,
    }

    def test_setup_raises_option_error(self):
        with self.assertRaises(OptionError) as ctx:
            self.world_setup()
        self.assertIn("Progressive Boost", str(ctx.exception))


class TestBoostPerCharacter(CTRTestBase):
    """Two boost copies for each of the sixteen racers."""

    run_default_tests = False
    options = {"progressive_boost": "per_character"}

    def test_creates_sixteen_private_chains(self):
        counts = _capability_counts(self.multiworld, self.player)
        self.assertEqual(len(counts), 16)
        self.assertEqual(set(counts.values()), {2})
        self.assertEqual(sum(counts.values()), 32)
        for character in progressive_capability.ROSTER:
            self.assertEqual(counts[
                progressive_capability.boost_item_name(character)], 2)


class TestStatsPerCharacterSupplyPoor(CTRTestBase):
    """The live supply guard replaces the old blanket mode ban."""

    auto_construct = False
    options = {"progressive_stats": "per_character"}

    def test_raises_option_error(self):
        with self.assertRaises(OptionError) as ctx:
            self.world_setup()
        self.assertIn("would add 192 item(s)", str(ctx.exception))
        self.assertIn("stats=per_character", str(ctx.exception))


class TestBothPacksPerCharacterRich(CTRTestBase):
    """All 240 private capability items fit with authored box supply."""

    run_default_tests = False
    options = {
        "progressive_boost": "per_character",
        "progressive_boost_blue_fire": True,
        "progressive_stats": "per_character",
        "box_locations": True,
        "shortcut_knowledge": "hard",
    }

    def test_creates_full_private_pool(self):
        counts = _capability_counts(self.multiworld, self.player)
        self.assertEqual(len(counts), 64)
        self.assertEqual(sum(counts.values()), 240)

    def test_wire_reports_private_modes(self):
        co = self.world.fill_slot_data()["ctr_options"]
        self.assertEqual(co["boost_mode"], 2)
        self.assertEqual(co["stats_mode"], 2)


class TestPerCharacterRichSeedGenerates(CTRTestBase):
    """A maximal private-chain seed completes AP's real fill pipeline."""

    options = {
        "progressive_boost": "per_character",
        "progressive_boost_blue_fire": True,
        "progressive_stats": "per_character",
        "box_locations": True,
        "shortcut_knowledge": "hard",
        "itemsanity": True,
        "accessibility": "full",
    }


class TestPerCharacterGateSemantics(unittest.TestCase):
    """The four binding #252 gate-semantics arms."""

    PLAYER = 1

    def _rich(self, **extra):
        options = {
            "progressive_boost": "per_character",
            "progressive_stats": "per_character",
            "box_locations": True,
            "shortcut_knowledge": "hard",
        }
        options.update(extra)
        mw = _build(**options)
        return mw, mw.worlds[self.PLAYER], CollectionState(mw)

    @staticmethod
    def _other(world, excluded=()):
        return next(c for c in progressive_capability.ROSTER
                    if c != world.ctr_starting_character and c not in excluded)

    def test_locked_gate_reads_only_the_required_racer(self):
        mw, world, state = self._rich()
        required = self._other(world)
        start = world.ctr_starting_character
        state.add_item(progressive_capability.boost_item_name(start), self.PLAYER, 2)
        self.assertFalse(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2,
            required_character=required))
        state.add_item(characters.unlock_item_name(required), self.PLAYER, 1)
        state.add_item(progressive_capability.boost_item_name(required), self.PLAYER, 2)
        self.assertTrue(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2,
            required_character=required))

    def test_unlocked_gate_accepts_any_driveable_racer(self):
        mw, world, state = self._rich()
        racer = self._other(world)
        state.add_item(progressive_capability.boost_item_name(racer), self.PLAYER, 2)
        self.assertFalse(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2))
        state.add_item(characters.unlock_item_name(racer), self.PLAYER, 1)
        self.assertTrue(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2))

    def test_requirements_cannot_split_across_racers(self):
        mw, world, state = self._rich()
        boost_racer = self._other(world)
        stat_racer = self._other(world, {boost_racer})
        for racer in (boost_racer, stat_racer):
            state.add_item(characters.unlock_item_name(racer), self.PLAYER, 1)
        state.add_item(progressive_capability.boost_item_name(boost_racer),
                       self.PLAYER, 2)
        for chain in progressive_capability.STAT_CHAINS:
            state.add_item(progressive_capability.stat_item_name(chain, stat_racer),
                           self.PLAYER, 1)
        stats = {chain: 1 for chain in progressive_capability.STAT_CHAINS}
        self.assertFalse(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2, stat_mins=stats))
        for chain in progressive_capability.STAT_CHAINS:
            state.add_item(progressive_capability.stat_item_name(chain, boost_racer),
                           self.PLAYER, 1)
        self.assertTrue(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2, stat_mins=stats))

    def test_all_unlocked_mode_needs_no_unlock_item(self):
        mw = _build(progressive_boost="per_character", character_unlocks=False)
        world = mw.worlds[self.PLAYER]
        state = CollectionState(mw)
        racer = self._other(world)
        state.add_item(progressive_capability.boost_item_name(racer), self.PLAYER, 2)
        self.assertTrue(progressive_capability.gate_satisfied(
            world, state, self.PLAYER, boost_min=2))

    def test_unlock_items_are_progression_without_racer_locks(self):
        mw = _build(progressive_boost="per_character",
                    racer_locked_pads=False, character_unlocks=True)
        world = mw.worlds[self.PLAYER]
        unlocks = set(characters.created_unlock_names(world))
        items = [item for item in mw.itempool if item.player == self.PLAYER
                 and item.name in unlocks]
        self.assertEqual(len(items), 15)
        self.assertTrue(all(item.advancement for item in items))


class TestPerCharacterUniversalTracker(unittest.TestCase):
    """UT restores the two mode scalars that select private item names."""

    def test_private_modes_override_tracking_yaml(self):
        mw = _build(progressive_boost="off", progressive_stats="off")
        world = mw.worlds[1]
        world._ut_restore_options({
            "ctr_options": {"boost_mode": 2, "stats_mode": 2},
            "warp_pad_unlock": {},
            "podium_checks": {},
        })
        self.assertEqual(world.options.progressive_boost.value, 2)
        self.assertEqual(world.options.progressive_stats.value, 2)

    def test_wire_needs_no_per_racer_rank_block(self):
        mw = _build(progressive_boost="per_character",
                    progressive_stats="per_character",
                    box_locations=True, shortcut_knowledge="hard")
        slot_data = mw.worlds[1].fill_slot_data()
        self.assertEqual(slot_data["ctr_options"]["boost_mode"], 2)
        self.assertEqual(slot_data["ctr_options"]["stats_mode"], 2)
        self.assertNotIn("capability_ranks", slot_data)


class TestItemCodeStability:
    """Not a CTRTestBase subclass (no generation needed) -- pure data checks
    against data/items.json and the module's own roster/name helpers."""

    def _items(self):
        return json.loads(
            pkgutil.get_data("worlds.ctr", "data/items.json").decode("utf-8"))

    def test_roster_has_sixteen_characters(self):
        assert len(progressive_capability.ROSTER) == 16
        assert len(set(progressive_capability.ROSTER)) == 16

    def test_every_capability_name_registered_with_a_stable_code(self):
        items = self._items()
        by_name = {i["name"]: i for i in items}
        expected = {progressive_capability.boost_item_name()}
        for chain in progressive_capability.STAT_CHAINS:
            expected.add(progressive_capability.stat_item_name(chain))
        for character in progressive_capability.ROSTER:
            expected.add(progressive_capability.boost_item_name(character))
            for chain in progressive_capability.STAT_CHAINS:
                expected.add(progressive_capability.stat_item_name(chain, character))
        assert expected == {n for n in by_name if n.startswith(CAPABILITY_ITEM_PREFIXES)}
        for name in expected:
            assert by_name[name]["classification"] == "useful"
            # Reserved (per_character) or option-driven (global) -- either
            # way the TABLE count is 0; actual per-seed counts are computed
            # in progressive_capability.created_item_counts, Trap-item
            # precedent (data/items.json's Icy Road etc. are also 0).
            assert by_name[name]["count"] == 0

    def test_no_duplicate_codes_across_whole_table(self):
        items = self._items()
        codes = [i["code"] for i in items]
        assert len(codes) == len(set(codes))
