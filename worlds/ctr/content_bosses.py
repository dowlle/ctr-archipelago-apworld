"""Boss garages on content plans (#133 PR 6).

With `content_pool.bosses.enabled: true` the five garages hold encounters
again, as in a normal room. The plan's optional `bosses` record carries the
seed's settings (feature `boss_encounters_v1`); with bosses off it is absent
and every earlier plan keeps its wire exactly.

ENCOUNTERS. One record per encounter (implementation packet, `Encounter`):

  * the four ordinary garages, `encounter/garage:<g>/0` for g 0 to 3 (Ripper
    Roo, Papu Papu, Komodo Joe, Pinstripe), each the retail pair: the garage's
    own boss as the opponent, on its home track, or with `boss_track_shuffle`
    on, on the track the #169 tier 1 draw gives that garage
    (boss_track_shuffle.draw, the certified venue table, its allow and block
    lists; never a repeated venue, decision 7 of 2026-10-28). Since #133 PR 6b the draw also
    takes the plan's selected custom tracks and Cortex Vortex (ruling
    2026-10-15: custom tracks join the Boss Track Shuffle pool): a package
    joins when it states `ai_nav: true` and a `checkpoints` count that
    carries the garage's attack schedule (`boss_track_shuffle.schedule_fits`;
    native measures both on load and refuses a mismatch). A non-empty
    `boss_track_allowlist` names retail tracks only, so it keeps custom
    tracks out; the blocklist does not touch them. With opponent or kit
    shuffle (#169 tiers 2 and 3, job J11) the garage races a drawn racer
    and a composed kit, see the section at the end of this module;
  * N. Oxide's two encounters in the Oxide garage, `encounter/garage:4/0` on
    Oxide Station and `encounter/garage:4/1` on `oxide_final_track` (Cortex
    Vortex by default), unless `oxide_goal` is `disabled`.

Each encounter names a `boss_race` entry (`entry/boss:<g>/<index>`: the venue
track, its three laps and the opponent with the retail driving profile and
the inherited attack kit) and a requirement record.

BOSS CUPS (#133 PR 6b, ruling 2026-10-23: boss AI on every leg). With
`content_pool.bosses.cups` (an exact count or {min, max}, 0 to 4, default 0)
that many ordinary garages, drawn uniformly, hold a `boss_cup` entry instead:
four legs against the garage's own boss alone, who drives and attacks as in
his boss race on every leg; a points win completes the garage's encounter
(its frozen check, its personal-win event), as the 2026-09-22 cup ruling
says. The legs are four different tracks of the garage's certified venue
pool (the retail venues that carry its attack schedule, and the plan's
certified custom tracks and Cortex Vortex as for Boss Track Shuffle), three
laps each. Its check's boost is the strictest of its legs' boss win rules. Venue tracks are plan
tracks; a venue raced nowhere else lists the trophy mode only, like a track
raced only in cups.

CHECKS. One `boss_race` check per encounter, the frozen location the garage
pays today: `<Boss> Garage: Boss Race` (35011100 + g), `N. Oxide Garage:
N. Oxide's Challenge` (35011104) and `... Final Challenge` (35011105), owned
by the encounter, with one route (mode `boss_race`, the encounter id, the
garage pad, award `win`). Its `boost` with Progressive Boost on is the legacy
boss win rule (Rules.add_boss_garage_rules, add_oxide_access_contract): the
first rank, and the venue's finish rank (content_capability.finish_boost,
USF on Hot Air Skyway, Cortex Castle, Cortex Vortex and Oxide Station unless
Shortcut Knowledge is hard). No Reach 10 Wumpa, podium, letter or Item Box
route comes from a boss race, the same as cup legs since PR 5: the logic is
stricter than the runtime there, never looser.

REQUIREMENTS. The garage pad takes its hub's Key gate (`keys:<g>`, Ripper
Roo's `free`; the Oxide garage `keys:4`, its fixed door) once it holds an
encounter; an empty garage keeps `free`, so plans without bosses are
unchanged. The encounter's own requirement:

  * `boss:<g>`: the mixed-item garage roll (#133 PR 6b, ruling 2026-10-23,
    the 2026-09-01 garage requirement design): one received-item family per garage, Trophy (always
    exactly four) or any other counted family (a Relic tier, a Token or Gem
    colour, Any Relic, Any CTR Token, Any Gem, Keys), never free. The count
    is drawn from a band of the base supply set by
    `content_pool.bosses.requirement_level` (`standard`, `high` default,
    `very_high`, `chaotic`) and the garage's depth (`garage_band`); a family
    an earlier garage took is rerolled once (variety bias). Keys ask more
    than the garage's own hub Key gate and at most three. Native validates
    the shape and the base supply, it does not redraw (`check_garage_requirement`);
  * N. Oxide's Challenge: `free`, or `oxide:first` with the goal's companion
    terms when `oxide_goal` is `any_percent` (the 2026-09-03 contract);
  * N. Oxide's Final Challenge: `oxide:final`, the companion terms when Oxide
    is the goal, and the relic term of `oxide_final_challenge_unlock` and its
    count (lowered to 18 in a one-tier mode and then to the base supply of the
    tiers it names, the 2026-09-18 and 2026-10-01 rulings, with the same
    notices).

The companion terms are the goal's: `checked` over the four Boss Race codes
for Bosses Required Goal, and the goal's distinct-Gem term. A `checked` term
counts encounters the player personally won (native: the #458 boss-won flags;
the apworld: the companion events below), never a Collect.

GOAL. The plan's goal becomes the AND (`all`) of the active arms: Oxide
(`checked` on 35011104 or 35011105), Bosses (`checked` on the four Boss Race
codes) and Gems (the distinct-Gem term, as before). One arm is written alone,
so a Gem-only goal keeps the earlier predicate. The Oxide goal location is
excluded from progression placement, as on the legacy path (issue #27).

Universal Tracker restores everything from the plan; native reads the record,
recomputes every encounter, requirement and check, and drives the normal
room's garage, Oxide and goal code from it (ap_content_plan_impl.hpp).
"""
from Options import OptionError

from . import boss_track_shuffle, content_item_pool, destinations
from .content_capability import finish_boost
from .Locations import CTR_LOCATION_IDS
from .content_cups import LEG_RETAIL_IDS
from .usf_finish import FIRST_BOOST_COUNT

FEATURE = "boss_encounters_v1"
KIND = "boss_race"
MODE = "boss_race"
AWARD = "win"
HIT_AWARD = "hit"
LAPS = 3
KEY_ITEM = 35010014
TROPHY_ITEM = content_item_pool.ITEMS["Trophy"]
RELIC_ITEMS = tuple(content_item_pool.ITEMS[f"{tier} Relic"] for tier in ("Sapphire", "Gold", "Platinum"))
OXIDE_GARAGE = 4
OXIDE_KEYS = 4
OXIDE_ID = 15
OXIDE_FIRST, OXIDE_FINAL = 35011104, 35011105
#: The four ordinary garages: (garage, boss_track_shuffle key, hub Keys,
#: Trophy count, opponent engine id, Boss Race code, companion event).
GARAGES = (
    (0, destinations.BOSS_ROO, 0, 4, 10, 35011100, "Ripper Roo Boss Race Won"),
    (1, destinations.BOSS_PAPU, 1, 8, 9, 35011101, "Papu Papu Boss Race Won"),
    (2, destinations.BOSS_JOE, 2, 12, 11, 35011102, "Komodo Joe Boss Race Won"),
    (3, destinations.BOSS_PINSTRIPE, 3, 16, 8, 35011103, "Pinstripe Boss Race Won"),
)
BOSS_CODES = tuple(row[5] for row in GARAGES)
#: Encounter completion code -> its personal-win companion event (the
#: legacy `_install_goal` names).
EVENTS = {**{row[5]: row[6] for row in GARAGES},
          OXIDE_FIRST: "N. Oxide's Challenge Cleared", OXIDE_FINAL: "N. Oxide's Final Challenge Cleared"}
OXIDE_STATION = "Oxide Station"
RECORD_KEYS = ("oxide_goal", "bosses_required", "oxide_1_optional", "oxide_final_unlock",
               "oxide_final_count", "track_shuffle", "repeats", "requirement_level", "cups")
