"""Cups on content plans (#133 PR 5).

A content plan may seat cups on its 27 normal pads. `content_pool.cups`
asks for a `count`, exact or an inclusive `{min, max}` range, and optionally
a `composition`. With crystals also drawn from a range, the generator
chooses uniformly among the feasible (cups, crystals) pairs instead of
drawing one count and trimming the other (implementation packet, Proposed
authoring surface). Tracks fill the remaining pads as before.

COMPOSITION. A cup has exactly four ordered legs, drawn from the seed's own
tracks:

  * `sources`: which tracks a leg may be, any of `retail` (the 16 retail race
    tracks of the `tracks.retail` selection, no trial track, as the #166 Gem
    Cup pool clamp), `custom` (the selected custom tracks that can run a
    Trophy race: eight karts with AI paths) and `cortex_vortex` (when
    `tracks.cortex_vortex` is on). Default: all three.
  * `custom_legs`: `{min, max}` custom and Cortex Vortex legs per cup, default
    0 to 4.
  * `repeats`: `within_cup` (default false: four different tracks per cup)
    and `across_cups` (default true: a track may lead several cups), the
    shape of the retail Gem Cups. These defaults are engineering choices.

CUP TRACKS (`tracks`, ruled 2026-10-30). `off`: a Gem Cup races its original
four tracks (data/gem_cup_legs.json) and a sixth cup onward draws as
`random_no_repeats`. `random`: every leg is drawn, repeats allowed.
`random_no_repeats`, the default: four different tracks per cup. An explicit
`tracks` decides repeats within a cup and wins over
`composition.repeats.within_cup`; without it that older key still picks between
the two drawn values, until row 7 removes it. `composition` shapes drawn cups
only, never the original legs of `off`.

GEM CUPS (ruled 2026-10-30). The first five cups of a plan are the original Gem
Cups, Red first, with their names and frozen checks; a plan with fewer keeps the
first ones. A sixth cup onward takes a name from the pool. A Gem Cup is the
entry `entry/gem_cup:<colour>`, with colour 0 (Red) to 4 (Purple), owned by
`gem_cup:<colour>`, and the plan declares GEM_FEATURE. Its Gem is a shuffled item
unless the plan fixes it (content_fixed).

A leg track may also hold its own standalone pad, or appear only in cups.

LAPS. A leg races its track's authored laps (retail and Cortex Vortex 3, a
custom package its `laps`), shortened to `max(1, floor(laps / 2))` when
`one_lap_cups` is on (the shortened-cup rule, ruled 2026-09-22): retail
3 to 1, custom 7 to 3. Every leg of a plan uses the same switch; the plan
does not carry the option, the legs' laps do.

ROSTER. The player slot only, with the engine's eight-kart Adventure field:
the opponents follow the player's racer at cup start, as in a retail Gem
Cup, and stay the same for all four legs (slice plan, open question on the
roster, option A built). With Hit Character on (cup roster ruling of
2026-10-21, #133 PR 5b) native seats the cup's field from the encounter draw
instead: drawn once at cup start from the cup's own order (the encounter
block's `content_cups`), frozen for every leg and retry, custom legs
included; every leg is then a Hit route (content_global_checks).

CHECKS.
  * `<Cup>: Win` (35027000 + name index) on a points win, `<Colour> Gem Cup:
    Gem` (35011200 + colour) on a Gem Cup. A sixth cup onward takes one name
    from the 27-name pool (cup_checks.CUP_NAMES), drawn per seed (naming
    model ruled 2026-10-13 21:47 CEST). Its `boost` is the legs' highest
    finish rank (usf_finish.cup_finish_t: USF when a leg is a USF finish
    track).
  * `<Cup>: Win All Legs` (35027200 + name index, 35028300 + colour on a Gem
    Cup) with `cup_sweep_checks`: first place in all four legs of one
    uninterrupted attempt (#246). Its `boost` is the legs' highest Trophy Race
    rank.
  * `<Track>: Cup Leg Victory` for a leg track with no standalone Trophy Race
    check in the plan (ruling 17 and 29, 2026-09-01): first place in that
    leg, paid at the leg's finish. Every occurrence is a route to the one
    check. A route needs the cup pad, the finish of every earlier leg and the
    Trophy Race rank of its own leg (ordered prefix); the routes carry no
    `boost` on the wire, the rule is recomputed from the plan.

A plan without cups draws nothing here and keeps its wire exactly.
"""
from Options import OptionError

