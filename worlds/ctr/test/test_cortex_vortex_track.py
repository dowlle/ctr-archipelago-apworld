"""Cortex Vortex as a full pad track (2026-09-13 contract).

Covers what the apworld owns: the option-off identity, the dropped-destination
draw and its eligibility, pad placement with and without destination shuffle,
removal of the dropped destination's checks, the stage 1 / stage 2 lifecycle,
the USF finish term, Gem Cup legs, lettersanity, the relic tier pool, the
`cortex_vortex_track` wire block and its Universal Tracker restore.

Most tests pin the dropped destination by presetting
`options._cortex_vortex_dropped` before generate_early -- the same path the
two-stage fill probe takes -- so each scenario names its destination instead of
depending on a seed's draw.
"""
import io
import json
import unittest
from unittest import mock

from BaseClasses import CollectionState
from NetUtils import convert_to_base_types
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld, cortex_vortex_track as cvt
from ..cortex_vortex_track import CORTEX_VORTEX, DESTINATION_ID
from ..relic_tiers import tier_location_pool

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
BOOST = "Progressive Boost"
ALL_DESTINATIONS = sorted(cvt.destination_table())

#: Destination LevelIDs used below, spelled out.
CRASH_COVE, HOT_AIR_SKYWAY, TIGER_TEMPLE = 3, 7, 4
SLIDE_COLISEUM, TURBO_TRACK = 16, 17
SKULL_ROCK = 21
RED_CUP, PURPLE_CUP = 100, 104


def _build(dropped=None, seed=1, steps=STEPS, **options):
    options.setdefault("cortex_vortex_track", True)
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    if dropped is not None:
        mw.worlds[PLAYER].options._cortex_vortex_dropped = dropped
    for step in steps:
        call_all(mw, step)
    return mw


def _names(mw):
    return {loc.name for loc in mw.get_locations(PLAYER)}


def _state(mw, boost=0, exclude=()):
    """Every item at a generous count, minus the boost chain and `exclude`."""
    state = CollectionState(mw)
    for item in mw.worlds[PLAYER]._item_data_by_name:
        if item == BOOST or item.startswith(f"{BOOST} (") or item in exclude:
            continue
        state.add_item(item, PLAYER, 99)
    if boost:
        state.add_item(BOOST, PLAYER, boost)
    return state


def _reach(mw, state, name):
    return state.can_reach(name, "Location", PLAYER)


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _ut_regen(wire, seed=99):
    mw = setup_multiworld(ctrAPWorld, (), seed=seed)
    mw.re_gen_passthrough = {ctrAPWorld.game: wire}
    mw.generation_is_fake = True
    for step in STEPS:
        call_all(mw, step)
    return mw


