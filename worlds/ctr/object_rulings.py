"""Project-owned custom pickup rulings, separate from package measurements."""
import json
import pkgutil


def _load():
    raw = json.loads(pkgutil.get_data(__package__, "data/object_rulings.json"))
    if raw["version"] != 1:
        raise ValueError("object_rulings.json: version must be 1")
    out = {}
    for row in raw["rulings"]:
        key = (row.get("content_id"), row.get("kind"), row.get("ordinal"))
        if (set(row) != {"content_id", "kind", "ordinal", "hard_rank", "blue_fire_rank", "ruling"}
                or type(key[0]) is not str or not key[0]
                or key[1] not in ("weapon_crate", "wumpa_crate", "wumpa_fruit")
                or type(key[2]) is not int or not 1 <= key[2] <= 65536
                or type(row["hard_rank"]) is not int or row["hard_rank"] not in (1, 2)
                or type(row["blue_fire_rank"]) is not int or row["blue_fire_rank"] != 3
                or type(row["ruling"]) is not str or "2026-" not in row["ruling"] or key in out):
            raise ValueError("object_rulings.json: invalid or duplicate object ruling")
        out[key] = row
    return out


RULINGS = _load()


def rank(track, package, kind, ordinal, capability):
    """None removes the object, zero preserves its existing rule.

    Easy/medium require Blue Fire and hard uses the ruled floor. Removal is
    independent of the boost pack; the caller omits rank terms with boost off.
    """
    if track["origin"] != "custom":
        return 0
    row = RULINGS.get(((package or {}).get("content_id"), kind, ordinal))
    if row is None:
        return 0
    if (capability or {}).get("logic_difficulty", 2) == 2:
        return row["hard_rank"]
    return row["blue_fire_rank"] if capability["boost_blue_fire"] else None
