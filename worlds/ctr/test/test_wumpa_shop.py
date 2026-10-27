"""The Wumpa Shop and the Wumpa goal (#249).

Design: 0.3.0 design - Wumpa Shop and Wumpa goal (#249), with the design
review and the rulings of 2026-10-16. test/fixtures/wumpa_shop.json is the
shared wire fixture; a byte-identical copy lives in native as
tools/fixtures/wumpa_shop.json and native's test-wumpa-shop-seedcfg harness
parses it.
"""
import json
import pkgutil
import unittest

from BaseClasses import CollectionState, LocationProgressType
from Fill import distribute_items_restrictive
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld, sphere0_guard
from .. import wumpa_shop as ws

FIXTURE = json.loads(pkgutil.get_data(__package__, "fixtures/wumpa_shop.json"))
PLAYER = 1


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, seed=seed, options=options)


def _filled(seed=1, **options):
    mw = _build(seed, **options)
    distribute_items_restrictive(mw)
    call_all(mw, "post_fill")
    return mw


def _shop_locations(mw):
    return [loc for loc in mw.get_locations(PLAYER)
            if getattr(loc, "type", None) == ws.LOCATION_TYPE]


class TestShelves(unittest.TestCase):
    def test_initial_shelves_are_half_and_at_least_two(self):
        self.assertEqual([ws.initial_shelves(n) for n in (1, 2, 3, 4, 10, 25)],
                         [1, 2, 2, 2, 5, 13])

    def test_unlocks_step_by_fifty_scaled(self):
        self.assertEqual([ws.unlock_banked(n, 10, 100) for n in range(1, 11)],
                         [0, 0, 0, 0, 0, 50, 100, 150, 200, 250])
        self.assertEqual(ws.unlock_banked(25, 25, 100), 600)
        self.assertEqual(ws.unlock_banked(6, 10, 25), 13)

    def test_bands_scale_and_never_reach_zero(self):
        self.assertEqual(ws.price_band("Citadel City", 100), (40, 80))
        self.assertEqual(ws.price_band("N. Sanity Beach", 25), (3, 8))
        self.assertEqual(ws.price_band("N. Sanity Beach", 400), (40, 120))


class TestCreation(unittest.TestCase):
    def test_slots_per_hub_create_five_times_n(self):
        for n in (0, 1, 10, 25):
            with self.subTest(slots=n):
                mw = _build(1, wumpa_shop_slots=n)
                shop = _shop_locations(mw)
                self.assertEqual(len(shop), 5 * n)
                for loc in shop:
                    hub = loc.name.split(" Shop: Slot ")[0]
                    self.assertEqual(loc.parent_region.name, hub)
                    self.assertEqual(loc.address, ws.shop_code(hub, int(loc.name.rsplit(" ", 1)[1])))

    def test_off_creates_no_event_and_no_wire(self):
        mw = _build(1, wumpa_shop_slots=0, goal_wumpa=0)
        self.assertNotIn(ws.WUMPA_INCOME, {loc.name for loc in mw.get_locations(PLAYER)})
        self.assertNotIn(ws.WUMPA_INCOME_REGION, {r.name for r in mw.get_regions(PLAYER)})
        sd = mw.worlds[PLAYER].fill_slot_data()
        self.assertNotIn("wumpa_shop", sd)
        for key in ws.options_to_wire(mw.worlds[PLAYER].options):
            self.assertNotIn(key, sd["ctr_options"])

    def test_goal_alone_creates_income_but_no_shop(self):
        mw = _build(1, wumpa_shop_slots=0, goal_wumpa=200)
        self.assertIn(ws.WUMPA_INCOME, {loc.name for loc in mw.get_locations(PLAYER)})
        self.assertEqual(_shop_locations(mw), [])
        sd = mw.worlds[PLAYER].fill_slot_data()
        self.assertNotIn("wumpa_shop", sd)
        self.assertEqual(sd["ctr_options"]["goal_wumpa"], 200)
        self.assertEqual(sd["ctr_options"]["wumpa_shop_slots"], 0)


