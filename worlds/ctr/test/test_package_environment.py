"""Check the packed world's boundary with the standalone Solo runtime."""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


WORLD = pathlib.Path(__file__).resolve().parents[1]


class PackageEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get("CTR_PACKED_APWORLD")
        if archive:
            cls.archive = pathlib.Path(archive)
            return
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.archive = pathlib.Path(folder.name) / "ctr.apworld"
        subprocess.run([sys.executable, str(WORLD / "tools" / "build_apworld.py"),
                        str(cls.archive)], check=True, capture_output=True)

    def test_packed_python_has_no_environment_access(self):
        forbidden = re.compile(r"\bos\s*\.\s*(environ|getenv|putenv|unsetenv)\b")
        findings = []
        with zipfile.ZipFile(self.archive) as packed:
            for name in packed.namelist():
                if name.endswith(".py"):
                    for number, line in enumerate(packed.read(name).decode("utf-8").splitlines(), 1):
                        if forbidden.search(line):
                            findings.append(f"{name}:{number}: {line.strip()}")
        self.assertEqual(findings, [], "\n".join(findings))

    def test_packed_world_omits_solo_sources(self):
        with zipfile.ZipFile(self.archive) as packed:
            names = packed.namelist()
        self.assertIn("ctr/__init__.py", names)
        solo = [name for name in names if name.startswith("ctr/tools/solo/")
                or pathlib.PurePosixPath(name).name in {"ctr_solo.py", "trim_core.py", "options-overlay.json"}]
        self.assertEqual(solo, [])

    def test_packed_world_keeps_ap_pie_presets(self):
        prefix = "ctr/solo/presets/"
        source = WORLD / "solo" / "presets"
        with zipfile.ZipFile(self.archive) as packed:
            index = packed.read(prefix + "presets.json")
            files = {"presets.json", *(p["file"] for p in json.loads(index)["presets"])}
            self.assertEqual({name.removeprefix(prefix) for name in packed.namelist()
                              if name.startswith(prefix)}, files)
            for name in files:
                self.assertEqual(packed.read(prefix + name), (source / name).read_bytes(), name)

    def test_packed_world_keeps_complete_track_fill_catalogue(self):
        prefix = "ctr/data/track_fill/"
        source = WORLD / "data" / "track_fill"
        index = json.loads((source / "index.json").read_bytes())
        files = {"index.json", *(f"{key}/{sha[:16]}.json" for key, pins in index.items() for sha in pins)}
        with zipfile.ZipFile(self.archive) as packed:
            self.assertEqual({name.removeprefix(prefix) for name in packed.namelist()
                              if name.startswith(prefix)}, files)
            for name in files:
                self.assertEqual(packed.read(prefix + name), (source / name).read_bytes(), name)

    @unittest.skipIf(os.environ.get("CTR_PACKED_APWORLD"), "Launcher rules run in the CTR pytest suite")
    def test_launcher_pack_rules_keep_shared_presets_and_omit_solo_tools(self):
        from Utils import read_apignore

        global_rules = read_apignore(WORLD.parents[1] / "data" / "GLOBAL.apignore")
        rules = global_rules + read_apignore(WORLD / ".apignore")
        files = {pathlib.PurePath(name).as_posix() for name in rules.match_tree_files(WORLD, negate=True)}
        self.assertIn("solo/presets/presets.json", files)
        self.assertFalse([name for name in files if name.startswith("tools/solo/")])
