"""Experimental content-plan generation, independent of legacy cup displacement.

The executable profile builds standalone track entries with their Trophy Race,
CTR Challenge and Relic Race modes (#133 PR 3), their podium rungs, Reach 10
Wumpa and C/T/R letter checks (#133 PR 3b), Cortex Vortex as a track and the
Relic Race Perfect checks (#133 PR 3c, #453), pool-only packs (#133 PR 4a),
character unlocks with racer-locked pads and the stat settings (#133 PR 4b),
Progressive Boost, Progressive Stats and Logic Difficulty with the boost terms
on every check (#133 PR 4c, content_capability.py), Itemsanity and Hit
Character as global checks routed from every race (#133 PR 4d,
content_global_checks.py), Item Box Locations on retail and named-block custom
tracks (#133 PR 4e, content_item_boxes.py), plando_items and item_links
checked around the framework phases (#133 PR 4f, content_item_pool.py),
four-leg cups with their Win, sweep and Cup Leg Victory checks (#133 PR 5,
content_cups.py), boss garages with their encounters and the Oxide and Boss
goals (#133 PR 6, content_bosses.py), Crystal Challenge entries, pad
placement and requirements (one generator row 3, content_requirements.py), and
items fixed to their own check (one generator row 4, content_fixed.py).
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

from .Options import DL_SEND_BITS

from . import (content_item_pool, characters, cortex_vortex_track, destinations, named_tracks, podium,
               relic_tiers, sphere0_guard, traps, warp_pad_rules, wumpa_family)
from .custom_check_namespace import custom_check_code, custom_check_name
from .custom_track_titles import is_sanitized, seed_titles
from .custom_tracks import BABY_T_PARK_PROFILES
from . import (arena_content, content_bosses, content_capability, content_cups, content_fixed, content_global_checks,
               content_item_boxes, content_requirements, custom_packages, tizi_helper, turbo_grant)
from .Locations import CTR_LOCATION_IDS
from . import warp_pad_logic
from .warp_pad_logic import HUB_STATIC

#: Equal to slot_data.SLOT_DATA_SCHEMA: both room shapes share the 0.3.0 step
#: (test_content_plan checks it).
SCHEMA = 18
MANUAL_FEATURE = "manual_pad_requirements_v1"
#: Track modes (#133 PR 3). A plan whose track entries are all Trophy-only keeps
#: the earlier wire exactly; any other entry declares this feature.
MODE_FEATURE = "track_modes_v1"
MODES = ("trophy", "ctr", "relic")
#: Second-stage gate record of a physical pad: `stage2:<physical LevelID>`.
STAGE2_PREFIX = "stage2:"
#: With vanilla requirements, Mystery Caves (1 Trophy) and Sewer Speedway (3)
#: are the pads behind the two open ones.
VANILLA_NEAR_TROPHIES = 3
RELIC_TIERS = ("Sapphire", "Gold", "Platinum")
#: (route award, named-block key, location suffix) of every check a mode owns.
#: Codes come from the frozen names: retail `<Track>: <suffix>`, named blocks by
#: key, generic slots `Custom Track N: <suffix>`.
MODE_CHECKS = {
    "trophy": (("win", "trophy", "Trophy Race"),),
    "ctr": (("win_letters", "ctr_token", "CTR Token Challenge"),),
    "relic": tuple((tier.lower(), "relic_" + tier.lower(), tier + " Time Trial") for tier in RELIC_TIERS),
}
#: Relic tier checks follow the item counts (ruled 2026-10-30): a tier's Time
#: Trial checks exist on as many Relic Races as there are items of the tier,
#: drawn per seed. The plan's check list says which, as with Lettersanity's
#: letters. The feature is declared when some Relic Race lacks a tier.
RELIC_FEATURE = "relic_tier_checks_v1"
#: The five surface items: ledger rows that add no check and no rule, all five
#: or none (content_item_pool.resolve).
SURFACE_FEATURE = "surface_items_v1"
SURFACE_CODES = frozenset(content_item_pool.ITEMS[name] for name in content_item_pool.SURFACE_NAMES)
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
#: Relic Race Perfect (#453, #133 PR 3c): breaking every time crate in a Relic
#: Race. The plan's `track_checks.relic_perfect` says the option is on; every
#: track entry with a Relic Race then owns one perfect check on that route.
PERFECT_FEATURE = "relic_perfect_v1"
PERFECT_SUFFIX = "Relic Race Perfect"
#: Cortex Vortex as a content-plan track (#133 PR 3c): the bundled Lockheart
#: pair the legacy pad track and the Oxide 2 venue use (pinned in
#: cortex_vortex_track), under its own frozen `Cortex Vortex:` names and the
#: 35026000 block. It is not a `packages` row: `package_id` names the bundled
#: pair, which native locates and hashes itself, and it takes no custom slot.
CORTEX_ORIGIN = "cortex_vortex"
CORTEX_TRACK_ID = "cortex_vortex"
CORTEX_PACKAGE_ID = "bundled/cortex-vortex"
CORTEX_LAPS = 3


def cortex_track():
    """The Cortex Vortex track record, without its modes."""
    return dict(id=CORTEX_TRACK_ID, origin=CORTEX_ORIGIN, package_id=CORTEX_PACKAGE_ID,
                display_name=destinations.CORTEX_VORTEX, laps=CORTEX_LAPS)
#: Aggregate manual rule -> the counted item names it sums, in wire order.
#: Native holds the same three lists; the parity fixtures compare them.
SUM_FAMILIES = {"AnyCtrToken": warp_pad_rules.TOKENS, "AnyRelic": warp_pad_rules.RELICS,
                "AnyGem": warp_pad_rules.GEMS}
PADS = json.loads(pkgutil.get_data(__package__, "data/warp_pad_ids.json"))["pads"]
RETAIL = {row["level_id"]: name.removesuffix(" Warp Pad") for name, row in PADS.items()
          if row["kind"] in ("race", "trial")}
ITEM_BY_CODE = {code: name for name, code in content_item_pool.ITEMS.items()}
LOCATION_BY_CODE = {code: name for name, code in CTR_LOCATION_IDS.items()}


#: Pool-only packs (#133 PR 4a): items that add no location and no rule, so
#: the plan only sizes them in the item ledger. The plan's optional
#: `item_packs` record carries the seed's settings; it is
#: absent when all three are off, so such a plan keeps its earlier wire.
#: (setting, item name).
PACK_FEATURE = "item_packs_v1"
PACK_ITEMS = (("progressive_starting_wumpa", "Progressive Starting Wumpa"),
              ("turbo_grant", turbo_grant.TURBO_GRANT_ITEM),
              ("tizi_helper", tizi_helper.TIZI_HELPER_ITEM))
#: Highest Progressive Starting Wumpa count (Options.ProgressiveStartingWumpa).
STARTING_WUMPA_MAX = 10
#: Envelope keys a content plan carries only when the option is not at the
#: content plan's earlier fixed behaviour (#133 PR 4a): an explicit DeathLink
#: send list, and the two warp-pad display settings. Native reads each one;
#: absent keys mean the legacy send coupling, the one-pile glow and AP item
#: type colours on, as before.
ENVELOPE_OPTIONAL = ("death_link_send", "warp_pad_item_display", "ap_item_type_colors")
#: Character packs (#133 PR 4b). With Character Unlocks on, the plan's
#: optional `racers` record names the starting racer (engine character id),
#: whether Remove Playable Oxide is on and the requested racer-lock maximum.
#: The item ledger then pools one row per unlock racer (the roster minus the
#: starting racer, and minus Oxide when he is removed), and a pad that does not
#: open at the start may carry a `racer_lock`. The record is absent when
#: Character Unlocks is off, so such a plan keeps its earlier wire.
RACER_FEATURE = "character_unlocks_v1"
RACER_KEYS = ("starting_character", "remove_playable_oxide", "requested_locks")
#: The client stat settings (#133 PR 4b): optional envelope keys, present only
#: when set. The stat trio is the resolved outcome of
#: characters.effective_stat_config, sent together; native never re-derives
#: the precedence. Progressive Stats (source 1) joined with #133 PR 4c.
STAT_ENVELOPE = ("starting_stat_class", "penta_stats", "stat_source", "stat_owner", "stat_editing_allowed")


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
    package has no relic target times. Both revisions measure six super turbo
    pad trigger quads (#133 PR 4c) and eight weapon crates (#133 PR 4e).
    They also measure 35 restart points with AI navigation; the optional
    `checkpoints` and `ai_nav` (#133 PR 6b) stay out of these examples so
    rooms that do not race a boss on them keep their bytes."""
    revision = profile["package_version"]
    sizes = (2579256, 458808) if revision == "1.0.0" else (2558168, 458808)
    files = [dict(role=role, sha256=profile[role + "_sha256"], bytes=size,
                  format="ctr-" + role, format_version=1)
             for role, size in zip(("lev", "vrm"), sizes)]
    return dict(id="package/baby-t-park/" + revision, content_id="baby-t-park",
                uuid=profile["package_uuid"], revision=revision, display_name="Baby T Park",
                author="Lockheart", laps=profile["laps"],
                capabilities=dict(time_trial=True, arcade=True, relic=False, ctr_tokens=True, wumpa=True,
                                  super_turbo_pads=True, weapon_crates=8),
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


def relic_supply(rows):
    """{tier: base + extra copies} from the ledger's wire rows."""
    by_code = {row["item"]: row for row in rows}
    return {tier.lower(): by_code[content_item_pool.ITEMS[f"{tier} Relic"]]["base"]
            + by_code[content_item_pool.ITEMS[f"{tier} Relic"]]["extra"] for tier in RELIC_TIERS}


def relic_races(entries):
    """Track entries with a Relic Race: the races a tier's checks are drawn on."""
    return sum(e["kind"] == "track" and "relic" in e["modes"] for e in entries)


def required_features(requirements, entries=(), checks=(), settings=None, packs=None, racers=None, capability=None,
                      global_checks=None, item_boxes=None, bosses=None, rows=(), pad_requirements=None, fixed=None,
                      guarded=None):
    # Cups (#133 PR 5a) declare their feature after Item Box Locations, boss
    # garages (#133 PR 6) next, the row 2 plan content, then row 3's pad
    # requirements and row 4's fixed items last. `guarded` names the track of
    # the relic guard, whose Relic Race holds no tier check.
    races = relic_races(entries)
    eligible = races - (guarded is not None)
    manual = any(r["id"].startswith("manual:") for r in requirements)
    settings = settings or {}
    return (["content_plan_v1"] + ([MANUAL_FEATURE] if manual else [])
            + (["crystal_entries_v1"] if any(e['kind']=='crystal' for e in entries) else [])
            + (["crystal_pickups_v1"] if any(c['kind']=='crystal_pickup' for c in checks) else [])
            + (["arcade_crystals_v1"] if any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in entries) else [])
            + ([MODE_FEATURE] if any(e["kind"] == "track" and e["modes"] != ["trophy"] for e in entries) else [])
            + ([PODIUM_FEATURE] if "podium_rungs" in settings else [])
            + ([WUMPA_FEATURE] if "wumpa" in settings else [])
            + ([LETTER_FEATURE] if "lettersanity" in settings else [])
            + ([PERFECT_FEATURE] if "relic_perfect" in settings else [])
            + ([PACK_FEATURE] if packs else [])
            + ([RACER_FEATURE] if racers else [])
            + ([content_capability.FEATURE] if capability else [])
            + ([content_global_checks.FEATURE] if global_checks else [])
            + ([content_item_boxes.FEATURE] if item_boxes else [])
            + ([content_cups.FEATURE] if any(e["kind"] == content_cups.KIND for e in entries) else [])
            + ([content_bosses.FEATURE] if bosses is not None else [])
            + ([content_cups.GEM_FEATURE] if any(e["kind"] == content_cups.KIND
                                                 and content_cups.gem_colour(e["id"]) is not None for e in entries) else [])
            + ([SURFACE_FEATURE] if any(row["item"] in SURFACE_CODES for row in rows) else [])
            + ([RELIC_FEATURE] if rows and any(min(count, eligible) < races for count in relic_supply(rows).values())
               else [])
            + ([content_requirements.FEATURE] if pad_requirements else [])
            + ([content_fixed.FEATURE] if fixed else []))


def family_settings(options):
    """The plan's `track_checks` record from the seed's options; {} when the
    podium rungs, Wumpa checks and Lettersanity are all off (#133 PR 3b).

    `podium_rungs` lists the created rung keys in podium.SLOT_ORDER (the
    sub-toggles decide them, as on the legacy path); `wumpa` is `global` or
    `per_track`; `lettersanity` is the mode 1 to 3, with `letters_per_track`
    only for the two location-bearing modes. `relic_perfect` is true when
    Relic Race Perfect checks are on (#133 PR 3c)."""
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
    if options.relic_perfect_checks.value:
        out["relic_perfect"] = True
    return out


def check_settings(settings):
    """Shape and values of a plan's `track_checks` record."""
    if (not isinstance(settings, dict) or not settings
            or set(settings) - {"podium_rungs", "wumpa", "lettersanity", "letters_per_track", "relic_perfect"}):
        error("track_checks must be a nonempty mapping of podium_rungs, wumpa, lettersanity, "
              "letters_per_track and relic_perfect.")
    if "relic_perfect" in settings and settings["relic_perfect"] is not True:
        error("track_checks.relic_perfect must be true when present.")
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


