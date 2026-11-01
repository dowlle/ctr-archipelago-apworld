"""Pad placement and pad requirements of a content plan (one generator row 3).

Placement seats the seed's content on the physical pads (`pad_placement`).
Requirements come in two forms:

- Vanilla: each physical pad keeps its original requirement, whatever content
  lands behind it, and every pad with several races takes a Key stage 2 counted
  from the physical pad's hub.
- Random: a **reference placement** gives each check of the plan a stand-in
  item, and the v0.2.x simulated playthrough (warp_pad_logic) runs over it, so
  a pad only asks for items held when the simulated player reaches it. The
  simulation is not rewritten: ReferenceWorld shows it the plan as the region
  graph it already reads. Regions are keyed by physical pad, because the plan
  knows its placement before it draws, so the identity view and the
  re-validation of the original generator have nothing to do here.

`requirement_weights` is the one table, with the any-of counts of
icebound_beta5. Everything here is read from the plan alone or draws from
world.random.
"""
import json
import pkgutil

from . import (arena_content, content_bosses, content_cups, content_item_pool, destinations, sphere0_guard,
               warp_pad_logic, warp_pad_rules)

FEATURE = "pad_requirements_v1"
#: `warppad_unlock_requirements` values and their names on the plan.
MODES = {0: "vanilla", 1: "randomized", 2: "random_without_4_keys"}
PLACEMENTS = ("vanilla", "shuffle_within_kind", "shuffle")
#: Requirement record of a pad's drawn or vanilla stage 1: `stage1:<physical>`.
STAGE1_PREFIX = "stage1:"
#: A redraw of the placement stops after this many tries (Rulebook, 2026-10-30).
PLACEMENT_REDRAWS = 8
#: Tries when a fixed first Key needs room in front of it. A narrow start can miss
#: on most draws, and a draw costs next to nothing.
FIRST_KEY_REDRAWS = 512
SUM_FAMILIES = {"AnyCtrToken": warp_pad_rules.TOKENS, "AnyRelic": warp_pad_rules.RELICS,
                "AnyGem": warp_pad_rules.GEMS}
PADS = json.loads(pkgutil.get_data(__package__, "data/warp_pad_ids.json"))["pads"]
KEY_BY_PHYSICAL = {d.level_id: d.key for d in destinations.DESTINATIONS}
PHYSICAL_KIND = {row["level_id"]: ("track" if row["kind"] in ("race", "trial") else
                                   "arena" if row["kind"] == "crystal" else "cup")
                 for row in PADS.values()}
#: The four N. Sanity Beach race pads never carry a racer lock.
BOOTSTRAP_PADS = frozenset(row["level_id"] for row in PADS.values() if row.get("bootstrap"))
TOKEN_COLOUR = destinations.token_colours()
SAPPHIRE_PAD_COUNT = 10
CUP_TOKENS = 4
#: Vanilla stage 2 Keys of a Gem Stone Valley trial pad and of a Cups Room pad.
TRIAL_STAGE2_KEYS = 2
CUP_STAGE2_KEYS = 3


def vanilla_rule(physical):
    """The original requirement of a physical pad as (item, count), None for a
    pad that opens with its hub. Counts are the game's; vanilla_requirements
    clamps them to the seed's items."""
    title = KEY_BY_PHYSICAL[physical]
    row = PADS[title + " Warp Pad"]
    kind = row["kind"]
    if kind == "race":
        return ("Trophy", row["vanilla_trophies"]) if row["vanilla_trophies"] else None
    if kind == "crystal":
        return ("Key", vanilla_stage2_keys(physical))
    if kind == "trial":
        return ("Sapphire Relic", SAPPHIRE_PAD_COUNT) if title == "Slide Coliseum" else ("AnyGem", 5)
    return (title.split()[0] + " CTR Token", CUP_TOKENS)


def vanilla_stage2_keys(physical):
    """Keys of the vanilla stage 2, from the physical pad's hub. A Crystal
    Challenge pad's vanilla stage 1 asks the same number: one above its hub."""
    if PHYSICAL_KIND[physical] == "cup":
        return CUP_STAGE2_KEYS
    title = KEY_BY_PHYSICAL[physical]
    if PADS[title + " Warp Pad"]["kind"] == "trial":
        return TRIAL_STAGE2_KEYS
    gate = destinations.hub_static()[title]
    return (gate[0][1] if gate else 0) + 1


