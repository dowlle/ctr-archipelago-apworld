"""Keep early YAML rolls stable when the origin-letter registry grows."""
from dataclasses import dataclass

from Options import (ExcludeLocations, ItemLinks, LocalItems, NonLocalItems,
                     PerGameCommonOptions as APCommonOptions, PlandoItems,
                     PriorityLocations, StartHints, StartLocationHints)


class _StableRandomNames:
    def verify(self, world, player_name, plando_options):
        if self.random_str and not self.value:
            from .track_origins import legacy_option_world
            world = legacy_option_world(world)
        super().verify(world, player_name, plando_options)


class CTRLocalItems(_StableRandomNames, LocalItems):
    __doc__ = LocalItems.__doc__


class CTRNonLocalItems(_StableRandomNames, NonLocalItems):
    __doc__ = NonLocalItems.__doc__


class CTRStartHints(_StableRandomNames, StartHints):
    __doc__ = StartHints.__doc__


class CTRStartLocationHints(_StableRandomNames, StartLocationHints):
    __doc__ = StartLocationHints.__doc__


class CTRExcludeLocations(_StableRandomNames, ExcludeLocations):
    __doc__ = ExcludeLocations.__doc__


class CTRPriorityLocations(_StableRandomNames, PriorityLocations):
    __doc__ = PriorityLocations.__doc__


class CTRPlandoItems(PlandoItems):
    __doc__ = PlandoItems.__doc__

    def verify(self, world, player_name, plando_options):
        from .track_origins import legacy_option_world

        # Group draws are rolled before tracks are picked. Explicit item
        # names can still address any registered origin letter.
        super().verify(legacy_option_world(world) if self.value else world, player_name, plando_options)


class CTRItemLinks(ItemLinks):
    __doc__ = ItemLinks.__doc__

    def verify(self, world, player_name, plando_options):
        from .track_origins import legacy_option_world

        if self.value:
            old_view = legacy_option_world(world)
            old = ItemLinks.from_any(self.value)
            old.verify(old_view._replace(item_names=world.item_names), player_name, plando_options)
            self.legacy_value = old.value
        super().verify(world, player_name, plando_options)


@dataclass
class PerGameCommonOptions(APCommonOptions):
    local_items: CTRLocalItems
    non_local_items: CTRNonLocalItems
    start_hints: CTRStartHints
    start_location_hints: CTRStartLocationHints
    exclude_locations: CTRExcludeLocations
    priority_locations: CTRPriorityLocations
    item_links: CTRItemLinks
    plando_items: CTRPlandoItems


NAME_OPTION_TYPES = [CTRLocalItems, CTRNonLocalItems, CTRStartHints, CTRStartLocationHints,
                     CTRExcludeLocations, CTRPriorityLocations, CTRItemLinks, CTRPlandoItems]
