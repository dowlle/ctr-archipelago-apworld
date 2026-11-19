"""Origin catalogue, pinned from the public track registry."""

import json
import pkgutil

from .named_tracks import MINTED_ORIGIN_GLYPHS

FEATURE = "origin_letters_v1"
DEFAULT = "CTR"

# Source: https://github.com/dowlle/ctr-track-registry/blob/d812a83aee1097b06e34e0eeefd3f979159a957e/origins.json
_CATALOGUE = json.loads(pkgutil.get_data(__package__, "data/origins.json"))


def letters_for_package(package):
    """Stage 1 requires models in the exact LEV the seed pins."""
    row = _CATALOGUE["tracks"].get(package["content_id"])
    if not row or row["review"] != "verified" or row["relation"] not in ("port", "remake"):
        return DEFAULT
    game = _CATALOGUE["games"][row["origin_game"]]
    code = game["code"]
    lev = package["files"][0]["sha256"]
    if (game["racing_game"] and row.get("own_letter_models", {}).get(lev) == code
            and set(code) <= set(DEFAULT + MINTED_ORIGIN_GLYPHS)):
        return code
    return DEFAULT
