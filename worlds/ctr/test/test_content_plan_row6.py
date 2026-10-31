"""One generator row 6: the plan's `pad_client` record, and `win_logic` on plan
rooms, compared with `location.can_reach` by the wire evaluator of
test_win_logic_parity on the mixes that shape a win check's rule."""
import copy
import json
import random
import unittest

from BaseClasses import CollectionState
from Options import OptionError

from .. import content_bosses, content_plan, content_wumpa
from ..win_logic import wire_block, wire_size
from .test_content_plan import make_world
from .test_content_plan_row5 import fill, options
from .test_win_logic_parity import WireEvaluator, _received, _start_entries

PLAYER = 1
ITEM_POOL = {"Sapphire Relic": {"base": 18}, "Gold Relic": {"base": 18}, "Platinum Relic": {"base": 18}}
#: Every switch that adds a term to a win check, or moves a race on its pad.
MIXES = {
    "default": {},
    "vanilla": dict(warppad_unlock_requirements="vanilla"),
    "per_pad": dict(pad_layout=dict(placement="shuffle", stages="two", mode_order="per_pad", merge_trophy_ctr=False)),
    "per_seed": dict(pad_layout=dict(placement="shuffle", stages="two", mode_order="per_seed", merge_trophy_ctr=False)),
    "single": dict(pad_layout=dict(placement="shuffle", stages="single", mode_order="fixed", merge_trophy_ctr=False)),
    "ctr_first": dict(adventure_structure="ctr_first"),
    "ctr_first_per_pad": dict(adventure_structure="ctr_first",
                              pad_layout=dict(placement="shuffle", stages="two", mode_order="per_pad",
                                              merge_trophy_ctr=False)),
    "letters": dict(lettersanity="items_only"),
    "letters_mix": dict(lettersanity="locations_and_items", letters_per_track=2),
    "first_letters": dict(adventure_structure="ctr_first", lettersanity="items_only"),
    "boost": dict(progressive_boost="shared_global"),
    "boost_racer": dict(progressive_boost="per_character", racer_locked_pads=6),
    "boost_itemsanity": dict(progressive_boost="shared_global", itemsanity=True),
    "racers": dict(racer_locked_pads=6),
    "goal_gems": dict(gems_required_goal=3, oxide_goal="any_percent"),
    "goal_bosses": dict(bosses_required_goal=2, oxide_goal="101_percent"),
    "wumpa_goal": dict(goal_wumpa=500, oxide_goal="any_percent"),
    "wumpa_goal_final": dict(goal_wumpa=500, oxide_goal="101_percent", progressive_boost="shared_global"),
    "fixed": dict(shuffle_keys=False, shuffle_gems=False),
}


def client_options(**overrides):
    return options(**overrides)


def wire_options(world, plan):
    capability = plan.get("capability", {})
    return dict(boost_mode=capability.get("boost_mode", 0),
                starting_character=content_plan.characters.ROSTER_CHARACTER_ID[world.ctr_starting_character],
                character_unlocks="racers" in plan)


def compare(world, rng, states=24):
    """Disagreements of the block with `can_reach`, as test_win_logic_parity."""
    mw = world.multiworld
    block = wire_block(world)
    self_check = json.loads(json.dumps(block))
    assert self_check == block
    plan = world.ctr_content_plan
    wins = {loc.address: loc for loc in mw.get_locations(PLAYER)
            if loc.address in content_plan.win_kinds(plan)}
    assert set(map(int, block["checks"])) == set(wins)
    items = [(it, 1) for it in mw.itempool if it.player == PLAYER]
    items += [(loc.item, int(loc.address)) for loc in mw.get_locations() if loc.item is not None
              and loc.item.player == PLAYER and loc.address is not None]
    start = _start_entries(mw)
    wumpa = mw.get_location(content_wumpa.INCOME, PLAYER) if content_wumpa.banking(plan) else None
    boss_events = [content_bosses.EVENTS[code] for code in content_bosses.BOSS_CODES
                   if code in {c["location"] for c in plan["checks"]}]
    item_ids = world.item_name_to_id
    bad = []
    for n in range(states + 2):
        p = rng.choice((0.15, 0.35, 0.6, 0.85))
        chosen = [] if n == 0 else items if n == 1 else [i for i in items if rng.random() < p]
        won = [] if n == 0 else boss_events if n == 1 else [e for e in boss_events if rng.random() < p]
        state = CollectionState(mw)
        for it, _ in chosen:
            if it.advancement:
                state.add_item(it.name, PLAYER)
        for name in won:
            state.add_item(name, PLAYER)
        # An event only the sweep collects: as Archipelago's state holds it.
        if wumpa is not None and wumpa.can_reach(state):
            state.add_item(content_wumpa.INCOME, PLAYER)
            state.stale[PLAYER] = True
        received = _received(start + [(int(it.code), loc, it.flags) for it, loc in chosen if it.code is not None])
        ev = WireEvaluator(block, wire_options(world, plan), received, len(won), item_ids)
        for code, loc in wins.items():
            if loc.can_reach(state) != ev.in_logic(code):
                bad.append((loc.name, n, loc.can_reach(state)))
    return bad


