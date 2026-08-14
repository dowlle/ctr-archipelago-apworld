"""The 0.2.0 datapackage name freeze (#177).

0.2.0 spends exactly ONE datapackage bump. A name's id is global to the game and
permanent once shipped, so a family discovered after the bump costs a second one
-- which churns the datapackage for everyone running a server or a tracker. #177
makes completeness a build gate rather than a tidiness preference, and this file
is that gate in test form.

Three properties are asserted here, and each one guards a different failure:

  1. THE CENSUS. Every family's exact name count and code block, so a future edit
     that drops or duplicates a name fails loudly with the family named, instead
     of showing up as a one-line manifest diff nobody reads.
  2. INERTNESS. Every frozen name is registered and creates nothing: the location
     classes return empty per-seed subsets and every appended item carries
     count 0. This is what makes the freeze safe to merge ahead of the features
     -- the spine-1 precedent, where 64 per-character capability names shipped
     with the feature gated behind an OptionError.
  3. NO DRIFT BETWEEN THE TWO SIDES. Families that mint BOTH items and locations
     (itemsanity, lettersanity) keep their item order pinned to the module
     constant the location order is built from, so the two halves of one family
     can never be reordered independently.

The per-name id pins live in the two fixtures the #168 / #176 stability tests
read: fixtures/item_id_stability_v0_2_0.json and
fixtures/location_class_id_stability_v0_2_0.json.
"""
import unittest

from worlds.AutoWorld import AutoWorldRegister

from .. import (
    FROZEN_TRAP_ITEM_NAMES,
    TRAP_ITEM_NAMES,
    item_boxes,
    itemsanity,
    lettersanity,
    relic_perfect,
    trial_trophy,
    wumpa_checks,
)
from ..Items import load_item_table
from ..Locations import CTR_LOCATION_CLASSES

#: (registry key, name count, code blocks) for every location class, in
#: registration order. Registration order IS datapackage order.
EXPECTED_CLASSES = [
    ("podium", 112, (35015000, 35015100)),
    ("relic_perfect", 18, (35012400,)),
    ("lettersanity", 48, (35012500,)),
    ("item_boxes", 270, (35014000,)),
    ("itemsanity", 22, (35016000,)),
    ("wumpa", 1, (35016100,)),
    ("trial_trophy", 2, (35016200,)),
]

#: (label, first item code, last item code, count) for each appended item block,
#: in append order. The order of the first two is the ruled freeze order (ruled,
#: 2026-08-10 11:38: itemsanity block first, the H-dossier families after it).
EXPECTED_ITEM_BLOCKS = [
    ("itemsanity weapons", 35010095, 35010105, 11),
    ("H-dossier traps/useful/wumpa", 35010106, 35010122, 17),
    ("character unlocks", 35010123, 35010138, 16),
    ("lettersanity letters", 35010139, 35010186, 48),
    ("gas pedal", 35010187, 35010187, 1),
]

#: Every name the freeze appended to data/items.json, in append order.
FROZEN_ITEM_NAMES = (
    list(itemsanity.ITEM_NAMES)
    + FROZEN_TRAP_ITEM_NAMES
    + ["Passive Shield", "Invincibility Mask", "Invisibility"]
    + ["Small Wumpa Bundle", "Big Wumpa Bundle", "Progressive Starting Wumpa"]
    + ["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura", "Neo Cortex",
       "N. Tropy", "Ripper Roo", "Papu Papu", "Komodo Joe", "Pinstripe",
       "Dingodile", "Tiny Tiger", "N. Gin", "Fake Crash", "Nitros Oxide",
       "Penta Penguin"]
    + list(lettersanity.ITEM_NAMES)
    + ["Gas Pedal"]
)


