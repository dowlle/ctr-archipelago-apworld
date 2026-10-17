"""Experimental content-plan generation, independent of legacy cup displacement.

The executable profile builds standalone track entries with their Trophy Race,
CTR Challenge and Relic Race modes (#133 PR 3), their podium rungs, Reach 10
Wumpa and C/T/R letter checks (#133 PR 3b), and Crystal Challenge entries.
Unsupported content and check families fail explicitly while their native
consumers are developed. This is an internal integration path, not completion
of the full rewrite.
"""
import copy
import itertools
import json
import pkgutil

from BaseClasses import Region, Location
from Options import OptionError

from . import (content_item_pool, characters, destinations, named_tracks, podium, sphere0_guard, traps,
               warp_pad_rules, wumpa_family)
from .custom_check_namespace import custom_check_code, custom_check_name
from .custom_track_titles import is_sanitized, seed_titles
from .custom_tracks import BABY_T_PARK_PROFILES
from . import arena_content, custom_packages
from .Locations import CTR_LOCATION_IDS
from .warp_pad_logic import HUB_STATIC

SCHEMA = 18
MANUAL_FEATURE = "manual_pad_requirements_v1"
#: Track modes (#133 PR 3). A plan whose track entries are all Trophy-only keeps
#: the earlier wire exactly; any other entry declares this feature.
MODE_FEATURE = "track_modes_v1"
MODES = ("trophy", "ctr", "relic")
#: Second-stage gate record of a physical pad: `stage2:<physical LevelID>`.
STAGE2_PREFIX = "stage2:"
#: Highest count a drawn second-stage gate asks for. The legacy generator caps
#: its stage-2 counts the same way (warp_pad_logic._STAGE2_COUNT_CEILING).
STAGE2_COUNT_CEILING = 4
RELIC_TIERS = ("Sapphire", "Gold", "Platinum")
#: (route award, named-block key, location suffix) of every check a mode owns.
#: Codes come from the frozen names: retail `<Track>: <suffix>`, named blocks by
#: key, generic slots `Custom Track N: <suffix>`.
MODE_CHECKS = {
    "trophy": (("win", "trophy", "Trophy Race"),),
    "ctr": (("win_letters", "ctr_token", "CTR Token Challenge"),),
    "relic": tuple((tier.lower(), "relic_" + tier.lower(), tier + " Time Trial") for tier in RELIC_TIERS),
}
#: Per-track check families (#133 PR 3b), each with its own feature: podium
#: rungs on a Trophy Race, Reach 10 Wumpa on a Trophy Race or CTR Challenge,
#: and the C, T and R letters of a CTR Challenge (Lettersanity). The plan's
#: optional `track_checks` record carries the seed's settings; it is absent
#: when all three are off, so such a plan keeps its earlier wire exactly.
PODIUM_FEATURE = "podium_rungs_v1"
WUMPA_FEATURE = "wumpa_checks_v1"
LETTER_FEATURE = "lettersanity_v1"
#: Rung keys in podium.SLOT_ORDER and their frozen location suffixes.
RUNG_SUFFIX = {key: suffix for key, _offset, suffix in named_tracks.LOCATION_OFFSETS
               if key in podium.SLOT_ORDER}
#: The rung sets a seed can create: podium.created_rung_keys over its four
#: sub-toggles, without the empty set (podium checks off).
RUNG_SETS = tuple(sorted({tuple(podium.created_rung_keys(*bits))
                          for bits in itertools.product((False, True), repeat=4)} - {()}))
LETTERS = ("C", "T", "R")
LETTER_KEYS = ("letter_c", "letter_t", "letter_r")
WUMPA_SUFFIX = "Reach 10 Wumpa"
#: Race modes in which ten fruit can be reached. A Relic Race has no Wumpa
#: route, as on the legacy trial tracks (wumpa_checks.py).
WUMPA_MODES = ("trophy", "ctr")
WUMPA_GLOBAL_NAME = "Wumpa: Reach 10 Wumpa"
#: Aggregate manual rule -> the counted item names it sums, in wire order.
#: Native holds the same three lists; the parity fixtures compare them.
SUM_FAMILIES = {"AnyCtrToken": warp_pad_rules.TOKENS, "AnyRelic": warp_pad_rules.RELICS,
                "AnyGem": warp_pad_rules.GEMS}
PADS = json.loads(pkgutil.get_data(__package__, "data/warp_pad_ids.json"))["pads"]
RETAIL = {row["level_id"]: name.removesuffix(" Warp Pad") for name, row in PADS.items()
          if row["kind"] in ("race", "trial")}
ITEM_BY_CODE = {code: name for name, code in content_item_pool.ITEMS.items()}
LOCATION_BY_CODE = {code: name for name, code in CTR_LOCATION_IDS.items()}


def error(message):
    raise OptionError("CTR content plan: " + message)


def closed(value, keys, path):
    if not isinstance(value, dict) or set(value) - set(keys):
        error(f"{path} must be a mapping with only {', '.join(keys)}.")
    return value


def package_descriptor(profile):
    """Complete descriptor of a Baby T Park revision this build has measured.

    Open admission (#133 PR 2) accepts any complete descriptor; these two stay
    as known-good examples for tests, fixtures and the fuzz meta file. The
    flags were measured on the pinned bytes (8 spawns, AI paths, 35
    checkpoints, C/T/R letters, 8 fruit crates); relic is false because the
    package has no relic target times."""
    revision = profile["package_version"]
    sizes = (2579256, 458808) if revision == "1.0.0" else (2558168, 458808)
    files = [dict(role=role, sha256=profile[role + "_sha256"], bytes=size,
                  format="ctr-" + role, format_version=1)
             for role, size in zip(("lev", "vrm"), sizes)]
    return dict(id="package/baby-t-park/" + revision, content_id="baby-t-park",
                uuid=profile["package_uuid"], revision=revision, display_name="Baby T Park",
                author="Lockheart", laps=profile["laps"],
                capabilities=dict(time_trial=True, arcade=True, relic=False, ctr_tokens=True, wumpa=True),
                files=files,
                evidence=[dict(capability="trophy", file_hashes=[f["sha256"] for f in files],
                               verifier="ctr-managed-profile", revision=1, level="structural")])


PACKAGES = tuple(package_descriptor(p) for p in BABY_T_PARK_PROFILES)
#: Retail tracks race their authored three laps.
RETAIL_LAPS = 3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def resolve_packages(raw, where="tracks.custom"):
    """Admit any complete descriptor (#133 PR 2); bytes are checked by native."""
    try:
        return custom_packages.admit_all(raw, where)
    except custom_packages.PackageError as exc:
        error(f"{exc}. Export the package descriptor again from the Custom Content page "
              "or the AP-Pie track picker; legacy Gem Cup placement descriptors are not this format.")


def pad_registry():
    result = []
    for name, row in PADS.items():
        title = name.removesuffix(" Warp Pad")
        physical = row["level_id"]
        keys = HUB_STATIC[title][0][1] if HUB_STATIC[title] else 0
        hub = 25 if row["kind"] in ("trial", "cup") else 26 + keys
        result.append((physical, hub, keys))
    return sorted(result)


def _zero_count(value, path):
    if type(value) is int and value == 0:
        return
    if isinstance(value, dict) and set(value) == {"min", "max"} and all(type(v) is int and v == 0 for v in value.values()):
        return
    error(f"{path}: cups and crystals are not implemented in this experimental standalone profile; "
          "use an explicit zero count. The requested settings were not changed.")


PAD_KEY_BY_LEVEL_ID = {d.level_id: d.key for d in destinations.DESTINATIONS}