def rule_predicate(rule, by_name):
    """The plan's predicate of (item, count), over the base items. None when the
    seed has none of the item: the pad then asks for nothing."""
    item, count = rule
    names = [n for n in SUM_FAMILIES.get(item, (item,)) if by_name[n].requirement_ceiling > 0]
    supply = sum(by_name[n].requirement_ceiling for n in names)
    count = min(count, supply)
    if not count:
        return None
    if item in SUM_FAMILIES:
        return dict(op="sum", items=[by_name[n].item for n in names], count=count)
    return dict(op="count", item=by_name[item].item, count=count)


def vanilla_requirements(entries, by_name, density_off):
    """({physical: stage 1 predicate}, {physical: stage 2 predicate}) of the
    vanilla mode. `entries` is {physical: modes of the pad's track, or ()}."""
    stage1, stage2 = {}, {}
    for physical, modes in entries.items():
        rule = vanilla_rule(physical)
        predicate = rule_predicate(rule, by_name) if rule else None
        if predicate:
            stage1[physical] = predicate
        if len(modes) > 1 and not density_off:
            stage2[physical] = rule_predicate(("Key", vanilla_stage2_keys(physical)), by_name)
    return stage1, stage2


# Placement

def content_kind(item):
    return "arena" if "arena_id" in item else "cup" if "cup_index" in item else "track"


def home_pad(item):
    """The physical pad that holds this content in the original game, or None."""
    if "arena_id" in item:
        return item["arena_id"] if item["arena_id"] in PHYSICAL_KIND else None
    if "cup_index" in item:
        return 100 + item["gem_cup"] if item.get("gem_cup") is not None else None
    return item.get("retail_id")


def _seat(world, chosen, seats, placement, manual):
    """{physical: content}. `seats` is the shuffled pad list."""
    rnd = world.random
    out, left = {}, []
    if placement == "vanilla":
        for item in chosen:
            home = home_pad(item)
            if home is None:
                left.append(item)
            else:
                out[home] = item
    elif placement == "shuffle_within_kind":
        for kind in ("track", "cup", "arena"):
            contents = [item for item in chosen if content_kind(item) == kind]
            rnd.shuffle(contents)
            pads = [seat[0] for seat in seats if PHYSICAL_KIND[seat[0]] == kind]
            out.update(zip(pads, contents))
            left += contents[len(pads):]
    else:
        contents = list(chosen)
        rnd.shuffle(contents)
        out.update(zip([seat[0] for seat in seats], contents))
    # Content that does not fit its own kind of pad takes any free pad; its own
    # kind first, so a custom track on `vanilla` stays on a track pad if it can.
    for item in left:
        free = [seat[0] for seat in seats if seat[0] not in out]
        own = [physical for physical in free if PHYSICAL_KIND[physical] == content_kind(item)]
        out[(own or free)[0]] = item
    # A manual rule's seat always hosts content (warp_pad_rules rule 8).
    for physical in sorted(manual):
        if physical not in out:
            donors = sorted(p for p in out if p not in manual)
            out[physical] = out.pop(rnd.choice(donors))
    return out


def own_content(seated):
    """Every piece of content sits on its original pad, and at least one has one."""
    homes = [(physical, home_pad(item)) for physical, item in seated.items() if home_pad(item) is not None]
    return bool(homes) and len(homes) == len(seated) and all(p == h for p, h in homes)


def capacity_met(seated, seats, rungs):
    """The trophy-capable slots of each boss floor (warp_pad_logic._BOSS_CAP_FLOORS):
    a track holds its race and rungs, an arena one check, a cup counts none, so
    too many cups on early pads fail the floor (Rulebook, destinations rule 5)."""
    keys_of = {seat[0]: seat[2] for seat in seats}
    for floor, keys in warp_pad_logic._BOSS_CAP_FLOORS:
        capacity = sum(0 if content_kind(item) == "cup" else 1 if content_kind(item) == "arena" else 1 + rungs
                       for physical, item in seated.items() if keys_of[physical] <= keys)
        if capacity < floor:
            return False
    return True


