"""Issue #52: entrance hints under warp-pad destination shuffle.

extend_hint_information annotates each location in a shuffled DESTINATION region
with the PHYSICAL pad that now loads it, so the server renders the hint as
"... at the <pad> pad". It is a per-seed multidata channel (er_hint_data): no
ids, names, datapackage, fill, or reachability are touched.

These tests use an INDEPENDENT oracle: a pad exit's connected_region is the
region that pad physically loads (the Regions.py:537-554 wiring). So every
location in that region -- and in its podium dead-end -- must carry
"the <pad minus ' Warp Pad'> pad", derived from the built graph rather than from
warp_pad_map the way the implementation derives it.

extend_hint_information is an OUTPUT-time hook (Main.call_all), which
WorldTestBase does not run, so the tests invoke it directly on the generated
world and inspect the hint_data it fills.
"""

from . import CTRTestBase

_SUFFIX = " Warp Pad"


def _label(pad_name):
    base = pad_name[:-len(_SUFFIX)] if pad_name.endswith(_SUFFIX) else pad_name
    return f"the {base} pad"


def _shuffled_pads(world):
    """Pads that GENUINELY moved this seed. warp_pad_map lists every pad in a
    participating pool, and a within-pool permutation can leave a pad on its own
    destination (a fixed point); those are NOT worth a hint (research spec §2:
    a location's own name already carries its track). Filtering them here is what
    keeps the oracle correct across the random per-test seed."""
    return [pad for pad, dest_lid in world.warp_pad_map.items()
            if dest_lid != world.warp_pad_ids.get(pad, {}).get("level_id")]


class TestEntranceHintsShuffle(CTRTestBase):
    """Merged tracks+crystals+cups+arenas shuffle: the shipped-default topology."""
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
        "warp_pad_shuffle_grouping": "merged",
        "shuffle_gems": True,
        "shuffle_keys": True,
        "include_gem_cups": True,
        "include_battle_arenas": True,
        "podium_placement_checks": True,
        "podium_any_position_rung": True,
    }

    def _hint_text(self):
        world = self.multiworld.worlds[self.player]
        hd = {}
        world.extend_hint_information(hd)
        return hd





class TestEntranceHintsNoShuffle(CTRTestBase):
    """Control: with no destination shuffle, the hook is a no-op (a location's own
    name already carries its track)."""
    options = {
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": [],
    }