def manual_rules(options):
    """{physical LevelID -> rule} from warp_pad_rules, or {} when unused.
    Shape, names and the unlock-mode conflicts are checked here; the supply
    check needs the item ledger and runs in manual_requirements."""
    raw = options.warp_pad_rules.value
    if not raw:
        return {}
    rules = warp_pad_rules.parse(raw)
    mode = int(options.warppad_unlock_requirements.value)
    if mode == 0:
        error("warp_pad_rules needs warppad_unlock_requirements randomized or "
              "random_without_4_keys; with vanilla, remove the rules or change the mode.")
    for pad, rule in rules.items():
        if mode == 2 and rule is not None and rule[0] == "Key" and rule[1] >= 4:
            error(f"warp_pad_rules {pad!r}: Key x {rule[1]} is not allowed with "
                  "random_without_4_keys.")
    ids = {d.key: d.level_id for d in destinations.DESTINATIONS}
    return {ids[pad]: rule for pad, rule in rules.items()}


def starting_counts(options):
    """Items the slot starts with: from-pool starts plus additional starts."""
    held = {}
    for source in (options.start_inventory_from_pool.value, options.start_inventory.value):
        for name, count in source.items():
            held[name] = held.get(name, 0) + count
    return held


def rule_met(rule, held):
    if rule is None:
        return True
    item, count = rule
    members = SUM_FAMILIES.get(item)
    return (sum(held.get(m, 0) for m in members) if members else held.get(item, 0)) >= count


def manual_requirements(manual, rows):
    """One requirement record per named non-free pad, checked against the base
    supply (`requirement_ceiling`). A concrete item is a count record; an Any
    rule is a sum record over the items the seed has as base items."""
    by_name = {row.name: row for row in rows}
    out = []
    for physical, rule in sorted(manual.items()):
        if rule is None:
            continue
        pad, (item, count) = PAD_KEY_BY_LEVEL_ID[physical], rule
        names = SUM_FAMILIES.get(item)
        eligible = [n for n in (names or (item,)) if by_name[n].requirement_ceiling > 0]
        have = sum(by_name[n].requirement_ceiling for n in eligible)
        if not eligible:
            error(f"warp_pad_rules {pad!r}: {item} x {count}, but this seed has no "
                  f"{item if not names else 'items of that kind'}.")
        if count > have:
            error(f"warp_pad_rules {pad!r}: {item} x {count}, but the base item pool "
                  f"holds only {have}.")
        predicate = (dict(op="sum", items=[by_name[n].item for n in eligible], count=count)
                     if names else dict(op="count", item=by_name[item].item, count=count))
        out.append(dict(id=f"manual:{physical}", predicate=predicate))
    return out


def required_features(requirements, entries=(), checks=(), settings=None):
    manual = any(r["id"].startswith("manual:") for r in requirements)
    settings = settings or {}
    return (["content_plan_v1"] + ([MANUAL_FEATURE] if manual else [])
            + (["crystal_entries_v1"] if any(e['kind']=='crystal' for e in entries) else [])
            + (["crystal_pickups_v1"] if any(c['kind']=='crystal_pickup' for c in checks) else [])
            + (["arcade_crystals_v1"] if any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in entries) else [])
            + ([MODE_FEATURE] if any(e["kind"] == "track" and e["modes"] != ["trophy"] for e in entries) else [])
            + ([PODIUM_FEATURE] if "podium_rungs" in settings else [])
            + ([WUMPA_FEATURE] if "wumpa" in settings else [])
            + ([LETTER_FEATURE] if "lettersanity" in settings else []))


def family_settings(options):
    """The plan's `track_checks` record from the seed's options; {} when the
    podium rungs, Wumpa checks and Lettersanity are all off (#133 PR 3b).

    `podium_rungs` lists the created rung keys in podium.SLOT_ORDER (the
    sub-toggles decide them, as on the legacy path); `wumpa` is `global` or
    `per_track`; `lettersanity` is the mode 1 to 3, with `letters_per_track`
    only for the two location-bearing modes."""
    out = {}
    rungs = podium.created_rung_keys_from_options(options)
    if rungs:
        out["podium_rungs"] = [key for key in podium.SLOT_ORDER if key in rungs]
    wumpa = int(options.wumpa_check.value)
    if wumpa:
        out["wumpa"] = "global" if wumpa == 1 else "per_track"
    letters = int(options.lettersanity.value)
    if letters:
        out["lettersanity"] = letters
        if letters in (1, 2):
            out["letters_per_track"] = int(options.letters_per_track.value)
    return out


def check_settings(settings):
    """Shape and values of a plan's `track_checks` record."""
    if (not isinstance(settings, dict) or not settings
            or set(settings) - {"podium_rungs", "wumpa", "lettersanity", "letters_per_track"}):
        error("track_checks must be a nonempty mapping of podium_rungs, wumpa, lettersanity "
              "and letters_per_track.")
    if "podium_rungs" in settings and tuple(settings["podium_rungs"]) not in RUNG_SETS:
        error("track_checks.podium_rungs is not a rung set the podium options create.")
    if "wumpa" in settings and settings["wumpa"] not in ("global", "per_track"):
        error("track_checks.wumpa must be global or per_track.")
    mode = settings.get("lettersanity")
    if "lettersanity" in settings and (type(mode) is not int or mode not in (1, 2, 3)):
        error("track_checks.lettersanity must be 1, 2 or 3.")
    count = settings.get("letters_per_track")
    if ("letters_per_track" in settings) != (mode in (1, 2)) or (
            "letters_per_track" in settings and (type(count) is not int or count not in (1, 2, 3))):
        error("track_checks.letters_per_track (1 to 3) belongs to Lettersanity modes 1 and 2 only.")
    return settings


def supported_modes(origin, package=None):
    """Modes a track can run, in MODES order (#133 PR 3).

    Retail tracks run all three. A custom package's measured capability flags
    decide: Trophy needs an eight-kart grid with AI paths (`arcade`), the CTR
    Challenge also needs the C, T and R letters (`ctr_tokens`), and the Relic
    Race needs time crates with target times (`relic`) on a timed lap graph
    (`time_trial`). Native measures the same flags on the bytes before a
    package is admitted (ap_content_capability.h)."""
    if origin == "retail":
        return list(MODES)
    caps = package["capabilities"]
    out = []
    if caps["arcade"]:
        out.append("trophy")
        if caps["ctr_tokens"]:
            out.append("ctr")
    if caps["relic"] and caps["time_trial"]:
        out.append("relic")
    return out


def track_location(track, key, suffix):
    """(location name, code) of one of a track's checks: the named block's
    offset `key`, else the frozen `<retail track>: <suffix>` or
    `Custom Track N: <suffix>` name."""
    if track["origin"] == "custom" and "named_block" in track:
        code = named_tracks.location_code(track["named_block"], key)
        return LOCATION_BY_CODE[code], code
    stem = (f"Custom Track {track['custom_slot']}" if track["origin"] == "custom"
            else track["display_name"])
    name = f"{stem}: {suffix}"
    return name, CTR_LOCATION_IDS[name]


def mode_checks(track, mode):
    """[(award, location name, code, display suffix)] a track's mode owns."""
    out = []
    for award, key, suffix in MODE_CHECKS[mode]:
        name, code = track_location(track, key, suffix)
        out.append((award, name, code, suffix))
    return out


def letter_suffix(index):
    return f"Letter {LETTERS[index]}"


def letter_code(track, index):
    return track_location(track, LETTER_KEYS[index], letter_suffix(index))[1]


def letter_item(track, index):
    """(item name, code) of a track's Letter C, T or R item: the named block's
    item offset, the generic `Letter C (Custom Track N)` family, or the retail
    `Letter C (<track>)` item."""
    if track["origin"] == "custom" and "named_block" in track:
        return (named_tracks.item_name(track["room_title"], LETTER_KEYS[index]),
                named_tracks.item_code(track["named_block"], LETTER_KEYS[index]))
    if track["origin"] == "custom":
        return (custom_check_name("letter_item", track["custom_slot"], index),
                custom_check_code("letter_item", track["custom_slot"], index))
    name = f"Letter {LETTERS[index]} ({track['display_name']})"
    return name, content_item_pool.ITEMS[name]


