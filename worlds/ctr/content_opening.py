"""The opening of a content plan: which items open the seed, and whether the
layout has room for them (one generator row 8b).

AP's fill places items backwards, so the items the start depends on come last,
when only a few checks are left for them. Each of those items takes a spot, and a
gate that needs several items pays for all of them before it opens anything. A
layout whose best opening leaves no room fails the fill whatever the order, and
the room left separates the seeds well: measured on six failing YAMLs, 150 seeds
each, no seed left with 5 or more failed, and nearly all left with 3 or fewer did.

`search` finds the opening. It is pure and works on any `room(held)`: the real
rules in the start bootstrap (sphere0_guard), and `PlanReach` in generate, where
no rule exists yet. A plan that leaves less than FIT_ROOM spots draws again
(content_plan.generate). Neither refuses a seed: the best draw stands.
"""
import heapq
import itertools
from collections import Counter

from . import content_bosses, content_capability, content_cups, content_fixed, content_laps, content_wumpa

#: Spots an opening has to leave, or a quarter of the plan's checks on a small one.
FIT_ROOM = 5
#: Spots to spare in front of each fixed Key. Dense pools fill most of them with
#: other progression (row 8b: 16 Relics asked of 21 spots stalled the fill).
KEY_SLACK = 12
#: Largest group of three or more kinds of item.
MIXED_GROUP = 4
#: `room` calls of one search. A fair search takes a few dozen.
PROBES = 300


def search(pool, room, target, reached=None, probes=PROBES, bundles=(), goals=()):
    """(names to seat in order, spots they leave open). `pool` is {name: copies},
    `room(held)` counts the spots open with the sorted tuple `held`, and an item
    takes one of them. A step needs its spots open before it, so a gate that needs
    several items is taken as one group, and one that does not fit is no step.
    Stops at `target` spots left; else the best opening found stands. With
    `reached(held)`, an opening also has to reach what it tests, and one that does
    beats one that does not. `bundles` are groups taken only whole: one track's
    letter items (letter_bundles). Their names are in `pool` but in no other step."""
    memo = {}
    spent = [0]
    loose = {name for bundle in bundles for name in bundle}

    def free(held):
        key = tuple(sorted(held))
        if key not in memo:
            memo[key] = room(key) - len(key)
        return memo[key]

    def done(held):
        return reached is None or reached(tuple(sorted(held)))

    start = free(())
    if start >= target and done(()):
        return [], start
    # A gate's items: what the whole pool cannot do without. Groups use only those.
    names = [name for name in sorted(pool) if name not in loose]
    rich = tuple(name for name in names for _ in range(pool[name]))
    full = free(rich) + len(rich)
    needed = [name for name in names
              if free(tuple(n for n in rich if n != name)) + len(rich) - pool[name] < full]

    def left(held, name):
        return pool.get(name, 0) - held.count(name)

    def opening(held, spots, groups):
        """The groups that open something, within the probe budget."""
        out = []
        for group in itertools.islice(groups, max(0, probes - spent[0])):
            spent[0] += 1
            if free(held + group) + len(group) > spots:
                out.append(group)
        return out

    def fits(held, group):
        return all(left(held, name) >= group.count(name) for name in set(group))

    def bundle_seats(held, group):
        # A letter can open its own check before the next letter is seated.
        # Pay every prefix; a jointly gated bundle still needs all its slots.
        for n in range(len(group)):
            if spent[0] >= probes:
                return False
            spent[0] += 1
            if free(held + group[:n]) <= 0:
                return False
        return True

    def moves(held, spots):
        spent[0] += len(names)
        singles = sorted(((free(held + (name,)), name) for name in names if left(held, name)), reverse=True)
        found = [(name,) for after, name in singles if after + 1 > spots]
        # A fixed-Key garage can need many copies that open nothing until
        # its whole demand is held. Seat those together when they fit, paying
        # for every copy, alongside the ordinary capacity-opening moves.
        for goal in goals:
            remaining = tuple(name for name, count in Counter(goal).items()
                              for _ in range(max(0, count - held.count(name))))
            if remaining and len(remaining) <= spots and fits(held, remaining):
                found.append(remaining)
        if found:
            return found
        # A track's letters are one search move, with each seat proved in order.
        if bundles:
            found = opening(held, spots, [bundle for bundle in bundles if fits(held, bundle) and bundle_seats(held, bundle)])
            if found or spent[0] >= probes:
                return found
        # One kind first, then two: a garage asks that, at any count. Then any mix.
        # Copies of one kind come at every count before any pair, or the pairs of
        # many kinds (a boost per racer) spend the probes before three of a kind.
        found = opening(held, spots, [(name,) * size for size in range(2, spots + 1) for name in needed
                                      if fits(held, (name,) * size)])
        if found or spent[0] >= probes:
            return found
        for size in range(2, spots + 1):
            groups = [(a,) * n + (b,) * (size - n) for a, b in itertools.combinations(needed, 2) for n in range(1, size)]
            found = opening(held, spots, [group for group in groups if fits(held, group)])
            if found or spent[0] >= probes:
                return found
        for size in range(3, min(spots, MIXED_GROUP) + 1):
            found = opening(held, spots, (group for group in itertools.combinations_with_replacement(needed, size)
                                          if len(set(group)) > 2 and fits(held, group)))
            if found or spent[0] >= probes:
                return found
        return []

    best = (done(()), start, ())
    todo = [(not best[0], -start, 0, ())]
    seen = {()}
    while todo and spent[0] < probes:
        _undone, _rank, _length, held = heapq.heappop(todo)
        spots = free(held)
        finished = done(held)
        if (finished, spots, -len(held)) > (best[0], best[1], -len(best[2])):
            best = (finished, spots, held)
        if finished and spots >= target:
            break
        if spots > 0:
            for group in moves(held, spots):
                after = held + group
                key = tuple(sorted(after))
                if key not in seen:
                    seen.add(key)
                    heapq.heappush(todo, (not done(after), -free(after), len(after), after))
    return list(best[2]), best[1]