def seat_content(world, chosen, seats, placement, manual, rungs, reach, start_checks, cycle=None, near_floor=0,
                 key_fits=None):
    """(content in pad order, seats with the occupied ones first): `seats[i]`
    holds `chosen[i]`. A draw that leaves all content at home, too many cups on
    early pads, too few checks open at the start or content on a pad that needs
    that content's own fixed item (`cycle(physical, content)`) is drawn again, at
    most PLACEMENT_REDRAWS times. With vanilla requirements `reach(seat)` is 2 for a
    pad that can open at the start, 1 for one just behind it, else 0, and
    `start_checks(content)` counts the checks it then opens with no items, aimed
    at the start the guards call wide: arenas, cups or boost terms can leave
    little on the two open pads. Random requirements pass None: their free pads
    are drawn with the start in mind (draw). If none fits, the best draw
    stands: one with no such cycle, then one that passes the first two tests,
    then the best early pads, and `shuffle` then trades content onto the open
    pads. Vanilla placement never redraws. `near_floor` asks that many checks of
    the pads with `reach`, for a fixed first Key behind a Trophy garage, and
    `key_fits(seated)` is the final capacity check in front of that Key. It only
    ever draws again, up to FIRST_KEY_REDRAWS times: the best draw stands."""
    seats = list(seats)
    weight = {seat[0]: reach(seat) if reach else 0 for seat in seats}
    need = min(sphere0_guard.NARROW_START_CHECKS, sum(start_checks(item) for item in chosen)) if reach else 0
    best, best_score = None, (False, False, False, -1)
    for _ in range(FIRST_KEY_REDRAWS if key_fits else PLACEMENT_REDRAWS):
        world.random.shuffle(seats)
        seated = _seat(world, chosen, seats, placement, manual)
        start = sum(start_checks(item) for physical, item in seated.items() if weight[physical] == 2)
        fits = not own_content(seated) and capacity_met(seated, seats, rungs)
        clear = not (cycle and any(cycle(physical, item) for physical, item in seated.items()))
        near = sum(start_checks(item) for physical, item in seated.items() if weight[physical])
        room = key_fits is None or key_fits(seated)
        if placement == "vanilla" or (clear and fits and start >= need and near >= near_floor and room):
            best = None
            break
        score = (clear, room, fits, sum(weight[physical] * start_checks(item) for physical, item in seated.items()))
        if score > best_score:
            best, best_score = (list(seats), seated), score
    if best:
        seats, seated = best
    if placement == "shuffle" and reach and not (key_fits and key_fits(seated)):
        # Still short: content that opens nothing at the start trades places
        # with content that does, as the open empty pad swap does for a gap.
        for physical in [p for p in seated if weight[p] == 2]:
            if sum(start_checks(seated[p]) for p in seated if weight[p] == 2) >= need:
                break
            donors = sorted((p for p in seated if weight[p] < 2 and p not in manual
                             and start_checks(seated[p]) > start_checks(seated[physical])
                             and not (cycle and cycle(p, seated[physical]))),
                            key=lambda p: (-start_checks(seated[p]), p))
            if donors and physical not in manual:
                seated[physical], seated[donors[0]] = seated[donors[0]], seated[physical]
    # No redraw cleared a cycle: its content trades places, the deepest pad first.
    for physical in [p for p, item in seated.items() if cycle and cycle(p, item)]:
        others = sorted((p for p in seated if not cycle(p, seated[physical]) and not cycle(physical, seated[p])
                         and p not in manual), key=lambda p: (weight[p], p))
        if others:
            seated[physical], seated[others[0]] = seated[others[0]], seated[physical]
        else:
            seated[next(seat[0] for seat in seats if seat[0] not in seated)] = seated.pop(physical)
    ordered = sorted(seated, key=[seat[0] for seat in seats].index)
    by_physical = {seat[0]: seat for seat in seats}
    return [seated[p] for p in ordered], [by_physical[p] for p in ordered] + [s for s in seats if s[0] not in seated]


# Reference placement

