"""Items fixed to their own check on a content plan (one generator row 4).

The plan's optional `fixed_items` record names what the seed fixes:

  * `keys`: `shuffle_keys: off` on a plan with boss garages. Each base Key stays
    on its boss completion check. Without garages there is no boss check, so the
    Keys shuffle.
  * `gems`: `shuffle_gems: off` with all five Gem Cups in the seed. Each base Gem
    stays on `<Colour> Gem Cup: Gem`. With any Gem Cup missing all five shuffle,
    with no message, also on a Gems goal (ruled 2026-10-30).
  * `oxide_1_filler`: `oxide_1_optional: filler` with `oxide_goal: 101_percent`.
    N. Oxide's Challenge holds a Wumpa Fruit, as on the original generator. That
    copy is no ledger row and no filler slot, so it never enters the trap draw,
    and the goal check keeps its own filler slot.

The record is present only with something in it, so other plans keep their wire.
Which check holds what is not on the wire: `placements` reads it from the record
and the ledger, on both sides. Extras stay shuffled. A from-pool start takes an
extra first, then a pinned copy: a colour with no copy left leaves its Gem Cup a
free check, and with fewer than four Keys left the last garages are free checks.

With vanilla requirements and Gems fixed, the physical five-Gem pad keeps that
gate whatever sits on it. A Gem Cup there could need its own Gem, so the placement
draws again (seat_content), and the Relic Race there holds no tier check: 17
counts eligible checks, and the item counts stay exact (relic guard, dispatcher
decision of 2026-10-30, `guarded_track`). A Turbo Track on another pad is an
ordinary track.

With vanilla requirements a fixed first Key sits behind 4 Trophies, and the later
races of every pad behind that Key, so few checks are open before it. The
placement and the mode order draw again until FIRST_KEY_CHECKS are.

Random garages draw their kind before the fill, so a fixed Key or Gem can sit
behind a garage that needs it: `draw_garages` draws again, and what stays stuck
asks Trophies instead (Rulebook: a requirement that cannot be proven is replaced).
Pads need nothing of the kind: the simulated playthrough holds the pins as its
stand-ins, so a pad only asks for what the simulated player holds there.
"""
from Options import OptionError

from . import content_bosses, content_cups, content_item_pool, content_requirements

FEATURE = "fixed_items_v1"
KEYS = ("keys", "gems", "oxide_1_filler")
#: The check of Gem Cup colour 0 (Red) to 4 (Purple).
GEM_CHECK = 35011200
GEM_NAMES = tuple(f"{colour.title()} Gem" for colour in content_item_pool.COLOURS)
FILLER = "Wumpa Fruit"
#: The physical pad that asks for all five Gems with vanilla requirements.
GEM_PAD = next(physical for physical, kind in content_requirements.PHYSICAL_KIND.items()
               if kind == "track" and content_requirements.vanilla_rule(physical) == ("AnyGem", 5))
GARAGE_REDRAWS = content_requirements.PLACEMENT_REDRAWS
#: With vanilla requirements a fixed first Key sits behind 4 Trophies, and every
#: multi-race pad's later races need that Key. Fill failures sit on seeds with
#: fewer checks than this open before it (measured on row 4's CI failures), so the
#: placement and the mode order draw again below it.
FIRST_KEY_CHECKS = 9


def error(message):
    raise OptionError("CTR content plan: " + message)


def settings(options, bosses, gem_cups):
    """The plan's `fixed_items` record; {} when nothing is fixed. `gem_cups` lists
    the Gem Cup colours in the seed."""
    out = {}
    if not options.shuffle_keys.value and bosses is not None:
        out["keys"] = True
    if not options.shuffle_gems.value and set(gem_cups) == set(range(len(GEM_NAMES))):
        out["gems"] = True
    if bosses is not None and bosses["oxide_goal"] == content_bosses.GOAL_FINAL and int(options.oxide_1_optional.value) == 2:
        out["oxide_1_filler"] = True
    return out


def check_settings(plan):
    """Shape of a plan's `fixed_items` record, and that what it fixes exists."""
    record = plan["fixed_items"]
    if not isinstance(record, dict) or not record or set(record) - set(KEYS) or any(v is not True for v in record.values()):
        error("fixed_items must be a nonempty mapping of keys, gems and oxide_1_filler, each true when present.")
    bosses = plan.get("bosses")
    if "keys" in record and bosses is None:
        error("fixed_items.keys needs boss garages.")
    if "gems" in record and {e["id"] for e in plan["entries"] if e["kind"] == content_cups.KIND
                             and content_cups.gem_colour(e["id"]) is not None} \
            != {f"entry/gem_cup:{colour}" for colour in range(len(GEM_NAMES))}:
        error("fixed_items.gems needs all five Gem Cups.")
    if "oxide_1_filler" in record and (bosses is None or bosses["oxide_goal"] != content_bosses.GOAL_FINAL
                                       or not bosses["oxide_1_optional"]):
        error("fixed_items.oxide_1_filler belongs to oxide_goal 101_percent with oxide_1_optional.")
    return record


