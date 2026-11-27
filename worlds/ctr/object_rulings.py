"""Project-owned custom pickup rulings, separate from package measurements."""
import json
import pkgutil

from . import track_rulings
from .destinations import canonical_track_key


def _load():
    raw = json.loads(pkgutil.get_data(__package__, "data/object_rulings.json"))
    if raw["version"] != 1:
        raise ValueError("object_rulings.json: version must be 1")
    out = {}
    for row in raw["rulings"]:
        pin = row.get("lev_sha256")
        scope, scope_fields = track_rulings.scope_keys(row) if "revision" in row else ((), set())
        key = (row.get("content_id"), row.get("kind"), row.get("ordinal"), *scope)
        if (set(row) != {"content_id", "kind", "ordinal", "hard_rank", "blue_fire_rank", "ruling",
                         "lev_sha256"} | scope_fields
                or type(key[0]) is not str or not key[0]
                or key[1] not in ("weapon_crate", "wumpa_crate", "wumpa_fruit")
                or type(key[2]) is not int or not 1 <= key[2] <= 65536
                or type(pin) is not str or len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin)
                or type(row["hard_rank"]) is not int or type(row["blue_fire_rank"]) is not int
                or (row["hard_rank"], row["blue_fire_rank"]) not in (((0, 0), (1, 3), (2, 3))
                                                                   if scope else ((1, 3), (2, 3)))
                or type(row["ruling"]) is not str or "2026-" not in row["ruling"] or key in out):
            raise ValueError("object_rulings.json: invalid or duplicate object ruling")
        out[key] = row
    return out


RULINGS = _load()


def _selection(package, kind, ordinal, *, legacy=False):
    raw = package["content_id"]
    road = canonical_track_key(raw)
    version = track_rulings.scoped_version()
    pinned, scoped_keys = {}, []
    # Prefer a historical key's own row when both keys name this exact source.
    for content in dict.fromkeys((road, raw)):
        key = (content, kind, ordinal)
        row = RULINGS.get(key)
        if row is not None:
            pinned[row["lev_sha256"]] = row
        scoped_keys.extend(row_key for row_key in RULINGS if row_key[:-3] == key and row_key[-1] <= version)
    # The latest applicable version wins. The raw key breaks ties.
    scoped = {key[-3:-1]: RULINGS[key] for key in sorted(scoped_keys, key=lambda key: (key[-1], key[0] == raw))}
    current = track_rulings.revision_ref(package)
    source = current if current in scoped else track_rulings.scoped_source(package, scoped, pins=pinned)
    row = scoped.get(source) or pinned.get(source[1])
    if row is None and ((legacy and version == 0) or 0 < version < 4):
        row = RULINGS.get((raw, kind, ordinal))
    return row, source


def _selectors(package):
    raw = (package or {}).get("content_id")
    if isinstance(raw, str):
        keys = (raw, canonical_track_key(raw))
        return {(row[1], row[2]) for row in RULINGS if row[0] in keys}
    return set()


def applies_to(package, enabled):
    return any(kind in enabled and _selection(package, kind, ordinal)[0] is not None
               for kind, ordinal in _selectors(package))


def carried_source(package):
    current = track_rulings.revision_ref(package)
    for kind, ordinal in sorted(_selectors(package)):
        row, source = _selection(package, kind, ordinal)
        if row is not None and source[0] is not None and source != current:
            return source
    return None


def rank(track, package, kind, ordinal, capability, *, legacy=False):
    """None removes the object, zero preserves its existing rule.

    Easy/medium require Blue Fire and hard uses the ruled floor. Removal is
    independent of the boost pack; the caller omits rank terms with boost off.
    """
    key = (package or {}).get("content_id")
    if track["origin"] != "custom" or not isinstance(key, str):
        return 0
    row, _ = _selection(package, kind, ordinal, legacy=legacy)
    if row is None or row["hard_rank"] == 0:
        return 0
    if (capability or {}).get("logic_difficulty", 2) == 2:
        return row["hard_rank"]
    return row["blue_fire_rank"] if capability["boost_blue_fire"] else None


def parse_rule(text):
    """A spot's `rule_of` text `<kind>:<ordinal>` as (kind, ordinal), or None."""
    kind, sep, ordinal = text.partition(":") if isinstance(text, str) else ("", "", "")
    if not sep or not ordinal.isascii() or not ordinal.isdigit() or str(int(ordinal)) != ordinal:
        return None
    return (kind, int(ordinal)) if kind in ("weapon_crate", "wumpa_crate", "wumpa_fruit") else None


def has_ruling(content_id, kind, ordinal):
    """Whether a track key has a ruling for this object (any revision)."""
    return (kind, ordinal) in _selectors({"content_id": content_id})
