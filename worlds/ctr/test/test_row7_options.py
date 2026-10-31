"""The flat YAML of one generator row 7: every option of plan section 2, and the
default that makes every YAML a plan."""
import logging
import unittest

from Options import OptionError

from .. import content_fixed, content_requirements
from ..Options import ctrAPOptions, CustomTracks, CupTracks, CortexVortexTrack, ap_ctr_option_groups
from ..custom_tracks import BABY_T_PARK_CURRENT
from .test_content_plan import make_world
from .test_content_plan_row3 import SHAPE  # noqa: F401, the module's inputs stay importable

#: Plan section 2, by table. `lap_completion_checks` arrives with row 8.
SECTION_2 = """
retail_tracks track_modes custom_tracks cortex_vortex_track required_entries
cup_count cup_tracks cup_custom_legs one_lap_cups crystal_challenge_count crystal_arenas
boss_garages boss_cups garage_requirement_level boss_track_shuffle boss_track_pool boss_opponent_shuffle
boss_character_pool boss_track_assignment boss_kit_shuffle boss_attack_assignment boss_attack_intensity
boss_loss_easing boss_weapon_pool oxide_attack_profile oxide_weapon_pool purple_cup_boss_gauntlet
oxide_goal oxide_1_optional bosses_required_goal gems_required_goal goal_wumpa oxide_final_challenge_unlock
oxide_final_challenge_relic_count oxide_final_track
pad_placement race_mode_order adventure_structure warppad_unlock_requirements requirement_weights two_stage_density
warp_pad_rules racer_locked_pads shuffle_keys shuffle_gems
podium_rungs relic_perfect_checks lettersanity letters_per_track cup_sweep_checks box_locations itemsanity
crystalsanity wumpa_check hit_character wumpa_shop_slots wumpa_shop_prices wumpa_shop_progression wumpa_shop_hints
item_pool start_inventory_from_pool trap_fill_percentage trap_weights wumpa_bundles reserve_top_up
progressive_starting_wumpa turbo_grant tizi_helper
starting_character character_unlocks remove_playable_oxide starting_stat_class penta_stats editable_stats
progressive_stats
progressive_boost progressive_boost_blue_fire logic_difficulty shortcut_knowledge
death_link death_link_send deathlink_amnesty
warp_pad_item_display ap_item_type_colors color_boxes_by_item spoiler_items race_type_selector tracker_pad_launch
""".split()
ROW_8 = {"lap_completion_checks"}
#: Plan section 2, what happens to every current option: the names that go.
RETIRED = """
content_pool pad_layout boss_track_allowlist boss_track_blocklist boss_character_allowlist boss_character_blocklist
boss_oxide_in_pool boss_powerup_blocklist oxide_powerup_blocklist boss_encounter_repeats
bossgarage_unlock_requirements include_gem_cups randomize_gem_cup_tracks include_battle_arenas include_arcade_arenas
slide_coliseum_races turbo_track_races warp_pad_shuffle_categories warp_pad_shuffle_grouping requirement_variety
podium_placement_checks podium_held_rungs podium_held_fifth_rung podium_finish_rungs podium_any_position_rung
sapphire_relic_count gold_relic_count platinum_relic_count
""".split()
DEFAULTS = dict(cup_count=5, cup_custom_legs=4, crystal_challenge_count=4, boss_cups=0, boss_garages=1,
                one_lap_cups=1, shuffle_keys=1, shuffle_gems=1, two_stage_density=4, wumpa_shop_slots=10)
GARAGE_POOL = ["Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway"]


def own_options():
    common = {"local_items", "non_local_items", "start_inventory", "start_hints", "start_location_hints",
              "exclude_locations", "priority_locations", "item_links", "plando_items", "progression_balancing",
              "accessibility"}
    return set(ctrAPOptions.type_hints) - common


