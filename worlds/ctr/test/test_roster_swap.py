"""The roster swap (ruled 2026-10-30): with random bosses the slots change out
with the bosses, and the chaos Final Challenge race. Rules: Rulebook Characters
and stats, open question 1; Goal and N. Oxide, open question 1."""
import copy
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_bosses, content_global_checks, content_plan, hit_character
from ..Options import OxideFinalTrack, final_chaos, final_on_cortex
from .test_content_bosses import boss_options
from .test_content_plan import make_world

ROO, PAPU, JOE, PINSTRIPE, OXIDE = 10, 9, 11, 8, 15
CRASH, CORTEX = 0, 2
TROPY, PENTA, FAKE = 12, 13, 14
RETAIL = dict(hit_character.BOSS_WIN_OPPONENTS)


def swapped(*garages, final=OXIDE):
    return {35011100: garages[0], 35011101: garages[1], 35011102: garages[2], 35011103: garages[3],
            35011104: final, 35011105: final}


class TestSwapTriggers(unittest.TestCase):
    def test_the_retail_table_is_the_retail_triggers(self):
        self.assertEqual(hit_character.unlock_triggers_for(RETAIL), hit_character.UNLOCK_TRIGGERS)

    def test_stefs_example_crash_takes_hub_1(self):
        table = swapped(CRASH, PAPU, JOE, PINSTRIPE)
        triggers = hit_character.unlock_triggers_for(table)
        self.assertEqual(hit_character.boss_codes(table, CRASH), (35011100,))
        self.assertEqual(triggers[ROO], ((), "boss"))
        self.assertNotIn(ROO, hit_character.fallback_guests(set(table), hit_character.CONTENT_PLAN_FALLBACK_KEYS, triggers))

    def test_roo_on_another_garage_waits_for_that_garage(self):
        table = swapped(CRASH, ROO, JOE, PINSTRIPE)
        self.assertEqual(hit_character.unlock_triggers_for(table)[ROO], ((35011101,), "boss"))

    def test_a_drawn_guest_waits_for_its_garage_not_its_track(self):
        table = swapped(TROPY, PAPU, JOE, PINSTRIPE)
        self.assertEqual(hit_character.unlock_triggers_for(table)[TROPY], ((35011100,), "boss"))

    def test_a_guest_drawn_nowhere_keeps_track_wins_and_keys(self):
        table = swapped(CRASH, PAPU, JOE, PINSTRIPE)
        triggers = hit_character.unlock_triggers_for(table)
        self.assertEqual(triggers[PENTA], hit_character.UNLOCK_TRIGGERS[PENTA])
        keys = hit_character.fallback_guests({35011100}, hit_character.CONTENT_PLAN_FALLBACK_KEYS, triggers)
        self.assertEqual(keys[PENTA], 2)
        self.assertNotIn(ROO, keys)

    def test_oxide_displaced_races_from_the_start(self):
        table = swapped(ROO, PAPU, JOE, PINSTRIPE, final=CRASH)
        triggers = hit_character.unlock_triggers_for(table)
        self.assertEqual(triggers[OXIDE], ((), "boss"))
        self.assertNotIn(OXIDE, hit_character.fallback_guests(set(table), hit_character.CONTENT_PLAN_FALLBACK_KEYS, triggers))

    def test_oxide_disabled_races_from_the_start(self):
        # Fixes 2026-11-02: his codes are raced nowhere, so they seat nobody
        # and the fixed Key fallback goes, as for any original boss.
        seats = swapped(CRASH, PAPU, JOE, PINSTRIPE, final=-1)
        created = {35011100, 35011101, 35011102, 35011103}
        triggers = hit_character.unlock_triggers_for(seats)
        self.assertEqual(triggers[OXIDE], ((), "boss"))
        self.assertNotIn(OXIDE, hit_character.fallback_guests(created, hit_character.CONTENT_PLAN_FALLBACK_KEYS,
                                                              triggers))

    def test_oxide_disabled_without_random_bosses_keeps_his_keys(self):
        keys = hit_character.fallback_guests({35011100, 35011101, 35011102, 35011103},
                                             hit_character.CONTENT_PLAN_FALLBACK_KEYS,
                                             hit_character.unlock_triggers_for(RETAIL))
        self.assertEqual(keys[OXIDE], 4)

    def test_bosses_off_keeps_the_key_table(self):
        keys = hit_character.fallback_guests(set(), hit_character.CONTENT_PLAN_FALLBACK_KEYS,
                                             hit_character.unlock_triggers_for(RETAIL))
        self.assertEqual((keys[ROO], keys[PAPU], keys[JOE], keys[PINSTRIPE]), (1, 2, 3, 4))