def wumpa_modes(track, package=None):
    """The track's modes, in canonical order, that can reach ten fruit: its
    Trophy Race and CTR Challenge. A custom package needs its measured `wumpa`
    capability (custom_packages.CAPABILITIES)."""
    if track["origin"] == "custom" and not (package and package["capabilities"]["wumpa"]):
        return []
    return [m for m in MODES if m in WUMPA_MODES and m in track["modes"]]


def letter_layout(track, settings, location_letters=()):
    """(location letters, item letters) of a track's CTR Challenge, as letter
    indices. Lettersanity mode 1 has letter checks only, mode 2 checks and
    items for the same letters_per_track letters, mode 3 all three items and
    no checks. `location_letters` are the letters drawn for modes 1 and 2."""
    mode = settings.get("lettersanity", 0)
    if not mode or "ctr" not in track["modes"]:
        return (), ()
    if mode == 3:
        return (), (0, 1, 2)
    letters = tuple(sorted(location_letters))
    return letters, (letters if mode == 2 else ())


def plan_letters(plan, track, settings):
    """letter_layout for a track of an existing plan, reading which letters
    have checks from the plan itself."""
    present = {check["location"] for check in plan["checks"]}
    return letter_layout(track, settings, [i for i in range(3) if letter_code(track, i) in present])


def letter_requirements(plan):
    """{location code: (letter item names)} the Lettersanity items gate
    (Rules.add_lettersanity_rules on the legacy path): a mode 2 letter check
    needs its own item, and a CTR Token Challenge needs every letter item of
    its track (mode 2 the selected letters, mode 3 all three)."""
    settings = plan.get("track_checks", {})
    if settings.get("lettersanity", 0) not in (2, 3):
        return {}
    out = {}
    for track in plan["tracks"]:
        locations, items = plan_letters(plan, track, settings)
        if not items:
            continue
        names = tuple(letter_item(track, i)[0] for i in items)
        out[mode_checks(track, "ctr")[0][2]] = names
        for i in locations:
            out[letter_code(track, i)] = (letter_item(track, i)[0],)
    return out


def plan_letter_items(plan):
    """{item code: name} of every letter item the plan pools."""
    settings = plan.get("track_checks", {})
    out = {}
    for track in plan["tracks"]:
        for i in plan_letters(plan, track, settings)[1]:
            name, code = letter_item(track, i)
            out[code] = name
    return out


def room_title(track):
    """What the room and Universal Tracker call a track's checks."""
    return track.get("room_title", track["display_name"]) if track["origin"] == "custom" else track["display_name"]


def route(entry_id, mode, pad_id, award):
    return dict(entry_id=entry_id, mode=mode, leg_id=None, encounter_id=None, own_pad_id=pad_id, award=award)


def track_checks(track, entry_id, pad_id, modes, settings=None, letters=(), package=None):
    """Every check of a standalone track entry, in its entry's mode order.

    Each mode's own checks come first; a Trophy Race adds the seed's podium
    rungs, a CTR Challenge its letter checks (`letters`, Lettersanity modes 1
    and 2). A per-track Reach 10 Wumpa check comes last, with one route per
    mode that can reach ten fruit (#133 PR 3b)."""
    title = room_title(track)
    settings = settings or {}

    def check(code, kind, suffix, routes):
        return dict(location=code, owner=track["id"], kind=kind, display_name=f"{title}: {suffix}",
                    routes=[route(entry_id, mode, pad_id, award) for mode, award in routes])
    out = []
    for mode in modes:
        for award, _name, code, suffix in mode_checks(track, mode):
            out.append(check(code, mode, suffix, [(mode, award)]))
        if mode == "trophy":
            for key in settings.get("podium_rungs", ()):
                out.append(check(track_location(track, key, RUNG_SUFFIX[key])[1], "podium",
                                 RUNG_SUFFIX[key], [("trophy", key)]))
        if mode == "ctr":
            for index in letter_layout(track, settings, letters)[0]:
                out.append(check(letter_code(track, index), "letter", letter_suffix(index),
                                 [("ctr", LETTER_KEYS[index])]))
    if settings.get("wumpa") == "per_track":
        reach = wumpa_modes(track, package)
        if reach:
            out.append(check(track_location(track, "wumpa", WUMPA_SUFFIX)[1], "wumpa", WUMPA_SUFFIX,
                             [(mode, "wumpa") for mode in reach]))
    return out


def global_wumpa_check(routes):
    """The one `Wumpa: Reach 10 Wumpa` check of `wumpa: global`, with a route
    for every Trophy Race and CTR Challenge that can reach ten fruit, in
    physical pad order, then mode order. None when no route exists."""
    if not routes:
        return None
    ordered = sorted(routes, key=lambda r: (int(r[1].split(":")[1]), MODES.index(r[2])))
    return dict(location=CTR_LOCATION_IDS[WUMPA_GLOBAL_NAME], owner="global", kind="wumpa",
                display_name=WUMPA_GLOBAL_NAME,
                routes=[route(entry_id, mode, pad_id, "wumpa") for entry_id, pad_id, mode in ordered])


def mode_gates(modes, first_requirement, stages, physical):
    """The pad's mode gates: the first mode uses the entrance requirement; with
    two stages the others share `stage2:<physical>`, otherwise they use the
    entrance requirement too (Wayfinder ticket 16, 2026-09-22)."""
    gates = [dict(mode=modes[0], stage=1, requirement_id=first_requirement)]
    for mode in modes[1:]:
        gates.append(dict(mode=mode, stage=2, requirement_id=f"{STAGE2_PREFIX}{physical}") if stages == "two"
                     else dict(mode=mode, stage=1, requirement_id=first_requirement))
    return gates


def draw_stage2(world, rows):
    """One second-stage gate predicate from the base supply.

    Concrete counted items with a base copy, plus an Any family when two or
    more of its items have one; never Keys, which already gate the hubs. The
    count is 1 up to STAGE2_COUNT_CEILING and never above the base supply
    (`requirement_ceiling`), so a gate cannot ask for items the seed lacks.
    Returns None when the seed has no eligible base item."""
    by_name = {row.name: row for row in rows}
    candidates = [(name, (name,)) for name in content_item_pool.COUNTED_NAMES
                  if name != "Key" and by_name[name].requirement_ceiling > 0]
    for family, names in SUM_FAMILIES.items():
        eligible = tuple(n for n in names if by_name[n].requirement_ceiling > 0)
        if len(eligible) >= 2:
            candidates.append((family, eligible))
    if not candidates:
        return None
    label, names = world.random.choice(candidates)
    supply = sum(by_name[n].requirement_ceiling for n in names)
    count = world.random.randint(1, min(STAGE2_COUNT_CEILING, supply))
    if label in SUM_FAMILIES:
        return dict(op="sum", items=[by_name[n].item for n in names], count=count)
    return dict(op="count", item=by_name[label].item, count=count)


def crystal_selection(world, raw):
    o=world.options
    pool=raw.get('pool','all')
    allowed=list(arena_content.ARENAS)
    if pool!='all' and (not isinstance(pool,list) or any(type(i) is not int or i not in allowed for i in pool) or len(set(pool))!=len(pool)):
        error('crystals.pool must be all or distinct arena LevelIDs 18 through 24.')
    eligible=(list(arena_content.ARENAS) if pool=='all' else list(pool))
    if not o.include_battle_arenas.value:
        return [],0
    if not o.include_arcade_arenas.value:
        if pool!='all' and any(i in arena_content.ARCADE for i in eligible):
            error('an arcade arena in crystals.pool requires include_arcade_arenas.')
        eligible=[i for i in eligible if i not in arena_content.ARCADE]
    count=raw.get('count',0)
    if isinstance(count,dict) and set(count)=={'min','max'}:
        low,high=count['min'],count['max']
        if type(low) is not int or type(high) is not int or not 0<=low<=high<=len(eligible):
            error('crystals.count range exceeds the eligible arena pool.')
        count=low if low==high else world.random.randint(low,high)
    if type(count) is not int or not 0<=count<=len(eligible):
        error('crystals.count must fit the eligible arena pool.')
    return eligible,count