class TestOptionSet(unittest.TestCase):
    def test_section_2_is_the_option_set(self):
        self.assertEqual(own_options(), set(SECTION_2))
        self.assertEqual(len(SECTION_2) + len(ROW_8), 89)

    def test_every_retired_name_is_gone(self):
        self.assertFalse(own_options() & set(RETIRED))

    def test_every_option_has_one_group(self):
        grouped = [cls for classes in ap_ctr_option_groups.values() for cls in classes]
        self.assertEqual(len(grouped), len(set(grouped)))
        hints = ctrAPOptions.type_hints
        self.assertEqual({cls for name, cls in hints.items() if name in SECTION_2} - {hints["start_inventory_from_pool"]},
                         set(grouped))

    def test_defaults_are_the_plan_table(self):
        for name, value in DEFAULTS.items():
            self.assertEqual(ctrAPOptions.type_hints[name].default, value, name)
        hints = ctrAPOptions.type_hints
        self.assertEqual(hints["pad_placement"].default, hints["pad_placement"].option_shuffle)
        self.assertEqual(hints["race_mode_order"].default, hints["race_mode_order"].option_fixed)
        self.assertEqual(hints["garage_requirement_level"].default, hints["garage_requirement_level"].option_high)
        self.assertEqual(CortexVortexTrack.default, CortexVortexTrack.option_off)
        self.assertEqual(CupTracks.default, CupTracks.option_random_no_repeats)
        self.assertEqual(set(hints["podium_rungs"].default), {"held_1st", "held_3rd", "finish_on_podium", "finish_any"})
        self.assertEqual(hints["track_modes"].default, {"default": ["trophy", "ctr", "relic"]})
        self.assertEqual(len(hints["boss_character_pool"].default), 15)
        self.assertEqual(len(hints["boss_weapon_pool"].default), 10)
        self.assertEqual(len(hints["oxide_weapon_pool"].default), 11)
        self.assertEqual(len(hints["crystal_arenas"].valid_keys), 7)
        self.assertEqual(len(hints["crystal_arenas"].default), 4)

    def test_cup_tracks_takes_the_word_random(self):
        self.assertEqual(CupTracks.from_any("random").value, CupTracks.option_random_repeats)
        self.assertEqual(CupTracks.from_any(False).value, CupTracks.option_off)

    def test_old_baby_t_park_mapping_is_refused(self):
        with self.assertRaisesRegex(OptionError, "Purple Gem Cup"):
            CustomTracks.from_any({"baby-t-park": dict(BABY_T_PARK_CURRENT, replaces="purple_gem_cup")})
        self.assertEqual(CustomTracks.from_any({}).value, [])


class TestDefaultSeed(unittest.TestCase):
    def test_no_content_settings_give_the_vanilla_shape(self):
        plan = make_world({}).ctr_content_plan
        kinds = [e["kind"] for e in plan["entries"]]
        self.assertEqual(kinds.count("track"), 18)
        self.assertEqual(kinds.count("cup"), 5)
        self.assertEqual(kinds.count("crystal"), 4)
        self.assertEqual(sum(p["entry_id"] is not None for p in plan["pads"] if p["kind"] == "normal"), 27)
        self.assertEqual(len(plan["encounters"]), 6)
        for entry in plan["entries"]:
            if entry["kind"] == "track":
                self.assertEqual(entry["modes"], ["trophy", "ctr", "relic"], entry["id"])
        self.assertEqual(plan["pad_requirements"]["mode"], "randomized")

    def test_cortex_vortex_states(self):
        plan = make_world({}).ctr_content_plan
        self.assertFalse(any(e.get("track_id") == "cortex_vortex" for e in plan["entries"] if e["kind"] == "track"))
        for seed in range(6):
            plan = make_world(dict(cortex_vortex_track="own_pad"), seed).ctr_content_plan
            self.assertTrue(any(e.get("track_id") == "cortex_vortex" for e in plan["entries"] if e["kind"] == "track"))

    def test_required_entries_refuse_cortex_vortex(self):
        with self.assertRaisesRegex(OptionError, "own_pad"):
            make_world(dict(required_entries=["Cortex Vortex"]))

    def test_required_entries_take_names(self):
        plan = make_world(dict(retail_tracks=GARAGE_POOL + ["Slide Coliseum"], cup_count=0, crystal_challenge_count=1,
                               required_entries=["Slide Coliseum", "Rocky Road"], boss_garages=False,
                               oxide_goal="disabled", gems_required_goal=1, wumpa_shop_slots=0,
                               item_pool=dict(base=dict(trophies=0, relics=dict(sapphire=0, gold=0),
                                                        tokens=dict(red=0, green=0, blue=0, yellow=0, purple=0))),
                               podium_rungs=[], character_unlocks=False, two_stage_density="off")).ctr_content_plan
        self.assertTrue(any(e["kind"] == "crystal" for e in plan["entries"]))

    def test_ctr_needs_trophy(self):
        with self.assertRaisesRegex(OptionError, "without trophy"):
            make_world(dict(track_modes={"default": ["ctr", "relic"]}))

    def test_a_track_name_replaces_default(self):
        plan = make_world(dict(track_modes={"Slide Coliseum": ["relic"], "Turbo Track": ["relic"]})).ctr_content_plan
        modes = {t["display_name"]: t["modes"] for t in plan["tracks"]}
        self.assertEqual(modes["Slide Coliseum"], ["relic"])
        self.assertEqual(modes["Crash Cove"], ["trophy", "ctr", "relic"])

    def test_every_single_rung_set_generates(self):
        for rung in ctrAPOptions.type_hints["podium_rungs"].valid_keys:
            plan = make_world(dict(podium_rungs=[rung], item_pool=dict(base=dict(relics=dict(sapphire=4, gold=4))))).ctr_content_plan
            self.assertEqual(len(plan["track_checks"]["podium_rungs"]), 1)


