"""Small local simulation of the changed-file tier rule."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("ctr_fuzz_tiers.py")
spec = importlib.util.spec_from_file_location("ctr_fuzz_tiers", SCRIPT)
tiers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiers)
guard_spec = importlib.util.spec_from_file_location("ctr_tag_guard", SCRIPT.with_name("ctr_tag_guard.py"))
guard = importlib.util.module_from_spec(guard_spec)
guard_spec.loader.exec_module(guard)


DEV = "refs/heads/dev/custom-pad-0.3.0"
MAIN = "refs/heads/main"


class ClassifyTests(unittest.TestCase):
    def test_safe_changes_skip_fuzz_only_on_pr(self):
        paths = [
            "worlds/ctr/solo/app.py",
            "worlds/ctr/docs/guide.txt",
            "worlds/ctr/test/test_seed.py",
            "README.md",
            "worlds/ctr/version.py",
            "worlds/ctr/archipelago.json",
            "worlds/ctr/datapackage_manifest.json",
        ]
        self.assertEqual(tiers.classify("pull_request", paths), "none")
        self.assertEqual(tiers.classify("push", paths, DEV), "pr")
        self.assertEqual(tiers.classify("push", paths, MAIN), "full")
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(tiers.classify("push", [path], DEV), "pr")
                self.assertEqual(tiers.classify("push", [path], "refs/heads/release/0.3.0"), "full")

    def test_generation_and_workflow_changes(self):
        for path in ("worlds/ctr/Rules.py", ".github/workflows/ctr-world.yml"):
            self.assertEqual(tiers.classify("pull_request", [path]), "pr")
            self.assertEqual(tiers.classify("push", [path], DEV), "pr")
            self.assertEqual(tiers.classify("push", [path], MAIN), "full")
            self.assertEqual(tiers.classify("push", [path], "refs/heads/ci/x"), "full")

    def test_full_fuzz_label(self):
        self.assertEqual(tiers.classify("pull_request", ["README.md"], labels=["full-fuzz"]), "full")
        self.assertEqual(tiers.classify("pull_request", ["worlds/ctr/Rules.py"], labels=["bug", "full-fuzz"]), "full")
        self.assertEqual(tiers.classify("pull_request", ["worlds/ctr/Rules.py"], labels=["bug"]), "pr")

    def test_mixed_and_empty_diffs_are_conservative(self):
        self.assertEqual(tiers.classify("pull_request", ["README.md", "worlds/ctr/Options.py"]), "pr")
        self.assertEqual(tiers.classify("pull_request", []), "pr")
        self.assertEqual(tiers.classify("push", [], DEV), "pr")
        self.assertEqual(tiers.classify("push", [], MAIN), "full")
        with self.assertRaises(ValueError):
            tiers.classify("push", [], "refs/tags/v0.3.0")

    def test_scheduled_and_manual_runs_are_full(self):
        for event in ("schedule", "workflow_dispatch"):
            self.assertEqual(tiers.classify(event, [], DEV), "full")
            self.assertEqual(tiers.classify(event, ["README.md"], DEV), "full")

    def test_matrix_selection(self):
        matrix_file = SCRIPT.parents[1] / "fuzz" / "ctr-world-matrix.yml"
        full = tiers.matrix_for_tier("full", matrix_file)["include"]
        pr = tiers.matrix_for_tier("pr", matrix_file)["include"]
        self.assertEqual(len(pr), 17)
        self.assertEqual({arm["check_name"] for arm in pr}, set(tiers.PR_ARMS))
        self.assertEqual(pr, [arm for arm in full if arm["check_name"] in tiers.PR_ARMS])
        self.assertEqual(set(tiers.PR_ARMS.values()), tiers.FAMILIES)
        self.assertTrue(any(arm.get("check_tracker") == "yes" for arm in pr))
        self.assertEqual(tiers.matrix_for_tier("none", matrix_file), {"include": []})


class TagGuardTests(unittest.TestCase):
    def jobs(self, names, conclusion="success"):
        return [{"name": name, "conclusion": conclusion} for name in names]

    def test_full_run_passes_and_pr_run_does_not(self):
        matrix_file = SCRIPT.parents[1] / "fuzz" / "ctr-world-matrix.yml"
        full = [arm["check_name"] for arm in tiers.matrix_for_tier("full", matrix_file)["include"]]
        base = ["pytest worlds/ctr", "pack ctr.apworld", "ctr-world summary"]
        self.assertEqual(guard.missing_jobs(self.jobs(base + [f"fuzz / {a}" for a in full]), full), set())
        pr_run = self.jobs(base + [f"fuzz / {a}" for a in tiers.PR_ARMS])
        self.assertEqual(len(guard.missing_jobs(pr_run, full)), len(full) - len(tiers.PR_ARMS))
        failed = self.jobs(base + [f"fuzz / {a}" for a in full[1:]]) + self.jobs([f"fuzz / {full[0]}"], "failure")
        self.assertEqual(guard.missing_jobs(failed, full), {f"fuzz / {full[0]}"})


if __name__ == "__main__":
    unittest.main()
