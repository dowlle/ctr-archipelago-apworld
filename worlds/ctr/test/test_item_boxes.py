"""Focused gates for the #109 item-box seating activation.

The seating table, rule map and tier-removal sets were derived in the
2026-08-10 seating spec and independently re-verified against the FINAL 241
placement file (counts, positions AND interleaving-aware slot numbers) before
this build; these tests lock the derived numbers so a drift in any table is a
red suite, not a silently mis-seated seed.
"""
import unittest

from BaseClasses import CollectionState
from test.general import setup_multiworld

from .. import ctrAPWorld
from ..item_boxes import (BOX_RULES, BOX_TRACKS, EXPLICIT_NO_GATE,
                          ITEM_BOX_CLASS, ITEM_BOX_CODE_BASE, PLACED_COUNTS,
                          SK_HARD, SK_MEDIUM, SK_REQUIRED_TIER, SLOTS_PER_TRACK,
                          TIGER_TEMPLE_DOOR_OPENERS, TRACK_LEVEL_IDS)
from ..progressive_capability import STAT_CHAINS
from . import CTRTestBase

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def _build(seed=1, **options):
    return setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)


def _grant(state, player, *items):
    for item in items:
        state.add_item(item, player, 1)


class TestSeatingTables(unittest.TestCase):
    """The static tables against their derived invariants."""

    def test_placed_counts_sum_and_shape(self):
        self.assertEqual(sum(PLACED_COUNTS.values()), 241)
        self.assertEqual(set(PLACED_COUNTS), set(BOX_TRACKS))
        self.assertEqual(set(TRACK_LEVEL_IDS), set(BOX_TRACKS))
        self.assertEqual(sorted(TRACK_LEVEL_IDS.values()), list(range(18)))

    def test_rule_census(self):
        """Spec 2 census plus the three ruled Hot Air Skyway defaults and the
        live-session Tiny Arena 1 fix: 40 gated slots, 8 explicit no-gate, 193
        plain free-reach."""
        self.assertEqual(len(BOX_RULES), 40)
        boost1 = [k for k, (b, s) in BOX_RULES.items() if b == 1 and not s]
        boost2 = [k for k, (b, s) in BOX_RULES.items() if b == 2 and not s]
        stats = [k for k, (b, s) in BOX_RULES.items() if s]
        sk_only = [k for k, (b, s) in BOX_RULES.items() if b == 0 and not s]
        # 6 pure + 4 with a medium SK term + Tiny Arena 1 (ruled 2026-08-12).
        self.assertEqual(len(boost1), 11)
        self.assertIn(("Tiny Arena", 1), boost1)
        self.assertEqual(len(boost2), 21)   # 18 captured + 3 ruled HAS defaults
        self.assertEqual(len(stats), 5)     # the 5 hard-tier slots
        # Dragon Mines 2 / Coco Park 7 (respawn) + the Tiger Temple door.
        self.assertEqual(sorted(sk_only),
                         [("Coco Park", 7), ("Dragon Mines", 2),
                          ("Tiger Temple", 5)])
        self.assertEqual(len(EXPLICIT_NO_GATE), 8)
        self.assertFalse(set(EXPLICIT_NO_GATE) & set(BOX_RULES))
        # Every gated/no-gate slot must actually be a placed slot.
        for track, slot in list(BOX_RULES) + list(EXPLICIT_NO_GATE):
            self.assertLessEqual(slot, PLACED_COUNTS[track])

    def test_sk_removal_sets(self):
        self.assertEqual(len(SK_REQUIRED_TIER), 12)
        hard = {k for k, tier in SK_REQUIRED_TIER.items() if tier == SK_HARD}
        self.assertEqual(hard, {("Papu's Pyramid", 7), ("Papu's Pyramid", 10),
                                ("Polar Pass", 9), ("Hot Air Skyway", 8),
                                ("Oxide Station", 6)})
        # The hard-tier slots are exactly the stats-reading slots.
        self.assertEqual(hard, {k for k, (b, s) in BOX_RULES.items() if s})

    def test_slot_codes_follow_the_frozen_block(self):
        self.assertEqual(ITEM_BOX_CLASS.slot_code(BOX_TRACKS[0], 1),
                         ITEM_BOX_CODE_BASE)
        for ti, track in enumerate(BOX_TRACKS):
            self.assertEqual(
                ITEM_BOX_CLASS.slot_code(track, SLOTS_PER_TRACK),
                ITEM_BOX_CODE_BASE + ti * SLOTS_PER_TRACK + SLOTS_PER_TRACK - 1)


