"""Independent supply, immutable accounting and explicit capacity refusals."""
import copy
import unittest

from Options import OptionError
from ..content_item_pool import normalize, resolve


def small_pool():
    return {"base": {"trophies": 5, "relics": {"sapphire": 0, "gold": 0, "platinum": 0},
                     "tokens": dict.fromkeys(("red", "green", "blue", "yellow", "purple"), 0),
                     "gems": ["red", "green", "blue", "yellow", "purple"], "keys": 4}}


class TestContentItemPool(unittest.TestCase):
    def test_defaults_are_independent_retail_supply(self):
        base, extras = normalize({})
        self.assertEqual(sum(base.values()), 99)
        self.assertEqual(sum(extras.values()), 0)
        self.assertEqual(base["Platinum Relic"], 18)
        self.assertEqual(base["Purple CTR Token"], 4)

    def test_extras_replace_filler_without_raising_requirements(self):
        raw = small_pool()
        raw["extra"] = {"trophies": 2, "keys": 2, "gems": {"red": 1}}
        before = copy.deepcopy(raw)
        plan = resolve(raw, 21, trap_percentage=50)
        self.assertEqual((plan.filler_count, plan.trap_count), (2, 1))
        key = next(row for row in plan.rows if row.name == "Key")
        self.assertEqual((key.base, key.extra, key.remaining, key.receipt_cap,
                          key.requirement_ceiling), (4, 2, 6, 6, 4))
        self.assertEqual(raw, before)

    def test_starts_and_realized_locks_have_distinct_owners(self):
        plan = resolve(small_pool(), 13, starts={"Key": 2}, additional={"Trophy": 8},
                       locked={"Trophy": 1}, locked_checks=1)
        self.assertEqual(sum(row.remaining for row in plan.rows), 11)
        self.assertEqual(plan.filler_count, 1)
        trophy = next(row for row in plan.rows if row.name == "Trophy")
        self.assertEqual((trophy.remaining, trophy.receipt_cap, trophy.requirement_ceiling), (4, 13, 5))

    def test_overflow_names_counts_and_keeps_settings(self):
        raw = small_pool()
        raw["extra"] = {"keys": 3}
        before = copy.deepcopy(raw)
        with self.assertRaisesRegex(OptionError, "17 selected copies for 15 free checks.*Short by 2 checks"):
            resolve(raw, 15)
        self.assertEqual(raw, before)

    def test_explicit_starts_make_room_without_an_automatic_repair(self):
        with self.assertRaises(OptionError):
            resolve(small_pool(), 12)
        plan = resolve(small_pool(), 12, starts={"Key": 2})
        self.assertEqual(plan.filler_count, 0)
        with self.assertRaisesRegex(OptionError, "cannot supply 5 from-pool starts"):
            resolve(small_pool(), 19, starts={"Key": 5})

    def test_preserves_existing_trap_floor_rounding(self):
        plan = resolve(small_pool(), 19, trap_percentage=50)
        self.assertEqual((plan.filler_count, plan.trap_count), (5, 2))

    def test_absent_race_families_do_not_remove_selected_items(self):
        raw = small_pool()
        raw["base"]["tokens"]["red"] = 8
        raw["base"]["relics"]["gold"] = 3
        # No content/mode input exists here: only the number of active checks.
        names = resolve(raw, 30).selected_names()
        self.assertEqual(names.count("Red CTR Token"), 8)
        self.assertEqual(names.count("Gold Relic"), 3)

    def test_strict_shape_and_mandatory_keys(self):
        invalid = [None, {"unexpected": 2}, {"base": []}, {"base": {"keys": 0}},
                   {"extra": {"percent": 10}}, {"base": {"trophies": True}},
                   {"extra": {"keys": 2.0}}, {"base": {"gems": ["red", "red"]}},
                   {"base": {"gems": ["cyan"]}}, {"base": {"relics": {"silver": 2}}}]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(OptionError):
                normalize(raw)

    def test_registered_pack_copies_share_the_capacity_ledger(self):
        plan = resolve(small_pool(), 16, selected_packs={"Ignore Grass": 1})
        self.assertIn("Ignore Grass", plan.selected_names())
        self.assertEqual(plan.filler_count, 1)
        with self.assertRaises(OptionError):
            resolve(small_pool(), 19, selected_packs={"Key": 1})
        with self.assertRaises(OptionError):
            resolve(small_pool(), 19, locked={"Key": 1}, locked_checks=0)
