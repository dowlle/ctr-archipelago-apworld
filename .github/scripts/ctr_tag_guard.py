"""Check that a commit has a green full-tier CTR world run.

A run counts when pytest, pack and every arm in ctr-world-matrix.yml
succeeded in it, so a pr-tier or none-tier run never satisfies the guard.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


REQUIRED_JOBS = {"pytest worlds/ctr", "pack ctr.apworld"}


def gh_pages(endpoint: str, key: str) -> list[dict]:
    out = subprocess.run(
        ["gh", "api", "--paginate", endpoint, "--jq", f".{key}[]"],
        check=True, capture_output=True, text=True,
    ).stdout
    return [json.loads(line) for line in out.splitlines() if line]


def missing_jobs(jobs: list[dict], arms: list[str]) -> set[str]:
    passed = {job["name"] for job in jobs if job["conclusion"] == "success"}
    wanted = REQUIRED_JOBS | {f"fuzz / {arm}" for arm in arms}
    return wanted - passed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--matrix-file", type=Path, required=True)
    args = parser.parse_args()
    arms = [arm["check_name"] for arm in yaml.safe_load(args.matrix_file.read_text())]
    runs = gh_pages(
        f"repos/{args.repo}/actions/workflows/ctr-world.yml/runs?head_sha={args.sha}&per_page=100",
        "workflow_runs",
    )
    for run in runs:
        jobs = gh_pages(f"repos/{args.repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100", "jobs")
        missing = missing_jobs(jobs, arms)
        print(f"run {run['id']} ({run['event']}, {run['conclusion']}): {len(missing)} required jobs not green")
        if not missing:
            print(f"Full tier green on {args.sha}: {run['html_url']}")
            return
    print(
        f"::error::No full-tier CTR world run passed on {args.sha} ({len(arms)} arms). "
        "Run the CTR world workflow by hand on this commit (Run workflow, or "
        "gh workflow run ctr-world.yml --ref <branch or tag>) and rerun this check once it is green."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
