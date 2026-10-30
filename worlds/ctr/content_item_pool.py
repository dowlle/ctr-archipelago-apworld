"""Exact item supply for the content-plan generator.

Content determines capacity only. It never chooses, trims or precollects the
selected items. The immutable ledger is shared by generation and wire restore.
From-pool starts are granted by Main.py; the caller consumes its later depletion
request after materializing this post-start ledger, so subtraction happens once.
"""
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from Options import OptionError

from .Items import load_item_table
from .item_creation import SURFACE_ITEM_NAMES

COLOURS = ("red", "green", "blue", "yellow", "purple")
TIERS = ("sapphire", "gold", "platinum")
FAMILIES = ("trophies", "relics", "tokens", "gems", "keys")
ITEMS = {item["name"]: item["code"] for item in load_item_table()}
COUNTED_NAMES = ("Trophy", *(f"{x.title()} Relic" for x in TIERS),
                 *(f"{x.title()} CTR Token" for x in COLOURS),
                 *(f"{x.title()} Gem" for x in COLOURS), "Key")
#: The base counts of the three relic tiers. Platinum is 0 so that no needed
#: item sits behind the hardest times (ruled 2026-10-29, one generator).
RELIC_DEFAULTS = {"sapphire": 18, "gold": 18, "platinum": 0}
#: The five surface items, in code order. A plan creates them together and
#: drops them together (`resolve`).
SURFACE_NAMES = tuple(sorted(SURFACE_ITEM_NAMES, key=ITEMS.__getitem__))
MAX_COUNT = 2147483647


def fail(message):
    raise OptionError("CTR item_pool: " + message)


def exact_count(value, path):
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        fail(f"{path} must be an exact nonnegative integer, at most {MAX_COUNT}.")
    return value


def fields(value, allowed, path):
    if not isinstance(value, dict):
        fail(f"{path} must be a mapping.")
    unknown = set(value) - set(allowed)
    if unknown:
        fail(f"unknown field in {path}: {sorted(unknown, key=str)!r}.")
    return value


def normalize(raw):
    """Return independent base/extra maps; defaults retain retail quantities."""
    fields(raw, ("base", "extra"), "item_pool")
    base, extra = {}, {}
    for side, output in (("base", base), ("extra", extra)):
        config = fields(raw.get(side, {}), FAMILIES, side)
        for family, name, default in (("trophies", "Trophy", 16), ("keys", "Key", 4)):
            output[name] = exact_count(config.get(family, default if side == "base" else 0),
                                       f"{side}.{family}")
        for family, parts, suffix, defaults in (("relics", TIERS, "Relic", RELIC_DEFAULTS),
                                                 ("tokens", COLOURS, "CTR Token", dict.fromkeys(COLOURS, 4))):
            nested = fields(config.get(family, {}), parts, f"{side}.{family}")
            for part in parts:
                output[f"{part.title()} {suffix}"] = exact_count(
                    nested.get(part, defaults[part] if side == "base" else 0), f"{side}.{family}.{part}")
        if side == "base":
            gems = config.get("gems", list(COLOURS))
            if (not isinstance(gems, list) or any(type(x) is not str or x not in COLOURS for x in gems)
                    or len(set(gems)) != len(gems)):
                fail("base.gems must be a list of distinct red/green/blue/yellow/purple colours.")
            output.update({f"{x.title()} Gem": int(x in gems) for x in COLOURS})
        else:
            gems = fields(config.get("gems", {}), COLOURS, "extra.gems")
            output.update({f"{x.title()} Gem": exact_count(gems.get(x, 0), f"extra.gems.{x}")
                           for x in COLOURS})
    if base["Key"] != 4:
        fail("base.keys must be 4; all four hub Keys remain mandatory.")
    return base, extra


def relic_totals(raw):
    """{tier: base + extra copies} of `item_pool`, the counts a plan's Time
    Trial checks follow."""
    base, extra = normalize(raw)
    return {tier: base[f"{tier.title()} Relic"] + extra[f"{tier.title()} Relic"] for tier in TIERS}


@dataclass(frozen=True)
class ItemRow:
    name: str
    item: int
    base: int
    extra: int
    start_from_pool: int
    start_additional: int
    locked_selected: int
    remaining: int
    receipt_cap: int
    requirement_ceiling: int

    def wire(self):
        return {key: value for key, value in vars(self).items() if key != "name"}


