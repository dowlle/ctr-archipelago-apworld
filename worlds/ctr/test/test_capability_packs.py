"""Capability packs on content plans (#133 PR 4c).

Progressive Boost (with Blue Fire), Progressive Stats and Logic Difficulty in a
content-plan seed. The plan's `capability` record carries the settings, the
item ledger pools the chains, and every check whose race needs a boost rank
carries it as `boost`. Retail tracks keep their legacy terms (the USF finish
gate, the difficulty rules), a custom track with a super turbo pad takes the
Hot Air Skyway finish rule (ruling 2026-10-17), the CTR Token Challenge waits
for the first boost and the Relic Race Perfect needs USF. The paired native
parser reads the same records (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_capability, content_item_pool, content_plan, custom_packages, progressive_capability
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN
from .test_track_checks import check_options

BTP = "custom/baby-t-park/1.0.2"
LOOP = "custom/fixture-loop/2.1"
RECORD = dict(boost_mode=1, boost_blue_fire=False, stats_mode=0, logic_difficulty=1, shortcut_knowledge=0)


def cap_options(boost="shared_global", stats="off", difficulty="medium", blue_fire=False, knowledge="easy",
                loop_pads=None, **extra):
    loop = copy.deepcopy(UNKNOWN)
    if loop_pads is not None:
        loop["capabilities"]["super_turbo_pads"] = loop_pads
    options = check_options(rungs=True, custom=[copy.deepcopy(content_plan.PACKAGES[1]), loop])
    options.update(progressive_boost=boost, progressive_stats=stats, logic_difficulty=difficulty,
                   progressive_boost_blue_fire=blue_fire, shortcut_knowledge=knowledge, **extra)
    return options


def first_world(options, seed=0):
    """The first seed from `seed` on that the starting-check guard accepts:
    boost terms can leave a narrow start, which the guard refuses as on the
    legacy path (sphere0_guard.raise_if_narrow)."""
    for attempt in range(seed, seed + 20):
        try:
            return make_world(options, seed=attempt)
        except OptionError as exc:
            if "at the start" not in str(exc):
                raise
    raise AssertionError("no seed in 20 passed the starting-check guard")


def check_of(plan, owner, kind, award=None):
    return next(c for c in plan["checks"] if c["owner"] == owner and c["kind"] == kind
                and (award is None or c["routes"][0]["award"] == award))


def refused(plan):
    try:
        content_plan.validate(plan)
    except OptionError:
        return True
    return False


def retail(name):
    return dict(origin="retail", display_name=name)


class TestOffKeepsTheWire(unittest.TestCase):
    def test_both_off_means_no_record_feature_rank_or_row(self):
        world = make_world(cap_options(boost="off"), seed=4)
        plan = world.ctr_content_plan
        self.assertNotIn("capability", plan)
        self.assertNotIn(content_capability.FEATURE, plan["required_features"])
        self.assertFalse(any("boost" in c for c in plan["checks"]))
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["progressive_boost"], co["progressive_stats"]), (0, 0))
        self.assertFalse(any(i.name.startswith("Progressive") for i in world.multiworld.itempool
                             if i.name != "Progressive Starting Wumpa"))

    def test_packs_take_no_draw(self):
        off = make_world(cap_options(boost="off"), seed=9).ctr_content_plan
        on = make_world(cap_options(stats="shared_global", blue_fire=True), seed=9).ctr_content_plan
        self.assertEqual(on["tracks"], off["tracks"])
        self.assertEqual(on["pads"], off["pads"])
        self.assertEqual([{k: v for k, v in c.items() if k != "boost"} for c in on["checks"]], off["checks"])


class TestRecordRowsAndEnvelope(unittest.TestCase):
    def rows(self, plan):
        names = {code: name for name, code in content_item_pool.ITEMS.items()}
        return {names[r["item"]]: r["base"] for r in plan["items"]["rows"] if names.get(r["item"], "").startswith(
            ("Progressive Boost", "Progressive Top", "Progressive Acc", "Progressive Turn"))}

    def test_shared_chains(self):
        world = first_world(cap_options(stats="shared_global", blue_fire=True, difficulty="hard"), seed=2)
        plan = world.ctr_content_plan
        self.assertEqual(plan["capability"], dict(boost_mode=1, boost_blue_fire=True, stats_mode=1,
                                                  logic_difficulty=2, shortcut_knowledge=0))
        self.assertEqual(plan["required_features"][-1], content_capability.FEATURE)
        self.assertEqual(self.rows(plan), {"Progressive Boost": 3, "Progressive Top Speed": 4,
                                           "Progressive Acceleration": 4, "Progressive Turning": 4})
        co = world.fill_slot_data()["ctr_options"]
        self.assertEqual((co["progressive_boost"], co["progressive_stats"]), (1, 1))
        self.assertEqual((co["stat_source"], co["stat_owner"], co["stat_editing_allowed"]), (1, 1, False))
        # The boost chain is progression (rules read it); the stats stay useful.
        pool = world.multiworld.itempool
        self.assertTrue(all(i.advancement for i in pool if i.name == "Progressive Boost"))
        self.assertFalse(any(i.advancement for i in pool if i.name == "Progressive Turning"))
        self.assertTrue(content_plan.validate(plan))

    def test_per_racer_chains(self):
        counts = content_capability.item_counts(dict(boost_mode=2, boost_blue_fire=False, stats_mode=2))
        self.assertEqual(len(counts), 64)
        self.assertEqual(counts["Progressive Boost (Coco Bandicoot)"], 2)
        self.assertEqual(counts["Progressive Turning (Penta Penguin)"], 4)
        # 48 boosts and 192 stat copies outgrow this profile's checks: the
        # ledger refuses with its message, as for any pack.
        with self.assertRaisesRegex(OptionError, "free checks"):
            make_world(cap_options(boost="per_character", stats="per_character"), seed=3)
        plan = first_world(cap_options(boost="per_character", character_unlocks=True), seed=3).ctr_content_plan
        rows = self.rows(plan)
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows["Progressive Boost (Coco Bandicoot)"], 2)

    def test_boost_only_and_stats_only(self):
        plan = first_world(cap_options(), seed=1).ctr_content_plan
        self.assertEqual(self.rows(plan), {"Progressive Boost": 2})
        plan = first_world(cap_options(boost="off", stats="shared_global", blue_fire=True), seed=1).ctr_content_plan
        self.assertEqual(plan["capability"]["boost_blue_fire"], False)
        self.assertEqual(set(self.rows(plan)), {"Progressive Top Speed", "Progressive Acceleration", "Progressive Turning"})
        # Stats alone add no term.
        self.assertFalse(any("boost" in c for c in plan["checks"]))


class TestRanks(unittest.TestCase):
    def need(self, track, kind, award="win", package=None, letters=None, **record):
        return content_capability.check_boost(track, kind, award, dict(RECORD, **record), package, letters)

    def test_retail_terms(self):
        has, cove, oxide, castle = (retail(n) for n in ("Hot Air Skyway", "Crash Cove", "Oxide Station", "Cortex Castle"))
        self.assertEqual(self.need(has, "trophy"), 2)
        self.assertEqual(self.need(castle, "trophy"), 2)
        self.assertEqual(self.need(cove, "trophy"), 1)
        self.assertEqual(self.need(cove, "trophy", logic_difficulty=2), 0)
        self.assertEqual(self.need(oxide, "trophy"), 2)
        self.assertEqual(self.need(oxide, "trophy", shortcut_knowledge=2), 0)
        # A CTR Challenge waits for the first boost; Oxide Station's T and R need USF.
        self.assertEqual(self.need(cove, "ctr", "win_letters", logic_difficulty=2), 1)
        self.assertEqual(self.need(oxide, "ctr", "win_letters", shortcut_knowledge=2), 2)
        self.assertEqual(self.need(oxide, "ctr", "win_letters", shortcut_knowledge=2, letters={"letter_c"}), 1)
        self.assertEqual(self.need(retail("Papu's Pyramid"), "letter", "letter_c", logic_difficulty=2), 1)
        self.assertEqual(self.need(retail("Papu's Pyramid"), "letter", "letter_r", logic_difficulty=2), 0)
        self.assertEqual(self.need(oxide, "letter", "letter_t", shortcut_knowledge=2), 2)
        self.assertEqual(self.need(has, "letter", "letter_c"), 2)

    def test_rungs(self):
        has, cove = retail("Hot Air Skyway"), retail("Crash Cove")
        self.assertEqual(self.need(has, "podium", "held_1st", logic_difficulty=2), 2)
        self.assertEqual(self.need(cove, "podium", "held_1st"), 1)
        self.assertEqual(self.need(cove, "podium", "held_1st", logic_difficulty=2), 0)
        self.assertEqual(self.need(has, "podium", "held_3rd"), 0)
        self.assertEqual(self.need(has, "podium", "finish_any"), 2)
        self.assertEqual(self.need(cove, "podium", "finish_podium"), 0)
        self.assertEqual(self.need(cove, "podium", "finish_podium", logic_difficulty=0), 1)

    def test_relic_tiers_and_perfect(self):
        cove, labs = retail("Crash Cove"), retail("N. Gin Labs")
        self.assertEqual(self.need(cove, "relic", "sapphire"), 0)
        self.assertEqual(self.need(cove, "relic", "gold"), 1)
        self.assertEqual(self.need(cove, "relic", "platinum"), 2)
        self.assertEqual(self.need(cove, "relic", "platinum", logic_difficulty=2), 1)
        self.assertEqual(self.need(labs, "relic", "platinum", logic_difficulty=2), 2)
        self.assertEqual(self.need(cove, "relic", "platinum", logic_difficulty=0, boost_blue_fire=True), 3)
        self.assertEqual(self.need(cove, "perfect", "perfect", logic_difficulty=2), 2)
        self.assertEqual(self.need(cove, "wumpa", "wumpa"), 0)

    def test_custom_tracks_follow_their_super_turbo_pads(self):
        track = dict(origin="custom", display_name="Loop")
        pads = dict(capabilities=dict(super_turbo_pads=True))
        none = dict(capabilities=dict(super_turbo_pads=False))
        unstated = dict(capabilities={})
        # Any super turbo pad: the Hot Air Skyway finish rule on every finish.
        for kind, award in (("trophy", "win"), ("relic", "sapphire"), ("ctr", "win_letters"),
                            ("podium", "finish_any"), ("letter", "letter_c")):
            self.assertEqual(self.need(track, kind, award, pads, logic_difficulty=2), 2, kind)
        self.assertEqual(self.need(track, "trophy", "win", unstated, logic_difficulty=2), 2)
        # None: only the generic terms.
        self.assertEqual(self.need(track, "trophy", "win", none), 1)
        self.assertEqual(self.need(track, "trophy", "win", none, logic_difficulty=2), 0)
        self.assertEqual(self.need(track, "relic", "sapphire", none), 0)
        self.assertEqual(self.need(track, "ctr", "win_letters", none, logic_difficulty=2), 1)
        self.assertEqual(self.need(track, "perfect", "perfect", none, logic_difficulty=2), 2)
        self.assertEqual(self.need(track, "podium", "held_1st", pads, logic_difficulty=2), 0)

    def test_per_track_rulings(self):
        # the project's per-track rulings (2026-10-18), by content id, decide before
        # the measured flag, whatever the package states.
        self.assertEqual(content_capability.USF_FINISH_RULINGS, {
            "arabian-heights-night": True, "cortex-vortex": True,
            "tv-world": False, "north-pole": False, "baby-t-park": False})
        track = dict(origin="custom", display_name="Loop")
        for key, stated, want in (("arabian-heights-night", False, 2), ("cortex-vortex", None, 2),
                                  ("tv-world", True, 0), ("north-pole", True, 0), ("baby-t-park", True, 0)):
            caps = {} if stated is None else dict(super_turbo_pads=stated)
            package = dict(content_id=key, capabilities=caps)
            with self.subTest(key=key):
                self.assertEqual(content_capability.finish_boost(track, RECORD, package), want)
                self.assertEqual(self.need(track, "relic", "sapphire", package, logic_difficulty=2), want)
        # The bundled Cortex Vortex track keeps its confirmed USF finish.
        cortex = dict(origin="cortex_vortex", display_name="Cortex Vortex")
        self.assertEqual(self.need(cortex, "trophy", "win", logic_difficulty=2), 2)
        # A track with no ruling keeps the measured default: super pads
        # stated or unstated need USF, none stated take the generic terms.
        for caps, want in (({"super_turbo_pads": True}, 2), ({}, 2), ({"super_turbo_pads": False}, 0)):
            package = dict(content_id="arabian-heights-night-bplus", capabilities=caps)
            self.assertEqual(content_capability.finish_boost(track, RECORD, package), want)

    def test_rulings_file_shape_is_enforced(self):
        import json as _json
        raw = _json.loads(open(content_capability.__file__.replace("content_capability.py",
                                                                    "data/usf_finish_rulings.json")).read())
        self.assertTrue(all("2026-10-18" in row["ruling"] for row in raw["rulings"]))

    def test_boost_off_means_no_rank(self):
        self.assertEqual(self.need(retail("Hot Air Skyway"), "trophy", boost_mode=0, stats_mode=1), 0)


class TestPlanRanks(unittest.TestCase):
    def test_generated_ranks_match_the_table(self):
        for seed, (difficulty, pads) in enumerate((("easy", None), ("medium", False), ("hard", True))):
            world = first_world(cap_options(difficulty=difficulty, loop_pads=pads, relic_perfect_checks=True,
                                           wumpa_check="per_track"), seed=seed * 20)
            plan = world.ctr_content_plan
            with self.subTest(difficulty=difficulty):
                self.assertEqual(check_of(plan, "retail:7", "trophy").get("boost"), 2)  # Hot Air Skyway
                self.assertEqual(check_of(plan, "retail:3", "ctr").get("boost"), 1)     # Crash Cove
                self.assertEqual(check_of(plan, "retail:3", "perfect").get("boost"), 2)
                loop = check_of(plan, LOOP, "relic", "sapphire").get("boost", 0)
                self.assertEqual(loop, 0 if pads is False else 2)
                self.assertNotIn("boost", check_of(plan, "retail:3", "wumpa"))

    def test_a_ranked_check_needs_the_boosts(self):
        world = first_world(cap_options(difficulty="hard"), seed=5)
        mw, plan = world.multiworld, world.ctr_content_plan
        trophy = check_of(plan, "retail:7", "trophy")
        location = mw.get_location(content_plan.LOCATION_BY_CODE[trophy["location"]], 1)
        state = CollectionState(mw)
        for item in mw.itempool:
            if item.name != "Progressive Boost":
                state.collect(item, True)
        self.assertFalse(location.can_reach(state))
        boosts = [i for i in mw.itempool if i.name == "Progressive Boost"]
        state.collect(boosts[0], True)
        self.assertFalse(location.can_reach(state))
        state.collect(boosts[1], True)
        self.assertTrue(location.can_reach(state))

    def test_a_locked_pad_binds_its_racer(self):
        world = first_world(cap_options(boost="per_character", difficulty="hard", character_unlocks=True,
                                       racer_locked_pads=27), seed=7)
        mw, plan = world.multiworld, world.ctr_content_plan
        pads = {p["id"]: p for p in plan["pads"]}
        check = next(c for c in plan["checks"] if c.get("boost") == 2
                     and pads[c["routes"][0]["own_pad_id"]]["racer_lock"] is not None)
        lock = pads[check["routes"][0]["own_pad_id"]]["racer_lock"]
        from .. import characters
        racer = characters.CHARACTER_ID_TO_NAME[lock]
        other = next(n for n in progressive_capability.ROSTER if n != racer)
        location = mw.get_location(content_plan.LOCATION_BY_CODE[check["location"]], 1)
        state = CollectionState(mw)
        for item in mw.itempool:
            if not item.name.startswith("Progressive Boost (") or item.name == f"Progressive Boost ({other})":
                state.collect(item, True)
        self.assertFalse(location.can_reach(state))
        for item in mw.itempool:
            if item.name == f"Progressive Boost ({racer})":
                state.collect(item, True)
        self.assertTrue(location.can_reach(state))


class TestEarlyBoost(unittest.TestCase):
    """Ruling 2026-10-18: with boost on and a narrow start (fewer than
    sphere0_guard.BOOST_NARROW_START_CHECKS checks reachable without boost),
    the starting racer's first Progressive Boost is a local early item."""

    def worlds(self, **extra):
        from .. import sphere0_guard
        out = []
        for seed in range(40):
            try:
                world = make_world(cap_options(**extra), seed=seed)
            except OptionError:
                continue
            out.append((world, sphere0_guard.sphere0_breadth(world)))
        return out

    def test_narrow_boost_starts_mark_the_starting_racers_boost(self):
        from .. import sphere0_guard
        seen = {True: 0, False: 0}
        for boost in ("shared_global", "per_character"):
            for world, breadth in self.worlds(boost=boost, character_unlocks=True, racer_locked_pads=21):
                early = world.multiworld.local_early_items.get(1, {})
                name = sphere0_guard.starting_boost_item(world)
                narrow = breadth < sphere0_guard.BOOST_NARROW_START_CHECKS
                seen[narrow] += 1
                with self.subTest(boost=boost, breadth=breadth):
                    self.assertEqual(early.get(name, 0), 1 if narrow else 0)
                    self.assertEqual(getattr(world, "_ctr_early_boost", None), name if narrow else None)
                    self.assertFalse(world.multiworld.precollected_items[1])
                    if boost == "per_character":
                        self.assertEqual(name, f"Progressive Boost ({world.ctr_starting_character})")
        self.assertTrue(seen[True] and seen[False], seen)

    def test_boost_off_never_marks_a_boost(self):
        for world, _ in self.worlds(boost="off", stats="shared_global"):
            self.assertIsNone(getattr(world, "_ctr_early_boost", None))
            self.assertFalse(any(n.startswith("Progressive Boost")
                                 for n in world.multiworld.local_early_items.get(1, {})))


class TestForgedPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = first_world(cap_options(stats="shared_global", relic_perfect_checks=True), seed=7).ctr_content_plan

    def forged(self, change):
        plan = copy.deepcopy(self.plan)
        change(plan)
        return refused(plan)

    def test_unchanged_copy_is_accepted(self):
        self.assertFalse(self.forged(lambda p: None))

    def test_forgeries_refuse(self):
        boost_code = content_item_pool.ITEMS["Progressive Boost"]
        ranked = next(i for i, c in enumerate(self.plan["checks"]) if c.get("boost") == 2)
        free = next(i for i, c in enumerate(self.plan["checks"]) if "boost" not in c)

        def drop_record(p):
            p.pop("capability")
            p["required_features"].remove(content_capability.FEATURE)

        def row(p):
            return next(r for r in p["items"]["rows"] if r["item"] == boost_code)

        cases = {
            "rank lowered": lambda p: p["checks"][ranked].__setitem__("boost", 1),
            "rank dropped": lambda p: p["checks"][ranked].pop("boost"),
            "rank added": lambda p: p["checks"][free].__setitem__("boost", 1),
            "rank above the chain": lambda p: p["checks"][ranked].__setitem__("boost", 3),
            "rank as Boolean": lambda p: p["checks"][ranked].__setitem__("boost", True),
            "record dropped": drop_record,
            "feature dropped": lambda p: p["required_features"].remove(content_capability.FEATURE),
            "difficulty changed": lambda p: p["capability"].__setitem__("logic_difficulty", 2),
            "knowledge changed": lambda p: p["capability"].__setitem__("shortcut_knowledge", 2),
            "Blue Fire without its copy": lambda p: p["capability"].__setitem__("boost_blue_fire", True),
            "boost mode changed": lambda p: p["capability"].__setitem__("boost_mode", 2),
            "both modes off": lambda p: p["capability"].update(boost_mode=0, stats_mode=0),
            "unknown record field": lambda p: p["capability"].__setitem__("hit_character", 0),
            "record field missing": lambda p: p["capability"].pop("stats_mode"),
            "boost row with an extra copy": lambda p: row(p).update(base=3, remaining=3, receipt_cap=3,
                                                                    requirement_ceiling=3),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertTrue(self.forged(change), name)

    def test_envelope_must_match(self):
        wire = json.loads(json.dumps(first_world(cap_options(stats="shared_global"), seed=3).fill_slot_data()))
        for change in (dict(progressive_boost=0), dict(progressive_boost=2), dict(progressive_stats=0),
                       dict(stat_source=2, stat_editing_allowed=True), dict(stat_owner=2),
                       dict(stat_editing_allowed=True), dict(progressive_boost=True)):
            forged = copy.deepcopy(wire)
            forged["ctr_options"].update(change)
            with self.subTest(change=change), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)


