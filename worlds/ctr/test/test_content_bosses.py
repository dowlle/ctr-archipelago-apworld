"""Boss garages on content plans (#133 PR 6): encounter records, venues,
requirements, checks, goals, logic, Hit Character and the Universal Tracker
restore."""
import copy
import json
import unittest

from BaseClasses import CollectionState, LocationProgressType
from Options import OptionError

from .. import boss_track_shuffle, content_bosses, content_plan, hit_character
from .test_content_plan import make_world, profile_options

BOSS_NAMES = ["Ripper Roo Garage: Boss Race", "Papu Papu Garage: Boss Race", "Komodo Joe Garage: Boss Race",
              "Pinstripe Garage: Boss Race", "N. Oxide Garage: N. Oxide's Challenge",
              "N. Oxide Garage: N. Oxide's Final Challenge"]


def boss_options(**overrides):
    options = profile_options()
    pool = options["content_pool"]
    pool["bosses"] = dict(enabled=True)
    pool["tracks"]["modes"] = ["trophy", "ctr", "relic"]
    options["item_pool"]["base"]["trophies"] = 16
    options["item_pool"]["base"]["relics"] = dict(sapphire=6, gold=4, platinum=2)
    options.update(oxide_goal="any_percent", bosses_required_goal=0, gems_required_goal=0)
    options.update(overrides)
    return options