def pack_settings(options):
    """The plan's `item_packs` record from the seed's options; {} when
    Progressive Starting Wumpa, Turbo Grant and Tizi Helper are all off
    (#133 PR 4a). The counts are the legacy item creator's: the slider's
    value, and one copy of each grant."""
    out = {}
    if options.progressive_starting_wumpa.value:
        out["progressive_starting_wumpa"] = int(options.progressive_starting_wumpa.value)
    if options.turbo_grant.value:
        out["turbo_grant"] = True
    if options.tizi_helper.value:
        out["tizi_helper"] = True
    return out


def check_pack_settings(packs):
    """Shape and values of a plan's `item_packs` record. Key order is not a
    rule: JSON objects carry none, and native reads them sorted."""
    if not isinstance(packs, dict) or not packs or set(packs) - {key for key, _item in PACK_ITEMS}:
        error("item_packs must be a nonempty mapping of progressive_starting_wumpa, turbo_grant and "
              "tizi_helper.")
    count = packs.get("progressive_starting_wumpa", 1)
    if type(count) is not int or not 1 <= count <= STARTING_WUMPA_MAX:
        error(f"item_packs.progressive_starting_wumpa must be 1 to {STARTING_WUMPA_MAX} when present.")
    if any(packs[key] is not True for key in ("turbo_grant", "tizi_helper") if key in packs):
        error("item_packs.turbo_grant and item_packs.tizi_helper must be true when present.")
    return packs


def pack_counts(packs):
    """{item name: copies} the ledger pools for an `item_packs` record."""
    return {item: (packs[key] if key == "progressive_starting_wumpa" else 1)
            for key, item in PACK_ITEMS if key in packs}


def envelope_options(options):
    """The optional content-plan `ctr_options` keys this seed sets (#133 PR
    4a), see ENVELOPE_OPTIONAL. Values use the normal seed's encoding."""
    out = {}
    if set(options.death_link_send.value) != {"follow_death_link"}:
        out["death_link_send"] = options.death_link_send.send_mask(options.death_link.value)
    if options.warp_pad_item_display.value:
        out["warp_pad_item_display"] = int(options.warp_pad_item_display.value)
    if not options.ap_item_type_colors.value:
        out["ap_item_type_colors"] = False
    return out


def check_envelope_options(co):
    """Types and bounds of the optional envelope keys, as native reads them."""
    # death_link is always emitted; native admits 0 off to 4 weapon_hit (#483).
    if "death_link" in co and (type(co["death_link"]) is not int or not 0 <= co["death_link"] <= 4):
        error("ctr_options.death_link must be 0 to 4.")
    if "death_link_send" in co and (type(co["death_link_send"]) is not int or not 0 <= co["death_link_send"] <= 7):
        error("ctr_options.death_link_send must be a send bitmask 0 to 7.")
    if "warp_pad_item_display" in co and (type(co["warp_pad_item_display"]) is not int
                                          or co["warp_pad_item_display"] not in (0, 1)):
        error("ctr_options.warp_pad_item_display must be 0 or 1.")
    if "ap_item_type_colors" in co and type(co["ap_item_type_colors"]) is not bool:
        error("ctr_options.ap_item_type_colors must be true or false.")
    if "starting_stat_class" in co and (type(co["starting_stat_class"]) is not int
                                        or not 1 <= co["starting_stat_class"] <= 4):
        error("ctr_options.starting_stat_class must be 1 to 4 when present.")
    if "penta_stats" in co and (type(co["penta_stats"]) is not int or co["penta_stats"] != characters.PENTA_PAL):
        error("ctr_options.penta_stats must be 1 when present.")
    trio = [key in co for key in STAT_ENVELOPE[2:]]
    # Editable stats (2, owner 1 or 2, editing on), or Progressive Stats (1,
    # owner its mode, editing off, #133 PR 4c), which wins over editable stats.
    if any(trio) and not (all(trio) and type(co["stat_source"]) is int and type(co["stat_owner"]) is int
                          and co["stat_owner"] in (1, 2)
                          and ((co["stat_source"] == characters.STAT_SOURCE_EDITABLE
                                and co["stat_editing_allowed"] is True)
                               or (co["stat_source"] == characters.STAT_SOURCE_PROGRESSIVE
                                   and co["stat_editing_allowed"] is False))):
        error("ctr_options.stat_source, stat_owner and stat_editing_allowed must be editable stats "
              "(2, 1 or 2, true) or Progressive Stats (1, 1 or 2, false) together when present.")


def check_relic_progression(co):
    if "relic_progression" not in co:
        return
    value = co["relic_progression"]
    if (type(value) is not dict or set(value) != {"Sapphire Relic", "Gold Relic", "Platinum Relic"}
            or any(type(flag) is not bool for flag in value.values())):
        error("ctr_options.relic_progression must name exactly the three relic tiers with boolean values.")


def box_envelope(world):
    """Item Box Locations (#133 PR 4e): `box_locations` and the seed's
    `color_boxes_by_item`, present exactly when the plan has its `item_boxes`
    record, so plans without boxes keep their envelope. Native reads an absent
    `color_boxes_by_item` as off (pink boxes)."""
    if "item_boxes" not in world.ctr_content_plan:
        return {}
    return dict(box_locations=True, color_boxes_by_item=bool(world.options.color_boxes_by_item.value))


def check_box_envelope(plan, co):
    """The envelope's box keys are present exactly with the `item_boxes`
    record: `box_locations` true and `color_boxes_by_item` true or false."""
    if "item_boxes" in plan:
        if co.get("box_locations") is not True or type(co.get("color_boxes_by_item")) is not bool:
            error("box envelope disagrees with the plan's item_boxes record")
    elif "box_locations" in co or "color_boxes_by_item" in co:
        error("box envelope keys without the plan's item_boxes record")


def check_racer_envelope(plan, co):
    """Character packs (#133 PR 4b): the envelope's `character_unlocks` is
    true exactly when the plan has its `racers` record, and then its
    `starting_character` is the record's."""
    racers = plan.get("racers")
    if co.get("character_unlocks") is not (racers is not None) or (
            racers is not None and (type(co.get("starting_character")) is not int
                                    or co["starting_character"] != racers["starting_character"])):
        error("character envelope disagrees with the plan's racers record")


def stat_envelope(world):
    """The optional stat keys of the content-plan envelope (#133 PR 4b), see
    STAT_ENVELOPE. Absent keys mean the racer's own class, Penta's ordinary
    table and vanilla stats, as before."""
    o = world.options
    out = {}
    if o.starting_stat_class.value:
        out["starting_stat_class"] = int(o.starting_stat_class.value)
    if o.penta_stats.value:
        out["penta_stats"] = int(o.penta_stats.value)
    source, owner, editable = characters.effective_stat_config(world)
    if source:
        out.update(stat_source=source, stat_owner=owner, stat_editing_allowed=bool(editable))
    return out


def check_racer_settings(racers):
    """Shape and values of a plan's `racers` record (#133 PR 4b)."""
    if not isinstance(racers, dict) or set(racers) != set(RACER_KEYS):
        error("racers must be a mapping of exactly starting_character, remove_playable_oxide and requested_locks.")
    start, removed, requested = (racers[key] for key in RACER_KEYS)
    if type(start) is not int or start not in characters.CHARACTER_ID_TO_NAME:
        error("racers.starting_character must be an engine character id 0 to 15.")
    if type(removed) is not bool:
        error("racers.remove_playable_oxide must be true or false.")
    if removed and characters.CHARACTER_ID_TO_NAME[start] == characters.OXIDE:
        error("racers: Nitros Oxide cannot be removed and be the starting racer.")
    if type(requested) is not int or not 0 <= requested <= characters.PHYSICAL_PAD_COUNT:
        error(f"racers.requested_locks must be 0 to {characters.PHYSICAL_PAD_COUNT}.")
    return racers


def racer_excluded(racers, name):
    """A racer the plan never pools nor locks: the starting racer, and Oxide
    when Remove Playable Oxide is on (characters._excluded_racer)."""
    cid = characters.ROSTER_CHARACTER_ID[name]
    return cid == racers["starting_character"] or (racers["remove_playable_oxide"] and name == characters.OXIDE)


def unlock_names(racers):
    """The unlock items a `racers` record pools, in roster order: the
    roster minus the starting racer, and minus Oxide when removed."""
    return [name for name in characters.ROSTER_CHARACTER_ID if not racer_excluded(racers, name)]


def predicate_met(node, held):
    """A requirement predicate against {item code: count} the slot starts with."""
    if node["op"] == "always":
        return True
    if node["op"] == "count":
        return held.get(node["item"], 0) >= node["count"]
    return sum(held.get(code, 0) for code in node["items"]) >= node["count"]


def lock_eligible(plan):
    """Pad ids, in physical order, that may carry a racer lock (#133 PR 4b).

    An occupied normal pad that does not open at the start: its hub gate needs
    Keys, or its stage-1 rule is not met by the items the slot starts with
    (from-pool and additional starts in the item ledger). Pads that open at the
    start never take a lock, so the starting checks are the same with locks on
    or off, and neither do the four N. Sanity Beach race pads (the legacy rule
    in characters.eligible_lock_pads). Vanilla requirements lock no pad. Read
    from the plan alone."""
    record = plan.get("pad_requirements")
    if record and record["mode"] == "vanilla":
        return []
    held = {row["item"]: row["start_from_pool"] + row["start_additional"] for row in plan["items"]["rows"]}
    req = {row["id"]: row["predicate"] for row in plan["requirements"]}
    out = []
    for pad in plan["pads"]:
        if (pad["kind"] != "normal" or pad["entry_id"] is None
                or (record and pad_physical(pad) in content_requirements.BOOTSTRAP_PADS)):
            continue
        first = [g["requirement_id"] for g in pad["mode_gates"] if g["stage"] == 1][:1]
        opens = pad["entrance_req"] == "free" and all(predicate_met(req[rid], held) for rid in first)
        if not opens:
            out.append(pad["id"])
    return sorted(out, key=lambda pad_id: int(pad_id.split(":")[1]))


def plan_racer_locks(plan):
    """{pad id: roster name} of the plan's racer-locked pads."""
    return {pad["id"]: characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
            for pad in plan["pads"] if pad["racer_lock"] is not None}


def draw_racer_locks(world, plan, racers):
    """Seat the seed's racer locks on the plan's pads (#133 PR 4b).

    The legacy rule (characters.resolve_racer_locks): the player's count is a
    maximum, the seed takes min(requested, eligible), the pads are a sample of
    the eligible ones and the racers are spread so no racer locks a second pad
    before every candidate locks one. Never the starting racer, never Oxide
    when removed. No draw when no lock is taken."""
    pads = lock_eligible(plan)
    requested = racers["requested_locks"]
    world.ctr_racer_lock_counts = {"requested": requested, "eligible": len(pads)}
    n = min(requested, len(pads))
    if n <= 0:
        return
    chosen = sorted(world.random.sample(pads, n), key=lambda pad_id: int(pad_id.split(":")[1]))
    candidates = [name for name in characters.ROSTER_CHARACTER_ID if not racer_excluded(racers, name)]
    by_id = {pad["id"]: pad for pad in plan["pads"]}
    for pad_id, name in zip(chosen, characters.spread_lock_racers(world, candidates, n)):
        by_id[pad_id]["racer_lock"] = characters.ROSTER_CHARACTER_ID[name]


def supported_modes(origin, package=None):
    """Modes a track can run, in MODES order (#133 PR 3).

    Retail tracks and Cortex Vortex run all three (Cortex Vortex's bundled
    pair has AI paths, the three letters and 100 time crates; its relic
    targets are compiled placeholders, as on the legacy pad track). A custom
    package's measured capability flags
    decide: Trophy needs an eight-kart grid with AI paths (`arcade`), the CTR
    Challenge also needs the C, T and R letters (`ctr_tokens`), and the Relic
    Race needs time crates with target times (`relic`) on a timed lap graph
    (`time_trial`). Native measures the same flags on the bytes before a
    package is admitted (ap_content_capability.h)."""
    if origin in ("retail", CORTEX_ORIGIN):
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
    offset `key`, else the frozen `<retail track>: <suffix>`,
    `Cortex Vortex: <suffix>` or `Custom Track N: <suffix>` name."""
    if track["origin"] == "custom" and "named_block" in track:
        code = named_tracks.location_code(track["named_block"], key)
        return LOCATION_BY_CODE[code], code
    stem = (f"Custom Track {track['custom_slot']}" if track["origin"] == "custom"
            else track["display_name"])
    name = f"{stem}: {suffix}"
    return name, CTR_LOCATION_IDS[name]


def mode_checks(track, mode, relics=None):
    """[(award, location name, code, display suffix)] a track's mode owns.
    `relics` narrows a Relic Race to the tiers it holds a check for."""
    out = []
    for award, key, suffix in MODE_CHECKS[mode]:
        if mode == "relic" and relics is not None and award not in relics:
            continue
        name, code = track_location(track, key, suffix)
        out.append((award, name, code, suffix))
    return out


def plan_relics(plan, track):
    """The tiers a track's Relic Race holds a check for, read from the plan."""
    present = {check["location"] for check in plan["checks"]}
    return {award for award, _name, code, _suffix in mode_checks(track, "relic") if code in present}


def draw_relic_checks(world, tracks, totals):
    """{track id: tiers it holds a check for}. Each tier takes as many of the
    seed's Relic Races as `totals` holds copies of it, drawn at random, capped
    by the Relic Races in the seed. Items beyond that land on other checks. A
    tier with a copy for every race takes no draw."""
    out = {track: set() for track in tracks}
    for tier, total in totals.items():
        for track in tracks if total >= len(tracks) else relic_tiers.draw_tier(world, tracks, total):
            out[track].add(tier)
    return out