class TestNameFreezeCensus(unittest.TestCase):
    """Property 1: the counts and blocks are exactly what was signed off."""

    def test_registration_order_and_counts(self) -> None:
        live = [(c.key, len(c.all_locations()), tuple(c.code_blocks))
                for c in CTR_LOCATION_CLASSES]
        self.assertEqual(live, EXPECTED_CLASSES)

    def test_total_registered_names(self) -> None:
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        self.assertEqual(len(world_type.item_name_to_id), 188)
        self.assertEqual(len(world_type.location_name_to_id), 574)

    def test_each_class_codes_sit_inside_its_declared_blocks(self) -> None:
        for location_class in CTR_LOCATION_CLASSES:
            with self.subTest(location_class=location_class.key):
                for name, code, _region in location_class.all_locations():
                    self.assertTrue(
                        any(base <= code < base + 1000
                            for base in location_class.code_blocks),
                        f"{name!r} at {code} escapes {location_class.key}'s "
                        f"declared blocks {location_class.code_blocks}",
                    )

    def test_item_blocks_are_contiguous_and_in_the_ruled_order(self) -> None:
        table = load_item_table()
        codes = [item["code"] for item in table]
        self.assertEqual(codes, list(range(35010000, 35010000 + len(table))),
                         "item codes must stay contiguous from the prefix -- "
                         "ids are positional per #168 and an inserted entry "
                         "renumbers everything after it")
        for label, first, last, count in EXPECTED_ITEM_BLOCKS:
            with self.subTest(block=label):
                self.assertEqual(last - first + 1, count)

    def test_appended_names_match_the_frozen_list_in_order(self) -> None:
        table = load_item_table()
        appended = [item["name"] for item in table
                    if item["code"] >= 35010095]
        self.assertEqual(appended, FROZEN_ITEM_NAMES)

    def test_the_three_families_the_sweep_recovered_are_registered(self) -> None:
        """Character unlocks (#54/#209), the gas pedal (R-I) and the trial-track
        trophy races (#203) were absent from the freeze session's input list and
        were recovered by the #177 item-9 exhaustiveness sweep. Pinned by name so
        a later edit cannot quietly drop them again."""
        item_names = {item["name"] for item in load_item_table()}
        self.assertIn("Gas Pedal", item_names)
        self.assertIn("Nitros Oxide", item_names)
        self.assertIn("Penta Penguin", item_names)
        location_names = {n for n, _c, _r in CTR_LOCATION_CLASSES.all_locations()}
        self.assertIn("Slide Coliseum: Trophy Race", location_names)
        self.assertIn("Turbo Track: Trophy Race", location_names)

    def test_sixteen_character_names_not_fifteen(self) -> None:
        """#209 pins FIFTEEN unlock items per seed, but 15 is a pool count: the
        starting character is a YAML choice, so any of the 16 can be the unlock
        item in some seed and all 16 names must exist. Registered vs created."""
        item_names = {item["name"] for item in load_item_table()}
        characters = FROZEN_ITEM_NAMES[31:47]
        self.assertEqual(len(characters), 16)
        for character in characters:
            with self.subTest(character=character):
                self.assertIn(character, item_names)


class TestNameFreezeInertness(unittest.TestCase):
    """Property 2: registered, creating nothing."""

    def test_unimplemented_frozen_items_have_count_zero(self) -> None:
        for item in load_item_table():
            if item["code"] >= 35010095 and item["name"] not in itemsanity.ITEM_NAMES:
                with self.subTest(item=item["name"]):
                    self.assertEqual(
                        item["count"], 0,
                        "a frozen name that creates pool items is not inert; "
                        "the count belongs to the feature's own build",
                    )

    def test_every_unimplemented_location_class_creates_nothing(self) -> None:
        for location_class in CTR_LOCATION_CLASSES:
            if location_class.key in {"podium", "itemsanity"}:
                continue  # shipped / this build genuinely option-driven
            with self.subTest(location_class=location_class.key):
                self.assertEqual(location_class.created_location_names(None), [])
                self.assertFalse(location_class.is_enabled(None))

    def test_frozen_traps_stay_out_of_the_buildable_draw_list(self) -> None:
        """TRAP_ITEM_NAMES drives the trap_fill_percentage draw and its order is
        pinned to native's AP_TrapEffect enum. A frozen trap with no native
        effect must not be drawable, or a player receives a trap that does
        nothing."""
        self.assertEqual(len(TRAP_ITEM_NAMES), 5)
        self.assertEqual(len(FROZEN_TRAP_ITEM_NAMES), 11)
        self.assertEqual(set(TRAP_ITEM_NAMES) & set(FROZEN_TRAP_ITEM_NAMES), set())

    def test_frozen_traps_are_in_the_datapackage_group_anyway(self) -> None:
        """item_name_groups is part of the checksummed payload, so a trap added
        to its own group later would spend a second bump."""
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        traps = set(world_type.item_name_groups["Traps"])
        self.assertEqual(traps, set(TRAP_ITEM_NAMES) | set(FROZEN_TRAP_ITEM_NAMES))
        self.assertEqual(len(traps), 16)