class TestReferenceDraw(unittest.TestCase):
    ORDER = list(range(16))

    def eligible(self, held=(), joined=()):
        return [(i < 8 and i not in held) or i in joined for i in range(16)]

    def test_a_held_default_is_out_while_the_field_can_fill(self):
        eligible = self.eligible(held=(CRASH,), joined=(ROO,))
        field, _ = hit_character.reference_draw(self.ORDER, 7, eligible, [False] * 16, 7, [15, 15, 15])
        self.assertEqual(len(field), 7)
        self.assertNotIn(CRASH, field)
        self.assertIn(ROO, field)

    def test_a_short_field_runs_with_fewer_karts(self):
        # Five held defaults: two free and three extras fill five of seven
        # seats. No held racer takes a seat early (fixes 2026-11-02).
        held = (0, 1, 2, 3, 4)
        eligible = self.eligible(held=held, joined=(ROO, PAPU, JOE, PINSTRIPE, OXIDE))
        field, _ = hit_character.reference_draw(self.ORDER, 7, eligible, [False] * 16, 7, [15, 15, 15])
        self.assertEqual(len(set(field)), 5)
        self.assertEqual(sum(1 for i in field if i >= 8), 3)
        self.assertFalse(any(i in held for i in field))

    def test_nobody_held_is_todays_draw(self):
        eligible = self.eligible()
        field, _ = hit_character.reference_draw(self.ORDER, 7, eligible, [False] * 16, 7, [15, 15, 15])
        self.assertEqual(sorted(field), [0, 1, 2, 3, 4, 5, 6])


def swap_seed(seed, **extra):
    return make_world(boss_options(boss_opponent_shuffle=True, hit_character=True, **extra), seed=seed)


class TestSwapOnSeeds(unittest.TestCase):
    def test_every_seed_keeps_the_rule(self):
        seen_default = seen_swap = 0
        for seed in range(30):
            world = swap_seed(seed)
            plan = world.ctr_content_plan
            self.assertTrue(content_plan.validate(plan))
            table = content_bosses.identity(plan)
            block = world.ctr_hit_character_encounters
            raced = {table[code] for code in content_bosses.BOSS_CODES}
            for boss in hit_character.ORIGINAL_BOSS_IDS:
                entry = block["unlock_triggers"][str(boss)]
                if boss in table.values():
                    self.assertEqual(entry["any_of"], list(hit_character.boss_codes(table, boss)))
                    continue
                seen_swap += 1
                self.assertEqual(entry, dict(kind="boss", any_of=[]))
            seen_default += any(cid < 8 for cid in raced)
        self.assertGreater(seen_default, 5)
        self.assertGreater(seen_swap, 5)

    def test_a_held_default_needs_its_garage_and_a_displaced_boss_does_not(self):
        for seed in range(60):
            world = swap_seed(seed)
            plan = world.ctr_content_plan
            table = content_bosses.identity(plan)
            held = [cid for code, cid in table.items() if code in content_bosses.BOSS_CODES and cid < 8]
            free = [boss for boss in hit_character.ORIGINAL_BOSS_IDS if boss not in table.values()]
            if not held or not free:
                continue
            state = CollectionState(world.multiworld)
            target = held[0]
            name = hit_character.HIT_CHARACTER_CLASS.location_name(target)
            location = world.multiworld.get_location(name, world.player)
            for item in world.multiworld.get_items():
                if item.player == world.player and item.advancement and item.name != "Key":
                    state.collect(item, prevent_sweep=True)
            garages = {code: world.multiworld.get_location(content_bosses.CTR_LOCATION_ID_NAMES[code], world.player)
                       for code in hit_character.boss_codes(table, target)}
            if not any(g.can_reach(state) for g in garages.values()):
                self.assertFalse(location.can_reach(state))
                return
        self.fail("no seed held a default racer behind a shut garage")

    def test_oxide_disabled_races_from_the_start_on_seeds(self):
        for seed in range(6):
            world = swap_seed(seed, oxide_goal="disabled", gems_required_goal=2)
            plan = world.ctr_content_plan
            self.assertNotEqual(content_bosses.identity(plan), RETAIL)
            if OXIDE in content_bosses.seats(plan).values():
                continue  # drawn for a garage: he waits for it
            entry = world.ctr_hit_character_encounters["unlock_triggers"][str(OXIDE)]
            self.assertEqual(entry, dict(kind="boss", any_of=[]))
            self.assertNotIn(OXIDE, world.ctr_hit_character_fallback)
            # The wire's bosses table is unchanged: his codes still name him.
            self.assertEqual(world.ctr_hit_character_encounters["bosses"]["35011105"], OXIDE)
            state = CollectionState(world.multiworld)
            location = world.multiworld.get_location(hit_character.HIT_CHARACTER_CLASS.location_name(OXIDE),
                                                     world.player)
            for item in world.multiworld.get_items():
                if item.player == world.player and item.advancement and item.name != "Key":
                    state.collect(item, prevent_sweep=True)
            self.assertTrue(location.can_reach(state))

    def test_seats_keep_the_retail_table_without_random_bosses(self):
        plan = make_world(boss_options(oxide_goal="disabled", gems_required_goal=2)).ctr_content_plan
        self.assertEqual(content_bosses.seats(plan), RETAIL)

    def test_the_block_round_trips_through_the_tracker_check(self):
        world = swap_seed(4)
        slot = dict(hit_character_encounters=world.ctr_hit_character_encounters,
                    ctr_options=dict(hit_character=True))
        content_global_checks.check_encounter_block(world.ctr_content_plan, slot)
        block = copy.deepcopy(world.ctr_hit_character_encounters)
        displaced = next((b for b in hit_character.ORIGINAL_BOSS_IDS
                          if not block["unlock_triggers"][str(b)]["any_of"]), None)
        if displaced is not None:
            block["unlock_triggers"][str(displaced)]["fallback_keys"] = hit_character.CONTENT_PLAN_FALLBACK_KEYS[displaced]
            with self.assertRaises(OptionError):
                content_global_checks.check_encounter_block(world.ctr_content_plan,
                                                            dict(slot, hit_character_encounters=block))