def varied(seed):
    """A varied boss profile for the seed."""
    goals = ["any_percent", "101_percent", "none", "disabled"]
    options = boss_options(oxide_goal=goals[seed % 4], bosses_required_goal=seed % 5,
                           gems_required_goal=[0, 1, 3, 5][(seed // 2) % 4],
                           boss_track_shuffle=seed % 3 != 0, boss_encounter_repeats=["disallow", "allow"][seed % 2],
                           oxide_final_track=["cortex_vortex", "oxide_station"][(seed // 3) % 2],
                           oxide_1_optional=["mandatory", "optional"][(seed // 5) % 2],
                           oxide_final_challenge_unlock=["sapphire_relics", "gold_relics", "platinum_relics",
                                                         "any_relic_type", "total_relics"][seed % 5],
                           oxide_final_challenge_relic_count=[1, 4, 12, 18, 30][(seed // 4) % 5])
    if goals[seed % 4] in ("none", "disabled") and options["bosses_required_goal"] == 0 \
            and options["gems_required_goal"] == 0:
        options["gems_required_goal"] = 2
    if seed % 6 == 5:
        options.update(progressive_boost="shared_global", hit_character=True)
    if seed % 7 == 3:
        options.update(progressive_boost="per_character", character_unlocks=True, racer_locked_pads=4,
                       itemsanity=True, hit_character=True)
    if seed % 4 == 1:
        options["content_pool"]["cups"] = dict(count=dict(min=1, max=3))
        options["content_pool"]["tracks"]["cortex_vortex"] = True
    return options


def encounters(plan):
    return plan["encounters"]


def collect_requirement(world, state, predicate):
    """Collect the items a garage requirement asks for (one family)."""
    by_code = {code: name for name, code in content_bosses.content_item_pool.ITEMS.items()}
    items = [predicate["item"]] if predicate["op"] == "count" else predicate["items"]
    for n in range(predicate["count"]):
        state.collect(world.create_item(by_code[items[n % len(items)]]), prevent_sweep=True)


class TestBossEncounters(unittest.TestCase):
    def test_retail_pairs_by_default(self):
        world = make_world(boss_options())
        plan = world.ctr_content_plan
        self.assertTrue(content_plan.validate(plan))
        self.assertEqual(plan["required_features"][-1], content_bosses.FEATURE)
        self.assertEqual(plan["bosses"], dict(oxide_goal=1, bosses_required=0, oxide_1_optional=False,
                                              oxide_final_unlock=0, oxide_final_count=6, track_shuffle=False,
                                              repeats=False, requirement_level="high"))
        entries = {e["id"]: e for e in plan["entries"]}
        venues = [entries[e["entry_id"]]["track_id"] for e in encounters(plan)]
        home = boss_track_shuffle.VENUE_LEVEL_IDS
        self.assertEqual(venues, [f"retail:{home[t]}" for t in ("Roo's Tubes", "Papu's Pyramid", "Dragon Mines",
                                                                 "Hot Air Skyway", "Oxide Station")] + ["cortex_vortex"])
        self.assertEqual([entries[e["entry_id"]]["opponent"]["character_id"] for e in encounters(plan)],
                         [10, 9, 11, 8, 15, 15])
        self.assertEqual([e["id"] for e in encounters(plan)],
                         [f"encounter/garage:{g}/0" for g in range(5)] + ["encounter/garage:4/1"])
        checks = {c["location"]: c for c in plan["checks"] if c["kind"] == content_bosses.KIND}
        self.assertEqual(sorted(checks), list(range(35011100, 35011106)))
        self.assertEqual([checks[c]["display_name"] for c in sorted(checks)], BOSS_NAMES)
        req = {r["id"]: r["predicate"] for r in plan["requirements"]}
        # The mixed-item roll (#133 PR 6b): one checked family per garage.
        for g in range(4):
            content_bosses.check_garage_requirement(req[f"boss:{g}"], plan["items"]["rows"], g)
        self.assertEqual(req["oxide:final"], dict(op="count", item=content_bosses.RELIC_ITEMS[0], count=6))
        self.assertNotIn("oxide:first", req)
        gates = {p["id"]: p["entrance_req"] for p in plan["pads"] if p["kind"] == "garage"}
        self.assertEqual(gates, {"garage:0": "free", "garage:1": "keys:1", "garage:2": "keys:2",
                                 "garage:3": "keys:3", "garage:4": "keys:4"})
        self.assertEqual(plan["goal"], dict(op="checked", locations=[35011104], count=1))
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["goal_oxide"], co["goal_bosses"], co["goal_gems"]), (1, 0, 0))
        # Venues raced nowhere else are trophy-only plan tracks.
        tracks = {t["id"]: t for t in plan["tracks"]}
        self.assertEqual(tracks["cortex_vortex"]["modes"], ["trophy"])

    def test_bosses_off_keeps_the_earlier_wire(self):
        world = make_world(profile_options())
        plan = world.ctr_content_plan
        self.assertNotIn("bosses", plan)
        self.assertEqual(plan["encounters"], [])
        self.assertTrue(all(p["entrance_req"] == "free" for p in plan["pads"] if p["kind"] == "garage"))
        self.assertEqual(plan["goal"]["op"], "distinct")
        self.assertNotIn(content_bosses.FEATURE, plan["required_features"])

    def test_oxide_disabled_keeps_four_garages(self):
        world = make_world(boss_options(oxide_goal="disabled", bosses_required_goal=4))
        plan = world.ctr_content_plan
        self.assertEqual(len(encounters(plan)), 4)
        self.assertEqual(plan["bosses"]["oxide_final_count"], 18)
        self.assertEqual(next(p for p in plan["pads"] if p["id"] == "garage:4")["entrance_req"], "free")
        self.assertEqual(plan["goal"], dict(op="checked", locations=list(content_bosses.BOSS_CODES), count=4))
        self.assertNotIn(35011104, {c["location"] for c in plan["checks"]})

    def test_goal_arms_and_companions(self):
        world = make_world(boss_options(oxide_goal="any_percent", bosses_required_goal=2, gems_required_goal=3))
        plan = world.ctr_content_plan
        gem = content_bosses.gem_term_of(plan["goal"])
        bosses = dict(op="checked", locations=list(content_bosses.BOSS_CODES), count=2)
        self.assertEqual(plan["goal"], dict(op="all", terms=[dict(op="checked", locations=[35011104], count=1),
                                                             bosses, gem]))
        req = {r["id"]: r["predicate"] for r in plan["requirements"]}
        self.assertEqual(req["oxide:first"], dict(op="all", terms=[bosses, gem]))
        self.assertEqual(req["oxide:final"]["terms"][:2], [bosses, gem])
        first = next(e for e in encounters(plan) if e["completion_location"] == 35011104)
        self.assertEqual(first["requirement_id"], "oxide:first")
        # 101_percent: the companions gate the Final Challenge only.
        world = make_world(boss_options(oxide_goal="101_percent", bosses_required_goal=1))
        plan = world.ctr_content_plan
        req = {r["id"]: r["predicate"] for r in plan["requirements"]}
        self.assertNotIn("oxide:first", req)
        self.assertEqual(req["oxide:final"]["op"], "all")
        self.assertEqual(plan["goal"]["terms"][0], dict(op="checked", locations=[35011105], count=1))
        # none: Oxide is optional, no companion gates either challenge.
        world = make_world(boss_options(oxide_goal="none", bosses_required_goal=3))
        req = {r["id"]: r["predicate"] for r in world.ctr_content_plan["requirements"]}
        self.assertEqual(req["oxide:final"]["op"], "count")
        self.assertEqual(world.ctr_content_plan["goal"],
                         dict(op="checked", locations=list(content_bosses.BOSS_CODES), count=3))

    def test_goal_location_is_excluded(self):
        for goal, name in (("any_percent", BOSS_NAMES[4]), ("101_percent", BOSS_NAMES[5])):
            world = make_world(boss_options(oxide_goal=goal))
            location = world.multiworld.get_location(name, 1)
            self.assertEqual(location.progress_type, LocationProgressType.EXCLUDED)

    def test_track_shuffle_draws_certified_venues(self):
        for seed in range(12):
            world = make_world(boss_options(boss_track_shuffle=True,
                                            boss_encounter_repeats="allow" if seed % 2 else "disallow"), seed=seed)
            plan = world.ctr_content_plan
            venues, final = content_bosses.plan_venues(plan)
            for g, track in venues.items():
                self.assertTrue(boss_track_shuffle.inherited_attack_certified(content_bosses.GARAGES[g][1], track))
            if seed % 2 == 0:
                self.assertEqual(len(set(venues.values())), 4)
            self.assertEqual(final, "Cortex Vortex")
            again = make_world(boss_options(boss_track_shuffle=True,
                                            boss_encounter_repeats="allow" if seed % 2 else "disallow"), seed=seed)
            self.assertEqual(again.ctr_content_plan, plan)

    def test_final_on_oxide_station(self):
        world = make_world(boss_options(oxide_final_track="oxide_station"))
        venues, final = content_bosses.plan_venues(world.ctr_content_plan)
        self.assertEqual(final, "Oxide Station")
        self.assertNotIn("cortex_vortex", {t["id"] for t in world.ctr_content_plan["tracks"]})

    def test_relic_modes_and_counts(self):
        cases = [("gold_relics", 30, dict(op="count", item=content_bosses.RELIC_ITEMS[1], count=4)),
                 ("platinum_relics", 1, dict(op="count", item=content_bosses.RELIC_ITEMS[2], count=1)),
                 ("total_relics", 30, dict(op="sum", items=list(content_bosses.RELIC_ITEMS), count=12)),
                 ("any_relic_type", 5, dict(op="any", terms=[dict(op="count", item=content_bosses.RELIC_ITEMS[0],
                                                                  count=5)])),
                 ("any_relic_type", 3, dict(op="any", terms=[dict(op="count", item=content_bosses.RELIC_ITEMS[t],
                                                                  count=3) for t in (0, 1)]))]
        for unlock, count, want in cases:
            with self.subTest(unlock=unlock, count=count):
                world = make_world(boss_options(oxide_final_challenge_unlock=unlock,
                                                oxide_final_challenge_relic_count=count))
                req = {r["id"]: r["predicate"] for r in world.ctr_content_plan["requirements"]}
                self.assertEqual(req["oxide:final"], want)
                self.assertEqual(world.ctr_content_plan["bosses"]["oxide_final_count"], want.get("count", count))

    def test_refusals(self):
        cases = [
            (profile_options() | dict(oxide_goal="any_percent"), "bosses.enabled: false"),
            (profile_options() | dict(boss_track_shuffle=True), "boss_track_shuffle needs"),
            (boss_options(oxide_goal="101_percent", oxide_1_optional="filler"), "filler"),
            (boss_options(oxide_goal="none"), "no goal"),
            (boss_options(), None),
        ]
        # PR 6b: a small Trophy pool no longer refuses; Trophy rolls need four.
        few = boss_options()
        few["item_pool"]["base"]["trophies"] = 3
        cases.append((few, None))
        level = boss_options()
        level["content_pool"]["bosses"]["requirement_level"] = "extreme"
        cases.append((level, "requirement_level must be one of"))
        none = boss_options(oxide_final_challenge_unlock="platinum_relics")
        none["item_pool"]["base"]["relics"] = dict(sapphire=6, gold=4, platinum=0)
        cases.append((none, "no base relic"))
        flag = profile_options()
        flag["content_pool"]["bosses"] = dict(enabled="yes")
        cases.append((flag, "must be true or false"))
        # Review finding 1: a ledger with no filler cannot hold the excluded
        # Oxide goal check; refused before fill (98 checks, 61 extra Trophies).
        tight = boss_options()
        tight["item_pool"]["extra"] = dict(trophies=61)
        cases.append((tight, "holds only filler"))
        loose = boss_options(oxide_goal="none", bosses_required_goal=1)
        loose["item_pool"]["extra"] = dict(trophies=61)
        cases.append((loose, None))
        for options, message in cases:
            with self.subTest(message=message):
                if message is None:
                    make_world(options)
                    continue
                with self.assertRaisesRegex(OptionError, message):
                    make_world(options)

    def test_boss_checks_carry_the_legacy_boost(self):
        world = make_world(boss_options(progressive_boost="shared_global", oxide_final_track="cortex_vortex"))
        checks = {c["location"]: c for c in world.ctr_content_plan["checks"] if c["kind"] == content_bosses.KIND}
        # First rank everywhere, USF on Hot Air Skyway, Oxide Station and Cortex Vortex.
        self.assertEqual([checks[c].get("boost") for c in sorted(checks)], [1, 1, 1, 2, 2, 2])
        world = make_world(boss_options(progressive_boost="shared_global", shortcut_knowledge="hard",
                                        logic_difficulty="hard"))
        checks = {c["location"]: c for c in world.ctr_content_plan["checks"] if c["kind"] == content_bosses.KIND}
        self.assertEqual(checks[35011104]["boost"], 1)

    def test_logic_garage_doors_and_goal(self):
        world = make_world(boss_options(oxide_goal="any_percent", bosses_required_goal=1))
        mw = world.multiworld
        state = CollectionState(mw)
        roo = mw.get_location(BOSS_NAMES[0], 1)
        papu = mw.get_location(BOSS_NAMES[1], 1)
        oxide = mw.get_location(BOSS_NAMES[4], 1)
        req = {r["id"]: r["predicate"] for r in world.ctr_content_plan["requirements"]}
        self.assertFalse(roo.can_reach(state))
        collect_requirement(world, state, req["boss:0"])
        self.assertTrue(roo.can_reach(state))
        collect_requirement(world, state, req["boss:1"])
        if req["boss:1"].get("item") != content_bosses.KEY_ITEM:
            self.assertFalse(papu.can_reach(state))  # Lost Ruins needs a Key
            state.collect(world.create_item("Key"), prevent_sweep=True)
        self.assertTrue(papu.can_reach(state))
        for _ in range(3):
            state.collect(world.create_item("Key"), prevent_sweep=True)
        # Four Keys, but the any_percent companion asks for one boss won.
        self.assertFalse(oxide.can_reach(state))
        state.sweep_for_advancements()
        self.assertTrue(oxide.can_reach(state))
        self.assertFalse(mw.completion_condition[1](CollectionState(mw)))
        all_state = mw.get_all_state(False)
        self.assertTrue(mw.completion_condition[1](all_state))

    def test_varied_profiles_generate_validate_and_restore(self):
        for seed in range(30):
            with self.subTest(seed=seed):
                world = make_world(varied(seed), seed=seed)
                plan = world.ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                coded = [loc for loc in world.multiworld.get_locations(1) if loc.address is not None]
                self.assertEqual(len(coded), len(plan["checks"]))
                wire = json.loads(json.dumps(world.fill_slot_data()))
                restored = make_world({}, passthrough=copy.deepcopy(wire))
                self.assertEqual(restored.ctr_content_plan, plan)
                self.assertEqual(json.loads(json.dumps(restored.fill_slot_data())), wire)
                self.assertEqual(restored.options.oxide_goal.value, plan["bosses"]["oxide_goal"])
                all_state = world.multiworld.get_all_state(False)
                for location in world.multiworld.get_locations(1):
                    self.assertTrue(location.can_reach(all_state), location.name)

    def test_forged_rooms_refuse(self):
        world = make_world(boss_options(boss_track_shuffle=True, bosses_required_goal=2, gems_required_goal=2))
        original = json.loads(json.dumps(world.fill_slot_data()))

        def entry(w, g):
            return next(e for e in w["content_plan"]["entries"] if e["id"] == f"entry/boss:{g}/0")

        def venue(w):
            entry(w, 0)["track_id"] = entry(w, 1)["track_id"]

        def opponent(w):
            entry(w, 0)["opponent"]["character_id"] = 3

        def kit(w):
            entry(w, 2)["opponent"]["attack_profile"] = "mixed"

        def requirement(w):
            next(r for r in w["content_plan"]["requirements"] if r["id"] == "boss:3")["predicate"]["count"] = 99

        def gate(w):
            next(p for p in w["content_plan"]["pads"] if p["id"] == "garage:2")["entrance_req"] = "free"

        def goal(w):
            w["content_plan"]["goal"]["terms"][1]["count"] = 1

        def record(w):
            w["content_plan"]["bosses"]["track_shuffle"] = False

        def drop(w):
            w["content_plan"]["encounters"].pop()

        def check(w):
            next(c for c in w["content_plan"]["checks"] if c["location"] == 35011100)["routes"][0]["award"] = "hit"

        def envelope(w):
            w["ctr_options"]["goal_bosses"] = 1

        def unfeature(w):
            w["content_plan"]["required_features"].remove(content_bosses.FEATURE)

        def no_record(w):
            del w["content_plan"]["bosses"]

        def final(w):
            entry(w, 4)["track_id"] = "cortex_vortex"

        def no_filler(w):
            # Review round 2: the excluded Oxide goal check needs a filler slot.
            items = w["content_plan"]["items"]
            row = next(r for r in items["rows"] if r["item"] == content_bosses.TROPHY_ITEM)
            row.update(extra=items["filler_count"], remaining=16 + items["filler_count"],
                       receipt_cap=16 + items["filler_count"])
            items.update(filler_count=0, trap_count=0)

        for mutate in (venue, opponent, kit, requirement, gate, goal, record, drop, check, envelope, unfeature,
                       no_record, final, no_filler):
            wire = copy.deepcopy(original)
            mutate(wire)
            with self.subTest(mutation=mutate.__name__), self.assertRaises((OptionError, ValueError)):
                make_world({}, passthrough=wire)


class TestBossHits(unittest.TestCase):
    def test_boss_guests_join_through_their_races(self):
        world = make_world(boss_options(hit_character=True))
        block = world.fill_slot_data()["hit_character_encounters"]
        fallback = {int(g) for g, e in block["unlock_triggers"].items() if "fallback_keys" in e}
        # The four bosses and Oxide join through their own races, not Keys.
        self.assertFalse(fallback & {8, 9, 10, 11, 15})
        self.assertEqual(world.ctr_hit_character_fallback, {g: k for g, k in hit_character.FALLBACK_KEYS.items()
                                                            if g in fallback})
        plan = world.ctr_content_plan
        hits = {c["location"] - hit_character.HIT_CHARACTER_CODE_BASE: c for c in plan["checks"] if c["kind"] == "hit"}
        for cid, codes in ((10, [35011100]), (15, [35011104, 35011105]), (0, [])):
            boss = [r for r in hits[cid]["routes"] if r["mode"] == content_bosses.MODE]
            self.assertEqual([r["encounter_id"] for r in boss],
                             [e["id"] for e in plan["encounters"] if e["completion_location"] in codes])
            self.assertTrue(all(r["award"] == "hit" for r in boss))

    def test_a_boss_is_hit_in_its_own_race(self):
        world = make_world(boss_options(hit_character=True))
        mw = world.multiworld
        state = CollectionState(mw)
        hit_roo = mw.get_location("Hit Ripper Roo", 1)
        req = {r["id"]: r["predicate"] for r in world.ctr_content_plan["requirements"]}
        collect_requirement(world, state, req["boss:0"])
        # Roo's garage is open with its requirement: his Hit check is in logic
        # through his boss race even before he joins the draw.
        self.assertTrue(hit_roo.can_reach(state))

    def test_bosses_off_keeps_the_content_plan_fallback(self):
        options = profile_options()
        options["hit_character"] = True
        world = make_world(options)
        self.assertEqual({g: world.ctr_hit_character_fallback[g] for g in (8, 9, 10, 11)},
                         {g: hit_character.CONTENT_PLAN_FALLBACK_KEYS[g] for g in (8, 9, 10, 11)})


class TestGarageRoll(unittest.TestCase):
    """The mixed-item garage roll (#133 PR 6b, design 2026-09-01)."""

    def test_bands_rise_with_depth_and_level(self):
        for supply in (1, 2, 5, 12, 16):
            for level in ("standard", "high", "very_high"):
                bands = [content_bosses.garage_band(level, d, supply) for d in range(4)]
                self.assertEqual(bands, sorted(bands), (level, supply))
                self.assertTrue(all(1 <= lo <= hi <= supply for lo, hi in bands))
            self.assertEqual(content_bosses.garage_band("chaotic", 0, supply), (1, supply))
        self.assertEqual(content_bosses.garage_band("very_high", 3, 5)[1], 4)  # one copy of margin

    def test_rolls_are_valid_never_free_and_vary(self):
        seen = set()
        for seed in range(40):
            options = boss_options()
            options["content_pool"]["bosses"]["requirement_level"] = content_bosses.LEVELS[seed % 4]
            world = make_world(options, seed=seed)
            plan = world.ctr_content_plan
            req = {r["id"]: r["predicate"] for r in plan["requirements"]}
            for g in range(4):
                pred = req[f"boss:{g}"]
                content_bosses.check_garage_requirement(pred, plan["items"]["rows"], g)
                if pred.get("item") == content_bosses.TROPHY_ITEM:
                    self.assertEqual(pred["count"], 4)
                if pred.get("item") == content_bosses.KEY_ITEM:
                    self.assertTrue(content_bosses.GARAGES[g][2] < pred["count"] <= 3)
                seen.add(json.dumps(pred, sort_keys=True))
        self.assertGreater(len(seen), 10)

    def test_forged_garage_requirements_refuse(self):
        rows = make_world(boss_options()).ctr_content_plan["items"]["rows"]
        trophy, key = content_bosses.TROPHY_ITEM, content_bosses.KEY_ITEM
        for pred, g in ((dict(op="count", item=trophy, count=8), 0),
                        (dict(op="count", item=key, count=1), 2),
                        (dict(op="count", item=key, count=4), 0),
                        (dict(op="always"), 1),
                        (dict(op="sum", items=[35010001], count=1), 1),
                        (dict(op="count", item=trophy, count=4, extra=1), 0)):
            with self.subTest(pred=pred), self.assertRaises(OptionError):
                content_bosses.check_garage_requirement(pred, rows, g)



class TestCustomBossVenues(unittest.TestCase):
    """Custom tracks and Cortex Vortex as boss venues (#133 PR 6b)."""
    BTP = "custom/baby-t-park/1.0.2"

    def drawn(self, options, seeds=range(12)):
        out = set()
        for seed in seeds:
            world = make_world(copy.deepcopy(options), seed=seed)
            plan = world.ctr_content_plan
            self.assertTrue(content_plan.validate(plan))
            entries = {e["id"]: e for e in plan["entries"]}
            out |= {entries[e["entry_id"]]["track_id"] for e in plan["encounters"][:4]}
            wire = json.loads(json.dumps(world.fill_slot_data()))
            restored = make_world({}, passthrough=copy.deepcopy(wire))
            self.assertEqual(restored.ctr_content_plan, plan)
        return out

    def test_custom_tracks_and_cortex_vortex_join_the_draw(self):
        options = boss_options(boss_track_shuffle=True)
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        drawn = self.drawn(options)
        self.assertIn(self.BTP, drawn)
        self.assertIn("cortex_vortex", drawn)

    def test_a_package_without_navigation_or_count_stays_out(self):
        options = boss_options(boss_track_shuffle=True)
        del options["content_pool"]["tracks"]["custom"][0]["capabilities"]["checkpoints"]
        self.assertNotIn(self.BTP, self.drawn(options))

    def test_an_allowlist_keeps_custom_tracks_out(self):
        options = boss_options(boss_track_shuffle=True, boss_encounter_repeats="allow",
                               boss_track_allowlist=["Crash Cove", "Dingo Canyon"])
        ids = boss_track_shuffle.VENUE_LEVEL_IDS
        self.assertTrue(self.drawn(options, range(4)) <= {f"retail:{ids['Crash Cove']}", f"retail:{ids['Dingo Canyon']}"})

    def test_off_keeps_the_retail_pairs(self):
        options = boss_options()
        options["content_pool"]["tracks"]["cortex_vortex"] = True
        self.assertNotIn(self.BTP, self.drawn(options, range(3)))

    def test_schedule_fits_by_count(self):
        for key, *_ in boss_track_shuffle.GARAGES:
            self.assertTrue(boss_track_shuffle.schedule_fits(key, 35))
            self.assertTrue(boss_track_shuffle.schedule_fits(key, content_bosses.CORTEX_RESTART_POINTS))
            self.assertFalse(boss_track_shuffle.schedule_fits(key, 3))
            self.assertFalse(boss_track_shuffle.schedule_fits(key, None))

    def test_a_forged_count_is_refused(self):
        options = boss_options(boss_track_shuffle=True)
        for seed in range(40):
            world = make_world(copy.deepcopy(options), seed=seed)
            plan = world.ctr_content_plan
            entries = {e["id"]: e for e in plan["entries"]}
            if any(entries[e["entry_id"]]["track_id"] == self.BTP for e in plan["encounters"][:4]):
                break
        else:
            self.fail("no seed drew Baby T Park")
        forged = copy.deepcopy(plan)
        next(p for p in forged["packages"] if p["content_id"] == "baby-t-park")["capabilities"]["checkpoints"] = 3
        with self.assertRaises(OptionError):
            content_plan.validate(forged)

if __name__ == "__main__":
    unittest.main()
