"""Global check families on content plans (#133 PR 4d): Itemsanity and Hit Character.

Both families belong to no track. On the legacy path their checks hang off the
`Menu` region; in a content plan each check is a shared check with one route
per race that can earn it, in physical pad order and then mode order, like the
`wumpa: global` check (#133 PR 3b). The plan's optional `global_checks` record
says which family is on (feature `global_checks_v1`); it is absent when both
are off, so such a plan keeps its earlier wire.

ITEMSANITY. The 22 use checks of itemsanity.py (`35016000` + 2 x weapon, plain
then juiced) with a route for every Trophy Race and CTR Challenge in the plan,
on retail tracks, Cortex Vortex and custom tracks alike: a weapon can be fired
in any race that rolls weapon crates. The 11 weapon items take one item ledger
row each. The rule is the legacy one (Rules.add_itemsanity_rules): the weapon
item, and for Turbo the first Progressive Boost rank when boost is on, ANDed
with any route. A plan with no such race (every normal pad a cup or an arena,
the 27-cup seed of 0.3.0-alpha3 job A3-7, ruled 2026-11-05) routes every
Itemsanity check from every cup leg instead, as Hit Character does: a cup leg
is an Adventure race that rolls weapon crates, and native mints a use in any
race. Such a leg route needs the finish of every earlier leg, bound to the cup
pad's racer lock. A plan with a Trophy Race or CTR Challenge keeps its routes
exactly. Native keys the whole runtime (use hook, crate filter, the
Turbo Grant and Tizi Helper companions) on the server holding `35016000`, so a
content-plan room needs no other wire for it.

HIT CHARACTER. The 16 checks of hit_character.py (`35025000` + engine id).
Native seats the encounter draw on every Trophy Race and CTR Challenge of a
content plan, retail, Cortex Vortex and custom tracks alike (#133 PR 5b,
ruling of 2026-10-21: no logic or check differences between custom and retail
tracks where possible), so every target, guest or default racer, is routed
from every such race. A content-plan cup (#133 PR 5b, cup roster ruling of
2026-10-21) draws its field once at cup start from its own order (the block's
`content_cups`) and keeps it for every leg and retry, custom legs included,
so each leg of a cup is a route too (mode `cup`, the leg's `leg_id`). A leg
route needs the finish of every earlier leg, as a Cup Leg Victory route does,
but not a win, by a racer the target can be drawn against. The rule is the legacy one (hit_character.py encounter
predicates): a hit method while Itemsanity models weapons; for a guest, one of
its unlock wins reachable, or its Key fallback when none of them is in the
plan; and a route whose pad is open with a selectable racer the target can be
drawn against (never the target itself, the pad's racer lock when it has
one). With bosses off the four boss guests have no boss race, so they take the
content-plan Key fallback (hit_character.CONTENT_PLAN_FALLBACK_KEYS); with
bosses on (#133 PR 6) each joins through its own boss race win like a normal
room, and a boss can also be hit in its boss race (one `boss_race` route per
encounter, after the others). With random bosses the slots swap (ruled
2026-10-30): a racer drawn as a boss, default racers too, joins through that
boss race win, and an original boss raced nowhere takes ordinary routes from
the start, with no Key term. Before PR 5b a guest was routed
from retail races only and a custom-served race kept the stock field of the
player's arcade pack.

The room carries the normal `hit_character_encounters` block (schema 3) when
Hit Character is on, with the fallback derived from the plan's checks, and,
when the plan has cups, `content_cups`: one order per cup name index.

WEAPON CRATES (#133 PR 4e). A custom track whose package states
`capabilities.weapon_crates: 0` rolls no weapon, so it is no route for either
family: nothing can be fired or hit there. A package that does not state the
count keeps the earlier routes (every real package measured has crates).
"""
from Options import OptionError

from . import characters, content_bosses, content_cups, hit_character, itemsanity, logic_terms, progressive_capability