from . import cup_checks, gem_cup_legs, named_tracks
from .content_capability import check_boost, finish_boost
from .Locations import CTR_LOCATION_IDS

FEATURE = "cup_entries_v1"
GEM_FEATURE = "gem_cups_v1"
KIND = "cup"
SWEEP_KIND = "cup_sweep"
LEG_KIND = "cup_leg"
MODE = "cup"
AWARD = "win"
SWEEP_AWARD = "win_all_legs"
LEG_AWARD = "leg_win"
#: Retail race tracks a leg can be: the 16 Trophy tracks, no trial track.
LEG_RETAIL_IDS = tuple(range(16))
LEGS = 4
FIELD_SIZE = 8
ROSTER = ({"role": "player", "slot": 0},)
PADS = 27
SOURCES = ("retail", "custom", "cortex_vortex")
REPEAT_KEYS = ("within_cup", "across_cups")
DEFAULT_REPEATS = {"within_cup": False, "across_cups": True}
CUP_TRACKS = ("off", "random", "random_no_repeats")
GEM_CUPS = cup_checks.GEM_CUPS
GEM_ENTRY_PREFIX = "entry/gem_cup:"


def error(message):
    raise OptionError("CTR content plan: " + message)


def _bounds(value, path, ceiling):
    if type(value) is int:
        low = high = value
    elif isinstance(value, dict) and set(value) == {"min", "max"} and all(type(v) is int for v in value.values()):
        low, high = value["min"], value["max"]
    else:
        error(f"{path} must be an exact count or {{min, max}}. The requested settings were not changed.")
    if not 0 <= low <= high <= ceiling:
        error(f"{path} must satisfy 0 <= min <= max <= {ceiling}. The requested settings were not changed.")
    return low, high


def settings(raw):
    """The `content_pool.cups` record, checked: {bounds, repeats, sources,
    custom_legs, tracks}. `count` stays required (an explicit 0 for no cups)."""
    if not isinstance(raw, dict) or set(raw) - {"count", "composition", "tracks"}:
        error("content_pool.cups must be a mapping with only count, tracks and composition.")
    if "count" not in raw:
        error("cups.count is required; use an explicit 0 for no cups. The requested settings were not changed.")
    bounds = _bounds(raw["count"], "cups.count", PADS)
    composition = raw.get("composition", {})
    if not isinstance(composition, dict) or set(composition) - {"repeats", "sources", "custom_legs"}:
        error("cups.composition must be a mapping with only repeats, sources and custom_legs.")
    repeats = composition.get("repeats", {})
    if not isinstance(repeats, dict) or set(repeats) - set(REPEAT_KEYS):
        error("cups.composition.repeats must be a mapping with only within_cup and across_cups.")
    out = dict(DEFAULT_REPEATS)
    for key, value in repeats.items():
        if type(value) is not bool:
            error(f"cups.composition.repeats.{key} must be true or false.")
        out[key] = value
    sources = composition.get("sources", list(SOURCES))
    if (not isinstance(sources, list) or not sources or any(s not in SOURCES for s in sources)
            or len(set(sources)) != len(sources)):
        error("cups.composition.sources must be a nonempty list of distinct sources from retail, custom "
              "and cortex_vortex.")
    custom = _bounds(composition.get("custom_legs", {"min": 0, "max": LEGS}), "cups.composition.custom_legs", LEGS)
    # A YAML `off` reaches us as false.
    tracks = "off" if raw.get("tracks") is False else raw.get("tracks", "")
    if "tracks" not in raw:
        tracks = "random" if out["within_cup"] else "random_no_repeats"
    elif tracks not in CUP_TRACKS:
        error("cups.tracks must be off, random or random_no_repeats.")
    out["within_cup"] = tracks == "random"
    return dict(bounds=bounds, repeats=out, sources=set(sources), custom_legs=custom, tracks=tracks)