class TestChaosOption(unittest.TestCase):
    def test_four_choices_with_the_default_kept(self):
        self.assertEqual(OxideFinalTrack.default, 0)
        self.assertEqual({k: v for k, v in OxideFinalTrack.options.items()},
                         dict(cortex_vortex=0, oxide_station=1, vanilla_chaos=2, vortex_chaos=3))

    def test_venue_and_chaos_read_apart(self):
        for value, cortex, chaos in ((0, True, False), (1, False, False), (2, False, True), (3, True, True)):
            option = OxideFinalTrack(value)
            self.assertEqual((final_on_cortex(option), final_chaos(option)), (cortex, chaos))


class TestChaosPlan(unittest.TestCase):
    def test_off_adds_nothing(self):
        plan = make_world(boss_options(oxide_final_track="cortex_vortex")).ctr_content_plan
        self.assertNotIn(content_bosses.CHAOS_KEY, plan["bosses"])
        self.assertNotIn(content_bosses.CHAOS_FEATURE, plan["required_features"])
        self.assertEqual(content_bosses.chaos_lineup(plan), ())

    def test_retail_five_on_each_venue(self):
        for value, venue in (("vortex_chaos", "cortex_vortex"), ("vanilla_chaos", "retail:13")):
            world = make_world(boss_options(oxide_final_track=value))
            plan = world.ctr_content_plan
            self.assertTrue(content_plan.validate(plan))
            self.assertIs(plan["bosses"]["final_chaos"], True)
            self.assertIn(content_bosses.CHAOS_FEATURE, plan["required_features"])
            self.assertEqual(content_bosses.chaos_lineup(plan), (OXIDE, ROO, PAPU, JOE, PINSTRIPE))
            entries = {e["id"]: e for e in plan["entries"]}
            self.assertEqual(entries[plan["encounters"][-1]["entry_id"]]["track_id"], venue)

    def test_challenge_stays_one_rival_and_the_same_checks(self):
        plain = make_world(boss_options(oxide_final_track="cortex_vortex"), seed=2).ctr_content_plan
        chaos = make_world(boss_options(oxide_final_track="vortex_chaos"), seed=2).ctr_content_plan
        self.assertEqual(plain["encounters"], chaos["encounters"])
        self.assertEqual(plain["checks"], chaos["checks"])
        self.assertEqual(plain["goal"], chaos["goal"])

    def test_the_drawn_five_with_oxide_randomized(self):
        pool = list(content_bosses._be().POOL_NAMES)
        for seed in range(20):
            plan = make_world(boss_options(boss_opponent_shuffle=True, boss_character_pool=pool,
                                           oxide_final_track="vortex_chaos"), seed=seed).ctr_content_plan
            lineup = content_bosses.chaos_lineup(plan)
            self.assertEqual(len(set(lineup)), 5)
            self.assertNotEqual(lineup[0], OXIDE)  # the boss selection rule of his garage

    def test_oxide_disabled_ignores_chaos_silently(self):
        plan = make_world(boss_options(oxide_final_track="vortex_chaos", oxide_goal="disabled",
                                       gems_required_goal=2)).ctr_content_plan
        self.assertNotIn(content_bosses.CHAOS_KEY, plan["bosses"])

    def test_validate_refuses_a_false_key(self):
        plan = copy.deepcopy(make_world(boss_options(oxide_final_track="vortex_chaos")).ctr_content_plan)
        plan["bosses"]["final_chaos"] = False
        with self.assertRaises(OptionError):
            content_plan.validate(plan)

    def test_tracker_restores_the_choice(self):
        for value in ("vanilla_chaos", "vortex_chaos"):
            plan = make_world(boss_options(oxide_final_track=value)).ctr_content_plan
            tracker = make_world(boss_options(oxide_final_track="cortex_vortex"))
            content_bosses.restore_options(tracker, plan)
            self.assertEqual(tracker.options.oxide_final_track.current_key, value)

    def test_spoiler_names_the_five(self):
        plan = make_world(boss_options(oxide_final_track="vortex_chaos")).ctr_content_plan
        self.assertIn("Final Challenge: chaos race against Nitros Oxide, Ripper Roo, Papu Papu, Komodo Joe, Pinstripe",
                      content_bosses.spoiler_lines(plan))