FEATURE = "global_checks_v1"
KEYS = ("itemsanity", "hit_character")
#: The check kinds of the two families.
KINDS = ("itemsanity", "hit")
#: Modes whose race seats AI opponents and rolls weapon crates.
RACE_MODES = ("trophy", "ctr")
MODE_ORDER = ("trophy", "ctr", "relic", "cup")
OWNER = "global"


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options):
    """The plan's `global_checks` record from the seed's options; {} when both
    families are off."""
    out = {}
    if options.itemsanity.value:
        out["itemsanity"] = True
    if options.hit_character.value:
        out["hit_character"] = True
    return out


def check_settings(record):
    """Shape and values of a plan's `global_checks` record."""
    if (not isinstance(record, dict) or not record or set(record) - set(KEYS)
            or any(value is not True for value in record.values())):
        error("global_checks must be a nonempty mapping of itemsanity and hit_character, each true.")
    return record


def item_counts(record):
    """{item name: copies} the ledger pools: one of each weapon with Itemsanity."""
    if not record or not record.get("itemsanity"):
        return {}
    return {name: 1 for name in itemsanity.ITEM_NAMES}


def _route(entry_id, mode, pad_id, award, leg_id=None):
    return dict(entry_id=entry_id, mode=mode, leg_id=leg_id, encounter_id=None, own_pad_id=pad_id, award=award)


def no_crates(track, packages):
    """True for a custom track whose package states no weapon crates."""
    package = (packages or {}).get(track.get("package_id"))
    return track.get("origin") == "custom" and bool(package) and \
        package["capabilities"].get("weapon_crates", 1) == 0


def race_routes(tracks, entries, pads, packages=None):
    """[(physical pad, entry id, pad id, mode, origin)] of every Trophy Race and
    CTR Challenge in the plan, in physical pad order, then mode order. A custom
    track with no weapon crates is skipped."""
    by_track = {track["id"]: track for track in tracks if not no_crates(track, packages)}
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    out = []
    for entry in entries:
        if entry["kind"] != "track" or entry["track_id"] not in by_track or entry["id"] not in pad_of:
            continue
        origin = by_track[entry["track_id"]]["origin"]
        pad_id = pad_of[entry["id"]]
        out.extend((int(pad_id.split(":")[1]), entry["id"], pad_id, mode, origin)
                   for mode in entry["modes"] if mode in RACE_MODES)
    return sorted(out, key=lambda r: (r[0], MODE_ORDER.index(r[3])))


def cup_routes(tracks, entries, pads, packages=None):
    """[(physical pad, entry id, pad id, "cup", leg id)] of every leg of every
    cup in the plan (#133 PR 5b), in physical pad order, then leg order. A leg
    on a custom track with no weapon crates is skipped: nothing can be hit
    there."""
    by_track = {track["id"]: track for track in tracks}
    pad_of = {pad["entry_id"]: pad["id"] for pad in pads if pad["entry_id"] is not None}
    out = []
    for entry in entries:
        if entry["kind"] != content_cups.KIND or entry["id"] not in pad_of:
            continue
        pad_id = pad_of[entry["id"]]
        out.extend((int(pad_id.split(":")[1]), entry["id"], pad_id, content_cups.MODE, leg["id"])
                   for leg in entry["legs"] if not no_crates(by_track[leg["track_id"]], packages))
    return sorted(out, key=lambda r: r[0])


def hit_routes(routes, legs):
    """Every route a Hit target can be drawn on: every Trophy Race and CTR
    Challenge, and every cup leg, in physical pad order, then mode order, then
    leg order (a pad holds one entry). The same for every target."""
    out = [(r[0], r[1], r[2], r[3], None) for r in routes] + list(legs)
    return sorted(out, key=lambda r: (r[0], MODE_ORDER.index(r[3])))


