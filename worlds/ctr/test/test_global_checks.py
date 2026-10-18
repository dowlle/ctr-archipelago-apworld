"""Itemsanity and Hit Character on content plans (#133 PR 4d).

Both families are global: each check is a shared check with a route per race
that can earn it. Itemsanity's 22 use checks route from every Trophy Race and
CTR Challenge, and its 11 weapon items take ledger rows. Hit Character's 16
checks route a default racer from every such race and a guest from retail
races only (custom-served races keep the stock field); a guest joins through
its unlock win when the plan has one, else through its Key fallback, and the
four boss guests always take the content-plan fallback because content plans
have no boss encounters yet. The paired native parser reads the same records
(native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_global_checks, content_item_pool, content_plan, hit_character, itemsanity
from .test_content_plan import make_world
from .test_track_checks import check_options

BTP = "entry/custom/baby-t-park/1.0.2"
LOOP = "entry/custom/fixture-loop/2.1"


def global_options(items=True, hits=True, retail=None, modes=("trophy", "ctr", "relic"), **extra):
    options = check_options(rungs=True, modes=modes)
    if retail is not None:
        options["content_pool"]["tracks"]["retail"] = retail
    options.update(itemsanity=items, hit_character=hits, character_unlocks=False)
    options.update(extra)
    return options


def first_world(options, seed=0):
    """The first seed from `seed` on that the starting-check guard accepts."""
    for attempt in range(seed, seed + 20):
        try:
            return make_world(options, seed=attempt)
        except OptionError as exc:
            if "at the start" not in str(exc):
                raise
    raise AssertionError("no seed in 20 passed the starting-check guard")


def check_at(plan, code):
    return next(c for c in plan["checks"] if c["location"] == code)


def refused(plan):
    try:
        content_plan.validate(plan)
    except OptionError:
        return True
    return False


def race_routes(plan):
    tracks = {t["id"]: t for t in plan["tracks"]}
    pad_of = {p["entry_id"]: p["id"] for p in plan["pads"] if p["entry_id"]}
    out = []
    for entry in plan["entries"]:
        if entry["kind"] != "track":
            continue
        for mode in ("trophy", "ctr"):
            if mode in entry["modes"]:
                out.append((int(pad_of[entry["id"]].split(":")[1]), entry["id"], mode,
                            tracks[entry["track_id"]]["origin"]))
    return sorted(out, key=lambda r: (r[0], r[2] != "trophy"))


def state_with(world, *names):
    state = CollectionState(world.multiworld)
    for name in names:
        state.collect(world.create_item(name), prevent_sweep=True)
    return state


class TestOffKeepsTheWire(unittest.TestCase):
    def test_both_off_means_no_record_feature_check_row_or_block(self):
        world = make_world(global_options(items=False, hits=False), seed=4)
        plan = world.ctr_content_plan
        wire = world.fill_slot_data()
        self.assertNotIn("global_checks", plan)
        self.assertNotIn(content_global_checks.FEATURE, plan["required_features"])
        self.assertFalse(any(c["owner"] == "global" and c["kind"] in ("itemsanity", "hit") for c in plan["checks"]))
        self.assertNotIn("hit_character_encounters", wire)
        self.assertIs(wire["ctr_options"]["hit_character"], False)
        weapons = {content_item_pool.ITEMS[n] for n in itemsanity.ITEM_NAMES}
        self.assertFalse(weapons & {r["item"] for r in plan["items"]["rows"]})


class TestItemsanity(unittest.TestCase):
    def test_use_checks_rows_and_routes(self):
        world = make_world(global_options(hits=False), seed=3)
        plan = world.ctr_content_plan
        self.assertEqual(plan["global_checks"], {"itemsanity": True})
        self.assertEqual(plan["required_features"][-1], content_global_checks.FEATURE)
        uses = [c for c in plan["checks"] if c["kind"] == "itemsanity"]
        self.assertEqual([c["location"] for c in uses], list(range(35016000, 35016022)))
        expected = [(e, m) for _p, e, m, _o in race_routes(plan)]
        for check in uses:
            self.assertEqual(check["owner"], "global")
            self.assertEqual([(r["entry_id"], r["mode"]) for r in check["routes"]], expected)
            self.assertEqual({r["award"] for r in check["routes"]},
                             {"use_juiced" if check["display_name"].endswith("(Juiced)") else "use"})
        # Custom tracks are routes too: a weapon fires in any race.
        self.assertTrue({BTP, LOOP} <= {r["entry_id"] for r in uses[0]["routes"]})
        rows = {r["item"]: r for r in plan["items"]["rows"]}
        for name in itemsanity.ITEM_NAMES:
            row = rows[content_item_pool.ITEMS[name]]
            self.assertEqual((row["base"], row["extra"]), (1, 0))
        # The native runtime probes the room for the first use check.
        self.assertIn(35016000, {c["location"] for c in plan["checks"]})
        # One weapon type is seeded early, as on the legacy path.
        self.assertEqual(len(set(world.multiworld.early_items[1]) & set(itemsanity.WEAPONS)), 1)

    def test_rules_need_the_weapon_and_turbo_needs_the_first_boost(self):
        world = first_world(global_options(hits=False, progressive_boost="shared_global"), seed=2)
        turbo = world.multiworld.get_location("Itemsanity: Turbo", 1)
        bomb = world.multiworld.get_location("Itemsanity: Bomb (Juiced)", 1)
        self.assertFalse(bomb.can_reach(state_with(world)))
        self.assertTrue(bomb.can_reach(state_with(world, "Bomb")))
        self.assertFalse(turbo.can_reach(state_with(world, "Turbo")))
        self.assertTrue(turbo.can_reach(state_with(world, "Turbo", "Progressive Boost")))

    def test_weapon_arms_replace_the_first_boost_floors(self):
        # Legacy rulings: three useful weapon families for a difficulty-gated
        # Trophy Race (2026-09-20), one for Held 1st (2026-09-28), Turbo or
        # Mask for Papu's Pyramid C and T. A USF term has no arm.
        world = first_world(global_options(hits=False, retail=[5, 3, 7], stages="single", lettersanity=1,
                                           letters_per_track=3, progressive_boost="shared_global",
                                           logic_difficulty="medium", podium_held_rungs=True), seed=3)
        mw = world.multiworld
        weapons = set(itemsanity.ITEM_NAMES)
        others = [i.name for i in mw.itempool if i.advancement and i.name not in weapons
                  and i.name != "Progressive Boost"]
        loc = lambda name: mw.get_location(name, 1)
        bare = state_with(world, *others)
        self.assertFalse(loc("Crash Cove: Trophy Race").can_reach(bare))
        self.assertFalse(loc("Crash Cove: Trophy Race").can_reach(state_with(world, *others, "Mask", "Bomb")))
        self.assertTrue(loc("Crash Cove: Trophy Race").can_reach(state_with(world, *others, "Mask", "Bomb", "Warpball")))
        self.assertTrue(loc("Crash Cove: Trophy Race").can_reach(state_with(world, *others, "Progressive Boost")))
        self.assertFalse(loc("Crash Cove: Held 1st").can_reach(bare))
        self.assertTrue(loc("Crash Cove: Held 1st").can_reach(state_with(world, *others, "Missile x3")))
        self.assertFalse(loc("Papu's Pyramid: Letter C").can_reach(bare))
        self.assertTrue(loc("Papu's Pyramid: Letter C").can_reach(state_with(world, *others, "Mask")))
        # Hot Air Skyway's finish needs USF: no weapon replaces it.
        many = state_with(world, *others, *itemsanity.ITEM_NAMES)
        self.assertFalse(loc("Hot Air Skyway: Trophy Race").can_reach(many))
        # The CTR Token Challenge's first boost has no weapon arm either.
        self.assertFalse(loc("Crash Cove: CTR Token Challenge").can_reach(many))
        # Without Itemsanity the floors are boost only.
        plain = first_world(global_options(items=False, hits=False, retail=[5, 3, 7], stages="single",
                                           progressive_boost="shared_global", logic_difficulty="medium"), seed=3)
        self.assertIsNone(plain.ctr_content_plan.get("global_checks"))

    def test_a_plan_with_no_race_refuses(self):
        options = global_options(hits=False, modes=("relic",))
        options["content_pool"]["tracks"]["custom"] = []
        options["content_pool"]["required_entries"] = []
        with self.assertRaisesRegex(OptionError, "itemsanity needs at least one Trophy Race or CTR Challenge"):
            make_world(options, seed=1)

    def test_tiger_temple_door(self):
        world = first_world(global_options(hits=False, retail=[4, 3], lettersanity=1, letters_per_track=3), seed=1)
        token = world.multiworld.get_location("Tiger Temple: CTR Token Challenge", 1)
        letter = world.multiworld.get_location("Tiger Temple: Letter R", 1)
        everything = [i.name for i in world.multiworld.itempool if i.advancement and i.name not in
                      ("Bomb", "Bomb x3", "Missile", "Missile x3", "Beaker", "Shield Bubble", "Mask")]
        state = state_with(world, *everything)
        self.assertFalse(token.can_reach(state) or letter.can_reach(state))
        state.collect(world.create_item("Beaker"), prevent_sweep=True)
        self.assertTrue(token.can_reach(state) and letter.can_reach(state))
        # Without Itemsanity there is no door term.
        plain = first_world(global_options(items=False, hits=False, retail=[4, 3], lettersanity=1,
                                           letters_per_track=3), seed=1)
        names = [i.name for i in plain.multiworld.itempool if i.advancement]
        self.assertTrue(plain.multiworld.get_location("Tiger Temple: Letter R", 1).can_reach(state_with(plain, *names)))


class TestHitCharacter(unittest.TestCase):
    def test_checks_routes_block_and_fallback(self):
        # Crash Cove (Fake Crash) and Slide Coliseum (N. Tropy) are in the
        # plan; Penta's wins are not.
        world = make_world(global_options(items=False, retail=[3, 16, 4]), seed=5)
        plan = world.ctr_content_plan
        wire = world.fill_slot_data()
        self.assertEqual(plan["global_checks"], {"hit_character": True})
        hits = [c for c in plan["checks"] if c["kind"] == "hit"]
        self.assertEqual([c["location"] for c in hits], list(range(35025000, 35025016)))
        everything = [(e, m) for _p, e, m, _o in race_routes(plan)]
        retail_only = [(e, m) for _p, e, m, o in race_routes(plan) if o == "retail"]
        for check in hits:
            target = check["location"] - 35025000
            routes = [(r["entry_id"], r["mode"]) for r in check["routes"]]
            self.assertEqual(routes, everything if target < 8 else retail_only, check["display_name"])
        self.assertIs(wire["ctr_options"]["hit_character"], True)
        block = wire["hit_character_encounters"]
        hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS)
        fallback = {int(g): e.get("fallback_keys") for g, e in block["unlock_triggers"].items()}
        self.assertEqual(fallback, {8: 4, 9: 2, 10: 1, 11: 3, 12: None, 13: 2, 14: None, 15: 4})

    def test_guest_rules_follow_wins_and_keys(self):
        world = first_world(global_options(items=False, retail=[3, 16, 4], stages="single"), seed=5)
        mw = world.multiworld
        fake_crash = mw.get_location("Hit Fake Crash", 1)
        penta = mw.get_location("Hit Penta Penguin", 1)
        roo = mw.get_location("Hit Ripper Roo", 1)
        crash = mw.get_location("Hit Crash Bandicoot", 1)
        keys = ["Key"] * 4
        state = state_with(world, *keys)
        # The pads all open with four Keys; a default racer needs nothing more.
        self.assertTrue(crash.can_reach(state))
        self.assertTrue(roo.can_reach(state) and penta.can_reach(state))
        self.assertFalse(roo.can_reach(state_with(world)))
        self.assertTrue(roo.can_reach(state_with(world, "Key")))
        self.assertFalse(penta.can_reach(state_with(world, "Key")))
        self.assertTrue(penta.can_reach(state_with(world, "Key", "Key")))
        # Fake Crash joins through his Crash Cove win, never through Keys.
        win = mw.get_location("Crash Cove: Trophy Race", 1)
        self.assertEqual(fake_crash.can_reach(state), win.can_reach(state))

    def test_itemsanity_adds_the_hit_method(self):
        world = first_world(global_options(retail=[3, 16, 4], stages="single"), seed=5)
        crash = world.multiworld.get_location("Hit Crash Bandicoot", 1)
        keys = ["Key"] * 4
        self.assertFalse(crash.can_reach(state_with(world, *keys, "Turbo", "Mask")))
        self.assertTrue(crash.can_reach(state_with(world, *keys, "Missile x3")))

    def test_locked_racers_may_sit_on_global_checks(self):
        # Global checks glow on no pad and route from every race, so the
        # racer-lock placement rule (#133 PR 4b) leaves them out.
        world = first_world(global_options(character_unlocks=True, racer_locked_pads=6), seed=7)
        locks = world.ctr_racer_locks
        self.assertTrue(locks)
        racer = next(iter(locks.values()))
        item = world.create_item(racer)
        for name in ("Itemsanity: Bomb", "Hit Crash Bandicoot"):
            self.assertTrue(world.multiworld.get_location(name, 1).item_rule(item), name)

    def test_custom_track_appearance(self):
        # On a custom-served race the stock pack holds the other defaults for
        # a default player and 0..6 for a guest player, never a guest target.
        self.assertEqual(content_global_checks._appearance(7, "custom", None),
                         tuple(n for n in content_global_checks.progressive_capability.ROSTER
                               if hit_character.characters.ROSTER_CHARACTER_ID[n] < 7))
        self.assertEqual(content_global_checks._appearance(12, "custom", None), ())
        self.assertEqual(content_global_checks._appearance(0, "custom", "N. Tropy"), ("N. Tropy",))
        self.assertEqual(content_global_checks._appearance(7, "custom", "N. Tropy"), ())
        self.assertEqual(content_global_checks._appearance(7, "retail", "N. Tropy"), ("N. Tropy",))
        self.assertEqual(content_global_checks._appearance(0, "retail", "Crash Bandicoot"), ())

    def test_no_retail_race_refuses(self):
        options = global_options(items=False, retail=[])
        options["content_pool"]["required_entries"] = []
        with self.assertRaisesRegex(OptionError, "guest racers are drawn only in retail"):
            make_world(options, seed=1)

    def test_legacy_rooms_keep_the_boss_refusal(self):
        block = hit_character.build_encounters(7, {8: 4})
        with self.assertRaisesRegex(OptionError, "must not carry fallback_keys"):
            hit_character._validate_block(block)
        hit_character._validate_block(block, hit_character.CONTENT_PLAN_FALLBACK_KEYS)


class TestForgeryAndTracker(unittest.TestCase):
    def setUp(self):
        self.world = make_world(global_options(retail=[3, 16, 4]), seed=5)
        self.wire = json.loads(json.dumps(self.world.fill_slot_data()))

    def test_forged_plans_refuse(self):
        plan = self.wire["content_plan"]

        def guest_custom_route(p):
            route = next(r for r in check_at(p, 35025000)["routes"] if r["entry_id"] == BTP)
            check_at(p, 35025008)["routes"].append(route)

        def weapon_row(p):
            row = next(r for r in p["items"]["rows"] if r["item"] == content_item_pool.ITEMS["Mask"])
            row.update(base=2, remaining=2, receipt_cap=2, requirement_ceiling=2)
            p["items"]["filler_count"] -= 1

        def drop_record(p):
            del p["global_checks"]
            p["required_features"].remove(content_global_checks.FEATURE)

        for change in (lambda p: check_at(p, 35016000)["routes"].pop(),
                       lambda p: check_at(p, 35016003).update(owner="retail:3"),
                       guest_custom_route, weapon_row, drop_record,
                       lambda p: p["required_features"].remove(content_global_checks.FEATURE),
                       lambda p: p["global_checks"].update(box_locations=True),
                       lambda p: p["global_checks"].update(itemsanity=1)):
            forged = copy.deepcopy(plan)
            change(forged)
            self.assertTrue(refused(forged))
        self.assertFalse(refused(copy.deepcopy(plan)))

    def test_tracker_restores_without_a_redraw(self):
        other = make_world({}, passthrough=copy.deepcopy(self.wire))
        self.assertEqual(json.loads(json.dumps(other.fill_slot_data())), self.wire)
        self.assertTrue(other.options.itemsanity.value and other.options.hit_character.value)
        self.assertEqual(other.ctr_hit_character_fallback, self.world.ctr_hit_character_fallback)

    def test_tracker_refuses_a_disagreeing_block(self):
        def wrong_fallback(w):
            w["hit_character_encounters"]["unlock_triggers"]["14"]["fallback_keys"] = 1

        def boss_count(w):
            w["hit_character_encounters"]["unlock_triggers"]["8"]["fallback_keys"] = 3

        for change in (wrong_fallback, boss_count,
                       lambda w: w.pop("hit_character_encounters"),
                       lambda w: w["ctr_options"].update(hit_character=False)):
            bad = copy.deepcopy(self.wire)
            change(bad)
            with self.assertRaises(OptionError):
                make_world({}, passthrough=bad)


class TestFill(unittest.TestCase):
    def test_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        profiles = (global_options(),
                    global_options(progressive_boost="per_character", character_unlocks=True, racer_locked_pads=6),
                    global_options(hits=False, lettersanity=2, letters_per_track=2),
                    global_options(items=False, retail=[3, 9, 12], lettersanity=3))
        for index, options in enumerate(profiles):
            for seed in (11, 12):
                with self.subTest(profile=index, seed=seed):
                    world = first_world(options, seed=seed)
                    distribute_items_restrictive(world.multiworld)
                    state = CollectionState(world.multiworld)
                    state.sweep_for_advancements()
                    self.assertTrue(world.multiworld.can_beat_game(state))
                    self.assertTrue(all(loc.can_reach(state) for loc in world.multiworld.get_locations(1)))


if __name__ == "__main__":
    unittest.main()
