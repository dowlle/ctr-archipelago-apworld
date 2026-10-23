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
    lists and `boss_encounter_repeats`). Since #133 PR 6b the draw also
    takes the plan's selected custom tracks and Cortex Vortex (ruling
    2026-10-15: custom tracks join the Boss Track Shuffle pool): a package
    joins when it states `ai_nav: true` and a `checkpoints` count that
    carries the garage's attack schedule (`boss_track_shuffle.schedule_fits`;
    native measures both on load and refuses a mismatch). A non-empty
    `boss_track_allowlist` names retail tracks only, so it keeps custom
    tracks out; the blocklist does not touch them. The opponent never changes: opponent
    and kit shuffle (#169 tiers 2 and 3) are not built, so neither are the
    `home_track` and `independent` pairings of the implementation packet;
  * N. Oxide's two encounters in the Oxide garage, `encounter/garage:4/0` on
    Oxide Station and `encounter/garage:4/1` on `oxide_final_track` (Cortex
    Vortex by default), unless `oxide_goal` is `disabled`.

Each encounter names a `boss_race` entry (`entry/boss:<g>/<index>`: the venue
track, its three laps and the opponent with the retail driving profile and
the inherited attack kit) and a requirement record. Venue tracks are plan
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
               "oxide_final_count", "track_shuffle", "repeats", "requirement_level")
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
    enabled = raw.get("enabled")
    if type(enabled) is not bool:
        error("content_pool.bosses.enabled must be true or false. No content was changed.")
    if not enabled:
        if o.oxide_goal.value != GOAL_DISABLED or o.bosses_required_goal.value != 0 \
                or o.gems_required_goal.value == 0:
            error("with content_pool.bosses.enabled: false the garages are empty, so this profile needs "
                  "oxide_goal: disabled, bosses_required_goal: 0 and a positive gems_required_goal. Set "
                  "bosses.enabled: true for boss races and the Oxide and Boss goals.")
        if o.boss_track_shuffle.value:
            error("boss_track_shuffle needs content_pool.bosses.enabled: true; with bosses off the garages are "
                  "empty. No content was changed.")
        return None
    goal = int(o.oxide_goal.value)
    bosses = int(o.bosses_required_goal.value)
    if goal not in (GOAL_ANY, GOAL_FINAL) and bosses == 0 and o.gems_required_goal.value == 0:
        error("no goal: oxide_goal is none or disabled, and bosses_required_goal and gems_required_goal are 0. "
              "Set at least one goal condition.")
    optional = int(o.oxide_1_optional.value)
    if goal == GOAL_FINAL and optional == 2:
        error("oxide_1_optional: filler places a locked Wumpa Fruit on N. Oxide's Challenge, and content plans "
              "have no locked placements yet. Use mandatory or optional. No content was changed.")
    shuffle = bool(o.boss_track_shuffle.value)
    oxide = goal != GOAL_DISABLED
    level = raw.get("requirement_level", DEFAULT_LEVEL)
    if level not in LEVELS:
        error("content_pool.bosses.requirement_level must be one of " + ", ".join(LEVELS) + ". No content was changed.")
    return dict(oxide_goal=goal, bosses_required=bosses, requirement_level=level,
                oxide_1_optional=goal == GOAL_FINAL and optional == 1,
                oxide_final_unlock=int(o.oxide_final_challenge_unlock.value) if oxide else 0,
                oxide_final_count=int(o.oxide_final_challenge_relic_count.value) if oxide else SINGLE_TIER_MAX,
                track_shuffle=shuffle, repeats=shuffle and bool(o.boss_encounter_repeats.value))