def checks(record, tracks, entries, pads, packages=None, boss_hits=None):
    """Every global check of the record, Itemsanity first (frozen class order),
    then Hit Character (engine id order). Refuses a plan in which a check has no
    route. `tracks` holds every plan track, cup-only leg tracks included.
    `boss_hits` maps an opponent engine id to its boss race routes (#133 PR 6,
    content_bosses.hit_routes): a boss can be hit in its own boss race, so
    its Hit check takes those routes after the others."""
    if not record:
        return []
    routes = race_routes(tracks, entries, pads, packages)
    out = []
    if record.get("itemsanity"):
        # Every Trophy Race and CTR Challenge; with none, every cup leg (A3-7).
        use = ([(r[0], r[1], r[2], r[3], None) for r in routes] if routes
               else cup_routes(tracks, entries, pads, packages))
        if not use:
            error("itemsanity needs at least one Trophy Race, CTR Challenge or cup in the plan; select the "
                  "trophy or ctr mode or a cup, or turn itemsanity off. No content was changed.")
        for name, code, _region in itemsanity.ITEMSANITY_CLASS.all_locations():
            award = "use_juiced" if name.endswith("(Juiced)") else "use"
            out.append(dict(location=code, owner=OWNER, kind="itemsanity", display_name=name,
                            routes=[_route(e, m, p, award, leg) for _phys, e, p, m, leg in use]))
    if record.get("hit_character"):
        own = hit_routes(routes, cup_routes(tracks, entries, pads, packages))
        if not own:
            error("hit_character needs at least one Trophy Race, CTR Challenge or cup in the plan; select the "
                  "trophy or ctr mode or a cup, or turn hit_character off. No content was changed.")
        for cid in sorted(characters.CHARACTER_ID_TO_NAME):
            name = hit_character.HIT_CHARACTER_CLASS.location_name(cid)
            out.append(dict(location=hit_character.HIT_CHARACTER_CODE_BASE + cid, owner=OWNER, kind="hit",
                            display_name=name,
                            routes=[_route(e, m, p, "hit", leg) for _phys, e, p, m, leg in own]
                            + list((boss_hits or {}).get(cid, ()))))
    return out


def check_count(record, tracks, packages=None, cup_legs=()):
    """How many global checks a plan with these tracks holds (before the pads
    are assigned), refusing a family with no route as `checks` does.
    `cup_legs` is the track record of every leg of the plan's cups."""
    if not record:
        return 0
    racing = [t for t in tracks if "arena_id" not in t and set(t.get("modes", ())) & set(RACE_MODES)
              and not no_crates(t, packages)]
    count = 0
    if record.get("itemsanity"):
        if not racing and all(no_crates(t, packages) for t in cup_legs):
            error("itemsanity needs at least one Trophy Race, CTR Challenge or cup in the plan; select the "
                  "trophy or ctr mode or a cup, or turn itemsanity off. No content was changed.")
        count += len(itemsanity.ITEMSANITY_CLASS.all_locations())
    if record.get("hit_character"):
        if not racing and all(no_crates(t, packages) for t in cup_legs):
            error("hit_character needs at least one Trophy Race, CTR Challenge or cup in the plan; select the "
                  "trophy or ctr mode or a cup, or turn hit_character off. No content was changed.")
        count += len(characters.CHARACTER_ID_TO_NAME)
    return count


def plan_codes(plan):
    return {check["location"] for check in plan["checks"]}


def fallback(plan):
    """{guest engine id: Key count} for the guests with no unlock win in the
    plan. The unlock wins follow the racers the plan's boss races seat (job
    J11, decision 9). With random bosses an original boss raced nowhere,
    N. Oxide with his races disabled included, races from the start with no
    Keys (`content_bosses.seats`)."""
    triggers = hit_character.unlock_triggers_for(content_bosses.seats(plan))
    return hit_character.fallback_guests(plan_codes(plan), hit_character.CONTENT_PLAN_FALLBACK_KEYS, triggers)


