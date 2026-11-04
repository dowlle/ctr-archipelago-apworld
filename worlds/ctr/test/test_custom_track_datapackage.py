import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from worlds.AutoWorld import data_package_checksum
from ..custom_track_datapackage import embed_track_names


class TestRoomNames(unittest.TestCase):
    game = "Crash Team Racing"

    def build(self, aliases, names=None, *, reverse=False):
        names = names or {"Custom Track 1: Trophy Race": 1,
                          "Custom Track 2: Trophy Race": 2,
                          "Crash Cove: Trophy Race": 3}
        package = {"checksum": "original", "item_name_to_id": {"Key": 4},
                   "location_name_to_id": names,
                   "location_name_groups": {"Everything": list(names)}}
        original = copy.deepcopy(package)
        players = list(aliases)
        if reverse:
            players.reverse()
        worlds = {p: SimpleNamespace(game=self.game, aliases=a) for p, a in aliases.items()}
        mw = SimpleNamespace(player_ids=players, worlds=worlds,
                             player_name={p: f"Player{p}" for p in players},
                             get_locations=lambda p: [SimpleNamespace(address=c) for c in aliases[p]])
        data = {"datapackage": {self.game: package}}
        with patch("worlds.ctr.custom_track_datapackage.location_aliases",
                   side_effect=lambda w, **kwargs: w.aliases), \
                patch("worlds.ctr.custom_track_datapackage.item_aliases", return_value={}):
            embed_track_names(mw, data, self.game)
        self.assertEqual(package, original, "registered package mutated")
        result = data["datapackage"][self.game]
        self.assertEqual(set(result["location_name_to_id"].values()), set(names.values()))
        self.assertEqual(len(result["location_name_to_id"]), len(names))
        if result is not package:
            payload = {k: v for k, v in result.items() if k != "checksum"}
            self.assertEqual(data_package_checksum(payload), result["checksum"])
            self.assertEqual(set(result["location_name_groups"]["Everything"]),
                             set(result["location_name_to_id"]))
        return result

    def test_plain_title_and_shared_title(self):
        a = {1: "Baby T Park: Trophy Race"}
        single = self.build({1: a})
        shared = self.build({1: a, 2: a})
        self.assertEqual(single, shared)
        self.assertEqual(single["location_name_to_id"][a[1]], 1)

    def test_conflicting_players_are_both_named_and_order_is_stable(self):
        aliases = {1: {1: "Baby T Park: Trophy Race"}, 2: {1: "Cortex Vortex: Trophy Race"}}
        result = self.build(aliases)
        self.assertEqual(result, self.build(aliases, reverse=True))
        name = next(n for n, c in result["location_name_to_id"].items() if c == 1)
        self.assertEqual(name, "Baby T Park: Trophy Race (Player1, P1) / "
                               "Cortex Vortex: Trophy Race (Player2, P2)")

    def test_duplicate_title_and_retail_collision_keep_every_code(self):
        self.build({1: {1: "Same: Trophy Race", 2: "Same: Trophy Race"}})
        result = self.build({1: {1: "Crash Cove: Trophy Race"}})
        self.assertEqual(result["location_name_to_id"]["Crash Cove: Trophy Race"], 3)
        self.assertIn("Crash Cove: Trophy Race [location 1]", result["location_name_to_id"])

    def test_crafted_disambiguation_suffix_cannot_overwrite_another_code(self):
        result = self.build({1: {1: "X", 2: "X", 3: "X [location 1]"}})
        self.assertIn("X [location 1]*", result["location_name_to_id"])

    def test_datapackage_titles_are_plain_text(self):
        result = self.build({1: {1: "[Test] & Park: Trophy Race"}})
        self.assertIn("[Test] & Park: Trophy Race", result["location_name_to_id"])

    def test_no_custom_is_byte_equivalent_and_checksum_changes_with_title(self):
        self.assertEqual(self.build({1: {}})["checksum"], "original")
        self.assertNotEqual(self.build({1: {1: "A"}})["checksum"],
                            self.build({1: {1: "B"}})["checksum"])
