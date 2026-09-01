#!/usr/bin/env python3
"""Pack worlds/ctr into ctr.apworld the way a release does: members rooted at
ctr/, no test directory, no bytecode, no tooling. Prints the output path and
its sha256. Used by CI; a release still follows RELEASING.md."""
import hashlib, os, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.dirname(HERE)
EXCLUDE_DIRS = {"test", "tests", "__pycache__", "tools", ".pytest_cache"}
EXCLUDE_SUFFIX = (".pyc", ".pyo")


def main():
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
