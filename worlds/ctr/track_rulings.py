"""Project-reviewed custom track revisions and their ruling sources."""
import json
import pkgutil
from contextvars import ContextVar
from functools import wraps

from .box_spots import lev_pin

FEATURE = "carried_track_rulings_v1"
# Rows are [LEV SHA-256, revision], latest reviewed first. Preserve the order in
# the paired native table. Append a reviewed revision through a paired update.
REVIEWS = json.loads(pkgutil.get_data(__package__, "data/track_ruling_revisions.json"))
_history = ContextVar("ctr_track_ruling_history", default=None)


def _scoped(history):
    def decorate(function):
        @wraps(function)
        def call(subject, *args, **kwargs):
            token = _history.set(history(subject))
            try:
                return function(subject, *args, **kwargs)
            finally:
                _history.reset(token)
        return call
    return decorate


def enabled(plan):
    features = plan.get("required_features") if isinstance(plan, dict) else None
    return isinstance(features, list) and FEATURE in features


def _recorded(plan):
    """Read the optional room record. Shape and references are validated separately."""
    if not enabled(plan) or not isinstance(plan.get("track_ruling_sources"), list):
        return {}
    return {row["package_id"]: tuple((r["revision"], r["lev_sha256"]) for r in row["reviews"]
                                     if isinstance(r, dict) and {"revision", "lev_sha256"} <= r.keys())
            for row in plan["track_ruling_sources"]
            if isinstance(row, dict) and isinstance(row.get("package_id"), str)
            and isinstance(row.get("reviews"), list)}


generation = _scoped(lambda world: True)
validation = _scoped(_recorded)
regions = _scoped(lambda world: _recorded(world.ctr_content_plan))


def reviewed(package):
    """Ordered project review identities for a track key."""
    return tuple((revision, pin) for pin, revision in REVIEWS.get((package or {}).get("content_id"), ()))


def _reviews(package):
    history = _history.get()
    if history is not True:
        return (history or {}).get((package or {}).get("id"), ())
    reviews = reviewed(package)
    if not reviews:
        return ()
    pin = lev_pin(package)
    if not any(pin == old for _, old in reviews):
        # Exact asset data predates the index, including local imports and
        # renamed copies. Preserve its previous geometry-based generation.
        from . import crate_exclusions, sanity
        if pin in crate_exclusions.EXCLUSIONS or pin in sanity.REVIEWED_PICKUP_PINS:
            return ()
    return reviews


def revision_ref(package):
    return (package or {}).get("revision"), lev_pin(package)


def source(package, pins):
    """Resolve rows originally keyed by LEV, including the recorded old source."""
    current = revision_ref(package)
    pin = current[1]
    reviews = _reviews(package)
    if not reviews or current in reviews:
        return pin
    if pin in pins and any(pin == old for _, old in reviews):
        return pin
    return next((old for _, old in reviews if old in pins), None)


def scoped_source(package, refs):
    """Resolve a revision-and-LEV pair for scoped ranks."""
    current = revision_ref(package)
    reviews = _reviews(package)
    if not reviews or current in reviews or (_history.get() is True and current in refs):
        return current
    return next((ref for ref in reviews if ref in refs), (None, None))


def scope(row):
    """Validate the common optional revision and LEV selectors in a ruling row."""
    if "revision" not in row and "lev_sha256" not in row:
        return ()
    revision, pin = row.get("revision"), row.get("lev_sha256")
    if (not isinstance(revision, str) or not revision or not isinstance(pin, str)
            or len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin)):
        raise ValueError("a scoped track ruling needs both a revision and a lowercase LEV SHA-256")
    return revision, pin


def ruled_value(package, rulings, *selector):
    """Scoped data wins, with old unscoped rulings as a track-wide default."""
    package = package or {}
    key = (package.get("content_id"), *selector)
    refs = {row[-2:] for row in rulings if row[:-2] == key}
    source_ref = scoped_source(package, refs)
    return rulings.get((*key, *source_ref), rulings.get(key))


