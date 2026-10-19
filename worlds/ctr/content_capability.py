"""Capability packs on content plans (#133 PR 4c).

Progressive Boost (with its Blue Fire capstone), Progressive Stats and Logic
Difficulty in a content-plan seed. The plan's optional `capability` record
carries the settings, and every check whose race needs a boost rank carries
that rank as its own `boost` field, so the room holds the logic as data:
`content_plan.create_regions` reads it, `content_plan.validate` (and the
Universal Tracker restore) recomputes it from the plan, and native reads it
for the race-loss stakes. The record is absent when both packs are off, and
then no check has a `boost` field, so such a plan keeps its earlier wire.

Which rank a check needs follows the legacy rules for the same race
(`Rules.py`, `usf_finish.py`, `capability_contract.py`), keyed by what the
check pays for, with one difference: in a content plan no mode needs a win in
another (Wayfinder ticket 16), so a CTR Challenge, a Time Trial or a letter
does not inherit the Trophy Race's own Logic Difficulty term the way the
legacy `can_reach(<track>: Trophy Race)` prerequisite passes it on. The finish
term does carry over, because every one of those checks crosses the line.

  * finish term F: two ranks (USF) on the confirmed finish tracks (Hot Air
    Skyway, Cortex Castle, Cortex Vortex; Oxide Station unless Shortcut
    Knowledge is hard), and on a custom track whose LEV has a super turbo pad
    (ruling 2026-10-17). the project's per-track rulings in
    `data/usf_finish_rulings.json` (2026-10-18) decide first, by content id:
    Arabian Heights Night and Cortex Vortex need USF; TV World, North Pole and
    Baby T Park take the generic terms only. A custom package that is not
    ruled and does not state `super_turbo_pads` is treated as having one, the
    safe direction;
  * Trophy Race: F, and on easy and medium the first rank on every
    difficulty-gated track (all retail tracks outside the finish set, and every
    custom track, `CUSTOM_TRACK_SLOTS_RULED`);
  * podium rungs: Finish on Podium F (plus the easy first rank on a gated
    track), Finish Any Position F, Held 1st the first rank on easy and medium
    and USF on Hot Air Skyway, Cortex Castle and Oxide Station (unless
    Shortcut Knowledge is hard), Held 3rd and Held 5th nothing;
  * CTR Token Challenge: F and the first rank (ruling 2026-09-20); on Oxide
    Station USF whenever its T or R letter must be picked up;
  * letters: F, Papu's Pyramid C and T the first rank, Oxide Station T and R
    USF (the legacy letter rulings; with Itemsanity on, #133 PR 4d, the
    legacy weapon alternatives join the first-boost floors, `weapon_arm`);
  * Time Trials: Sapphire F, Gold and Platinum also `relic_tier_boost_min`
    (the difficulty-aware Platinum floor, three ranks on easy with Blue Fire);
  * Relic Race Perfect: USF on every track (ruling 2026-09-29, #453 answer 1);
  * Reach 10 Wumpa and crystal checks: nothing.

The rank binds the pad's racer lock when it has one (the legacy
`track_required_character`), else any driveable racer, exactly as
`progressive_capability.gate_satisfied` and the `win_logic` cap leaf read it.
Progressive Stats adds no rank here: the only content-plan locations that read
a stat chain are the hard-tier Item Box checks (#133 PR 4e), which carry it as
their own `stats` term (content_item_boxes.py).
"""
import json
import pkgutil
from types import SimpleNamespace

from Options import OptionError

from . import capability_contract, progressive_capability
from .usf_finish import (CTR_CHALLENGE_BOOST_COUNT, FIRST_BOOST_COUNT, USF_BOOST_COUNT,
                         relic_perfect_boost_min, relic_tier_boost_min)

FEATURE = "capability_packs_v1"
KEYS = ("boost_mode", "boost_blue_fire", "stats_mode", "logic_difficulty", "shortcut_knowledge")
SK_HARD = 2
HARD = 2
EASY = 0
#: Retail letter rulings without their weapon arms (Rules.add_lettersanity_rules).
LETTER_BOOST = {("Papu's Pyramid", "letter_c"): FIRST_BOOST_COUNT,
                ("Papu's Pyramid", "letter_t"): FIRST_BOOST_COUNT,
                ("Oxide Station", "letter_t"): USF_BOOST_COUNT,
                ("Oxide Station", "letter_r"): USF_BOOST_COUNT}
OXIDE = "Oxide Station"


