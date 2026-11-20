"""Project-reviewed custom track revisions and their ruling sources."""
import json
import pkgutil
from contextvars import ContextVar
from functools import wraps

from .box_spots import lev_pin

FEATURE = "carried_track_rulings_v1"
# Rows are [LEV SHA-256, revision, first catalog version], latest reviewed first.
# The initial rows omit the version, which is 1. Keep prior rows in order.
REVIEWS = json.loads(pkgutil.get_data(__package__, "data/track_ruling_revisions.json"))
# Future scoped additions bump this on both sides and cite it as their "since".
# Version 0 is the original markerless lookup, before versioned ruling rows.
RULING_VERSION = 1
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
    record = plan.get("track_ruling_sources") if enabled(plan) else None
    if not isinstance(record, dict) or not isinstance(record.get("packages"), list):
        return 0, {}, False
    history = {}
    for row in record["packages"]:
        if (isinstance(row, dict) and isinstance(row.get("package_id"), str)
                and isinstance(row.get("reviews"), list)):
            history[row["package_id"]] = tuple(
                (r["revision"], r["lev_sha256"]) for r in row["reviews"]
                if isinstance(r, dict) and {"revision", "lev_sha256"} <= r.keys())
    return record.get("version", 0), history, record.get("pickup_limits") is True


generation = _scoped(lambda world: True)
validation = _scoped(_recorded)
regions = _scoped(lambda world: _recorded(world.ctr_content_plan))


def reviewed(package, version=None):
    """Ordered project review identities for a track key."""
    version = RULING_VERSION if version is None else version
    return tuple((row[1], row[0]) for row in REVIEWS.get((package or {}).get("content_id"), ())
                 if (row[2] if len(row) > 2 else 1) <= version)


def _reviews(package):
    history = _history.get()
    if history is not True:
        return history[1].get((package or {}).get("id"), ()) if history else ()
    return reviewed(package)


def revision_ref(package):
    return (package or {}).get("revision"), lev_pin(package)


def inherits(package):
    reviews = _reviews(package)
    return bool(reviews and revision_ref(package) not in reviews)


def source(package, pins):
    """Resolve rows originally keyed by LEV, including the recorded old source."""
    current = revision_ref(package)
    pin = current[1]
    reviews = _reviews(package)
    if not reviews or current in reviews:
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


def scoped_version():
    history = _history.get()
    if history is True:
        return RULING_VERSION
    return history[0] if history else 0


def pickup_limits_enabled():
    history = _history.get()
    return history is True or bool(history and history[2])


def scope_keys(row):
    """Scoped additions carry the catalog version that first enables them."""
    ref = scope(row)
    if not ref:
        return (), set()
    if type(row.get("since")) is not int or not 2 <= row["since"] <= 65535:
        raise ValueError("a scoped track ruling needs its catalog version")
    return (*ref, row["since"]), {"revision", "lev_sha256", "since"}


def ruled_value(package, rulings, *selector):
    """Scoped data wins, with old unscoped rulings as a track-wide default."""
    package = package or {}
    key = (package.get("content_id"), *selector)
    version = scoped_version()
    applicable = [(row, value) for row, value in rulings.items() if row[:-3] == key and row[-1] <= version]
    rows = {row[-3:-1]: value for row, value in sorted(applicable, key=lambda entry: entry[0][-1])}
    refs = rows.keys()
    source_ref = scoped_source(package, refs)
    return rows.get(source_ref, rulings.get(key))


