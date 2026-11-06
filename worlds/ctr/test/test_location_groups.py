"""Exact membership for the location name groups (#536).

The expected sets are derived here with plain string matching over the
registered location names and from the owning classes, not by calling
location_groups, so the builder and its check cannot share a mistake.
"""
import re

from worlds.AutoWorld import AutoWorldRegister

from . import CTRTestBase
from ..hit_character import HIT_CHARACTER_CLASS
from ..itemsanity import ITEMSANITY_CLASS
from ..location_class import LocationClassRegistry
from ..location_groups import build_location_name_groups
from ..Locations import CTR_LOCATION_CLASSES

KIND_GROUPS = (
    "Held Placements", "Finish Podium", "Trophy Race", "CTR Challenge",
    "Relic Race", "Relic Race Sapphire", "Relic Race Gold",
    "Relic Race Platinum", "Battle Arenas", "Gem Cups", "Boss Races",
    "Hit Characters", "Item Boxes",
)
RETAIL_TRACKS = (
    "Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway", "Coco Park",
    "Tiger Temple", "Papu's Pyramid", "Dingo Canyon", "Blizzard Bluff",
    "Dragon Mines", "Polar Pass", "Tiny Arena", "Hot Air Skyway",
    "Cortex Castle", "N. Gin Labs", "Oxide Station",
)
OTHER_TRACKS = (
    "Skull Rock", "Rampage Ruins", "Rocky Road", "Nitro Court",
    "Slide Coliseum", "Turbo Track", "Red Gem Cup", "Green Gem Cup",
    "Blue Gem Cup", "Yellow Gem Cup", "Purple Gem Cup", "Cortex Vortex",
    "Parking Lot", "The North Bowl", "Lab Basement",
)
GEM_CUPS = ("Red Gem Cup", "Green Gem Cup", "Blue Gem Cup", "Yellow Gem Cup",
            "Purple Gem Cup")
ARENAS = ("Skull Rock", "Rampage Ruins", "Rocky Road", "Nitro Court",
          "Parking Lot", "The North Bowl", "Lab Basement")
GARAGES = ("Ripper Roo Garage", "Papu Papu Garage", "Komodo Joe Garage",
           "Pinstripe Garage", "N. Oxide Garage")


def _split(name):
    track, sep, suffix = name.partition(": ")
    return (track, suffix) if sep else (None, name)