class TestLogic(unittest.TestCase):
    def test_every_slot_needs_income(self):
        mw = _build(1)
        state = CollectionState(mw)
        for item in mw.itempool:
            state.collect(item, True)
        shop = _shop_locations(mw)
        self.assertTrue(shop)
        self.assertFalse(any(loc.can_reach(state) for loc in shop))
        income = mw.get_location(ws.WUMPA_INCOME, PLAYER)
        self.assertTrue(income.can_reach(state))
        state.collect(income.item, True)
        self.assertTrue(all(loc.can_reach(state) for loc in shop))

    def test_income_comes_from_a_retail_track_finish(self):
        mw = _build(1)
        region = mw.get_region(ws.WUMPA_INCOME_REGION, PLAYER)
        sources = {ent.parent_region.name for ent in region.entrances}
        self.assertTrue(sources)
        self.assertTrue(sources <= set(ws.income_tracks(mw.worlds[PLAYER])))

    def test_shop_slots_never_count_as_starting_checks(self):
        mw = _build(1)
        world = mw.worlds[PLAYER]
        base = sphere0_guard._base_state(world)
        open_shop = [loc for loc in _shop_locations(mw) if loc.can_reach(base)]
        self.assertTrue(open_shop, "precondition: the N. Sanity Beach shop is open at the start")
        expected = sum(1 for loc in mw.get_locations(PLAYER)
                       if loc.item is None and loc.address is not None
                       and loc.type != ws.LOCATION_TYPE and loc.can_reach(base))
        self.assertEqual(sphere0_guard.sphere0_breadth(world), expected)


class TestPlacement(unittest.TestCase):
    def test_later_shelves_hold_no_progression(self):
        for seed in (1, 2, 3, 4, 5):
            with self.subTest(seed=seed):
                mw = _filled(seed, wumpa_shop_slots=10)
                first = ws.initial_shelves(10)
                for loc in _shop_locations(mw):
                    if int(loc.name.rsplit(" ", 1)[1]) > first:
                        self.assertFalse(loc.item.advancement, loc.name)

    def test_excluded_holds_no_progression_and_no_useful(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                mw = _filled(seed, wumpa_shop_progression="excluded")
                for loc in _shop_locations(mw):
                    self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED)
                    self.assertFalse(loc.item.advancement, loc.name)
                    self.assertFalse(loc.item.useful, loc.name)


class TestPrices(unittest.TestCase):
    def test_prices_in_band_and_progression_at_the_bottom(self):
        for percent in (25, 100, 400):
            with self.subTest(percent=percent):
                mw = _filled(2, wumpa_shop_prices=percent)
                world = mw.worlds[PLAYER]
                block = world.fill_slot_data()["wumpa_shop"]
                by_code = {s["code"]: s for h in block["hubs"] for s in h["slots"]}
                for loc in _shop_locations(mw):
                    hub = loc.name.split(" Shop: Slot ")[0]
                    low, high = ws.price_band(hub, percent)
                    price = by_code[loc.address]["price"]
                    self.assertTrue(low <= price <= high, (loc.name, price))
                    if loc.item.advancement:
                        self.assertEqual(price, low, loc.name)

    def test_same_seed_same_prices(self):
        a = _filled(7).worlds[PLAYER].fill_slot_data()["wumpa_shop"]
        b = _filled(7).worlds[PLAYER].fill_slot_data()["wumpa_shop"]
        self.assertEqual(a, b)


