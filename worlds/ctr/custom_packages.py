"""Open admission of custom-track Package descriptors (#133 PR 2).

A content plan accepts any complete descriptor, not only revisions this build
was compiled with. A descriptor is untrusted player input, so every field is
closed and bounded here, and a malformed one is refused with a message that
names the field. The apworld cannot see the track's files: native checks the
bytes against the pins when it loads them, and refuses a package whose bytes
lack a capability the descriptor claims.

Descriptor (YAML `custom_tracks[]`, wire `content_plan.packages[]`):

    id            "package/<content_id>/<revision>", at most 64 bytes
    content_id    the registry track key: lowercase letters and digits in
                  hyphen-separated groups, such as "baby-t-park". A key with a
                  named id block uses that block; any other key uses a generic
                  Custom Track slot and its sanitized title (path B+).
    uuid          lowercase package UUID
    revision      the package version, such as "1.0.2" (quote it in YAML)
    display_name  title, 1 to 128 UTF-8 bytes, no control characters
    author        1 to 128 UTF-8 bytes, no control characters
    laps          authored race laps, 1 to 7
    capabilities  measured flags, each true or false: time_trial, arcade, relic,
                  ctr_tokens, wumpa; optional super_turbo_pads (#133 PR 4c),
                  whether the LEV has any super turbo pad trigger quad. Native
                  measures it and refuses a stated value the bytes disagree
                  with; an absent value counts as true in logic. Optional
                  weapon_crates (#133 PR 4e), a whole number 0 to 65536: how
                  many weapon crates (the "?" item crate) the LEV holds. Native
                  counts them and refuses a stated count the bytes disagree
                  with. It decides the track's Item Box checks on a named
                  block (min(count, 15)) and, at 0, that the track is no
                  Itemsanity route; absent means no Item Box checks and the
                  earlier Itemsanity routes. Optional checkpoints (#133
                  PR 6b), 1 to 255, the LEV's restart point count, and
                  ai_nav, whether it has AI navigation paths; native
                  measures both and refuses a mismatch. With both a track
                  may race a boss under Boss Track Shuffle.
    relic_targets optional; required exactly when relic is true. Sapphire, gold
                  and platinum times in ticks (960 per second), strictly faster
                  from sapphire to platinum, at most one hour
    files         exactly the LEV pin then the VRM pin: role, lowercase sha256,
                  bytes (LEV at most 16 MiB, VRM at most 4 MiB), format
                  ctr-lev / ctr-vrm, format_version 1
    evidence      0 to 16 informational rows; every hash must be one of the pins

Native (`ap/ap_content_plan_impl.hpp`) applies the same rules; the parity tool
`tools/test-content-plan-parity.py` compares the two on forged descriptors.
"""
import copy
import re

CAPABILITIES = ("time_trial", "arcade", "relic", "ctr_tokens", "wumpa")
#: Optional measured flags (#133 PR 4c). `super_turbo_pads`: the LEV has at
#: least one trigger quad whose terrain byte carries the super turbo pad step
#: flag (native COLL_STEP_TRIGGER_SUPER_TURBO_PAD). Such a track takes the Hot
#: Air Skyway finish rule (ruling 2026-10-17); an absent flag is treated as
#: true, the safe direction (content_capability.finish_boost).
#: `weapon_crates` (#133 PR 4e): the number of weapon crate instances
#: (PU_RANDOM_CRATE) in the LEV, a measured count rather than a flag. Item Box
#: checks on a named-block track take their seats from these crates
#: (content_item_boxes.py); native counts them on load and refuses a mismatch.
#: `checkpoints` and `ai_nav` (#133 PR 6b): the LEV's restart point count
#: (1 to 255) and whether it has AI navigation paths. Together they let the
#: track race a boss under Boss Track Shuffle (content_bosses); native
#: measures both on load and refuses a mismatch.
OPTIONAL_CAPABILITIES = ("super_turbo_pads", "weapon_crates", "checkpoints", "ai_nav")
CHECKPOINTS_MAX = 255
#: The instance-table ceiling native measures against
#: (native_custom_content_verify.c refuses a LEV with more instances).
WEAPON_CRATES_MAX = 65536
RELIC_TIERS = ("sapphire", "gold", "platinum")
REQUIRED = ("id", "content_id", "uuid", "revision", "display_name", "author", "laps",
            "capabilities", "files", "evidence")
