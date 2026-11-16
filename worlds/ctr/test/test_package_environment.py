"""Release archives must not contain direct environment access."""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


class PackageEnvironmentTests(unittest.TestCase):
    def test_packed_python_has_no_environment_access(self):
        world = pathlib.Path(__file__).resolve().parents[1]
        forbidden = re.compile(r"\bos\s*\.\s*(environ|getenv|putenv|unsetenv)\b")
        with tempfile.TemporaryDirectory() as folder:
            archive = pathlib.Path(folder) / "ctr.apworld"
            subprocess.run([sys.executable, str(world / "tools" / "build_apworld.py"),
                            str(archive)], check=True, capture_output=True)
            findings = []
            with zipfile.ZipFile(archive) as packed:
                for name in packed.namelist():
                    if name.endswith(".py"):
                        for number, line in enumerate(packed.read(name).decode("utf-8").splitlines(), 1):
                            if forbidden.search(line):
                                findings.append(f"{name}:{number}: {line.strip()}")
            self.assertEqual(findings, [], "\n".join(findings))
