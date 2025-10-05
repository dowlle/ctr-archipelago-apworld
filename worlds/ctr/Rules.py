from worlds.generic.Rules import add_rule
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ctrAPWorld



def set_rules(world: "ctrAPWorld"):
    player = world.player
    options = world.options

    add_rule(world.multiworld.get_entrance("N. Sanity Beach -> Gem Stone Valley", player),
             lambda state: state.has("Progressive Door", 1))
    add_rule(world.multiworld.get_entrance("Gem Stone Valley -> Lost Ruins", player),
             lambda state: state.has("Progressive Door", 1))
    
    # Victory condition rule!
    world.multiworld.completion_condition[player] = lambda state: state.has("Victory", player)