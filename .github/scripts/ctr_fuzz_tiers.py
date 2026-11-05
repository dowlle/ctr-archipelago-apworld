"""Select CTR fuzz arms from the workflow's single matrix definition.

Tiers (documented in .github/fuzz/README.md):
- none: pull requests that change only safe paths. pytest and pack still run.
- pr:   the arms in PR_ARMS. Every other pull request and every dev push.
- full: every arm. Pushes to main and release branches, scheduled and manual
        runs, and pull requests with the full-fuzz label.
"""

import argparse
import json
from pathlib import Path

import yaml


FULL_LABEL = "full-fuzz"

# Each pr-tier arm, with the generation family it stands for. Every family in
# FAMILIES must have at least one arm here.
PR_ARMS = {
    "canonical-default": "default",
    "default": "default",
    "no-restrictive-starts": "default",
    "check-determinism": "determinism",
    "check-static-output": "determinism",
    "check-ut": "ut",
    "content-plan-bosses": "bosses",
    "content-plan-full": "content plan",
    "content-plan-vanilla": "content plan",
    "content-plan-132": "content plan",
    "gem-cups-7-random": "cups",
    "pads-all-ut": "pads",
}
FAMILIES = {"default", "content plan", "cups", "bosses", "pads", "ut", "determinism"}

VERSION_FILES = {
    "worlds/ctr/version.py",
    "worlds/ctr/archipelago.json",
    "worlds/ctr/datapackage_manifest.json",
}
SAFE_PREFIXES = ("worlds/ctr/solo/", "worlds/ctr/docs/", "worlds/ctr/test/")


def is_safe(path: str) -> bool:
    return path.startswith(SAFE_PREFIXES) or path.endswith(".md") or path in VERSION_FILES


def classify(event: str, paths: list[str], ref: str = "", labels: list[str] = ()) -> str:
    if event in ("schedule", "workflow_dispatch"):
        return "full"
    if event == "push":
        # A push never skips fuzz, whatever it changed.
        if ref == "refs/heads/main" or ref.startswith(("refs/heads/release/", "refs/heads/ci/")):
            return "full"
        if ref.startswith("refs/heads/dev/"):
            return "pr"
        raise ValueError(f"unsupported push ref: {ref}")
    if event != "pull_request":
        raise ValueError(f"unsupported event: {event}")
    if FULL_LABEL in labels:
        return "full"
    if paths and all(is_safe(path) for path in paths):
        return "none"
    return "pr"


def matrix_for_tier(tier: str, matrix_file: Path) -> dict:
    arms = yaml.safe_load(matrix_file.read_text())
    names = [arm["check_name"] for arm in arms]
    if len(names) != len(set(names)):
        raise ValueError("duplicate fuzz arm name")
    if not set(PR_ARMS) <= set(names):
        raise ValueError(f"missing PR arms: {sorted(set(PR_ARMS) - set(names))}")
    if set(PR_ARMS.values()) != FAMILIES:
        raise ValueError(f"pr tier families: {sorted(set(PR_ARMS.values()))}")
    if tier == "none":
        arms = []
    elif tier == "pr":
        arms = [arm for arm in arms if arm["check_name"] in PR_ARMS]
    elif tier != "full":
        raise ValueError(f"unsupported tier: {tier}")
    return {"include": arms}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", default="")
    parser.add_argument("--labels-json", default="[]")
    parser.add_argument("--matrix-file", type=Path, required=True)
    parser.add_argument("--paths-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = args.paths_file.read_bytes().split(b"\0") if args.paths_file else []
    paths = [path.decode() for path in paths if path]
    labels = [label["name"] for label in json.loads(args.labels_json or "null") or []]
    tier = classify(args.event, paths, args.ref, labels)
    matrix = matrix_for_tier(tier, args.matrix_file)
    with args.output.open("a") as output:
        print(f"tier={tier}", file=output)
        print(f"matrix={json.dumps(matrix, separators=(',', ':'))}", file=output)
    print(f"CTR fuzz tier: {tier}; {len(matrix['include'])} arms")


if __name__ == "__main__":
    main()