def term_met(node, held):
    """A plan predicate against {item code: count}. Boss wins and the Wumpa goal arm
    stand far behind an opening, and count as shut."""
    op = node["op"]
    if op == "always":
        return True
    if op == "count":
        return held.get(node["item"], 0) >= node["count"]
    if op == "sum":
        return sum(held.get(code, 0) for code in node["items"]) >= node["count"]
    if op == "distinct":
        return sum(bool(held.get(code, 0)) for code in node["items"]) >= node["count"]
    if op == "all":
        return all(term_met(term, held) for term in node["terms"])
    if op == "any":
        return any(term_met(term, held) for term in node["terms"])
    return False


def gate_names(plan, by_code, boost_item):
    """Names of the items a pad, garage or boss asks for, with the boost and the
    racer locks. Other items open little more than their own check, so an opening
    can do without them, and Lettersanity alone would add over a hundred names to
    the search. That only ever finds less room than the seed has."""
    from .characters import CHARACTER_ID_TO_NAME
    from .progressive_capability import boost_item_name
    codes = set()

    def walk(node):
        codes.update(node.get("items", ()))
        if "item" in node:
            codes.add(node["item"])
        for term in node.get("terms", ()):
            walk(term)

    for row in plan["requirements"]:
        walk(row["predicate"])
    names = {by_code[code] for code in codes if code in by_code}
    racers = {CHARACTER_ID_TO_NAME[pad["racer_lock"]] for pad in plan["pads"] if pad["racer_lock"] is not None}
    names |= racers | ({boost_item} if boost_item else set())
    if plan.get("capability", {}).get("boost_mode") == 2:
        names.update(boost_item_name(racer) for racer in racers)
    return names


def letter_bundles(plan, pool):
    """Each track's letter items that gate its CTR Token, as one group, when every
    one of them is in `pool`. Lettersanity with letter items only: () otherwise.
    A letter opens little alone, but a track's letters open its letter checks and
    its Token, which on a `ctr_first` pad can be the most the start has."""
    from .content_plan import letter_requirements
    groups = {names for names in letter_requirements(plan).values()}
    return sorted(group for group in groups
                  if not any(set(group) < set(other) for other in groups)
                  and all(pool.get(name, 0) > 0 for name in group))