def placements(record, base, copies):
    """{location code: item name} of a `fixed_items` record. `base` holds the base
    copies of the Keys and Gems, `copies` what the pool has of them after from-pool
    starts."""
    out = {}
    if record.get("keys"):
        out.update(dict.fromkeys(content_bosses.BOSS_CODES[:max(0, min(base["Key"], copies["Key"]))], "Key"))
    if record.get("gems"):
        out.update({GEM_CHECK + colour: name for colour, name in enumerate(GEM_NAMES)
                    if base[name] and copies[name] > 0})
    if record.get("oxide_1_filler"):
        out[content_bosses.OXIDE_FIRST] = FILLER
    return out


def plan_placements(plan):
    """`placements` read from a finished plan's record and ledger."""
    names = {content_item_pool.ITEMS[name]: name for name in ("Key",) + GEM_NAMES}
    rows = [row for row in plan["items"]["rows"] if row["item"] in names]
    return placements(plan.get("fixed_items", {}), {names[r["item"]]: r["base"] for r in rows},
                      {names[r["item"]]: r["base"] + r["extra"] - r["start_from_pool"] for r in rows})


def locked_copies(pins):
    """{item name: copies} the pins take from the ledger. The Wumpa Fruit is no
    ledger row."""
    out = {}
    for name in pins.values():
        if name != FILLER:
            out[name] = out.get(name, 0) + 1
    return out


def guarded_track(mode, record, pads, entries):
    """The track id whose Relic Race stands on the physical five-Gem pad under
    the relic guard, or None. `mode` is the pad requirement mode."""
    if mode != "vanilla" or not record.get("gems"):
        return None
    pad = next((p for p in pads if p["id"] == f"pad:{GEM_PAD}"), None)
    entry = next((e for e in entries if pad is not None and e["id"] == pad["entry_id"]), None)
    return entry["track_id"] if entry is not None and entry["kind"] == "track" and "relic" in entry["modes"] else None


def stuck_garages(requirements, rows, pins, pads):
    """Garages that stay shut with every free copy held, when a pinned Key or Gem
    only comes from its check. A pad is taken as open once its hub Keys are held:
    a pad's requirement is drawn after the garages, around them."""
    held = {row.item: row.remaining + row.start_from_pool + row.start_additional for row in rows}
    key = content_item_pool.ITEMS["Key"]
    gem_keys = {}
    for pad in pads:
        colour = content_cups.gem_colour(pad["entry_id"]) if pad["entry_id"] else None
        if colour is not None:
            gem_keys[GEM_CHECK + colour] = int(pad["entrance_req"].removeprefix("keys:")) if pad["entrance_req"] != "free" else 0
    waiting = {code: name for code, name in pins.items() if name != FILLER}

    def met(predicate):
        if predicate["op"] == "count":
            return held.get(predicate["item"], 0) >= predicate["count"]
        return sum(held.get(code, 0) for code in predicate["items"]) >= predicate["count"]

    while True:
        shut = {g for g, predicate in requirements.items()
                if content_bosses.GARAGES[g][2] > held.get(key, 0) or not met(predicate)}
        gained = [code for code in waiting if (gem_keys[code] <= held.get(key, 0) if code in gem_keys
                                               else content_bosses.BOSS_CODES.index(code) not in shut)]
        if not gained:
            return sorted(shut)
        for code in gained:
            item = content_item_pool.ITEMS[waiting.pop(code)]
            held[item] = held.get(item, 0) + 1


def draw_garages(world, record, rows, vanilla, pins, pads):
    """{garage: predicate} of the four ordinary garages. Without a pin, or with
    the Trophy table of vanilla requirements, this is the plain draw. Otherwise a
    roll that leaves a garage stuck behind its own pins is drawn again, at most
    GARAGE_REDRAWS times. A garage still stuck asks for the first kind no pin holds,
    Trophies when the seed has them, and a pool with no such kind is refused."""
    out = content_bosses.draw_requirements(world, record, rows, vanilla)
    if vanilla or not locked_copies(pins):
        return out
    for _ in range(GARAGE_REDRAWS):
        if not stuck_garages(out, rows, pins, pads):
            return out
        out = content_bosses.draw_requirements(world, record, rows, vanilla)
    by_name = {row.name: row for row in rows}
    pinned = set(locked_copies(pins))
    for g in stuck_garages(out, rows, pins, pads):
        kinds = [o for o in content_bosses.garage_options(by_name, g, record["requirement_level"]) if not pinned & set(o[1])]
        if not kinds:
            error("a boss garage can only ask for Keys or Gems that sit behind the garages themselves. Add other "
                  "items to item_pool or shuffle the Keys or Gems. No content was changed.")
        _label, names, _weight, low, high = kinds[0]
        out[g] = content_bosses._predicate(by_name, names, world.random.randint(low, high))
    return out


def place(world, pins, names):
    """Lock the pins on their checks. Returns the placed copies: they are no
    created pool items (content_item_pool)."""
    items = []
    for code, name in sorted(pins.items()):
        item = world.create_item(name)
        world.get_location(names[code]).place_locked_item(item)
        items.append(item)
    return items


def restore_options(world, plan):
    """Universal Tracker: the options follow the record, for code that reads them."""
    record = plan.get("fixed_items", {})
    world.options.shuffle_keys.value = int("keys" not in record)
    world.options.shuffle_gems.value = int("gems" not in record)
    if "oxide_1_filler" in record:
        world.options.oxide_1_optional.value = 2