def leg_pools(candidates, packages, sources):
    """(other, custom): the track candidates a leg can race. `other` holds the
    retail race tracks 0..15; `custom` the custom tracks that can run a
    Trophy race, then Cortex Vortex. Each in a stable order."""
    other = sorted((t for t in candidates if t.get("origin") == "retail" and t["retail_id"] in LEG_RETAIL_IDS
                    and "retail" in sources), key=lambda t: t["retail_id"])
    custom = [t for t in candidates if t.get("origin") == "custom" and "custom" in sources
              and packages[t["package_id"]]["capabilities"]["arcade"]]
    custom.sort(key=lambda t: t["custom_slot"])
    custom += [t for t in candidates if t.get("origin") == "cortex_vortex" and "cortex_vortex" in sources]
    return other, custom


def fixed_legs(spec, candidates):
    """[[four track records]] of the Gem Cups that race their original tracks,
    in cup order, or None when no cup does (any value but `off`). The list stops
    at the first cup with a track the seed's selection leaves out."""
    if spec["tracks"] != "off":
        return None
    records = {t["display_name"]: t for t in candidates if t.get("origin") == "retail"}
    table = gem_cup_legs.load_vanilla_cup_legs()
    out = []
    for cup in GEM_CUPS:
        if any(name not in records for name in table[cup]):
            break
        out.append([records[name] for name in table[cup]])
    return out


def _cup_ok(k, custom_left, other_left, within):
    """One cup with k custom legs fits the tracks left in each pool."""
    if within:
        return (k == 0 or custom_left >= 1) and (k == LEGS or other_left >= 1)
    return k <= custom_left and LEGS - k <= other_left


def _use(k, within, across):
    """(custom, other) tracks one cup with k custom legs takes from the pools."""
    if across:
        return 0, 0
    if within:
        return int(k > 0), int(k < LEGS)
    return k, LEGS - k


def _fits(cups, custom_left, other_left, krange, repeats):
    """Whether `cups` more cups can be drawn."""
    within, across = repeats["within_cup"], repeats["across_cups"]
    lo, hi = krange
    if cups <= 0:
        return True
    if across:
        return any(_cup_ok(k, custom_left, other_left, within) for k in range(lo, hi + 1))
    if not within:
        return max(cups * lo, LEGS * cups - other_left) <= min(cups * hi, custom_left)
    if lo > 0 and hi < LEGS:
        return custom_left >= cups and other_left >= cups
    if lo > 0:
        return custom_left >= cups
    if hi < LEGS:
        return other_left >= cups
    return custom_left + other_left >= cups


def feasible_pairs(spec, crystal_bounds, crystal_pool, required_arenas, required_tracks, other, custom, fixed=None):
    """Every (cups, crystals) pair the seed can seat: both counts in their
    ranges, the crystals within the eligible arena pool and at least the
    required arena entries, cups plus crystals plus required tracks within the
    27 normal pads, a name for every cup, and the legs drawable. `fixed` is
    fixed_legs: a Gem Cup in the seed has to be among them, and draws nothing."""
    cup_bounds = spec["bounds"]

    def drawn(cups):
        return cups if fixed is None else cups - min(cups, len(GEM_CUPS))
    return [(c, k) for c in range(cup_bounds[0], cup_bounds[1] + 1)
            for k in range(crystal_bounds[0], crystal_bounds[1] + 1)
            if required_arenas <= k <= crystal_pool and c + k + required_tracks <= PADS
            and c <= len(cup_checks.CUP_NAMES)
            and (fixed is None or min(c, len(GEM_CUPS)) <= len(fixed))
            and _fits(drawn(c), len(custom), len(other), spec["custom_legs"], spec["repeats"])]


