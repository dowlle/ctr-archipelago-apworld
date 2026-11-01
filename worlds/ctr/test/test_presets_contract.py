"""The three presets are one shared set (2026-10-28 ruling): Play Solo reads them
from the packed apworld, and AP-Pie's YAML Builder reads the same files from the
release apworld of the version it builds for. This locks the contract AP-Pie
relies on: the index file, the three names, one game block per YAML, and only
real option names in it. Whether each preset generates is test_solo_runtime."""
import json
import os
import unittest

import yaml

from ..Options import ctrAPOptions

PRESETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solo", "presets")
GAME = "Crash Team Racing"


class PresetsContractTest(unittest.TestCase):
    def index(self):
        with open(os.path.join(PRESETS, "presets.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def test_index_lists_the_three_presets_in_order(self):
        index = self.index()
        self.assertEqual(index["schema"], 1)
        self.assertEqual([(p["id"], p["label"]) for p in index["presets"]],
                         [("quick", "Quick"), ("standard", "Standard"), ("full_adventure", "Full Adventure")])
        for preset in index["presets"]:
            self.assertEqual(sorted(preset), ["file", "id", "label", "summary"])
            self.assertTrue(preset["summary"])

    def test_every_preset_file_is_one_ctr_game_block_of_real_options(self):
        known = set(ctrAPOptions.type_hints)
        for preset in self.index()["presets"]:
            with self.subTest(preset=preset["id"]):
                with open(os.path.join(PRESETS, preset["file"]), encoding="utf-8") as handle:
                    doc = yaml.safe_load(handle)
                self.assertEqual(doc["game"], GAME)
                self.assertEqual(set(doc) - {"name", "game", GAME}, set())
                # accessibility and the other core options are Archipelago's own
                unknown = set(doc[GAME]) - known - {"accessibility", "progression_balancing"}
                self.assertEqual(unknown, set())
                self.assertEqual(doc[GAME]["death_link"], "off")

    def test_every_file_in_the_folder_is_indexed(self):
        listed = {p["file"] for p in self.index()["presets"]} | {"presets.json"}
        self.assertEqual(set(os.listdir(PRESETS)), listed)


if __name__ == "__main__":
    unittest.main()