def cup_indices(plan):
    """The name indices of the plan's pool cups (#133 PR 5b), the keys of the
    encounter block's `content_cups`. A Gem Cup draws from the block's own
    `cups` order for its LevelID, which every block carries."""
    return sorted(int(e["id"].removeprefix("entry/cup:")) for e in plan["entries"]
                  if e["kind"] == content_cups.KIND and content_cups.gem_colour(e["id"]) is None)


def encounter_block(world, plan):
    """Draw the roster seed once and build the `hit_character_encounters` block
    with the plan's fallback and one order per cup. The block's only draw,
    taken only with Hit Character on; the cup orders derive from the seed."""
    seed = int(world.random.getrandbits(32))
    bosses, seats = content_bosses.identity(plan), content_bosses.seats(plan)
    block = hit_character.build_encounters(seed, fallback(plan), cup_indices(plan), bosses, seats)
    hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS, cup_indices(plan), bosses,
                                  seats)
    world.ctr_hit_character_seed = seed
    world.ctr_hit_character_encounters = block
    world.ctr_hit_character_fallback = fallback(plan)
    return block


def check_encounter_block(plan, slot_data):
    """A content-plan room's Hit Character block: present exactly when the plan
    has Hit Character on, valid, and with exactly the plan's fallback."""
    record = plan.get("global_checks", {})
    co = slot_data.get("ctr_options", {})
    if co.get("hit_character") is not bool(record.get("hit_character")):
        error("ctr_options.hit_character disagrees with the plan's global_checks record")
    if not record.get("hit_character"):
        if "hit_character_encounters" in slot_data:
            error("hit_character_encounters without Hit Character in the plan")
        return
    block = slot_data.get("hit_character_encounters")
    block = hit_character._tuples_to_lists(block) if hit_character._has_tuple(block) else block
    hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS, cup_indices(plan),
                                  content_bosses.identity(plan), content_bosses.seats(plan))
    got = {int(g): e["fallback_keys"] for g, e in block["unlock_triggers"].items() if "fallback_keys" in e}
    if got != fallback(plan):
        error("hit_character_encounters fallback disagrees with the plan's unlock wins")


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------

def _appearance(target, lock):
    """Player racers the draw can seat `target` against on one route: any racer
    but the target, on every race (#133 PR 5b). A racer-locked pad narrows that
    to its lock, and a pad locked to the target proves nothing."""
    target_name = characters.CHARACTER_ID_TO_NAME[target]
    players = [n for n in progressive_capability.ROSTER if n != target_name]
    if lock is not None:
        return (lock,) if lock in players else ()
    return tuple(players)