@dataclass(frozen=True)
class ItemPlan:
    rows: tuple[ItemRow, ...]
    coded_checks: int
    locked_checks: int
    filler_count: int
    trap_count: int

    def wire(self):
        return dict(rows=[row.wire() for row in self.rows], coded_checks=self.coded_checks,
                    locked_checks=self.locked_checks, filler_count=self.filler_count,
                    trap_count=self.trap_count)

    def selected_names(self):
        return [row.name for row in self.rows for _ in range(row.remaining)]


def resolve(raw, coded_checks, *, starts=None, additional=None, locked=None,
            locked_checks=0, trap_percentage=0, selected_packs=None, pack_codes=None,
            surface=(), filler_reserve=0):
    """Resolve B+E-S-Q and capacity, without changing caller options or RNG.

    `locked` describes selected copies already placed by their owner. Future
    framework plando must not be entered here: it consumes its copies later.
    `selected_packs` supplies exact registered identities from the existing
    capability/racer/weapon/letter controls; it never changes counted families.
    Filler includes traps; trap_count is the portion replaced with traps.
    `pack_codes` names the codes of pack identities outside data/items.json
    (the named-block and generic custom letter items, #133 PR 3b).

    `surface` names the items created together and dropped together (the five
    surface items). They stay in only while `filler_reserve` filler slots are
    left, the ones the excluded checks need. There is no filler to give up
    first: filler is what remains once every selected copy has a check, so the
    order of the Rulebook (filler, then the surface items, then the refusal)
    holds by construction, and a refusal never counts a dropped surface item.
    """
    base, extra = normalize(raw)
    codes = dict(ITEMS)
    codes.update(pack_codes or {})
    for name, count in (selected_packs or {}).items():
        if name not in codes or name in base:
            fail(f"selected pack identity {name!r} is unknown or overlaps a counted family.")
        base[name] = exact_count(count, f"selected pack {name}")
        extra[name] = 0
    for label, values in (("starts", starts or {}), ("additional", additional or {}),
                          ("locked", locked or {})):
        if not isinstance(values, Mapping):
            fail(f"{label} must be a mapping.")
        for name, count in values.items():
            if name not in base and name not in surface:
                fail(f"{label} refers to unselected identity {name!r}.")
            exact_count(count, f"{label}.{name}")
    for label, value in (("coded_checks", coded_checks), ("locked_checks", locked_checks)):
        exact_count(value, label)
    if coded_checks > 4096 or locked_checks > coded_checks:
        fail("coded check capacity must be at most 4096 and cover every locked check.")
    exact_count(trap_percentage, "trap_percentage")
    if trap_percentage > 100:
        fail("trap_percentage must be at most 100.")
    if sum((locked or {}).values()) > locked_checks:
        fail("locked selected copies exceed realized locked checks.")
    if surface:
        taken = sum(base[name] + extra[name] for name in base) - sum((starts or {}).values()) \
            - sum((locked or {}).values()) + len(surface)
        if coded_checks - locked_checks - taken >= filler_reserve:
            base.update(dict.fromkeys(surface, 1))
            extra.update(dict.fromkeys(surface, 0))
        else:
            # A start cannot take a copy the seed no longer creates.
            for label, values in (("starts", starts or {}), ("additional", additional or {})):
                for name in values:
                    if name in surface:
                        fail(f"{label} names {name!r}, but the surface items do not fit in this seed's "
                             "checks and were dropped. Your settings were not changed.")
    rows = []
    for name in sorted(base, key=codes.__getitem__):
        b, e = base[name], extra[name]
        s, a, q = (starts or {}).get(name, 0), (additional or {}).get(name, 0), (locked or {}).get(name, 0)
        remaining = b + e - s - q
        if remaining < 0:
            fail(f"{name}: base {b} + extras {e} cannot supply {s} from-pool starts "
                 f"and {q} locked selected copies. Your settings were not changed.")
        if b + e + a > MAX_COUNT:
            fail(f"{name}: total receipt count exceeds {MAX_COUNT}.")
        rows.append(ItemRow(name, codes[name], b, e, s, a, q, remaining, b + e + a, b))
    demand = sum(row.remaining for row in rows)
    free = coded_checks - locked_checks
    if demand > free:
        fail(f"{demand} selected copies for {free} free checks. "
             f"Base {sum(r.base for r in rows)} + extras {sum(r.extra for r in rows)} "
             f"- from-pool starts {sum(r.start_from_pool for r in rows)} "
             f"- locked selected copies {sum(r.locked_selected for r in rows)} = {demand}. "
             f"Coded checks {coded_checks} - locked placements {locked_checks} = {free}. "
             f"Short by {demand - free} checks. Reduce selected counts/extras, choose explicit "
             "starts, or add content/checks. Your settings were not changed.")
    filler = free - demand
    return ItemPlan(tuple(rows), coded_checks, locked_checks, filler,
                    (filler * trap_percentage) // 100)


# Framework phases after item creation (#133 PR 4f): plando_items and
# item_links on content plans, per the Final phase ownership contract of the
# 2026-09-22 accounting design. The wire ledger above stays the immutable
# creation plan: plando and item links run later, in the framework, so they
# never change its rows. These checks keep the framework from inventing or
# dropping a selected copy around them.

def ledger_names(world):
    return {row.name for row in world.ctr_content_items.rows}


def filler_family(world):
    """Names this seed creates as filler or traps: the only items an explicit
    (`from_pool: false`) plando block may add, and the only ones removed to
    make room for it. Plain filler first, then traps."""
    from . import wumpa_family
    return tuple(wumpa_family.filler_weights(world)), tuple(sorted(world.item_name_groups["Traps"]))


def player_label(world):
    return world.multiworld.get_player_name(world.player)


def check_item_links(world):
    """Generation-time refusal: a link group's replacement item for this
    player must not be a selected (ledger) item. Each member would receive
    extra copies outside the item ledger, above its receipt cap."""
    names = ledger_names(world)
    for group in getattr(world.multiworld, "groups", {}).values():
        if world.player not in group["players"]:
            continue
        replacement = group.get("replacement_items", {}).get(world.player)
        if replacement in names:
            fail(f"item link {group['name']!r} of {player_label(world)} names {replacement!r} as its "
                 "replacement_item. That item is in this content plan's item ledger, and every linked copy "
                 "can bring a replacement copy outside it. Use a filler item or leave replacement_item empty. "
                 "Your settings were not changed.")


def _block_names(world, block):
    return [name for name in block.items if name in world.item_name_to_id]


def check_planned_blocks(world):
    """Before plando (generate_basic, after Main.py parsed the blocks).

    A `from_pool` block takes copies this world created; Fill.py silently
    creates a new copy when one is missing, which would add an unselected
    item. So the most copies any block could take must exist, counting every
    block's worst case. An item one of this player's links shares leaves the
    player's pool before plando runs, so a from-pool block may not name it.
    An explicit (`from_pool: false`) block may only add filler or traps,
    which pre_fill then pays for with this world's own filler."""
    blocks = getattr(world.multiworld, "plando_item_blocks", {}).get(world.player, ())
    if not blocks:
        return
    created = Counter(item.name for item in world.ctr_created_items)
    linked = set()
    for group in getattr(world.multiworld, "groups", {}).values():
        if world.player in group["players"]:
            linked |= set(group["item_pool"])
    plain, traps = filler_family(world)
    demand = Counter()
    for block in blocks:
        names = _block_names(world, block)
        most = block.count["max"] if isinstance(block.count, dict) else block.count
        # Fill.py clamps the count to the block's locations when it names some
        # and asks for no early/non-early set, so the worst case does too.
        if block.resolved_locations and not {"early_locations", "non_early_locations"} & set(block.locations):
            most = min(most, len(block.resolved_locations))
        if not block.from_pool:
            extra = sorted(set(names) - set(plain) - set(traps))
            if extra:
                fail(f"plando_items of {player_label(world)} adds {', '.join(extra)} with from_pool: false. "
                     "On a content plan an explicit plando block may only add filler or traps, because "
                     "every other item is counted in the item ledger. Use from_pool: true. "
                     "Your settings were not changed.")
            continue
        for name, count in Counter(names).items():
            demand[name] += min(count, most)
    for name, need in sorted(demand.items()):
        if name in linked:
            fail(f"plando_items of {player_label(world)} takes {name!r} from the pool, but an item link "
                 "of this player shares that item, so the copy leaves the player's pool before plando. "
                 "Remove it from the link or from the plando block. Your settings were not changed.")
        if need > created[name]:
            fail(f"plando_items of {player_label(world)} may take {need} {name!r} from the pool, but this "
                 f"content plan creates {created[name]}. Plando would create the missing copies itself, "
                 "outside the item ledger. Lower the plando count or select more copies in item_pool. "
                 "Your settings were not changed.")


def settle_after_plando(world):
    """pre_fill, after item links and plando.

    Every created copy is still in the pool or on a location (plando from the
    pool, or an item link's receipt event). A copy of this player on a real
    location that this world did not create is an explicit plando addition:
    it occupies a check that one of this world's items was counted for, so
    one of this world's own filler items leaves the pool for each. Returns
    the accounting for the spoiler."""
    mw, player = world.multiworld, world.player
    created = world.ctr_created_items
    created_ids = {id(item) for item in created}
    pool_ids = {id(item) for item in mw.itempool}
    placed, added = [], []
    for location in mw.get_filled_locations():
        item = location.item
        if item.player != player:
            continue
        if id(item) in created_ids:
            placed.append(location)
        elif location.address is not None:
            added.append(location)
    on_location = {id(location.item) for location in placed}
    lost = [item.name for item in created if id(item) not in pool_ids and id(item) not in on_location]
    if lost:
        fail(f"{len(lost)} selected or filler copies of {player_label(world)} left the item pool without "
             f"a location ({', '.join(sorted(set(lost)))}). Nothing may remove them before the fill.")
    names = ledger_names(world)
    invented = sorted({location.item.name for location in added if location.item.name in names})
    if invented:
        fail(f"plando placed a new copy of {', '.join(invented)} for {player_label(world)}. That item is in "
             "the item ledger and was not taken from the pool.")
    plain, traps = filler_family(world)
    removed = []
    for family in (plain, traps):
        for item in reversed(mw.itempool):
            if len(removed) == len(added):
                break
            if item.player == player and item.name in family and id(item) in created_ids:
                removed.append(item)
    # By identity: Item equality is name and player, so list.remove could
    # take an equal copy instead of the one counted here.
    gone = {id(item) for item in removed}
    mw.itempool[:] = [item for item in mw.itempool if id(item) not in gone]
    if len(removed) < len(added):
        fail(f"{len(added)} explicit plando items of {player_label(world)} need as many filler items to "
             f"make room, but only {len(removed)} filler or trap items are left in the pool. Removing a "
             "selected item instead is not allowed. Use from_pool: true or fewer explicit items.")
    world.ctr_plando_removed = removed
    linked = [location for location in placed if location.address is None and location.player in mw.groups]
    plando = [location for location in placed if location.address is not None]
    return dict(from_pool=Counter(location.item.name for location in plando),
                added=Counter(location.item.name for location in added),
                removed=Counter(item.name for item in removed),
                linked=Counter(location.item.name for location in linked))


def audit_before_output(world):
    """post_fill: every created copy (less the filler pre_fill removed) is on
    a location, and the precollected items are exactly the plan's starts. A
    fill that dropped a selected copy or moved one to the start inventory
    repaired the seed outside the ledger, so the seed is refused."""
    mw, player = world.multiworld, world.player
    removed = {id(item) for item in getattr(world, "ctr_plando_removed", ())}
    unplaced = sorted({item.name for item in world.ctr_created_items
                       if id(item) not in removed and item.location is None})
    if unplaced:
        fail(f"the fill left created items of {player_label(world)} without a location "
             f"({', '.join(unplaced)}). Refusing the seed instead of dropping them.")
    starts = Counter({row.name: row.start_from_pool + row.start_additional
                      for row in world.ctr_content_items.rows if row.start_from_pool + row.start_additional})
    held = Counter(item.name for item in mw.precollected_items[player])
    if held != starts:
        fail(f"the start inventory of {player_label(world)} differs from the content plan's starts "
             f"(extra {dict(held - starts)}, missing {dict(starts - held)}). An automatic start-inventory "
             "repair is not allowed on a content plan.")


def audit_room_before_output(multiworld):
    """stage_post_fill, once per room with a content-plan slot: no item of any
    slot may be left without a location. Fill.py only warns and drops the
    rest when a room has more items than locations, which an explicit plando
    block of another slot into a content-plan check can cause."""
    worlds = [w for w in multiworld.get_game_worlds("Crash Team Racing") if hasattr(w, "ctr_content_plan")]
    if not worlds or getattr(multiworld, "generation_is_fake", False):
        return
    unplaced = [item for item in multiworld.itempool if item.location is None]
    if unplaced:
        names = sorted({f"{item.name} ({multiworld.get_player_name(item.player)})" for item in unplaced})
        fail(f"the fill left {len(unplaced)} items without a location ({', '.join(names[:10])}). "
             "The room has more items than locations, usually from an explicit (from_pool: false) "
             "plando block. Refusing the seed instead of dropping them.")