def check_settings(record):
    """Shape and values of a plan's `bosses` record."""
    if not isinstance(record, dict) or set(record) != set(RECORD_KEYS):
        error("bosses must be a mapping of exactly " + ", ".join(RECORD_KEYS) + ".")
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
    if record["repeats"] and not record["track_shuffle"]:
        error("bosses.repeats belongs to track_shuffle only.")
    if type(unlock) is not int or not 0 <= unlock <= UNLOCK_TOTAL:
        error("bosses.oxide_final_unlock must be 0 to 4.")
    if type(count) is not int or not 1 <= count <= (54 if unlock == UNLOCK_TOTAL else SINGLE_TIER_MAX):
        error("bosses.oxide_final_count must be 1 to 18, or to 54 with total_relics.")
    if record["requirement_level"] not in LEVELS:
        error("bosses.requirement_level must be one of " + ", ".join(LEVELS) + ".")
    if goal == GOAL_DISABLED and (unlock, count) != (0, SINGLE_TIER_MAX):
        error("bosses.oxide_final_unlock and oxide_final_count keep their defaults when Oxide is disabled.")
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
    import itertools
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
    if record["repeats"]:
        picked = [world.random.choice(pool) for pool in pools]
    else:
        assignments = [combo for combo in itertools.product(*pools) if len(set(combo)) == 4]
        if not assignments:
            error("boss_track_shuffle cannot give the four boss garages four different tracks. Allow more tracks "
                  "or set boss_encounter_repeats: allow.")
        picked = list(world.random.choice(assignments))
    o._boss_track_venues = {_venue_key(g): picked[g] for g in range(4)}
    return dict(enumerate(picked))


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


def build(record, venues, final_track, rows, gem_term, capability, track_records, garage_reqs):
    """(encounters, entries, requirements, checks) of a `bosses` record.

    `venues` maps ordinary garages to track names, `final_track` is the Final
    Challenge venue, `rows` the item ledger rows (base supply), `gem_term`
    the goal's distinct-Gem term or None, `track_records` {track id: record}
    of the venues, `garage_reqs` {garage: predicate} of the four ordinary
    garages (draw_requirements, or a plan's own records once checked)."""
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
        tid = track_id_of(venue)
        entries.append(dict(id=nid, kind=KIND, track_id=tid, laps=LAPS,
                            opponent=dict(role="opponent", slot=1, character_id=opponent,
                                          driving_profile=DRIVING_PROFILE, attack_profile=ATTACK_PROFILE)))
        encounters.append(dict(id=eid, pad_id=f"garage:{g}", index=index, entry_id=nid, requirement_id=rid,
                               completion_location=code))
        check = dict(location=code, owner=eid, kind=KIND, display_name=CTR_LOCATION_ID_NAMES[code],
                     routes=[dict(entry_id=nid, mode=MODE, leg_id=None, encounter_id=eid,
                                  own_pad_id=f"garage:{g}", award=AWARD)])
        if capability and capability.get("boost_mode"):
            check["boost"] = max(FIRST_BOOST_COUNT, finish_boost(track_records[tid], capability))
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
        opponent = entries[enc["entry_id"]]["opponent"]["character_id"]
        out.setdefault(opponent, []).append(dict(entry_id=enc["entry_id"], mode=MODE, leg_id=None,
                                                 encounter_id=enc["id"], own_pad_id=enc["pad_id"], award=HIT_AWARD))
    return out


def plan_venues(plan):
    """({garage: track name}, Final Challenge track name) read from a plan's
    boss entries, refusing a venue this build cannot race."""
    entries = {e["id"]: e for e in plan["entries"]}
    by_id = {track_id_of(name): name for name in boss_track_shuffle.VENUES}
    by_id["cortex_vortex"] = destinations.CORTEX_VORTEX
    by_id.update({t["id"]: t["id"] for t in plan["tracks"] if t.get("origin") == "custom"})
    venues, final = {}, None
    for enc in plan["encounters"]:
        entry = entries.get(enc.get("entry_id"))
        if entry is None or entry.get("kind") != KIND or entry.get("track_id") not in by_id:
            error("an encounter names no boss race entry or an unknown venue")
        name = by_id[entry["track_id"]]
        garage = enc["pad_id"].removeprefix("garage:")
        if garage == str(OXIDE_GARAGE):
            if enc["index"] == 1:
                final = name
        elif garage in ("0", "1", "2", "3") and enc["index"] == 0:
            venues[int(garage)] = name
    return venues, final


