"""Character packs on content plans (#133 PR 4b).

Character Unlocks, Remove Playable Oxide and Racer-Locked Warp Pads work in a
content-plan seed on retail and custom tracks. With unlocks on, the plan's
optional `racers` record names the starting racer, the Oxide setting and the
requested lock maximum; the item ledger pools one row per unlock racer, and a
pad that does not open at the start may carry a `racer_lock`. Starting Stat
Class, Penta Penguin Stats and Editable Stats ride optional `ctr_options`
keys. The paired native parser applies the same rules (native
tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import characters, content_item_pool, content_plan
from .test_content_plan import make_world, profile_options
from .test_track_checks import check_options

ROSTER = list(characters.ROSTER_CHARACTER_ID)


def racer_options(unlocks=True, locks=0, oxide=False, start=None, **extra):
    options = check_options(rungs=False)
    options.update(character_unlocks=unlocks, racer_locked_pads=locks, remove_playable_oxide=oxide, **extra)
    if start is not None:
        options["starting_character"] = start
    return options


def rows_of(plan):
    return {row["item"]: row for row in plan["items"]["rows"]}


def racer_rows(plan):
    codes = {content_item_pool.ITEMS[name]: name for name in ROSTER}
    return {codes[code]: row for code, row in rows_of(plan).items() if code in codes}


def pool_names(world):
    return [item.name for item in world.multiworld.itempool if item.player == world.player]


def refused(plan):
    try:
        content_plan.validate(plan)
    except OptionError:
        return True
    return False


def locked_pads(plan):
    return {pad["id"]: pad["racer_lock"] for pad in plan["pads"] if pad["racer_lock"] is not None}


class TestOffKeepsTheWire(unittest.TestCase):
    def test_unlocks_off_means_no_record_feature_row_or_lock(self):
        world = make_world(racer_options(unlocks=False, locks=6), seed=4)
        plan = world.ctr_content_plan
        self.assertNotIn("racers", plan)
        self.assertNotIn(content_plan.RACER_FEATURE, plan["required_features"])
        self.assertFalse(racer_rows(plan))
        self.assertFalse(locked_pads(plan))
        self.assertFalse(set(ROSTER) & set(pool_names(world)))
        co = world.fill_slot_data()["ctr_options"]
        self.assertIs(co["character_unlocks"], False)
        self.assertFalse(set(content_plan.STAT_ENVELOPE) & set(co))

    def test_unlocks_take_no_layout_draw(self):
        # Turning unlocks on adds the start draw before the ledger; the
        # tracks are chosen before it.
        off = make_world(racer_options(unlocks=False), seed=9).ctr_content_plan
        on = make_world(racer_options(), seed=9).ctr_content_plan
        self.assertEqual(on["tracks"], off["tracks"])


class TestUnlocks(unittest.TestCase):
    def test_record_rows_pool_and_envelope(self):
        off = make_world(racer_options(unlocks=False), seed=5)
        world = make_world(racer_options(), seed=5)
        plan = world.ctr_content_plan
        start = characters.ROSTER_CHARACTER_ID[world.ctr_starting_character]
        self.assertEqual(plan["racers"], dict(starting_character=start, remove_playable_oxide=False, requested_locks=0))
        self.assertEqual(plan["required_features"][-1], content_plan.RACER_FEATURE)
        rows = racer_rows(plan)
        self.assertEqual(sorted(rows), sorted(n for n in ROSTER if n != world.ctr_starting_character))
        self.assertTrue(all((r["base"], r["extra"], r["remaining"]) == (1, 0, 1) for r in rows.values()))
        self.assertEqual(sorted(n for n in pool_names(world) if n in ROSTER), sorted(rows))
        # Fifteen filler slots became the racers; no location was added.
        self.assertEqual(plan["items"]["filler_count"], off.ctr_content_plan["items"]["filler_count"] - 15)
        self.assertEqual(len(world.multiworld.get_locations(1)), len(off.multiworld.get_locations(1)))
        # Nothing names a racer in logic without locks, so they stay useful.
        self.assertFalse(any(i.advancement for i in world.multiworld.itempool if i.name in ROSTER))
        co = world.fill_slot_data()["ctr_options"]
        self.assertIs(co["character_unlocks"], True)
        self.assertEqual(co["starting_character"], start)
        self.assertEqual(len(world.multiworld.precollected_items[1]), 0)
        self.assertTrue(content_plan.validate(plan))

    def test_remove_playable_oxide(self):
        for seed in range(6):
            world = make_world(racer_options(oxide=True, start="random_any", locks=27), seed=seed)
            plan = world.ctr_content_plan
            with self.subTest(seed=seed):
                self.assertNotEqual(world.ctr_starting_character, characters.OXIDE)
                self.assertTrue(plan["racers"]["remove_playable_oxide"])
                self.assertEqual(len(racer_rows(plan)), 14)
                self.assertNotIn(characters.OXIDE, racer_rows(plan))
                self.assertNotIn(15, locked_pads(plan).values())

    def test_oxide_start_with_oxide_removed_refuses(self):
        with self.assertRaises(OptionError):
            make_world(racer_options(oxide=True, start="nitros_oxide"), seed=1)

    def test_oxide_removal_without_unlocks_does_nothing(self):
        plan = make_world(racer_options(unlocks=False, oxide=True), seed=1).ctr_content_plan
        self.assertNotIn("racers", plan)

    def test_a_pool_too_small_refuses_with_the_ledger_message(self):
        options = racer_options(custom=[])
        options["content_pool"]["tracks"]["retail"] = [0, 1]
        options["content_pool"]["required_entries"] = []
        options["content_pool"]["tracks"]["modes"] = ["trophy"]
        with self.assertRaisesRegex(OptionError, "free checks"):
            make_world(options, seed=1)


class TestRacerLocks(unittest.TestCase):
    def test_locks_follow_the_legacy_rules(self):
        for seed in range(10):
            requested = (1, 4, 8, 15, 27)[seed % 5]
            world = make_world(racer_options(locks=requested), seed=seed)
            plan = world.ctr_content_plan
            locks = locked_pads(plan)
            eligible = content_plan.lock_eligible(plan)
            pads = {pad["id"]: pad for pad in plan["pads"]}
            start = plan["racers"]["starting_character"]
            with self.subTest(seed=seed, requested=requested):
                self.assertEqual(plan["racers"]["requested_locks"], requested)
                self.assertEqual(len(locks), min(requested, len(eligible)))
                self.assertTrue(set(locks) <= set(eligible))
                for pad_id in locks:
                    self.assertTrue(pads[pad_id]["entrance_req"] != "free"
                                    or any(g["requirement_id"].startswith("manual:") for g in pads[pad_id]["mode_gates"]))
                self.assertNotIn(start, locks.values())
                counts = [list(locks.values()).count(characters.ROSTER_CHARACTER_ID[n])
                          for n in ROSTER if characters.ROSTER_CHARACTER_ID[n] != start]
                self.assertLessEqual(max(counts) - min(counts), 1)
                self.assertEqual(world.ctr_racer_locks, content_plan.plan_racer_locks(plan))
                # Locks on: the unlock items gate pads, so they are progression.
                self.assertTrue(all(i.advancement for i in world.multiworld.itempool if i.name in ROSTER))

    def test_free_starting_pads_never_lock(self):
        plan = make_world(racer_options(locks=27), seed=3).ctr_content_plan
        for pad in plan["pads"]:
            if pad["entry_id"] is not None and pad["entrance_req"] == "free":
                self.assertIsNone(pad["racer_lock"], pad["id"])

    def test_start_breadth_is_the_same_with_locks(self):
        from .. import sphere0_guard
        for seed in range(4):
            off = make_world(racer_options(), seed=seed, stop_before="pre_fill")
            on = make_world(racer_options(locks=27), seed=seed, stop_before="pre_fill")
            self.assertEqual(sphere0_guard.sphere0_breadth(on), sphere0_guard.sphere0_breadth(off))

    def test_a_locked_pad_needs_its_racer(self):
        world = make_world(racer_options(locks=3), seed=2)
        plan, mw = world.ctr_content_plan, world.multiworld
        pad_id, cid = next(iter(locked_pads(plan).items()))
        racer = characters.CHARACTER_ID_TO_NAME[cid]
        entrance = mw.get_entrance(pad_id, 1)
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.name != racer:
                state.collect(item, True)
        self.assertFalse(entrance.can_reach(state))
        state.collect(next(i for i in mw.itempool if i.name == racer), True)
        self.assertTrue(entrance.can_reach(state))

    def test_legacy_boolean_is_the_alpha6_density(self):
        options = racer_options()
        options["racer_locked_pads"] = True
        plan = make_world(options, seed=6).ctr_content_plan
        eligible = len(content_plan.lock_eligible(plan))
        self.assertEqual(plan["racers"]["requested_locks"], max(1, min(6, int(eligible * 0.25))))

    def test_custom_track_pads_take_locks(self):
        seen = set()
        for seed in range(30):
            plan = make_world(racer_options(locks=27), seed=seed).ctr_content_plan
            entries = {e["id"]: e for e in plan["entries"]}
            for pad in plan["pads"]:
                if pad["racer_lock"] is not None:
                    seen.add(entries[pad["entry_id"]].get("track_id", "")[:7])
        self.assertIn("custom/", seen)
        self.assertIn("retail:", seen)


class TestForgedPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = make_world(racer_options(locks=6, oxide=True), seed=7).ctr_content_plan

    def forged(self, change):
        plan = copy.deepcopy(self.plan)
        change(plan)
        return refused(plan)

    def test_unchanged_copy_is_accepted(self):
        self.assertFalse(self.forged(lambda p: None))

    def test_forgeries_refuse(self):
        locks = locked_pads(self.plan)
        locked = next(iter(locks))
        start = self.plan["racers"]["starting_character"]
        free = next(p["id"] for p in self.plan["pads"] if p["entry_id"] and p["entrance_req"] == "free")
        empty = next(p["id"] for p in self.plan["pads"] if p["kind"] == "normal" and p["entry_id"] is None)
        unlocked = next(p for p in content_plan.lock_eligible(self.plan) if p not in locks)
        racer_code = content_item_pool.ITEMS[next(iter(racer_rows(self.plan)))]

        def pad(p, pad_id):
            return next(x for x in p["pads"] if x["id"] == pad_id)

        def drop_record(p):
            p.pop("racers")
            p["required_features"].remove(content_plan.RACER_FEATURE)

        def drop_row(p):
            p["items"]["rows"] = [r for r in p["items"]["rows"] if r["item"] != racer_code]
            p["items"]["filler_count"] += 1

        def start_row(p):
            row = copy.deepcopy(next(r for r in p["items"]["rows"] if r["item"] == racer_code))
            row["item"] = content_item_pool.ITEMS[characters.CHARACTER_ID_TO_NAME[start]]
            p["items"]["rows"].append(row)
            p["items"]["rows"].sort(key=lambda r: r["item"])
            p["items"]["filler_count"] -= 1

        def move_lock(p, target):
            pad(p, target)["racer_lock"] = pad(p, locked)["racer_lock"]
            pad(p, locked)["racer_lock"] = None

        cases = {
            "lock without the record": drop_record,
            "lock on a free starting pad": lambda p: move_lock(p, free),
            "lock on an empty pad": lambda p: move_lock(p, empty),
            "lock on a garage": lambda p: move_lock(p, "garage:0"),
            "lock names the starting racer": lambda p: pad(p, locked).__setitem__("racer_lock", start),
            "lock names removed Oxide": lambda p: pad(p, locked).__setitem__("racer_lock", 15),
            "lock names no racer": lambda p: pad(p, locked).__setitem__("racer_lock", 16),
            "lock as Boolean": lambda p: pad(p, locked).__setitem__("racer_lock", True),
            "one lock too many": lambda p: pad(p, unlocked).__setitem__("racer_lock", pad(p, locked)["racer_lock"]),
            "one lock dropped": lambda p: pad(p, locked).__setitem__("racer_lock", None),
            "requested count changed": lambda p: p["racers"].__setitem__("requested_locks", 5),
            "requested count 28": lambda p: p["racers"].__setitem__("requested_locks", 28),
            "start changed": lambda p: p["racers"].__setitem__("starting_character", (start + 1) % 16),
            "Oxide flag flipped": lambda p: p["racers"].__setitem__("remove_playable_oxide", False),
            "Oxide flag as integer": lambda p: p["racers"].__setitem__("remove_playable_oxide", 1),
            "unknown record field": lambda p: p["racers"].__setitem__("character_unlocks", True),
            "record field missing": lambda p: p["racers"].pop("requested_locks"),
            "feature dropped": lambda p: p["required_features"].remove(content_plan.RACER_FEATURE),
            "racer row missing": drop_row,
            "row for the starting racer": start_row,
            "racer row with an extra copy": lambda p: next(r for r in p["items"]["rows"] if r["item"] == racer_code).update(
                extra=1, remaining=2, receipt_cap=2),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(self.forged(change), name)


class TestStatsEnvelope(unittest.TestCase):
    def test_keys_present_only_when_set(self):
        co = make_world(racer_options(starting_stat_class="turning", penta_stats="pal", editable_stats="global"),
                        seed=3).fill_slot_data()["ctr_options"]
        self.assertEqual({k: co[k] for k in content_plan.STAT_ENVELOPE},
                         dict(starting_stat_class=4, penta_stats=1, stat_source=2, stat_owner=1, stat_editing_allowed=True))
        co = make_world(racer_options(), seed=3).fill_slot_data()["ctr_options"]
        self.assertFalse(set(content_plan.STAT_ENVELOPE) & set(co))

    def test_stats_take_no_draw(self):
        plain = make_world(racer_options(), seed=8).ctr_content_plan
        stats = make_world(racer_options(starting_stat_class="speed", editable_stats="per_character"), seed=8).ctr_content_plan
        self.assertEqual(plain, stats)

    def test_bad_values_refuse_on_restore(self):
        wire = json.loads(json.dumps(make_world(racer_options(editable_stats="global", starting_stat_class="speed"),
                                                seed=3).fill_slot_data()))
        for change in (dict(starting_stat_class=0), dict(starting_stat_class=5), dict(starting_stat_class=True),
                       dict(penta_stats=0), dict(penta_stats=2), dict(stat_source=1), dict(stat_owner=0),
                       dict(stat_owner=3), dict(stat_editing_allowed=False), dict(character_unlocks=False),
                       dict(starting_character=(wire["ctr_options"]["starting_character"] + 1) % 16)):
            forged = copy.deepcopy(wire)
            forged["ctr_options"].update(change)
            with self.subTest(change=change), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)
        for key in ("stat_source", "stat_owner", "stat_editing_allowed"):
            forged = copy.deepcopy(wire)
            forged["ctr_options"].pop(key)
            with self.subTest(dropped=key), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)


class TestTrackerAndFill(unittest.TestCase):
    def test_tracker_restores_racers_locks_and_stats(self):
        options = racer_options(locks=8, oxide=True, starting_stat_class="acceleration", penta_stats="pal",
                                editable_stats="per_character")
        world = make_world(options, seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(other.fill_slot_data(), wire)
        self.assertEqual(other.ctr_racer_locks, world.ctr_racer_locks)
        self.assertEqual(other.ctr_starting_character, world.ctr_starting_character)
        self.assertEqual(other.ctr_content_items.selected_names(), world.ctr_content_items.selected_names())
        o = other.options
        self.assertEqual((o.character_unlocks.value, o.remove_playable_oxide.value, o.racer_locked_pads.value,
                          o.starting_stat_class.value, o.penta_stats.value, o.editable_stats.value), (1, 1, 8, 2, 1, 2))
        # The tracker's racer items are progression too, so a locked pad opens
        # in its logic once the racer arrives.
        self.assertTrue(all(i.advancement for i in other.multiworld.itempool if i.name in ROSTER))

    def test_seeds_fill_beat_and_never_self_lock(self):
        from Fill import distribute_items_restrictive
        for seed in range(10):
            options = racer_options(locks=(0, 3, 9, 27)[seed % 4], oxide=seed % 3 == 0,
                                    wumpa_check=("off", "global", "per_track")[seed % 3])
            world = make_world(options, seed=seed)
            mw = world.multiworld
            with self.subTest(seed=seed):
                distribute_items_restrictive(mw)
                self.assertTrue(mw.can_beat_game())
                characters.verify_room_no_self_lock(mw)
                locks = world.ctr_racer_locks
                by_code = {c["location"]: c for c in world.ctr_content_plan["checks"]}
                for loc in mw.get_filled_locations(1):
                    if loc.item.name in ROSTER and loc.address in by_code:
                        pads = {r["own_pad_id"] for r in by_code[loc.address]["routes"]}
                        self.assertFalse(any(locks.get(p) == loc.item.name for p in pads), loc.name)


if __name__ == "__main__":
    unittest.main()