def stand_ins(world, checks, entries, pads, pad_modes, rows, skip, pins=None):
    """{check location: stand-in item name}. Fixed items stand on their own checks
    (`pins`, {location code: item name}). Then the Keys: the n-th Key goes on a
    check open with n - 1 Keys, a first race on a pad of that hub depth, so
    the simulated player always walks on to the next hub. A garage asks for a
    drawn requirement, and a Key held behind it could freeze the simulation at
    N. Sanity Beach, leaving every later pad a trivial requirement. Then a check
    holds the original reward where its content matches, while the seed has
    copies, and the other copies are spread over the remaining checks. Only
    the base items take part, as a requirement never asks above them. `skip`
    lists checks that hold no progression (the Oxide goal, excluded checks)."""
    supply = {row.name: row.requirement_ceiling for row in rows if row.name in content_item_pool.COUNTED_NAMES}
    out = {code: name for code, name in (pins or {}).items() if name in supply}
    for name in out.values():
        supply[name] -= 1
    entry_by_id = {e["id"]: e for e in entries}
    pad_by_id = {pad["id"]: pad for pad in pads}
    usable = []
    for check in checks:
        own = {route["own_pad_id"] for route in check["routes"]}
        if (len(own) == 1 and check["location"] not in skip and check["kind"] != content_cups.LEG_KIND
                and own != {f"garage:{content_bosses.OXIDE_GARAGE}"}):
            usable.append(check)

    def hub_keys(check):
        """Keys that open a first-race check of a normal pad, else None."""
        pad = pad_by_id[check["routes"][0]["own_pad_id"]]
        modes = pad_modes.get(int(pad["id"].split(":")[1]), ()) if pad["kind"] == "normal" else None
        if modes is None or (len(modes) > 1 and not any(r["mode"] == modes[0] for r in check["routes"])):
            return None
        return 0 if pad["entrance_req"] == "free" else int(pad["entrance_req"].removeprefix("keys:"))

    for keys in range(supply.get("Key", 0)):
        open_here = sorted(c["location"] for c in usable
                           if c["location"] not in out and hub_keys(c) is not None and hub_keys(c) <= keys)
        if open_here:
            out[world.random.choice(open_here)] = "Key"
            supply["Key"] -= 1
    open_checks = []
    for check in usable:
        if check["location"] in out:
            continue
        route = check["routes"][0]
        want = _reward(check, route, entry_by_id[route["entry_id"]], entry_by_id)
        if want is not None and supply.get(want, 0) > 0:
            supply[want] -= 1
            out[check["location"]] = want
        else:
            open_checks.append(check["location"])
    world.random.shuffle(open_checks)
    copies = [name for name in sorted(supply) for _ in range(supply[name])]
    world.random.shuffle(copies)
    out.update(zip(open_checks, copies))
    return out


def _reward(check, route, entry, entries):
    kind = check["kind"]
    if kind == "trophy":
        return "Trophy"
    if kind == "ctr":
        colour = TOKEN_COLOUR.get(check["display_name"].split(":")[0])
        return f"{colour} CTR Token" if colour else None
    if kind == "relic":
        return route["award"].capitalize() + " Relic"
    if kind == "crystal":
        return None if entry["arena_id"] in arena_content.ARCADE else "Purple CTR Token"
    if kind == content_cups.KIND:
        colour = content_cups.gem_colour(entry["id"])
        return None if colour is None else content_cups.GEM_CUPS[colour].split()[0] + " Gem"
    if kind in content_bosses.KINDS:
        return "Key"
    return None


class _Variety:
    current_key = "one_table"


class _Arenas:
    value = 1


class _Options:
    """The world's options as the simulation reads them: `requirement_weights`
    is the one table, and a plan pad sits behind its hub's Keys alone."""
    requirement_variety = _Variety
    include_battle_arenas = _Arenas

    def __init__(self, options):
        self._options = options

    def __getattr__(self, name):
        return getattr(self._options, name)


class _Exit:
    def __init__(self, name, region, gate):
        self.name, self.connected_region, self.access_rule_text = name, region, gate


class _Location:
    """A check of the reference placement. `logic_text` is only set while the
    start is measured: a check that needs a boost rank or stats, or that holds a
    fixed item, is not open at the start, but the simulated player can still win
    it later."""

    def __init__(self, view, name, check):
        self.view, self.name = view, name
        self.stand_in = view.stands.get(check["location"]) if check else None
        self.gated = bool(check and (check.get("boost") or check.get("stats") or check["location"] in view.pins))

    @property
    def logic_text(self):
        return "has('Not held', 1)" if self.gated and self.view.measuring else ""


