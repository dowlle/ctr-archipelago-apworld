#!/usr/bin/env python3
"""Lay an overlay over a fuzz meta, line by line: each `key: value` line of the
overlay replaces the line of the same key and indent, or joins the end of the
meta when it has none. Comments and blank lines of the overlay are skipped.
usage: apply-overlay.py <meta> <overlay>"""
import re
import sys

meta_path, overlay_path = sys.argv[1:3]
with open(meta_path) as handle:
    meta = handle.read().split("\n")
with open(overlay_path) as handle:
    overlay = [line for line in handle.read().split("\n") if line.strip() and not line.lstrip().startswith("#")]
for line in overlay:
    key = re.match(r"\s*[^:]+:", line).group(0)
    found = [i for i, row in enumerate(meta) if row.startswith(key)]
    if found:
        meta[found[0]] = line
    else:
        meta.insert(len(meta) - 1 if meta[-1] == "" else len(meta), line)
with open(meta_path, "w") as handle:
    handle.write("\n".join(meta))
