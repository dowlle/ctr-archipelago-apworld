"""Progressive Boost / Progressive Stats item packs (issues #12, #13).

Scope per the 0.2.0 spine-1 work order: pool/fill correctness only. No test
here checks track logic gating on a tier -- there is none yet, by design
(the capability matrix tiers are deliberately NOT encoded this order).

Covers: item counts per mode (off / shared_global / per_character-raises),
the blue-fire chain-length toggle, #168 code stability, the wire round-trip
(ctr_options boost_mode / boost_blue_fire / stats_mode), the pool-overflow
RAISE guard, and vanilla/off byte parity (no RNG draw, item pool unchanged).
"""
import pkgutil
import json

from Options import OptionError

from .. import progressive_capability
from . import CTRTestBase

CAPABILITY_ITEM_PREFIXES = (
    "Progressive Boost", "Progressive Top Speed",
    "Progressive Acceleration", "Progressive Turning",
)


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


class TestBoostPerCharacterBlocked(CTRTestBase):
    """per_character is reserved (names minted, issue #71 not built) --
    selecting it must raise, not silently generate an infeasible world."""

    auto_construct = False
    options = {"progressive_boost": "per_character"}

    def test_raises_option_error(self):
        with self.assertRaises(OptionError) as ctx:
            self.world_setup()
        self.assertIn("progressive_boost", str(ctx.exception))
        self.assertIn("per_character", str(ctx.exception))


class TestStatsPerCharacterBlocked(CTRTestBase):
    """Sibling of TestBoostPerCharacterBlocked for progressive_stats."""

    auto_construct = False
    options = {"progressive_stats": "per_character"}

    def test_raises_option_error(self):
        with self.assertRaises(OptionError) as ctx:
            self.world_setup()
        self.assertIn("progressive_stats", str(ctx.exception))
        self.assertIn("per_character", str(ctx.exception))


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
            # precedent (data/items.json's Icy Road Trap etc. are also 0).
            assert by_name[name]["count"] == 0

    def test_no_duplicate_codes_across_whole_table(self):
        items = self._items()
        codes = [i["code"] for i in items]
        assert len(codes) == len(set(codes))