def track_modes(raw_tracks):
    """(global modes, overrides) from content_pool.tracks, shape-checked.

    `modes` is a nonempty list of distinct modes (default all three). An
    override maps a logical track id to a nonempty narrower list; it never
    adds a mode the global list leaves out."""
    modes = raw_tracks.get("modes", list(MODES))
    if (not isinstance(modes, list) or not modes or any(m not in MODES for m in modes)
            or len(set(modes)) != len(modes)):
        error("tracks.modes must be a nonempty list of distinct modes from trophy, ctr and relic.")
    overrides = raw_tracks.get("overrides", {})
    if not isinstance(overrides, dict):
        error("tracks.overrides must map logical track ids to mode lists.")
    for track_id, narrowed in overrides.items():
        if (not isinstance(narrowed, list) or not narrowed or any(m not in MODES for m in narrowed)
                or len(set(narrowed)) != len(narrowed)):
            error(f"tracks.overrides[{track_id!r}] must be a nonempty list of distinct modes.")
        if set(narrowed) - set(modes):
            error(f"tracks.overrides[{track_id!r}] adds {', '.join(m for m in narrowed if m not in modes)}, "
                  "which tracks.modes leaves out; an override can only narrow the selected modes.")
    return modes, overrides


def generate(world):
    o = world.options
    raw = closed(o.content_pool.value, ("preset", "tracks", "cups", "crystals", "bosses", "required_entries"), "content_pool")
    if raw.get("preset", "mixed") != "mixed":
        error("the experimental standalone profile currently requires preset: mixed.")
    tracks = closed(raw.get("tracks", {}), ("retail", "custom", "cortex_vortex", "modes", "overrides"), "tracks")
    selected_modes, overrides = track_modes(tracks)
    if tracks.get("cortex_vortex", False) is not False:
        error("Cortex Vortex content-plan routes are not implemented yet.")
    _zero_count(closed(raw.get("cups", {}), ("count",), "cups").get("count"), "cups.count")
    crystals = closed(raw.get("crystals", {}), ("pool", "count"), "crystals")
    arena_pool, arena_count = crystal_selection(world, crystals)
    bosses = closed(raw.get("bosses", {}), ("enabled",), "bosses")
    if bosses.get("enabled") is not False:
        error("the experimental profile needs explicit bosses: {enabled: false}; encounter routes are pending.")
    layout = closed(o.pad_layout.value, ("placement", "stages", "mode_order", "merge_trophy_ctr"), "pad_layout")
    stages = layout.get("stages", "two")
    mode_order = layout.get("mode_order", "fixed")
    if layout.get("placement", "shuffle") != "shuffle":
        error("pad_layout.placement: only shuffle is built yet; vanilla placement is pending.")
    if stages not in ("single", "two"):
        error("pad_layout.stages must be single or two.")
    if mode_order not in ("fixed", "per_seed", "per_pad"):
        error("pad_layout.mode_order must be fixed, per_seed or per_pad.")
    if layout.get("merge_trophy_ctr", False) is not False:
        error("pad_layout.merge_trophy_ctr: the merged Trophy/CTR race is not built yet; it comes in a "
              "separate change after the track modes. Set merge_trophy_ctr: false. No content was changed.")
    if o.oxide_goal.value != 3 or o.bosses_required_goal.value != 0 or o.gems_required_goal.value == 0:
        error("this profile needs Oxide disabled, no Boss goal, and a positive Gem goal.")
    pending = ("character_unlocks", "racer_locked_pads", "progressive_boost", "progressive_stats",
               "itemsanity", "box_locations", "hit_character", "progressive_starting_wumpa",
               "turbo_grant", "tizi_helper", "relic_perfect_checks", "boss_track_shuffle")
    enabled = [name for name in pending if getattr(o, name).value]
    if enabled:
        error("these selected packs/checks do not have content-plan routes yet: " + ", ".join(enabled) + ".")
    # The content-plan wire carries death_link only, so native applies the
    # legacy send coupling. An explicit send list would be dropped silently.
    if set(o.death_link_send.value) != {"follow_death_link"}:
        error("an explicit death_link_send list has no content-plan route yet; leave it unset.")
    if o.custom_tracks.value or o.cortex_vortex_track.value:
        error("legacy custom_tracks/cortex_vortex_track cannot be mixed with content_pool.")
    if o.plando_items.value or o.item_links.value:
        error("plando and item-link accounting are not validated for this experimental profile yet.")
    retail = tracks.get("retail", "all")
    if retail == "all":
        retail = sorted(RETAIL)
    if (not isinstance(retail, list) or any(type(i) is not int or i not in RETAIL for i in retail)
            or len(set(retail)) != len(retail)):
        error("tracks.retail must be all or a list of distinct retail engine track IDs 0..17.")
    packages = resolve_packages(tracks.get("custom", []))
    # Field mapping (ruling of 2026-10-13): the named-block identity is the registry
    # `track_key`. The package descriptor carries it in its existing wire field
    # `content_id` (same string, e.g. "baby-t-park"); the wire name is kept so
    # schema 1 plans and the native registry do not change. Lookups below are
    # therefore by track_key.
    # #306: a package whose track key has a named block uses that block's
    # ids and frozen name; any other package keeps its generic slot ids and is
    # shown under its sanitized, clash-suffixed room title (B+). Room titles
    # are assigned once the seed's tracks are chosen (below), so validate can
    # recompute them from the plan alone.
    # (track record without its modes, package or None, named-block fields).
    pool = [(dict(id=f"retail:{i}", origin="retail", retail_id=i, display_name=RETAIL[i], laps=RETAIL_LAPS),
             None, {}) for i in sorted(retail)]
    for slot, package in enumerate(packages, 1):
        block = destinations.named_track(package["content_id"])
        pool.append((dict(id="custom/" + package["content_id"] + "/" + package["revision"],
                          origin="custom", package_id=package["id"], custom_slot=slot,
                          display_name=package["display_name"], laps=package["laps"]),
                     package, dict(named_block=block.block_index, room_title=block.ap_name) if block else {}))
    package_by_id = {p["id"]: p for p in packages}
    unknown = sorted(set(overrides) - {track["id"] for track, _package, _addressing in pool})
    if unknown:
        error(f"tracks.overrides names {', '.join(unknown)}, which is not a selected retail or custom track.")
    candidates = []
    for track, package, addressing in pool:
        wanted = overrides.get(track["id"], selected_modes)
        supported = supported_modes(track["origin"], package)
        if track["id"] in overrides and set(wanted) - set(supported):
            error(f"tracks.overrides[{track['id']!r}] asks for "
                  f"{', '.join(m for m in wanted if m not in supported)}, which this track cannot run "
                  "(its package capabilities do not allow it). No content was changed.")
        modes = [m for m in MODES if m in wanted and m in supported]
        if not modes:
            if package is not None:
                error(f"custom track {package['id']} can run none of the selected modes "
                      f"({', '.join(selected_modes)}): Trophy needs arcade, CTR needs arcade and ctr_tokens, "
                      "Relic needs relic and time_trial. Remove it from tracks.custom or select a mode it "
                      "supports. No content was changed.")
            continue
        # Field order as the Trophy-only profile wrote it, so its wire is unchanged.
        candidates.append(dict(track, modes=modes, capabilities=list(modes), field_size=8, **addressing))
    required = raw.get("required_entries", [])
    arena_candidates=[dict(id=f'arena:{lid}', arena_id=lid, display_name=arena_content.ARENAS[lid]) for lid in arena_pool]
    ids = {t["id"] for t in candidates+arena_candidates}
    if (not isinstance(required, list) or any(type(i) is not str or i not in ids for i in required)
            or len(set(required)) != len(required) or len(required) > 27):
        error("required_entries must be distinct eligible logical track IDs, fitting the 27 normal pads.")
    chosen_arenas=[a for a in arena_candidates if a['id'] in required]
    if len(chosen_arenas)>arena_count:
        error('required arena entries exceed crystals.count; no content count was changed.')
    chosen_arenas+=world.random.sample([a for a in arena_candidates if a['id'] not in required],arena_count-len(chosen_arenas))
    chosen = [t for t in candidates if t["id"] in required]
    if len(chosen)+arena_count>27:
        error('required entries and selected arenas exceed the 27 normal pads.')
    optional = [t for t in candidates if t["id"] not in required]
    chosen += world.random.sample(optional, min(len(optional), 27 - len(chosen)-arena_count))
    chosen += chosen_arenas
    titles = generic_room_titles([t for t in chosen if t.get("origin") == "custom"], package_by_id)
    for track in chosen:
        if track.get("origin") == "custom" and "named_block" not in track:
            track["room_title"] = titles[track["custom_slot"]]
    world.random.shuffle(chosen)
    registry = pad_registry()
    world.random.shuffle(registry)
    manual = manual_rules(o)
    if manual:
        # Reserve every named physical seat for selected content, then keep the
        # other seats in their shuffled order. A rule never disappears because
        # its seat drew empty, and no content or item is added to fit it.
        if len(manual) > len(chosen):
            error(f"warp_pad_rules names {len(manual)} pads, but only {len(chosen)} "
                  "entries are selected; name fewer pads or select more content. "
                  "No content or items were added.")
        registry = ([seat for seat in registry if seat[0] in manual]
                    + [seat for seat in registry if seat[0] not in manual])
    # Empty pads are valid, but a fresh Adventure must start with at least
    # sphere0_guard.MIN_STARTING_CHECKS open checks (start-check rulings
    # 2026-10-01 and 2026-10-02), or generate_basic refuses the slot. Keep
    # content/counts and every physical gate unchanged and grant no item: only
    # a layout that falls short exchanges a gated occupied seat with an open
    # empty one, until enough open seats hold content. A layout that already
    # has enough takes no draw here, so its seed is unchanged.
    need = min(len(chosen), sphere0_guard.MIN_STARTING_CHECKS)
    held = starting_counts(o)

    def opens_at_start(seat):
        # Hub gate free, and a manual rule on this seat met by the real start.
        physical, _hub, keys = seat
        return keys == 0 and (physical not in manual or rule_met(manual[physical], held))

    while sum(opens_at_start(seat) for seat in registry[:len(chosen)]) < need:
        # A named seat is never exchanged, so its rule stays where it was set.
        gated = [i for i in range(len(chosen))
                 if registry[i][2] != 0 and registry[i][0] not in manual]
        empty = [i for i in range(len(chosen), len(registry)) if registry[i][2] == 0]
        if not gated or not empty:
            if manual:
                error(f"warp_pad_rules leave only "
                      f"{sum(opens_at_start(seat) for seat in registry[:len(chosen)])} "
                      f"of the {need} starting checks a slot needs. Rules are fixed and "
                      "no item is granted; make a named pad free or lower its count.")
            break
        source = world.random.choice(gated)
        destination = world.random.choice(empty)
        registry[source], registry[destination] = registry[destination], registry[source]
    # Per-track check families (#133 PR 3b). Lettersanity modes 1 and 2 draw
    # letters_per_track letters per CTR Challenge here, before the ledger is
    # sized, in pad order; nothing is drawn when Lettersanity is off.
    settings = family_settings(o)
    letters = {}
    if settings.get("lettersanity") in (1, 2):
        for index, track in enumerate(chosen):
            if "ctr" in track.get("modes", ()):
                letters[index] = tuple(sorted(LETTERS.index(letter) for letter in
                                              world.random.sample(LETTERS, settings["letters_per_track"])))
    letter_packs = {}
    for index, track in enumerate(chosen):
        if "arena_id" not in track:
            for i in letter_layout(track, settings, letters.get(index, ()))[1]:
                name, code = letter_item(track, i)
                letter_packs[name] = code
    # Every check exists before the item ledger is sized; mode order and the
    # second-stage gates only decide which race and gate reaches each one.
    check_count = sum(len(track_checks(t, "entry/" + t["id"], "pad:0", t["modes"], settings, letters.get(index, ()),
                                       package_by_id.get(t.get("package_id"))))
                      if "arena_id" not in t
                      else len(arena_content.checks(dict(id="entry/" + t["id"], kind="crystal", arena_id=t["arena_id"],
                                                         target=20, time_limit_ticks=arena_content.TIMERS[t["arena_id"]]),
                                                    "pad:0", bool(o.crystalsanity.value)))
                      for index, t in enumerate(chosen))
    if settings.get("wumpa") == "global" and any(
            wumpa_modes(t, package_by_id.get(t.get("package_id"))) for t in chosen if "arena_id" not in t):
        check_count += 1
    world.ctr_content_items = content_item_pool.resolve(
        o.item_pool.value, check_count, starts=o.start_inventory_from_pool.value,
        additional=o.start_inventory.value, trap_percentage=o.trap_fill_percentage.value,
        **(dict(selected_packs={name: 1 for name in letter_packs}, pack_codes=letter_packs)
           if letter_packs else {}))
    # Mode order (Wayfinder ticket 16): fixed Trophy, CTR, Relic; one order for
    # the whole seed; or one per pad. Only entries with two or more modes take a
    # draw, so a Trophy-only plan draws nothing here.
    multi = [index for index in range(len(chosen)) if len(chosen[index].get("modes", ())) > 1]
    seed_order = list(MODES)
    if mode_order == "per_seed" and multi:
        world.random.shuffle(seed_order)
    entry_modes = {}
    for index in multi:
        modes = list(chosen[index]["modes"])
        if mode_order == "per_pad":
            world.random.shuffle(modes)
        else:
            modes.sort(key=seed_order.index)
        entry_modes[index] = modes
    stage2 = {}
    if stages == "two":
        for index in multi:
            drawn = draw_stage2(world, world.ctr_content_items.rows)
            if drawn is not None:
                stage2[registry[index][0]] = drawn
    entries, pads, checks = [], [], []
    requirements = [dict(id="free", predicate=dict(op="always"))]
    requirements += [dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)]
    gate_for = {physical: "free" if rule is None else f"manual:{physical}"
                for physical, rule in manual.items()}
    for index, (physical, hub, keys) in enumerate(registry):
        pad = dict(id=f"pad:{physical}", hub_id=f"hub:{hub}", kind="normal", entry_id=None,
                   entrance_req=f"keys:{keys}" if keys else "free", mode_gates=[], racer_lock=None)
        if index < len(chosen):
            track = chosen[index]
            entry_id = "entry/" + track["id"]
            crystal='arena_id' in track
            first = gate_for.get(physical, 'free')
            if crystal:
                entry=dict(id=entry_id,kind='crystal',arena_id=track['arena_id'],target=20,
                           time_limit_ticks=arena_content.TIMERS[track['arena_id']])
                gates=[dict(mode='crystal',stage=1,requirement_id=first)]
            else:
                modes = entry_modes.get(index, track["modes"])
                entry = dict(id=entry_id, kind='track', track_id=track['id'], modes=modes, merged=False)
                gates = mode_gates(modes, first, "two" if physical in stage2 else "single", physical)
            entries.append(entry)
            pad.update(entry_id=entry_id,mode_gates=gates)
            if crystal:
                checks.extend(arena_content.checks(entry,pad['id'],bool(o.crystalsanity.value)))
            else:
                checks.extend(track_checks(track, entry_id, pad['id'], entry['modes'], settings,
                                           letters.get(index, ()), package_by_id.get(track.get("package_id"))))
        pads.append(pad)
    if settings.get("wumpa") == "global":
        wumpa = global_wumpa_check(global_wumpa_routes(chosen, entries, pads, package_by_id))
        if wumpa:
            checks.append(wumpa)
    for boss in range(5):
        pads.append(dict(id=f"garage:{boss}", hub_id=f"hub:{26 + boss if boss < 4 else 25}",
                         kind="garage", entry_id=None, entrance_req="free", mode_gates=[], racer_lock=None))
    assert len(checks) == check_count
    if manual:
        requirements += manual_requirements(manual, world.ctr_content_items.rows)
        world._ctr_pad_rules = {key: manual[lid] for lid, key in PAD_KEY_BY_LEVEL_ID.items()
                                if lid in manual}
    requirements += [dict(id=f"{STAGE2_PREFIX}{physical}", predicate=stage2[physical]) for physical in sorted(stage2)]
    gem_ids = [r.item for r in world.ctr_content_items.rows if r.name.endswith(" Gem") and r.base]
    if o.gems_required_goal.value > len(gem_ids):
        error("Gem goal exceeds the selected distinct base Gem colours.")
    plan = dict(version=1, packages=[p for p in packages if any(t.get("package_id") == p["id"] for t in chosen)],
                tracks=[t for t in chosen if 'arena_id' not in t], entries=entries, pads=pads, encounters=[], requirements=requirements, checks=checks,
                items=world.ctr_content_items.wire(), goal=dict(op="distinct", items=gem_ids, count=o.gems_required_goal.value),
                required_features=required_features(requirements,entries,checks,settings))
    if settings:
        plan["track_checks"] = settings
    validate(plan)
    world.ctr_content_plan = plan
    # Actual native 0.6.7 protocol/handshake validation is a release gate. This
    # room barrier already prevents the rc1 client's default 0.6.4 admission.
    world.required_client_version = (0, 6, 7)
    world.ctr_content_original_starts = copy.deepcopy(o.start_inventory_from_pool.value)
    world.ctr_starting_character = characters.resolve_starting_character(world)
    return plan


