"""Keep early YAML rolls stable when the origin-letter registry grows."""
from dataclasses import dataclass

from Options import (ExcludeLocations, ItemLinks, LocalItems, NonLocalItems, OptionError,
                     PerGameCommonOptions as APCommonOptions, PlandoItems,
                     PriorityLocations, StartHints, StartLocationHints)


class _StableRandomNames:
    def verify(self, world, player_name, plando_options):
        if self.random_str and not self.value:
            from .track_origins import legacy_option_world
            world = legacy_option_world(world, for_random=True)
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
        super().verify(legacy_option_world(world, for_random=True) if self.value else world, player_name, plando_options)


class CTRItemLinks(ItemLinks):
    __doc__ = ItemLinks.__doc__

    def verify(self, world, player_name, plando_options):
        from .track_origins import legacy_option_world

        if self.value:
            old_view = legacy_option_world(world)
            old = ItemLinks.from_any(self.value)
            old.verify(old_view._replace(item_names=world.item_names), player_name, plando_options)
            self.legacy_value = old.value
            # The stock verifier has already checked both locality lists against
            # the legacy pool. Newly registered letters can be checked when the
            # plan tells us which of them are actually in this slot's pool.
            non_local = [link.pop("non_local_items", None) for link in self.value]
            super().verify(world, player_name, plando_options)
            for link, names in zip(self.value, non_local):
                if names is not None:
                    link["non_local_items"] = names
            return
        super().verify(world, player_name, plando_options)

    def verify_origin_locality(self, world, origin_items):
        if not origin_items:
            return
        for link in self.value:
            local = self.verify_items(link.get("local_items", ()), link["name"], "local_items", world)
            non_local = self.verify_items(link.get("non_local_items", ()), link["name"], "non_local_items", world)
            overlap = local & non_local & origin_items & set(link["item_pool"])
            if overlap:
                raise OptionError(f"item_link {link['name']} has {sorted(overlap)} items in both its local_items "
                                  "and non_local_items pool.")


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
