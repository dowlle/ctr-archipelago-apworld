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


class TestPodiumCupLegReachability(CTRTestBase):
    """Issue #86 -- a podium rung reachable ONLY via a Gem Cup leg must stay in
    logic when the track's own warp pad is shut.

    Vanilla unlock mode so the cup pad keeps its real has('<colour> CTR Token', 4)
    gate and every track pad sits behind its Key-gated hub (verified against
    data/world.json: N.Sanity->Gem Stone Valley Key-1, Gem Stone Valley->Cups Room
    Key-2, Yellow Cup pad Yellow CTR Token-4, Glacier Park->Citadel City Key-3).
    Yellow Gem Cup legs Hot Air Skyway (data/gem_cup_legs.json), and Hot Air Skyway
    lives in the Key-3 Citadel City hub, so with 2 Keys + 4 Yellow CTR Tokens the
    Yellow Gem Cup is reachable while the Hot Air Skyway track region is not -- the
    cup-leg-only case that was False before the joint-region fix."""
    options = {
        "warppad_unlock_requirements": "vanilla",
        "warp_pad_shuffle_categories": [],  # identity destinations: pin a
        # deterministic topology (default shuffle would re-key which physical pad
        # loads Hot Air Skyway per seed; the shuffle case is covered by the
        # randomized TestTopology* classes above, and the fix is shuffle-correct
        # because a cup leg belongs to the cup region regardless of pad).
        "podium_placement_checks": True,
        "podium_held_rungs": True,
        "include_gem_cups": True,
    }

    def _state_with(self, items):
        """A fresh CollectionState granting exactly the given {item_name: count}."""
        state = CollectionState(self.multiworld)
        world = self.multiworld.worlds[self.player]
        for name, n in items.items():
            for _ in range(n):
                state.collect(world.create_item(name), prevent_sweep=True)
        return state

    def test_cup_only_rung_in_logic(self):
        p = self.player
        state = self._state_with({"Key": 2, "Yellow CTR Token": 4})
        self.assertTrue(
            state.can_reach("Yellow Gem Cup", "Region", p),
            "Yellow Gem Cup should be reachable with 2 Keys + 4 Yellow CTR Tokens")
        self.assertFalse(
            state.can_reach("Hot Air Skyway", "Region", p),
            "Hot Air Skyway track region must stay Key-3 gated (Citadel City)")
        self.assertTrue(
            state.can_reach("Hot Air Skyway: Held 1st", "Location", p),
            "cup-only rung must be in logic via the Yellow Gem Cup leg (issue #86)")

    def test_cup_leg_exposes_only_rungs(self):
        p = self.player
        state = self._state_with({"Key": 2, "Yellow CTR Token": 4})
        # A Yellow Gem Cup leg is a real track load that fires Hot Air Skyway's
        # placement rungs, but does NOT earn its Trophy Race, CTR Token Challenge,
        # or Time Trials -- the joint podium region is a dead end, so cup
        # reachability exposes nothing else on the track (golden rule).
        for loc in ("Hot Air Skyway: Trophy Race",
                    "Hot Air Skyway: CTR Token Challenge",
                    "Hot Air Skyway: Sapphire Time Trial",
                    "Hot Air Skyway: Gold Time Trial",
                    "Hot Air Skyway: Platinum Time Trial"):
            self.assertFalse(
                state.can_reach(loc, "Location", p),
                f"{loc} must stay unreachable via a cup leg (golden rule)")

    def test_empty_inventory_no_rungs(self):
        p = self.player
        state = CollectionState(self.multiworld)
        self.assertFalse(state.has("Key", p),
                         "test premise broken: a Key is precollected")
        # Neither the Hot Air Skyway pad (Key-gated hub) nor any cup that legs it
        # is reachable from an empty inventory, so its rung is out of logic.
        self.assertFalse(
            state.can_reach("Hot Air Skyway: Held 1st", "Location", p),
            "a Key-gated track's rung must be unreachable with zero items")

    def test_joint_region_entrances(self):
        p, mw = self.player, self.multiworld
        # Hot Air Skyway is legged by BOTH Yellow and Purple Gem Cups, the exact
        # entrance-name-uniqueness hazard flagged for the joint region: names must
        # be unique per (source, track), all landing in the one podium region.
        for name in ("Hot Air Skyway -> Hot Air Skyway: Podium",
                     "Yellow Gem Cup -> Hot Air Skyway: Podium",
                     "Purple Gem Cup -> Hot Air Skyway: Podium"):
            ent = mw.get_entrance(name, p)
            self.assertEqual(
                ent.connected_region.name, "Hot Air Skyway: Podium",
                f"entrance '{name}' must connect to the joint podium region")
