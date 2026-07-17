"""Regression guard for the vanilla-hub return-exit drift.

The AP region graph must match the GAME's traversal semantics (native is the
source of truth): finishing a warp-pad race returns you to the PHYSICAL pad
you warped from, and the four hub doors open only on received Keys. Before
the Option-1b fix, destination shuffle left every destination region's
"<Dest> -> Hub" return exit pointing at its VANILLA hub, handing fill an
ungated phantom edge into Key-locked hubs. That divergence was measured as
benign on 2026-07-10 (155 seeds) and then proven load-bearing by community
seed 87763653607652956054, where fill placed all four Keys behind phantom
edges: an in-game hard lock that generation, accessibility:full, and the
fuzzer are all structurally blind to (they reason over the same graph).

These tests lock the corrected topology in:

- test_return_exits_target_physical_hub: every destination's return exit
  must lead to the hub its LOADING pad physically sits in (identity when
  shuffle is off, retargeted when it is on).
- test_keyed_hubs_unreachable_without_keys: from an empty inventory no
  Key-gated hub (and no location inside one) may be reachable, mirroring
  native AH_Door gating exactly.

If either test ever fails again, fill is reasoning over a map the game does
not play on, and unbeatable-but-"valid" seeds are back on the table.
"""

from BaseClasses import CollectionState

from . import CTRTestBase

# The four Key-gated hubs plus the Key-2 cups room (native arrKeysNeeded /
# AH_Door AP Option B). N. Sanity Beach is the start hub and stays open.
KEYED_HUBS = (
    "Gem Stone Valley",
    "Lost Ruins",
    "Glacier Park",
    "Citadel City",
    "Cups Room",
)


class ReturnExitGuardMixin:
    def test_return_exits_target_physical_hub(self):
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        checked = 0
        for pad_name in world.warp_pad_ids:
            try:
                pad = mw.get_entrance(pad_name, p)
            except KeyError:
                continue  # pad kind not present under these options
            dest = pad.connected_region
            try:
                ret = mw.get_entrance(f"{dest.name} -> Hub", p)
            except KeyError:
                continue  # destination without a return exit (boss garages)
            checked += 1
            self.assertIs(
                ret.connected_region, pad.parent_region,
                f"'{dest.name} -> Hub' returns to "
                f"'{ret.connected_region and ret.connected_region.name}' but its "
                f"loading pad '{pad_name}' is in '{pad.parent_region.name}': "
                f"phantom vanilla-hub edge (return-exit drift)")
        self.assertGreater(checked, 0, "guard exercised no return exits")

    def test_keyed_hubs_unreachable_without_keys(self):
        mw, p = self.multiworld, self.player
        state = CollectionState(mw)  # empty inventory (plus precollected)
        self.assertFalse(state.has("Key", p),
                         "test premise broken: a Key is precollected")
        for hub in KEYED_HUBS:
            self.assertFalse(
                state.can_reach_region(hub, p),
                f"'{hub}' is reachable with zero Keys; in game its door needs "
                f"received Keys (AH_Door), so fill may strand progression")


class TestTopologyMergedShuffle(ReturnExitGuardMixin, CTRTestBase):
    """The shipped default and the combo of the 2026-07-17 community seed."""
    options = {
        "warppad_unlock_requirements": "random_without_4_keys",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
        "warp_pad_shuffle_grouping": "merged",
        "shuffle_gems": True,
        "shuffle_keys": True,
        "include_gem_cups": True,
        "include_battle_arenas": True,
        "two_stage_density": "deep",
        "podium_placement_checks": True,
        "podium_any_position_rung": True,
    }


class TestTopologyPerCategoryShuffle(ReturnExitGuardMixin, CTRTestBase):
    options = {
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": ["crystals", "tracks"],
        "warp_pad_shuffle_grouping": "per_category",
        "shuffle_gems": True,
        "shuffle_keys": True,
        "include_gem_cups": True,
        "include_battle_arenas": True,
    }


class TestTopologyNoShuffle(ReturnExitGuardMixin, CTRTestBase):
    """Control: identity destinations must satisfy the same invariants."""
    options = {
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": [],
    }
