"""Drift guard for the committed datapackage manifest (issue #177 groundwork).

`worlds/ctr/datapackage_manifest.json` is a committed snapshot of the live
world's datapackage, built by `worlds.ctr.tools.gen_datapackage_manifest`. The
tool ships its own `--check` mode, but that mode is deliberately NOT wired
into CI: turning it on would make every future item/location append a build
failure until the manifest is regenerated and re-reviewed, which is exactly
the premature per-PR freeze issue #177 forbids before the name-freeze itself.

This test is the cheaper, always-on half of that guard: it fails a normal
`pytest` run the moment `build_manifest()` disagrees with the committed file,
so the manifest cannot rot silently between now and the freeze session, while
still leaving the decision of WHEN to regenerate and re-commit it to a human.
"""
import json
import unittest

from worlds.ctr.tools.gen_datapackage_manifest import MANIFEST_PATH, build_manifest


class TestDatapackageManifestDrift(unittest.TestCase):
    def test_committed_manifest_matches_the_registered_world(self) -> None:
        committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        current = build_manifest()
        self.assertEqual(
            committed, current,
            f"{MANIFEST_PATH} is stale relative to the registered world. Regenerate with "
            "`python -m worlds.ctr.tools.gen_datapackage_manifest` and review the diff before "
            "committing -- every name it adds must already be signed off on the frozen manifest "
            "in issue #177.",
        )