def _pick(world, pool, count, within, available):
    """`count` legs from `pool` (shared across cups when `available` is None)."""
    if not count:
        return []
    if available is None:
        return ([world.random.choice(pool) for _ in range(count)] if within
                else world.random.sample(pool, count))
    if within:
        one = world.random.choice(available)
        available.remove(one)
        return [one] * count
    drawn = world.random.sample(available, count)
    for track in drawn:
        available.remove(track)
    return drawn


def draw_legs(world, cups, other, custom, spec):
    """[[four track records]] per cup under the composition rules: the custom
    leg count of each cup first, then its tracks, then the leg order."""
    within, across = spec["repeats"]["within_cup"], spec["repeats"]["across_cups"]
    lo, hi = spec["custom_legs"]
    other_left, custom_left = (None, None) if across else (list(other), list(custom))
    out = []
    for index in range(cups):
        oc = len(other) if across else len(other_left)
        cc = len(custom) if across else len(custom_left)
        later = cups - index - 1
        ks = [k for k in range(lo, hi + 1) if _cup_ok(k, cc, oc, within)
              and _fits(later, cc - _use(k, within, across)[0], oc - _use(k, within, across)[1],
                        spec["custom_legs"], spec["repeats"])]
        k = world.random.choice(ks)
        legs = _pick(world, custom, k, within, custom_left) + _pick(world, other, LEGS - k, within, other_left)
        world.random.shuffle(legs)
        out.append(legs)
    return out


def base_laps(track):
    """A leg track's authored laps: retail and Cortex Vortex 3, a custom
    package's own."""
    return track["laps"]