class TestWire(unittest.TestCase):
    def test_fixture_block_is_the_pure_layout(self):
        o = FIXTURE["ctr_options"]
        prices = {ws.shop_name(hub, n): slot["price"]
                  for hub, h in zip(ws.SHOP_HUBS, FIXTURE["wumpa_shop"]["hubs"])
                  for n, slot in enumerate(h["slots"], 1)}
        self.assertEqual(ws.block_from(o["wumpa_shop_slots"], o["wumpa_shop_prices"],
                                       prices.__getitem__),
                         FIXTURE["wumpa_shop"])

    def test_generated_block_shape(self):
        mw = _filled(3, wumpa_shop_slots=4, wumpa_shop_prices=150, goal_wumpa=300)
        sd = mw.worlds[PLAYER].fill_slot_data()
        self.assertEqual(set(sd["ctr_options"]) >= set(FIXTURE["ctr_options"]), True)
        for key, value in FIXTURE["ctr_options"].items():
            self.assertEqual(sd["ctr_options"][key], value, key)
        block = sd["wumpa_shop"]
        self.assertEqual(block["version"], FIXTURE["wumpa_shop"]["version"])
        self.assertEqual([h["level"] for h in block["hubs"]],
                         [h["level"] for h in FIXTURE["wumpa_shop"]["hubs"]])
        for got, want in zip(block["hubs"], FIXTURE["wumpa_shop"]["hubs"]):
            self.assertEqual([(s["code"], s["unlock_banked"]) for s in got["slots"]],
                             [(s["code"], s["unlock_banked"]) for s in want["slots"]])

    def test_ut_restores_the_seed_values(self):
        sd = _filled(1, wumpa_shop_slots=7, wumpa_shop_prices=60,
                     wumpa_shop_progression="excluded", wumpa_shop_hints=False,
                     goal_wumpa=450).worlds[PLAYER].fill_slot_data()
        other = _build(2).worlds[PLAYER]
        ws.restore_options(other.options, sd)
        self.assertEqual(ws.options_to_wire(other.options),
                         {k: sd["ctr_options"][k] for k in ws.options_to_wire(other.options)})

    def test_ut_without_keys_restores_off(self):
        other = _build(2).worlds[PLAYER]
        self.assertEqual(other.options.wumpa_shop_slots.value, 10)
        ws.restore_options(other.options, {"ctr_options": {"schema_version": 18}})
        self.assertEqual(other.options.wumpa_shop_slots.value, 0)
        self.assertEqual(other.options.goal_wumpa.value, 0)


class TestGoal(unittest.TestCase):
    def test_wumpa_alone_is_a_valid_goal(self):
        mw = _filled(1, oxide_goal="none", goal_wumpa=100)
        self.assertEqual(mw.worlds[PLAYER].fill_slot_data()["ctr_options"]["goal"], -1)
        self.assertTrue(mw.can_beat_game(mw.state))

    def test_all_off_is_still_refused(self):
        with self.assertRaises(OptionError):
            _build(1, oxide_goal="none", goal_wumpa=0)

    def test_goal_needs_income_and_the_other_arms(self):
        mw = _build(1, bosses_required_goal=2, goal_wumpa=100)
        state = CollectionState(mw)
        for item in mw.itempool:
            state.collect(item, True)
        state.sweep_for_advancements(
            locations=[loc for loc in mw.get_locations(PLAYER)
                       if loc.item is not None and loc.name != ws.WUMPA_INCOME])
        self.assertFalse(mw.completion_condition[PLAYER](state))
        state.collect(mw.get_location(ws.WUMPA_INCOME, PLAYER).item, True)
        self.assertTrue(mw.completion_condition[PLAYER](state))


class TestContentPlan(unittest.TestCase):
    class _Opt:
        def __init__(self, value):
            self.value = value

    class _World:
        def __init__(self, goal):
            class O:
                pass
            self.options = O()
            self.options.goal_wumpa = TestContentPlan._Opt(goal)
            self.options.wumpa_shop_slots = TestContentPlan._Opt(10)

    def test_content_plan_turns_the_shop_off(self):
        world = self._World(0)
        ws.disable_for_content_plan(world, refuse=True)
        self.assertEqual(world.options.wumpa_shop_slots.value, 0)

    def test_content_plan_refuses_a_wumpa_goal(self):
        with self.assertRaises(OptionError):
            ws.disable_for_content_plan(self._World(100), refuse=True)


if __name__ == "__main__":
    unittest.main()