def letter_suffix(index):
    return f"Letter {LETTERS[index]}"


def letter_code(track, index):
    return track_location(track, LETTER_KEYS[index], letter_suffix(index))[1]


def letter_item(track, index):
    """(item name, code) of a track's Letter C, T or R item: the named block's
    item offset, the generic `Letter C (Custom Track N)` family, Cortex
    Vortex's `Letter C (Cortex Vortex)` items, or the retail
    `Letter C (<track>)` item."""
    if track["origin"] == "custom" and "named_block" in track:
        return (named_tracks.item_name(track["room_title"], LETTER_KEYS[index]),
                named_tracks.item_code(track["named_block"], LETTER_KEYS[index]))
    if track["origin"] == "custom":
        return (custom_check_name("letter_item", track["custom_slot"], index),
                custom_check_code("letter_item", track["custom_slot"], index))
    if track["origin"] == CORTEX_ORIGIN:
        return (cortex_vortex_track.letter_item_name(LETTERS[index]),
                cortex_vortex_track.LETTER_ITEM_CODES[index])
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


def track_checks(track, entry_id, pad_id, modes, settings=None, letters=(), package=None, capability=None,
                 item_boxes=None, relics=None):
    """Every check of a standalone track entry, in its entry's mode order.

    Each mode's own checks come first; a Trophy Race adds the seed's podium
    rungs, a CTR Challenge its letter checks (`letters`, Lettersanity modes 1
    and 2). A per-track Reach 10 Wumpa check comes last, with one route per
    mode that can reach ten fruit (#133 PR 3b). With `relic_perfect`, a Relic
    Race adds its Relic Race Perfect check after the three tiers (#133 PR 3c).

    With Progressive Boost on (#133 PR 4c), every check whose race needs a
    boost rank carries it as `boost` (content_capability.check_boost), among
    them the USF term of the perfect ruling (2026-10-13, #453 answer 1).

    With Item Box Locations on (#133 PR 4e), the track's box checks come
    last, each with a route per mode of the entry and its legacy box terms
    (content_item_boxes).

    `relics` is the set of tiers this track's Relic Race holds a check for
    (draw_relic_checks), all three when None."""
    title = room_title(track)
    settings = settings or {}

    def check(code, kind, suffix, routes):
        return dict(location=code, owner=track["id"], kind=kind, display_name=f"{title}: {suffix}",
                    routes=[route(entry_id, mode, pad_id, award) for mode, award in routes])
    out = []
    for mode in modes:
        for award, _name, code, suffix in mode_checks(track, mode, relics):
            out.append(check(code, mode, suffix, [(mode, award)]))
        if mode == "trophy":
            for key in settings.get("podium_rungs", ()):
                out.append(check(track_location(track, key, RUNG_SUFFIX[key])[1], "podium",
                                 RUNG_SUFFIX[key], [("trophy", key)]))
        if mode == "ctr":
            for index in letter_layout(track, settings, letters)[0]:
                out.append(check(letter_code(track, index), "letter", letter_suffix(index),
                                 [("ctr", LETTER_KEYS[index])]))
        if mode == "relic" and settings.get("relic_perfect"):
            out.append(check(track_location(track, "relic_perfect", PERFECT_SUFFIX)[1], "perfect",
                             PERFECT_SUFFIX, [("relic", "perfect")]))
    if settings.get("wumpa") == "per_track":
        reach = wumpa_modes(track, package)
        if reach:
            out.append(check(track_location(track, "wumpa", WUMPA_SUFFIX)[1], "wumpa", WUMPA_SUFFIX,
                             [(mode, "wumpa") for mode in reach]))
    if capability and capability["boost_mode"]:
        # Lettersanity mode 2: only the drawn letters must be picked up (an
        # undrawn one is transparent); otherwise all three.
        picked = ({LETTER_KEYS[i] for i in letters} if settings.get("lettersanity") == 2 else None)
        for item in out:
            need = content_capability.check_boost(track, item["kind"], item["routes"][0]["award"],
                                                  capability, package, picked)
            if need:
                item["boost"] = need
    for slot, code, suffix in content_item_boxes.track_boxes(track, item_boxes, package):
        box = check(code, content_item_boxes.KIND, suffix, [(mode, content_item_boxes.AWARD) for mode in modes])
        need, stats = content_item_boxes.box_terms(track, slot, capability, package)
        if need:
            box["boost"] = need
        if stats:
            box["stats"] = True
        out.append(box)
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
    entrance requirement too (Wayfinder ticket 16, 2026-09-22). Every later mode
    also needs the first race won (create_regions, stage_gate)."""
    gates = [dict(mode=modes[0], stage=1, requirement_id=first_requirement)]
    for mode in modes[1:]:
        gates.append(dict(mode=mode, stage=2, requirement_id=f"{STAGE2_PREFIX}{physical}") if stages == "two"
                     else dict(mode=mode, stage=1, requirement_id=first_requirement))
    return gates


def crystal_selection(world, raw):
    """(eligible arenas, count): a range draws its count here, as before cups."""
    eligible, (low, high) = crystal_bounds(world, raw)
    return eligible, (low if low == high else world.random.randint(low, high))


def crystal_bounds(world, raw):
    """(eligible arenas, (low, high)) without a draw. With cups (#133 PR 5a)
    the count is drawn together with the cup count (content_cups.feasible_pairs)."""
    o=world.options
    pool=raw.get('pool','all')
    allowed=list(arena_content.ARENAS)
    if pool!='all' and (not isinstance(pool,list) or any(type(i) is not int or i not in allowed for i in pool) or len(set(pool))!=len(pool)):
        error('crystals.pool must be all or distinct arena LevelIDs 18 through 24.')
    eligible=(list(arena_content.ARENAS) if pool=='all' else list(pool))
    if not o.include_battle_arenas.value:
        return [],(0,0)
    if not o.include_arcade_arenas.value:
        if pool!='all' and any(i in arena_content.ARCADE for i in eligible):
            error('an arcade arena in crystals.pool requires include_arcade_arenas.')
        eligible=[i for i in eligible if i not in arena_content.ARCADE]
    count=raw.get('count',0)
    if isinstance(count,dict) and set(count)=={'min','max'}:
        low,high=count['min'],count['max']
        if type(low) is not int or type(high) is not int or not 0<=low<=high<=len(eligible):
            error('crystals.count range exceeds the eligible arena pool.')
        return eligible,(low,high)
    if type(count) is not int or not 0<=count<=len(eligible):
        error('crystals.count must fit the eligible arena pool.')
    return eligible,(count,count)


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
    with_cortex = tracks.get("cortex_vortex", False)
    if type(with_cortex) is not bool:
        error("tracks.cortex_vortex must be true or false.")
    # Cups (#133 PR 5): a count or range and the composition. A plan without
    # cups draws its crystal count exactly as before.
    cup_spec = content_cups.settings(raw.get("cups", {}))
    crystals = closed(raw.get("crystals", {}), ("pool", "count"), "crystals")
    if cup_spec["bounds"][1] == 0:
        arena_pool, arena_count = crystal_selection(world, crystals)
    else:
        arena_pool, crystal_range = crystal_bounds(world, crystals)
    # Boss garages (#133 PR 6): the encounter settings, or None with bosses off.
    boss_record = content_bosses.settings(world, closed(raw.get("bosses", {}), ("enabled", "requirement_level", "cups"), "bosses"))
    layout = closed(o.pad_layout.value, ("placement", "stages", "mode_order", "merge_trophy_ctr"), "pad_layout")
    stages = layout.get("stages", "two")
    mode_order = layout.get("mode_order", "fixed")
    placement = layout.get("placement", "shuffle")
    if placement not in content_requirements.PLACEMENTS:
        error("pad_layout.placement must be vanilla, shuffle_within_kind or shuffle.")
    if stages not in ("single", "two"):
        error("pad_layout.stages must be single or two.")
    if mode_order not in ("fixed", "per_seed", "per_pad"):
        error("pad_layout.mode_order must be fixed, per_seed or per_pad.")
    if layout.get("merge_trophy_ctr", False) is not False:
        error("pad_layout.merge_trophy_ctr: the merged Trophy/CTR race is not built yet; it comes in a "
              "separate change after the track modes. Set merge_trophy_ctr: false. No content was changed.")
    if o.custom_tracks.value or o.cortex_vortex_track.value:
        error("legacy custom_tracks/cortex_vortex_track cannot be mixed with content_pool.")
    # An explicit death_link_send list rides the envelope (#133 PR 4a). No
    # one-way DeathLink (ruling 2026-09-30): the normal seed's resolution, no draw.
    from . import forced_options
    forced_options.resolve_death_link_off_when_send_conditions_set(world)
    # Character packs (#133 PR 4b): the normal seed's refusal and notes for
    # the character options. They take no draw.
    forced_options.raise_if_starting_as_removed_oxide(world)
    for note in (forced_options.warn_editable_stats_overridden_by_progressive,
                 forced_options.warn_penta_stats_without_vanilla_stats,
                 forced_options.warn_racer_locked_pads_boolean_normalized,
                 forced_options.warn_racer_locks_without_character_unlocks,
                 forced_options.warn_remove_playable_oxide_without_character_unlocks):
        note(world)
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
    # Cortex Vortex is a candidate only when selected, so a plan without it
    # draws exactly as before (#133 PR 3c).
    if with_cortex:
        pool.append((cortex_track(), None, {}))
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
    cup_count = 0
    if cup_spec["bounds"][1]:
        # One uniform draw among the feasible (cups, crystals) pairs (#133 PR
        # 5), never one count drawn first and the other trimmed.
        legs_other, legs_custom = content_cups.leg_pools(candidates, package_by_id, cup_spec["sources"])
        fixed_legs = content_cups.fixed_legs(cup_spec, candidates)
        pairs = content_cups.feasible_pairs(cup_spec, crystal_range, len(arena_pool), len(chosen_arenas),
                                            len(required) - len(chosen_arenas), legs_other, legs_custom, fixed_legs)
        if not pairs:
            repeats = cup_spec["repeats"]
            error(f"no cup and crystal counts fit: cups.count {cup_spec['bounds'][0]} to {cup_spec['bounds'][1]}, "
                  f"crystals.count {crystal_range[0]} to {crystal_range[1]} of {len(arena_pool)} eligible arenas, "
                  f"{len(required)} required entries, {len(legs_other)} retail and {len(legs_custom)} custom or "
                  f"Cortex Vortex leg tracks, custom_legs {cup_spec['custom_legs'][0]} to "
                  f"{cup_spec['custom_legs'][1]} per cup (repeats within a cup "
                  f"{'on' if repeats['within_cup'] else 'off'}, across cups "
                  f"{'on' if repeats['across_cups'] else 'off'}), and 27 normal pads"
                  + (f", with cups.tracks off and tracks.retail leaving {len(fixed_legs)} of the five Gem Cups "
                     "their original tracks" if fixed_legs is not None else "")
                  + ". No content count was changed.")
        cup_count, arena_count = world.random.choice(pairs)
    if len(chosen_arenas)>arena_count:
        error('required arena entries exceed crystals.count; no content count was changed.')
    chosen_arenas+=world.random.sample([a for a in arena_candidates if a['id'] not in required],arena_count-len(chosen_arenas))
    chosen = [t for t in candidates if t["id"] in required]
    if len(chosen)+arena_count+cup_count>27:
        error('required entries and selected arenas exceed the 27 normal pads.')
    optional = [t for t in candidates if t["id"] not in required]
    chosen += world.random.sample(optional, min(len(optional), 27 - len(chosen) - arena_count - cup_count))
    chosen += chosen_arenas
    cups = []
    if cup_count:
        # The first five are the Gem Cups; a sixth cup onward takes a name
        # from the pool (#133 PR 5). They are seated with the other entries.
        cups = content_cups.draw_cups(world, cup_count, legs_other, legs_custom, cup_spec,
                                      bool(o.one_lap_cups.value), fixed_legs)
    # Room titles of the seed's custom tracks, also those raced only as cup legs.
    raced = [t for t in chosen if t.get("origin") == "custom"]
    for cup in cups:
        raced += [t for t in cup["legs"] if t.get("origin") == "custom" and t not in raced]
    titles = generic_room_titles(sorted(raced, key=lambda t: t["custom_slot"]), package_by_id)
    for track in raced:
        if "named_block" not in track:
            track["room_title"] = titles[track["custom_slot"]]
    chosen += cups
    manual = manual_rules(o)
    unlock_mode = int(o.warppad_unlock_requirements.value)
    if unlock_mode and not warp_pad_logic.effective_custom_weights(world)["Trophy"]:
        error("requirement_weights Trophy must stay above 0: at the start the simulated player only holds Trophies.")
    # Reserve every named physical seat for selected content, then keep the
    # other seats in their shuffled order. A rule never disappears because its
    # seat drew empty, and no content or item is added to fit it.
    if len(manual) > len(chosen):
        error(f"warp_pad_rules names {len(manual)} pads, but only {len(chosen)} "
              "entries are selected; name fewer pads or select more content. "
              "No content or items were added.")
    settings = family_settings(o)
    capability = content_capability.settings(o)
    held = starting_counts(o)
    # Items fixed to their check (one generator row 4). Nothing is drawn.
    fixed = content_fixed.settings(o, boss_record, [cup["gem_cup"] for cup in cups if cup.get("gem_cup") is not None])

    def opens_at_start(seat):
        # Hub gate free, and a manual rule or the pad's vanilla requirement met
        # by the real start. Random pads are settled by the free subset below.
        physical, _hub, keys = seat
        rule = (content_requirements.vanilla_rule(physical) if unlock_mode == 0 else manual.get(physical))
        return keys == 0 and rule_met(rule, held)

    def seat_reach(seat):
        # 2: opens at the start. 1: a vanilla pad a few Trophies behind it.
        if opens_at_start(seat):
            return 2
        rule = content_requirements.vanilla_rule(seat[0]) if unlock_mode == 0 else None
        return int(seat[2] == 0 and rule is not None and rule[0] == "Trophy" and rule[1] <= VANILLA_NEAR_TROPHIES)

    def start_checks(item):
        # Checks a pad's content opens with no items: the first race and its
        # rungs that need no boost rank. Modes in their fixed order are enough
        # to judge a start; the seed's real start is measured in generate_basic.
        if not is_track(item):
            if "gems" in fixed and item.get("gem_cup") is not None:
                return 0
            return 0 if capability.get("boost_mode") and "cup_index" in item else 1
        if not capability.get("boost_mode"):
            count = 1 + len(settings.get("podium_rungs", ()))
        else:
            package = package_by_id.get(item.get("package_id"))
            terms = [("trophy", "win")] + [("podium", key) for key in settings.get("podium_rungs", ())]
            count = sum(not content_capability.check_boost(item, kind, award, capability, package, None)
                        for kind, award in terms)
        # A fixed Gem Cup opens nothing, and a drawn mode order can put a race
        # with one check first, so the other open pad may be all the start has.
        return min(count, 1) if "gems" in fixed and mode_order != "fixed" else count

    first_key_floor = content_fixed.FIRST_KEY_CHECKS if unlock_mode == 0 and "keys" in fixed else 0

    def needs_own_gem(physical, item):
        return (unlock_mode == 0 and "gems" in fixed and physical == content_fixed.GEM_PAD
                and item.get("gem_cup") is not None)

    chosen, registry = content_requirements.seat_content(world, chosen, pad_registry(), placement, manual,
                                                         len(settings.get("podium_rungs", ())),
                                                         seat_reach if unlock_mode == 0 else None, start_checks,
                                                         needs_own_gem, first_key_floor)
    # Empty pads are valid, but a fresh Adventure must start with at least
    # sphere0_guard.MIN_STARTING_CHECKS open checks (start-check rulings
    # 2026-10-01 and 2026-10-02), or generate_basic refuses the slot. Keep
    # content/counts and every physical gate unchanged and grant no item: only
    # a layout that falls short exchanges a gated occupied seat with an open
    # empty one, until enough open seats hold content. A layout that already
    # has enough takes no draw here, so its seed is unchanged.
    need = min(len(chosen), sphere0_guard.MIN_STARTING_CHECKS)
    while sum(opens_at_start(seat) for seat in registry[:len(chosen)]) < need:
        # A named seat is never exchanged, so its rule stays where it was set.
        gated = [i for i in range(len(chosen))
                 if not opens_at_start(registry[i]) and registry[i][0] not in manual]
        empty = [i for i in range(len(chosen), len(registry)) if opens_at_start(registry[i])]
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
    letters = {}
    if settings.get("lettersanity") in (1, 2):
        for index, track in enumerate(chosen):
            if "ctr" in track.get("modes", ()):
                letters[index] = tuple(sorted(LETTERS.index(letter) for letter in
                                              world.random.sample(LETTERS, settings["letters_per_track"])))
    letter_packs = {}
    for index, track in enumerate(chosen):
        if is_track(track):
            for i in letter_layout(track, settings, letters.get(index, ()))[1]:
                name, code = letter_item(track, i)
                letter_packs[name] = code
    # Relic tier checks follow the item counts (ruled 2026-10-30), so a tier is
    # drawn before the ledger is sized, among the tracks raced as a Relic Race.
    # With vanilla requirements and Gems fixed, the Relic Race on the physical
    # five-Gem pad holds no tier check (content_fixed); the item counts stay.
    guarded = next((chosen[i]["id"] for i in range(len(chosen)) if unlock_mode == 0 and "gems" in fixed
                    and registry[i][0] == content_fixed.GEM_PAD and is_track(chosen[i])
                    and "relic" in chosen[i]["modes"]), None)
    relics = draw_relic_checks(world, [t["id"] for t in chosen if is_track(t) and "relic" in t["modes"]
                                       and t["id"] != guarded],
                               content_item_pool.relic_totals(o.item_pool.value))
    if guarded is not None:
        relics[guarded] = set()
    # Cups (#133 PR 5): the leg tracks' records, and the sweep check switch.
    track_records = {t["id"]: t for t in candidates}
    sweep = bool(o.cup_sweep_checks.value) and bool(cup_count)
    # Every check exists before the item ledger is sized; mode order and the
    # pad requirements only decide which race and gate reaches each one.
    # Item Box Locations (#133 PR 4e): per-track box checks.
    item_boxes = content_item_boxes.settings(o)
    # Boss garages (#133 PR 6): the four venues (the retail pairs, or the #169
    # tier 1 draw, one draw only with boss_track_shuffle on) and the Final
    # Challenge venue. Nothing is drawn with bosses off.
    boss_venues, boss_final, boss_cups = ({}, None, {})
    if boss_record is not None:
        # A custom track is a boss venue only where the plan also races it
        # on a pad or in a cup (#133 PR 6b; native checks its record there).
        raced = ({t["id"] for t in chosen if is_track(t)}
                 | {leg["id"] for cup in chosen if "cup_index" in cup for leg in cup["legs"]})
        boss_custom = [(content_bosses.venue_key(t),
                        content_bosses.custom_venue_points(t, package_by_id.get(t.get("package_id"))))
                       for t in candidates if t.get("origin") == "cortex_vortex"
                       or (t.get("origin") == "custom" and t["id"] in raced)]
        boss_venues = content_bosses.draw_venues(world, boss_record, boss_custom)
        boss_final = (destinations.CORTEX_VORTEX if int(o.oxide_final_track.value) == 0
                      else content_bosses.OXIDE_STATION)
        # Boss cups (#133 PR 6b): which garages hold a cup, and their legs.
        boss_cups = content_bosses.draw_cups(world, boss_record, boss_custom)
    check_count = sum(len(track_checks(t, "entry/" + t["id"], "pad:0", t["modes"], settings, letters.get(index, ()),
                                       package_by_id.get(t.get("package_id")), item_boxes=item_boxes,
                                       relics=relics.get(t["id"])))
                      if is_track(t)
                      else len(content_cups.checks(content_cups.entry(t), "pad:0", track_records, None, None,
                                                   sweep)) if "cup_index" in t
                      else len(arena_content.checks(dict(id="entry/" + t["id"], kind="crystal", arena_id=t["arena_id"],
                                                         target=20, time_limit_ticks=arena_content.TIMERS[t["arena_id"]]),
                                                    "pad:0", bool(o.crystalsanity.value)))
                      for index, t in enumerate(chosen))
    if settings.get("wumpa") == "global" and any(
            wumpa_modes(t, package_by_id.get(t.get("package_id"))) for t in chosen if is_track(t)):
        check_count += 1
    # Cup Leg Victory (#133 PR 5): one per leg track without a Trophy Race pad.
    check_count += len(cup_leg_tracks(chosen))
    # Boss garages (#133 PR 6): one check per encounter.
    if boss_record is not None:
        check_count += len(content_bosses.encounter_rows(boss_record, boss_venues, boss_final))
    # Itemsanity and Hit Character (#133 PR 4d): global checks, routed from
    # every race that can earn them once the pads are assigned.
    global_checks = content_global_checks.settings(o)
    check_count += content_global_checks.check_count(global_checks, [t for t in chosen if "cup_index" not in t],
                                                     package_by_id,
                                                     [leg for t in chosen if "cup_index" in t for leg in t["legs"]])
    # Pool-only packs (#133 PR 4a) take ledger rows like the letter items; they
    # use slots that would otherwise be filler, as on the legacy path.
    packs = pack_settings(o)
    selected = {name: 1 for name in letter_packs}
    selected.update(pack_counts(packs))
    # Character unlocks (#133 PR 4b): one ledger row per unlock racer, which
    # needs the starting racer first. A plan with unlocks off keeps its draw
    # at the end, so its seed is unchanged.
    racers = None
    if characters.unlocks_enabled(world):
        world.ctr_starting_character = characters.resolve_starting_character(world)
        racers = dict(starting_character=characters.ROSTER_CHARACTER_ID[world.ctr_starting_character],
                      remove_playable_oxide=characters.oxide_removed(world), requested_locks=0)
        selected.update({name: 1 for name in unlock_names(racers)})
    # Capability packs (#133 PR 4c): the boost and stat chains, as many copies
    # as on the legacy path (progressive_capability.created_item_counts).
    selected.update(content_capability.item_counts(capability))
    # Itemsanity (#133 PR 4d): one row per weapon item.
    selected.update(content_global_checks.item_counts(global_checks))
    # Boss garages (#133 PR 6): the Oxide goal location holds filler only
    # (issue #27, excluded from progression), so the ledger keeps one filler
    # slot for it, as the legacy rung sizer reserves one. The surface items
    # stay out of that slot and of the slots a player's exclude_locations need.
    oxide_filler = (boss_record is not None
                    and boss_record["oxide_goal"] in (content_bosses.GOAL_ANY, content_bosses.GOAL_FINAL))
    # Fixed items hold their checks first, so the ledger sizes what is left. An
    # excluded check that holds one needs no filler.
    base_counts, extra_counts = content_item_pool.normalize(o.item_pool.value)
    pins = content_fixed.placements(fixed, base_counts,
                                    {name: base_counts[name] + extra_counts[name]
                                     - o.start_inventory_from_pool.value.get(name, 0) for name in base_counts})
    world.ctr_content_items = content_item_pool.resolve(
        o.item_pool.value, check_count, starts=o.start_inventory_from_pool.value,
        additional=o.start_inventory.value, trap_percentage=o.trap_fill_percentage.value,
        locked=content_fixed.locked_copies(pins), locked_checks=len(pins),
        surface=content_item_pool.SURFACE_NAMES,
        filler_reserve=int(oxide_filler) + len(set(o.exclude_locations.value)
                                               - {LOCATION_BY_CODE[code] for code in pins}),
        **(dict(selected_packs=selected, pack_codes=letter_packs) if selected else {}))
    if oxide_filler and world.ctr_content_items.filler_count < 1:
        error("the Oxide goal check holds only filler, but the item pool fills every check: "
              f"{check_count} checks for {check_count} selected copies. Lower an item_pool count or extra, or add "
              "content, so one filler slot is left. Your settings were not changed.")
    # Mode order (Wayfinder ticket 16): fixed Trophy, CTR, Relic; one order for
    # the whole seed; or one per pad. Only entries with two or more modes take a
    # draw, so a Trophy-only plan draws nothing here.
    multi = [index for index in range(len(chosen)) if len(chosen[index].get("modes", ())) > 1]
    # With Lettersanity 2 or 3 a CTR Challenge needs letter items, so it is
    # never a pad's first mode when the pad has another (ruling 2026-10-17):
    # a CTR-first start would open no check. A fixed or per-seed order moves
    # it one place back; a per-pad order puts it at a uniformly drawn later
    # place. Seeds without those Lettersanity modes draw exactly as before.
    ctr_last = settings.get("lettersanity") in (2, 3)

    def draw_mode_order():
        seed_order = list(MODES)
        if mode_order == "per_seed" and multi:
            world.random.shuffle(seed_order)
        # A Relic Race with no tier check is not a pad's first mode either: no check
        # proves its win, and a Perfect check is more than a win. The CTR rule wins
        # on a pad with only those two modes, whose later race then counts on its
        # items alone.
        out = {}
        for index in multi:
            modes = list(chosen[index]["modes"])
            if mode_order == "per_pad":
                world.random.shuffle(modes)
            else:
                modes.sort(key=seed_order.index)
            if modes[0] == "relic" and not relics.get(chosen[index]["id"]):
                modes.append(modes.pop(0))
            if ctr_last and modes[0] == "ctr":
                if mode_order == "per_pad":
                    modes.insert(world.random.randint(1, len(modes) - 1), modes.pop(0))
                else:
                    modes[0], modes[1] = modes[1], modes[0]
            out[index] = modes
        return out

    def first_key_checks(orders):
        # Checks open before a fixed first Key: the first race of the pads
        # seat_content calls near the start.
        total = 0
        for index, item in enumerate(chosen):
            if not seat_reach(registry[index]):
                continue
            if not is_track(item):
                total += start_checks(item)
                continue
            modes = orders.get(index, item["modes"])
            total += sum(any(r["mode"] == modes[0] for r in c["routes"]) and not c.get("boost")
                         for c in track_checks(item, "entry/" + item["id"], "pad:0", modes, settings, letters.get(index, ()),
                                               package_by_id.get(item.get("package_id")), capability, item_boxes,
                                               relics.get(item["id"])))
        return total

    # Mode order (Wayfinder ticket 16): fixed Trophy, CTR, Relic; one order for
    # the whole seed; or one per pad. Only entries with two or more modes take a
    # draw, so a Trophy-only plan draws nothing here. A drawn order that leaves a
    # fixed first Key short of checks draws again; the best one stands.
    entry_modes = draw_mode_order()
    if first_key_floor and mode_order != "fixed" and multi:
        best = first_key_checks(entry_modes)
        for _ in range(content_requirements.PLACEMENT_REDRAWS):
            if best >= first_key_floor:
                break
            orders = draw_mode_order()
            if first_key_checks(orders) > best:
                entry_modes, best = orders, first_key_checks(orders)
    entries, pads, checks = [], [], []
    requirements = [dict(id="free", predicate=dict(op="always"))]
    requirements += [dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)]
    for index, (physical, hub, keys) in enumerate(registry):
        pad = dict(id=f"pad:{physical}", hub_id=f"hub:{hub}", kind="normal", entry_id=None,
                   entrance_req=f"keys:{keys}" if keys else "free", mode_gates=[], racer_lock=None)
        if index < len(chosen):
            track = chosen[index]
            entry_id = "entry/" + track["id"]
            crystal='arena_id' in track
            cup = "cup_index" in track
            if cup:
                entry = content_cups.entry(track)
                entry_id = entry["id"]
            elif crystal:
                entry=dict(id=entry_id,kind='crystal',arena_id=track['arena_id'],target=20,
                           time_limit_ticks=arena_content.TIMERS[track['arena_id']])
            else:
                modes = entry_modes.get(index, track["modes"])
                entry = dict(id=entry_id, kind='track', track_id=track['id'], modes=modes, merged=False)
            entries.append(entry)
            pad.update(entry_id=entry_id)
            if cup:
                checks.extend(content_cups.checks(entry, pad["id"], track_records, capability, package_by_id, sweep))
            elif crystal:
                checks.extend(arena_content.checks(entry,pad['id'],bool(o.crystalsanity.value)))
            else:
                checks.extend(track_checks(track, entry_id, pad['id'], entry['modes'], settings,
                                           letters.get(index, ()), package_by_id.get(track.get("package_id")),
                                           capability, item_boxes, relics.get(track["id"])))
        pads.append(pad)
    standalone = [t for t in chosen if is_track(t)]
    plan_tracks = standalone + cup_only_tracks(standalone, entries, track_records)
    checks.extend(content_cups.leg_victories({t["id"]: t for t in plan_tracks}, entries, pads,
                                             {t["id"]: room_title(t) for t in plan_tracks}))
    if settings.get("wumpa") == "global":
        wumpa = global_wumpa_check(global_wumpa_routes(standalone, entries, pads, package_by_id))
        if wumpa:
            checks.append(wumpa)
    gem_ids = [r.item for r in world.ctr_content_items.rows if r.name.endswith(" Gem") and r.base]
    gem_term = (dict(op="distinct", items=gem_ids, count=o.gems_required_goal.value)
                if o.gems_required_goal.value else None)
    # Boss garages (#133 PR 6): the encounters, their boss race entries,
    # requirements and checks, and the venues raced nowhere else as plan
    # tracks (the trophy mode only, like a track raced only in cups).
    encounters, boss_entries, boss_requirements, boss_checks, boss_hits = [], [], [], [], {}
    if boss_record is not None:
        content_bosses.resolve_relic_count(world, boss_record, world.ctr_content_items.rows)
        have = {t["id"] for t in plan_tracks}
        for name in [v for g, v in boss_venues.items() if g not in boss_cups] \
                + [leg for g in sorted(boss_cups) for leg in boss_cups[g]] + ([content_bosses.OXIDE_STATION, boss_final]
                                                  if boss_record["oxide_goal"] != content_bosses.GOAL_DISABLED else []):
            record = content_bosses.venue_record(name, RETAIL, cortex_track(),
                                                 {t["id"]: t for t in candidates if t.get("origin") == "custom"})
            if record["id"] not in have:
                have.add(record["id"])
                plan_tracks.append(record)
        garage_reqs = content_fixed.draw_garages(world, boss_record, world.ctr_content_items.rows, unlock_mode == 0,
                                                 pins, pads)
        encounters, boss_entries, boss_requirements, boss_checks = content_bosses.build(
            boss_record, boss_venues, boss_final, world.ctr_content_items.rows, gem_term, capability,
            {t["id"]: t for t in plan_tracks}, garage_reqs, boss_cups, content_requirements.MODES[unlock_mode])
        boss_hits = content_bosses.hit_routes(dict(entries=boss_entries, encounters=encounters))
    checks.extend(content_global_checks.checks(global_checks, plan_tracks, entries, pads, package_by_id, boss_hits))
    checks.extend(boss_checks)
    for boss in range(5):
        gate = content_bosses.garage_gate(boss, any(e["pad_id"] == f"garage:{boss}" for e in encounters))
        pads.append(dict(id=f"garage:{boss}", hub_id=f"hub:{26 + boss if boss < 4 else 25}",
                         kind="garage", entry_id=None, entrance_req=gate, mode_gates=[], racer_lock=None))
    assert len(checks) == check_count
    # Archipelago fills an excluded check from filler alone. The names that are
    # checks of this seed count; the ledger's reserve above is an upper bound.
    goal_check = content_bosses.goal_location(boss_record) if oxide_filler else None
    excluded = len(set(o.exclude_locations.value) & {LOCATION_BY_CODE[c["location"]] for c in checks
                                                     if c["location"] != goal_check and c["location"] not in pins})
    if excluded + oxide_filler > world.ctr_content_items.filler_count:
        error(f"exclude_locations names {excluded} checks of this seed and the item pool leaves "
              f"{world.ctr_content_items.filler_count} filler slots"
              + (", one of them for the Oxide goal check" if oxide_filler else "")
              + ". An excluded check holds only filler. Lower an item_pool count or exclude fewer checks.")
    if manual:
        requirements += manual_requirements(manual, world.ctr_content_items.rows)
        world._ctr_pad_rules = {key: manual[lid] for lid, key in PAD_KEY_BY_LEVEL_ID.items()
                                if lid in manual}
    # Pad requirements (one generator row 3), once every check, the garages and
    # the ledger exist: the reference placement needs them all.
    by_name = {row.name: row for row in world.ctr_content_items.rows}
    pad_modes = {pad_physical(pad): next(e for e in entries if e["id"] == pad["entry_id"]).get("modes", ())
                 for pad in pads if pad["entry_id"] is not None}
    density_off = stages == "single" or not o.two_stage_density.value
    if unlock_mode == 0:
        stage1, stage2 = content_requirements.vanilla_requirements(pad_modes, by_name, density_off)
    else:
        stage1, stage2 = draw_pad_requirements(world, pads, pad_modes, entries + boss_entries, checks, encounters,
                                               boss_requirements, manual, by_name, unlock_mode, density_off,
                                               oxide_filler and goal_check, pins, boss_record)
    requirements += [dict(id=f"{content_requirements.STAGE1_PREFIX}{physical}", predicate=stage1[physical])
                     for physical in sorted(stage1)]
    gate_for = {physical: "free" if rule is None else f"manual:{physical}" for physical, rule in manual.items()}
    gate_for.update({physical: f"{content_requirements.STAGE1_PREFIX}{physical}" for physical in stage1})
    for pad in pads:
        if pad["entry_id"] is not None:
            physical = pad_physical(pad)
            pad["mode_gates"] = pad_gates(next(e for e in entries if e["id"] == pad["entry_id"]),
                                          gate_for.get(physical, "free"), physical in stage2, physical)
    requirements += [dict(id=f"{STAGE2_PREFIX}{physical}", predicate=stage2[physical]) for physical in sorted(stage2)]
    if o.gems_required_goal.value > len(gem_ids):
        error("Gem goal exceeds the selected distinct base Gem colours.")
    requirements += boss_requirements
    entries += boss_entries
    pad_record = dict(mode=content_requirements.MODES[unlock_mode])
    plan = dict(version=1, packages=[p for p in packages if any(t.get("package_id") == p["id"] for t in plan_tracks)],
                tracks=plan_tracks, entries=entries, pads=pads, encounters=encounters, requirements=requirements,
                checks=checks, items=world.ctr_content_items.wire(), goal=content_bosses.goal(boss_record, gem_term),
                required_features=required_features(requirements,entries,checks,settings,packs,racers,capability,
                                                    global_checks,item_boxes,boss_record,
                                                    world.ctr_content_items.wire()["rows"], pad_record, fixed, guarded),
                pad_requirements=pad_record)
    if fixed:
        plan["fixed_items"] = fixed
    if settings:
        plan["track_checks"] = settings
    if packs:
        plan["item_packs"] = packs
    if capability:
        plan["capability"] = capability
    if global_checks:
        plan["global_checks"] = global_checks
    if item_boxes:
        plan["item_boxes"] = item_boxes
    if boss_record is not None:
        plan["bosses"] = boss_record
    world.ctr_racer_locks, world.ctr_racer_lock_counts = {}, {"requested": 0, "eligible": 0}
    if racers:
        # Racer locks (#133 PR 4b) go on pads that do not open at the start,
        # once the layout and the ledger are final.
        racers["requested_locks"] = characters.requested_lock_count(world, len(lock_eligible(plan)))
        plan["racers"] = racers
        draw_racer_locks(world, plan, racers)
        world.ctr_racer_locks = plan_racer_locks(plan)
    validate(plan)
    world.ctr_content_plan = plan
    # Item links (#133 PR 4f): Main.py has already formed the groups.
    content_item_pool.check_item_links(world)
    # Actual native 0.6.7 protocol/handshake validation is a release gate. This
    # room barrier already prevents the rc1 client's default 0.6.4 admission.
    world.required_client_version = (0, 6, 7)
    world.ctr_content_original_starts = copy.deepcopy(o.start_inventory_from_pool.value)
    if racers is None:
        world.ctr_starting_character = characters.resolve_starting_character(world)
    # Hit Character (#133 PR 4d): the encounter block's roster seed, its only
    # draw, and the fallback from the plan's checks. Itemsanity: one weapon
    # type marked early, the legacy draw (item_creation.create_items). Neither
    # draws while its option is off, so other plans are unchanged.
    world.ctr_hit_character_encounters, world.ctr_hit_character_fallback = None, {}
    if global_checks.get("hit_character"):
        content_global_checks.encounter_block(world, plan)
    if global_checks.get("itemsanity"):
        from .itemsanity import WEAPONS
        early_count = world.random.randint(1, 2)
        weapon = world.random.sample(WEAPONS, early_count)[0]
        world.multiworld.early_items.setdefault(world.player, {})[weapon] = 1
    return plan


def pad_physical(pad):
    return int(pad["id"].split(":")[1])


def pad_gates(entry, first, two_stages, physical):
    """A pad's mode gates from its entry and stage-1 requirement id."""
    if entry["kind"] == content_cups.KIND:
        return content_cups.mode_gates(first)
    if entry["kind"] == "crystal":
        return [dict(mode="crystal", stage=1, requirement_id=first)]
    return mode_gates(entry["modes"], first, "two" if two_stages else "single", physical)


def draw_pad_requirements(world, pads, pad_modes, entries, checks, encounters, boss_requirements, manual, by_name,
                          mode, density_off, goal_check, pins, boss_record):
    """({physical: stage 1 predicate}, {physical: stage 2 predicate}) of the two
    random modes, from the simulated playthrough over the reference placement
    (content_requirements). A manual pad keeps its rule at stage 1; a pad whose
    two stages came out equal has no second stage."""
    skip = set(world.options.exclude_locations.value)
    skip = {code for code in LOCATION_BY_CODE if LOCATION_BY_CODE[code] in skip} | ({goal_check} if goal_check else set())
    relics = {name: by_name[name].requirement_ceiling for name in warp_pad_rules.RELICS}
    multi = sum(len(modes) > 1 for modes in pad_modes.values())

    def simulate():
        stands = content_requirements.stand_ins(world, checks, entries, pads, pad_modes,
                                                world.ctr_content_items.rows, skip, pins)
        view = content_requirements.ReferenceWorld(world, pads, pad_modes, checks, encounters,
                                                   {row["id"]: row["predicate"] for row in boss_requirements},
                                                   stands, relics, ITEM_BY_CODE, frozenset(pins))
        return content_requirements.draw(view, mode, density_off)

    drawn = simulate()
    # A fixed Key behind a garage the simulated player cannot open leaves every
    # later pad without a second stage. Such a roll draws the garages again; the
    # roll with the most second stages stands.
    if "Key" in pins.values() and not density_off:
        garages = [row for row in boss_requirements if row["id"].startswith("boss:")]
        seconds = lambda result: sum(pair[1] is not None for pair in result.values())
        best, kept = drawn, [row["predicate"] for row in garages]
        for _ in range(content_fixed.GARAGE_REDRAWS if seconds(drawn) < multi else 0):
            for row, predicate in zip(garages, content_fixed.draw_garages(
                    world, boss_record, world.ctr_content_items.rows, False, pins, pads).values()):
                row["predicate"] = predicate
            drawn = simulate()
            if seconds(drawn) > seconds(best):
                best, kept = drawn, [row["predicate"] for row in garages]
            if seconds(best) >= multi:
                break
        for row, predicate in zip(garages, kept):
            row["predicate"] = predicate
        drawn = best
    stage1, stage2 = {}, {}
    for title, (first, second) in drawn.items():
        physical = next(lid for lid, key in PAD_KEY_BY_LEVEL_ID.items() if key == title)
        if physical in manual:
            first = manual[physical]
        elif first:
            stage1[physical] = content_requirements.rule_predicate(first, by_name)
        if second and second != first and len(pad_modes[physical]) > 1:
            stage2[physical] = content_requirements.rule_predicate(second, by_name)
    return stage1, stage2


def is_track(item):
    """A drawn standalone track, not a crystal arena or a cup (#133 PR 5)."""
    return "arena_id" not in item and "cup_index" not in item


def cup_leg_tracks(chosen):
    """Ids of the leg tracks of the drawn cups that hold no standalone Trophy
    Race, each once: the tracks that take a Cup Leg Victory check."""
    trophy = {t["id"] for t in chosen if is_track(t) and "trophy" in t["modes"]}
    return {leg["id"] for cup in chosen if "cup_index" in cup for leg in cup["legs"]} - trophy


def cup_only_tracks(standalone, entries, records):
    """Track records of cup legs whose track holds no standalone pad (#133 PR
    5), in order of first leg. Their modes are `trophy` only: a cup leg is a
    Trophy-style race, and no mode-owned check exists for them."""
    have = {t["id"] for t in standalone}
    out = []
    for entry in entries:
        for leg in entry["legs"] if entry["kind"] == content_cups.KIND else ():
            if leg["track_id"] not in have:
                have.add(leg["track_id"])
                out.append(dict(records[leg["track_id"]], modes=["trophy"], capabilities=["trophy"]))
    return out


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
    if node["op"] == "checked":
        # Encounters the player personally won (#133 PR 6): their companion
        # events, never the location's checked state (content_bosses.EVENTS).
        events = [content_bosses.EVENTS[code] for code in node["locations"]]
        return lambda state: sum(state.has(name, player) for name in events) >= node["count"]
    if node["op"] in ("all", "any"):
        tests = tuple(predicate(world, term) for term in node["terms"])
        if node["op"] == "all":
            return lambda state: all(t(state) for t in tests)
        return lambda state: any(t(state) for t in tests)
    error("unsupported predicate in experimental content plan.")


def create_regions(world):
    mw, player, plan = world.multiworld, world.player, world.ctr_content_plan
    menu = Region("Menu", player, mw)
    mw.regions.append(menu)
    req = {r["id"]: r["predicate"] for r in plan["requirements"]}
    pad_by_id = {pad["id"]: pad for pad in plan["pads"]}
    # Lettersanity items a check needs on top of its route (#133 PR 3b).
    letters_needed = letter_requirements(plan)
    from .progressive_capability import gate_satisfied

    # With Itemsanity on (#133 PR 4d), the legacy weapon alternatives to a
    # first-boost floor (content_capability.weapon_arm).
    weapons = bool(plan.get("global_checks", {}).get("itemsanity"))
    track_by_id = {t["id"]: t for t in plan["tracks"]}
    package_by_id = {p["id"]: p for p in plan["packages"]}
    from .itemsanity import USEFUL_WEAPON_FAMILIES, family_count

    from .progressive_capability import STAT_CHAINS

    def with_boost(rule, check):
        """A check's boost rank (#133 PR 4c), and an Item Box check's stat
        term (#133 PR 4e, one copy of each stat chain), bound to its pad's racer
        lock: one racer must meet both, as the legacy box gate reads it."""
        need = check.get("boost", 0)
        stat_mins = {chain: 1 for chain in STAT_CHAINS} if check.get("stats") else None
        if not need and not stat_mins:
            return rule
        lock = pad_by_id[check["routes"][0]["own_pad_id"]]["racer_lock"]
        racer = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        track = track_by_id.get(check["owner"])
        arm = (content_capability.weapon_arm(track, check["kind"], check["routes"][0]["award"], plan["capability"],
                                             package_by_id.get(track.get("package_id")))
               if weapons and track is not None and need == 1 else None)

        def has_boost(state, need=need, racer=racer, arm=arm, stat_mins=stat_mins):
            if gate_satisfied(world, state, player, boost_min=need, stat_mins=stat_mins, required_character=racer):
                return True
            if arm is None:
                return False
            if arm[0] == "families":
                return family_count(state, player, USEFUL_WEAPON_FAMILIES) >= arm[1]
            return state.has_any(arm[1], player)
        return has_boost if rule is None else (lambda state, rule=rule: rule(state) and has_boost(state))

    def first_race(pad):
        """Codes of the checks that prove the pad's first race was won, those
        of its first mode. Empty when the mode holds no check of its own (a
        Relic Race with no tier check): then only the items count, as on
        native. Empty too on a pad with one race, and on a plan from before
        `pad_requirements_v1`."""
        modes = [g["mode"] for g in pad["mode_gates"]]
        if len(modes) < 2 or "pad_requirements" not in plan:
            return ()
        return tuple(c["location"] for c in by_pad.get(pad["id"], ()) if c["kind"] == modes[0])

    def stage_gate(route):
        """The test of a route's later race, or None for a pad's first race. A
        later race counts only once the pad's first race is won, on every pad
        (ruled 2026-10-30), and a stage-2 mode also needs its requirement."""
        pad = pad_by_id[route["own_pad_id"]]
        gates = pad["mode_gates"]
        if not gates or gates[0]["mode"] == route["mode"]:
            return None
        rid = next((g["requirement_id"] for g in gates if g["mode"] == route["mode"] and g["stage"] == 2), None)
        items = predicate(world, req[rid]) if rid is not None else None
        won = first_race(pad)
        if items is None and not won:
            return None

        def test(state, items=items, won=won):
            return ((items is None or items(state))
                    and (not won or any(placed[code].can_reach(state) for code in won)))
        return test

    def with_letters(rule, check):
        names = letters_needed.get(check["location"])
        if not names:
            return rule
        def has_letters(state, names=names):
            return state.has_all(names, player)
        return has_letters if rule is None else (lambda state, rule=rule: rule(state) and has_letters(state))

    # Boss garages (#133 PR 6): one region per encounter, behind its garage's
    # hub gate and its own requirement, with its check and companion event.
    if plan["encounters"]:
        content_bosses.install(world, plan, menu, predicate, lambda rule, check: with_boost(rule, check))
    by_pad = {}
    # Locations by code: Universal Tracker renames custom tracks' locations, so
    # a rule holds the Location, not its name.
    placed = {}
    shared = []
    legs = []
    for check in plan['checks']:
        if check["kind"] in content_bosses.KINDS:
            continue
        if check["kind"] == content_cups.LEG_KIND:
            legs.append(check)  # Cup Leg Victory (#133 PR 5), one route per leg occurrence
            continue
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
        # stage-1 gate of a pad shares one record). A later mode's checks also
        # need the first race won and, on a stage-2 mode, that mode's own gate.
        first = [g["requirement_id"] for g in pad["mode_gates"] if g["stage"] == 1][:1]
        gates = [predicate(world, req[rid]) for rid in [pad["entrance_req"]] + first]
        # A racer lock (#133 PR 4b) is ANDed onto the pad's own gates, never in
        # place of them (Rules.add_racer_lock_rules on the legacy path).
        if pad["racer_lock"] is not None:
            racer = characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
            gates.append(lambda state, racer=racer: state.has(racer, player))
        menu.connect(region, pad["id"], gates[0] if len(gates) == 1 else
                     (lambda state, gates=tuple(gates): all(g(state) for g in gates)))
        for check in by_pad.get(pad['id'], ()):
            location = Location(player, LOCATION_BY_CODE[check['location']], check['location'], region)
            placed[check["location"]] = location
            # A check with several routes on its pad (per-track Wumpa) is open
            # when any of them is: a stage-1 route opens it with the pad.
            tests = [stage_gate(r) for r in check["routes"]]
            rule = None
            if all(test is not None for test in tests):
                rule = tests[0] if len(tests) == 1 else (lambda state, tests=tuple(tests): any(t(state) for t in tests))
            rule = with_boost(with_letters(rule, check), check)
            if rule is not None:
                location.access_rule = rule
            region.locations.append(location)
    # Itemsanity and Hit Character checks (#133 PR 4d) take their rules in
    # set_rules, once every trigger location exists.
    world.ctr_global_routes = []
    for check in shared:
        location = Location(player, LOCATION_BY_CODE[check['location']], check['location'], menu)
        opens = []
        for r in check["routes"]:
            opens.append((r["entry_id"], stage_gate(r)))
        if check["kind"] in ("itemsanity", "hit"):
            world.ctr_global_routes.append((check, location, [(entry, test, r) for (entry, test), r
                                                              in zip(opens, check["routes"])]))

        def any_route(state, opens=tuple(opens)):
            return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                       for entry, test in opens)
        location.access_rule = with_boost(with_letters(any_route, check), check)
        menu.locations.append(location)
    # Cup Leg Victory (#133 PR 5): any occurrence, each needing its cup's pad,
    # the finish of every earlier leg and its own leg's Trophy rank, bound to
    # the cup pad's racer lock (content_cups.route_boost).
    entry_by_id = {e["id"]: e for e in plan["entries"]}
    capability = plan.get("capability", {})
    for check in legs:
        location = Location(player, LOCATION_BY_CODE[check['location']], check['location'], menu)
        tests = []
        for r in check["routes"]:
            need = content_cups.route_boost(entry_by_id[r["entry_id"]], r["leg_id"], track_by_id, capability,
                                            package_by_id)
            lock = pad_by_id[r["own_pad_id"]]["racer_lock"]
            racer = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
            tests.append((r["entry_id"], need, racer))

        def any_leg(state, tests=tuple(tests)):
            return any(state.can_reach(entry, "Region", player)
                       and (not need or gate_satisfied(world, state, player, boost_min=need, required_character=racer))
                       for entry, need, racer in tests)
        location.access_rule = any_leg
        menu.locations.append(location)
    from .custom_track_presentation import location_aliases
    world.location_id_to_alias = location_aliases(world)


