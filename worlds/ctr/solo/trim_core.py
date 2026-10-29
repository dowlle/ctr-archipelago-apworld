#!/usr/bin/env python3
"""Copy the part of an Archipelago source tree the solo runtime needs (#89).

Usage: trim_core.py <archipelago source> <destination>

The solo runtime generates and hosts CTR rooms only, so it needs the core
modules, a few data files, rule_builder and the Generic world. No other world,
no WebHost, no Kivy client. Both the native release packaging and the apworld
tests use this one allowlist, so they cannot drift.
"""
from __future__ import annotations

import os
import shutil
import sys

# Top-level modules: every core .py file except clients, adjusters and tools
# that pull GUI or game-specific dependencies and are never imported here.
SKIP_TOP_LEVEL = {"setup.py", "kvui.py", "Launcher.py", "LttPAdjuster.py", "OoTAdjuster.py",
                  "WebHost.py", "OptionsCreator.py"}
SKIP_SUFFIX_TOP_LEVEL = ("Client.py",)
KEEP_TOP_LEVEL = {"CommonClient.py"}  # imported by core modules
WORLD_FILES = ("__init__.py", "AutoWorld.py", "Files.py", "LauncherComponents.py")
TREES = ("rule_builder", os.path.join("worlds", "generic"))
DATA_SUFFIXES = (".yaml", ".json", ".txt")
EXTRA_FILES = ("LICENSE",)


def plan(source: str) -> list[str]:
    """Relative paths (files) to copy, sorted."""
    files: list[str] = []
    for name in os.listdir(source):
        full = os.path.join(source, name)
        if not os.path.isfile(full) or not name.endswith(".py"):
            continue
        if name in KEEP_TOP_LEVEL or not (name in SKIP_TOP_LEVEL or name.endswith(SKIP_SUFFIX_TOP_LEVEL)):
            files.append(name)
    for name in WORLD_FILES:
        files.append(os.path.join("worlds", name))
    for tree in TREES:
        for root, dirs, names in os.walk(os.path.join(source, tree)):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "test", "docs"))
            for name in names:
                if name.endswith((".pyc", ".pyo")):
                    continue
                files.append(os.path.relpath(os.path.join(root, name), source))
    data = os.path.join(source, "data")
    for name in os.listdir(data):
        if os.path.isfile(os.path.join(data, name)) and name.endswith(DATA_SUFFIXES):
            files.append(os.path.join("data", name))
    files.extend(EXTRA_FILES)
    missing = [f for f in files if not os.path.isfile(os.path.join(source, f))]
    if missing:
        raise SystemExit(f"Archipelago source is missing: {missing}")
    return sorted(set(files))


def copy(source: str, destination: str) -> list[str]:
    files = plan(source)
    for rel in files:
        target = os.path.join(destination, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(source, rel), target)
    # Empty folders Archipelago expects to exist.
    os.makedirs(os.path.join(destination, "custom_worlds"), exist_ok=True)
    return files


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    for path in copy(sys.argv[1], sys.argv[2]):
        print(path)