def global_wumpa_routes(tracks, entries, pads, packages):
    """[(entry id, pad id, mode)] of every Trophy Race and CTR Challenge that
    can reach ten fruit, for `wumpa: global`."""
    by_track = {track["id"]: track for track in tracks if "arena_id" not in track}
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    out = []
    for entry in entries:
        if entry["kind"] != "track" or entry["track_id"] not in by_track or entry["id"] not in pad_of:
            continue
        track = by_track[entry["track_id"]]
        out.extend((entry["id"], pad_of[entry["id"]], mode)
                   for mode in wumpa_modes(track, packages.get(track.get("package_id"))))
    return out


def generic_room_titles(tracks, packages):
    """{custom_slot: room title} for the generic-slot (B+) tracks among `tracks`.

    Only the seed's own tracks take part, in slot order, so a title clashes
    only with names in the same room: retail stems, every named block and an
    earlier generic track (custom_track_titles.seed_titles). A track with no
    usable title keeps its generic name."""
    rows = [(t["custom_slot"], packages[t["package_id"]]) for t in tracks
            if destinations.named_track(packages[t["package_id"]]["content_id"]) is None]
    titles = seed_titles([(slot, p["display_name"], p["author"], p["content_id"]) for slot, p in rows])
    return {slot: titles.get(slot, f"Custom Track {slot}") for slot, _ in rows}