def install(world, check, location, route_tests):
    """Set the access rule of one global check. `route_tests` is
    [(entry region name, stage-2 Term or None, route)] for the check's routes."""
    player = world.player
    kind = check["kind"]
    route_terms = tuple(route_tests)
    route_tests = tuple((entry, None if term is None else term.compile(), route)
                        for entry, term, route in route_terms)
    hints = bool(world.options.pad_approach_hints.value)
    opens = tuple((entry, test) for entry, test, _route in route_tests)

    def alternatives(terms):
        terms = tuple(terms)
        return logic_terms.FALSE if not terms else terms[0] if len(terms) == 1 else logic_terms.Or(*terms)

    def route_term(entry, stage, need_racer=(0, None)):
        region = logic_terms.ReachRegion(world, entry)
        term = region if stage is None else logic_terms.And(region, stage)
        need, racer = need_racer
        return term if not need else logic_terms.And(term, logic_terms.Cap(world, need, racer))

    def any_route(state):
        return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                   for entry, test in opens)

    if kind == "itemsanity":
        weapon = check["display_name"].removeprefix("Itemsanity: ").removesuffix(" (Juiced)")
        boost = weapon == "Turbo" and bool(world.options.progressive_boost.value)
        if any(route["mode"] == content_cups.MODE for _entry, _test, route in route_tests):
            # Cup leg routes (A3-7): the finish of every earlier leg, bound
            # to the cup pad's racer lock, as a Cup Leg Victory route.
            plan = world.ctr_content_plan
            pad_by_id = {pad["id"]: pad for pad in plan["pads"]}
            entry_by_id = {entry["id"]: entry for entry in plan["entries"]}
            tracks = {track["id"]: track for track in plan["tracks"]}
            packages = {package["id"]: package for package in plan["packages"]}
            capability = plan.get("capability", {})

            def leg_need(route):
                if route["mode"] != content_cups.MODE:
                    return 0, None
                lock = pad_by_id[route["own_pad_id"]]["racer_lock"]
                return (content_cups.prefix_boost(entry_by_id[route["entry_id"]], route["leg_id"], tracks, capability,
                                                  packages),
                        characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None)
            needs = tuple(leg_need(route) for _entry, _test, route in route_tests)

            def any_route(state):
                return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                           and (not need or progressive_capability.gate_satisfied(world, state, player, boost_min=need,
                                                                                 required_character=racer))
                           for (entry, test), (need, racer) in zip(opens, needs))

            route_terms = tuple((entry, stage, route, need) for (entry, stage, route), need in zip(route_terms, needs))
        else:
            route_terms = tuple((entry, stage, route, (0, None)) for entry, stage, route in route_terms)

        def rule(state, weapon=weapon, boost=boost):
            return (state.has(weapon, player)
                    and (not boost or progressive_capability.gate_satisfied(world, state, player, boost_min=1))
                    and any_route(state))
        location.access_rule = rule
        if hints:
            terms = [logic_terms.Has(weapon, 1, player),
                     alternatives(route_term(entry, stage, need) for entry, stage, _route, need in route_terms)]
            if boost:
                terms.append(logic_terms.Cap(world, 1, None))
            logic_terms.set_term(location, logic_terms.SerializedRule(rule, logic_terms.all_of(*terms)))
        return
    target = check["location"] - hit_character.HIT_CHARACTER_CODE_BASE
    plan = world.ctr_content_plan
    pads = {pad["id"]: pad for pad in plan["pads"]}
    entries = {entry["id"]: entry for entry in plan["entries"]}
    tracks = {track["id"]: track for track in plan["tracks"]}
    packages = {package["id"]: package for package in plan["packages"]}
    capability = plan.get("capability", {})
    legs = []
    leg_terms = []
    # Boss races (#133 PR 6): the boss can be hit in its own boss race once
    # the player can enter that race, whether or not it joined the draw
    # (hit_character._boss_predicate on the legacy path). Entering is the
    # encounter's region (garage gate and the race's own requirement); the win
    # check's boost rank is not needed to hit the racer (Rulebook: the player
    # does not need to beat the boss first).
    boss = tuple(entry for entry, _test, route in route_tests if route["mode"] in content_bosses.MODES)
    for (entry, test, route), (_entry, stage, _route) in zip(route_tests, route_terms):
        if route["mode"] in content_bosses.MODES:
            continue
        lock = pads[route["own_pad_id"]]["racer_lock"]
        lock = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        players = _appearance(target, lock)
        # A cup leg (#133 PR 5b) needs the finish of every earlier leg, and
        # the racer that finishes them is the one the field is drawn against,
        # so the boost term binds to the same appearance racer.
        need = (content_cups.prefix_boost(entries[route["entry_id"]], route["leg_id"], tracks, capability, packages)
                if route["mode"] == content_cups.MODE else 0)
        if players:
            legs.append((entry, test, players, need))
            if hints:
                racers = []
                for name in players:
                    selected = (logic_terms.TRUE if not characters.unlocks_enabled(world)
                                or name == world.ctr_starting_character else
                                logic_terms.Has(characters.unlock_item_name(name), 1, player))
                    racers.append(selected if not need else logic_terms.And(selected, logic_terms.Cap(world, need, name)))
                leg_terms.append(logic_terms.And(route_term(entry, stage), alternatives(racers)))
    legs = tuple(legs)
    fallback_keys = world.ctr_hit_character_fallback.get(target)
    triggers = ()
    if fallback_keys is None:
        table = world.ctr_hit_character_encounters["bosses"]
        # The roster swap: a default racer drawn as a boss waits for that boss
        # race like a guest does. An original boss raced nowhere has no term,
        # N. Oxide with his races disabled too: his codes are not in the plan.
        wins = (hit_character.boss_codes(table, target) if target in hit_character.DEFAULT_RACER_IDS
                else hit_character.unlock_triggers_for(table)[target][0])
        if wins:
            names = hit_character._location_name_by_code(world)
            present = {c["location"] for c in plan["checks"]}
            triggers = tuple(world.multiworld.get_location(names[code], player) for code in wins if code in present)
    weapons = bool(plan.get("global_checks", {}).get("itemsanity"))
    unlocks = characters.unlocks_enabled(world)

    def selectable(state, name):
        return (not unlocks or name == world.ctr_starting_character
                or state.has(characters.unlock_item_name(name), player))

    def rule(state):
        if weapons and not state.has_any(hit_character.HIT_METHOD_ITEMS, player):
            return False
        if boss and any(state.can_reach(region, "Region", player) for region in boss):
            return True
        if fallback_keys is not None:
            if not state.has(hit_character.KEY_ITEM, player, fallback_keys):
                return False
        elif triggers and not any(t.can_reach(state) for t in triggers):
            return False
        return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                   and any(selectable(state, name)
                           and (not need or progressive_capability.gate_satisfied(world, state, player, boost_min=need,
                                                                                 required_character=name))
                           for name in players)
                   for entry, test, players, need in legs)
    location.access_rule = rule
    if hints:
        guest = (logic_terms.Has(hit_character.KEY_ITEM, fallback_keys, player) if fallback_keys is not None
                 else alternatives(logic_terms.Ref(trigger, player) for trigger in triggers) if triggers
                 else logic_terms.TRUE)
        ordinary = logic_terms.And(guest, alternatives(leg_terms))
        paths = [ordinary] + [logic_terms.ReachRegion(world, region) for region in boss]
        term = alternatives(paths)
        if weapons:
            term = logic_terms.And(logic_terms.HasAny(hit_character.HIT_METHOD_ITEMS, player), term)
        logic_terms.set_term(location, logic_terms.SerializedRule(rule, term))