class TestPadClient(unittest.TestCase):
    def test_record_and_feature(self):
        plan = make_world(client_options()).ctr_content_plan
        self.assertEqual(plan["pad_client"], dict(race_type_selector="always", tracker_pad_launch=True))
        self.assertEqual(plan["required_features"][-1], content_plan.PAD_CLIENT_FEATURE)
        self.assertTrue(content_plan.validate(plan))

    def test_values_reach_the_record_and_draw_nothing(self):
        on = make_world(client_options(), seed=7).ctr_content_plan
        off = make_world(client_options(race_type_selector="productive", tracker_pad_launch=False), seed=7).ctr_content_plan
        self.assertEqual(off["pad_client"], dict(race_type_selector="productive", tracker_pad_launch=False))
        on, off = copy.deepcopy(on), copy.deepcopy(off)
        on.pop("pad_client"), off.pop("pad_client")
        self.assertEqual(json.dumps(on, sort_keys=True), json.dumps(off, sort_keys=True))

    def test_forged_records_are_refused(self):
        plan = make_world(client_options()).ctr_content_plan
        for label, forge in dict(
                unknown_value=lambda p: p["pad_client"].__setitem__("race_type_selector", "never"),
                not_a_boolean=lambda p: p["pad_client"].__setitem__("tracker_pad_launch", 1),
                extra_key=lambda p: p["pad_client"].__setitem__("extra", True),
                no_key=lambda p: p["pad_client"].pop("tracker_pad_launch"),
                no_feature=lambda p: p["required_features"].remove(content_plan.PAD_CLIENT_FEATURE),
                no_record=lambda p: p.pop("pad_client")).items():
            with self.subTest(label):
                bad = copy.deepcopy(plan)
                forge(bad)
                with self.assertRaises(OptionError):
                    content_plan.validate(bad)

    def test_a_plan_from_before_the_record_stays_valid(self):
        plan = copy.deepcopy(make_world(client_options()).ctr_content_plan)
        plan.pop("pad_client")
        plan["required_features"].remove(content_plan.PAD_CLIENT_FEATURE)
        self.assertTrue(content_plan.validate(plan))

    def test_tracker_restore(self):
        world = make_world(client_options(race_type_selector="productive", tracker_pad_launch=False), seed=5)
        wire = fill(world)
        tracker = make_world({"race_type_selector": "always", "tracker_pad_launch": True}, seed=999, passthrough=wire)
        self.assertEqual(tracker.options.race_type_selector.value, 0)
        self.assertEqual(tracker.options.tracker_pad_launch.value, 0)
        self.assertEqual(tracker.fill_slot_data(), wire)

    def test_tracker_restore_of_a_plan_without_the_record(self):
        wire = fill(make_world(client_options(), seed=5))
        wire["content_plan"].pop("pad_client")
        wire["content_plan"]["required_features"].remove(content_plan.PAD_CLIENT_FEATURE)
        tracker = make_world({"tracker_pad_launch": True}, seed=999, passthrough=wire)
        self.assertEqual(tracker.options.race_type_selector.value, 1)
        self.assertEqual(tracker.options.tracker_pad_launch.value, 0)

    def test_a_room_without_a_plan_has_none_of_it(self):
        slot = make_world({}, seed=3).fill_slot_data()
        self.assertNotIn("race_type_selector", slot["ctr_options"])
        self.assertNotIn("tracker_pad_launch", slot["ctr_options"])
        self.assertNotIn("content_plan", slot)


class TestPlanWinLogic(unittest.TestCase):
    def test_the_room_carries_the_block(self):
        wire = fill(make_world(client_options(), seed=2))
        self.assertEqual(wire["win_logic"]["version"], 1)
        self.assertTrue(wire["win_logic"]["checks"])

    def test_every_win_kind_is_exported(self):
        world = make_world(client_options(cups=dict(count=7)), seed=2)
        kinds = {e["kind"] for e in wire_block(world)["checks"].values()}
        self.assertLessEqual({"trophy", "ctr", "sapphire", "gold", "gem", "crystal", "boss", "oxide"}, kinds)

    def test_parity_on_every_mix(self):
        for name, extra in MIXES.items():
            for seed in range(3):
                with self.subTest(name, seed=seed):
                    try:
                        world = make_world(client_options(**extra), seed=seed)
                    except OptionError as refused:
                        self.assertNotIn("win_logic", str(refused))
                        continue
                    self.assertEqual(compare(world, random.Random(seed)), [])
                    self.assertLess(wire_size(wire_block(world)), 32 * 1024)
