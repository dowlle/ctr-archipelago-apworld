"""Generate the datapackage name manifest (groundwork for issue #177).

Emits every item + location name this world's datapackage currently registers,
each with its numeric id, plus the datapackage checksum
(`worlds.AutoWorld.WebWorld.get_data_package_data`) that would ship if nothing
else changed.

The manifest reads the LIVE registered world class rather than re-deriving ids
from the raw data files, so it can never disagree with what the server
actually sends a client. Its job is to turn "does the 0.2.0 superset review
cover every name" into a diff against a committed file instead of a
conversation held in people's heads -- see #177, whose whole point is that the
manifest is signed off BEFORE any of those names are written into a module.

This run only builds the tool and commits the CURRENT (v0.1.5) manifest as the
baseline. No 0.2.0 candidate name (character unlocks, per-character stats,
progressive boost, item boxes, lettersanity, itemsanity, ...) is mentioned or
minted here; that is #177's review, not this script's.

The #150 dossier separately asked for a static datapackage manifest to be
published from 0.1.5 onward, which the 0.1.5 release shipped without. This
tool's output is exactly that page's data (item/location names, ids, checksum,
groups) -- `--check` mode below could feed a "does the published doc match
what shipped" CI gate the same way it feeds the 0.2.0 bump review.

Run as:
    python -m worlds.ctr.tools.gen_datapackage_manifest          # (re)write the manifest
    python -m worlds.ctr.tools.gen_datapackage_manifest --check  # diff against the committed file, exit 1 on mismatch
"""
import argparse
import json
import pathlib
import sys

MANIFEST_PATH = pathlib.Path(__file__).parent.parent / "datapackage_manifest.json"
ARCHIPELAGO_JSON_PATH = pathlib.Path(__file__).parent.parent / "archipelago.json"


def build_manifest() -> dict:
    """Return the current datapackage manifest for the CTR world."""
    import worlds.ctr  # noqa: F401  (import registers the world with AutoWorldRegister)
    from worlds.AutoWorld import AutoWorldRegister

    world_type = AutoWorldRegister.world_types["Crash Team Racing"]
    package = world_type.get_data_package_data()
    world_version = json.loads(ARCHIPELAGO_JSON_PATH.read_text())["world_version"]

    return {
        "game": world_type.game,
        "world_version": world_version,
        "checksum": package["checksum"],
        "item_name_to_id": dict(sorted(package["item_name_to_id"].items())),
        "location_name_to_id": dict(sorted(package["location_name_to_id"].items())),
        "item_name_groups": package["item_name_groups"],
        "location_name_groups": package["location_name_groups"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check", action="store_true",
        help="compare the live world against the committed manifest instead of writing it; "
             "exit non-zero on any difference",
    )
    args = parser.parse_args(argv)

    current = build_manifest()

    if args.check:
        if not MANIFEST_PATH.exists():
            sys.stderr.write(f"{MANIFEST_PATH} does not exist -- run without --check to create it.\n")
            return 1
        committed = json.loads(MANIFEST_PATH.read_text())
        if committed != current:
            sys.stderr.write(
                f"{MANIFEST_PATH} is stale relative to the registered world.\n"
                "Regenerate with `python -m worlds.ctr.tools.gen_datapackage_manifest` and review the "
                "diff before committing -- every name it adds must already be signed off on the frozen "
                "manifest in issue #177.\n"
            )
            return 1
        sys.stdout.write(f"{MANIFEST_PATH} matches the registered world.\n")
        return 0

    MANIFEST_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.write(f"wrote {MANIFEST_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