def garage_demands(node, pool, base, names_by_code):
    """Whole item multisets that satisfy a garage's exported predicate.

    Precollected copies need no spot. Fixed rewards that are not in the pool
    are reached through the normal opening search, never invented here.
    """
    op = node["op"]
    if op == "always":
        return [()]
    if op == "count":
        name = names_by_code[node["item"]]
        count = max(0, node["count"] - base.get(node["item"], 0))
        return [(name,) * count] if pool.get(name, 0) >= count else []
    if op in ("sum", "distinct"):
        need = max(0, node["count"] - sum(bool(base.get(code, 0)) if op == "distinct" else base.get(code, 0)
                                          for code in node["items"]))
        names = [(names_by_code[code], min(pool.get(names_by_code[code], 0), 1) if op == "distinct"
                  else pool.get(names_by_code[code], 0)) for code in node["items"]
                 if op != "distinct" or not base.get(code, 0)]

        def ways(index, left):
            if left == 0:
                yield ()
            elif index < len(names):
                name, count = names[index]
                for taken in range(min(count, left) + 1):
                    for tail in ways(index + 1, left - taken):
                        yield (name,) * taken + tail

        return list(ways(0, need))
    children = [garage_demands(term, pool, base, names_by_code) for term in node.get("terms", [])]
    if op == "any":
        return [group for child in children for group in child]
    if op == "all":
        out = []
        for choice in itertools.product(*children):
            counts = Counter()
            for group in choice:
                counts |= Counter(group)
            out.append(tuple(name for name, count in sorted(counts.items()) for _ in range(count)))
        return out
    return []


