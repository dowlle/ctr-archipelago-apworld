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
with any route. Native keys the whole runtime (use hook, crate filter, the
Turbo Grant and Tizi Helper companions) on the server holding `35016000`, so a
content-plan room needs no other wire for it.

HIT CHARACTER. The 16 checks of hit_character.py (`35025000` + engine id).
Native seats the encounter draw only on retail track races (levels 0..17,
Trophy Race and CTR Challenge); a custom-served race, which a content-plan
custom track is, keeps its own permutation of the seven stock opponents of the
player's arcade pack. So a guest (engine id 8..15) is routed from the retail
races only, and a default racer (0..7) from every Trophy Race and CTR
Challenge. On a custom track the stock pack is the seven other defaults for a
default player and defaults 0..6 for a guest player, so Pura (7) appears there
only under a default player. The rule is the legacy one (hit_character.py
encounter predicates): a hit method while Itemsanity models weapons; for a
guest, one of its unlock wins reachable, or its Key fallback when none of them
is in the plan; and a route whose pad is open with a selectable racer the
target can be drawn against (never the target itself, the pad's racer lock
when it has one). Content plans have no boss encounters yet (#133 PR 6), so
the four boss guests always take the content-plan Key fallback
(hit_character.CONTENT_PLAN_FALLBACK_KEYS).

The room carries the normal `hit_character_encounters` block (schema 3) when
Hit Character is on, with the fallback derived from the plan's checks.
"""
from Options import OptionError

from . import characters, hit_character, itemsanity, progressive_capability

FEATURE = "global_checks_v1"
KEYS = ("itemsanity", "hit_character")
#: Modes whose race seats AI opponents and rolls weapon crates.
RACE_MODES = ("trophy", "ctr")
MODE_ORDER = ("trophy", "ctr", "relic")
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


def _route(entry_id, mode, pad_id, award):
    return dict(entry_id=entry_id, mode=mode, leg_id=None, encounter_id=None, own_pad_id=pad_id, award=award)


def race_routes(tracks, entries, pads):
    """[(physical pad, entry id, pad id, mode, origin)] of every Trophy Race and
    CTR Challenge in the plan, in physical pad order, then mode order."""
    by_track = {track["id"]: track for track in tracks}
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


def hit_routes(routes, target):
    """The race routes a Hit target can be drawn on: retail races for every
    target, and custom and Cortex Vortex races for a default racer (0..7)."""
    return [r for r in routes if r[4] == "retail" or target in hit_character.DEFAULT_RACER_IDS]


def checks(record, tracks, entries, pads):
    """Every global check of the record, Itemsanity first (frozen class order),
    then Hit Character (engine id order). Refuses a plan in which a check has no
    route."""
    if not record:
        return []
    routes = race_routes(tracks, entries, pads)
    out = []
    if record.get("itemsanity"):
        if not routes:
            error("itemsanity needs at least one Trophy Race or CTR Challenge in the plan; select the "
                  "trophy or ctr mode, or turn itemsanity off. No content was changed.")
        for name, code, _region in itemsanity.ITEMSANITY_CLASS.all_locations():
            award = "use_juiced" if name.endswith("(Juiced)") else "use"
            out.append(dict(location=code, owner=OWNER, kind="itemsanity", display_name=name,
                            routes=[_route(e, m, p, award) for _phys, e, p, m, _o in routes]))
    if record.get("hit_character"):
        for cid in sorted(characters.CHARACTER_ID_TO_NAME):
            own = hit_routes(routes, cid)
            name = hit_character.HIT_CHARACTER_CLASS.location_name(cid)
            if not own:
                error(f"hit_character: {name} has no race to be hit in. Guests are drawn only in retail "
                      "Trophy Races and CTR Challenges; select a retail track with the trophy or ctr mode, "
                      "or turn hit_character off. No content was changed.")
            out.append(dict(location=hit_character.HIT_CHARACTER_CODE_BASE + cid, owner=OWNER, kind="hit",
                            display_name=name,
                            routes=[_route(e, m, p, "hit") for _phys, e, p, m, _o in own]))
    return out


def check_count(record, tracks):
    """How many global checks a plan with these tracks holds (before the pads
    are assigned), refusing a family with no route as `checks` does."""
    if not record:
        return 0
    racing = [t for t in tracks if "arena_id" not in t and set(t.get("modes", ())) & set(RACE_MODES)]
    count = 0
    if record.get("itemsanity"):
        if not racing:
            error("itemsanity needs at least one Trophy Race or CTR Challenge in the plan; select the "
                  "trophy or ctr mode, or turn itemsanity off. No content was changed.")
        count += len(itemsanity.ITEMSANITY_CLASS.all_locations())
    if record.get("hit_character"):
        if not any(t["origin"] == "retail" for t in racing):
            error("hit_character: guest racers are drawn only in retail Trophy Races and CTR Challenges; "
                  "select a retail track with the trophy or ctr mode, or turn hit_character off. "
                  "No content was changed.")
        count += len(characters.CHARACTER_ID_TO_NAME)
    return count


def plan_codes(plan):
    return {check["location"] for check in plan["checks"]}


def fallback(plan):
    """{guest engine id: Key count} for the guests with no unlock win in the plan."""
    return hit_character.fallback_guests(plan_codes(plan), hit_character.CONTENT_PLAN_FALLBACK_KEYS)


def encounter_block(world, plan):
    """Draw the roster seed once and build the `hit_character_encounters` block
    with the plan's fallback. The block's only draw, taken only with Hit
    Character on."""
    seed = int(world.random.getrandbits(32))
    block = hit_character.build_encounters(seed, fallback(plan))
    hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS)
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
    hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS)
    got = {int(g): e["fallback_keys"] for g, e in block["unlock_triggers"].items() if "fallback_keys" in e}
    if got != fallback(plan):
        error("hit_character_encounters fallback disagrees with the plan's unlock wins")


# ---------------------------------------------------------------------------
# Logic
# ---------------------------------------------------------------------------

def _appearance(target, origin, lock):
    """Player racers the draw can seat `target` against on one route: any racer
    but the target on a retail race; on a custom-served race the racers whose
    stock pack holds the target. A racer-locked pad narrows that to its lock."""
    target_name = characters.CHARACTER_ID_TO_NAME[target]
    if origin == "retail":
        players = [n for n in progressive_capability.ROSTER if n != target_name]
    else:
        players = [n for n in progressive_capability.ROSTER if n != target_name
                   and target in hit_character.stock(characters.ROSTER_CHARACTER_ID[n])]
    if lock is not None:
        return (lock,) if lock in players else ()
    return tuple(players)


def install(world, check, location, route_tests):
    """Set the access rule of one global check. `route_tests` is
    [(entry region name, stage-2 test or None, route)] for the check's routes."""
    player = world.player
    kind = check["kind"]
    opens = tuple((entry, test) for entry, test, _route in route_tests)

    def any_route(state):
        return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                   for entry, test in opens)

    if kind == "itemsanity":
        weapon = check["display_name"].removeprefix("Itemsanity: ").removesuffix(" (Juiced)")
        boost = weapon == "Turbo" and bool(world.options.progressive_boost.value)

        def rule(state, weapon=weapon, boost=boost):
            return (state.has(weapon, player)
                    and (not boost or progressive_capability.gate_satisfied(world, state, player, boost_min=1))
                    and any_route(state))
        location.access_rule = rule
        return
    target = check["location"] - hit_character.HIT_CHARACTER_CODE_BASE
    plan = world.ctr_content_plan
    pads = {pad["id"]: pad for pad in plan["pads"]}
    origin_of = {entry["id"]: _origin(plan, entry) for entry in plan["entries"]}
    legs = []
    for entry, test, route in route_tests:
        lock = pads[route["own_pad_id"]]["racer_lock"]
        lock = characters.CHARACTER_ID_TO_NAME[lock] if lock is not None else None
        players = _appearance(target, origin_of[route["entry_id"]], lock)
        if players:
            legs.append((entry, test, players))
    legs = tuple(legs)
    fallback_keys = world.ctr_hit_character_fallback.get(target)
    triggers = ()
    if target not in hit_character.DEFAULT_RACER_IDS and fallback_keys is None:
        names = hit_character._location_name_by_code(world)
        present = {c["location"] for c in plan["checks"]}
        triggers = tuple(world.multiworld.get_location(names[code], player)
                         for code in hit_character.UNLOCK_TRIGGERS[target][0] if code in present)
    weapons = bool(plan.get("global_checks", {}).get("itemsanity"))
    unlocks = characters.unlocks_enabled(world)

    def selectable(state, name):
        return (not unlocks or name == world.ctr_starting_character
                or state.has(characters.unlock_item_name(name), player))

    def rule(state):
        if weapons and not state.has_any(hit_character.HIT_METHOD_ITEMS, player):
            return False
        if fallback_keys is not None:
            if not state.has(hit_character.KEY_ITEM, player, fallback_keys):
                return False
        elif triggers and not any(t.can_reach(state) for t in triggers):
            return False
        return any(state.can_reach(entry, "Region", player) and (test is None or test(state))
                   and any(selectable(state, name) for name in players)
                   for entry, test, players in legs)
    location.access_rule = rule


def _origin(plan, entry):
    tracks = {track["id"]: track for track in plan["tracks"]}
    track = tracks.get(entry.get("track_id"))
    return track["origin"] if track else "crystal"


def tiger_temple_door(world):
    """Tiger Temple's R letter sits behind the stone shortcut door. With
    Itemsanity on, picking it up needs one of the door-opener weapons
    (Rules.add_lettersanity_rules, item_boxes.TIGER_TEMPLE_DOOR_OPENERS): on its
    Letter R check, and on its CTR Token Challenge unless Lettersanity 2 left the
    R undrawn. Applies to the retail Tiger Temple only."""
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
    for name in names:
        location = world.multiworld.get_location(name, player)
        previous = location.access_rule
        location.access_rule = (lambda state, previous=previous:
                                previous(state) and state.has_any(TIGER_TEMPLE_DOOR_OPENERS, player))