CUP_KIND = "boss_cup"
CUP_MODE = "boss_cup"
CUP_LEGS = 4
KINDS = (KIND, CUP_KIND)
MODES = (MODE, CUP_MODE)
#: content_pool.bosses.requirement_level (2026-09-01 Wayfinder ruling C3a).
LEVELS = ("standard", "high", "very_high", "chaotic")
DEFAULT_LEVEL = "high"
GARAGE_TROPHIES = 4
GARAGE_KEY_MAX = 3
#: {level: garage depth 0..3 -> (low, high) fraction of the base supply}.
#: The first three rise with depth; `chaotic` takes the full range anywhere.
BANDS = {
    "standard": lambda d: (0.0, (d + 1) / 8),
    "high": lambda d: (d / 8, (d + 3) / 8),
    "very_high": lambda d: ((d + 1) / 8, (d + 5) / 8),
    "chaotic": lambda d: (0.0, 1.0),
}
#: Families boss-weighted levels roll twice as often (ruling C3a: Relics,
#: Gems, Keys and the aggregates more often than on warp pads).
BOSS_WEIGHTED = ("Relic", "Gem", "Key", "AnyRelic", "AnyCtrToken", "AnyGem")
#: oxide_goal values (Options.OxideGoal).
GOAL_NONE, GOAL_ANY, GOAL_FINAL, GOAL_DISABLED = 0, 1, 2, 3
#: oxide_final_challenge_unlock values (Options.FinalOxideUnlock).
UNLOCK_TOTAL, UNLOCK_ANY = 4, 3
SINGLE_TIER_MAX = 18
DRIVING_PROFILE = "retail"
ATTACK_PROFILE = "inherited"


def error(message):
    raise OptionError("CTR content plan: " + message)


def _venue_key(garage):
    return GARAGES[garage][1]


def home_track(garage):
    """The retail home track name of ordinary garage `garage`."""
    return boss_track_shuffle.retail_venues()[_venue_key(garage)]


def encounter_id(garage, index=0):
    return f"encounter/garage:{garage}/{index}"


def entry_id(garage, index=0):
    return f"entry/boss:{garage}/{index}"


def settings(world, raw):
    """The plan's `bosses` record from `content_pool.bosses` and the goal
    options, or None with bosses off. Takes no draw. The Final Challenge
    count is lowered to the base supply later (`resolve_relic_count`)."""
    o = world.options
    from .notices import note_ignored
    # The Purple Gem Cup gauntlet (decision 5) arms that cup's legs; content
    # plans have no Purple Gem Cup, so it is ignored with a notice (job J11).
    if o.purple_cup_boss_gauntlet.value:
        note_ignored(world, "Purple Gem Cup Boss Gauntlet (content plans have no Purple Gem Cup)")
        o.purple_cup_boss_gauntlet.value = 0
    wumpa = bool(o.goal_wumpa.value)
    enabled = raw.get("enabled")
    if type(enabled) is not bool:
        error("content_pool.bosses.enabled must be true or false. No content was changed.")
    if not enabled:
        if o.oxide_goal.value != GOAL_DISABLED or o.bosses_required_goal.value != 0 \
                or (o.gems_required_goal.value == 0 and not wumpa):
            error("with content_pool.bosses.enabled: false the garages are empty, so this profile needs "
                  "oxide_goal: disabled, bosses_required_goal: 0 and a positive gems_required_goal or goal_wumpa. "
                  "Set bosses.enabled: true for boss races and the Oxide and Boss goals.")
        if o.boss_track_shuffle.value:
            error("boss_track_shuffle needs content_pool.bosses.enabled: true; with bosses off the garages are "
                  "empty. No content was changed.")
        if (o.boss_opponent_shuffle.value or o.boss_kit_shuffle.value or o.boss_oxide_in_pool.value
                or int(o.oxide_attack_profile.value) != 0):
            error("boss_opponent_shuffle, boss_kit_shuffle, boss_oxide_in_pool and oxide_attack_profile: "
                  "all_compatible need content_pool.bosses.enabled: true; with bosses off the garages are empty. "
                  "No content was changed.")
        return None
    goal = int(o.oxide_goal.value)
    bosses = int(o.bosses_required_goal.value)
    if goal not in (GOAL_ANY, GOAL_FINAL) and bosses == 0 and o.gems_required_goal.value == 0 and not wumpa:
        error("no goal: oxide_goal is none or disabled, and bosses_required_goal, gems_required_goal and "
              "goal_wumpa are 0. Set at least one goal condition.")
    optional = int(o.oxide_1_optional.value)
    if goal == GOAL_FINAL and optional == 2:
        error("oxide_1_optional: filler places a locked Wumpa Fruit on N. Oxide's Challenge, and content plans "
              "have no locked placements yet. Use mandatory or optional. No content was changed.")
    shuffle = bool(o.boss_track_shuffle.value)
    oxide = goal != GOAL_DISABLED
    from .content_cups import _bounds
    cup_bounds = _bounds(raw.get("cups", 0), "content_pool.bosses.cups", 4)
    level = raw.get("requirement_level", DEFAULT_LEVEL)
    if level not in LEVELS:
        error("content_pool.bosses.requirement_level must be one of " + ", ".join(LEVELS) + ". No content was changed.")
    record = dict(oxide_goal=goal, bosses_required=bosses, requirement_level=level, cups=cup_bounds,
                  oxide_1_optional=goal == GOAL_FINAL and optional == 1,
                  oxide_final_unlock=int(o.oxide_final_challenge_unlock.value) if oxide else 0,
                  oxide_final_count=int(o.oxide_final_challenge_relic_count.value) if oxide else SINGLE_TIER_MAX,
                  track_shuffle=shuffle, repeats=False)
    record.update(encounter_settings(world, oxide, cup_bounds))
    return record


def check_settings(record):
    """Shape and values of a plan's `bosses` record."""
    if not isinstance(record, dict) or set(record) not in (set(RECORD_KEYS), set(RECORD_KEYS + ENCOUNTER_KEYS)):
        error("bosses must be a mapping of exactly " + ", ".join(RECORD_KEYS) + ", plus "
              + ", ".join(ENCOUNTER_KEYS) + " together when an opponent, kit or N. Oxide profile is drawn.")
    goal, bosses = record["oxide_goal"], record["bosses_required"]
    unlock, count = record["oxide_final_unlock"], record["oxide_final_count"]
    if type(goal) is not int or goal not in (GOAL_NONE, GOAL_ANY, GOAL_FINAL, GOAL_DISABLED):
        error("bosses.oxide_goal must be 0 to 3.")
    if type(bosses) is not int or not 0 <= bosses <= 4:
        error("bosses.bosses_required must be 0 to 4.")
    for key in ("oxide_1_optional", "track_shuffle", "repeats"):
        if type(record[key]) is not bool:
            error(f"bosses.{key} must be true or false.")
    if record["oxide_1_optional"] and goal != GOAL_FINAL:
        error("bosses.oxide_1_optional belongs to oxide_goal 101_percent only.")
    if record["repeats"]:
        # Decision 7 (2026-10-28): boss encounters never repeat. The field
        # stays on the wire, always false.
        error("bosses.repeats must be false: boss encounters never repeat.")
    if type(unlock) is not int or not 0 <= unlock <= UNLOCK_TOTAL:
        error("bosses.oxide_final_unlock must be 0 to 4.")
    if type(count) is not int or not 1 <= count <= (54 if unlock == UNLOCK_TOTAL else SINGLE_TIER_MAX):
        error("bosses.oxide_final_count must be 1 to 18, or to 54 with total_relics.")
    if not isinstance(record["cups"], list) or len(record["cups"]) > 4 or \
            any(type(g) is not int or not 0 <= g < 4 for g in record["cups"]) or record["cups"] != sorted(set(record["cups"])):
        error("bosses.cups must list distinct ordinary garages 0 to 3 in order.")
    if record["requirement_level"] not in LEVELS:
        error("bosses.requirement_level must be one of " + ", ".join(LEVELS) + ".")
    if goal == GOAL_DISABLED and (unlock, count) != (0, SINGLE_TIER_MAX):
        error("bosses.oxide_final_unlock and oxide_final_count keep their defaults when Oxide is disabled.")
    if "opponent_shuffle" in record:
        check_encounter_settings(record)
    return record


def _named_tiers(unlock):
    return (0, 1, 2) if unlock in (UNLOCK_ANY, UNLOCK_TOTAL) else (unlock,)


def _ceilings(rows):
    """{item code: base supply} of the plan's counted rows."""
    return {row["item"] if isinstance(row, dict) else row.item:
            row["requirement_ceiling"] if isinstance(row, dict) else row.requirement_ceiling for row in rows}


