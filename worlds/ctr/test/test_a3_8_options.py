"""A3-8: hint filter defaults, the adventure_structure rename and alias, the crystal_arenas default pool and the
required_entries error text."""
import json
import unittest
from types import SimpleNamespace

from Options import OptionError

from .. import content_plan
from ..Options import AdventureStructure, CrystalArenas, PadHintsProgressionOnly, PadHintsWaitForSpoiler
from .. import arena_content
from .test_content_ctr_first import first_options
from .test_content_plan import make_world, profile_options
from .test_item_packs import pack_options


class TestHintFilterDefaults(unittest.TestCase):
    def test_pad_filters_default_on_shop_filter_stays_off(self):
        self.assertEqual(PadHintsWaitForSpoiler.default, 1)
        self.assertEqual(PadHintsProgressionOnly.default, 1)
        wire = make_world(pack_options(), seed=3).fill_slot_data()["ctr_options"]
        self.assertIs(wire["pad_hints_wait_for_spoiler"], True)
        self.assertIs(wire["pad_hints_progression_only"], True)
        self.assertNotIn("shop_hints_progression_only", wire)

    def test_explicit_off_sends_no_key(self):
        wire = make_world(pack_options(pad_hints_wait_for_spoiler=False, pad_hints_progression_only=False),
                          seed=3).fill_slot_data()["ctr_options"]
        self.assertNotIn("pad_hints_wait_for_spoiler", wire)
        self.assertNotIn("pad_hints_progression_only", wire)

    def test_explicit_values_do_not_change_the_rest_of_the_wire(self):
        on = make_world(pack_options(), seed=3).fill_slot_data()
        off = make_world(pack_options(pad_hints_wait_for_spoiler=False, pad_hints_progression_only=False),
                         seed=3).fill_slot_data()
        on["ctr_options"].pop("pad_hints_wait_for_spoiler")
        on["ctr_options"].pop("pad_hints_progression_only")
        self.assertEqual(json.dumps(on, sort_keys=True), json.dumps(off, sort_keys=True))


class TestAdventureStructureName(unittest.TestCase):
    def test_new_name_and_old_alias_are_the_same_value(self):
        self.assertEqual(AdventureStructure.from_text("trophy_ctr_combined").value, 1)
        self.assertEqual(AdventureStructure.from_text("ctr_first").value, 1)
        self.assertEqual(AdventureStructure.from_any("ctr_first").value, 1)
        self.assertEqual(AdventureStructure.from_any("classic").value, 0)
        self.assertEqual(AdventureStructure.default, 0)
        self.assertEqual(AdventureStructure.name_lookup[1], "trophy_ctr_combined")

    def test_text_says_it_merges_the_two_races(self):
        doc = " ".join(AdventureStructure.__doc__.split())
        self.assertIn("merges the Trophy Race and the CTR Challenge into one race", doc)
        self.assertIn("`ctr_first` is the old name", doc)

    def test_old_and_new_names_generate_the_same_seed(self):
        old = make_world(first_options(adventure_structure="ctr_first"), seed=7)
        new = make_world(first_options(adventure_structure="trophy_ctr_combined"), seed=7)
        self.assertEqual(json.dumps(old.fill_slot_data(), sort_keys=True),
                         json.dumps(new.fill_slot_data(), sort_keys=True))
        # The wire keeps the string native reads.
        self.assertEqual(old.ctr_content_plan["adventure_structure"], "ctr_first")


class TestCrystalArenasDefault(unittest.TestCase):
    def test_default_pool_is_every_arena(self):
        self.assertEqual(CrystalArenas.default, frozenset(arena_content.ARENAS.values()))
        self.assertEqual(len(CrystalArenas.default), 7)

    def test_default_pool_reaches_the_draw_and_an_explicit_four_still_works(self):
        def settings(arenas):
            return content_plan.crystal_settings(SimpleNamespace(
                crystal_arenas=CrystalArenas.from_any(arenas), crystal_challenge_count=SimpleNamespace(value=4)))
        self.assertEqual(sorted(settings(CrystalArenas.default)[0]), sorted(arena_content.ARENAS))
        four = ["Rocky Road", "Rampage Ruins", "Skull Rock", "Nitro Court"]
        self.assertEqual(len(settings(four)[0]), 4)


class TestRequiredEntriesError(unittest.TestCase):
    def raised(self, entries):
        options = profile_options()
        options["content_pool"]["required_entries"] = entries
        with self.assertRaises(OptionError) as caught:
            make_world(options)
        return str(caught.exception)

    def test_names_each_entry_it_cannot_match(self):
        text = self.raised(["custom/baby-t-park/1.0.2", "Nowhere Speedway", "Moon Base"])
        self.assertIn("distinct tracks and arenas this seed can use", text)
        self.assertIn("'Nowhere Speedway'", text)
        self.assertIn("'Moon Base'", text)
        self.assertNotIn("baby-t-park", text)

    def test_names_a_repeated_entry(self):
        text = self.raised(["custom/baby-t-park/1.0.2", "custom/baby-t-park/1.0.2"])
        self.assertIn("listed more than once: 'baby-t-park'", text)


if __name__ == "__main__":
    unittest.main()