class _Region:
    def __init__(self, name, kind="generic"):
        self.name, self.type = name, kind
        self.exits, self.locations = [], []


class _Multiworld:
    def __init__(self, regions):
        self.regions = regions

    def get_regions(self, _player):
        return self.regions


class ReferenceWorld:
    """What warp_pad_logic reads of a world, for the plan's reference placement.

    Each occupied pad is a region named for its physical pad, behind an exit
    with the pad's hub Key floor. The first race's first check is the region's
    `<pad>: Trophy Race`, which the simulation uses as "the first race is won";
    a check only a later race can open has the name ending the simulation holds
    back for stage 2. Garages take their drawn requirement as the exit gate."""
    start_region = None
    measuring = False

    def __init__(self, world, pads, pad_modes, checks, encounters, requirements, stands, relics, by_code, pins=()):
        self.random = world.random
        self.options = _Options(world.options)
        self.player = world.player
        self._ctr_relic_created = relics
        self._ctr_pad_rules = getattr(world, "_ctr_pad_rules", None)
        self.stands, self.pins = stands, pins
        menu = _Region("Menu")
        regions = [menu]
        by_pad = {}
        for check in checks:
            if len({route["own_pad_id"] for route in check["routes"]}) == 1:
                by_pad.setdefault(check["routes"][0]["own_pad_id"], []).append(check)
        multi, occupied = set(), []
        for pad in pads:
            physical = pad["id"].split(":")[1]
            if pad["kind"] != "normal" or pad["entry_id"] is None:
                continue
            title = KEY_BY_PHYSICAL[int(physical)]
            region = _Region(title)
            regions.append(region)
            occupied.append(title)
            keys = pad["entrance_req"].removeprefix("keys:") if pad["entrance_req"] != "free" else None
            menu.exits.append(_Exit(title + " Warp Pad", region, f"has('Key', {keys})" if keys else "True"))
            modes = pad_modes.get(int(physical), ())
            if len(modes) > 1:
                multi.add(title)
            region.locations += self._pad_locations(title, modes, by_pad.get(pad["id"], ()))
        for encounter in encounters:
            garage = int(encounter["pad_id"].split(":")[1])
            if garage >= content_bosses.OXIDE_GARAGE:
                continue
            region = _Region(encounter["pad_id"], "boss")
            regions.append(region)
            keys = content_bosses.GARAGES[garage][2]
            gates = [f"has('Key', {keys})"] if keys else []
            gates.append(_gate_text(requirements[encounter["requirement_id"]], by_code))
            menu.exits.append(_Exit(encounter["pad_id"], region, " and ".join(gates)))
            region.locations += [_Location(self, f"{encounter['pad_id']}: {c['location']}", c)
                                 for c in by_pad.get(encounter["pad_id"], ())]
        self.multiworld = _Multiworld(regions)
        self.ctr_stage2_destinations = frozenset(multi)
        self.ctr_sim_pads = tuple(occupied)

    def _pad_locations(self, title, modes, checks):
        if len(modes) < 2:
            return [_Location(self, f"{title}: {c['location']}", c) for c in checks]
        first = [c for c in checks if any(route["mode"] == modes[0] for route in c["routes"])]
        primary = next((c for c in first if c["kind"] in (modes[0], "trophy")), first[0] if first else None)
        out = [_Location(self, f"{title}: Trophy Race", primary)]
        for check in checks:
            if check is primary:
                continue
            name = f"{title}: {check['location']}"
            out.append(_Location(self, name if check in first else name + " CTR Token Challenge", check))
        return out

    def free_every_open_pad(self):
        """Count every pad behind no Key as a free pad the player chose."""
        gates = {e.name.removesuffix(" Warp Pad"): e.access_rule_text for e in self.multiworld.regions[0].exits}
        self._ctr_pad_rules = {**{title: None for title, gate in gates.items() if gate == "True"},
                               **(self._ctr_pad_rules or {})}

    def breadth(self, out, held=()):
        """Checks a finished draw opens at the start, `held` counted as owned."""
        self.measuring = True
        reach = warp_pad_logic._sphere0_breadth(self, out, lambda t: t, True, held)
        self.measuring = False
        return reach


