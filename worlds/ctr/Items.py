import json
import pkgutil
from BaseClasses import ItemClassification
from typing import List, TYPE_CHECKING, TypedDict


if TYPE_CHECKING:
    from . import ctrAPWorld
    from .Types import ctrAPItem


class ItemDict(TypedDict):
    name: str
    code: int
    count: int
    classification: ItemClassification

def load_item_table() -> List[ItemDict]:
    """
    Loads item data from the CTR world's data/items.json file.
    Returns a list of item dictionaries with proper ItemClassification enums.
    """
    data_bytes = pkgutil.get_data(__package__, "data/items.json")
    raw_items = json.loads(data_bytes.decode("utf-8"))

    classes = {
        "progression": ItemClassification.progression,
        "filler": ItemClassification.filler,
        "useful": ItemClassification.useful,
        "trap": ItemClassification.trap,
        "progression_skip_balancing": ItemClassification.progression_skip_balancing,
        "progression_deprioritized": ItemClassification.progression_deprioritized,
        "progression_deprioritized_skip_balancing": ItemClassification.progression_deprioritized_skip_balancing,
    }

    item_table: List[ItemDict] = []
    seen_names = set()
    seen_codes = set()
    for entry in raw_items:
        cls_name = entry["classification"].lower()
        name = entry["name"]
        code = entry["code"]

        if not isinstance(name, str) or not name:
            raise ValueError(f"Invalid CTR item name: {name!r}")
        if type(code) is not int or code < 0:
            raise ValueError(f"Invalid CTR item code for {name!r}: {code!r}")
        if name in seen_names:
            raise ValueError(f"Duplicate CTR item name: {name!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate CTR item code: {code}")
        seen_names.add(name)
        seen_codes.add(code)

        item_table.append({
            "name": name,
            "code": code,
            "count": entry["count"],
            "classification": classes[cls_name],
        })

    return item_table


# Comfort-only issues #14/#15 pack. It stays atomic when a reduced location
# set cannot host all five, rather than emitting a seed-dependent subset.
SURFACE_ITEM_NAMES = frozenset({
    "Ignore Grass", "Ignore Dirt", "Ignore Snow", "Ignore Water", "Ignore Ice",
})


def create_item(world, name: str) -> "ctrAPItem":
    """The world's create_item (moved from item_creation in one generator row 12).
    Imports are local because Items loads before the modules it reads."""
    from . import characters, item_boxes, progressive_capability
    from .item_boxes import ITEM_BOX_CLASS
    from .Types import ctrAPItem
    item_id: int = world.item_name_to_id[name]
    classification = world._item_data_by_name[name]["classification"]
    # Honest per-seed relic classification (vanilla-fill lever 1).
    # data/items.json marks every relic "progression" unconditionally, but in a
    # vanilla-warp-pad seed whose goal/accessibility does not depend on a relic
    # tier, that tier gates nothing -- yet the ordered fill still treats it as
    # progression, inflating the pool to exactly the location count (zero slack)
    # and cornering fill_restrictive on the deepest currency. Downgrade such a
    # tier to "useful" so it leaves the ordered fill (placed by remaining_fill).
    # The map is a pure function of options; see _relic_progression_map.
    relic_prog = getattr(world, "_ctr_relic_prog", None)
    if relic_prog is not None and relic_prog.get(name) is False:
        classification = ItemClassification.useful
    # Honest per-seed BOOST classification, the same lever in the other
    # direction. #145 Itemsanity is the first logic reader of a capability
    # tier: its Turbo checks require one received Progressive Boost when
    # the chain is randomized (Decision 2 ruling, 2026-08-10). Logic state
    # only tracks progression items, so the gate is only real if the chain
    # is progression in exactly those seeds -- left `useful` (the #12/#13
    # shape), the Turbo checks sit permanently outside logic and fill
    # forbids progression/useful there, which surfaced as FillErrors in
    # the 5,000-run default fuzz arm. Every other seed keeps the frozen
    # `useful` classification from data/items.json.
    # #109 box slots are the second reader: boost-gated slots exist in
    # every box seed, and the hard-knowledge slots additionally read the
    # three stat chains (the hard-tier general rule), so those chains
    # upgrade too -- but ONLY at hard, because no easier tier creates a
    # stats-reading slot.
    # The USF finish gate (usf_finish.py, ruled 2026-08-12) is the
    # third reader and the one that makes the boost upgrade UNCONDITIONAL:
    # Hot Air Skyway's Trophy Race is a static location present in every
    # seed, so every randomized-boost seed reads the chain now, whatever
    # itemsanity and box locations are set to. Left `useful`, that track's
    # finish -- and its time trials, token challenge and finish rungs --
    # would sit permanently outside logic, the same FillError class the
    # #145 upgrade was written for. The stat chains keep their narrower
    # condition: no rule outside the hard box tier reads them.
    _boost_mode = int(world.options.progressive_boost.value)
    _boost_names = ({progressive_capability.BOOST_CHAIN} if _boost_mode == 1
                    else {progressive_capability.boost_item_name(c)
                          for c in progressive_capability.ROSTER}
                    if _boost_mode == 2 else set())
    if name in _boost_names:
        classification = ItemClassification.progression
    _stats_mode = int(world.options.progressive_stats.value)
    _stat_names = (set(progressive_capability.STAT_CHAINS)
                   if _stats_mode == 1 else
                   {progressive_capability.stat_item_name(chain, character)
                    for character in progressive_capability.ROSTER
                    for chain in progressive_capability.STAT_CHAINS}
                   if _stats_mode == 2 else set())
    if (name in _stat_names
            and ITEM_BOX_CLASS.is_enabled(world.options)
            and int(world.options.shortcut_knowledge.value) == item_boxes.SK_HARD):
        classification = ItemClassification.progression
    # Honest per-seed CHARACTER classification (R17), the same lever again.
    # data/items.json freezes all 16 racers as `useful`; a racer-locked seed
    # has pads whose access rule reads one, so in exactly those seeds the
    # unlock items are genuine progression. Locks off leaves them `useful`,
    # which is both the correct AP semantics for an item that gates nothing
    # and a deliberate relaxation of an already ~98%-progression pool.
    if name in characters.ROSTER_CHARACTER_ID:
        classification = characters.unlock_classification(world)
    return ctrAPItem(
        name=name,
        classification=classification,
        code=item_id,
        player=world.player,
    )
