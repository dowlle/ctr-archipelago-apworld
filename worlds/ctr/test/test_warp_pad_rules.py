"""Manual warp pad rules (`warp_pad_rules`, issue #463).

Covers the YAML contract (every accepted family, every refusal), the resolved
wire for the legacy generator, the AP access rules, behaviour under destination
shuffle, and the content-plan path (reserved seats, requirement records,
the schema-18 envelope and the Universal Tracker round trip).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from Options import OptionError

from test.general import setup_multiworld

from .. import ctrAPWorld, content_plan, destinations, warp_pad_rules
from .test_content_plan import make_world, profile_options

EARLY = ("generate_early",)
THROUGH_RULES = ("generate_early", "create_regions", "create_items", "set_rules")
FULL = THROUGH_RULES + ("generate_basic", "pre_fill")

# type enum of the wire Req (Contract section 2)
TYPE = {"Trophy": 1, "Key": 2, "CTR Token": 3, "Relic": 4, "Gem": 5,
        "AnyCtrToken": 6, "AnyRelic": 7, "AnyGem": 8}


def rule(item, count):
    return {"item": item, "count": count}


def lid(pad):
    return str(destinations.BY_KEY[pad].level_id)


def stage1(world, pad):
    return world.fill_slot_data()["warp_pad_unlock"][lid(pad)]["stage1"]


def build(rules, seed=1, steps=FULL, **options):
    options = dict(options, warp_pad_rules=rules, accessibility="full")
    return setup_multiworld(ctrAPWorld, steps, seed=seed, options=options)


class TestParse(unittest.TestCase):
    def test_example_from_the_design_note(self):
        parsed = warp_pad_rules.parse({
            "Crash Cove": rule("free", 0), "Roo's Tubes": rule("Key", 1),
            "Red Cup": rule("Red CTR Token", 3), "Skull Rock": rule("AnyRelic", 2)})
        self.assertEqual(parsed, {"Crash Cove": None, "Roo's Tubes": ("Key", 1),
                                  "Red Cup": ("Red CTR Token", 3),
                                  "Skull Rock": ("AnyRelic", 2)})

    def test_every_allowed_item_parses(self):
        for item in warp_pad_rules.ALLOWED_ITEMS:
            with self.subTest(item=item):
                self.assertEqual(warp_pad_rules.parse({"Crash Cove": rule(item, 1)}),
                                 {"Crash Cove": (item, 1)})

    def test_allowed_items_are_exactly_the_native_gate_families(self):
        self.assertEqual(len(warp_pad_rules.ALLOWED_ITEMS), 2 + 5 + 3 + 5 + 3)
        self.assertNotIn("Wumpa Fruit", warp_pad_rules.ALLOWED_ITEMS)

    def test_all_27_pads_are_named_by_the_destination_table(self):
        names = {d.key for d in destinations.DESTINATIONS}
        self.assertEqual(len(names), 27)
        parsed = warp_pad_rules.parse({n: rule("Trophy", 1) for n in names})
        self.assertEqual(set(parsed), names)

    def test_refusals(self):
        bad = {
            "unknown pad": {"Crash Covee": rule("Trophy", 1)},
            "warp pad suffix": {"Crash Cove Warp Pad": rule("Trophy", 1)},
            "garage": {"Ripper Roo Garage": rule("Trophy", 1)},
            "cortex vortex": {"Cortex Vortex": rule("Trophy", 1)},
            "duplicate after normalizing": {"Crash Cove": rule("Trophy", 1),
                                            " crash   cove ": rule("Key", 1)},
            "missing count": {"Crash Cove": {"item": "Trophy"}},
            "extra field": {"Crash Cove": {"item": "Trophy", "count": 1, "stage": 2}},
            "not a mapping": {"Crash Cove": "Trophy"},
            "bool count": {"Crash Cove": rule("Trophy", True)},
            "fraction": {"Crash Cove": rule("Trophy", 1.5)},
            "numeric string": {"Crash Cove": rule("Trophy", "3")},
            "zero count": {"Crash Cove": rule("Trophy", 0)},
            "negative count": {"Crash Cove": rule("Trophy", -1)},
            "free with count": {"Crash Cove": rule("free", 1)},
            "free with bool": {"Crash Cove": rule("free", False)},
            "wumpa": {"Crash Cove": rule("Wumpa Fruit", 1)},
            "character item": {"Crash Cove": rule("Penta Penguin", 1)},
            "item not text": {"Crash Cove": rule(3, 1)},
            "boss key typo": {"Crash Cove": rule("Keys", 1)},
        }
        for label, raw in bad.items():
            with self.subTest(label), self.assertRaises(OptionError) as ctx:
                warp_pad_rules.parse(raw)
            self.assertIn("warp_pad_rules", str(ctx.exception))

    def test_error_names_pad_item_and_count(self):
        with self.assertRaisesRegex(OptionError, r"'Red Cup'.*Purple Gem x 9"):
            build({"Red Cup": rule("Purple Gem", 9)}, steps=EARLY)

    def test_names_are_case_and_space_insensitive_but_one_rule_per_pad(self):
        parsed = warp_pad_rules.parse({"  roo's   TUBES": rule("key", 2)})
        self.assertEqual(parsed, {"Roo's Tubes": ("Key", 2)})


class TestSeedChecks(unittest.TestCase):
    def test_vanilla_unlock_mode_refuses_any_entry(self):
        with self.assertRaisesRegex(OptionError, "vanilla"):
            build({"Crash Cove": rule("free", 0)}, steps=EARLY,
                  warppad_unlock_requirements="vanilla")

    def test_empty_map_is_fine_with_vanilla(self):
        world = setup_multiworld(ctrAPWorld, EARLY, seed=1, options={
            "warppad_unlock_requirements": "vanilla"}).worlds[1]
        self.assertEqual(world._ctr_pad_rules, {})

    def test_no_four_keys_mode_refuses_a_four_key_rule_only(self):
        with self.assertRaisesRegex(OptionError, "random_without_4_keys"):
            build({"Coco Park": rule("Key", 4)}, steps=EARLY,
                  warppad_unlock_requirements="random_without_4_keys")
        world = build({"Coco Park": rule("Key", 3)}, steps=EARLY,
                      warppad_unlock_requirements="random_without_4_keys").worlds[1]
        self.assertEqual(world._ctr_pad_rules, {"Coco Park": ("Key", 3)})
        world = build({"Coco Park": rule("Key", 4)}, steps=EARLY,
                      warppad_unlock_requirements="randomized").worlds[1]
        self.assertEqual(world._ctr_pad_rules, {"Coco Park": ("Key", 4)})

    def test_pads_the_seed_does_not_have_are_refused(self):
        with self.assertRaisesRegex(OptionError, "battle arena"):
            build({"Skull Rock": rule("Trophy", 1)}, steps=EARLY,
                  include_battle_arenas=False)
        with self.assertRaisesRegex(OptionError, "gem cup"):
            build({"Red Cup": rule("Trophy", 1)}, steps=EARLY,
                  include_gem_cups=False)

    def test_supply_ceilings(self):
        cases = {
            "trophy": ("Trophy", 17), "key": ("Key", 5),
            "token": ("Red CTR Token", 5), "any token": ("AnyCtrToken", 21),
            "gem": ("Red Gem", 2), "any gem": ("AnyGem", 6),
            "relic tier with none created": ("Platinum Relic", 1),
            "any relic over the created total": ("AnyRelic", 37),
        }
        for label, (item, count) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(OptionError, "warp_pad_rules"):
                build({"Crash Cove": rule(item, count)}, steps=EARLY)

    def test_supply_ceiling_counts_the_created_relics(self):
        world = build({"Tiny Arena": rule("Gold Relic", 18)}, steps=EARLY).worlds[1]
        self.assertEqual(world._ctr_pad_rules, {"Tiny Arena": ("Gold Relic", 18)})
        with self.assertRaisesRegex(OptionError, "only 5"):
            build({"Tiny Arena": rule("Gold Relic", 6)}, steps=EARLY,
                  gold_relic_count=5)

    def test_purple_tokens_stay_available_with_arenas_off(self):
        # Ruling 2026-10-13 (#364): removing a check does not remove its item.
        world = build({"Red Cup": rule("Purple CTR Token", 4)}, steps=EARLY,
                      include_battle_arenas=False).worlds[1]
        self.assertEqual(world._ctr_pad_rules, {"Red Cup": ("Purple CTR Token", 4)})


class TestLegacyWire(unittest.TestCase):
    RULES = {"Crash Cove": rule("free", 0),
             "Roo's Tubes": rule("Trophy", 1),
             "Red Cup": rule("Red CTR Token", 3),
             "Skull Rock": rule("AnyRelic", 2),
             "Turbo Track": rule("Gold Relic", 3),
             "Dingo Canyon": rule("Trophy", 14),
             "Tiny Arena": rule("AnyCtrToken", 7),
             "Rocky Road": rule("Green Gem", 1),
             "Nitro Court": rule("AnyGem", 2),
             "Papu's Pyramid": rule("Key", 2)}
    WIRE = {"Crash Cove": {"type": 1, "count": 0, "colour": -1},
            "Roo's Tubes": {"type": 1, "count": 1, "colour": -1},
            "Red Cup": {"type": 3, "count": 3, "colour": 0},
            "Skull Rock": {"type": 7, "count": 2, "colour": -1},
            "Turbo Track": {"type": 4, "count": 3, "colour": 1},
            "Dingo Canyon": {"type": 1, "count": 14, "colour": -1},
            "Tiny Arena": {"type": 6, "count": 7, "colour": -1},
            "Rocky Road": {"type": 5, "count": 1, "colour": 1},
            "Nitro Court": {"type": 8, "count": 2, "colour": -1},
            "Papu's Pyramid": {"type": 2, "count": 2, "colour": -1}}

    def check_world(self, world):
        wire = world.fill_slot_data()["warp_pad_unlock"]
        for pad, expected in self.WIRE.items():
            self.assertEqual(wire[lid(pad)]["stage1"], expected, pad)

    def test_every_family_reaches_the_wire_exactly_as_written(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.check_world(build(self.RULES, seed=seed).worlds[1])

    def test_count_above_the_random_ceiling_is_not_lowered(self):
        # Random stage-1 counts are trimmed to 8 and by a 0.6 factor; a manual
        # Trophy x 14 must survive both.
        world = build(self.RULES, seed=4, steps=THROUGH_RULES).worlds[1]
        self.assertEqual(stage1(world, "Dingo Canyon")["count"], 14)

    def test_fixed_rules_survive_destination_shuffle(self):
        for seed in range(1, 7):
            with self.subTest(seed=seed):
                mw = build(self.RULES, seed=seed, steps=THROUGH_RULES,
                           warp_pad_shuffle_categories=["tracks", "crystals", "cups"],
                           warp_pad_shuffle_grouping="merged")
                self.check_world(mw.worlds[1])
                world = mw.worlds[1]
                moved = [p for p, dest in world.warp_pad_map.items()
                         if world.warp_pad_ids[p]["level_id"] != dest]
                self.assertTrue(moved, "shuffle did not move any pad")

    def test_unlisted_pads_keep_a_randomized_rule(self):
        world = build({"Crash Cove": rule("Trophy", 2)}, seed=2,
                      steps=THROUGH_RULES).worlds[1]
        wire = world.fill_slot_data()["warp_pad_unlock"]
        self.assertEqual(wire[lid("Crash Cove")]["stage1"],
                         {"type": 1, "count": 2, "colour": -1})
        self.assertGreater(len(set(json.dumps(v["stage1"], sort_keys=True)
                                   for v in wire.values())), 3)

    def test_access_rule_uses_the_resolved_value(self):
        mw = build({"Red Cup": rule("Red CTR Token", 3)}, seed=1, steps=THROUGH_RULES)
        world = mw.worlds[1]
        entrance = mw.get_entrance("Red Cup Warp Pad", 1)
        state = CollectionState(mw)
        for _ in range(4):
            state.collect(world.create_item("Key"), True)
        for _ in range(2):
            state.collect(world.create_item("Red CTR Token"), True)
        self.assertFalse(entrance.access_rule(state))
        state.collect(world.create_item("Red CTR Token"), True)
        self.assertTrue(entrance.access_rule(state))

    def test_free_pad_has_no_item_gate(self):
        mw = build({"Roo's Tubes": rule("free", 0)}, seed=1, steps=THROUGH_RULES)
        self.assertTrue(mw.get_entrance("Roo's Tubes Warp Pad", 1)
                        .access_rule(CollectionState(mw)))

    def test_generation_with_rules_fills_and_is_beatable(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                mw = build(self.RULES, seed=seed)
                distribute_items_restrictive(mw)
                self.assertTrue(mw.can_beat_game(CollectionState(mw)))

    def test_no_precollected_item_rescues_a_manual_rule(self):
        mw = build(self.RULES, seed=2)
        # The starting racer is the only start; no counted item is handed over.
        counted = {"Trophy", "Key"} | set(warp_pad_rules.TOKENS + warp_pad_rules.RELICS
                                          + warp_pad_rules.GEMS)
        self.assertFalse([i.name for i in mw.precollected_items[1] if i.name in counted])
        self.assertFalse(hasattr(mw.worlds[1], "_ctr_backstop_fired"))

    def test_empty_map_resolves_to_nothing(self):
        world = setup_multiworld(ctrAPWorld, EARLY, seed=1).worlds[1]
        self.assertEqual(world._ctr_pad_rules, {})

    def test_key_rule_with_pinned_keys_is_left_to_fill(self):
        # The design note's own example. With shuffle_keys off the synthetic
        # sweep cannot open a Key x 1 pad (the first Key needs four Trophies
        # from the other three starting pads), but real fill places Trophy
        # items anywhere, so the seed is solvable and must not be refused.
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                mw = build({"Roo's Tubes": rule("Key", 1)}, seed=seed, shuffle_keys=False)
                self.assertEqual(stage1(mw.worlds[1], "Roo's Tubes"),
                                 {"type": 2, "count": 1, "colour": -1})
                distribute_items_restrictive(mw)
                self.assertTrue(mw.can_beat_game(CollectionState(mw)))

    def test_fill_dead_end_is_reported_with_the_rules_and_the_cause(self):
        # Every starting pad needs four Keys, which sit behind bosses that need
        # Trophies: nothing is reachable, so the start guard refuses, and the
        # message names the rules instead of rescuing the seed.
        rules = {n: rule("Key", 4) for n in
                 ("Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway", "Skull Rock")}
        with self.assertRaisesRegex(OptionError, r"warp_pad_rules \(.*Key x 4"):
            build(rules, steps=FULL, shuffle_keys=False)

    def test_manual_rules_fill_check_reports_rules_and_cause_without_granting(self):
        mw = build({"Roo's Tubes": rule("Trophy", 3), "Red Cup": rule("AnyGem", 2)},
                   seed=1, steps=THROUGH_RULES + ("generate_basic",))
        world = mw.worlds[1]
        before = list(mw.precollected_items[1])

        def dead_end(panic):
            world._ctr_fill_failure = "Not enough locations for progression items."
            return False

        world._rollback_simulate_fill = dead_end
        with self.assertRaises(OptionError) as ctx:
            world._manual_rules_fill_check()
        text = str(ctx.exception)
        self.assertIn("Red Cup: AnyGem x 2", text)
        self.assertIn("Roo's Tubes: Trophy x 3", text)
        self.assertIn("Not enough locations for progression items.", text)
        self.assertEqual(mw.precollected_items[1], before)
        world._rollback_simulate_fill = lambda panic: True
        world._manual_rules_fill_check()  # a green replay changes nothing

    def test_too_few_starting_checks_names_the_rules(self):
        rules = {n: rule("Trophy", 5) for n in
                 ("Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway",
                  "Skull Rock")}
        with self.assertRaisesRegex(OptionError, "warp_pad_rules"):
            build(rules, seed=1)


def pool():
    """5 Trophies, 2 Sapphire and 2 Gold Relics, the five Gems, 4 Keys: 18 of
    the 19 checks, no Platinum Relics and no CTR Tokens."""
    return {"base": {"trophies": 5, "relics": {"sapphire": 2, "gold": 2, "platinum": 0},
                     "tokens": dict.fromkeys(("red", "green", "blue", "yellow", "purple"), 0),
                     "gems": ["red", "green", "blue", "yellow", "purple"], "keys": 4}}


class TestContentPlan(unittest.TestCase):
    RULES = {"Crash Cove": rule("Trophy", 3),
             "Skull Rock": rule("free", 0),
             "Red Cup": rule("AnyGem", 2),
             "Turbo Track": rule("Gold Relic", 2),
             "Dingo Canyon": rule("AnyRelic", 4)}

    def world(self, rules=None, seed=420, **extra):
        options = profile_options()
        options["item_pool"] = pool()
        options["warp_pad_rules"] = copy.deepcopy(self.RULES if rules is None else rules)
        options.update(extra)
        return make_world(options, seed=seed)

    def test_named_seats_are_reserved_and_requirement_records_resolve(self):
        for seed in range(0, 40):
            with self.subTest(seed=seed):
                plan = self.world(seed=seed).ctr_content_plan
                self.assertTrue(content_plan.validate(plan))
                pads = {p["id"]: p for p in plan["pads"]}
                reqs = {r["id"]: r["predicate"] for r in plan["requirements"]}
                for pad in ("Crash Cove", "Skull Rock", "Red Cup", "Turbo Track", "Dingo Canyon"):
                    physical = destinations.BY_KEY[pad].level_id
                    seat = pads[f"pad:{physical}"]
                    self.assertIsNotNone(seat["entry_id"], pad)
                    gate = seat["mode_gates"][0]["requirement_id"]
                    self.assertEqual(gate, "free" if pad == "Skull Rock" else f"manual:{physical}")
                self.assertEqual(plan["required_features"],
                                 ["content_plan_v1", "manual_pad_requirements_v1"])
                trophy = reqs[f"manual:{destinations.BY_KEY['Crash Cove'].level_id}"]
                self.assertEqual(trophy, {"op": "count", "item": 35010000, "count": 3})
                gems = reqs[f"manual:{destinations.BY_KEY['Red Cup'].level_id}"]
                self.assertEqual(gems["op"], "sum")
                self.assertEqual(gems["items"], list(range(35010009, 35010014)))
                relics = reqs[f"manual:{destinations.BY_KEY['Dingo Canyon'].level_id}"]
                self.assertEqual(relics, {"op": "sum", "items": [35010001, 35010002], "count": 4})

    def test_content_plan_seeds_fill_and_are_beatable(self):
        for seed in range(0, 12):
            with self.subTest(seed=seed):
                world = self.world(seed=seed)
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game(CollectionState(world.multiworld)))

    def test_content_plan_fill_dead_end_names_the_rules(self):
        world = self.world(seed=3)

        def dead_end(panic):
            world._ctr_fill_failure = "Unplaced items: Trophy"
            return False

        world._rollback_simulate_fill = dead_end
        with self.assertRaisesRegex(OptionError, r"Crash Cove: Trophy x 3.*Unplaced items: Trophy"):
            world.pre_fill()
        world._rollback_simulate_fill = lambda panic: True
        world.pre_fill()
        plain = make_world(profile_options(), seed=3)
        plain._rollback_simulate_fill = dead_end
        plain.pre_fill()  # no manual rules: the content-plan path never replays the fill

    def test_hub_key_floor_stays_in_entrance_req(self):
        plan = self.world().ctr_content_plan
        pads = {p["id"]: p for p in plan["pads"]}
        cup = pads[f"pad:{destinations.BY_KEY['Red Cup'].level_id}"]
        self.assertEqual(cup["entrance_req"], "keys:2")
        self.assertEqual(cup["mode_gates"][0]["requirement_id"],
                         f"manual:{destinations.BY_KEY['Red Cup'].level_id}")

    def test_schema_18_envelope_and_tracker_round_trip(self):
        world = self.world()
        wire = json.loads(json.dumps(world.fill_slot_data()))
        self.assertEqual(wire["schema_version"], 18)
        self.assertEqual(wire["ctr_options"]["schema_version"], 18)
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(other.fill_slot_data(), wire)
        for held in ({}, {"Trophy": 3}, {"Trophy": 3, "Key": 2}):
            seen = []
            for w in (world, other):
                state = CollectionState(w.multiworld)
                for name, count in held.items():
                    for _ in range(count):
                        state.collect(w.create_item(name), True)
                seen.append(sorted(loc.address for loc in
                                   w.multiworld.get_reachable_locations(state, 1)))
            self.assertEqual(seen[0], seen[1])

    def test_manual_rule_gates_the_pad_in_logic(self):
        world = self.world()
        plan = world.ctr_content_plan
        seat = f"pad:{destinations.BY_KEY['Crash Cove'].level_id}"
        entrance = world.multiworld.get_entrance(seat, 1)
        state = CollectionState(world.multiworld)
        for _ in range(2):
            state.collect(world.create_item("Trophy"), True)
        self.assertFalse(entrance.access_rule(state))
        state.collect(world.create_item("Trophy"), True)
        self.assertTrue(entrance.access_rule(state))
        self.assertTrue(plan)

    def test_without_rules_the_plan_is_the_experimental_baseline(self):
        plan = make_world(profile_options()).ctr_content_plan
        self.assertEqual(plan["required_features"], ["content_plan_v1"])
        self.assertTrue(all(r["id"] in ("free", "keys:1", "keys:2", "keys:3", "keys:4")
                            for r in plan["requirements"]))

    def test_more_named_pads_than_entries_fail_without_adding_content(self):
        options = profile_options()
        options["item_pool"] = pool()
        options["content_pool"]["tracks"]["retail"] = [0, 1, 2]
        options["content_pool"]["tracks"]["custom"] = []
        options["content_pool"]["required_entries"] = []
        options["warp_pad_rules"] = {n: rule("Trophy", 1) for n in
                                     ("Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway")}
        with self.assertRaisesRegex(OptionError, "only 3 entries"):
            make_world(options)

    def test_rules_leaving_too_few_starts_are_refused_not_relaxed(self):
        rules = {n: rule("Trophy", 5) for n in
                 ("Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway", "Skull Rock")}
        with self.assertRaisesRegex(OptionError, "starting checks"):
            self.world(rules)

    def test_start_inventory_can_open_a_named_pad(self):
        # The repair reads the real starting inventory: with a Trophy in hand the
        # five Trophy x 1 pads count as open starts. generate_early only, because
        # the test harness does not push start items the way Main.py does.
        rules = {n: rule("Trophy", 1) for n in
                 ("Crash Cove", "Roo's Tubes", "Mystery Caves", "Sewer Speedway", "Skull Rock")}
        options = profile_options()
        options["item_pool"] = pool()
        options.update(warp_pad_rules=rules, start_inventory={"Trophy": 1})
        mw = setup_multiworld(ctrAPWorld, EARLY, seed=420, options=options)
        self.assertTrue(content_plan.validate(mw.worlds[1].ctr_content_plan))
        options["start_inventory"] = {}
        with self.assertRaisesRegex(OptionError, "starting checks"):
            setup_multiworld(ctrAPWorld, EARLY, seed=420, options=options)

    def test_refusals(self):
        bad = {"vanilla": ({"Crash Cove": rule("Trophy", 1)},
                           {"warppad_unlock_requirements": "vanilla"}, "vanilla"),
               "four keys": ({"Crash Cove": rule("Key", 4)},
                             {"warppad_unlock_requirements": "random_without_4_keys"}, "random_without_4_keys"),
               "over supply": ({"Crash Cove": rule("Trophy", 6)}, {}, "holds only 5"),
               "unknown pad": ({"Nowhere": rule("Trophy", 1)}, {}, "not a warp pad"),
               "no such items": ({"Crash Cove": rule("Platinum Relic", 1)},
                                 {}, "no Platinum Relic")}
        for label, (rules, extra, text) in bad.items():
            with self.subTest(label), self.assertRaisesRegex(OptionError, text):
                options = profile_options()
                options["item_pool"] = pool()
                options["warp_pad_rules"] = rules
                for key, value in extra.items():
                    if isinstance(value, dict):
                        options[key].update(value)
                    else:
                        options[key] = value
                make_world(options)

    def test_validator_refuses_forged_manual_records(self):
        original = self.world().ctr_content_plan

        def tamper(change):
            plan = copy.deepcopy(original)
            change(plan)
            return plan

        def req(plan, physical):
            return next(r for r in plan["requirements"] if r["id"] == f"manual:{physical}")

        cove = destinations.BY_KEY["Crash Cove"].level_id
        cup = destinations.BY_KEY["Red Cup"].level_id
        cases = {
            "count above supply": lambda p: req(p, cove)["predicate"].update(count=17),
            "unknown item": lambda p: req(p, cove)["predicate"].update(item=35010099),
            "wumpa item": lambda p: req(p, cove)["predicate"].update(item=35010015),
            "sum with a missing colour": lambda p: req(p, cup)["predicate"]["items"].pop(),
            "sum items reordered": lambda p: req(p, cup)["predicate"]["items"].reverse(),
            "feature missing": lambda p: p.__setitem__("required_features", ["content_plan_v1"]),
            "feature without rules": lambda p: [p["requirements"].remove(r) for r in
                                               [r for r in p["requirements"] if r["id"].startswith("manual:")]],
            "gate points elsewhere": lambda p: next(
                x for x in p["pads"] if x["id"] == f"pad:{cove}")["mode_gates"][0].update(requirement_id="free"),
            "unknown op": lambda p: req(p, cove).update(predicate={"op": "all", "terms": [{"op": "always"}]}),
        }
        for label, change in cases.items():
            with self.subTest(label), self.assertRaises(OptionError):
                content_plan.validate(tamper(change))


if __name__ == "__main__":
    unittest.main()
