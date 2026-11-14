"""Who made a custom track, from data the apworld already holds (A4-71).

A track author cup (cup_checks.CUP_TRACK_AUTHORS) prefers its author's tracks.
A track's authors are the union of:

* the custom package's `author` label, split on ",", "&", "/", "+" and the
  word "and", so a label naming two people counts for both;
* the `credits` of its registry entry, keyed by the package's content id (the
  registry track key), from data/track_credits.json. That file is written by
  tools/build_named_tracks.py from the same pinned registry commit as
  data/named_tracks.json, so generation never contacts the registry.

Cortex Vortex (origin `cortex_vortex`) is looked up under its registry key
`cortex-vortex`. Retail tracks have no author here. Names are compared in
lower case.
"""
import json
import pkgutil
import re
from typing import FrozenSet, Mapping, Optional

CORTEX_VORTEX_KEY = "cortex-vortex"
_SPLIT = re.compile(r"\s*(?:,|&|/|\+|\band\b)\s*", re.IGNORECASE)


def _load():
    document = json.loads(pkgutil.get_data(__package__, "data/track_credits.json").decode("utf-8"))
    return {key: tuple(names) for key, names in document["credits"].items()}


#: registry track key -> credit names, at the pinned registry commit.
REGISTRY_CREDITS = _load()


def split_author(label: str):
    """The names in one package `author` label."""
    return [part.strip() for part in _SPLIT.split(label or "") if part.strip()]


def authors_of(track: Mapping, package: Optional[Mapping] = None) -> FrozenSet[str]:
    """Lower-case author names of one leg track record."""
    origin = track.get("origin")
    if origin == "cortex_vortex":
        key, label = CORTEX_VORTEX_KEY, ""
    elif origin == "custom" and package is not None:
        key, label = package.get("content_id"), package.get("author", "")
    else:
        return frozenset()
    names = list(REGISTRY_CREDITS.get(key, ())) + split_author(label)
    return frozenset(name.strip().lower() for name in names)