def leg_laps(track, shortened):
    return max(1, base_laps(track) // 2) if shortened else base_laps(track)


def draw_cups(world, count, other, custom, spec, shortened, fixed=None):
    """The seed's cups as plan candidates: {cup_index, id, legs, shortened}. The
    first five are the Gem Cups, Red first, with `gem_cup` their colour and
    `cup_index` None. The drawn legs come first, then a sample of the pool's
    name indices for a sixth cup onward. `fixed` is fixed_legs."""
    gems = min(count, len(GEM_CUPS))
    kept = (fixed or [])[:gems]
    legs = kept + draw_legs(world, count - len(kept), other, custom, spec)
    names = world.random.sample(range(len(cup_checks.CUP_NAMES)), count - gems)
    return ([dict(gem_cup=colour, cup_index=None, id=gem_owner(colour), legs=legs[colour], shortened=shortened)
             for colour in range(gems)]
            + [dict(cup_index=index, id=f"cup:{index}", legs=cup_legs, shortened=shortened)
               for index, cup_legs in zip(names, legs[gems:])])


def entry_id(index):
    return f"entry/cup:{index}"


def gem_entry_id(colour):
    return f"{GEM_ENTRY_PREFIX}{colour}"


def owner(index):
    return f"cup:{index}"


def gem_owner(colour):
    return f"gem_cup:{colour}"


def gem_colour(eid):
    """The colour of a Gem Cup's entry id, None for any other id."""
    if not eid.startswith(GEM_ENTRY_PREFIX):
        return None
    digits = eid.removeprefix(GEM_ENTRY_PREFIX)
    return int(digits) if digits in ("0", "1", "2", "3", "4") else None


def win_code(index):
    return cup_checks._pool_code(cup_checks.CUP_WIN_CODE_BASE, cup_checks.CUP_WIN_GROWTH_BASE, index)


def sweep_code(index):
    return cup_checks._pool_code(cup_checks.CUP_SWEEP_CODE_BASE, cup_checks.CUP_SWEEP_GROWTH_BASE, index)


def entry(cup):
    """The plan's Cup entry record for a drawn cup."""
    gem = cup.get("gem_cup")
    eid = entry_id(cup["cup_index"]) if gem is None else gem_entry_id(gem)
    return dict(id=eid, kind=KIND,
                display_name=cup_checks.CUP_NAMES[cup["cup_index"]] if gem is None else GEM_CUPS[gem],
                legs=[dict(id=f"{eid}/leg:{n}", track_id=track["id"], laps=leg_laps(track, cup["shortened"]))
                      for n, track in enumerate(cup["legs"])],
                roster=[dict(r) for r in ROSTER], field_size=FIELD_SIZE)


def mode_gates(first_requirement):
    """A cup pad's one gate: the cup opens with the pad."""
    return [dict(mode=MODE, stage=1, requirement_id=first_requirement)]


def _route(cup_entry, pad_id, award, leg_id=None):
    return dict(entry_id=cup_entry["id"], mode=MODE, leg_id=leg_id, encounter_id=None, own_pad_id=pad_id,
                award=award)


def checks(cup_entry, pad_id, tracks, capability=None, packages=None, sweep=False):
    """The cup's own checks: `<Cup>: Win`, and `<Cup>: Win All Legs` with
    `sweep`, with their boost ranks when Progressive Boost is on. `tracks`
    maps track id to record, `packages` package id to descriptor."""
    index = int(cup_entry["id"].split(":")[1])
    gem = gem_colour(cup_entry["id"]) is not None
    name = GEM_CUPS[index] if gem else cup_checks.CUP_NAMES[index]
    win_name = f"{name}: Gem" if gem else cup_checks.cup_win_name(name)
    win_location = CTR_LOCATION_IDS[win_name] if gem else win_code(index)
    sweep_location = cup_checks.GEM_CUP_SWEEP_CODE_BASE + index if gem else sweep_code(index)
    owned_by = gem_owner(index) if gem else owner(index)
    legs = [tracks[leg["track_id"]] for leg in cup_entry["legs"]]
    packages = packages or {}

    def package(track):
        return packages.get(track.get("package_id"))
    boost = bool(capability and capability.get("boost_mode"))
    win = dict(location=win_location, owner=owned_by, kind=KIND, display_name=win_name,
               routes=[_route(cup_entry, pad_id, AWARD)])
    if boost:
        need = max(finish_boost(t, capability, package(t)) for t in legs)
        if need:
            win["boost"] = need
    out = [win]
    if sweep:
        all_legs = dict(location=sweep_location, owner=owned_by, kind=SWEEP_KIND,
                        display_name=cup_checks.cup_sweep_name(name), routes=[_route(cup_entry, pad_id, SWEEP_AWARD)])
        if boost:
            need = max(check_boost(t, "trophy", "win", capability, package(t)) for t in legs)
            if need:
                all_legs["boost"] = need
        out.append(all_legs)
    return out


def leg_victory_code(track):
    """A track's `Cup Leg Victory` code: the retail name's, Cortex Vortex's
    35027027, a named block's offset 15, or `Custom Track N:`'s."""
    if track["origin"] == "custom" and "named_block" in track:
        return named_tracks.location_code(track["named_block"], "cup_leg_victory")
    stem = f"Custom Track {track['custom_slot']}" if track["origin"] == "custom" else track["display_name"]
    return CTR_LOCATION_IDS[cup_checks.cup_leg_name(stem)]


def leg_victories(tracks, entries, pads, titles):
    """Every `Cup Leg Victory` check of the plan: one per leg track without a
    standalone Trophy Race check, with a route per occurrence in entry order,
    then leg order. `titles` maps track id to its room title."""
    with_trophy = {e["track_id"] for e in entries if e["kind"] == "track" and "trophy" in e["modes"]}
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    out = {}
    for cup_entry in entries:
        if cup_entry["kind"] != KIND or cup_entry["id"] not in pad_of:
            continue
        for leg in cup_entry["legs"]:
            track = tracks[leg["track_id"]]
            if track["id"] in with_trophy:
                continue
            if track["id"] not in out:
                out[track["id"]] = dict(location=leg_victory_code(track), owner=track["id"], kind=LEG_KIND,
                                        display_name=f"{titles[track['id']]}: Cup Leg Victory", routes=[])
            out[track["id"]]["routes"].append(_route(cup_entry, pad_of[cup_entry["id"]], LEG_AWARD, leg["id"]))
    return list(out.values())


def route_boost(cup_entry, leg_id, tracks, capability, packages=None):
    """The rank a Cup Leg Victory route needs: the finish of every earlier leg
    and the Trophy Race rank of its own leg (ordered prefix)."""
    if not capability or not capability.get("boost_mode"):
        return 0
    packages = packages or {}
    need = 0
    for leg in cup_entry["legs"]:
        track = tracks[leg["track_id"]]
        package = packages.get(track.get("package_id"))
        if leg["id"] == leg_id:
            return max(need, check_boost(track, "trophy", "win", capability, package))
        need = max(need, finish_boost(track, capability, package))
    raise KeyError(leg_id)


def prefix_boost(cup_entry, leg_id, tracks, capability, packages=None):
    """The rank reaching a leg needs (#133 PR 5b, a Hit route): the finish of
    every earlier leg, without the leg's own win."""
    if not capability or not capability.get("boost_mode"):
        return 0
    packages = packages or {}
    need = 0
    for leg in cup_entry["legs"]:
        if leg["id"] == leg_id:
            return need
        track = tracks[leg["track_id"]]
        need = max(need, finish_boost(track, capability, packages.get(track.get("package_id"))))
    raise KeyError(leg_id)


def check_lineup(entries):
    """The plan's cups are the Gem Cups Red first, and a pool cup only after
    all five."""
    ids = [e["id"] for e in entries if e["kind"] == KIND]
    gems = sorted(colour for colour in map(gem_colour, ids) if colour is not None)
    if gems != list(range(len(gems))) or (len(gems) < len(GEM_CUPS) and len(gems) != len(ids)):
        error("a plan's first five cups are the Gem Cups, Red first")


def check_entry(cup_entry, tracks, packages, shortened):
    """Shape and registry of one Cup entry against the plan's tracks. Returns
    (entry id, shortened) where `shortened` is the plan-wide lap switch seen
    so far (None before the first leg that tells)."""
    eid = cup_entry["id"]
    gem = gem_colour(eid)
    if gem is None:
        try:
            index = int(eid.removeprefix("entry/cup:"))
        except ValueError:
            index = -1
        if not (eid == entry_id(index) and 0 <= index < len(cup_checks.CUP_NAMES)):
            error("cup entry id is not entry/cup:<name index> or entry/gem_cup:<colour>")
    if cup_entry["display_name"] != (GEM_CUPS[gem] if gem is not None else cup_checks.CUP_NAMES[index]):
        error("cup display name is not its Gem Cup or pool name")
    if cup_entry["roster"] != [dict(r) for r in ROSTER] or cup_entry["field_size"] != FIELD_SIZE:
        error("cup roster or field size is not the Adventure field")
    legs = cup_entry["legs"]
    if len(legs) != LEGS:
        error("a cup has exactly four legs")
    for n, leg in enumerate(legs):
        track = tracks.get(leg["track_id"])
        if leg["id"] != f"{eid}/leg:{n}" or track is None:
            error("a cup leg does not name a track of the plan")
        origin = track.get("origin")
        if not ((origin == "retail" and track["retail_id"] in LEG_RETAIL_IDS) or origin == "cortex_vortex"
                or (origin == "custom" and packages[track["package_id"]]["capabilities"]["arcade"])):
            error("a cup leg is not a retail race track, Cortex Vortex or a custom track with a Trophy race")
        full, short = base_laps(track), max(1, base_laps(track) // 2)
        if leg["laps"] not in (full, short):
            error("a cup leg's laps are not its track's laps or the shortened-cup laps")
        if full != short:
            this = leg["laps"] == short
            if shortened is not None and this != shortened:
                error("cup legs shorten their laps in some legs and not in others")
            shortened = this
    return eid, shortened
