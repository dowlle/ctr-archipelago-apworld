"""List the registry's current verified revisions that inherit CTR logic."""
import argparse
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def version_key(row):
    parts = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", row["revision"])
    return (tuple(map(int, parts.groups())) if parts else (-1, -1, -1), row["revision"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text())
    reviews = json.loads((DATA / "track_ruling_revisions.json").read_text())
    print("### Custom tracks using carried-over rulings")
    found = False
    for track in registry["tracks"]:
        candidates = [row for row in track["revisions"] if row.get("files", {}).get("lev", {}).get("sha256")]
        known = reviews.get(track["track_key"])
        if not known or not candidates:
            continue
        latest = max(candidates, key=version_key)
        pin = latest["files"]["lev"]["sha256"]
        if [pin, latest["revision"]] in known:
            continue
        if not found:
            print()
            print("| Track | Current revision | Latest reviewed revision |")
            print("| --- | --- | --- |")
        found = True
        print(f"| {track['track_key']} | {latest['revision']} | {known[0][1]} |")
    if not found:
        print("\nAll current verified revisions with project rulings have reviewed data.")


if __name__ == "__main__":
    main()
