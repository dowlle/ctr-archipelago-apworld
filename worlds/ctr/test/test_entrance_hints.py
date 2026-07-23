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

    def test_shuffled_locations_name_physical_pad(self):
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        shuffled = _shuffled_pads(world)
        self.assertTrue(shuffled,
                        "test premise broken: no pad genuinely moved this seed")
        hd = self._hint_text()
        self.assertIn(p, hd, "shuffled seed emitted no entrance hints")
        text = hd[p]

        checked_regions = 0
        checked_locs = 0
        for pad_name in shuffled:
            try:
                dest = mw.get_entrance(pad_name, p).connected_region
            except KeyError:
                continue  # pad kind not present under these options
            if dest is None:
                continue
            expected = _label(pad_name)
            region_names = {dest.name, f"{dest.name}: Podium"}
            hit = False
            for loc in mw.get_locations(p):
                if loc.address is None or loc.parent_region is None:
                    continue
                if loc.parent_region.name in region_names:
                    self.assertEqual(
                        text.get(loc.address), expected,
                        f"'{loc.name}' in '{loc.parent_region.name}' is loaded by "
                        f"'{pad_name}', so its hint should be '{expected}'")
                    checked_locs += 1
                    hit = True
            if hit:
                checked_regions += 1

        self.assertGreater(checked_regions, 0,
                           "oracle exercised no shuffled destination region")
        self.assertGreater(checked_locs, 0, "oracle exercised no location")

    def test_podium_rungs_carry_the_pad_hint(self):
        """A rung location lives in '<track>: Podium', not '<track>', so it only
        carries the hint if the track-prefix mapping fires (research §3 refinement)."""
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        hd = self._hint_text()
        text = hd.get(p, {})
        checked = 0
        for pad_name in _shuffled_pads(world):
            try:
                dest = mw.get_entrance(pad_name, p).connected_region
            except KeyError:
                continue
            if dest is None:
                continue
            podium_name = f"{dest.name}: Podium"
            expected = _label(pad_name)
            for loc in mw.get_locations(p):
                if (loc.address is not None and loc.parent_region is not None
                        and loc.parent_region.name == podium_name):
                    self.assertEqual(
                        text.get(loc.address), expected,
                        f"podium rung '{loc.name}' should hint '{expected}'")
                    checked += 1
        self.assertGreater(
            checked, 0,
            "no podium rung was checked (expected some under podium_placement_checks)")

    def test_no_stray_hints(self):
        """Every hinted location must sit in a genuinely shuffled destination region
        (or its podium) -- never a vanilla-loaded one."""
        mw, p = self.multiworld, self.player
        world = mw.worlds[p]
        text = self._hint_text().get(p, {})
        shuffled = set()
        for pad_name in _shuffled_pads(world):
            try:
                dest = mw.get_entrance(pad_name, p).connected_region
            except KeyError:
                continue
            if dest is not None:
                shuffled.add(dest.name)
                shuffled.add(f"{dest.name}: Podium")
        addr_region = {loc.address: loc.parent_region.name
                       for loc in mw.get_locations(p)
                       if loc.address is not None and loc.parent_region is not None}
        for addr in text:
            self.assertIn(
                addr_region.get(addr), shuffled,
                f"hinted location addr {addr} ('{addr_region.get(addr)}') is not a "
                f"shuffled destination region")


class TestEntranceHintsNoShuffle(CTRTestBase):
    """Control: with no destination shuffle, the hook is a no-op (a location's own
    name already carries its track)."""
    options = {
        "warppad_unlock_requirements": "randomized",
        "warp_pad_shuffle_categories": [],
    }

    def test_no_hints_without_shuffle(self):
        world = self.multiworld.worlds[self.player]
        self.assertFalse(world.warp_pad_map,
                         "test premise broken: a pad shuffled with categories=[]")
        hd = {}
        world.extend_hint_information(hd)
        self.assertEqual(hd, {}, "identity/vanilla seed must emit no entrance hints")