class PlanReach:
    """The checks open with some items held, read from a finished plan. It follows
    create_regions: hub Keys, a pad's stage 1, a later race's stage 2 and first
    race won, boost ranks, letters and the `ctr_first` Trophy win. A fixed item
    counts once its check is open. What it cannot see counts as shut, so it finds no
    more room than the seed has: a stat term, Itemsanity's weapon arm, and the
    Itemsanity and Hit checks, whose rules ask for a weapon or a kart."""

    def __init__(self, plan, rows, excluded, boost_item):
        self.plan = plan
        from .characters import CHARACTER_ID_TO_NAME
        from .content_plan import first_race_checks, letter_requirements, merged_race
        from .progressive_capability import boost_item_name
        self.req = {row["id"]: row["predicate"] for row in plan["requirements"]}
        self.pads = {pad["id"]: pad for pad in plan["pads"]}
        self.encounters = {e["id"]: e for e in plan["encounters"]}
        self.code = {row.name: row.item for row in rows}
        self.boost = self.code.get(boost_item)
        self.base = {row.item: row.start_from_pool + row.start_additional for row in rows}
        self.pool = {row.name: row.remaining for row in rows if row.remaining > 0}
        self.letters = letter_requirements(plan)
        self.pins = {code: self.code[name] for code, name in content_fixed.plan_placements(plan).items()
                     if name in self.code}
        pins = content_fixed.plan_placements(plan)
        tracks = {t["id"]: t for t in plan["tracks"]}
        packages = {p["id"]: p for p in plan["packages"]}
        capability = plan.get("capability", {})
        entries = {e["id"]: e for e in plan["entries"]}
        goal = content_bosses.goal_location(plan["bosses"]) if plan.get("bosses") else None
        shop = plan.get("wumpa_shop")
        floors = {code: content_wumpa.KEY_FLOORS[hub] for hub, _n, code, _name in content_wumpa.slots(shop)} if shop else {}
        spare_shop = bool(shop) and shop["progression"] != "excluded"
        by_pad = {}
        for check in plan["checks"]:
            own = {route["own_pad_id"] for route in check["routes"]}
            if len(own) == 1:
                by_pad.setdefault(next(iter(own)), []).append(check)
        self.first = {}
        for pad_id, pad in self.pads.items():
            modes = [gate["mode"] for gate in pad["mode_gates"]]
            if len(modes) > 1:
                self.first[pad_id] = first_race_checks(by_pad.get(pad_id, ()), modes[0])
        merged = {}
        for pad_id, checks in by_pad.items():
            if merged_race(checks):
                codes = {c["kind"]: c["location"] for c in checks}
                merged[codes["ctr"]] = codes["trophy"]
        self.merged = merged

        def rank(check, route):
            track = tracks.get(check["owner"])
            if check["kind"] == content_cups.LEG_KIND:
                return content_cups.route_boost(entries[route["entry_id"]], route["leg_id"], tracks, capability, packages)
            if check["kind"] == content_laps.KIND and capability.get("boost_mode"):
                package = packages.get(track.get("package_id"))
                need = content_capability.finish_boost(track, capability, package)
                if route["leg_id"] is not None:
                    need = max(need, content_cups.prefix_boost(entries[route["entry_id"]], route["leg_id"], tracks,
                                                               capability, packages))
                return need
            if route["leg_id"] is not None and check["kind"] in ("wumpa", "podium"):
                # A cup leg route of a Wumpa check or rung (row 10i): the
                # earlier legs' finish, with the check's own rank on top.
                return max(check.get("boost", 0), content_cups.prefix_boost(entries[route["entry_id"]], route["leg_id"],
                                                                           tracks, capability, packages))
            return check.get("boost", 0)

        def region(route):
            own = route.get("encounter_id") or route["own_pad_id"]
            if own.startswith("garage:"):
                return next(e["id"] for e in plan["encounters"] if e["pad_id"] == own)
            return own

        def later(route):
            gates = self.pads[route["own_pad_id"]]["mode_gates"]
            return bool(gates) and gates[0]["mode"] != route["mode"]

        def boost_of(route):
            # Per racer boost: a locked pad counts that racer's own ranks.
            lock = self.pads[route["own_pad_id"]]["racer_lock"]
            if capability.get("boost_mode") != 2 or lock is None:
                return self.boost
            return self.code.get(boost_item_name(CHARACTER_ID_TO_NAME[lock]))

        self.checks = []
        for check in plan["checks"]:
            code = check["location"]
            if check.get("stats") or check["kind"] in ("itemsanity", "hit"):
                continue
            spot = code not in pins and code != goal and code not in excluded
            if check["kind"] == content_wumpa.KIND:
                spot = spot and spare_shop
                self.checks.append((code, spot, floors[code], None))
            else:
                self.checks.append((code, spot, None, [(region(route), later(route), route, rank(check, route), boost_of(route))
                                                       for route in check["routes"]]))
        self.income = [dict(own_pad_id=pad_id, mode=mode, later=later(dict(own_pad_id=pad_id, mode=mode)),
                            boost=boost_of(dict(own_pad_id=pad_id)),
                            need=content_capability.finish_boost(track, capability, content_wumpa.income_package(plan, track))
                            if capability.get("boost_mode") else 0)
                       for _entry, pad_id, mode, track in content_wumpa.income_routes(plan)]

    def _met(self, requirement, held):
        return term_met(self.req[requirement], held)

    def _pad_open(self, pad, held):
        if not self._met(pad["entrance_req"], held):
            return False
        if pad["racer_lock"] is not None:
            from .characters import CHARACTER_ID_TO_NAME
            code = self.code.get(CHARACTER_ID_TO_NAME[pad["racer_lock"]])
            if code is not None and not held.get(code, 0):
                return False
        return all(self._met(gate["requirement_id"], held) for gate in pad["mode_gates"][:1])

    def _sweep(self, held, fixed=None):
        """The open check codes, with the fixed items on them collected."""
        waiting = dict(self.pins if fixed is None else fixed)
        while True:
            opened = self._open(held)
            gained = [code for code in waiting if code in opened]
            if not gained:
                return opened
            for code in gained:
                item = waiting.pop(code)
                held[item] = held.get(item, 0) + 1

    def _open(self, held):
        region_open = {pad_id: pad["entry_id"] is not None and self._pad_open(pad, held)
                       for pad_id, pad in self.pads.items()}
        for encounter in self.encounters.values():
            region_open[encounter["id"]] = (self._met(self.pads[encounter["pad_id"]]["entrance_req"], held)
                                            and self._met(encounter["requirement_id"], held))

        def stage_met(route, opened):
            pad = self.pads[route["own_pad_id"]]
            if any(g["mode"] == route["mode"] and g["stage"] == 2 and not self._met(g["requirement_id"], held)
                   for g in pad["mode_gates"]):
                return False
            won = self.first.get(pad["id"], ())
            return not won or any(code in opened for code in won)

        def letters_held(code):
            return all(held.get(self.code.get(name), 0) for name in self.letters.get(code, ()))

        opened = set()
        waiting = []
        for code, _spot, _floor, routes in self.checks:
            if routes is None or not letters_held(code):
                continue
            usable = [(later, route) for own, later, route, need, boost in routes
                      if need <= held.get(boost, 0) and region_open[own]]
            if any(not later for later, _route in usable):
                opened.add(code)
            elif usable:
                waiting.append((code, usable))
        first = set(opened)
        opened.update(code for code, usable in waiting if any(stage_met(route, first) for _later, route in usable))
        opened -= {code for code, trophy in self.merged.items() if trophy not in opened}
        income = any(route["need"] <= held.get(route["boost"], 0) and region_open[route["own_pad_id"]]
                     and (not route["later"] or stage_met(route, first)) for route in self.income)
        key = self.code.get("Key")
        opened.update(code for code, _spot, floor, routes in self.checks
                      if routes is None and income and held.get(key, 0) >= floor)
        return opened

    def _held(self, held):
        counts = dict(self.base)
        for name in held:
            counts[self.code[name]] = counts.get(self.code[name], 0) + 1
        return counts

    def room(self, held):
        """Spots open with the sorted tuple of names `held`."""
        opened = self._sweep(self._held(held))
        return sum(spot and code in opened for code, spot, _floor, _routes in self.checks)

    def encounter_reached(self, encounter, held):
        """The garage can actually be won, including its check capability."""
        return encounter["completion_location"] in self._sweep(self._held(held))

    def key_slack(self, non_local=()):
        """Best costed opening before each fixed Key, capped by the search target.

        Earlier Keys are granted for the probe, but every other pooled item
        spends a slot before opening checks. In particular, letters, racer
        unlocks and boosts cannot contribute free capacity. This is a bounded
        layout estimate used only for redraws; the best draw still stands.
        """
        from .content_plan import ITEM_BY_CODE
        key = self.code.get("Key")
        saved_base, saved_pins = self.base, self.pins
        gates = gate_names(self.plan, ITEM_BY_CODE, ITEM_BY_CODE.get(self.boost))
        eligible = {name: count for name, count in self.pool.items() if name not in non_local}
        bundles = letter_bundles(self.plan, eligible)
        names = gates | {name for bundle in bundles for name in bundle}
        pool = {name: count for name, count in eligible.items() if name in names and name != "Key"}
        out = None
        try:
            self.pins = {code: item for code, item in saved_pins.items() if item != key}
            for encounter in self.encounters.values():
                if saved_pins.get(encounter["completion_location"]) != key:
                    continue
                self.base = dict(saved_base)
                requirement = self.pads[encounter["pad_id"]]["entrance_req"]
                self.base[key] = int(requirement.removeprefix("keys:")) if requirement != "free" else 0

                def reached(held):
                    # Winning the target garage also needs its venue's
                    # capability rule, beyond its displayed item demand.
                    return self.encounter_reached(encounter, held)

                goals = garage_demands(self.req[encounter["requirement_id"]], pool, self.base, ITEM_BY_CODE)
                held, room = search(pool, self.room, KEY_SLACK, reached, bundles=bundles, goals=goals)
                score = room if reached(held) else -1
                out = score if out is None else min(out, score)
            return out
        finally:
            self.base, self.pins = saved_base, saved_pins

    def holds(self, held, name):
        """With `held`, does the slot hold `name`, on a fixed check or in `held`?"""
        counts = self._held(held)
        self._sweep(counts)
        return counts.get(self.code[name], 0) > 0