def create_items(world):
    plan = world.ctr_content_items
    world._ctr_relic_prog = relic_progression_map(world)
    names = plan.selected_names()
    names += traps.draw_trap_names(world, plan.trap_count)
    names += [wumpa_family.draw_filler_name(world) for _ in range(plan.filler_count - plan.trap_count)]
    # The created copies, so the framework phases after creation (plando and
    # item links, #133 PR 4f) can be audited against them.
    world.ctr_created_items = [world.create_item(name) for name in names]
    world.multiworld.itempool.extend(world.ctr_created_items)
    # Fixed items (one generator row 4) go straight on their own checks.
    world.ctr_fixed_items = content_fixed.place(world, content_fixed.plan_placements(world.ctr_content_plan),
                                                LOCATION_BY_CODE)
    # Main.py has granted these starts. Consume only this world's local removal
    # request; retain the original configuration for spoiler/Tracker diagnostics.
    world.options.start_inventory_from_pool.value = {}


def relic_progression_map(world):
    """Classify relic tiers from the plan's gates and required access."""
    tiers = {name: True for name in ("Sapphire Relic", "Gold Relic", "Platinum Relic")}
    passthrough = getattr(world.multiworld, "re_gen_passthrough", {}).get(world.game)
    if passthrough:
        wire = (passthrough.get("ctr_options") or {}).get("relic_progression")
        return dict(wire) if wire is not None else tiers
    plan = world.ctr_content_plan
    if plan.get("pad_requirements", {}).get("mode") != "vanilla":
        return tiers

    codes = {content_item_pool.ITEMS[name]: name for name in tiers}
    needed = set()

    def read(node):
        if node["op"] == "count":
            if node["item"] in codes:
                needed.add(codes[node["item"]])
        elif node["op"] in ("sum", "distinct"):
            needed.update(codes[code] for code in node["items"] if code in codes)
        elif node["op"] in ("all", "any"):
            for term in node["terms"]:
                read(term)

    final_goal = plan.get("bosses", {}).get("oxide_goal") == content_bosses.GOAL_FINAL
    access_full = world.options.accessibility.value == 0
    final_required = access_full or final_goal
    for row in plan["requirements"]:
        if row["id"] != "oxide:final" or final_required:
            read(row["predicate"])
    read(plan["goal"])
    if final_required:
        needed.add("Sapphire Relic")
    return {name: name in needed for name in tiers}