def resolve_relic_count(world, record, rows):
    """The legacy count rulings on the plan's base supply: a one-tier mode asks
    at most 18 (2026-09-18), and every mode at most what its tiers hold
    (2026-10-01, `forced_options.resolve_oxide_final_relic_count_to_created_supply`),
    each with its notice. Refuses a mode whose tiers hold no relic."""
    if record is None or record["oxide_goal"] == GOAL_DISABLED:
        return
    from .forced_options import _warn
    from .notices import slot_label
    unlock, count = record["oxide_final_unlock"], record["oxide_final_count"]
    if unlock != UNLOCK_TOTAL and count > SINGLE_TIER_MAX:
        _warn(world, "content_bosses_relic_mode",
              f"CTR ({slot_label(world)}): Oxide's Final Challenge Relic Count lowered from {count} to 18, "
              "the most a one-tier mode allows.")
        count = SINGLE_TIER_MAX
    ceiling = _ceilings(rows)
    tiers = [ceiling.get(RELIC_ITEMS[t], 0) for t in _named_tiers(unlock)]
    supply = sum(tiers) if unlock == UNLOCK_TOTAL else max(tiers)
    if supply < 1:
        error("oxide_final_challenge_unlock names relic tiers with no base relic in item_pool.base.relics, so "
              "N. Oxide's Final Challenge could never open. Add relics or choose another mode.")
    if count > supply:
        _warn(world, "content_bosses_relic_supply",
              f"CTR ({slot_label(world)}): Oxide's Final Challenge Relic Count lowered from {count} to {supply}, "
              "the base relics its mode can count.")
        count = supply
    record["oxide_final_count"] = count


def relic_term(record, rows):
    """The Final Challenge's relic predicate on the plan's base supply,
    refusing a count above what its tiers hold (`resolve_relic_count` lowers
    a generated count first)."""
    unlock, count = record["oxide_final_unlock"], record["oxide_final_count"]
    ceiling = _ceilings(rows)
    tiers = [ceiling.get(RELIC_ITEMS[t], 0) for t in _named_tiers(unlock)]
    if not 1 <= count <= (sum(tiers) if unlock == UNLOCK_TOTAL else max(tiers)):
        error("the Final Challenge relic count is above the base relics its mode can count")
    if unlock == UNLOCK_TOTAL:
        items = [RELIC_ITEMS[t] for t in range(3) if ceiling.get(RELIC_ITEMS[t], 0) > 0]
        return dict(op="sum", items=items, count=count)
    if unlock == UNLOCK_ANY:
        return dict(op="any", terms=[dict(op="count", item=RELIC_ITEMS[t], count=count)
                                     for t in range(3) if ceiling.get(RELIC_ITEMS[t], 0) >= count])
    return dict(op="count", item=RELIC_ITEMS[unlock], count=count)


def _all(terms):
    return terms[0] if len(terms) == 1 else dict(op="all", terms=list(terms))


def companion_terms(record, gem_term):
    """The goal arms besides Oxide, which gate the selected Oxide finale."""
    out = []
    if record["bosses_required"]:
        out.append(dict(op="checked", locations=list(BOSS_CODES), count=record["bosses_required"]))
    if gem_term is not None:
        out.append(gem_term)
    return out


def goal(record, gem_term):
    """The plan's goal predicate. Without a record the Gem term alone, as
    before; with one, the AND of the active arms."""
    if record is None:
        return gem_term
    terms = []
    if record["oxide_goal"] == GOAL_ANY:
        terms.append(dict(op="checked", locations=[OXIDE_FIRST], count=1))
    elif record["oxide_goal"] == GOAL_FINAL:
        terms.append(dict(op="checked", locations=[OXIDE_FINAL], count=1))
    terms += companion_terms(record, gem_term)
    if not terms:
        error("no goal: oxide_goal is none or disabled, and bosses_required_goal and gems_required_goal are 0.")
    return _all(terms)


def gem_term_of(goal_predicate):
    """The distinct-Gem term of a plan goal, or None."""
    if goal_predicate.get("op") == "distinct":
        return goal_predicate
    if goal_predicate.get("op") == "all":
        found = [t for t in goal_predicate.get("terms", ()) if isinstance(t, dict) and t.get("op") == "distinct"]
        return found[0] if len(found) == 1 else None
    return None


def _families():
    """[(label, item names, weight class)] of every garage family, in a fixed
    order: Trophy, the concrete counted items, then the three aggregates."""
    from . import warp_pad_rules
    out = [("Trophy", ("Trophy",), "Trophy")]
    for name in content_item_pool.COUNTED_NAMES:
        if name == "Trophy":
            continue
        kind = "Key" if name == "Key" else "Relic" if name.endswith(" Relic") else \
            "Gem" if name.endswith(" Gem") else "Token"
        out.append((name, (name,), kind))
    for label, names in (("AnyRelic", warp_pad_rules.RELICS), ("AnyCtrToken", warp_pad_rules.TOKENS),
                         ("AnyGem", warp_pad_rules.GEMS)):
        out.append((label, tuple(names), label))
    return out