def fit(world, plan):
    """(how the plan's best opening does, what fits), both (spots it leaves, spots to
    spare in front of a fixed Key), so they compare. With Keys fixed the opening has
    to reach the first Key, or it leaves none. Neither counts above what fits."""
    from .content_plan import ITEM_BY_CODE, LOCATION_BY_CODE
    from .sphere0_guard import BOOTSTRAP_START_CHECKS, starting_boost_item
    excluded = set(world.options.exclude_locations.value)
    excluded = {code for code, name in LOCATION_BY_CODE.items() if name in excluded}
    boost = starting_boost_item(world) if plan.get("capability", {}).get("boost_mode") else None
    reach = PlanReach(plan, world.ctr_content_items.rows, excluded, boost)
    checks = sum(check["kind"] != content_wumpa.KIND for check in plan["checks"])
    need = min(FIT_ROOM, BOOTSTRAP_START_CHECKS, checks // 4)
    gates = gate_names(plan, ITEM_BY_CODE, boost)
    non_local = world.options.non_local_items.value
    pool = {name: count for name, count in reach.pool.items() if name in gates and name not in non_local}
    bundles = letter_bundles(plan, {name: count for name, count in reach.pool.items() if name not in non_local})
    pool.update((name, reach.pool[name]) for bundle in bundles for name in bundle)
    first_key = (lambda held: reach.holds(held, "Key")) if plan.get("fixed_items", {}).get("keys") else None
    names, room = search(pool, reach.room, need, first_key, bundles=bundles)
    if first_key is None:
        return (min(room, need), KEY_SLACK), (need, KEY_SLACK)
    room = room if first_key(tuple(sorted(names))) else 0
    # Vanilla garages ask a fixed table: a redraw could not change what they ask.
    slack = None if plan["pad_requirements"]["mode"] == "vanilla" else reach.key_slack(non_local)
    return (min(room, need), KEY_SLACK if slack is None else min(slack, KEY_SLACK)), (need, KEY_SLACK)