def set_rules(world):
    world.multiworld.completion_condition[world.player] = predicate(world, world.ctr_content_plan["goal"])
    for check, location, route_tests in getattr(world, "ctr_global_routes", ()):
        content_global_checks.install(world, check, location, route_tests)
    content_global_checks.tiger_temple_door(world)
    add_racer_unlock_placement_rules(world)


def add_racer_unlock_placement_rules(world):
    """Keep each racer's unlock item off every check with a route on a pad
    that racer locks (#133 PR 4b), the legacy design b
    (Rules.add_racer_unlock_placement_rules). A check whose only routes are
    on that pad is already out of logic without the racer; this also covers a
    shared check (`wumpa: global`) that the locked pad is one route of, so the
    pad that says "requires X" never glows with X's own unlock. Item links
    count, as on the legacy path. No rule when no pad is locked."""
    from worlds.generic.Rules import add_item_rule
    plan, player = world.ctr_content_plan, world.player
    locks = {pad["id"]: characters.CHARACTER_ID_TO_NAME[pad["racer_lock"]]
             for pad in plan["pads"] if pad["racer_lock"] is not None}
    if not locks:
        return
    for check in plan["checks"]:
        # Itemsanity and Hit Character checks (#133 PR 4d) route from every
        # race and glow on no pad, so a lock gives them no self-lock to guard:
        # the rule would only bar each locked racer's unlock from all 38 of
        # them, which left fills with nowhere to put the last racer item.
        if check["kind"] in ("itemsanity", "hit"):
            continue
        racers = sorted({locks[r["own_pad_id"]] for r in check["routes"] if r["own_pad_id"] in locks})
        if not racers:
            continue
        location = world.multiworld.get_location(LOCATION_BY_CODE[check["location"]], player)
        for racer in racers:
            owners = (player,) + characters.racer_link_groups(world.multiworld, player, racer)
            add_item_rule(location, lambda item, n=racer, o=owners: not (item.name == n and item.player in o))


