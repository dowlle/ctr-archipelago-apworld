"""Boss opponent and kit shuffle on content plans (job J11, decisions 7 and 9)."""
import copy
import json
import unittest

from Options import OptionError

from .. import boss_encounters, boss_track_shuffle, content_bosses, content_plan, hit_character
from .test_content_bosses import boss_options, encounters
from .test_content_ctr_first import assert_complete, full_generation
from .test_content_plan import make_world
from .test_track_checks import refused

ALL = dict(boss_opponent_shuffle=True, boss_kit_shuffle=True, boss_oxide_in_pool=True,
           oxide_attack_profile="all_compatible", hit_character=True, wumpa_shop_slots=0)


def shuffle_options(**overrides):
    options = boss_options(**ALL)
    options.update(overrides)
    return options


def opponents(plan):
    """[(encounter id, opponent record)] in encounter order."""
    entries = {e["id"]: e for e in plan["entries"]}
    return [(enc["id"], entries[enc["entry_id"]]["opponent"]) for enc in plan["encounters"]]


def venue_of(plan, garage):
    entries = {e["id"]: e for e in plan["entries"]}
    return entries[content_bosses.entry_id(garage)]["track_id"]


class TestContentBossShuffle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = make_world(shuffle_options(), seed=20261029)
        cls.plan = cls.world.ctr_content_plan

    def test_record_and_feature(self):
        record = self.plan["bosses"]
        self.assertEqual({k: record[k] for k in content_bosses.ENCOUNTER_KEYS},
                         dict(opponent_shuffle=True, oxide_in_pool=True, kit_shuffle=True, gauntlet=False,
                              kit=dict(assignment="mixed_loadouts", intensity="standard", loss_easing=True),
                              oxide_attack_profile="all_compatible", track_assignment="independent_track"))
        features = self.plan["required_features"]
        self.assertLess(features.index("boss_encounters_v1"), features.index("boss_opponents_v1"))

    def test_racers_are_distinct_and_oxide_races_a_drawn_racer(self):
        rows = opponents(self.plan)
        garages = [o["character_id"] for _e, o in rows[:4]]
        final = rows[4][1]["character_id"]
        self.assertEqual(len(set(garages + [final])), 5)
        self.assertNotEqual(final, 15)
        self.assertEqual(rows[4][1], rows[5][1])

    def test_composed_kits(self):
        rows = opponents(self.plan)
        weapons = set()
        for g, (_eid, opponent) in enumerate(rows[:4]):
            self.assertEqual(opponent["attack_profile"], "composed")
            schedule = opponent["schedule"]
            self.assertEqual(len(schedule), 5)
            venue = venue_of(self.plan, g)
            name = next(n for n, lid in boss_track_shuffle.VENUE_LEVEL_IDS.items() if f"retail:{lid}" == venue)
            self.assertEqual(tuple(s[0] for s in schedule),
                             boss_track_shuffle.translated_schedule(content_bosses.GARAGES[g][1], name))
            self.assertFalse(any(boss_encounters.family_of(s[2]) == "super_engine" for s in schedule))
            weapons.add(tuple(s[2] for s in schedule))
        self.assertEqual(len(weapons), 4)
        final = rows[4][1]["schedule"]
        self.assertEqual(tuple(s[0] for s in final), boss_encounters.OXIDE_CHECKPOINTS)

    def test_hit_block_follows_the_draw(self):
        wire = self.world.fill_slot_data()
        block = wire["hit_character_encounters"]
        self.assertEqual({int(k): v for k, v in block["bosses"].items()}, content_bosses.identity(self.plan))
        rows = opponents(self.plan)
        drawn = {o["character_id"] for _e, o in rows}
        triggers = block["unlock_triggers"]
        for boss, keys in ((10, 1), (9, 2), (11, 3), (8, 4)):
            if boss not in drawn:
                self.assertEqual(triggers[str(boss)].get("fallback_keys"), keys)
        hits = {c["location"] - hit_character.HIT_CHARACTER_CODE_BASE: c for c in self.plan["checks"]
                if c["kind"] == "hit"}
        for eid, opponent in rows:
            boss_routes = [r for r in hits[opponent["character_id"]]["routes"] if r["mode"] == "boss_race"]
            self.assertIn(eid, [r["encounter_id"] for r in boss_routes])
        for retail in (10, 9, 11, 8):
            if retail not in drawn:
                self.assertFalse([r for r in hits[retail]["routes"] if r["mode"] == "boss_race"])

    def test_spoiler_lines(self):
        lines = content_bosses.spoiler_lines(self.plan)
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("Ripper Roo Garage: "))
        self.assertIn("kit: ", lines[0])

    def test_validate_and_tracker_round_trip(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertTrue(content_plan.validate(wire["content_plan"]))
        tracker = make_world(dict(boss_opponent_shuffle=False, boss_character_blocklist=["Crash Bandicoot"]),
                             seed=999, passthrough=wire)
        o = tracker.options
        self.assertEqual((o.boss_opponent_shuffle.value, o.boss_kit_shuffle.value, o.boss_oxide_in_pool.value,
                          o.oxide_attack_profile.value), (1, 1, 1, 1))
        self.assertEqual(o.boss_character_blocklist.value, set())
        self.assertEqual(tracker.fill_slot_data(), wire)

    def test_forged_plans_refuse(self):
        def opp(p, g):
            entries = {e["id"]: e for e in p["entries"]}
            return entries[content_bosses.entry_id(g)]["opponent"]

        def final(p):
            entries = {e["id"]: e for e in p["entries"]}
            return [entries[content_bosses.entry_id(4, i)]["opponent"] for i in (0, 1)]

        def both_final(change):
            def apply(p):
                for record in final(p):
                    change(record)
            return apply

        cases = dict(
            repeat=lambda p: opp(p, 1).update(character_id=opp(p, 0)["character_id"]),
            out_of_pool=lambda p: opp(p, 0).update(character_id=16),
            final_is_oxide=both_final(lambda r: r.update(character_id=15)),
            final_is_garage_racer=lambda p: [r.update(character_id=opp(p, 2)["character_id"]) for r in final(p)],
            finals_differ=lambda p: final(p)[1].update(character_id=final(p)[1]["character_id"] ^ 1),
            checkpoint=lambda p: opp(p, 0)["schedule"][1].__setitem__(0, opp(p, 0)["schedule"][1][0] + 1),
            cooldown=lambda p: opp(p, 0)["schedule"][0].__setitem__(4, 200),
            uncertified=lambda p: opp(p, 0)["schedule"][0].__setitem__(1, 7),
            super_engine=lambda p: opp(p, 0)["schedule"][0].__setitem__(2, 0x0D),
            never_attacks=lambda p: [s.__setitem__(2, 0x0F) for s in opp(p, 0)["schedule"]],
            short_schedule=lambda p: opp(p, 0)["schedule"].pop(),
            inherited=lambda p: (opp(p, 0).pop("schedule"), opp(p, 0).update(attack_profile="inherited")),
            same_kit=lambda p: opp(p, 1).update(schedule=[[a] + b[1:] for a, b in zip(
                [s[0] for s in opp(p, 1)["schedule"]], opp(p, 0)["schedule"])]),
            final_checkpoint=both_final(lambda r: r["schedule"][3].__setitem__(0, 48)),
            final_inherited=both_final(lambda r: (r.pop("schedule"), r.update(attack_profile="inherited"))),
            kit_null=lambda p: p["bosses"].update(kit=None),
            kit_intensity=lambda p: p["bosses"]["kit"].update(intensity="mayhem"),
            no_kit_shuffle=lambda p: p["bosses"].update(kit_shuffle=False),
            oxide_in_pool_off=lambda p: p["bosses"].update(oxide_in_pool=False),
            opponent_off=lambda p: p["bosses"].update(opponent_shuffle=False),
            profile_retail=lambda p: p["bosses"].update(oxide_attack_profile="retail"),
            home_track=lambda p: p["bosses"].update(track_assignment="character_home_track"),
            drop_key=lambda p: p["bosses"].pop("kit"),
            drop_feature=lambda p: p["required_features"].remove("boss_opponents_v1"),
            driving=lambda p: opp(p, 3).update(driving_profile="boss"),
            slot=lambda p: opp(p, 3).update(slot=2),
        )
        for name, change in cases.items():
            with self.subTest(name):
                plan = copy.deepcopy(self.plan)
                change(plan)
                self.assertTrue(refused(plan))

    def test_forged_hit_block_refuses(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        wire["hit_character_encounters"]["bosses"]["35011100"] = 10
        with self.assertRaises(OptionError):
            make_world({}, seed=999, passthrough=wire)


class TestContentBossShuffleDraws(unittest.TestCase):
    def test_off_keeps_the_record(self):
        plan = make_world(boss_options(wumpa_shop_slots=0), seed=5).ctr_content_plan
        self.assertEqual(set(plan["bosses"]), set(content_bosses.RECORD_KEYS))
        self.assertNotIn("boss_opponents_v1", plan["required_features"])
        for _eid, opponent in opponents(plan):
            self.assertEqual(set(opponent), {"role", "slot", "character_id", "driving_profile", "attack_profile"})
            self.assertEqual(opponent["attack_profile"], "inherited")

    def test_off_options_draw_nothing(self):
        """Subordinate options without their switch change nothing."""
        base = make_world(boss_options(wumpa_shop_slots=0), seed=5).ctr_content_plan
        noisy = make_world(boss_options(wumpa_shop_slots=0, boss_character_blocklist=["Polar"],
                                        boss_attack_intensity="mayhem"),
                           seed=5).ctr_content_plan
        self.assertEqual(noisy, base)

    def test_home_track_pairing(self):
        world = make_world(shuffle_options(boss_track_shuffle=True), seed=11)
        plan = world.ctr_content_plan
        self.assertEqual(plan["bosses"]["track_assignment"], "character_home_track")
        by_id = {cid: name for name, cid in boss_encounters.OPPONENT_ENGINE_ID.items()}
        for g, (_eid, opponent) in enumerate(opponents(plan)[:4]):
            home = boss_encounters.HOME_TRACK[by_id[opponent["character_id"]]]
            self.assertEqual(venue_of(plan, g), content_bosses.track_id_of(home))
            self.assertIn(content_bosses.track_id_of(home), {t["id"] for t in plan["tracks"]})
        self.assertTrue(content_plan.validate(plan))

    def test_custom_venue_maps_the_kit_on_its_restart_points(self):
        """independent_track with Baby T Park (35 restart points) and Cortex
        Vortex (255) in the plan: a garage on either maps its kit there."""
        seen = set()
        for seed in range(1, 80):
            options = shuffle_options(boss_track_shuffle=True, boss_track_assignment="independent_track")
            options["content_pool"]["tracks"]["cortex_vortex"] = True
            try:
                plan = make_world(options, seed=seed).ctr_content_plan
            except OptionError:
                continue
            for g, (_eid, opponent) in enumerate(opponents(plan)[:4]):
                venue = venue_of(plan, g)
                points = {"custom/baby-t-park/1.0.2": 35, "cortex_vortex": 255}.get(venue)
                if points:
                    self.assertEqual(tuple(s[0] for s in opponent["schedule"]),
                                     content_bosses.mapped_checkpoints(g, points))
                    seen.add(venue)
            if len(seen) == 2:
                break
        self.assertEqual(seen, {"custom/baby-t-park/1.0.2", "cortex_vortex"})

    def test_signature_profiles_and_intensity(self):
        world = make_world(shuffle_options(boss_attack_assignment="signature_profiles",
                                           boss_attack_intensity="mayhem", boss_loss_easing=False), seed=3)
        plan = world.ctr_content_plan
        self.assertEqual(plan["bosses"]["kit"], dict(assignment="signature_profiles", intensity="mayhem",
                                                     loss_easing=False))
        profiles = set()
        for _eid, opponent in opponents(plan)[:4]:
            rows = [tuple(s[1:]) for s in opponent["schedule"]]
            match = [key for key, sig in boss_encounters.SIGNATURES.items()
                     if rows == [(t, w, p, boss_encounters.scale_cooldown(c, 3), j) for w, t, p, c, j in sig]]
            self.assertEqual(len(match), 1)
            profiles.add(match[0])
        self.assertEqual(len(profiles), 4)
        self.assertTrue(content_plan.validate(plan))

    def test_opponent_only_keeps_inherited_attacks(self):
        plan = make_world(boss_options(boss_opponent_shuffle=True, wumpa_shop_slots=0), seed=3).ctr_content_plan
        self.assertEqual(plan["bosses"]["kit"], None)
        rows = opponents(plan)
        self.assertTrue(all(o["attack_profile"] == "inherited" and "schedule" not in o for _e, o in rows))
        self.assertTrue(all(o["character_id"] == 15 for _e, o in rows[4:]))
        self.assertTrue(content_plan.validate(plan))

    def test_oxide_profile_only(self):
        plan = make_world(boss_options(oxide_attack_profile="all_compatible", wumpa_shop_slots=0),
                          seed=3).ctr_content_plan
        record = plan["bosses"]
        self.assertFalse(record["opponent_shuffle"] or record["kit_shuffle"])
        rows = opponents(plan)
        self.assertEqual([o["character_id"] for _e, o in rows], [10, 9, 11, 8, 15, 15])
        self.assertEqual(rows[4][1]["attack_profile"], "composed")
        self.assertTrue(content_plan.validate(plan))

    def test_refusals(self):
        off = boss_options(boss_kit_shuffle=True, wumpa_shop_slots=0, oxide_goal="disabled", gems_required_goal=2)
        off["content_pool"]["bosses"]["enabled"] = False
        with self.assertRaises(OptionError):
            make_world(off, seed=1)
        small = shuffle_options(boss_character_allowlist=["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura"])
        with self.assertRaises(OptionError) as caught:
            make_world(small, seed=1)
        self.assertIn("never repeat", str(caught.exception))

    def test_oxide_disabled_draws_no_final_racer(self):
        plan = make_world(shuffle_options(oxide_goal="disabled", gems_required_goal=2), seed=4).ctr_content_plan
        record = plan["bosses"]
        self.assertEqual(record["oxide_attack_profile"], "retail")
        self.assertEqual(len(plan["encounters"]), 4)
        self.assertTrue(content_plan.validate(plan))

    def test_full_generation_accessibility_full(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                world, wire = full_generation(shuffle_options(accessibility="full", boss_track_shuffle=seed != 2),
                                              seed)
                assert_complete(self, world)
                self.assertTrue(content_plan.validate(wire["content_plan"]))


class TestContentAll030(unittest.TestCase):
    """All four J11 features on together."""

    def options(self, seed):
        options = shuffle_options(adventure_structure="ctr_first", wumpa_shop_slots=4,
                                  wumpa_shop_progression=["allowed", "excluded"][seed % 2], goal_wumpa=500,
                                  boss_track_shuffle=bool(seed % 2), accessibility="full",
                                  itemsanity=seed % 3 == 0, lettersanity=seed % 2,
                                  progressive_boost=["off", "shared_global", "per_character"][seed % 3],
                                  podium_placement_checks=True)
        options["pad_layout"]["stages"] = "two"
        return options

    def test_full_generation_and_tracker(self):
        done = 0
        for seed in range(1, 12):
            try:
                world, wire = full_generation(self.options(seed), seed)
            except OptionError:
                continue
            with self.subTest(seed=seed):
                assert_complete(self, world)
                plan = wire["content_plan"]
                self.assertTrue(content_plan.validate(plan))
                self.assertEqual(plan["required_features"][-5:],
                                 ["ctr_first_v1", "boss_opponents_v1", "wumpa_shop_v1", "wumpa_goal_v1", "pad_client_v1"])
                tracker = make_world({}, seed=999, passthrough=wire)
                self.assertEqual(tracker.fill_slot_data(), wire)
                # The regenerated world reasons like the room: the same
                # checks in logic for the same items.
                names = sorted(item.name for item in world.multiworld.itempool if item.player == 1
                               and item.advancement)[::3]
                for held in ([], ["Key"] * 4, ["Key"] * 4 + names):
                    reach = []
                    for each in (world, tracker):
                        from BaseClasses import CollectionState
                        state = CollectionState(each.multiworld)
                        for name in held:
                            state.collect(each.create_item(name), True)
                        state.sweep_for_advancements(
                            locations=[loc for loc in each.multiworld.get_locations(1) if loc.address is None])
                        reach.append(sorted(loc.address for loc in each.multiworld.get_locations(1)
                                            if loc.address is not None and loc.can_reach(state)))
                    self.assertEqual(reach[0], reach[1])
                done += 1
        self.assertGreaterEqual(done, 4)


if __name__ == "__main__":
    unittest.main()