def _load_rulings():
    """{content id: needs USF to finish} from the project's per-track rulings on
    the super turbo pad finish rule (ruling 2026-10-18: "they require USF
    UNLESS I say otherwise"). Project-owned data, never a descriptor field;
    every entry cites its ruling. A track not listed keeps the measured
    default (`super_turbo_pads`)."""
    raw = json.loads(pkgutil.get_data(__package__, "data/usf_finish_rulings.json"))
    out = {}
    for row in raw["rulings"]:
        if (set(row) != {"content_id", "usf_finish", "ruling"} or type(row["usf_finish"]) is not bool
                or not row["content_id"] or "2026-" not in row["ruling"] or row["content_id"] in out):
            raise ValueError("usf_finish_rulings.json: each entry needs content_id, a Boolean usf_finish "
                             "and a dated ruling, once per track")
        out[row["content_id"]] = row["usf_finish"]
    return out


#: the project's per-track rulings: {content id: needs USF to finish}.
USF_FINISH_RULINGS = _load_rulings()


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options):
    """The plan's `capability` record from the seed's options; {} when
    Progressive Boost and Progressive Stats are both off. Blue Fire is false
    without Progressive Boost, as it has no effect there."""
    boost = int(options.progressive_boost.value)
    stats = int(options.progressive_stats.value)
    if not boost and not stats:
        return {}
    return dict(boost_mode=boost, boost_blue_fire=bool(boost and options.progressive_boost_blue_fire.value),
                stats_mode=stats, logic_difficulty=int(options.logic_difficulty.value),
                shortcut_knowledge=int(options.shortcut_knowledge.value))


def check_settings(record):
    """Shape and values of a plan's `capability` record."""
    if not isinstance(record, dict) or set(record) != set(KEYS):
        error("capability must be a mapping of exactly " + ", ".join(KEYS) + ".")
    for key in ("boost_mode", "stats_mode", "logic_difficulty", "shortcut_knowledge"):
        if type(record[key]) is not int or record[key] not in (0, 1, 2):
            error(f"capability.{key} must be 0, 1 or 2.")
    if type(record["boost_blue_fire"]) is not bool:
        error("capability.boost_blue_fire must be true or false.")
    if not record["boost_mode"] and not record["stats_mode"]:
        error("capability is present only when Progressive Boost or Progressive Stats is on.")
    if record["boost_blue_fire"] and not record["boost_mode"]:
        error("capability.boost_blue_fire needs Progressive Boost.")
    return record


def ceiling(record):
    """Highest rank the seed's boost chain reaches: 2, or 3 with Blue Fire."""
    return (progressive_capability.BOOST_COPIES_BLUE_FIRE if record.get("boost_blue_fire")
            else progressive_capability.BOOST_COPIES_NO_BLUE_FIRE)


def item_counts(record):
    """{item name: copies} the item ledger pools for a `capability` record:
    `progressive_capability.created_item_counts` for the same modes."""
    shim = SimpleNamespace(options=SimpleNamespace(
        progressive_boost=SimpleNamespace(value=record.get("boost_mode", 0)),
        progressive_boost_blue_fire=SimpleNamespace(value=int(record.get("boost_blue_fire", False))),
        progressive_stats=SimpleNamespace(value=record.get("stats_mode", 0))))
    return progressive_capability.created_item_counts(shim)


def _name(track):
    """The name the legacy capability tables use for a track, or None for a
    custom package (which has no row there)."""
    return None if track["origin"] == "custom" else track["display_name"]


def finish_boost(track, record, package=None):
    """F: the ranks crossing this track's finish line needs."""
    name = _name(track)
    if name is None:
        package = package or {}
        ruled = USF_FINISH_RULINGS.get(package.get("content_id"))
        if ruled is not None:
            return USF_BOOST_COUNT if ruled else 0
        stated = package.get("capabilities", {}).get("super_turbo_pads", True)
        return USF_BOOST_COUNT if stated else 0
    if name in capability_contract.unconditional_usf_finish_tracks():
        return USF_BOOST_COUNT
    if name in capability_contract.usf_or_hard_finish_tracks():
        return 0 if record["shortcut_knowledge"] == SK_HARD else USF_BOOST_COUNT
    return 0


def _difficulty_track(track):
    name = _name(track)
    return name is None or name in capability_contract.difficulty_gated_tracks()


def _held_first_usf(track, record):
    name = _name(track)
    if name is None or name not in capability_contract.held_first_gated_tracks():
        return 0
    if name in capability_contract.usf_or_hard_finish_tracks() and record["shortcut_knowledge"] == SK_HARD:
        return 0
    return USF_BOOST_COUNT