def wire(world):
    o = world.options
    plan=world.ctr_content_plan
    extra=({'include_battle_arenas':True,
            'include_arcade_arenas':any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']),
            'crystalsanity':any(c['kind']=='crystal_pickup' for c in plan['checks'])}
           if any(e['kind']=='crystal' for e in plan['entries']) else {})
    # #133 PR 4a: the optional envelope keys (ENVELOPE_OPTIONAL) and the
    # trap_identities block every schema-18 seed carries, so a content-plan
    # room names its trap effects the same way a normal room does.
    # Hit Character (#133 PR 4d): the normal room's encounter block, with the
    # plan's fallback, and the envelope flag that admits it.
    hit = dict(hit_character_encounters=copy.deepcopy(world.ctr_hit_character_encounters)) \
        if plan.get("global_checks", {}).get("hit_character") else {}
    relic_progression = getattr(world, "_ctr_relic_prog", None) or relic_progression_map(world)
    relic_option = ({"relic_progression": relic_progression}
                    if plan.get("pad_requirements", {}).get("mode") == "vanilla"
                    and not all(relic_progression.values()) else {})
    return dict(schema_version=SCHEMA, content_plan=copy.deepcopy(world.ctr_content_plan),
                ctr_options=dict(schema_version=SCHEMA, world_version=world.world_version.as_simple_string(), content_plan=True,
                                 goal=-1, **goal_envelope(plan),
                                 starting_character=characters.ROSTER_CHARACTER_ID[world.ctr_starting_character],
                                 # True exactly when the plan has its `racers` record (#133 PR 4b).
                                 character_unlocks="racers" in plan,
                                 # The capability record's modes (#133 PR 4c), 0 without it.
                                 progressive_boost=plan.get("capability", {}).get("boost_mode", 0),
                                 progressive_stats=plan.get("capability", {}).get("stats_mode", 0),
                                 hit_character=bool(plan.get("global_checks", {}).get("hit_character")),
                                 death_link=o.death_link.value, deathlink_amnesty=o.deathlink_amnesty.value,**extra,
                                 **envelope_options(o), **stat_envelope(world), **box_envelope(world), **relic_option),
                trap_identities=traps.trap_identities_block(world.item_name_to_id), **hit)