class TestBoxLocationsOff(CTRTestBase):
    def test_no_box_locations_by_default(self):
        for name in ITEM_BOX_CLASS.names():
            with self.subTest(location=name):
                with self.assertRaises(KeyError):
                    self.multiworld.get_location(name, self.player)

    def test_off_wire_keeps_scalars_and_omits_block(self):
        slot_data = self.world.fill_slot_data()
        self.assertFalse(slot_data["ctr_options"]["box_locations"])
        self.assertIn("shortcut_knowledge", slot_data["ctr_options"])
        self.assertNotIn("item_box_checks", slot_data)


class TestSeatingPerTier(unittest.TestCase):
    PLAYER = 1

    def _created(self, **options):
        mw = _build(box_locations=True, **options)
        return [loc.name for loc in mw.get_locations(self.PLAYER)
                if getattr(loc, "type", None) == "item_boxes"]

    def test_easy_creates_229(self):
        created = self._created()
        self.assertEqual(len(created), 229)
        self.assertNotIn("Tiger Temple: Item Box 5", created)
        self.assertNotIn("Coco Park: Item Box 7", created)

    def test_medium_creates_236(self):
        created = self._created(shortcut_knowledge="medium")
        self.assertEqual(len(created), 236)
        self.assertIn("Tiger Temple: Item Box 5", created)
        self.assertNotIn("Polar Pass: Item Box 9", created)

    def test_hard_creates_241(self):
        created = self._created(shortcut_knowledge="hard")
        self.assertEqual(len(created), 241)
        self.assertIn("Polar Pass: Item Box 9", created)

    def test_inert_slots_are_never_created(self):
        created = set(self._created(shortcut_knowledge="hard"))
        self.assertNotIn("Crash Cove: Item Box 11", created)
        self.assertNotIn("Dragon Mines: Item Box 14", created)


class TestBoxAccessRules(unittest.TestCase):
    PLAYER = 1

    def _rule(self, track, slot, **options):
        mw = _build(box_locations=True, **options)
        name = ITEM_BOX_CLASS.location_name(track, slot)
        loc = mw.get_location(name, self.PLAYER)
        return mw, loc.access_rule

    def test_boost_terms_vacuous_when_pack_off(self):
        for track, slot in (("Crash Cove", 4), ("N. Gin Labs", 4)):
            with self.subTest(track=track, slot=slot):
                mw, rule = self._rule(track, slot)
                self.assertTrue(rule(CollectionState(mw)))

    def test_boost_terms_bind_when_randomized(self):
        # Tiny Arena 1 is the slot found unbreakable-but-in-logic on
        # 2026-08-12; it takes one boost copy, not USF.
        for track, slot in (("Crash Cove", 4), ("Tiny Arena", 1)):
            with self.subTest(track=track, slot=slot):
                mw, rule = self._rule(track, slot,
                                      progressive_boost="shared_global")
                state = CollectionState(mw)
                self.assertFalse(rule(state))
                _grant(state, self.PLAYER, "Progressive Boost")
                self.assertTrue(rule(state))

    def test_usf_slots_need_two_copies(self):
        mw, rule = self._rule("N. Gin Labs", 4,
                              progressive_boost="shared_global")
        state = CollectionState(mw)
        _grant(state, self.PLAYER, "Progressive Boost")
        self.assertFalse(rule(state))
        _grant(state, self.PLAYER, "Progressive Boost")
        self.assertTrue(rule(state))

    def test_hard_stats_term_binds_only_when_stats_randomized(self):
        mw, rule = self._rule("Oxide Station", 6, shortcut_knowledge="hard")
        self.assertTrue(rule(CollectionState(mw)))
        mw, rule = self._rule("Oxide Station", 6, shortcut_knowledge="hard",
                              progressive_stats="shared_global")
        state = CollectionState(mw)
        self.assertFalse(rule(state))
        _grant(state, self.PLAYER, *STAT_CHAINS)
        self.assertTrue(rule(state))

    def test_tiger_temple_door_reads_itemsanity(self):
        mw, rule = self._rule("Tiger Temple", 5, shortcut_knowledge="medium")
        self.assertTrue(rule(CollectionState(mw)))
        mw, rule = self._rule("Tiger Temple", 5, shortcut_knowledge="medium",
                              itemsanity=True)
        state = CollectionState(mw)
        self.assertFalse(rule(state))
        _grant(state, self.PLAYER, TIGER_TEMPLE_DOOR_OPENERS[0])
        self.assertTrue(rule(state))

    def test_no_gate_slots_carry_no_rule(self):
        mw = _build(box_locations=True, shortcut_knowledge="hard",
                    progressive_boost="shared_global",
                    progressive_stats="shared_global", itemsanity=True)
        state = CollectionState(mw)
        for track, slot in EXPLICIT_NO_GATE:
            with self.subTest(track=track, slot=slot):
                name = ITEM_BOX_CLASS.location_name(track, slot)
                self.assertTrue(
                    mw.get_location(name, self.PLAYER).access_rule(state))