def check_boost(track, kind, award, record, package=None, letters=None):
    """Ranks one check of `track` needs. `kind` and `award` are the check's
    plan kind and route award; `letters` is the set of letter keys the track's
    CTR Challenge must pick up (None: all three)."""
    if not record or not record["boost_mode"]:
        return 0
    finish = finish_boost(track, record, package)
    difficulty = record["logic_difficulty"]
    win_floor = FIRST_BOOST_COUNT if difficulty < HARD and _difficulty_track(track) else 0
    name = _name(track)
    if kind == "trophy":
        return max(finish, win_floor)
    if kind == "podium":
        if award == "held_1st":
            return max(FIRST_BOOST_COUNT if difficulty < HARD else 0, _held_first_usf(track, record),
                       win_floor if difficulty == EASY else 0)
        if award == "finish_podium":
            return max(finish, win_floor if difficulty == EASY else 0)
        if award == "finish_any":
            return finish
        return 0
    if kind == "ctr":
        need = max(finish, CTR_CHALLENGE_BOOST_COUNT)
        picked = set(letters) if letters is not None else {"letter_c", "letter_t", "letter_r"}
        if name == OXIDE and picked & {"letter_t", "letter_r"}:
            need = max(need, USF_BOOST_COUNT)
        return need
    if kind == "letter":
        return max(finish, LETTER_BOOST.get((name, award), 0))
    if kind == "relic":
        tier = award.title()
        options = SimpleNamespace(logic_difficulty=SimpleNamespace(value=difficulty),
                                  progressive_boost_blue_fire=SimpleNamespace(value=int(record["boost_blue_fire"])))
        # A custom track takes the tier floors of a track outside every USF set.
        return max(finish, relic_tier_boost_min(name or "", tier, options))
    if kind == "perfect":
        return max(finish, relic_perfect_boost_min(name or ""))
    return 0


#: Weapons that open Papu's Pyramid's C and T routes instead of boost
#: (Rules.add_lettersanity_rules).
PAPU_LETTER_WEAPONS = ("Turbo", "Mask")


def weapon_arm(track, kind, award, record, package=None):
    """The legacy Itemsanity alternative to a check's first-boost floor (#133 PR
    4d), or None. Only for a check whose rank is the first boost and comes
    from a floor the legacy rules let weapons replace; a finish term or a USF
    gate never has one, and the CTR Token Challenge's first boost has none.
    Returns ("families", n): n distinct useful weapon families
    (itemsanity.USEFUL_WEAPON_FAMILIES); or ("any", names): one of the named
    weapon items.

      * Trophy Race on a difficulty-gated track below hard: three families
        (Rules.add_capability_difficulty_rules, ruling 2026-09-20);
      * Held 1st below hard without a USF gate: one family (ruling
        2026-09-28), three on easy on a gated track, where the difficulty
        term also binds it;
      * Finish on Podium on easy on a gated track: three families;
      * Papu's Pyramid Letter C and T: Turbo or Mask.

    The caller applies it only with Itemsanity on. Native's race-loss stakes
    read the rank alone, so a loss can stay exempt while a weapon arm already
    has the check in logic."""
    from .itemsanity import DIFFICULTY_WEAPON_FAMILY_MIN, HELD_FIRST_WEAPON_FAMILY_MIN
    if not record or not record["boost_mode"]:
        return None
    if finish_boost(track, record, package):
        return None
    difficulty = record["logic_difficulty"]
    gated = _difficulty_track(track)
    if kind == "trophy" and difficulty < HARD and gated:
        return ("families", DIFFICULTY_WEAPON_FAMILY_MIN)
    if kind == "podium" and award == "held_1st" and difficulty < HARD and not _held_first_usf(track, record):
        return ("families", DIFFICULTY_WEAPON_FAMILY_MIN if difficulty == EASY and gated
                else HELD_FIRST_WEAPON_FAMILY_MIN)
    if kind == "podium" and award == "finish_podium" and difficulty == EASY and gated:
        return ("families", DIFFICULTY_WEAPON_FAMILY_MIN)
    if kind == "letter" and LETTER_BOOST.get((_name(track), award)) == FIRST_BOOST_COUNT:
        return ("any", PAPU_LETTER_WEAPONS)
    return None


def check_envelope(record, co):
    """The envelope's `progressive_boost` and `progressive_stats` are the
    record's modes (0 without it), and a Progressive Stats seed sends the
    progressive stat trio (source 1, owner the stats mode, no editing)."""
    boost = record.get("boost_mode", 0) if record else 0
    stats = record.get("stats_mode", 0) if record else 0
    if co.get("progressive_boost") != boost or co.get("progressive_stats") != stats or \
            type(co.get("progressive_boost")) is not int or type(co.get("progressive_stats")) is not int:
        error("capability envelope disagrees with the plan's capability record")
    if stats and not (co.get("stat_source") == 1 and co.get("stat_owner") == stats
                      and co.get("stat_editing_allowed") is False):
        error("a Progressive Stats plan must send stat_source 1, stat_owner its mode and no editing")
    if not stats and co.get("stat_source") == 1:
        error("stat_source 1 (Progressive Stats) without the plan's capability record")