OPTIONAL = ("relic_targets",)
#: The most descriptors one content plan may list; also the generic slot count.
MAX_PACKAGES = 32
MAX_LAPS = 7  # GameTracker.lapTime has seven entries
LEV_MAX_BYTES = 16 * 1024 * 1024  # native_custom_content_verify.c LEV_MAX
VRM_MAX_BYTES = 4 * 1024 * 1024  # native_custom_content_verify.c VRM_MAX
TICKS_PER_SECOND = 960
RELIC_TICKS_MAX = TICKS_PER_SECOND * 60 * 60
MAX_EVIDENCE = 16
INT32_MAX = 2**31 - 1

TRACK_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HEX64 = re.compile(r"[0-9a-f]{64}")
KEY = re.compile(r"[A-Za-z0-9_.:/+\-]+")
FILES = (("lev", "ctr-lev", LEV_MAX_BYTES), ("vrm", "ctr-vrm", VRM_MAX_BYTES))


class PackageError(ValueError):
    pass


def _fail(where, message):
    raise PackageError(f"{where}: {message}")


def _closed(value, required, optional, where):
    if type(value) is not dict:
        _fail(where, "must be a mapping")
    missing = [k for k in required if k not in value]
    extra = sorted(str(k) for k in value if k not in required and k not in optional)
    if missing:
        _fail(where, "missing " + ", ".join(missing))
    if extra:
        _fail(where, "unknown field " + ", ".join(extra))


def _integer(value, low, high, where):
    if type(value) is not int:
        _fail(where, f"must be a whole number from {low} to {high}")
    if not low <= value <= high:
        _fail(where, f"{value} is outside {low} to {high}")
    return value


def _utf8_size(value, where):
    try:
        return len(value.encode("utf-8"))
    except UnicodeError:
        _fail(where, "is not valid Unicode text")


def _string(value, pattern, max_bytes, where, hint=""):
    if type(value) is not str:
        _fail(where, "must be a text value" + (f" ({hint})" if hint else ""))
    if not value or _utf8_size(value, where) > max_bytes:
        _fail(where, f"must be 1 to {max_bytes} bytes")
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(where, "has characters this field does not allow" + (f" ({hint})" if hint else ""))
    return value


def _label(value, where):
    if type(value) is not str:
        _fail(where, "must be a text value")
    if not value or _utf8_size(value, where) > 128:
        _fail(where, "must be 1 to 128 UTF-8 bytes")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        _fail(where, "contains a control character")
    return value