def goal_envelope(plan):
    """The envelope's goal keys from the plan (#133 PR 6): `goal_oxide` and
    `goal_bosses` from the `bosses` record (3 and 0 without one, as before)
    and `goal_gems` the Gem arm's count (0 when the goal has none)."""
    record = plan.get("bosses")
    gem = content_bosses.gem_term_of(plan["goal"])
    return dict(goal_oxide=record["oxide_goal"] if record else content_bosses.GOAL_DISABLED,
                goal_bosses=record["bosses_required"] if record else 0, goal_gems=gem["count"] if gem else 0)


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
    # Boss garages (#133 PR 6): encounters exist exactly with the `bosses`
    # record, and every encounter, boss entry, boss requirement and boss check
    # is recomputed from it, the venues its entries name and the ledger.
    boss_record = plan.get("bosses")
    require((boss_record is None) == (not plan["encounters"]), "encounters without the bosses record, or the reverse")
    boss_encounters, boss_entries, boss_requirements, boss_checks, boss_tracks = [], [], [], [], {}
    if boss_record is not None:
        try:
            boss_encounters, boss_entries, boss_requirements, boss_checks, boss_tracks = content_bosses.expected(
                plan, RETAIL, cortex_track())
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            error("boss encounter records do not match the bosses record")
        require(plan["encounters"] == boss_encounters, "encounter records do not match the bosses record")
    boss_entry_ids = {e["id"] for e in boss_entries}
    require([e for e in plan["entries"] if e["kind"] in content_bosses.KINDS] == boss_entries,
            "boss race entries do not match the encounters")
    require({rid: row for rid, row in requirements.items() if rid.startswith(("boss:", "oxide:"))}
            == {row["id"]: row for row in boss_requirements}, "boss requirement records do not match the encounters")
    expected_requirements = {"free": {"id": "free", "predicate": {"op": "always"}}}
    expected_requirements.update({f"keys:{n}": dict(id=f"keys:{n}", predicate=dict(op="count", item=35010014, count=n)) for n in range(1, 5)})
    manual = {rid: row for rid, row in requirements.items() if rid.startswith("manual:")}
    later = {rid: row for rid, row in requirements.items() if rid.startswith(STAGE2_PREFIX)}
    drawn = {rid: row for rid, row in requirements.items() if rid.startswith(content_requirements.STAGE1_PREFIX)}
    require({rid: row for rid, row in requirements.items() if rid not in manual and rid not in later and rid not in drawn
             and not rid.startswith(("boss:", "oxide:"))}
            == expected_requirements, "unsupported or changed physical hub requirements")
    settings = check_settings(plan["track_checks"]) if "track_checks" in plan else {}
    packs = check_pack_settings(plan["item_packs"]) if "item_packs" in plan else {}
    racers = check_racer_settings(plan["racers"]) if "racers" in plan else None
    capability = content_capability.check_settings(plan["capability"]) if "capability" in plan else {}
    global_checks = content_global_checks.check_settings(plan["global_checks"]) if "global_checks" in plan else {}
    item_boxes = (content_item_boxes.check_settings(plan["item_boxes"], capability)
                  if "item_boxes" in plan else {})
    fixed = content_fixed.check_settings(plan) if "fixed_items" in plan else {}
    guarded = content_fixed.guarded_track(plan.get("pad_requirements", {}).get("mode"), fixed, plan["pads"], plan["entries"])
    require(plan['required_features']==required_features(plan['requirements'],plan['entries'],plan['checks'],settings,packs,racers,capability,
                                                         global_checks,item_boxes,boss_record,plan['items']['rows'],
                                                         plan.get("pad_requirements"), fixed, guarded),
            'required features do not match the selected content/checks')
    crystalsanity=any(c['kind']=='crystal_pickup' for c in plan['checks'])
    expected_pads = {f"pad:{physical}": (f"hub:{hub}", f"keys:{keys}" if keys else "free")
                     for physical, hub, keys in pad_registry()}
    expected_pads.update({f"garage:{i}": (f"hub:{26+i if i<4 else 25}",
                                          content_bosses.garage_gate(i, any(e["pad_id"] == f"garage:{i}"
                                                                            for e in boss_encounters)))
                          for i in range(5)})
    require(set(pads) == set(expected_pads), "physical pad registry mismatch")
    # Racer locks (#133 PR 4b): only with Character Unlocks, only on a pad that
    # does not open at the start, never the starting racer or a removed Oxide,
    # and exactly min(requested, eligible) of them.
    locks = {pad_id: pad["racer_lock"] for pad_id, pad in pads.items() if pad["racer_lock"] is not None}
    if locks:
        require(racers is not None, "a racer lock needs Character Unlocks (the racers record)")
        try:
            eligible = set(lock_eligible(plan))
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            eligible = set()
        for pad_id, cid in locks.items():
            require(pad_id in eligible, "a racer lock on a pad that opens at the start or holds no entry")
            require(cid in characters.CHARACTER_ID_TO_NAME
                    and not racer_excluded(racers, characters.CHARACTER_ID_TO_NAME[cid]),
                    "a racer lock names the starting racer, a removed Oxide or no racer")
    if racers is not None:
        try:
            eligible_count = len(lock_eligible(plan))
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            eligible_count = -1
        require(len(locks) == min(racers["requested_locks"], eligible_count),
                "racer lock count is not min(requested_locks, eligible pads)")
    occupied = []
    for pad_id, pad in pads.items():
        require((pad["hub_id"], pad["entrance_req"]) == expected_pads[pad_id], "pad has wrong hub or hub gate")
        require(pad["kind"] == ("garage" if pad_id.startswith("garage:") else "normal"), "pad kind mismatch")
        if pad["entry_id"] is None:
            require(not pad["mode_gates"], "empty pad has mode gates")
        else:
            require(pad["kind"] == "normal" and pad["entry_id"] in entries, "invalid normal entry")
            physical = pad_id.split(":")[1]
            gate = (f"manual:{physical}" if f"manual:{physical}" in manual else
                    f"{content_requirements.STAGE1_PREFIX}{physical}"
                    if f"{content_requirements.STAGE1_PREFIX}{physical}" in drawn else "free")
            require(f"manual:{physical}" not in manual or f"{content_requirements.STAGE1_PREFIX}{physical}" not in drawn,
                    "a manual rule and a drawn requirement on one pad")
            entry = entries[pad['entry_id']]
            if entry['kind'] == 'crystal':
                expected_gates = [dict(mode='crystal', stage=1, requirement_id=gate)]
            elif entry["kind"] == content_cups.KIND:
                expected_gates = content_cups.mode_gates(gate)
            else:
                stage = "two" if f"{STAGE2_PREFIX}{physical}" in later else "single"
                expected_gates = (mode_gates(entry["modes"], gate, stage, physical)
                                  if type(entry["modes"]) is list and entry["modes"] else None)
            require(pad['mode_gates'] == expected_gates, 'unsupported mode gates')
            occupied.append(pad["entry_id"])
    require(len(occupied) == len(set(occupied)) and set(occupied) | boss_entry_ids == set(entries)
            and not set(occupied) & boss_entry_ids, "entry occurrence ownership mismatch")
    require(all(f"pad:{rid.split(':')[1]}" in pads and pads[f"pad:{rid.split(':')[1]}"]["entry_id"] is not None
                for rid in {**manual, **drawn}), "manual requirement without an occupied pad")
    # A second-stage record belongs to exactly one pad, which uses it for its
    # later modes (checked by the gate comparison above).
    require(all(any(g["requirement_id"] == rid and g["stage"] == 2 for g in pads.get(f"pad:{rid[len(STAGE2_PREFIX):]}", {}).get("mode_gates", ()))
                for rid in later), "second-stage requirement without a pad that uses it")
    used_tracks, used_packages, slots, retail_ids = set(), set(), set(), set()
    expected_checks = {}
    relic_counts = {}
    # Generic-slot room titles are recomputed from the plan's own tracks; a
    # forged title (a retail or named track's name, or a repeated one) differs.
    try:
        expected_titles = generic_room_titles([t for t in plan["tracks"] if t["origin"] == "custom"
                                               and t["package_id"] in packages
                                               and type(t["custom_slot"]) is int], packages)
    except (KeyError, TypeError):
        expected_titles = {}
    arena_ids=set()
    # Cups (#133 PR 5): sweeps exist for every cup or none; leg laps share one
    # switch; leg tracks need no standalone entry. The Gem Cups come first.
    content_cups.check_lineup(plan["entries"])
    sweep = any(c["kind"] == content_cups.SWEEP_KIND for c in plan["checks"])
    shortened, cup_names, leg_tracks = None, set(), set()
    standalone_ids = {e["track_id"] for e in entries.values() if e["kind"] == "track"}
    for entry in entries.values():
        if entry["kind"] != content_cups.KIND:
            continue
        index, shortened = content_cups.check_entry(entry, tracks, packages, shortened)
        require(index not in cup_names, "two cups share a name")
        cup_names.add(index)
        pad_id = next(p["id"] for p in pads.values() if p["entry_id"] == entry["id"])
        for check in content_cups.checks(entry, pad_id, tracks, capability, packages, sweep):
            require(check["location"] not in expected_checks, "duplicate check identity")
            expected_checks[check["location"]] = check
        for leg in entry["legs"]:
            leg_tracks.add(leg["track_id"])
            if tracks[leg["track_id"]].get("package_id") in packages:
                used_packages.add(tracks[leg["track_id"]]["package_id"])
    for track_id in leg_tracks - standalone_ids:
        track = tracks[track_id]
        require(track["modes"] == ["trophy"] and track["capabilities"] == ["trophy"] and track["field_size"] == 8,
                "a track raced only in cups lists the trophy mode only")
    for entry in entries.values():
        if entry["kind"] in (content_cups.KIND,) + content_bosses.KINDS:
            continue
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
        elif track["origin"] == CORTEX_ORIGIN:
            # The bundled pair under its own identity; one per plan.
            require({k: v for k, v in track.items() if k not in ("modes", "capabilities", "field_size")}
                     == cortex_track(), "Cortex Vortex track metadata mismatch")
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
        relics = plan_relics(plan, track) if "relic" in track["modes"] else None
        require(track["id"] != guarded or not relics, "the Relic Race on the guarded five-Gem pad holds a tier check")
        for tier in relics or ():
            relic_counts[tier] = relic_counts.get(tier, 0) + 1
        for check in track_checks(track, entry["id"], pad_id, entry["modes"], settings, locations,
                                  packages.get(track.get("package_id")), capability, item_boxes, relics):
            require(check["location"] not in expected_checks, "duplicate check identity")
            expected_checks[check["location"]] = check
    # A track raced only in cups is checked like a standalone one (#133 PR 5).
    for track_id in sorted(leg_tracks - used_tracks):
        track = tracks[track_id]
        if track["origin"] == "retail":
            i = track["retail_id"]
            require(i in RETAIL and i not in retail_ids, "unknown or duplicate retail track")
            retail_ids.add(i)
            require(track["display_name"] == RETAIL[i] and track["laps"] == RETAIL_LAPS and track["id"] == f"retail:{i}",
                    "retail track metadata mismatch")
        elif track["origin"] == CORTEX_ORIGIN:
            require({k: v for k, v in track.items() if k not in ("modes", "capabilities", "field_size")}
                    == cortex_track(), "Cortex Vortex track metadata mismatch")
        else:
            require(track["origin"] == "custom" and track["package_id"] in packages, "unknown custom package")
            package = packages[track["package_id"]]
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
        used_tracks.add(track_id)
    for check in content_cups.leg_victories(tracks, plan["entries"], plan["pads"],
                                            {t["id"]: room_title(t) for t in plan["tracks"]}):
        require(check["location"] not in expected_checks, "duplicate check identity")
        expected_checks[check["location"]] = check
    # Boss venues (#133 PR 6): a venue raced nowhere else is listed once, the
    # trophy mode only; a venue that is also a pad track or a cup leg keeps
    # that record.
    for track_id, venue in boss_tracks.items():
        if track_id in used_tracks:
            continue
        require(tracks.get(track_id) == venue, "a boss venue raced nowhere else is not its trophy-only record")
        if venue["origin"] == "retail":
            require(venue["retail_id"] not in retail_ids, "unknown or duplicate retail track")
            retail_ids.add(venue["retail_id"])
        used_tracks.add(track_id)
    for check in boss_checks:
        require(check["location"] not in expected_checks, "duplicate check identity")
        expected_checks[check["location"]] = check
    require(used_tracks == set(tracks) and used_packages == set(packages), "unused track/package")
    if settings.get("wumpa") == "global":
        wumpa = global_wumpa_check(global_wumpa_routes(plan["tracks"], plan["entries"], plan["pads"], packages))
        if wumpa:
            require(wumpa["location"] not in expected_checks, "duplicate check identity")
            expected_checks[wumpa["location"]] = wumpa
    # Itemsanity and Hit Character (#133 PR 4d), recomputed from the layout.
    boss_hits = content_bosses.hit_routes(dict(entries=boss_entries, encounters=boss_encounters))
    for check in content_global_checks.checks(global_checks, plan["tracks"], plan["entries"], plan["pads"], packages,
                                              boss_hits):
        require(check["location"] not in expected_checks, "duplicate check identity")
        expected_checks[check["location"]] = check
    require(not entries or any(p["entry_id"] is not None and p["entrance_req"] == "free" for p in pads.values()),
            "content layout has no playable starting pad")
    require(checks == expected_checks, "check registry or route ownership mismatch")
    item_plan = plan["items"]
    rows = {row["item"]: row for row in item_plan["rows"]}
    # Lettersanity modes 2 and 3 pool one copy of each letter item they use.
    letter_items = plan_letter_items(plan)
    # Pool-only packs (#133 PR 4a): one row per pack item, its count from item_packs.
    pack_rows = {content_item_pool.ITEMS[name]: count for name, count in pack_counts(packs).items()}
    # Character unlocks (#133 PR 4b): one row per unlock racer.
    pack_rows.update({content_item_pool.ITEMS[name]: 1 for name in (unlock_names(racers) if racers else ())})
    # Capability packs (#133 PR 4c): the boost and stat chains.
    pack_rows.update({content_item_pool.ITEMS[name]: count
                      for name, count in content_capability.item_counts(capability).items()})
    # Itemsanity (#133 PR 4d): one row per weapon item.
    pack_rows.update({content_item_pool.ITEMS[name]: count
                      for name, count in content_global_checks.item_counts(global_checks).items()})
    # The five surface items are pooled together or not at all.
    surface = set(rows) & SURFACE_CODES
    require(surface in (set(), SURFACE_CODES), "the five surface items are pooled together")
    pack_rows.update(dict.fromkeys(surface, 1))
    require(len(rows) == len(item_plan["rows"]) and set(rows) == {content_item_pool.ITEMS[n] for n in content_item_pool.COUNTED_NAMES}
            | set(letter_items) | set(pack_rows), "item family registry mismatch")
    # A tier's checks follow its copies, capped by the Relic Races in the seed.
    races = relic_races(plan["entries"]) - (guarded is not None)
    require(all(relic_counts.get(tier, 0) == min(total, races) for tier, total in relic_supply(item_plan["rows"]).items()),
            "relic tier checks do not follow the item counts")
    require(all(rows[code]["base"] == 1 and rows[code]["extra"] == 0 for code in letter_items),
            "a letter item is pooled once")
    require(all(rows[code]["base"] == count and rows[code]["extra"] == 0 for code, count in pack_rows.items()),
            "a pack, racer, capability, weapon or surface item row disagrees with its record")
    # Fixed items (one generator row 4): the ledger's locked fields are what the
    # record pins, recomputed from it.
    pins = content_fixed.plan_placements(plan)
    locked = {content_item_pool.ITEMS[name]: count for name, count in content_fixed.locked_copies(pins).items()}
    require(set(pins) <= set(checks), "a fixed item without its check")
    for row in rows.values():
        require(row["start_from_pool"] <= 10000 and row["start_additional"] <= 10000,
                "starting count exceeds the framework ItemDict bound")
        require(row["locked_selected"] == locked.get(row["item"], 0)
                and row["remaining"] == row["base"] + row["extra"] - row["start_from_pool"] - row["locked_selected"],
                "invalid remaining selected count")
        require(row["receipt_cap"] == row["base"] + row["extra"] + row["start_additional"] and
                row["requirement_ceiling"] == row["base"], "invalid receipt cap or base requirement ceiling")
    require(rows[35010014]["base"] == 4, "four base Keys are mandatory")
    require(all(rows[i]["base"] in (0, 1) for i in range(35010009, 35010014)), "base Gems are distinct colours")
    require(item_plan["coded_checks"] == len(checks) and item_plan["locked_checks"] == len(pins) and
            sum(r["remaining"] for r in rows.values()) + item_plan["filler_count"] + len(pins) == len(checks) and
            item_plan["trap_count"] <= item_plan["filler_count"], "item/check capacity mismatch")
    # Boss garages (#133 PR 6): the excluded Oxide goal check needs one filler slot.
    require(boss_record is None or boss_record["oxide_goal"] not in (content_bosses.GOAL_ANY, content_bosses.GOAL_FINAL)
            or item_plan["filler_count"] >= 1, "the Oxide goal check needs one filler slot")
    goal = plan["goal"]
    gems = [i for i in range(35010009, 35010014) if rows[i]["base"]]
    # The Gem arm counts the selected distinct base Gem colours; boss garages
    # (#133 PR 6) add the Oxide and Boss arms and allow no Gem arm.
    gem = content_bosses.gem_term_of(goal)
    require(gem is None or (gem["items"] == gems and 1 <= gem["count"] <= len(gems)),
            "goal must count selected distinct base Gem colours")
    if boss_record is None:
        require(gem is not None and goal == gem, "goal must count selected distinct base Gem colours")
    else:
        try:
            want = content_bosses.goal(boss_record, gem)
        except OptionError:
            want = None
        require(goal == want, "goal does not match the bosses record")
    require("pad_requirements" in plan or not drawn, "a stage 1 record needs the pad_requirements record")
    if "pad_requirements" in plan:
        content_requirements.check_record(plan, drawn, later, manual, [
            content_item_pool.ItemRow(name=ITEM_BY_CODE.get(r["item"], str(r["item"])), **r) for r in item_plan["rows"]],
            require)
    for rid, row in {**manual, **drawn, **later}.items():
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
    if co.get("goal") != -1 or any(type(co.get(key)) is not int or co[key] != value
                                   for key, value in goal_envelope(plan).items()):
        error("goal envelope disagrees with the plan")
    check_envelope_options(co)
    check_relic_progression(co)
    check_racer_envelope(plan, co)
    check_box_envelope(plan, co)
    capability = plan.get("capability", {})
    content_capability.check_envelope(capability, co)
    racers = plan.get("racers")
    names = {**ITEM_BY_CODE, **plan_letter_items(plan)}
    rows = tuple(content_item_pool.ItemRow(name=names[r["item"]], **r) for r in plan["items"]["rows"])
    world.ctr_content_items = content_item_pool.ItemPlan(rows, **{k: v for k, v in plan["items"].items() if k != "rows"})
    world.ctr_content_plan = plan
    world.required_client_version = (0, 6, 7)
    world.ctr_starting_character = characters.CHARACTER_ID_TO_NAME[starting]
    world.ctr_content_original_starts = {r.name: r.start_from_pool for r in rows if r.start_from_pool}
    world.options.start_inventory_from_pool.value = copy.deepcopy(world.ctr_content_original_starts)
    world.options.start_inventory.value = {r.name: r.start_additional for r in rows if r.start_additional}
    # The goal and the boss options (#133 PR 6) follow the plan.
    content_bosses.restore_options(world, plan)
    content_fixed.restore_options(world, plan)
    world.options.crystalsanity.value=int(any(c['kind']=='crystal_pickup' for c in plan['checks']))
    world.options.include_battle_arenas.value=int(any(e['kind']=='crystal' for e in plan['entries']))
    world.options.include_arcade_arenas.value=int(any(e['kind']=='crystal' and e['arena_id'] in arena_content.ARCADE for e in plan['entries']))
    world.options.death_link.value = co.get("death_link", 0)
    # An explicit send list (#133 PR 4a) is the bits of the mask; an absent key
    # is the default, which follows death_link.
    if "death_link_send" in co:
        world.options.death_link_send.value = {key for key, bit in DL_SEND_BITS.items()
                                               if co["death_link_send"] & bit}
    else:
        # The tracking player's own YAML must not leak into a seed that omitted it.
        world.options.death_link_send.value = {"follow_death_link"}
    world.options.deathlink_amnesty.value = co.get("deathlink_amnesty", 1)
    # Optional legacy classifiers must not read the tracking player's unrelated YAML.
    # Character packs (#133 PR 4b) come from the plan and the envelope.
    world.options.character_unlocks.value = int(racers is not None)
    world.options.remove_playable_oxide.value = int(bool(racers and racers["remove_playable_oxide"]))
    world.options.racer_locked_pads.value = racers["requested_locks"] if racers else 0
    if "pad_requirements" in plan:
        world.options.warppad_unlock_requirements.value = {name: value for value, name in content_requirements.MODES.items()}[
            plan["pad_requirements"]["mode"]]
    world.options.racer_locked_pads.legacy_boolean_auto = False
    world.ctr_racer_locks = plan_racer_locks(plan)
    world.ctr_racer_lock_counts = {"requested": racers["requested_locks"] if racers else 0,
                                   "eligible": len(lock_eligible(plan)) if racers else 0}
    world.options.starting_stat_class.value = co.get("starting_stat_class", 0)
    world.options.penta_stats.value = co.get("penta_stats", 0)
    world.options.editable_stats.value = co.get("stat_owner", 0) if co.get("stat_source") == characters.STAT_SOURCE_EDITABLE else 0
    # Capability packs (#133 PR 4c) come from the plan's record; Logic
    # Difficulty and Shortcut Knowledge matter only with it.
    world.options.progressive_boost.value = capability.get("boost_mode", 0)
    world.options.progressive_boost_blue_fire.value = int(capability.get("boost_blue_fire", False))
    world.options.progressive_stats.value = capability.get("stats_mode", 0)
    if capability:
        world.options.logic_difficulty.value = capability["logic_difficulty"]
        world.options.shortcut_knowledge.value = capability["shortcut_knowledge"]
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
    world.options.relic_perfect_checks.value = int(settings.get("relic_perfect", False))
    # Cups (#133 PR 5): the sweep checks and the shortened legs follow the plan.
    world.options.cup_sweep_checks.value = int(any(c["kind"] == content_cups.SWEEP_KIND for c in plan["checks"]))
    shortened = None
    tracks_by_id = {t["id"]: t for t in plan["tracks"]}
    for entry in plan["entries"]:
        for leg in entry.get("legs", ()):
            full = content_cups.base_laps(tracks_by_id[leg["track_id"]])
            if full != max(1, full // 2):
                shortened = leg["laps"] != full
    if shortened is not None:
        world.options.one_lap_cups.value = int(shortened)
    # Pool-only packs (#133 PR 4a): the ledger rows above are the items; the
    # options follow them for code that reads options.
    packs = plan.get("item_packs", {})
    world.options.progressive_starting_wumpa.value = packs.get("progressive_starting_wumpa", 0)
    world.options.turbo_grant.value = int("turbo_grant" in packs)
    world.options.tizi_helper.value = int("tizi_helper" in packs)
    world.options.warp_pad_item_display.value = co.get("warp_pad_item_display", 0)
    world.options.ap_item_type_colors.value = int(co.get("ap_item_type_colors", True))
    # Itemsanity and Hit Character (#133 PR 4d): the plan's record, and the
    # room's encounter block verbatim (no redraw), its fallback checked against
    # the plan's unlock wins.
    global_checks = plan.get("global_checks", {})
    content_global_checks.check_encounter_block(plan, slot_data)
    # Item Box Locations (#133 PR 4e): the record's tier and the envelope's
    # colour setting.
    item_boxes = plan.get("item_boxes")
    world.options.box_locations.value = int(item_boxes is not None)
    if item_boxes is not None:
        world.options.shortcut_knowledge.value = item_boxes["shortcut_knowledge"]
        world.options.color_boxes_by_item.value = int(co["color_boxes_by_item"])
    world.options.itemsanity.value = int(bool(global_checks.get("itemsanity")))
    world.options.hit_character.value = int(bool(global_checks.get("hit_character")))
    world.ctr_hit_character_encounters, world.ctr_hit_character_fallback = None, {}
    if global_checks.get("hit_character"):
        from . import hit_character
        hit_character.restore_from_wire(world, slot_data, hit_character.CONTENT_PLAN_FALLBACK_KEYS,
                                        content_global_checks.cup_indices(plan))
