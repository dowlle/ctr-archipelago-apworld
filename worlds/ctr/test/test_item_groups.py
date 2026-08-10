"""Guards for the item_name_groups added in issue #167.

Group names share the item-name namespace: AutoWorld's registration metaclass
builds `all_item_and_group_names` from `item_names | set(item_name_groups)`
(worlds/AutoWorld.py:73), and Options.py resolves a YAML entry against the item
names first and the group names second (Options.py:1525). A group named after a
real item would therefore shadow that item in every option that accepts either.
None of the four group names collide today; this test keeps it that way when
items.json grows.

The membership assertions are verbatim against data/items.json because a member
that is not a real item name is silently useless: `item_name_groups.get(name,
{name})` (Options.py:1534, BaseClasses.py:274) expands the group into whatever
strings it holds, and a typo becomes an unresolvable item downstream instead of
an error here.
"""

from worlds.AutoWorld import AutoWorldRegister

from . import CTRTestBase
from ..Items import load_item_table

# The four groups exactly as issue #167 specifies them, with "Traps" extended by
# the 0.2.0 name freeze (#177).
#
# The 11 added traps are the H-dossier families ruled in on 2026-08-10. They are
# registered but not buildable: they carry count 0 in data/items.json and stay
# out of __init__.TRAP_ITEM_NAMES (the draw list pinned to native's
# AP_TrapEffect enum) until their native effects exist. They are in the GROUP
# anyway because item_name_groups is part of the checksummed datapackage
# payload, so adding them later would spend a second bump -- the exact churn
# #177 exists to prevent. Membership feeds !hint / item_links /
# start_inventory_from_pool expansion and is read by nothing in fill, so this
# changes no placement.
EXPECTED_GROUPS = {
    "Relics": {"Sapphire Relic", "Gold Relic", "Platinum Relic"},
    "CTR Tokens": {"Red CTR Token", "Green CTR Token", "Blue CTR Token",
                   "Yellow CTR Token", "Purple CTR Token"},
    "Gems": {"Red Gem", "Green Gem", "Blue Gem", "Yellow Gem", "Purple Gem"},
    "Traps": {
        # shipped, buildable (native AP_TrapEffect 0-4)
        "Icy Road Trap", "Low Gravity Trap", "No Brakes Trap",
        "Forced Boost Trap", "First Person Trap",
        # frozen by #177, not yet buildable
        "Wumpa Reset Trap", "Flatten Trap", "Item Reroll Trap", "Auto-Use Trap",
        "Empty Crates Trap", "Weakened Kart Trap", "No Boost Trap",
        "Wireframe Trap", "Nitro Trap", "Reverse Controls Trap",
        "Red Potion Trap",
    },
}


class TestItemGroups(CTRTestBase):
    def test_groups_match_the_spec(self) -> None:
        """Each declared group holds exactly the members issue #167 names."""
        groups = self.world.item_name_groups
        for group_name, members in EXPECTED_GROUPS.items():
            with self.subTest(group=group_name):
                self.assertIn(group_name, groups)
                self.assertEqual(set(groups[group_name]), members)

    def test_declared_groups_are_only_the_spec_plus_everything(self) -> None:
        """AutoWorld injects "Everything"; nothing else should appear unnoticed."""
        declared = set(self.world.item_name_groups)
        self.assertEqual(declared, set(EXPECTED_GROUPS) | {"Everything"})

    def test_members_are_real_item_names(self) -> None:
        """Every member resolves to an entry in data/items.json."""
        item_names = {item["name"] for item in load_item_table()}
        for group_name, members in EXPECTED_GROUPS.items():
            for member in sorted(members):
                with self.subTest(group=group_name, item=member):
                    self.assertIn(member, item_names)

    def test_group_names_do_not_collide_with_item_names(self) -> None:
        """Group names share a namespace with item names -- no shadowing."""
        item_names = {item["name"] for item in load_item_table()}
        for group_name in self.world.item_name_groups:
            with self.subTest(group=group_name):
                self.assertNotIn(group_name, item_names)

    def test_groups_reach_the_data_package(self) -> None:
        """The datapackage carries the groups, which is what serves group hints."""
        world_type = AutoWorldRegister.world_types["Crash Team Racing"]
        package = world_type.get_data_package_data()
        for group_name, members in EXPECTED_GROUPS.items():
            with self.subTest(group=group_name):
                self.assertEqual(sorted(members),
                                 package["item_name_groups"][group_name])
