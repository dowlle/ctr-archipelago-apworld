"""Check the packed world's boundary with the standalone Solo runtime."""
import pathlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


class PackageEnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get("CTR_PACKED_APWORLD")
        if archive:
            cls.archive = pathlib.Path(archive)
            return
        world = pathlib.Path(__file__).resolve().parents[1]
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.archive = pathlib.Path(folder.name) / "ctr.apworld"
        subprocess.run([sys.executable, str(world / "tools" / "build_apworld.py"),
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
        solo = [name for name in names if "solo" in pathlib.PurePosixPath(name).parts
                or pathlib.PurePosixPath(name).name in {"ctr_solo.py", "trim_core.py", "options-overlay.json"}]
        self.assertEqual(solo, [])