def admit(descriptor, where="package"):
    """Return a canonical copy of one complete descriptor, or raise PackageError."""
    _closed(descriptor, REQUIRED, OPTIONAL, where)
    d = descriptor
    key = _string(d["content_id"], TRACK_KEY, 64, where + ".content_id",
                  "lowercase letters and digits in hyphen-separated groups, such as baby-t-park")
    revision = _string(d["revision"], REVISION, 64, where + ".revision", "quote versions such as \"1.0\"")
    expected_id = f"package/{key}/{revision}"
    if len(expected_id.encode()) > 64 or len(f"custom/{key}/{revision}".encode()) > 64:
        _fail(where, "content_id and revision together are too long (the package id must fit 64 bytes)")
    if d["id"] != expected_id:
        _fail(where + ".id", f"must be {expected_id!r}")
    _string(d["uuid"], UUID, 36, where + ".uuid", "a lowercase UUID")
    _label(d["display_name"], where + ".display_name")
    _label(d["author"], where + ".author")
    laps = _integer(d["laps"], 1, MAX_LAPS, where + ".laps")
    caps = d["capabilities"]
    _closed(caps, CAPABILITIES, OPTIONAL_CAPABILITIES, where + ".capabilities")
    for name in CAPABILITIES + tuple(n for n in OPTIONAL_CAPABILITIES if n in caps):
        if name == "weapon_crates":
            _integer(caps[name], 0, WEAPON_CRATES_MAX, f"{where}.capabilities.{name}")
        elif name == "checkpoints":
            _integer(caps[name], 1, CHECKPOINTS_MAX, f"{where}.capabilities.{name}")
        elif type(caps[name]) is not bool:
            _fail(f"{where}.capabilities.{name}", "must be true or false")
    if caps["relic"] != ("relic_targets" in d):
        _fail(where, "relic_targets is required exactly when capabilities.relic is true")
    out = dict(id=expected_id, content_id=key, uuid=d["uuid"], revision=revision,
               display_name=d["display_name"], author=d["author"], laps=laps,
               capabilities={name: caps[name] for name in CAPABILITIES + OPTIONAL_CAPABILITIES
                             if name in caps})
    if "relic_targets" in d:
        targets = d["relic_targets"]
        _closed(targets, RELIC_TIERS, (), where + ".relic_targets")
        ticks = [_integer(targets[t], 1, RELIC_TICKS_MAX, f"{where}.relic_targets.{t}") for t in RELIC_TIERS]
        if not ticks[0] > ticks[1] > ticks[2]:
            _fail(where + ".relic_targets", "sapphire must be slower than gold, and gold slower than platinum")
        out["relic_targets"] = dict(zip(RELIC_TIERS, ticks))
    files = d["files"]
    if type(files) is not list or len(files) != 2:
        _fail(where + ".files", "must list exactly two files, the LEV then the VRM")
    pins = []
    for i, ((role, fmt, limit), pin) in enumerate(zip(FILES, files)):
        at = f"{where}.files[{i}]"
        _closed(pin, ("role", "sha256", "bytes", "format", "format_version"), (), at)
        if pin["role"] != role:
            _fail(at + ".role", f"must be {role!r} (the LEV comes first, then the VRM)")
        _string(pin["sha256"], HEX64, 64, at + ".sha256", "64 lowercase hexadecimal characters")
        _integer(pin["bytes"], 1, limit, at + ".bytes")
        if pin["format"] != fmt:
            _fail(at + ".format", f"must be {fmt!r}")
        if type(pin["format_version"]) is not int or pin["format_version"] != 1:
            _fail(at + ".format_version", "must be 1")
        pins.append(dict(role=role, sha256=pin["sha256"], bytes=pin["bytes"], format=fmt, format_version=1))
    out["files"] = pins
    evidence = d["evidence"]
    if type(evidence) is not list or len(evidence) > MAX_EVIDENCE:
        _fail(where + ".evidence", f"must be a list of at most {MAX_EVIDENCE} rows")
    hashes = {p["sha256"] for p in pins}
    rows = []
    for i, row in enumerate(evidence):
        at = f"{where}.evidence[{i}]"
        _closed(row, ("capability", "file_hashes", "verifier", "revision", "level"), (), at)
        _string(row["capability"], KEY, 64, at + ".capability")
        refs = row["file_hashes"]
        if (type(refs) is not list or not 1 <= len(refs) <= 2 or len(set(map(str, refs))) != len(refs)
                or any(type(h) is not str or h not in hashes for h in refs)):
            _fail(at + ".file_hashes", "must list one or two distinct hashes of this package's pinned files")
        _string(row["verifier"], KEY, 64, at + ".verifier")
        _integer(row["revision"], 1, INT32_MAX, at + ".revision")
        if row["level"] not in ("structural", "runtime") or type(row["level"]) is not str:
            _fail(at + ".level", "must be structural or runtime")
        rows.append(copy.deepcopy(row))
    out["evidence"] = rows
    return out


def admit_all(raw, where="tracks.custom"):
    """Admit a whole descriptor list, sorted by package id; refuse duplicates."""
    if type(raw) is not list or len(raw) > MAX_PACKAGES:
        _fail(where, f"must be a list of at most {MAX_PACKAGES} complete package descriptors")
    result, seen = [], {}
    for i, descriptor in enumerate(raw):
        package = admit(descriptor, f"{where}[{i}]")
        for label, value in (("track key", package["content_id"]), ("package uuid", package["uuid"]),
                             ("LEV and VRM pair", (package["files"][0]["sha256"], package["files"][1]["sha256"]))):
            if (label, value) in seen:
                _fail(f"{where}[{i}]", f"repeats the {label} of {where}[{seen[label, value]}]; "
                      "list each track once, with one revision")
            seen[label, value] = i
        result.append(package)
    return sorted(result, key=lambda p: p["id"])