def predicate(world, node):
    player = world.player
    if node["op"] == "always":
        return lambda state: True
    if node["op"] == "count":
        return lambda state: state.has(ITEM_BY_CODE[node["item"]], player, node["count"])
    if node["op"] == "sum":
        names = [ITEM_BY_CODE[code] for code in node["items"]]
        return lambda state: sum(state.count(name, player) for name in names) >= node["count"]
    if node["op"] == "distinct":
        return lambda state: sum(state.has(ITEM_BY_CODE[code], player) for code in node["items"]) >= node["count"]
    error("unsupported predicate in experimental content plan.")


def create_regions(world):
    mw, player, plan = world.multiworld, world.player, world.ctr_content_plan
    menu = Region("Menu", player, mw)
    mw.regions.append(menu)
    req = {r["id"]: r["predicate"] for r in plan["requirements"]}
    pad_by_id = {pad["id"]: pad for pad in plan["pads"]}
    # Lettersanity items a check needs on top of its route (#133 PR 3b).
    letters_needed = letter_requirements(plan)

    def stage_gate(route):
        """The second-stage requirement id of a route's mode, or None."""
        gates = {g["mode"]: g["requirement_id"] for g in pad_by_id[route["own_pad_id"]]["mode_gates"]
                 if g["stage"] == 2}
        return gates.get(route["mode"])

    def with_letters(rule, check):
        names = letters_needed.get(check["location"])
        if not names:
            return rule
        def has_letters(state, names=names):
            return state.has_all(names, player)
        return has_letters if rule is None else (lambda state, rule=rule: rule(state) and has_letters(state))

    by_pad = {}
    shared = []
    for check in plan['checks']:
        pads_of = {r["own_pad_id"] for r in check["routes"]}
        if len(pads_of) == 1:
            by_pad.setdefault(check['routes'][0]['own_pad_id'], []).append(check)
        else:
            shared.append(check)  # `wumpa: global`, one route per race
    for pad in plan["pads"]:
        if pad["entry_id"] is None:
            continue
        region = Region(pad["entry_id"], player, mw)
        mw.regions.append(region)
        # The pad opens on its hub gate and its stage-1 requirement (every
        # stage-1 gate of a pad shares one record). A stage-2 mode's checks
        # also need that mode's own gate; no mode needs a win in another one.
        first = [g["requirement_id"] for g in pad["mode_gates"] if g["stage"] == 1][:1]
        gates = [predicate(world, req[rid]) for rid in [pad["entrance_req"]] + first]
        menu.connect(region, pad["id"], gates[0] if len(gates) == 1 else
                     (lambda state, gates=tuple(gates): all(g(state) for g in gates)))
        for check in by_pad[pad['id']]:
            location = Location(player, LOCATION_BY_CODE[check['location']], check['location'], region)
            # A check with several routes on its pad (per-track Wumpa) is open
            # when any of them is: a stage-1 route opens it with the pad.
            later = [stage_gate(r) for r in check["routes"]]
            rule = None
            if all(rid is not None for rid in later):
                tests = [predicate(world, req[rid]) for rid in dict.fromkeys(later)]
                rule = tests[0] if len(tests) == 1 else (lambda state, tests=tuple(tests): any(t(state) for t in tests))
            rule = with_letters(rule, check)
            if rule is not None:
                location.access_rule = rule
            region.locations.append(location)
    for check in shared:
        location = Location(player, LOCATION_BY_CODE[check['location']], check['location'], menu)
        opens = []
        for r in check["routes"]:
            rid = stage_gate(r)
            opens.append((r["entry_id"], predicate(world, req[rid]) if rid is not None else None))

        def any_route(state, opens=tuple(opens)):
            return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                       for entry, test in opens)
        location.access_rule = with_letters(any_route, check)
        menu.locations.append(location)
    from .custom_track_presentation import location_aliases
    world.location_id_to_alias = location_aliases(world)


def create_items(world):
    plan = world.ctr_content_items
    names = plan.selected_names()
    names += traps.draw_trap_names(world, plan.trap_count)
    names += [wumpa_family.draw_filler_name(world) for _ in range(plan.filler_count - plan.trap_count)]
    world.multiworld.itempool.extend(world.create_item(name) for name in names)
    # Main.py has granted these starts. Consume only this world's local removal
    # request; retain the original configuration for spoiler/Tracker diagnostics.
    world.options.start_inventory_from_pool.value = {}


def set_rules(world):
    world.multiworld.completion_condition[world.player] = predicate(world, world.ctr_content_plan["goal"])


def wire(world):
    o = world.options
    plan=world.ctr_content_plan
    extra=({'include_battle_arenas':True,
            'include_arcade_arenas':any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']),
            'crystalsanity':any(c['kind']=='crystal_pickup' for c in plan['checks'])}
           if any(e['kind']=='crystal' for e in plan['entries']) else {})
    return dict(schema_version=SCHEMA, content_plan=copy.deepcopy(world.ctr_content_plan),
                ctr_options=dict(schema_version=SCHEMA, world_version="0.3.0-content-dev", content_plan=True,
                                 goal=-1, goal_oxide=3, goal_bosses=0, goal_gems=o.gems_required_goal.value,
                                 starting_character=characters.ROSTER_CHARACTER_ID[world.ctr_starting_character], character_unlocks=False,
                                 progressive_boost=0, progressive_stats=0, hit_character=False,
                                 death_link=o.death_link.value, deathlink_amnesty=o.deathlink_amnesty.value,**extra))