def carried_sources(package):
    """Ruling families inherited by an unreviewed revision."""
    from . import content_capability, content_item_boxes, crate_exclusions, sanity
    from . import green_hill_raceway, royal_raceway

    content = package.get("content_id")
    current = revision_ref(package)
    pin = current[1]
    reviews = _reviews(package)
    if not pin or not reviews or current in reviews:
        return {}
    families = {
        "ordinary pickups": sanity.CATALOG.keys() | content_item_boxes.PICKUP_RULE_PINS,
        "AP box pickup ranks": content_item_boxes.PICKUP_RULE_PINS,
        "crate exclusions": crate_exclusions.EXCLUSIONS,
        "finish": {royal_raceway.LEV_SHA256, green_hill_raceway.LEV_SHA256},
    }
    result = {}
    for family, pins in families.items():
        selected = source(package, pins)
        if selected != pin:
            previous = next((ref for ref in reviews if ref[1] == selected), None)
            if previous:
                result[family] = previous
    finish_refs = {(revision, digest) for key, revision, digest in content_capability.USF_FINISH_RULINGS
                   if key == content and digest}
    finish_source = scoped_source(package, finish_refs)
    if finish_source in finish_refs and finish_source != current:
        result["finish"] = finish_source
    latest = reviews[0]
    for family, rulings, key_size in (("letters", content_capability.LETTER_BOOST_RULINGS, 2),
                                      ("objects", sanity.object_rulings.RULINGS, 3)):
        keys = [row for row in rulings if row[0] == content]
        refs = {row[-2:] for row in keys if len(row) > key_size}
        selected = scoped_source(package, refs)
        if selected in refs and selected != current:
            result[family] = selected
        elif any(len(row) == key_size for row in keys):
            result[family] = latest
    if "finish" not in result and (content, None, None) in content_capability.USF_FINISH_RULINGS:
        result["finish"] = latest
    return result


def plan_sources(plan):
    """List the inherited sources used by this room's selected check families."""
    boost = plan.get("capability", {}).get("boost_mode", 0)
    sanity = {row["track_id"] for row in plan.get("sanity", {}).get("tracks", ())}
    boxes = plan.get("item_boxes", {})
    excluded = {row["track_id"] for row in boxes.get("crate_exclusions", ())}
    pickup_ranks = set(boxes.get("pickup_rules", ()))
    letters = {check["owner"] for check in plan["checks"] if check["kind"] in ("ctr", "letter")}
    tracks = {track.get("package_id"): track["id"] for track in plan["tracks"] if track["origin"] == "custom"}
    for package in plan["packages"]:
        tid = tracks.get(package["id"])
        used = {
            "AP box pickup ranks": tid in pickup_ranks,
            "crate exclusions": tid in excluded or tid in sanity,
            "ordinary pickups": tid in sanity,
            "objects": tid in sanity,
            "finish": boost,
            "letters": boost and tid in letters,
        }
        for family, (revision, digest) in carried_sources(package).items():
            if used[family]:
                yield package["id"], family, revision, digest


def wire_sources(plan):
    """Save the ordered review identities that produced this room's logic."""
    used = {pid for pid, _, _, _ in plan_sources(plan)}
    return [{"package_id": package["id"], "reviews": [
        {"revision": rev, "lev_sha256": pin} for rev, pin in reviewed(package)]}
        for package in plan["packages"] if package["id"] in used]


@validation
def spoiler_sources(plan):
    return list(plan_sources(plan))


def valid_sources(plan, packages):
    """Every pinned identity belongs to this track's review history."""
    records = plan.get("track_ruling_sources", ())
    if enabled(plan) != bool(records):
        return False
    ids = [row["package_id"] for row in records]
    if ids != sorted(set(ids)) or not set(ids) <= packages.keys():
        return False
    for row in records:
        package = packages[row["package_id"]]
        known = reviewed(package)
        refs = [(r["revision"], r["lev_sha256"]) for r in row["reviews"]]
        known_subset = [ref for ref in known if ref in refs]
        if refs != known_subset or revision_ref(package) in refs:
            return False
    return True