class TestBoxSeedClassification(unittest.TestCase):
    """Box seeds are the second logic reader of the capability chains
    (create_item's per-seed honest classification, the #145 pattern)."""
    PLAYER = 1

    def _pool(self, name, **options):
        mw = _build(**options)
        return [item for item in mw.itempool
                if item.player == self.PLAYER and item.name == name]

    def test_boost_progression_in_box_seeds_without_itemsanity(self):
        items = self._pool("Progressive Boost", box_locations=True,
                           progressive_boost="shared_global")
        self.assertTrue(items)
        self.assertTrue(all(item.advancement for item in items))

    def test_boost_progression_without_boxes_or_itemsanity(self):
        """No reader is optional any more: the USF finish gate (ruled
        2026-08-12) reads the boost chain on Hot Air Skyway's Trophy Race in
        every seed, so the upgrade no longer depends on this feature at all.
        The stat chains below still do."""
        items = self._pool("Progressive Boost",
                           progressive_boost="shared_global")
        self.assertTrue(items)
        self.assertTrue(all(item.advancement for item in items))

    def test_stats_progression_only_at_hard(self):
        for chain in STAT_CHAINS:
            with self.subTest(chain=chain):
                hard = self._pool(chain, box_locations=True,
                                  shortcut_knowledge="hard",
                                  progressive_stats="shared_global")
                self.assertTrue(hard)
                self.assertTrue(all(item.advancement for item in hard))
                medium = self._pool(chain, box_locations=True,
                                    shortcut_knowledge="medium",
                                    progressive_stats="shared_global")
                self.assertTrue(medium)
                self.assertFalse(any(item.advancement for item in medium))


class TestWireBlock(CTRTestBase):
    run_default_tests = False
    options = {"box_locations": True, "shortcut_knowledge": "medium"}

    def test_scalars(self):
        slot_data = self.world.fill_slot_data()
        self.assertTrue(slot_data["ctr_options"]["box_locations"])
        self.assertEqual(slot_data["ctr_options"]["shortcut_knowledge"], 1)

    def test_block_shape_and_liveness(self):
        block = self.world.fill_slot_data()["item_box_checks"]
        self.assertTrue(block["enabled"])
        self.assertEqual(set(block["locations"]),
                         {str(i) for i in range(18)})
        self.assertEqual(
            block["placement_counts"],
            {"0": 15, "1": 13, "2": 14, "3": 10, "4": 10, "5": 12, "6": 11,
             "7": 15, "8": 15, "9": 13, "10": 14, "11": 15, "12": 15,
             "13": 14, "14": 10, "15": 15, "16": 15, "17": 15})
        live = 0
        for lid, row in block["locations"].items():
            self.assertEqual(len(row), 15)
            live += sum(1 for c in row if c != -1)
            for c in row:
                self.assertTrue(c == -1 or c in
                                self.world.location_name_to_id.values())
        self.assertEqual(live, 236)   # medium tier
        # Polar Pass (LevelID 12) slot 9 is hard-tier: inert at medium.
        self.assertEqual(block["locations"]["12"][8], -1)
        # Crash Cove (LevelID 3): 10 placed, tail inert.
        self.assertEqual(block["locations"]["3"][10:], [-1] * 5)


class TestUTRestoresBoxOptions(unittest.TestCase):
    """The seed's box toggle, knowledge tier and stats mode now steer which
    locations exist and how their rules read, so UT must take them from the
    wire, not the tracking player's YAML."""
    PLAYER = 1

    def _restored(self, wire_ctr_options, **build_options):
        mw = _build(**build_options)
        world = mw.worlds[self.PLAYER]
        world._ut_restore_options({"ctr_options": wire_ctr_options,
                                   "warp_pad_unlock": {}, "podium_checks": {}})
        o = world.options
        return (o.box_locations.value, o.shortcut_knowledge.value,
                o.progressive_stats.value)

    def test_wire_overrides_local_yaml(self):
        self.assertEqual(
            self._restored({"box_locations": True, "shortcut_knowledge": 2,
                            "stats_mode": 1}),
            (1, 2, 1))
        self.assertEqual(
            self._restored({"box_locations": False, "shortcut_knowledge": 0,
                            "stats_mode": 0},
                           box_locations=True, shortcut_knowledge="hard",
                           progressive_stats="shared_global"),
            (0, 0, 0))

    def test_absent_keys_leave_local_values(self):
        self.assertEqual(
            self._restored({}, box_locations=True,
                           shortcut_knowledge="medium"),
            (1, 1, 0))


class TestBoxSeedGenerates(CTRTestBase):
    """End-to-end: a maximal box seed (hard tier, both packs, itemsanity)
    builds through all steps -- the harness runs generate_early through
    set_rules and the default tests fill the world."""
    options = {"box_locations": True, "shortcut_knowledge": "hard",
               "progressive_boost": "shared_global",
               "progressive_stats": "shared_global",
               "itemsanity": True}