def carried_sources(package):
    """Ruling families inherited by an unreviewed revision."""
    from . import content_capability, content_item_boxes, crate_exclusions, sanity
    from . import green_hill_raceway, royal_raceway

    content = package.get("content_id")
    current = revision_ref(package)
    pin = current[1]
    reviews = _reviews(package)
    if not pin or not reviews:
        return {}
    if current in reviews:
        return {}
    families = {
        "ordinary pickups": sanity.CATALOG.keys() | content_item_boxes.PICKUP_RULE_PINS,
        "AP box pickup ranks": content_item_boxes.PICKUP_RULE_PINS,
        "crate exclusions": crate_exclusions.EXCLUSIONS,
        "finish": content_capability.CARRY_FREE_FINISH_PINS | {royal_raceway.LEV_SHA256, green_hill_raceway.LEV_SHA256},
    }
    result = {}
    for family, pins in families.items():
        selected = source(package, pins)
        previous = next((ref for ref in reviews if ref[1] == selected), None)
        if previous:
            result[family] = previous
    finish_refs = content_capability.finish_ruling_rows(content)
    finish_source = scoped_source(package, finish_refs)
    if finish_source in finish_refs and finish_source != current:
        result["finish"] = finish_source
    latest = reviews[0]
    for family, rulings, key_size in (("letters", content_capability.LETTER_BOOST_RULINGS, 2),
                                      ("objects", sanity.object_rulings.RULINGS, 3)):
        keys = [row for row in rulings if row[0] == content]
        refs = {row[-3:-1] for row in keys if len(row) > key_size and row[-1] <= scoped_version()}
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
    limited = any(omitted_pickups(plan))
    if not limited and not (RULING_VERSION > 1 and plan["packages"]) and not any(plan_sources(plan)):
        return None
    record = {"version": RULING_VERSION, "packages": [
        {"package_id": package["id"], "reviews": [
            {"revision": rev, "lev_sha256": pin} for rev, pin in _reviews(package)]}
        for package in plan["packages"]]}
    if limited:
        record["pickup_limits"] = True
    return record


@validation
def spoiler_sources(plan):
    return list(plan_sources(plan))


def omitted_pickups(plan):
    """Ranges of added pickup ordinals absent from enabled check families."""
    from . import content_item_boxes, sanity

    if not pickup_limits_enabled():
        return
    packages = {pkg["id"]: pkg for pkg in plan["packages"]}
    record = plan.get("sanity", {})
    counts_by_track = {row["track_id"]: row["counts"] for row in record.get("tracks", ())}
    boxes = plan.get("item_boxes", {})
    entries = {pad["entry_id"] for pad in plan["pads"]}
    spots = content_item_boxes.spot_sets(boxes)
    fallback = {e["track_id"] for e in plan["entries"] if boxes and e["kind"] == "track"
                and e["id"] in entries and e["track_id"] not in spots}
    for track in plan["tracks"]:
        package = packages.get(track.get("package_id"))
        reviewed = sanity.reviewed_counts(package)
        if reviewed is None:
            continue
        tid = track["id"]
        counts = counts_by_track.get(tid, (0, 0, 0))
        wumpa = record.get("wumpasanity", 0)
        weapon = (content_item_boxes.crate_count(package) or 0) if tid in fallback else 0
        active = (max(weapon, counts[0] if record.get("itemboxsanity") else 0),
                  counts[1] if wumpa & 1 else 0, counts[2] if wumpa & 2 else 0)
        for name, previous, current in zip(sanity.SUFFIXES, reviewed, active):
            if current > previous:
                yield package["id"], name, previous + 1, current


@validation
def report_omitted_pickups(plan):
    return list(omitted_pickups(plan))


def valid_sources(plan, packages):
    """Every pinned identity belongs to this track's review history."""
    record = plan.get("track_ruling_sources")
    if enabled(plan) != bool(record):
        return False
    if not record:
        return True
    if not 1 <= record["version"] <= RULING_VERSION:
        return False
    if "pickup_limits" in record and (record["pickup_limits"] is not True or not any(omitted_pickups(plan))):
        return False
    records = record["packages"]
    ids = [row["package_id"] for row in records]
    if ids != sorted(packages):
        return False
    for row in records:
        package = packages[row["package_id"]]
        known = reviewed(package, record["version"])
        refs = tuple((r["revision"], r["lev_sha256"]) for r in row["reviews"])
        if refs != known:
            return False
    return True