def _gate_text(predicate, by_code):
    """A garage predicate as the `has(...)` text the simulation parses."""
    if predicate["op"] == "count":
        return f"has('{by_code[predicate['item']]}', {predicate['count']})"
    names = {by_code[code] for code in predicate["items"]}
    label = next(label for label, family in SUM_FAMILIES.items() if names <= set(family))
    return f"has('{label}', {predicate['count']})"


def draw(view, mode, collapse):
    """{pad title: (stage 1 rule, stage 2 rule)} from the simulation.

    As on v0.2.x (warp_pad_logic.run_sphere_search) a narrow start draws again.
    The last step differs, in the order of the start guards (dispatcher,
    2026-10-30): a start a single item widens keeps its second stages, since
    the early item takes it (sphere0_guard.mark_early_opener). Only a start no
    item widens loses them, silently."""
    def attempts(best, width, without_stage2):
        for _ in range(warp_pad_logic._SPHERE0_REPAIR_TRIES):
            out = warp_pad_logic._run_sphere_search_once(view, mode, None, without_stage2, True)
            reach = view.breadth(out)
            if reach > width:
                best, width = out, reach
            if reach >= warp_pad_logic._SPHERE0_MIN_BREADTH:
                break
        return best, width

    best, width = attempts(None, -1, collapse)
    if width < warp_pad_logic._SPHERE0_MIN_BREADTH:
        if width < sphere0_guard.MIN_STARTING_CHECKS:
            # Every open pad goes free, the top of the 3 to 5 free pads, before
            # a seed is refused for its start.
            view.free_every_open_pad()
            best, width = attempts(best, width, collapse)
        if not collapse and not any(view.breadth(best, (name,)) > width for name in warp_pad_logic.Inv.CAPS):
            best, width = attempts(best, width - 1, True)
    return {title: (stages[1], stages[2]) for title, stages in best.items() if title in view.ctr_sim_pads}


def check_record(plan, stage1, stage2, manual, rows, require):
    """The `pad_requirements` record against the plan's gates. The draw is not
    recomputed (the plan carries the result). Vanilla is a fixed table; a drawn
    stage keeps its count ceiling and a stage 2 asks more than its stage 1; the
    no-4-Key mode bars the Key count everywhere it is drawn."""
    record = plan["pad_requirements"]
    mode = record["mode"]
    key = content_item_pool.ITEMS["Key"]
    if mode == "vanilla":
        by_name = {row.name: row for row in rows}
        entries = {e["id"]: e for e in plan["entries"]}
        modes = {int(p["id"].split(":")[1]): (entries[p["entry_id"]].get("modes", ()) if entries[p["entry_id"]]["kind"] == "track" else ())
                 for p in plan["pads"] if p["kind"] == "normal" and p["entry_id"] is not None}
        want1, want2 = vanilla_requirements(modes, by_name, not stage2)
        require({int(rid.split(":")[1]): row["predicate"] for rid, row in stage1.items()} == want1,
                "vanilla stage 1 requirements do not match the physical pads")
        require({int(rid.split(":")[1]): row["predicate"] for rid, row in stage2.items()} == want2,
                "vanilla stage 2 requirements do not match the physical pads")
        return
    first = {int(rid.split(":")[1]): row["predicate"] for rid, row in {**stage1, **manual}.items()}
    for row in stage1.values():
        predicate = row["predicate"]
        require(predicate.get("item") == key or predicate["count"] <= warp_pad_logic._STAGE1_COUNT_CEILING,
                "a drawn stage 1 asks above its count ceiling")
    for rid, row in stage2.items():
        predicate = row["predicate"]
        require(predicate.get("item") == key or predicate["count"] <= warp_pad_logic._STAGE2_COUNT_CEILING,
                "a drawn stage 2 asks above its count ceiling")
        before = first.get(int(rid.split(":")[1]))
        require(before is None or predicate["count"] > before["count"]
                or not set(before.get("items", [before.get("item")])) <= set(predicate.get("items", [predicate.get("item")])),
                "a stage 2 asks no more than its stage 1")
    if mode == "random_without_4_keys":
        require(not any(row["predicate"]["op"] == "count" and row["predicate"]["item"] == key
                        and row["predicate"]["count"] >= 4 for row in {**stage1, **stage2, **manual}.values()),
                "random_without_4_keys asks for 4 Keys")