class TestBossPools(unittest.TestCase):
    def test_four_boss_cups_need_no_track_each(self):
        world = make_world(dict(boss_cups=4, boss_track_shuffle=True, boss_track_pool=GARAGE_POOL))
        plan = world.ctr_content_plan
        self.assertEqual(plan["bosses"]["cups"], [0, 1, 2, 3])
        legs = {leg["track_id"] for e in plan["entries"] if e["kind"] == "boss_cup" for leg in e["legs"]}
        self.assertEqual(len(legs), 4)

    def test_a_boss_cup_needs_four_tracks(self):
        with self.assertRaisesRegex(OptionError, "boss_track_pool"):
            make_world(dict(boss_cups=1, boss_track_shuffle=True, boss_track_pool=GARAGE_POOL[:3]))

    def test_boss_races_need_their_own_tracks(self):
        with self.assertRaisesRegex(OptionError, "boss_track_pool"):
            make_world(dict(boss_track_shuffle=True, boss_track_pool=GARAGE_POOL[:3]))

    def test_the_pool_is_ignored_with_the_switch_off(self):
        plan = make_world(dict(boss_track_pool=GARAGE_POOL[:1])).ctr_content_plan
        self.assertEqual(len(plan["encounters"]), 6)

    def test_pool_takes_cortex_vortex(self):
        names = {}
        for seed in range(8):
            world = make_world(dict(boss_track_shuffle=True, cortex_vortex_track="in_pool",
                                    boss_track_pool=GARAGE_POOL[:3] + ["Cortex Vortex"]), seed)
            names.update(world.options._boss_track_venues)
        self.assertIn("Cortex Vortex", names.values())

    def test_listing_oxide_lets_him_be_a_boss(self):
        pool = ["Nitros Oxide", "Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura", "Neo Cortex"]
        plan = make_world(dict(boss_opponent_shuffle=True, boss_character_pool=pool)).ctr_content_plan
        self.assertTrue(plan["bosses"]["oxide_in_pool"])
        plan = make_world(dict(boss_opponent_shuffle=True, boss_character_pool=pool[1:])).ctr_content_plan
        self.assertFalse(plan["bosses"]["oxide_in_pool"])


class TestQuietOutput(unittest.TestCase):
    def test_settings_with_no_effect_print_nothing(self):
        options = dict(boss_track_pool=GARAGE_POOL, boss_weapon_pool=["bomb"], oxide_weapon_pool=["bomb"],
                       boss_character_pool=["Polar"], boss_loss_easing=False, boss_attack_intensity="mayhem",
                       editable_stats="global", progressive_stats="shared_global", penta_stats="pal",
                       racer_locked_pads=3, character_unlocks=False, remove_playable_oxide=True,
                       letters_per_track=1, warppad_unlock_requirements="vanilla",
                       requirement_weights=dict(Key=50), death_link_send=["mask_grab"])
        with self.assertNoLogs(level=logging.INFO):
            make_world(options, stop_before="create_regions")


class TestFirstKeyPath(unittest.TestCase):
    def test_four_open_checks_hold_four_trophies(self):
        pads = [(0, [0], False), (0, [0], False), (1, [0], False), (3, [0], False)]
        self.assertEqual(content_fixed.first_key_path(pads), ["Trophy"] * 4)

    def test_the_ladder_needs_a_fifth_check(self):
        pads = [(0, [0], False), (0, [0], False), (1, [0], False), (3, [0], False)]
        self.assertIsNone(content_fixed.first_key_path(pads, 0, True))
        self.assertEqual(content_fixed.first_key_path(pads[:3] + [(0, [0], True)], 10, True).count("boost"), 1)

    def test_a_start_of_one_check_does_not_fit(self):
        self.assertIsNone(content_fixed.first_key_path([(0, [1], True), (0, [0], False), (1, [0], False)], 10))

    def test_a_boost_gated_pad_costs_a_check(self):
        pads = [(0, [0], False), (0, [0], False), (1, [1], False), (3, [0], False)]
        self.assertIsNone(content_fixed.first_key_path(pads))

    def test_the_shop_joins_once_a_track_pays(self):
        arenas = [(0, [0], False), (0, [0], False)]
        self.assertIsNone(content_fixed.first_key_path(arenas, 10))
        self.assertIsNotNone(content_fixed.first_key_path(arenas[:1] + [(0, [0], True)], 10))

    def test_vanilla_redraw_seats_the_path(self):
        world = make_world(dict(warppad_unlock_requirements="vanilla", shuffle_keys=False, podium_rungs=[],
                                progressive_boost="shared_global"), 2, stop_before="fill")
        self.assertEqual(world.ctr_first_key_path.count("Trophy"), content_fixed.FIRST_KEY_TROPHIES)
        self.assertGreaterEqual(sum(loc.item is not None and loc.item.name == "Trophy" and loc.address is not None
                                    for loc in world.multiworld.get_locations(world.player)), 4)

    def test_redraws_stay_a_draw(self):
        self.assertGreater(content_requirements.FIRST_KEY_REDRAWS, content_requirements.PLACEMENT_REDRAWS)