def check_venues(record, venues, final, points=None, raced=None):
    """The venues a record allows: retail pairs, or certified drawn venues
    (distinct unless repeats), a custom venue or Cortex Vortex by its
    restart point count (`points`: {venue: count}); the Final Challenge on
    Cortex Vortex or Oxide Station."""
    if sorted(venues) != [0, 1, 2, 3]:
        error("the four ordinary garages need one encounter each")
    points = points or {}
    for g, name in venues.items():
        if name.startswith("custom/") and name not in (raced or ()):
            error(f"garage {g}: a custom boss venue the plan does not race on a pad or in a cup")
        if record["track_shuffle"]:
            certified = (boss_track_shuffle.schedule_fits(_venue_key(g), points.get(name))
                         if name == destinations.CORTEX_VORTEX or name.startswith("custom/")
                         else boss_track_shuffle.inherited_attack_certified(_venue_key(g), name))
            if not certified:
                error(f"garage {g}: {name} is not a certified venue for this boss")
        elif name != home_track(g):
            error(f"garage {g}: without track_shuffle a boss races its home track")
    if record["track_shuffle"] and not record["repeats"] and len(set(venues.values())) != 4:
        error("boss venues repeat without repeats")
    if record["oxide_goal"] != GOAL_DISABLED and final not in (destinations.CORTEX_VORTEX, OXIDE_STATION):
        error("N. Oxide's Final Challenge races Cortex Vortex or Oxide Station")


def install(world, plan, menu, predicate, with_boost):
    """Regions, locations and companion events of the plan's encounters
    (content_plan.create_regions). `predicate` builds a requirement test,
    `with_boost` adds a check's boost rank."""
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
    if record is None:
        o.oxide_goal.value, o.bosses_required_goal.value = GOAL_DISABLED, 0
        return
    o.oxide_goal.value = record["oxide_goal"]
    o.bosses_required_goal.value = record["bosses_required"]
    o.oxide_1_optional.value = int(record["oxide_1_optional"])
    o.oxide_final_challenge_unlock.value = record["oxide_final_unlock"]
    o.oxide_final_challenge_relic_count.value = record["oxide_final_count"]
    o.boss_track_shuffle.value = int(record["track_shuffle"])
    o.boss_encounter_repeats.value = int(record["repeats"])
    o.boss_track_allowlist.value = set()
    o.boss_track_blocklist.value = set()
    venues, final = plan_venues(plan)
    o._boss_track_venues = {_venue_key(g): name for g, name in venues.items()}
    if final is not None:
        o.oxide_final_track.value = 0 if final == destinations.CORTEX_VORTEX else 1


def expected(plan, retail, cortex):
    """Recompute a plan's encounters, boss entries, boss requirements and boss
    checks from its `bosses` record, the venues its boss entries name, its
    item ledger and its goal (content_plan.validate and the Tracker restore).
    Returns (encounters, entries, requirements, checks, venue track records)."""
    record = check_settings(plan["bosses"])
    venues, final = plan_venues(plan)
    packages = {p["id"]: p for p in plan.get("packages", [])}
    points = {venue_key(t): custom_venue_points(t, packages.get(t.get("package_id")))
              for t in plan["tracks"] if t.get("origin") in ("custom", "cortex_vortex")}
    points.setdefault(destinations.CORTEX_VORTEX, CORTEX_RESTART_POINTS)
    raced = {e["track_id"] for e in plan["entries"] if e.get("kind") == "track"} \
        | {leg["track_id"] for e in plan["entries"] if e.get("kind") == "cup" for leg in e.get("legs", ())}
    check_venues(record, venues, final, points, raced)
    gem = gem_term_of(plan["goal"])
    names = list(venues[g] for g in range(4))
    if record["oxide_goal"] != GOAL_DISABLED:
        names += [OXIDE_STATION, final]
    known = {t["id"]: t for t in plan["tracks"]}
    tracks = {}
    for name in names:
        venue = venue_record(name, retail, cortex, known)
        tracks.setdefault(venue["id"], venue)
    own = {r["id"]: r["predicate"] for r in plan["requirements"]}
    built = build(record, venues, final, plan["items"]["rows"], gem, plan.get("capability", {}),
                  {tid: known.get(tid, venue) for tid, venue in tracks.items()},
                  {g: own.get(f"boss:{g}") for g in range(4)})
    return built + (tracks,)
