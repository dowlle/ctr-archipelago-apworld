#!/usr/bin/env python3
"""Pack worlds/ctr into ctr.apworld the way a release does: members rooted at
ctr/, no tests, bytecode or tools. The shared YAML presets remain packaged
for AP-Pie's Builder. Prints the output path and SHA-256. Used by CI; a release
still follows RELEASING.md."""
import hashlib, os, sys, zipfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.dirname(HERE)
EXCLUDE_DIRS = {"test", "tests", "__pycache__", "tools", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo")


def main():
    # Validate before opening the archive. Keep the packer independent of
    # Archipelago dependencies so it also runs in the packaging job.
    sys.path.insert(0, WORLD)
    import box_spot_catalog

    world = Path(WORLD)
    read = lambda path: (world / path).read_bytes()
    paths = {path.relative_to(world).as_posix()
             for kind in ("retail", "custom") for path in (world / "data/box_spots" / kind).glob("*.json")}
    box_spot_catalog.load_catalog(read, box_spot_catalog.load_sources(read), paths=paths)
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "ctr.apworld")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(WORLD):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for fn in sorted(files):
                if fn.endswith(EXCLUDE_SUFFIX):
                    continue
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, os.path.dirname(WORLD))  # ctr/...
                zf.write(full, rel)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(f"{out}\t{digest}")


if __name__ == "__main__":
    main()