def tiger_temple_door(world):
    """Tiger Temple's R letter sits behind the stone shortcut door. With
    Itemsanity on, picking it up needs one of the door-opener weapons
    (Rules.add_lettersanity_rules, item_boxes.TIGER_TEMPLE_DOOR_OPENERS): on its
    Letter R check, and on its CTR Token Challenge unless Lettersanity 2 left the
    R undrawn. Item Box 5 sits behind the same door (item_boxes.BOX_RULES,
    #133 PR 4e) and takes the same term. Applies to the retail Tiger Temple
    only."""
    plan = world.ctr_content_plan
    if not plan.get("global_checks", {}).get("itemsanity"):
        return
    from .item_boxes import TIGER_TEMPLE_DOOR_OPENERS
    player = world.player
    codes = {check["location"] for check in plan["checks"]}
    from .Locations import CTR_LOCATION_IDS
    token, letter_r = "Tiger Temple: CTR Token Challenge", "Tiger Temple: Letter R"
    mode = plan.get("track_checks", {}).get("lettersanity", 0)
    names = []
    if CTR_LOCATION_IDS[letter_r] in codes:
        names.append(letter_r)
    if CTR_LOCATION_IDS[token] in codes and (mode != 2 or CTR_LOCATION_IDS[letter_r] in codes):
        names.append(token)
    door_box = "Tiger Temple: Item Box 5"
    if CTR_LOCATION_IDS[door_box] in codes:
        names.append(door_box)
    for name in names:
        location = world.multiworld.get_location(name, player)
        logic_terms.and_term(location, logic_terms.HasAny(TIGER_TEMPLE_DOOR_OPENERS, player))