def garage_band(level, depth, supply):
    """(low, high) count of a non-Trophy family with `supply` base copies at
    garage depth `depth` (0 Ripper Roo to 3 Pinstripe). `very_high` keeps
    one copy of margin where the family has several."""
    lo_f, hi_f = BANDS[level](depth)
    hi = min(supply, max(1, int(supply * hi_f + 0.5)))
    if level == "very_high" and supply > 1:
        hi = min(hi, supply - 1)
    lo = min(hi, max(1, -int(-supply * lo_f // 1)))
    return lo, hi


def garage_options(by_name, garage, level):
    """[(label, names, weight, low, high)] a garage may roll on the base
    supply `by_name` (ledger rows by item name). Trophy only with four base
    Trophies, at exactly four; Keys above the garage's own hub Key gate and
    at most GARAGE_KEY_MAX; an aggregate only over two or more base items."""
    out = []
    weighted = level != "standard"
    for label, names, kind in _families():
        eligible = tuple(n for n in names if by_name[n].requirement_ceiling > 0)
        if not eligible or (label.startswith("Any") and len(eligible) < 2):
            continue
        supply = sum(by_name[n].requirement_ceiling for n in eligible)
        if label == "Trophy":
            if supply < GARAGE_TROPHIES:
                continue
            lo = hi = GARAGE_TROPHIES
        else:
            lo, hi = garage_band(level, garage, supply)
            if label == "Key":
                lo, hi = max(lo, GARAGES[garage][2] + 1), min(hi, GARAGE_KEY_MAX)
                if lo > hi:
                    continue
        out.append((label, eligible, 2 if weighted and kind in BOSS_WEIGHTED else 1, lo, hi, kind))
    # A group (Trophy, Keys, a Relic tier, a Token colour, a Gem colour, each
    # aggregate) carries its weight once; its tiers or colours share it, so
    # five Gem colours do not outweigh one Trophy roll.
    size = {}
    for row in out:
        size[row[5]] = size.get(row[5], 0) + 1
    return [(label, names, weight / size[kind], lo, hi) for label, names, weight, lo, hi, kind in out]


def _predicate(by_name, names, count):
    if len(names) == 1:
        return dict(op="count", item=by_name[names[0]].item, count=count)
    return dict(op="sum", items=[by_name[n].item for n in names], count=count)


def draw_requirements(world, record, rows):
    """{garage: predicate} of the four ordinary garages (the mixed-item roll,
    see REQUIREMENTS). Draws in garage order with world.random; only called
    with bosses on, so other plans keep their stream."""
    by_name = {row.name: row for row in rows}
    out, used = {}, set()
    for g in range(4):
        options = garage_options(by_name, g, record["requirement_level"])
        if not options:
            error(f"{CTR_LOCATION_ID_NAMES[GARAGES[g][5]].split(':')[0]} has no item to ask for: the item pool "
                  "holds no base Trophies, Relics, CTR Tokens, Gems or Keys it can count. No content was changed.")
        pick = world.random.choices(options, weights=[o[2] for o in options])[0]
        if pick[0] in used and any(o[0] not in used for o in options):
            pick = world.random.choices(options, weights=[o[2] for o in options])[0]
        used.add(pick[0])
        label, names, _w, lo, hi = pick
        out[g] = _predicate(by_name, names, world.random.randint(lo, hi))
    return out


def check_garage_requirement(predicate, rows, garage):
    """Refuses a garage predicate the roll cannot produce: one family over its
    base items, Trophy exactly four, Keys above the hub gate and at most
    three, any other count 1 to the family's base supply. The level and the
    draw are not recomputed (the plan carries the result, as for pad rules)."""
    from . import warp_pad_rules
    ceiling = _ceilings(rows)
    items = content_item_pool.ITEMS
    if not isinstance(predicate, dict) or predicate.get("op") not in ("count", "sum"):
        error(f"garage {garage}: a boss garage requirement is one item count or one family sum")
    count = predicate.get("count")
    if type(count) is not int:
        error(f"garage {garage}: requirement count must be an integer")
    if predicate["op"] == "count":
        if set(predicate) != {"op", "item", "count"}:
            error(f"garage {garage}: malformed requirement")
        names = [n for n in content_item_pool.COUNTED_NAMES if items[n] == predicate["item"]]
        supply = ceiling.get(predicate["item"], 0)
        if not names or supply < 1:
            error(f"garage {garage}: requirement item has no base copy")
        if names[0] == "Trophy":
            if count != GARAGE_TROPHIES or supply < GARAGE_TROPHIES:
                error(f"garage {garage}: a Trophy garage asks exactly four of at least four base Trophies")
        elif names[0] == "Key":
            if not GARAGES[garage][2] < count <= min(GARAGE_KEY_MAX, supply):
                error(f"garage {garage}: a Key garage asks more than its hub gate and at most three")
        elif not 1 <= count <= supply:
            error(f"garage {garage}: requirement count outside the base supply")
        return
    if set(predicate) != {"op", "items", "count"}:
        error(f"garage {garage}: malformed requirement")
    for names in (warp_pad_rules.RELICS, warp_pad_rules.TOKENS, warp_pad_rules.GEMS):
        eligible = [items[n] for n in names if ceiling.get(items[n], 0) > 0]
        if predicate["items"] == eligible and len(eligible) >= 2:
            if not 1 <= count <= sum(ceiling[i] for i in eligible):
                error(f"garage {garage}: requirement count outside the base supply")
            return
    error(f"garage {garage}: sum requirement items are not exactly one family's base items")


#: Cortex Vortex's restart point count (the bundled LEV, measured with the
#: retail editor's levtool on 2026-10-23; native re-measures it on load).
CORTEX_RESTART_POINTS = 255


def custom_venue_points(track, package):
    """The restart point count a plan track may race a boss on, or None:
    Cortex Vortex, or a custom package stating AI navigation and its count."""
    if track.get("origin") == "cortex_vortex":
        return CORTEX_RESTART_POINTS
    caps = (package or {}).get("capabilities", {})
    if track.get("origin") == "custom" and caps.get("ai_nav") is True and type(caps.get("checkpoints")) is int:
        return caps["checkpoints"]
    return None


def venue_key(track):
    """The venue name content_bosses uses for a plan track: the retail or
    Cortex Vortex name, or a custom track's own id (`custom/...`)."""
    return track["id"] if track.get("origin") == "custom" else track["display_name"]


def draw_venues(world, record, custom=()):
    """{garage: venue} of the four ordinary garages: the retail pairs, or the
    #169 tier 1 draw (one world.random draw, only with the switch on).
    `custom` is [(venue, restart points)] of the plan's selected custom
    tracks and Cortex Vortex that may race a boss; without any the draw is
    exactly the retail one."""
    o = world.options
    custom = [(name, points) for name, points in custom if points is not None]
    if not record["track_shuffle"] or not custom or o.boss_track_allowlist.value:
        boss_track_shuffle.draw(world)
        venues = boss_track_shuffle.venues(o)
        return {g: venues[_venue_key(g)] for g in range(4)}
    boss_track_shuffle.validate_options(world)
    retail = boss_track_shuffle.garage_candidates(o)
    pools = [retail[_venue_key(g)] + [name for name, points in custom
                                      if boss_track_shuffle.schedule_fits(_venue_key(g), points)]
             for g in range(4)]
    # Never repeats (decision 7). Same draw as choosing from every distinct
    # four-way assignment, without listing them (0.3.0 review finding 2).
    picked = boss_track_shuffle.choose_distinct_assignment(world.random, pools)
    if picked is None:
        error("boss_track_shuffle cannot give the four boss garages four different tracks. Allow more tracks.")
    o._boss_track_venues = {_venue_key(g): picked[g] for g in range(4)}
    return dict(enumerate(picked))


def draw_cups(world, record, custom=()):
    """{garage: [leg venue]} of the garages that hold a boss cup. One
    world.random draw for how many (in the record's bounds) and which, then
    four different certified legs per cup; nothing is drawn with no cups.
    Writes the resolved garage list into the record."""
    low, high = record["cups"]
    if high == 0:
        record["cups"] = []
        return {}
    count = world.random.randint(low, high)
    garages = sorted(world.random.sample(range(4), count))
    o = world.options
    # Cup legs are the 16 retail race tracks (content_cups.LEG_RETAIL_IDS), so
    # the trial tracks Slide Coliseum and Turbo Track stay out.
    retail = [t for t, lid in boss_track_shuffle.VENUE_LEVEL_IDS.items() if lid in LEG_RETAIL_IDS]
    out = {}
    for g in garages:
        pool = [t for t in retail if boss_track_shuffle.inherited_attack_certified(_venue_key(g), t)]
        pool += [name for name, points in custom
                 if points is not None and boss_track_shuffle.schedule_fits(_venue_key(g), points)]
        if len(pool) < CUP_LEGS:
            error(f"garage {g}: a boss cup needs four tracks that carry the boss's attack.")
        out[g] = world.random.sample(pool, CUP_LEGS)
    record["cups"] = garages
    return out


def venue_record(name, retail, cortex, custom_records=None):
    """A plan track record for a venue raced nowhere else: the trophy mode
    only, like a track raced only in cups. `custom_records` maps a custom
    venue to its candidate track record."""
    if name == destinations.CORTEX_VORTEX:
        return dict(cortex, modes=["trophy"], capabilities=["trophy"], field_size=8)
    if name.startswith("custom/"):
        return dict(custom_records[name], modes=["trophy"], capabilities=["trophy"], field_size=8)
    lid = boss_track_shuffle.VENUE_LEVEL_IDS[name]
    return dict(id=f"retail:{lid}", origin="retail", retail_id=lid, display_name=retail[lid], laps=LAPS,
                modes=["trophy"], capabilities=["trophy"], field_size=8)


def track_id_of(name):
    if name == destinations.CORTEX_VORTEX:
        return "cortex_vortex"
    if name.startswith("custom/"):
        return name
    return f"retail:{boss_track_shuffle.VENUE_LEVEL_IDS[name]}"


def encounter_rows(record, venues, final_track):
    """[(garage, index, venue name, opponent, completion code)] in encounter order."""
    rows = [(g, 0, venues[g], GARAGES[g][4], GARAGES[g][5]) for g in range(4)]
    if record["oxide_goal"] != GOAL_DISABLED:
        rows += [(OXIDE_GARAGE, 0, OXIDE_STATION, OXIDE_ID, OXIDE_FIRST),
                 (OXIDE_GARAGE, 1, final_track, OXIDE_ID, OXIDE_FINAL)]
    return rows


def build(record, venues, final_track, rows, gem_term, capability, track_records, garage_reqs, cups=None,
          opponents=None):
    """(encounters, entries, requirements, checks) of a `bosses` record.

    `venues` maps ordinary garages to track names, `final_track` is the Final
    Challenge venue, `rows` the item ledger rows (base supply), `gem_term`
    the goal's distinct-Gem term or None, `track_records` {track id: record}
    of the venues, `garage_reqs` {garage: predicate} of the four ordinary
    garages (draw_requirements, or a plan's own records once checked),
    `cups` {garage: [leg venue]} of the garages holding a boss cup.
    `opponents` {garage: (engine id, schedule or None)} is the drawn racer
    and composed kit of each garage (OXIDE_GARAGE for both N. Oxide races,
    job J11); None keeps the retail opponents and their inherited attacks."""
    cups = cups or {}
    encounters, entries, requirements, checks = [], [], [], []
    companions = companion_terms(record, gem_term)
    for g, index, venue, opponent, code in encounter_rows(record, venues, final_track):
        eid, nid = encounter_id(g, index), entry_id(g, index)
        if g < OXIDE_GARAGE:
            rid = f"boss:{g}"
            check_garage_requirement(garage_reqs[g], rows, g)
            requirements.append(dict(id=rid, predicate=garage_reqs[g]))
        elif index == 0:
            rid = "free"
            if record["oxide_goal"] == GOAL_ANY and companions:
                rid = "oxide:first"
                requirements.append(dict(id=rid, predicate=_all(companions)))
        else:
            rid = "oxide:final"
            terms = (list(companions) if record["oxide_goal"] in (GOAL_ANY, GOAL_FINAL) else []) \
                + [relic_term(record, rows)]
            requirements.append(dict(id=rid, predicate=_all(terms)))
        opponent_record = opponent_entry(*(opponents[g] if opponents else (opponent, None)))
        cup = g < OXIDE_GARAGE and g in cups
        if cup:
            leg_ids = [track_id_of(leg) for leg in cups[g]]
            entries.append(dict(id=nid, kind=CUP_KIND,
                                legs=[dict(id=f"{nid}/leg:{n}", track_id=tid, laps=LAPS) for n, tid in enumerate(leg_ids)],
                                opponent=opponent_record))
        else:
            leg_ids = [track_id_of(venue)]
            entries.append(dict(id=nid, kind=KIND, track_id=leg_ids[0], laps=LAPS, opponent=opponent_record))
        encounters.append(dict(id=eid, pad_id=f"garage:{g}", index=index, entry_id=nid, requirement_id=rid,
                               completion_location=code))
        check = dict(location=code, owner=eid, kind=CUP_KIND if cup else KIND, display_name=CTR_LOCATION_ID_NAMES[code],
                     routes=[dict(entry_id=nid, mode=CUP_MODE if cup else MODE, leg_id=None, encounter_id=eid,
                                  own_pad_id=f"garage:{g}", award=AWARD)])
        if capability and capability.get("boost_mode"):
            check["boost"] = max([FIRST_BOOST_COUNT] + [finish_boost(track_records[tid], capability) for tid in leg_ids])
        checks.append(check)
    return encounters, entries, requirements, checks


CTR_LOCATION_ID_NAMES = {code: name for name, code in CTR_LOCATION_IDS.items()}


def garage_gate(garage, has_encounter):
    """The entrance requirement id of garage pad `garage`."""
    if not has_encounter:
        return "free"
    keys = OXIDE_KEYS if garage == OXIDE_GARAGE else GARAGES[garage][2]
    return f"keys:{keys}" if keys else "free"


def hit_routes(plan):
    """{opponent engine id: [route]} the Hit checks take from boss races: a
    boss can be hit in its own boss race (hit_character._build_boss_routes),
    one route per encounter, in encounter order."""
    out = {}
    entries = {e["id"]: e for e in plan["entries"]}
    for enc in plan["encounters"]:
        entry = entries[enc["entry_id"]]
        opponent = entry["opponent"]["character_id"]
        out.setdefault(opponent, []).append(dict(entry_id=enc["entry_id"], mode=CUP_MODE if entry["kind"] == CUP_KIND else MODE,
                                                 leg_id=None,
                                                 encounter_id=enc["id"], own_pad_id=enc["pad_id"], award=HIT_AWARD))
    return out


def plan_venues(plan):
    """({garage: track name}, Final Challenge track name, {garage: [leg]})
    read from a plan's boss entries, refusing a venue this build cannot race.
    A boss cup garage's venue is its first leg."""
    entries = {e["id"]: e for e in plan["entries"]}
    by_id = {track_id_of(name): name for name in boss_track_shuffle.VENUES}
    by_id["cortex_vortex"] = destinations.CORTEX_VORTEX
    by_id.update({t["id"]: t["id"] for t in plan["tracks"] if t.get("origin") == "custom"})
    venues, final, cups = {}, None, {}
    for enc in plan["encounters"]:
        entry = entries.get(enc.get("entry_id"))
        garage = enc["pad_id"].removeprefix("garage:")
        if entry is not None and entry.get("kind") == CUP_KIND and garage in ("0", "1", "2", "3") and enc["index"] == 0:
            legs = entry.get("legs")
            if (not isinstance(legs, list) or len(legs) != CUP_LEGS
                    or any(not isinstance(l, dict) or l.get("track_id") not in by_id for l in legs)):
                error("a boss cup names no four legs or an unknown venue")
            cups[int(garage)] = [by_id[l["track_id"]] for l in legs]
            venues[int(garage)] = cups[int(garage)][0]
            continue
        if entry is None or entry.get("kind") != KIND or entry.get("track_id") not in by_id:
            error("an encounter names no boss race entry or an unknown venue")
        name = by_id[entry["track_id"]]
        if garage == str(OXIDE_GARAGE):
            if enc["index"] == 1:
                final = name
        elif garage in ("0", "1", "2", "3") and enc["index"] == 0:
            venues[int(garage)] = name
    return venues, final, cups


def _certified(g, name, points):
    if name == destinations.CORTEX_VORTEX or name.startswith("custom/"):
        return boss_track_shuffle.schedule_fits(_venue_key(g), points.get(name))
    return boss_track_shuffle.inherited_attack_certified(_venue_key(g), name)


def check_venues(record, venues, final, points=None, raced=None, cups=None):
    """The venues a record allows: retail pairs, or certified drawn venues
    (distinct unless repeats), a custom venue or Cortex Vortex by its
    restart point count (`points`: {venue: count}); the Final Challenge on
    Cortex Vortex or Oxide Station."""
    if sorted(venues) != [0, 1, 2, 3]:
        error("the four ordinary garages need one encounter each")
    points = points or {}
    cups = cups or {}
    if sorted(cups) != record["cups"]:
        error("the boss cup garages do not match the bosses record")
    for g, legs in cups.items():
        if len(set(legs)) != CUP_LEGS:
            error(f"garage {g}: a boss cup races four different tracks")
        for name in legs:
            if name in boss_track_shuffle.VENUE_LEVEL_IDS and \
                    boss_track_shuffle.VENUE_LEVEL_IDS[name] not in LEG_RETAIL_IDS:
                error(f"garage {g}: a boss cup leg is a retail race track")
            if name.startswith("custom/") and name not in (raced or ()):
                error(f"garage {g}: a custom boss cup leg the plan does not race on a pad or in a cup")
            if not _certified(g, name, points):
                error(f"garage {g}: {name} is not a certified venue for this boss")
    race_venues = {g: name for g, name in venues.items() if g not in cups}
    for g, name in race_venues.items():
        if name.startswith("custom/") and name not in (raced or ()):
            error(f"garage {g}: a custom boss venue the plan does not race on a pad or in a cup")
        if record["track_shuffle"]:
            if not _certified(g, name, points):
                error(f"garage {g}: {name} is not a certified venue for this boss")
        elif name != home_track(g):
            error(f"garage {g}: without track_shuffle a boss races its home track")
    if record["track_shuffle"] and not record["repeats"] and len(set(race_venues.values())) != len(race_venues):
        error("boss venues repeat without repeats")
    if record["oxide_goal"] != GOAL_DISABLED and final not in (destinations.CORTEX_VORTEX, OXIDE_STATION):
        error("N. Oxide's Final Challenge races Cortex Vortex or Oxide Station")


def install(world, plan, menu, predicate, with_boost, oxide_event=None):
    """Regions, locations and companion events of the plan's encounters
    (content_plan.create_regions). `predicate` builds a requirement test,
    `with_boost` adds a check's boost rank. `oxide_event` names an event
    item both N. Oxide races also need (`Wumpa Income` with the Wumpa goal
    on, job J11), or None."""
    from BaseClasses import Location, LocationProgressType, Region
    from .content_plan import LOCATION_BY_CODE
    mw, player = world.multiworld, world.player
    req = {r["id"]: r["predicate"] for r in plan["requirements"]}
    pads = {p["id"]: p for p in plan["pads"]}
    checks = {c["location"]: c for c in plan["checks"]}
    record = plan["bosses"]
    goal_code = {GOAL_ANY: OXIDE_FIRST, GOAL_FINAL: OXIDE_FINAL}.get(record["oxide_goal"])
    for enc in plan["encounters"]:
        region = Region(enc["entry_id"], player, mw)
        mw.regions.append(region)
        gates = (predicate(world, req[pads[enc["pad_id"]]["entrance_req"]]),
                 predicate(world, req[enc["requirement_id"]]))
        if oxide_event and enc["pad_id"] == f"garage:{OXIDE_GARAGE}":
            gates += (lambda state, name=oxide_event: state.has(name, player),)
        menu.connect(region, enc["id"], lambda state, gates=gates: all(g(state) for g in gates))
        code = enc["completion_location"]
        check = checks[code]
        location = Location(player, LOCATION_BY_CODE[code], code, region)
        rule = with_boost(None, check)
        if rule is not None:
            location.access_rule = rule
        if code == goal_code:
            location.progress_type = LocationProgressType.EXCLUDED
        region.locations.append(location)
        event = Location(player, EVENTS[code], None, region)
        if rule is not None:
            event.access_rule = rule
        event.place_locked_item(world.create_event(EVENTS[code]))
        region.locations.append(event)


def restore_options(world, plan):
    """Universal Tracker: the goal and boss options from the plan, for code
    that reads options."""
    o = world.options
    record = plan.get("bosses")
    gem = gem_term_of(plan["goal"])
    o.gems_required_goal.value = gem["count"] if gem else 0
    restore_encounter_options(o, record)
    if record is None:
        o.oxide_goal.value, o.bosses_required_goal.value = GOAL_DISABLED, 0
        return
    o.oxide_goal.value = record["oxide_goal"]
    o.bosses_required_goal.value = record["bosses_required"]
    o.oxide_1_optional.value = int(record["oxide_1_optional"])
    o.oxide_final_challenge_unlock.value = record["oxide_final_unlock"]
    o.oxide_final_challenge_relic_count.value = record["oxide_final_count"]
    o.boss_track_shuffle.value = int(record["track_shuffle"])
    o.boss_track_allowlist.value = set()
    o.boss_track_blocklist.value = set()
    venues, final, _cups = plan_venues(plan)
    o._boss_track_venues = {_venue_key(g): name for g, name in venues.items()}
    if final is not None:
        o.oxide_final_track.value = 0 if final == destinations.CORTEX_VORTEX else 1


def expected(plan, retail, cortex):
    """Recompute a plan's encounters, boss entries, boss requirements and boss
    checks from its `bosses` record, the venues its boss entries name, its
    item ledger and its goal (content_plan.validate and the Tracker restore).
    Returns (encounters, entries, requirements, checks, venue track records)."""
    record = check_settings(plan["bosses"])
    venues, final, cups = plan_venues(plan)
    packages = {p["id"]: p for p in plan.get("packages", [])}
    points = {venue_key(t): custom_venue_points(t, packages.get(t.get("package_id")))
              for t in plan["tracks"] if t.get("origin") in ("custom", "cortex_vortex")}
    points.setdefault(destinations.CORTEX_VORTEX, CORTEX_RESTART_POINTS)
    raced = {e["track_id"] for e in plan["entries"] if e.get("kind") == "track"} \
        | {leg["track_id"] for e in plan["entries"] if e.get("kind") == "cup" for leg in e.get("legs", ())}
    check_venues(record, venues, final, points, raced, cups)
    gem = gem_term_of(plan["goal"])
    names = list(venues[g] for g in range(4) if g not in cups) + [leg for g in sorted(cups) for leg in cups[g]]
    if record["oxide_goal"] != GOAL_DISABLED:
        names += [OXIDE_STATION, final]
    known = {t["id"]: t for t in plan["tracks"]}
    tracks = {}
    for name in names:
        venue = venue_record(name, retail, cortex, known)
        tracks.setdefault(venue["id"], venue)
    own = {r["id"]: r["predicate"] for r in plan["requirements"]}
    opponents = check_opponents(record, venues, points, plan_opponents(plan), cups)
    built = build(record, venues, final, plan["items"]["rows"], gem, plan.get("capability", {}),
                  {tid: known.get(tid, venue) for tid, venue in tracks.items()},
                  {g: own.get(f"boss:{g}") for g in range(4)}, cups, opponents)
    return built + (tracks,)


# ---------------------------------------------------------------------------
# Boss opponent and kit shuffle on content plans (job J11, decisions 7 and 9)
# ---------------------------------------------------------------------------
#
# The ordinary room's draws (boss_encounters.py) carried over. With any of
# `boss_opponent_shuffle`, `boss_kit_shuffle` or `oxide_attack_profile:
# all_compatible` on, the `bosses` record gains ENCOUNTER_KEYS (feature
# `boss_opponents_v1`); otherwise it is byte-identical to before and nothing
# is drawn. Each boss race entry's `opponent` names the racer drawn for its
# garage (`character_id`), and with a composed kit its `schedule` (rows
# [checkpoint, throw, weapon, path, cooldown, juice]):
#
#   * ordinary garages: five segments at the garage's retail segment starts
#     mapped onto the encounter's venue restart points (retail table, Cortex
#     Vortex 255, a custom package's `checkpoints`), certified rows, cooldown
#     scaled by `boss_attack_intensity` (floor 2), at least one attack, no
#     Super Engine;
#   * both N. Oxide races: the final racer (15 unless `boss_oxide_in_pool`
#     drew another), and with `all_compatible` one 13-segment profile on
#     N. Oxide's retail segment starts, any certified row, the Super Engine
#     included (native remaps it on Cortex Vortex as on ordinary rooms).
#
# Racers never repeat: the four garage racers and the final racer are
# pairwise distinct, N. Oxide is a garage racer only with
# `boss_oxide_in_pool`, and then the final racer is never N. Oxide. With
# `oxide_goal: disabled` there are no N. Oxide races, so no final racer is
# drawn and `all_compatible` is ignored with a notice (conservative J11
# choice). `boss_track_assignment: character_home_track` with both draw
# switches on draws the racers first and races each on their home track (a
# venue raced nowhere else becomes a trophy-only plan track, as any boss
# venue); otherwise the content-plan venue draw is unchanged. Boss cups take
# no drawn opponent or kit yet and refuse together with either switch.

OPPONENT_FEATURE = "boss_opponents_v1"
ENCOUNTER_KEYS = ("opponent_shuffle", "oxide_in_pool", "kit_shuffle", "kit", "oxide_attack_profile",
                  "track_assignment")
ATTACK_COMPOSED = "composed"
PROFILES = ("retail", "all_compatible")
TRACK_ASSIGNMENTS = ("character_home_track", "independent_track")
def _be():
    from . import boss_encounters
    return boss_encounters


def _pool_by_id():
    be = _be()
    return {cid: name for name, cid in be.OPPONENT_ENGINE_ID.items()}


def _intensity_names():
    return [name for name, _num, _den in _be().INTENSITY]


def encounter_settings(world, oxide, cup_bounds):
    """The record's ENCOUNTER_KEYS from the options, or {} when no opponent,
    kit or N. Oxide profile is drawn. Takes no draw. Notes the subordinate
    options it ignores, as the ordinary room does."""
    be = _be()
    o = world.options
    from .notices import note_ignored
    if be.oxide_profile_all(o) and not oxide:
        note_ignored(world, "N. Oxide Attack Profile (oxide_goal: disabled, no N. Oxide races)")
        o.oxide_attack_profile.value = 0
    be.validate_options(world)
    opponent, kit, profile = be.opponent_on(o), be.kit_on(o), be.oxide_profile_all(o)
    if not (opponent or kit or profile):
        return {}
    if cup_bounds[1] and (opponent or kit):
        error("boss cups do not take a drawn opponent or kit yet: set content_pool.bosses.cups to 0, or turn "
              "boss_opponent_shuffle and boss_kit_shuffle off. No content was changed.")
    return dict(opponent_shuffle=opponent, oxide_in_pool=be.oxide_in_pool(o), kit_shuffle=kit,
                kit=dict(assignment=be.ASSIGNMENTS[int(o.boss_attack_assignment.value)],
                         intensity=be.INTENSITY[int(o.boss_attack_intensity.value)][0],
                         loss_easing=bool(o.boss_loss_easing.value)) if kit else None,
                oxide_attack_profile=PROFILES[1] if profile else PROFILES[0],
                track_assignment=TRACK_ASSIGNMENTS[0] if be.home_pairing(o) else TRACK_ASSIGNMENTS[1])


def check_encounter_settings(record):
    """Types and values of the record's ENCOUNTER_KEYS."""
    for key in ("opponent_shuffle", "oxide_in_pool", "kit_shuffle"):
        if type(record[key]) is not bool:
            error(f"bosses.{key} must be true or false.")
    if record["oxide_attack_profile"] not in PROFILES:
        error("bosses.oxide_attack_profile must be retail or all_compatible.")
    if record["track_assignment"] not in TRACK_ASSIGNMENTS:
        error("bosses.track_assignment must be character_home_track or independent_track.")
    if not (record["opponent_shuffle"] or record["kit_shuffle"] or record["oxide_attack_profile"] == PROFILES[1]):
        error("bosses encounter fields are present only with an opponent, kit or N. Oxide profile drawn.")
    if record["oxide_in_pool"] and not record["opponent_shuffle"]:
        error("bosses.oxide_in_pool needs opponent_shuffle.")
    if record["track_assignment"] == TRACK_ASSIGNMENTS[0] and not (record["track_shuffle"]
                                                                   and record["opponent_shuffle"]):
        error("bosses.track_assignment character_home_track needs track_shuffle and opponent_shuffle.")
    if record["oxide_goal"] == GOAL_DISABLED and record["oxide_attack_profile"] != PROFILES[0]:
        error("bosses.oxide_attack_profile all_compatible needs N. Oxide's races (oxide_goal not disabled).")
    kit = record["kit"]
    if record["kit_shuffle"]:
        be = _be()
        if (not isinstance(kit, dict) or set(kit) != set(be.KIT_KEYS) or kit["assignment"] not in be.ASSIGNMENTS
                or kit["intensity"] not in _intensity_names() or type(kit["loss_easing"]) is not bool):
            error("bosses.kit must be {assignment, intensity, loss_easing} with kit_shuffle.")
    elif kit is not None:
        error("bosses.kit must be null without kit_shuffle.")
    if record["cups"] and (record["opponent_shuffle"] or record["kit_shuffle"]):
        error("boss cups do not take a drawn opponent or kit yet.")


def drawn(record):
    """Does the record carry drawn encounters (ENCOUNTER_KEYS)?"""
    return record is not None and "opponent_shuffle" in record


def home_paired(record):
    return drawn(record) and record["track_assignment"] == TRACK_ASSIGNMENTS[0]


def _with_final(record):
    return record["oxide_in_pool"] and record["oxide_goal"] != GOAL_DISABLED


def _draw_racers(world, record, pools):
    """{garage: roster name} and the final racer's name: one distinct draw
    over the four garage pools, plus N. Oxide's garage with Oxide in the pool
    and N. Oxide's races in the plan (decision 7)."""
    be = _be()
    o = world.options
    regions = [row[1] for row in boss_track_shuffle.GARAGES]
    for g in range(4):
        if not pools[g]:
            error(f"boss_opponent_shuffle has no racer left for {regions[g]} after boss_character_allowlist and "
                  "boss_character_blocklist" + (" whose home track is in the boss track pool. Allow more racers or "
                                                "tracks, or set boss_track_assignment: independent_track."
                                                if home_paired(record) else "."))
    lists = [list(pools[g]) for g in range(4)]
    with_final = _with_final(record)
    if with_final:
        if not be.final_pool(o):
            error("boss_oxide_in_pool has no racer other than N. Oxide left for N. Oxide Garage after "
                  "boss_character_allowlist and boss_character_blocklist.")
        lists.append(be.final_pool(o))
    picked = be._distinct_draw(world.random, lists)
    if picked is None:
        error("boss_opponent_shuffle cannot give the "
              + ("four boss garages and N. Oxide's garage five" if with_final else "four boss garages four")
              + " different racers from the allowed pool (" + ", ".join(be.opponent_pool(o))
              + f"). Bosses never repeat, so allow at least {len(lists)} racers that fit.")
    return {g: picked[g] for g in range(4)}, (picked[4] if with_final else be.OXIDE_NAME)


def draw_home_venues(world, record):
    """character_home_track: ({garage: home track venue}, racers, final
    racer). The racers are drawn first among those whose home track is in the
    boss track pool and carries the garage's attack, as on the ordinary room."""
    be = _be()
    o = world.options
    boss_track_shuffle.validate_options(world)
    pool = set(boss_track_shuffle.venue_pool(o))
    pools = [[n for n in be.opponent_pool(o)
              if be.HOME_TRACK[n] in pool and boss_track_shuffle.inherited_attack_certified(_venue_key(g),
                                                                                           be.HOME_TRACK[n])]
             for g in range(4)]
    racers, final = _draw_racers(world, record, pools)
    return {g: be.HOME_TRACK[racers[g]] for g in range(4)}, racers, final


def draw_racers(world, record):
    """(racers, final racer) by roster name: the opponent draw, or the
    retail bosses and N. Oxide without opponent shuffle (no draw)."""
    be = _be()
    o = world.options
    if not drawn(record) or not record["opponent_shuffle"]:
        return {g: be.GARAGE_BOSS[_venue_key(g)] for g in range(4)}, be.OXIDE_NAME
    return _draw_racers(world, record, [be.opponent_pool(o) for _g in range(4)])


def venue_points(name, points):
    """Restart point count of a boss venue: the retail table, Cortex Vortex,
    or a custom track's stated `checkpoints` (`points` {venue: count})."""
    if name in boss_track_shuffle.VENUES:
        return boss_track_shuffle.VENUES[name]
    if name == destinations.CORTEX_VORTEX:
        return CORTEX_RESTART_POINTS
    return points[name]


def mapped_checkpoints(garage, restart_points):
    """The garage's retail segment starts on a venue with `restart_points`
    (boss_track_shuffle.translated_schedule for any venue)."""
    key = _venue_key(garage)
    home_last = boss_track_shuffle.VENUES[home_track(garage)] - 1
    return tuple(boss_track_shuffle.translate_checkpoint(cp, home_last, restart_points - 1)
                 for cp in boss_track_shuffle.RETAIL_ATTACK_CHECKPOINTS[key])


def draw_encounters(world, record, venues, racers, final, points):
    """{garage: (engine id, schedule or None)} for the four garages and
    OXIDE_GARAGE, or None when the record draws nothing (retail opponents and
    inherited attacks). Draws the kits (as boss_encounters._draw_kits, on the
    plan's venues) and N. Oxide's profile."""
    if not drawn(record):
        return None
    be = _be()
    o = world.options
    kits = {}
    if record["kit_shuffle"]:
        intensity = int(o.boss_attack_intensity.value)
        if int(o.boss_attack_assignment.value) == 1:
            profiles = be.allowed_signatures(o)
            if len(profiles) < 4:
                error("boss_attack_assignment: signature_profiles needs four different retail profiles, but "
                      "boss_powerup_blocklist leaves " + (", ".join(profiles) or "none")
                      + ". Bosses never repeat, so unblock weapons.")
            rows = {g: be.SIGNATURES[p] for g, p in enumerate(world.random.sample(profiles, 4))}
        else:
            families = be.allowed_families(o)
            if len(families) < be.MIX_MIN:
                error(f"boss_attack_assignment: mixed_loadouts needs at least {be.MIX_MIN} weapon types, but "
                      "boss_powerup_blocklist leaves " + (", ".join(families) or "none") + ".")
            rows, seen = {}, set()
            for g in range(4):
                mix = be._mixed_rows(world.random, families)
                tries = 0
                while tuple(r[0] for r in mix) in seen:
                    tries += 1
                    if tries > 1000:
                        error("could not draw four different boss kits.")
                    mix = be._mixed_rows(world.random, families)
                seen.add(tuple(r[0] for r in mix))
                rows[g] = mix
        for g in range(4):
            cps = mapped_checkpoints(g, venue_points(venues[g], points))
            kits[g] = tuple((cp, throw, weapon, path, be.scale_cooldown(cooldown, intensity), juice)
                            for cp, (weapon, throw, path, cooldown, juice) in zip(cps, rows[g]))
    final_schedule = None
    if record["oxide_attack_profile"] == PROFILES[1] and record["oxide_goal"] != GOAL_DISABLED:
        final_schedule = be._draw_oxide_profile(world)
    out = {g: (be.OPPONENT_ENGINE_ID[racers[g]], kits.get(g)) for g in range(4)}
    out[OXIDE_GARAGE] = (be.OPPONENT_ENGINE_ID[final], final_schedule)
    return out


def opponent_entry(character_id, schedule=None):
    """A boss race entry's `opponent` record."""
    record = dict(role="opponent", slot=1, character_id=character_id, driving_profile=DRIVING_PROFILE,
                  attack_profile=ATTACK_COMPOSED if schedule else ATTACK_PROFILE)
    if schedule:
        record["schedule"] = [list(seg) for seg in schedule]
    return record


def plan_opponents(plan):
    """{garage: [opponent record]} of a plan's encounters, in encounter order."""
    entries = {e["id"]: e for e in plan["entries"]}
    out = {}
    for enc in plan["encounters"]:
        entry = entries.get(enc.get("entry_id"), {})
        garage = int(str(enc["pad_id"]).removeprefix("garage:"))
        out.setdefault(garage, []).append(entry.get("opponent"))
    return out


def _base_cooldowns():
    be = _be()
    out = {}
    for rows in tuple(be.FAMILY_VARIANTS.values()) + tuple(be.SIGNATURES.values()):
        for w, t, p, c, j in rows:
            out.setdefault((w, t, p, j), set()).add(c)
    return out


def _check_schedule(schedule, checkpoints, intensity, garage_row, label):
    """A composed schedule: six-integer certified rows on exactly
    `checkpoints`, each cooldown a certified row's base cooldown scaled by
    `intensity`, at least one attack; the Super Engine only off a garage."""
    be = _be()
    if not isinstance(schedule, list) or len(schedule) != len(checkpoints):
        error(f"{label}: a composed schedule has {len(checkpoints)} segments")
    bases = _base_cooldowns()
    out = []
    for seg in schedule:
        problem = be._row_problem(seg, garage_row)
        if problem:
            error(f"{label}: {problem}")
        cp, throw, weapon, path, cooldown, juice = seg
        if cooldown not in {be.scale_cooldown(c, intensity) for c in bases.get((weapon, throw, path, juice), ())}:
            error(f"{label}: a segment cooldown is not its row's cooldown at this intensity")
        out.append(tuple(seg))
    if tuple(seg[0] for seg in out) != tuple(checkpoints):
        error(f"{label}: schedule checkpoints are not the mapped retail segments on this venue")
    if all(seg[2] == 0x0F for seg in out):
        error(f"{label}: schedule never attacks")
    return tuple(out)


def _check_kit_shape(schedule, intensity, assignment, label, oxide=False):
    """The kit rules native also enforces (J11 parity): a signature_profiles
    garage kit is one retail garage profile at the kit intensity; a
    mixed_loadouts garage kit uses two to four weapon families; N. Oxide's
    composed profile one to six. Every row of a mixed kit or of N. Oxide's
    profile belongs to a weapon family (no empty segment)."""
    be = _be()
    if not oxide and assignment == "signature_profiles":
        rows = tuple((w, t, p, c, j) for _cp, t, w, p, c, j in schedule)
        if not any(rows == tuple((w, t, p, be.scale_cooldown(c, intensity), j) for w, t, p, c, j in profile)
                   for profile in be.SIGNATURES.values()):
            error(f"{label}: a signature_profiles boss kit is not a retail garage profile at its intensity")
        return
    families = {be.family_of(seg[2]) for seg in schedule}
    if None in families:
        error(f"{label}: a boss kit row is not a weapon family row")
    low, high = (1, 6) if oxide else (be.MIX_MIN, be.MIX_MAX)
    if not low <= len(families) <= high:
        error(f"{label}: " + ("N. Oxide's composed profile uses one to six weapon families" if oxide
                              else "a mixed_loadouts boss kit uses two to four weapon families"))


def check_opponents(record, venues, points, opponents, cups=None):
    """Check a plan's boss opponents against its record and return them as
    build() takes them, or None for a record without drawn encounters (build
    then expects the retail records). The draw is not recomputed; every
    invariant of it is (distinct racers, pool membership, N. Oxide rules, home
    tracks, kit rows and checkpoints, distinct kits, N. Oxide's profile)."""
    if not drawn(record):
        return None
    be = _be()
    by_id = _pool_by_id()
    names = _intensity_names()
    intensity = names.index(record["kit"]["intensity"]) if record["kit_shuffle"] else names.index("standard")
    out = {}
    for g in range(4):
        rows = opponents.get(g, [])
        if len(rows) != 1 or not isinstance(rows[0], dict):
            error(f"garage {g}: one boss race opponent expected")
        opponent = rows[0]
        cid = opponent.get("character_id")
        if type(cid) is not int or cid not in by_id:
            error(f"garage {g}: the opponent is not a racer of the boss pool")
        if not record["opponent_shuffle"] and cid != GARAGES[g][4]:
            error(f"garage {g}: the opponent moved without opponent_shuffle")
        if cid == OXIDE_ID and not record["oxide_in_pool"]:
            error(f"garage {g}: N. Oxide races a garage only with oxide_in_pool")
        if home_paired(record) and venues[g] != be.HOME_TRACK[by_id[cid]]:
            error(f"garage {g}: with character_home_track the racer races their home track")
        schedule = None
        if record["kit_shuffle"]:
            schedule = _check_schedule(opponent.get("schedule"),
                                       mapped_checkpoints(g, venue_points(venues[g], points)),
                                       intensity, True, f"garage {g}")
            _check_kit_shape(schedule, intensity, record["kit"]["assignment"], f"garage {g}")
        out[g] = (cid, schedule)
    if len({out[g][0] for g in range(4)}) != 4:
        error("two garages race the same racer: bosses never repeat")
    if record["kit_shuffle"] and len({tuple(seg[2] for seg in out[g][1]) for g in range(4)}) != 4:
        error("two garages carry the same kit: bosses never repeat")
    finals = opponents.get(OXIDE_GARAGE, [])
    if record["oxide_goal"] != GOAL_DISABLED:
        if len(finals) != 2 or not all(isinstance(r, dict) for r in finals) or finals[0] != finals[1]:
            error("both N. Oxide races seat the same racer with the same attack")
        cid = finals[0].get("character_id")
        if type(cid) is not int or cid not in by_id:
            error("N. Oxide's garage: the opponent is not a racer of the boss pool")
        if record["oxide_in_pool"]:
            if cid == OXIDE_ID or cid in {out[g][0] for g in range(4)}:
                error("N. Oxide's garage: with oxide_in_pool the final racer is neither N. Oxide nor a garage racer")
        elif cid != OXIDE_ID:
            error("N. Oxide's garage: the final racer moved without oxide_in_pool")
        schedule = None
        if record["oxide_attack_profile"] == PROFILES[1]:
            schedule = _check_schedule(finals[0].get("schedule"), be.OXIDE_CHECKPOINTS, intensity, False,
                                       "N. Oxide's garage")
            _check_kit_shape(schedule, intensity, None, "N. Oxide's garage", oxide=True)
        out[OXIDE_GARAGE] = (cid, schedule)
    return out


def identity(plan):
    """{boss win code: engine id of the racer the boss race seats} for the
    Hit Character block's `bosses` table (decision 9): the plan's encounters,
    and the retail racer of a code the plan does not race (N. Oxide's codes
    with Oxide disabled, every code with bosses off)."""
    from .hit_character import BOSS_WIN_OPPONENTS
    out = dict(BOSS_WIN_OPPONENTS)
    entries = {e["id"]: e for e in plan["entries"]}
    for enc in plan["encounters"]:
        out[enc["completion_location"]] = entries[enc["entry_id"]]["opponent"]["character_id"]
    return out


def spoiler_lines(plan):
    """The drawn encounters for the spoiler, as the ordinary room writes them;
    () without drawn encounters."""
    record = plan.get("bosses")
    if not drawn(record):
        return ()
    be = _be()
    by_id = _pool_by_id()
    entries = {e["id"]: e for e in plan["entries"]}
    tracks = {t["id"]: t for t in plan["tracks"]}
    lines = []
    regions = {g: boss_track_shuffle.GARAGES[g][1] for g in range(4)}
    regions[OXIDE_GARAGE] = boss_track_shuffle.OXIDE_GARAGE
    for enc in plan["encounters"]:
        entry = entries[enc["entry_id"]]
        g = int(enc["pad_id"].removeprefix("garage:"))
        opponent = entry["opponent"]
        venues = [tracks[leg["track_id"]] for leg in entry["legs"]] if entry["kind"] == CUP_KIND \
            else [tracks[entry["track_id"]]]
        parts = [" / ".join(t.get("room_title", t["display_name"]) for t in venues),
                 f"vs {by_id[opponent['character_id']]}"]
        if opponent.get("schedule"):
            parts.append(f"kit: {be.kit_label(opponent['schedule'])}")
        label = regions[g] + (f" ({'Final Challenge' if enc['index'] else 'Challenge'})" if g == OXIDE_GARAGE else "")
        lines.append(f"{label}: " + ", ".join(parts))
    return tuple(lines)


def restore_encounter_options(o, record):
    """Universal Tracker: the opponent and kit options from the record (off
    without drawn encounters), so the tracking player's YAML cannot leak in."""
    be = _be()
    o.purple_cup_boss_gauntlet.value = 0
    o.oxide_powerup_blocklist.value = set()
    be._clear_subordinates(o)
    on = drawn(record)
    o.boss_opponent_shuffle.value = int(on and record["opponent_shuffle"])
    o.boss_oxide_in_pool.value = int(on and record["oxide_in_pool"])
    o.boss_kit_shuffle.value = int(on and record["kit_shuffle"])
    o.oxide_attack_profile.value = int(on and record["oxide_attack_profile"] == PROFILES[1])
    if on and record["kit_shuffle"]:
        o.boss_attack_assignment.value = be.ASSIGNMENTS.index(record["kit"]["assignment"])
        o.boss_attack_intensity.value = _intensity_names().index(record["kit"]["intensity"])
        o.boss_loss_easing.value = int(record["kit"]["loss_easing"])
    if on and record["track_shuffle"] and record["opponent_shuffle"]:
        o.boss_track_assignment.value = TRACK_ASSIGNMENTS.index(record["track_assignment"])