class TestNameFreezeCrossSideConsistency(unittest.TestCase):
    """Property 3: the item half and the location half of one family agree."""

    def test_itemsanity_item_order_matches_its_location_order(self) -> None:
        table = {item["name"]: item["code"] for item in load_item_table()}
        for wi, weapon in enumerate(itemsanity.WEAPONS):
            with self.subTest(weapon=weapon):
                self.assertEqual(table[weapon], 35010095 + wi)
                self.assertEqual(
                    itemsanity.ITEMSANITY_CLASS.code_for(weapon, False),
                    itemsanity.ITEMSANITY_CODE_BASE + wi * 2)
                self.assertEqual(
                    itemsanity.ITEMSANITY_CLASS.code_for(weapon, True),
                    itemsanity.ITEMSANITY_CODE_BASE + wi * 2 + 1)

    def test_lettersanity_item_order_matches_its_location_order(self) -> None:
        table = {item["name"]: item["code"] for item in load_item_table()}
        self.assertEqual(len(lettersanity.ITEM_NAMES), 48)
        for i, item_name in enumerate(lettersanity.ITEM_NAMES):
            with self.subTest(item=item_name):
                self.assertEqual(table[item_name], 35010139 + i)
        for ti, track in enumerate(lettersanity.LETTER_TRACKS):
            for li, letter in enumerate(lettersanity.LETTERS):
                with self.subTest(track=track, letter=letter):
                    self.assertEqual(
                        lettersanity.LETTERSANITY_CLASS.code_for(track, letter),
                        lettersanity.LETTERSANITY_CODE_BASE + ti * 3 + li)

    def test_the_eighteen_track_families_share_one_canonical_order(self) -> None:
        """Boxes and relic perfects both derive their track order from the
        Sapphire trial block, so they cannot drift apart."""
        self.assertEqual(item_boxes.BOX_TRACKS, relic_perfect.RELIC_TRACKS)
        self.assertEqual(len(item_boxes.BOX_TRACKS), 18)
        self.assertEqual(item_boxes.BOX_TRACKS[-2:],
                         list(trial_trophy.TRIAL_TRACKS))

    def test_lettersanity_covers_exactly_the_token_challenge_tracks(self) -> None:
        self.assertEqual(len(lettersanity.LETTER_TRACKS), 16)
        self.assertEqual(lettersanity.LETTER_TRACKS,
                         item_boxes.BOX_TRACKS[:16])

    def test_the_box_ceiling_is_the_full_grid_not_the_authored_set(self) -> None:
        """Ruled 2026-08-10 16:23: freeze 18 x 15, not the 241 authored boxes, so
        curation and lap-skip additions never need a second bump."""
        self.assertEqual(item_boxes.SLOTS_PER_TRACK, 15)
        self.assertEqual(len(item_boxes.ITEM_BOX_CLASS.all_locations()), 270)
        for track in item_boxes.BOX_TRACKS:
            with self.subTest(track=track):
                self.assertEqual(
                    item_boxes.ITEM_BOX_CLASS.location_name(track, 1),
                    f"{track}: Item Box 1")

    def test_the_wumpa_check_is_global_and_singular(self) -> None:
        """Ruled 2026-08-10 16:28: one location per seed, not one per track."""
        self.assertEqual(len(wumpa_checks.WUMPA_CLASS.all_locations()), 1)