class TestSuperTurboPadsDescriptor(unittest.TestCase):
    def test_flag_is_optional_and_boolean(self):
        d = copy.deepcopy(UNKNOWN)
        self.assertNotIn("super_turbo_pads", custom_packages.admit(d)["capabilities"])
        d["capabilities"]["super_turbo_pads"] = False
        self.assertIs(custom_packages.admit(d)["capabilities"]["super_turbo_pads"], False)
        for bad in (1, "yes", None):
            d["capabilities"]["super_turbo_pads"] = bad
            with self.subTest(bad=bad), self.assertRaises(custom_packages.PackageError):
                custom_packages.admit(d)


class TestTrackerAndFill(unittest.TestCase):
    def test_tracker_restores_the_options_and_plan(self):
        world = first_world(cap_options(boost="per_character", stats="shared_global", blue_fire=True,
                                       difficulty="easy", knowledge="hard", character_unlocks=True,
                                       racer_locked_pads=4), seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(other.fill_slot_data(), wire)
        o = other.options
        self.assertEqual((o.progressive_boost.value, o.progressive_boost_blue_fire.value, o.progressive_stats.value,
                          o.logic_difficulty.value, o.shortcut_knowledge.value), (2, 1, 1, 0, 2))
        self.assertTrue(all(i.advancement for i in other.multiworld.itempool if i.name.startswith("Progressive Boost (")))

    def test_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        from .. import characters
        modes = ("shared_global", "per_character")
        filled = 0
        for seed in range(8):
            options = cap_options(boost=modes[seed % 2], stats=("off", "shared_global")[seed % 2 == 0 and seed % 4 == 0],
                                  difficulty=("easy", "medium", "hard")[seed % 3], blue_fire=seed % 3 == 1,
                                  character_unlocks=seed % 2 == 1, racer_locked_pads=(0, 4)[seed % 2],
                                  relic_perfect_checks=True, wumpa_check=("off", "per_track")[seed % 2])
            try:
                world = make_world(options, seed=seed)
            except OptionError as exc:
                # The starting-check guard may refuse a narrow start, as on the legacy path.
                self.assertIn("at the start", str(exc))
                continue
            mw = world.multiworld
            with self.subTest(seed=seed):
                distribute_items_restrictive(mw)
                self.assertTrue(mw.can_beat_game())
                characters.verify_room_no_self_lock(mw)
                filled += 1
        self.assertGreaterEqual(filled, 6)


if __name__ == "__main__":
    unittest.main()