class TestOptionOff(unittest.TestCase):
    """With the option off nothing about the seed may change beyond the two
    unconditional wire facts: the current schema (16 since Hit Character) and
    the 0 scalar."""

    @classmethod
    def setUpClass(cls):
        cls.mw = _build(cortex_vortex_track=False)

    def test_no_cortex_vortex_pad_track_content(self):
        names = _names(self.mw)
        self.assertFalse({n for n in names if n.startswith(CORTEX_VORTEX)
                          and n != "Cortex Vortex: Reach 10 Wumpa"})
        with self.assertRaises(KeyError):
            self.mw.get_region(CORTEX_VORTEX, PLAYER)

    def test_wire_carries_only_the_scalar_and_schema(self):
        wire = _wire(self.mw)
        self.assertEqual(wire["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["schema_version"], 16)
        self.assertEqual(wire["ctr_options"]["cortex_vortex_track"], 0)
        self.assertNotIn("cortex_vortex_track", wire)
        self.assertNotIn(DESTINATION_ID, wire["warp_pad_map"].values())

    def test_the_draw_takes_no_random_number(self):
        world = self.mw.worlds[PLAYER]
        before = world.random.getstate()
        self.assertIsNone(cvt.draw_dropped_destination(world))
        self.assertEqual(world.random.getstate(), before)

    def test_relic_pool_is_the_eighteen_retail_names(self):
        options = self.mw.worlds[PLAYER].options
        for tier in ("Sapphire", "Gold", "Platinum"):
            pool = tier_location_pool(ctrAPWorld.location_name_to_id, tier, options)
            self.assertEqual(pool, tier_location_pool(
                ctrAPWorld.location_name_to_id, tier))
            self.assertEqual(len(pool), 18)
            self.assertNotIn(cvt.relic_name(tier), pool)

    def test_leg_pool_is_the_sixteen_trophy_tracks(self):
        mw = _build(cortex_vortex_track=False, randomize_gem_cup_tracks=True,
                    steps=("generate_early", "create_regions"))
        legs = {t for v in mw.worlds[PLAYER].gem_cup_legs.values() for t in v}
        self.assertNotIn(CORTEX_VORTEX, legs)


class TestEligibility(unittest.TestCase):
    def _eligible(self, **options):
        mw = _build(steps=(), **options)
        return cvt.eligible_dropped_destinations(mw.worlds[PLAYER])

    def test_defaults_allow_all_27_destinations(self):
        self.assertEqual(self._eligible(), ALL_DESTINATIONS)
        self.assertEqual(len(ALL_DESTINATIONS), 27)

    def test_pinned_gems_keep_every_cup(self):
        eligible = self._eligible(shuffle_gems=False)
        self.assertFalse([lid for lid in eligible if lid >= 100])

    def test_excluded_cups_keep_every_cup(self):
        eligible = self._eligible(include_gem_cups=False)
        self.assertFalse([lid for lid in eligible if lid >= 100])

    def test_excluded_arenas_keep_every_arena(self):
        eligible = self._eligible(include_battle_arenas=False)
        self.assertFalse({18, 19, 21, 23} & set(eligible))

    def test_comfort_guard_keeps_turbo_track(self):
        eligible = self._eligible(warppad_unlock_requirements="vanilla",
                                  shuffle_gems=False)
        self.assertNotIn(TURBO_TRACK, eligible)
        self.assertIn(SLIDE_COLISEUM, eligible)

    def test_a_custom_track_keeps_its_cup(self):
        from ..custom_tracks import BABY_T_PARK_EXAMPLE
        eligible = self._eligible(
            custom_tracks={"baby-t-park": dict(BABY_T_PARK_EXAMPLE)})
        self.assertNotIn(PURPLE_CUP, eligible)
        self.assertIn(RED_CUP, eligible)

    def test_supply_check_filters_and_falls_back(self):
        mw = _build(steps=())
        world = mw.worlds[PLAYER]
        with mock.patch.object(cvt, "_supply_feasible",
                               side_effect=lambda w, lid: lid != CRASH_COVE):
            self.assertNotIn(CRASH_COVE, cvt.eligible_dropped_destinations(world))
        with mock.patch.object(cvt, "_supply_feasible", return_value=False):
            self.assertEqual(cvt.eligible_dropped_destinations(world),
                             ALL_DESTINATIONS)

    def test_supply_check_leaves_no_trace(self):
        mw = _build(steps=())
        world = mw.worlds[PLAYER]
        self.assertTrue(cvt._supply_feasible(world, HOT_AIR_SKYWAY))
        self.assertFalse(hasattr(world.options, "_cortex_vortex_dropped"))
        self.assertFalse(hasattr(world.options, "_lettersanity_selected"))
        self.assertFalse(hasattr(world, "_ctr_relic_created"))

    def test_a_box_heavy_drop_that_overfills_the_seed_is_refused(self):
        """The rung sizer is the gate: a destination whose removal leaves it
        refusing the seed is not drawn while another one keeps it valid."""
        mw = _build(steps=())
        world = mw.worlds[PLAYER]
        from .. import rung_sizer
        real = rung_sizer.required_categories

        def fake(w):
            return 99 if w.options._cortex_vortex_dropped == HOT_AIR_SKYWAY else real(w)

        with mock.patch.object(rung_sizer, "required_categories", side_effect=fake):
            self.assertNotIn(HOT_AIR_SKYWAY,
                             cvt.eligible_dropped_destinations(world))

    def test_the_draw_stays_in_the_eligible_set_and_varies(self):
        seen = set()
        for seed in range(12):
            mw = _build(seed=seed, steps=("generate_early",), shuffle_gems=False,
                        include_battle_arenas=False)
            lid = mw.worlds[PLAYER].options._cortex_vortex_dropped
            self.assertLess(lid, 18)
            seen.add(lid)
        self.assertGreater(len(seen), 4)

    def test_a_preset_ineligible_destination_is_refused(self):
        with self.assertRaises(Exception):
            _build(dropped=RED_CUP, shuffle_gems=False, steps=("generate_early",))


class TestPlacementWithoutShuffle(unittest.TestCase):
    """No destination shuffle: Cortex Vortex sits on the dropped pad."""

    @classmethod
    def setUpClass(cls):
        cls.mw = _build(dropped=HOT_AIR_SKYWAY, warp_pad_shuffle_categories=[],
                        wumpa_check="per_track", box_locations=True,
                        lettersanity="locations_only", letters_per_track=3)
        cls.world = cls.mw.worlds[PLAYER]
        cls.wire = _wire(cls.mw)

    def test_the_dropped_pad_loads_110_and_everything_else_is_identity(self):
        self.assertEqual(self.world.warp_pad_map,
                         {"Hot Air Skyway Warp Pad": DESTINATION_ID})
        for lid, dest in self.wire["warp_pad_map"].items():
            self.assertEqual(dest, DESTINATION_ID if lid == "7" else int(lid))
        self.assertFalse(self.wire["ctr_options"]["shuffle_warp_pads"])

    def test_the_pad_exit_leads_to_the_track(self):
        pad = self.mw.get_entrance("Hot Air Skyway Warp Pad", PLAYER)
        self.assertEqual(pad.connected_region.name, CORTEX_VORTEX)
        back = self.mw.get_entrance("Cortex Vortex -> Hub", PLAYER)
        self.assertEqual(back.connected_region.name, "Citadel City")

    def test_every_check_of_the_dropped_destination_is_removed(self):
        names = _names(self.mw)
        leftovers = {n for n in names if n.startswith("Hot Air Skyway:")}
        self.assertEqual(leftovers, set())
        self.assertNotIn("7", self.wire["podium_checks"]["locations"])
        self.assertNotIn("7", self.wire["wumpa_checks"]["retail_tracks"])
        self.assertNotIn("7", self.wire["lettersanity_checks"]["locations"])
        self.assertEqual(set(self.wire["item_box_checks"]["locations"]["7"]), {-1})

    def test_the_track_has_its_retail_shaped_checks(self):
        names = _names(self.mw)
        for name in (cvt.TROPHY_NAME, cvt.CTR_TOKEN_NAME,
                     "Cortex Vortex: Held 1st", "Cortex Vortex: Finish on Podium",
                     "Cortex Vortex: Reach 10 Wumpa", "Cortex Vortex: Letter C",
                     "Cortex Vortex: Letter T", "Cortex Vortex: Letter R"):
            self.assertIn(name, names)
        self.assertNotIn("Cortex Vortex: Relic Race Perfect", names)
        self.assertNotIn(35026005, ctrAPWorld.location_name_to_id.values())

    def test_spoiler_names_the_dropped_destination_and_the_pad(self):
        buf = io.StringIO()
        self.world.write_spoiler(buf)
        text = buf.getvalue()
        self.assertIn("CTR Cortex Vortex track (Tester1): Hot Air Skyway "
                      "(destination 7) has no pad this seed", text)
        self.assertIn("Hot Air Skyway Warp Pad: loads Cortex Vortex", text)


class TestPlacementWithShuffle(unittest.TestCase):
    def test_merged_shuffle_runs_over_the_survivors_plus_110(self):
        for seed in range(4):
            with self.subTest(seed=seed):
                mw = _build(dropped=RED_CUP, seed=seed,
                            warp_pad_shuffle_categories=["tracks", "crystals", "cups"],
                            warp_pad_shuffle_grouping="merged")
                values = sorted(_wire(mw)["warp_pad_map"].values())
                expected = sorted([lid for lid in ALL_DESTINATIONS if lid != RED_CUP]
                                  + list(range(24, 28)) + [20, 22] + [DESTINATION_ID])
                self.assertEqual(values, expected)
                self.assertNotIn("Red Gem Cup: Gem", _names(mw))

    def test_per_category_keeps_110_in_the_dropped_category(self):
        mw = _build(dropped=SKULL_ROCK, warp_pad_shuffle_categories=["tracks", "crystals"],
                    warp_pad_shuffle_grouping="per_category")
        wire = _wire(mw)["warp_pad_map"]
        crystal_values = {wire[str(lid)] for lid in (18, 19, 21, 23)}
        self.assertIn(DESTINATION_ID, crystal_values)
        self.assertNotIn(SKULL_ROCK, wire.values())
        self.assertNotIn("Skull Rock: Crystal Bonus Round", _names(mw))

    def test_vanilla_unlock_trial_drop_keeps_the_physical_pad_gate(self):
        mw = _build(dropped=SLIDE_COLISEUM, warppad_unlock_requirements="vanilla",
                    sapphire_relic_count=18)
        self.assertEqual(mw.worlds[PLAYER].warp_pad_map.get("Slide Coliseum Warp Pad"),
                         DESTINATION_ID)
        full = _state(mw)
        poor = _state(mw, exclude={"Sapphire Relic"})
        poor.add_item("Sapphire Relic", PLAYER, 9)
        self.assertTrue(_reach(mw, full, cvt.TROPHY_NAME))
        self.assertFalse(_reach(mw, poor, cvt.TROPHY_NAME))


class TestLifecycle(unittest.TestCase):
    """Stage 1 opens the Trophy Race; stage 2 (keyed to the destination) opens
    the Time Trials and the CTR Token Challenge."""

    def test_stage_two_gates_the_relic_and_token_checks(self):
        found = False
        for seed in range(1, 12):
            mw = _build(seed=seed, two_stage_density="full")
            world = mw.worlds[PLAYER]
            concrete = world.warp_pad_unlock_stage2_concrete.get(CORTEX_VORTEX)
            if concrete is None or concrete[0] in ("AnyCtrToken", "AnyRelic", "AnyGem"):
                continue
            item, count = concrete
            pad = next(p for p, d in world.warp_pad_map.items() if d == DESTINATION_ID)
            wire_s2 = _wire(mw)["warp_pad_unlock"][
                str(world.warp_pad_ids[pad]["level_id"])]["stage2"]
            self.assertNotEqual(wire_s2["type"], 0)
            opened = _state(mw)
            starved = _state(mw, exclude={item})
            starved.add_item(item, PLAYER, count - 1)
            if not _reach(mw, starved, cvt.TROPHY_NAME):
                continue  # stage 1 shares the item on this seed
            for name in (cvt.CTR_TOKEN_NAME, *(cvt.relic_name(t) for t in cvt.RELIC_TIER_LABELS)):
                if name in _names(mw):
                    self.assertTrue(_reach(mw, opened, name), name)
                    self.assertFalse(_reach(mw, starved, name), name)
            found = True
            break
        self.assertTrue(found, "no seed gave Cortex Vortex a real, separate stage 2")

    def test_the_relic_and_token_checks_need_the_trophy_race(self):
        mw = _build(dropped=CRASH_COVE, warp_pad_shuffle_categories=[])
        # Close the pad itself: every other item is held, the Trophy Race is
        # not reachable, so neither is anything behind it.
        pad = mw.get_entrance("Crash Cove Warp Pad", PLAYER)
        pad.access_rule = lambda state: False
        state = _state(mw)
        for name in (cvt.TROPHY_NAME, cvt.CTR_TOKEN_NAME):
            self.assertFalse(_reach(mw, state, name))


class TestUsfFinishTerm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mw = _build(dropped=CRASH_COVE, warp_pad_shuffle_categories=[],
                        progressive_boost="shared_global", wumpa_check="per_track",
                        lettersanity="locations_only", letters_per_track=3,
                        podium_held_fifth_rung=True, podium_any_position_rung=True,
                        sapphire_relic_count=18, gold_relic_count=18,
                        platinum_relic_count=18)

    def _at(self, boost, name):
        return _reach(self.mw, _state(self.mw, boost=boost), name)

    def test_finish_checks_need_two_boosts(self):
        finish = [cvt.TROPHY_NAME, cvt.CTR_TOKEN_NAME,
                  "Cortex Vortex: Finish on Podium",
                  "Cortex Vortex: Finish (Any Position)",
                  "Cortex Vortex: Letter C", "Cortex Vortex: Letter R"]
        finish += [cvt.relic_name(t) for t in cvt.RELIC_TIER_LABELS]
        for name in finish:
            with self.subTest(name=name):
                self.assertFalse(self._at(1, name))
                self.assertTrue(self._at(2, name))

    def test_mid_race_checks_stay_free(self):
        for name in ("Cortex Vortex: Held 1st", "Cortex Vortex: Held 3rd",
                     "Cortex Vortex: Held 5th", "Cortex Vortex: Reach 10 Wumpa"):
            with self.subTest(name=name):
                self.assertTrue(self._at(0, name))

    def test_the_contract_record_drives_it(self):
        from ..capability_contract import CONFIRMED_FINISH_BY_TRACK
        record = CONFIRMED_FINISH_BY_TRACK[CORTEX_VORTEX]
        self.assertEqual((record.boost_count, record.hard_shortcut_escape,
                          record.gate_held_first), (2, False, False))

    def test_hard_shortcut_knowledge_is_no_escape(self):
        mw = _build(dropped=CRASH_COVE, warp_pad_shuffle_categories=[],
                    progressive_boost="shared_global", shortcut_knowledge="hard")
        self.assertFalse(_reach(mw, _state(mw, boost=1), cvt.TROPHY_NAME))


class TestOxideVenueWithPadTrack(unittest.TestCase):
    def test_wumpa_code_exists_for_the_pad_track_even_on_the_retail_venue(self):
        mw = _build(dropped=CRASH_COVE, wumpa_check="per_track",
                    oxide_final_track="oxide_station")
        wire = _wire(mw)
        self.assertEqual(wire["oxide_final_venue"]["wumpa_location"], 35016121)
        self.assertEqual(wire["cortex_vortex_track"]["locations"]["wumpa"], 35016121)
        region = mw.get_region("Cortex Vortex: Wumpa", PLAYER)
        self.assertEqual({e.parent_region.name for e in region.entrances},
                         {CORTEX_VORTEX})

    def test_both_routes_reach_one_wumpa_identity(self):
        mw = _build(dropped=CRASH_COVE, wumpa_check="per_track",
                    oxide_final_track="cortex_vortex")
        region = mw.get_region("Cortex Vortex: Wumpa", PLAYER)
        self.assertEqual({e.parent_region.name for e in region.entrances},
                         {CORTEX_VORTEX, "N. Oxide Garage"})

    def test_the_venue_finish_is_not_bound_to_the_pad_racer_lock(self):
        """Oxide's Final Challenge starts in the garage; the racer locked on the
        pad that carries the pad track must not be demanded for it."""
        checked = 0
        for seed in range(1, 40):
            mw = _build(seed=seed, progressive_boost="per_character",
                        racer_locked_pads=26, oxide_goal="101_percent",
                        oxide_final_challenge_relic_count=1)
            world = mw.worlds[PLAYER]
            pad = next(p for p, d in world.warp_pad_map.items() if d == DESTINATION_ID)
            racer = world.ctr_racer_locks.get(pad)
            if racer is None:
                continue
            state = _state(mw, exclude={racer})
            start = world.ctr_starting_character
            from ..progressive_capability import boost_item_name
            state.add_item(boost_item_name(start), PLAYER, 2)
            self.assertTrue(_reach(mw, state, "N. Oxide Garage: N. Oxide's Final Challenge"))
            checked += 1
            break
        self.assertEqual(checked, 1, "no seed locked the pad carrying Cortex Vortex")


class TestGemCupLegs(unittest.TestCase):
    OPTIONS = dict(randomize_gem_cup_tracks=True, progressive_boost="shared_global",
                   wumpa_check="per_track")

    def test_the_dropped_track_is_never_a_leg_and_cortex_vortex_can_be(self):
        legged = 0
        for seed in range(20):
            mw = _build(dropped=TIGER_TEMPLE, seed=seed,
                        steps=("generate_early", "create_regions"), **self.OPTIONS)
            flat = [t for v in mw.worlds[PLAYER].gem_cup_legs_table.values() for t in v]
            self.assertNotIn("Tiger Temple", flat)
            legged += CORTEX_VORTEX in flat
        self.assertGreater(legged, 0)

    def test_a_cup_that_legs_it_reaches_its_podium_and_wumpa_and_needs_usf(self):
        for seed in range(40):
            mw = _build(dropped=TIGER_TEMPLE, seed=seed, **self.OPTIONS)
            world = mw.worlds[PLAYER]
            cups = [c for c, legs in world.gem_cup_legs.items() if CORTEX_VORTEX in legs]
            if cups:
                break
        else:
            self.fail("no seed legged Cortex Vortex")
        cup = cups[0]
        for region in ("Cortex Vortex: Podium", "Cortex Vortex: Wumpa"):
            sources = {e.parent_region.name
                       for e in mw.get_region(region, PLAYER).entrances}
            self.assertIn(cup, sources, region)
        gem = f"{cup}: Gem"
        self.assertFalse(_reach(mw, _state(mw, boost=1), gem))
        self.assertTrue(_reach(mw, _state(mw, boost=2), gem))
        wire = _wire(mw)
        cup_lid = {"Red Gem Cup": "100", "Green Gem Cup": "101", "Blue Gem Cup": "102",
                   "Yellow Gem Cup": "103", "Purple Gem Cup": "104"}[cup]
        self.assertIn(DESTINATION_ID, wire["gem_cup_legs"][cup_lid])
        self.assertNotIn(TIGER_TEMPLE, [x for v in wire["gem_cup_legs"].values() for x in v])


class TestLettersanity(unittest.TestCase):
    def test_locations_and_items(self):
        mw = _build(dropped=CRASH_COVE, lettersanity="locations_and_items",
                    letters_per_track=2)
        world = mw.worlds[PLAYER]
        chosen = world.options._lettersanity_selected[CORTEX_VORTEX]
        self.assertEqual(len(chosen), 2)
        names = _names(mw)
        for letter in cvt.LETTERS:
            self.assertEqual(cvt.letter_location_name(letter) in names, letter in chosen)
        pool = [item.name for item in mw.itempool]
        for letter in cvt.LETTERS:
            self.assertEqual(pool.count(cvt.letter_item_name(letter)), int(letter in chosen))
        self.assertFalse([n for n in pool if n.endswith("(Crash Cove)")])
        self.assertFalse([n for n in names if n.startswith("Crash Cove: Letter")])
        missing = cvt.letter_item_name(chosen[0])
        self.assertTrue(_reach(mw, _state(mw), cvt.CTR_TOKEN_NAME))
        self.assertFalse(_reach(mw, _state(mw, exclude={missing}), cvt.CTR_TOKEN_NAME))
        self.assertFalse(_reach(mw, _state(mw, exclude={missing}),
                                cvt.letter_location_name(chosen[0])))

    def test_items_only(self):
        mw = _build(dropped=SKULL_ROCK, lettersanity="items_only")
        names = _names(mw)
        self.assertFalse([n for n in names if n.startswith("Cortex Vortex: Letter")])
        pool = [item.name for item in mw.itempool]
        for letter in cvt.LETTERS:
            self.assertEqual(pool.count(cvt.letter_item_name(letter)), 1)
        self.assertFalse(_reach(mw, _state(mw, exclude={cvt.letter_item_name("T")}),
                                cvt.CTR_TOKEN_NAME))
        block = _wire(mw)["cortex_vortex_track"]
        self.assertEqual(block["locations"]["letters"], [-1, -1, -1])
        self.assertEqual(block["letter_items"], [35010200, 35010201, 35010202])

    def test_dropping_tiger_temple_keeps_its_itemsanity_door_rule_quiet(self):
        mw = _build(dropped=TIGER_TEMPLE, lettersanity="locations_and_items",
                    itemsanity=True)
        self.assertNotIn("Tiger Temple: CTR Token Challenge", _names(mw))


class TestRelicPool(unittest.TestCase):
    def test_a_dropped_track_hands_its_slot_to_cortex_vortex(self):
        mw = _build(dropped=HOT_AIR_SKYWAY, steps=())
        options = mw.worlds[PLAYER].options
        pool = tier_location_pool(ctrAPWorld.location_name_to_id, "Gold", options)
        self.assertEqual(len(pool), 18)
        self.assertIn("Cortex Vortex: Gold Time Trial", pool)
        self.assertNotIn("Hot Air Skyway: Gold Time Trial", pool)

    def test_a_dropped_arena_widens_the_pool_to_19(self):
        mw = _build(dropped=SKULL_ROCK, steps=())
        options = mw.worlds[PLAYER].options
        self.assertEqual(len(tier_location_pool(
            ctrAPWorld.location_name_to_id, "Sapphire", options)), 19)

    def test_created_counts_are_unchanged_and_the_wire_lists_its_codes(self):
        mw = _build(dropped=HOT_AIR_SKYWAY, sapphire_relic_count=18,
                    gold_relic_count=18, platinum_relic_count=18)
        world = mw.worlds[PLAYER]
        self.assertEqual(world._ctr_relic_created,
                         {"Sapphire Relic": 18, "Gold Relic": 18, "Platinum Relic": 18})
        wire = _wire(mw)
        self.assertEqual(wire["cortex_vortex_track"]["locations"]["relic"],
                         [35026001, 35026002, 35026003])
        self.assertIn(35026002, wire["ctr_options"]["relic_tier_locations"]["Gold Relic"])


class TestWireAndUniversalTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mw = _build(dropped=RED_CUP, seed=7, warppad_unlock_requirements="vanilla",
                        wumpa_check="per_track", lettersanity="locations_only",
                        letters_per_track=1, podium_held_fifth_rung=True,
                        podium_any_position_rung=True)
        cls.wire = cls.mw.worlds[PLAYER].fill_slot_data()

    def test_block_shape(self):
        block = json.loads(json.dumps(self.wire))["cortex_vortex_track"]
        self.assertEqual(block["version"], 1)
        self.assertEqual(block["destination_id"], 110)
        self.assertEqual(block["host_level_id"], 13)
        self.assertEqual(block["dropped_destination"], RED_CUP)
        self.assertEqual(block["lev_sha256"], cvt.LEV_SHA256)
        self.assertEqual(block["vrm_sha256"], cvt.VRM_SHA256)
        self.assertEqual(block["locations"]["trophy"], 35026000)
        self.assertEqual(block["locations"]["ctr_token"], 35026004)
        self.assertEqual(block["locations"]["podium"], {
            "held_1st": 35026010, "held_3rd": 35026011, "held_5th": 35026012,
            "finish_podium": 35026013, "finish_any": 35026014})
        self.assertEqual(sorted(c for c in block["locations"]["letters"] if c != -1),
                         [c for c in block["locations"]["letters"] if c != -1])
        self.assertEqual(sum(c != -1 for c in block["locations"]["letters"]), 1)
        self.assertEqual(list(self.wire["warp_pad_map"].values()).count(110), 1)
        self.assertEqual(self.wire["warp_pad_map"]["100"], 110)

    def test_ut_regen_through_the_real_wire_pipeline(self):
        """Vanilla unlock mode derives include_gem_cups from pad gates it does
        not carry; the dropped cup must still prove the toggle on, or the
        tracker pins a Gem onto the dropped cup's absent location."""
        ut = _ut_regen(convert_to_base_types(self.wire))
        self.assertEqual(_names(ut), _names(self.mw))
        uw = ut.worlds[PLAYER]
        self.assertEqual(uw.options._cortex_vortex_dropped, RED_CUP)
        self.assertEqual(uw.options.include_gem_cups.value, 1)
        again = json.loads(json.dumps(uw.fill_slot_data()))
        original = json.loads(json.dumps(self.wire))
        for key in ("cortex_vortex_track", "warp_pad_map", "warp_pad_unlock",
                    "podium_checks", "lettersanity_checks", "wumpa_checks"):
            self.assertEqual(again[key], original[key], key)

    def test_ut_regen_pins_shuffle_legs_and_stage_two(self):
        mw = _build(seed=3, randomize_gem_cup_tracks=True, two_stage_density="full")
        wire = mw.worlds[PLAYER].fill_slot_data()
        ut = _ut_regen(convert_to_base_types(wire))
        uw, w = ut.worlds[PLAYER], mw.worlds[PLAYER]
        self.assertEqual(uw.gem_cup_legs, w.gem_cup_legs)
        self.assertEqual(uw.warp_pad_unlock_stage2_concrete,
                         w.warp_pad_unlock_stage2_concrete)
        self.assertEqual(_names(ut), _names(mw))

    def test_restore_refuses_a_foreign_block(self):
        base = json.loads(json.dumps(self.wire))
        for key, value in (("destination_id", 111), ("host_level_id", 6),
                           ("dropped_destination", 99), ("version", 2),
                           ("lev_sha256", "0" * 64)):
            bad = json.loads(json.dumps(base))
            bad["cortex_vortex_track"][key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    cvt.restore_from_wire(self.mw.worlds[PLAYER].options, bad)
        bad = json.loads(json.dumps(base))
        del bad["cortex_vortex_track"]
        with self.assertRaises(ValueError):
            cvt.restore_from_wire(self.mw.worlds[PLAYER].options, bad)

    def test_an_older_room_restores_the_option_off(self):
        mw = _build(cortex_vortex_track=False, steps=())
        options = mw.worlds[PLAYER].options
        options.cortex_vortex_track.value = 1
        cvt.restore_from_wire(options, {"ctr_options": {}})
        self.assertEqual(options.cortex_vortex_track.value, 0)


if __name__ == "__main__":
    unittest.main()
