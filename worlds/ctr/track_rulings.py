"""Project-reviewed custom track revisions and their ruling sources."""
import json
import pkgutil
from contextvars import ContextVar
from functools import wraps

from .box_spots import lev_pin

FEATURE = "carried_track_rulings_v1"
REVIEWS = json.loads(pkgutil.get_data(__package__, "data/track_ruling_revisions.json"))
_carry = ContextVar("ctr_carry_track_rulings", default=False)


def _scoped(enabled):
    def decorate(function):
        @wraps(function)
        def call(subject, *args, **kwargs):
            token = _carry.set(enabled(subject))
            try:
                return function(subject, *args, **kwargs)
            finally:
                _carry.reset(token)
        return call
    return decorate


def enabled(plan):
    features = plan.get("required_features") if isinstance(plan, dict) else None
    return isinstance(features, list) and FEATURE in features


generation = _scoped(lambda world: True)
validation = _scoped(enabled)
regions = _scoped(lambda world: enabled(world.ctr_content_plan))


def source(package, pins):
    """Return the exact pin or the latest reviewed eligible pin for this family."""
    pin = lev_pin(package)
    if not pin or pin in pins or not _carry.get():
        return pin
    reviews = REVIEWS.get((package or {}).get("content_id"), ())
    if any(pin == reviewed for reviewed, _ in reviews):
        return pin
    return next((reviewed for reviewed, _ in reviews if reviewed in pins), pin)


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
    lev = lev_pin(package)
    exact = rulings.get((*key, package.get("revision"), lev))
    if exact is not None:
        return exact
    values = {row[-1]: value for row, value in rulings.items() if row[:-2] == key}
    inherited = source(package, values)
    return values[inherited] if inherited != lev else rulings.get(key)


def carried_sources(package):
    """Ruling families inherited by an unreviewed revision."""
    from . import content_capability, crate_exclusions, sanity
    from . import country_speedway, green_hill_raceway, royal_raceway, toasty_terrace

    content = package.get("content_id")
    pin = lev_pin(package)
    reviews = REVIEWS.get(content, ())
    if not pin or not reviews or any(pin == reviewed for reviewed, _ in reviews):
        return {}
    families = {
        "ordinary pickups": set(sanity.CATALOG) | {
            country_speedway.LEV_SHA256, green_hill_raceway.LEV_SHA256,
            royal_raceway.LEV_SHA256, toasty_terrace.LEV_SHA256},
        "crate exclusions": crate_exclusions.EXCLUSIONS,
        "finish": {digest for key, _, digest in content_capability.USF_FINISH_RULINGS if key == content and digest}
                  | {royal_raceway.LEV_SHA256, green_hill_raceway.LEV_SHA256},
    }
    result = {}
    for family, pins in families.items():
        reviewed = next(((revision, digest) for digest, revision in reviews if digest in pins), None)
        if reviewed:
            result[family] = reviewed
    latest = reviews[0]
    if any(row[0] == content for row in content_capability.LETTER_BOOST_RULINGS):
        result["letters"] = (latest[1], latest[0])
    if any(row[0] == content for row in sanity.object_rulings.RULINGS):
        result["objects"] = (latest[1], latest[0])
    if "finish" not in result and (content, None, None) in content_capability.USF_FINISH_RULINGS:
        result["finish"] = (latest[1], latest[0])
    return result