def validate(plan):
    """Closed shape plus registry/ownership/accounting for the implemented profile."""
    from .content_plan_schema import validate_shape
    try:
        validate_shape(plan)
    except (ValueError, TypeError, OverflowError) as exc:
        error(str(exc))

    def require(test, message):
        if not test:
            error(message)

    def table(name, key="id"):
        result = {row[key]: row for row in plan[name]}
        require(len(result) == len(plan[name]), "duplicate identity in " + name)
        return result

    packages = table("packages")
    # The wire is canonical: an admitted copy of each record must equal it.
    require(resolve_packages(plan["packages"], "content_plan.packages") == sorted(plan["packages"], key=lambda p: p["id"])
            and [p["id"] for p in plan["packages"]] == sorted(packages),
            "package records are not canonical or not sorted by id")
    tracks, entries, pads = table("tracks"), table("entries"), table("pads")
    checks, requirements = table("checks", "location"), table("requirements")
    require(not plan["encounters"], "encounter routes are not implemented by this profile")
    expected_requirements = {"free": {"id": "free", "predicate": {"op": "always"}}}
    expected_requirements.update({f"keys:{n}": dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)})
    manual = {rid: row for rid, row in requirements.items() if rid.startswith("manual:")}
    later = {rid: row for rid, row in requirements.items() if rid.startswith(STAGE2_PREFIX)}
    require({rid: row for rid, row in requirements.items() if rid not in manual and rid not in later}
            == expected_requirements, "unsupported or changed physical hub requirements")
    settings = check_settings(plan["track_checks"]) if "track_checks" in plan else {}
    require(plan['required_features']==required_features(plan['requirements'],plan['entries'],plan['checks'],settings),
            'required features do not match the selected content/checks')
    crystalsanity=any(c['kind']=='crystal_pickup' for c in plan['checks'])
    expected_pads = {f"pad:{physical}": (f"hub:{hub}", f"keys:{keys}" if keys else "free")
                     for physical, hub, keys in pad_registry()}
    expected_pads.update({f"garage:{i}": (f"hub:{26+i if i<4 else 25}", "free") for i in range(5)})
    require(set(pads) == set(expected_pads), "physical pad registry mismatch")
    occupied = []
    for pad_id, pad in pads.items():
        require((pad["hub_id"], pad["entrance_req"]) == expected_pads[pad_id], "pad has wrong hub or hub gate")
        require(pad["kind"] == ("garage" if pad_id.startswith("garage:") else "normal"), "pad kind mismatch")
        require(pad["racer_lock"] is None, "racer-lock routes are not implemented")
        if pad["entry_id"] is None:
            require(not pad["mode_gates"], "empty pad has mode gates")
        else:
            require(pad["kind"] == "normal" and pad["entry_id"] in entries, "invalid normal entry")
            physical = pad_id.split(":")[1]
            gate = f"manual:{physical}" if f"manual:{physical}" in manual else "free"
            entry = entries[pad['entry_id']]
            if entry['kind'] == 'crystal':
                expected_gates = [dict(mode='crystal', stage=1, requirement_id=gate)]
            else:
                stage = "two" if f"{STAGE2_PREFIX}{physical}" in later else "single"
                expected_gates = (mode_gates(entry["modes"], gate, stage, physical)
                                  if type(entry["modes"]) is list and entry["modes"] else None)
            require(pad['mode_gates'] == expected_gates, 'unsupported mode gates')
            occupied.append(pad["entry_id"])
    require(len(occupied) == len(set(occupied)) and set(occupied) == set(entries), "entry occurrence ownership mismatch")
    require(all(f"pad:{rid.split(':')[1]}" in pads and pads[f"pad:{rid.split(':')[1]}"]["entry_id"] is not None
                for rid in manual), "manual requirement without an occupied pad")
    # A second-stage record belongs to exactly one pad, which uses it for its
    # later modes (checked by the gate comparison above).
    require(all(any(g["requirement_id"] == rid and g["stage"] == 2 for g in pads.get(f"pad:{rid[len(STAGE2_PREFIX):]}", {}).get("mode_gates", ()))
                for rid in later), "second-stage requirement without a pad that uses it")
    used_tracks, used_packages, slots, retail_ids = set(), set(), set(), set()
    expected_checks = {}
    # Generic-slot room titles are recomputed from the plan's own tracks; a
    # forged title (a retail or named track's name, or a repeated one) differs.
    try:
        expected_titles = generic_room_titles([t for t in plan["tracks"] if t["origin"] == "custom"
                                               and t["package_id"] in packages
                                               and type(t["custom_slot"]) is int], packages)
    except (KeyError, TypeError):
        expected_titles = {}
    arena_ids=set()
    for entry in entries.values():
        if entry['kind']=='crystal':
            lid=entry['arena_id']
            require(lid in arena_content.ARENAS and lid not in arena_ids,'unknown or repeated arena')
            arena_ids.add(lid)
            require(entry['id']==f'entry/arena:{lid}' and entry['target']==20 and entry['time_limit_ticks']==arena_content.TIMERS[lid],
                    'arena metadata mismatch')
            pad_id=next(p['id'] for p in pads.values() if p['entry_id']==entry['id'])
            expected_checks.update({c['location']:c for c in arena_content.checks(entry,pad_id,crystalsanity)})
            continue
        require(entry["kind"] == "track" and entry["merged"] is False, "unsupported entry kind or merged mode")
        require(entry["track_id"] in tracks and entry["track_id"] not in used_tracks, "missing or repeated standalone track")
        used_tracks.add(entry["track_id"])
        track = tracks[entry["track_id"]]
        # Track modes are canonical (MODES order); the entry lists the same
        # modes in its pad's resolved order.
        require(track["modes"] == [m for m in MODES if m in track["modes"]] and track["capabilities"] == track["modes"]
                and track["field_size"] == 8 and sorted(entry["modes"]) == sorted(track["modes"]),
                "unsupported track modes or capabilities")
        if track["origin"] == "retail":
            i = track["retail_id"]
            require(i in RETAIL and i not in retail_ids, "unknown or duplicate retail track")
            retail_ids.add(i)
            require(track["display_name"] == RETAIL[i] and track["laps"] == RETAIL_LAPS and track["id"] == f"retail:{i}",
                    "retail track metadata mismatch")
            name = RETAIL[i] + ": Trophy Race"
        else:
            require(track["origin"] == "custom" and track["package_id"] in packages, "unknown custom package")
            package = packages[track["package_id"]]
            used_packages.add(package["id"])
            slot = track["custom_slot"]
            require(1 <= slot <= 32 and slot not in slots, "unregistered or duplicate custom slot")
            slots.add(slot)
            require(track["laps"] == package["laps"] and track["display_name"] == package["display_name"] and
                    track["id"] == "custom/" + package["content_id"] + "/" + package["revision"], "custom track metadata mismatch")
            block = destinations.named_track(package["content_id"])
            if "named_block" in track:
                require(block is not None and track["named_block"] == block.block_index and
                        track.get("room_title") == block.ap_name, "named block does not match this build's registry")
            else:
                require(block is None, "a track with a named block must use it")
                require(is_sanitized(track.get("room_title", track["display_name"])), "room title is not sanitized")
                require(track.get("room_title", track["display_name"]) == expected_titles.get(slot),
                        "room title is not the seed's clash-suffixed title for this track")
        require(set(track["modes"]) <= set(supported_modes(track["origin"], packages.get(track.get("package_id")))),
                "a track mode its capabilities do not allow")
        pad_id = next(p["id"] for p in pads.values() if p["entry_id"] == entry["id"])
        locations, _items = plan_letters(plan, track, settings)
        require(len(locations) == (settings["letters_per_track"] if settings.get("lettersanity") in (1, 2)
                                   and "ctr" in track["modes"] else 0),
                "letter checks do not match letters_per_track")
        for check in track_checks(track, entry["id"], pad_id, entry["modes"], settings, locations,
                                  packages.get(track.get("package_id"))):
            require(check["location"] not in expected_checks, "duplicate check identity")
            expected_checks[check["location"]] = check
    require(used_tracks == set(tracks) and used_packages == set(packages), "unused track/package")
    if settings.get("wumpa") == "global":
        wumpa = global_wumpa_check(global_wumpa_routes(plan["tracks"], plan["entries"], plan["pads"], packages))
        if wumpa:
            require(wumpa["location"] not in expected_checks, "duplicate check identity")
            expected_checks[wumpa["location"]] = wumpa
    require(not entries or any(p["entry_id"] is not None and p["entrance_req"] == "free" for p in pads.values()),
            "content layout has no playable starting pad")
    require(checks == expected_checks, "check registry or route ownership mismatch")
    item_plan = plan["items"]
    rows = {row["item"]: row for row in item_plan["rows"]}
    # Lettersanity modes 2 and 3 pool one copy of each letter item they use.
    letter_items = plan_letter_items(plan)
    require(len(rows) == len(item_plan["rows"]) and set(rows) == {content_item_pool.ITEMS[n] for n in content_item_pool.COUNTED_NAMES}
            | set(letter_items), "item family registry mismatch")
    require(all(rows[code]["base"] == 1 and rows[code]["extra"] == 0 for code in letter_items),
            "a letter item is pooled once")
    for row in rows.values():
        require(row["start_from_pool"] <= 10000 and row["start_additional"] <= 10000,
                "starting count exceeds the framework ItemDict bound")
        require(row["locked_selected"] == 0 and row["remaining"] == row["base"] + row["extra"] - row["start_from_pool"],
                "invalid remaining selected count")
        require(row["receipt_cap"] == row["base"] + row["extra"] + row["start_additional"] and
                row["requirement_ceiling"] == row["base"], "invalid receipt cap or base requirement ceiling")
    require(rows[35010014]["base"] == 4, "four base Keys are mandatory")
    require(all(rows[i]["base"] in (0, 1) for i in range(35010009, 35010014)), "base Gems are distinct colours")
    require(item_plan["coded_checks"] == len(checks) and item_plan["locked_checks"] == 0 and
            sum(r["remaining"] for r in rows.values()) + item_plan["filler_count"] == len(checks) and
            item_plan["trap_count"] <= item_plan["filler_count"], "item/check capacity mismatch")
    goal = plan["goal"]
    gems = [i for i in range(35010009, 35010014) if rows[i]["base"]]
    require(goal["op"] == "distinct" and goal["items"] == gems and 1 <= goal["count"] <= len(gems),
            "goal must count selected distinct base Gem colours")
    for rid, row in {**manual, **later}.items():
        predicate_ = row["predicate"]
        if predicate_["op"] == "count":
            item = predicate_["item"]
            require(item in rows and ITEM_BY_CODE.get(item) in content_item_pool.COUNTED_NAMES
                    and 1 <= predicate_["count"] <= rows[item]["requirement_ceiling"],
                    f"{rid}: count rule item or count outside the base supply")
        else:
            require(predicate_["op"] == "sum", f"{rid}: unsupported manual predicate")
            family = next((names for names in SUM_FAMILIES.values()
                           if predicate_["items"] == [rows[content_item_pool.ITEMS[n]]["item"] for n in names
                                                      if rows[content_item_pool.ITEMS[n]]["requirement_ceiling"] > 0]), None)
            require(family is not None and predicate_["items"] and
                    1 <= predicate_["count"] <= sum(rows[code]["requirement_ceiling"] for code in predicate_["items"]),
                    f"{rid}: sum rule items or count outside the base supply")
    return True


