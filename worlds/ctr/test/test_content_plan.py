"""Real world lifecycle and Tracker reconstruction for content-plan generation."""
import copy
import json
from argparse import Namespace

from BaseClasses import CollectionState, MultiWorld
from Options import OptionError
from worlds.AutoWorld import call_all
from test.general import gen_steps

from .. import ctrAPWorld, content_plan
from . import CTRTestBase
from .test_content_item_pool import small_pool


def profile_options():
    return dict(content_pool=dict(preset="mixed", tracks=dict(retail="all", modes=["trophy"],
                                                            custom=[copy.deepcopy(content_plan.PACKAGES[1])]),
                                  cups=dict(count=0), crystals=dict(count=0), bosses=dict(enabled=False),
                                  required_entries=["custom/baby-t-park/1.0.2"]),
                pad_layout=dict(placement="shuffle", stages="single", mode_order="fixed", merge_trophy_ctr=False),
                item_pool=small_pool(), oxide_goal="disabled", bosses_required_goal=0, gems_required_goal=5,
                character_unlocks=False, podium_placement_checks=False, accessibility="full")


def make_world(options, seed=420, passthrough=None):
    mw = MultiWorld(1)
    mw.game[1] = ctrAPWorld.game
    mw.player_name = {1: "ContentPlan"}
    mw.set_seed(seed)
    mw.seed_name = str(seed)
    args = Namespace()
    for name, cls in ctrAPWorld.options_dataclass.type_hints.items():
        setattr(args, name, {1: cls.from_any(copy.deepcopy(options.get(name, cls.default)))})
    mw.set_options(args)
    if passthrough:
        mw.re_gen_passthrough = {ctrAPWorld.game: passthrough}
        mw.generation_is_fake = True
    mw.state = CollectionState(mw)
    for step in gen_steps:
        call_all(mw, step)
    return mw.worlds[1]


class TestContentPlan(CTRTestBase):
    options = profile_options()

    def test_generated_plan_has_real_package_and_independent_supply(self):
        plan = self.world.ctr_content_plan
        self.assertTrue(content_plan.validate(plan))
        self.assertEqual(len(plan["checks"]), 19)
        self.assertEqual(len(self.multiworld.get_locations(1)), 19)
        self.assertEqual(len(self.multiworld.itempool), 19)
        self.assertEqual(plan["items"]["filler_count"], 5)
        self.assertEqual(len([p for p in plan["pads"] if p["kind"] == "normal" and p["entry_id"] is None]), 8)
        self.assertIn("Custom Track 1: Trophy Race", [loc.name for loc in self.multiworld.get_locations(1)])
        self.assertEqual(plan["packages"], [content_plan.PACKAGES[1]])
        self.assertEqual(sum(item.name == "Key" for item in self.multiworld.itempool), 4)
        self.assertEqual(sum(item.name.endswith(" Gem") for item in self.multiworld.itempool), 5)
        self.assertEqual(len(self.multiworld.precollected_items[1]), 0)
        self.assertFalse(hasattr(self.world, "_ctr_backstop_fired"))

    def test_tracker_uses_wire_without_reroll(self):
        wire = json.loads(json.dumps(self.world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, self.world.ctr_content_plan)
        self.assertEqual(other.fill_slot_data(), wire)
        for key_count in range(5):
            expected, actual = [], []
            for world, target in ((self.world, expected), (other, actual)):
                state = CollectionState(world.multiworld)
                for _ in range(key_count):
                    state.collect(world.create_item("Key"), True)
                target.extend(sorted(loc.address for loc in world.multiworld.get_reachable_locations(state, 1)))
            self.assertEqual(actual, expected)

    def test_exact_extras_do_not_change_selected_content(self):
        base = make_world(profile_options())
        options = profile_options()
        options["item_pool"]["extra"] = {"keys": 2, "trophies": 1, "gems": {"red": 1}}
        extra = make_world(options)
        self.assertEqual(base.ctr_content_plan["pads"], extra.ctr_content_plan["pads"])
        self.assertEqual(base.ctr_content_plan["checks"], extra.ctr_content_plan["checks"])
        self.assertEqual(extra.ctr_content_plan["items"]["filler_count"], 1)
        self.assertEqual(base.ctr_content_plan["goal"], extra.ctr_content_plan["goal"])

    def test_empty_pad_draw_retains_a_playable_start(self):
        from Fill import distribute_items_restrictive
        # Before the feasible-placement guard, this real seed left all five
        # N. Sanity pads empty, although nineteen entries were selected.
        world = make_world(profile_options(), seed=693)
        self.assertGreater(len(world.multiworld.get_reachable_locations()), 0)
        self.assertEqual(len(world.multiworld.precollected_items[1]), 0)
        distribute_items_restrictive(world.multiworld)
        self.assertTrue(world.multiworld.can_beat_game())
        self.assertEqual(len(world.ctr_content_plan["tracks"]), 19)
        self.assertEqual(world.ctr_content_plan["items"]["filler_count"], 5)

    def test_wire_rejects_semantic_forgery(self):
        original = self.world.fill_slot_data()
        def corrupt_pad(w): w["content_plan"]["pads"][0]["hub_id"] = "hub:99"
        def corrupt_check(w): w["content_plan"]["checks"][0]["location"] = 35011204
        def corrupt_route(w): w["content_plan"]["checks"][0]["routes"][0]["award"] = "finish_any"
        def corrupt_package(w): w["content_plan"]["packages"][0]["files"][0]["sha256"] = "0" * 64
        def corrupt_supply(w): w["content_plan"]["items"]["rows"][0]["remaining"] += 1
        def corrupt_keys(w): w["content_plan"]["items"]["rows"][-1]["base"] = 3
        def corrupt_boolean(w): w["content_plan"]["pads"][0]["mode_gates"][0]["stage"] = True
        for mutate in (corrupt_pad, corrupt_check, corrupt_route, corrupt_package, corrupt_supply, corrupt_keys):
            wire = copy.deepcopy(original)
            mutate(wire)
            with self.subTest(mutation=mutate.__name__), self.assertRaises(OptionError):
                make_world({}, passthrough=wire)
        wire = copy.deepcopy(original)
        next(p for p in wire["content_plan"]["pads"] if p["mode_gates"])["mode_gates"][0]["stage"] = True
        with self.assertRaises(OptionError):
            make_world({}, passthrough=wire)

    def test_capacity_and_unsupported_requests_do_not_downgrade(self):
        options = profile_options()
        options["item_pool"]["extra"] = {"keys": 6}
        with self.assertRaisesRegex(OptionError, "Short by 1 checks"):
            make_world(options)
        options = profile_options()
        options["content_pool"]["cups"]["count"] = 1
        with self.assertRaisesRegex(OptionError, "not implemented"):
            make_world(options)
