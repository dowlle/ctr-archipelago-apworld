#!/usr/bin/env python3
"""Generate worlds/ctr/data/named_tracks.json from one pinned registry commit.

The public track registry (https://github.com/dowlle/ctr-track-registry) is the
record of which custom tracks have a named id block (#306). It assigns
`block_index` and `ap_name` when a track is promoted; this script only copies
them. It never invents, sorts or renumbers a block.

    python worlds/ctr/tools/build_named_tracks.py \
        --registry /path/to/ctr-track-registry --commit <full sha> [--check]

What it does:

1. Reads `registry.json`, `named_tracks.json`, `DIGEST.json` and `tracks/*.json`
   at exactly `--commit` with `git show`, so the working tree of the clone does
   not matter.
2. Recomputes the registry digest (the same formula as the registry's own
   tools/check_registry.py) and refuses a commit whose DIGEST.json or
   named_tracks.json carries a different one.
3. Takes only entries with `mint_status: mint` (the default). `reserved` keeps
   its block number unminted until the entry is confirmed; `builtin` maps to a
   block the apworld already has (Cortex Vortex). Neither is written here.
4. Refuses unless the registry's own named_tracks.json lists exactly those
   entries, so the two files of one commit cannot disagree.
5. Writes the apworld file with the registry repository, commit and digest for
   provenance. With --check it writes nothing and fails if the committed file
   differs from what the pinned commit produces.

Append only: a block already in the apworld file must come back unchanged
(test_named_tracks.py enforces the same rule against the published lock).
Standard library only; tools/ is not packed into ctr.apworld.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = "https://github.com/dowlle/ctr-track-registry"
WORLD = Path(__file__).resolve().parent.parent
OUTPUT = WORLD / "data" / "named_tracks.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MINT_STATUSES = ("mint", "reserved", "builtin")


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def read_commit(repo: Path, commit: str):
    """{relative path: bytes} for the files the build reads, at `commit`."""
    resolved = _git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    if resolved != commit:
        raise SystemExit(f"--commit must be a full 40-character sha; {commit!r} resolves to {resolved}")
    listing = _git(repo, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    wanted = ["registry.json", "named_tracks.json", "DIGEST.json"]
    wanted += sorted(p for p in listing if p.startswith("tracks/") and p.endswith(".json")
                     and p.count("/") == 1)
    return {rel: _git(repo, "show", f"{commit}:{rel}") for rel in wanted}


def digest_of(files) -> str:
    """The registry digest: registry.json plus every tracks/*.json, by name."""
    paths = ["registry.json"] + [p for p in files if p.startswith("tracks/")]
    h = hashlib.sha256()
    for rel in sorted(paths):
        h.update(rel.encode() + b"\0" + hashlib.sha256(files[rel]).hexdigest().encode() + b"\n")
    return h.hexdigest()


def mint_rows(registry):
    """The `mint` entries with a block, in block order, as apworld rows."""
    rows = []
    for t in registry.get("tracks", []):
        status = t.get("mint_status", "mint")
        if status not in MINT_STATUSES:
            raise SystemExit(f"{t.get('track_key')}: unknown mint_status {status!r}")
        if status != "mint" or t.get("block_index") is None:
            continue
        rows.append({
            "track_key": t["track_key"],
            "block_index": t["block_index"],
            "ap_name": t["ap_name"],
            "shipped_in": t.get("shipped_in"),
            "revisions": [r["content_id"] for r in t.get("revisions", []) if r.get("content_id")],
        })
    rows.sort(key=lambda r: r["block_index"])
    return rows


def build(repo: Path, commit: str):
    files = read_commit(repo, commit)
    registry = json.loads(files["registry.json"])
    named = json.loads(files["named_tracks.json"])
    digest_doc = json.loads(files["DIGEST.json"])
    digest = digest_of(files)
    if digest_doc.get("digest") != digest:
        raise SystemExit(f"DIGEST.json at {commit} does not match its registry ({digest})")
    if (named.get("registry") or {}).get("digest") != digest:
        raise SystemExit(f"named_tracks.json at {commit} carries a different digest")
    rows = mint_rows(registry)
    if named.get("format") != 1 or named.get("tracks") != rows:
        raise SystemExit(f"named_tracks.json at {commit} does not list exactly the mint entries")
    return {
        "format": 1,
        "registry": {"repository": REPOSITORY, "commit": commit, "digest": digest},
        "tracks": rows,
    }


def append_only_problems(previous, current):
    """A block in the previous apworld file must come back unchanged."""
    now = {r["track_key"]: r for r in current["tracks"]}
    problems = []
    for row in previous.get("tracks", []):
        same = now.get(row["track_key"])
        if same is None:
            problems.append(f"{row['track_key']}: block {row['block_index']} was dropped")
        elif (same["block_index"], same["ap_name"]) != (row["block_index"], row["ap_name"]):
            problems.append(f"{row['track_key']}: block_index or ap_name changed")
    return problems


def render(document) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", required=True, type=Path, help="a git clone of the registry")
    parser.add_argument("--commit", required=True, help="the full registry commit sha to pin")
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed file instead of writing it")
    args = parser.parse_args(argv)
    if not SHA_RE.match(args.commit):
        raise SystemExit("--commit must be a full 40-character lowercase sha")
    document = build(args.registry, args.commit)
    text = render(document)
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    problems = append_only_problems(previous, document)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != text:
            print(f"{OUTPUT} differs from registry commit {args.commit}", file=sys.stderr)
            return 1
        print(f"{OUTPUT} matches registry commit {args.commit} ({len(document['tracks'])} tracks)")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(document['tracks'])} tracks from {args.commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
