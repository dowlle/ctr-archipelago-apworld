"""slot_data assembly for the CTR world (split out of __init__.py, issue #309).

Every seed is a content plan (one generator). The wire is the plan's
(content_plan.wire), plus the two additive envelope flags and the exported
logic. One generator row 12 deleted the original generator's blocks.
"""

import logging
from typing import Dict

from . import wumpa_family


#: The global slot_data schema this apworld emits. Schema 18 is the only one
#: (one generator plan, section 4, decided 2026-10-30).
SLOT_DATA_SCHEMA = 18


def win_logic_block(world) -> Dict[str, object]:
    """The `win_logic` key, or nothing when another world wrapped a rule."""
    from .win_logic import ForeignRuleError, wire_block
    try:
        return {"win_logic": wire_block(world)}
    except ForeignRuleError as error:
        logging.getLogger(__name__).warning(
            "%s: win_logic omitted, race-loss DeathLink sends on every loss: %s",
            world.player_name, error)
        return {}


def fill_slot_data(world) -> Dict[str, object]:
    from . import content_plan
    wire = content_plan.wire(world)
    wire["ctr_options"]["reserve_top_up"] = wumpa_family.reserve_top_up_enabled(world)
    wire["ctr_options"]["spoiler_items"] = bool(world.options.spoiler_items.value)
    wire.update(win_logic_block(world))
    return wire