def _tracker_arrays(value, depth=0, budget=None):
    """AP room persistence stores JSON arrays as tuples; restore their JSON form.

    Keep scalar types and object keys exact so normal admission still refuses
    malformed numbers, booleans and fields. Bound this walk before copying.
    """
    if budget is None:
        budget = [0]
    budget[0] += 1
    if depth > 32 or budget[0] > 500000:
        error("content_plan: nesting/node budget")
    if type(value) in (list, tuple):
        return [_tracker_arrays(v, depth + 1, budget) for v in value]
    if type(value) is dict:
        return {k: _tracker_arrays(v, depth + 1, budget) for k, v in value.items()}
    return value


def restore(world, slot_data):
    plan = _tracker_arrays(slot_data["content_plan"])
    validate(plan)
    co = slot_data.get("ctr_options", {})
    if (type(slot_data.get("schema_version")) is not int or slot_data["schema_version"] != SCHEMA or
            type(co.get("schema_version")) is not int or co["schema_version"] != SCHEMA or co.get("content_plan") is not True):
        error("content-plan envelope is missing or inconsistent")
    has_crystals=any(e['kind']=='crystal' for e in plan['entries'])
    for key,want in dict(include_battle_arenas=has_crystals,
                         include_arcade_arenas=any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']),
                         crystalsanity=any(c['kind']=='crystal_pickup' for c in plan['checks'])).items():
        if has_crystals and co.get(key) is not want:
            error('Crystal option envelope disagrees with plan: '+key)
        if not has_crystals and key in co:
            error('Crystal option without selected Crystal entries: '+key)
    starting = co.get("starting_character")
    if type(starting) is not int or not 0 <= starting < 16:
        error("invalid starting racer")
    names = {**ITEM_BY_CODE, **plan_letter_items(plan)}
    rows = tuple(content_item_pool.ItemRow(name=names[r["item"]], **r) for r in plan["items"]["rows"])
    world.ctr_content_items = content_item_pool.ItemPlan(rows, **{k: v for k, v in plan["items"].items() if k != "rows"})
    world.ctr_content_plan = plan
    world.required_client_version = (0, 6, 7)
    world.ctr_starting_character = characters.CHARACTER_ID_TO_NAME[starting]
    world.ctr_content_original_starts = {r.name: r.start_from_pool for r in rows if r.start_from_pool}
    world.options.start_inventory_from_pool.value = copy.deepcopy(world.ctr_content_original_starts)
    world.options.start_inventory.value = {r.name: r.start_additional for r in rows if r.start_additional}
    world.options.gems_required_goal.value = plan["goal"]["count"]
    world.options.crystalsanity.value=int(any(c['kind']=='crystal_pickup' for c in plan['checks']))
    world.options.include_battle_arenas.value=int(any(e['kind']=='crystal' for e in plan['entries']))
    world.options.include_arcade_arenas.value=int(any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']))
    world.options.death_link.value = co.get("death_link", 0)
    world.options.deathlink_amnesty.value = co.get("deathlink_amnesty", 1)
    # Optional legacy classifiers must not read the tracking player's unrelated YAML.
    world.options.character_unlocks.value = 0
    world.options.racer_locked_pads.value = 0
    world.options.progressive_boost.value = 0
    world.options.progressive_stats.value = 0
    # The plan's own check families (#133 PR 3b), for code that reads options.
    settings = plan.get("track_checks", {})
    rungs = settings.get("podium_rungs", ())
    world.options.podium_placement_checks.value = int(bool(rungs))
    world.options.podium_held_rungs.value = int("held_1st" in rungs)
    world.options.podium_held_fifth_rung.value = int("held_5th" in rungs)
    world.options.podium_finish_rungs.value = int("finish_podium" in rungs)
    world.options.podium_any_position_rung.value = int("finish_any" in rungs)
    world.options.wumpa_check.value = {"global": 1, "per_track": 2}.get(settings.get("wumpa"), 0)
    world.options.lettersanity.value = settings.get("lettersanity", 0)
    if "letters_per_track" in settings:
        world.options.letters_per_track.value = settings["letters_per_track"]