class TestLocationGroups(CTRTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.groups = self.world.location_name_groups
        self.names = set(self.world.location_name_to_id)

    def _where(self, test):
        return {n for n in self.names if test(*_split(n))}

    def test_the_declared_groups_are_the_expected_set(self) -> None:
        for group in (*KIND_GROUPS, *RETAIL_TRACKS, *OTHER_TRACKS,
                      "Itemsanity Checks", "Everywhere"):
            self.assertIn(group, self.groups)
        named = set(self.groups) - set(KIND_GROUPS) - set(RETAIL_TRACKS) \
            - set(OTHER_TRACKS) - {"Itemsanity Checks", "Everywhere"}
        self.assertEqual(len(named), 86)
        self.assertIn("Acid Lake", named)

    def test_every_track_group_is_that_tracks_prefix(self) -> None:
        for group, members in self.groups.items():
            if group in KIND_GROUPS or group in ("Everywhere",
                                                 "Itemsanity Checks"):
                continue
            with self.subTest(group=group):
                self.assertEqual(
                    members, {n for n in self.names if n.startswith(f"{group}: ")})

    def test_group_counts(self) -> None:
        # 31 retail and special tracks + 86 named blocks + 13 kind groups
        # + Itemsanity Checks + Everywhere.
        self.assertEqual(len(self.groups), 31 + 86 + 13 + 1 + 1)
        self.assertEqual(len(self.groups["Crash Cove"]), 34 + 35)
        self.assertEqual(len(self.groups["Cortex Vortex"]), 17)

    def test_no_generic_custom_slot_has_a_group(self) -> None:
        self.assertFalse([g for g in self.groups if g.startswith("Custom Track")])

    def test_held_placements(self) -> None:
        want = self._where(lambda t, s: re.fullmatch(r"Held \d+(st|nd|rd|th)", s))
        self.assertEqual(self.groups["Held Placements"], want)
        self.assertEqual(len(want), 711)

    def test_finish_podium(self) -> None:
        want = self._where(lambda t, s: s in (
            "Finish on Podium", "Finish 1st", "Finish 2nd or 3rd"))
        self.assertEqual(self.groups["Finish Podium"], want)
        self.assertEqual(len(want), 269)
        self.assertNotIn("Crash Cove: Finish (Any Position)", want)

    def test_trophy_race_and_ctr_challenge(self) -> None:
        self.assertEqual(self.groups["Trophy Race"],
                         self._where(lambda t, s: s == "Trophy Race"))
        self.assertEqual(self.groups["CTR Challenge"],
                         self._where(lambda t, s: s == "CTR Token Challenge"))
        self.assertEqual(len(self.groups["Trophy Race"]), 237)
        self.assertEqual(len(self.groups["CTR Challenge"]), 237)

    def test_relic_race_and_tiers(self) -> None:
        tiers = {}
        for tier in ("Sapphire", "Gold", "Platinum"):
            tiers[tier] = self._where(lambda t, s, tier=tier:
                                      s == f"{tier} Time Trial")
            self.assertEqual(self.groups[f"Relic Race {tier}"], tiers[tier])
            self.assertEqual(len(tiers[tier]), 237)
        perfect = self._where(lambda t, s: s == "Relic Race Perfect")
        self.assertEqual(self.groups["Relic Race"],
                         set().union(*tiers.values()) | perfect)
        self.assertEqual(len(self.groups["Relic Race"]), 948)

    def test_battle_arenas_gem_cups_boss_races(self) -> None:
        self.assertEqual(self.groups["Battle Arenas"],
                         self._where(lambda t, s: t in ARENAS))
        self.assertEqual(self.groups["Gem Cups"],
                         self._where(lambda t, s: t in GEM_CUPS))
        self.assertEqual(self.groups["Boss Races"],
                         self._where(lambda t, s: t in GARAGES))
        self.assertEqual(len(self.groups["Battle Arenas"]), 147)
        self.assertEqual(len(self.groups["Gem Cups"]), 10)
        self.assertEqual(len(self.groups["Boss Races"]), 6)
        self.assertIn("Ripper Roo Garage: Boss Race", self.groups["Boss Races"])
        self.assertIn("N. Oxide Garage: N. Oxide's Final Challenge",
                      self.groups["Boss Races"])

    def test_hit_characters_and_item_boxes(self) -> None:
        self.assertEqual(self.groups["Hit Characters"],
                         set(HIT_CHARACTER_CLASS.names()))
        self.assertEqual(len(self.groups["Hit Characters"]), 16)
        self.assertEqual(self.groups["Item Boxes"],
                         self._where(lambda t, s: re.fullmatch(r"Item Box \d+", s)))
        # 270 retail + 86 x 15 named + 132 x 15 generic, plus the alpha3 Item
        # Box 16 to 50 for 18 retail tracks and 86 named blocks.
        self.assertEqual(len(self.groups["Item Boxes"]), 3540 + 18 * 35 + 86 * 35)

    def test_itemsanity_checks_is_kept(self) -> None:
        self.assertEqual(self.groups["Itemsanity Checks"],
                         set(ITEMSANITY_CLASS.names()))

    def test_members_are_registered_and_names_do_not_collide(self) -> None:
        items = set(self.world.item_name_to_id)
        for group, members in self.groups.items():
            if group == "Everywhere":
                continue
            with self.subTest(group=group):
                self.assertTrue(members)
                self.assertLessEqual(members, self.names)
                self.assertNotIn(group, self.names)
                self.assertNotIn(group, items)

    def test_groups_reach_the_data_package(self) -> None:
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        package = world_type.get_data_package_data()
        for group, members in self.groups.items():
            if group == "Everywhere":
                continue
            with self.subTest(group=group):
                self.assertEqual(sorted(members),
                                 package["location_name_groups"][group])

    def test_a_group_named_like_a_location_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "collides"):
            build_location_name_groups(
                [*self.names, "Held Placements"], CTR_LOCATION_CLASSES)

    def test_a_group_named_like_an_item_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "collides"):
            build_location_name_groups(
                self.names, CTR_LOCATION_CLASSES, ["Item Boxes"])

    def test_a_class_group_may_not_repeat_a_registry_group(self) -> None:
        class Dup(LocationClassRegistry):
            def location_name_groups(self):
                return {"Item Boxes": {"Crash Cove: Item Box 1"}}
        with self.assertRaisesRegex(ValueError, "twice"):
            build_location_name_groups(self.names, Dup())
