"""The alpha3 data package traps and Trap Display (ruled 2026-11-06).

Seven traps join the weighted filler draw with stable keys, and `trap_display`
rides the content-plan envelope only when it is not `shown`, so an option-off
room's slot_data is unchanged. The paired native reader is
ap/ap_trap_display_logic.h (tools/test-trap-display.c).
"""
import copy
import json
import unittest

from BaseClasses import ItemClassification
from Options import OptionError

from .. import content_plan
from ..Options import ContentItemPool, TrapDisplay, TrapWeights, ap_ctr_option_groups
from ..traps import DEFAULT_TRAP_WEIGHTS, TRAP_REGISTRY, TRAP_WEIGHT_KEYS
from .test_content_plan import make_world
from .test_item_packs import pack_options

ALPHA3 = {
    "always_jumping": ("Always Jumping", 35010208, 3),
    "no_drifting": ("No Drifting", 35010209, 3),
    "rival_surge": ("Rival Surge", 35010210, 3),
    "mud_season": ("Mud Season", 35010211, 3),
    "limp_mode": ("Limp Mode", 35010212, 3),
    "stuck_steering": ("Stuck Steering", 35010213, 1),
    "wumpa_leak": ("Wumpa Leak", 35010214, 4),
}


class TestAlpha3TrapRegistry(unittest.TestCase):
    def test_rows_keys_weights_in_native_order(self):
        tail = TRAP_REGISTRY[-7:]
        self.assertEqual([e.key for e in tail], list(ALPHA3))
        for entry in tail:
            name, _code, weight = ALPHA3[entry.key]
            self.assertEqual((entry.name, entry.weight, entry.buildable), (name, weight, True))
            self.assertEqual(DEFAULT_TRAP_WEIGHTS[entry.key], weight)

    def test_help_text_names_every_new_key(self):
        for key in ALPHA3:
            self.assertIn(f"`{key}`", TrapWeights.__doc__)
        self.assertIn("Stuck Steering (always 7 seconds)", " ".join(TrapWeights.__doc__.split()))

    def test_item_pool_help_has_the_extra_example(self):
        doc = ContentItemPool.__doc__
        self.assertIn("exact counts, not percentages", " ".join(doc.split()))
        self.assertIn("trophies: 4", doc)
        self.assertIn("keys: 2", doc)


class TestEachAlpha3TrapDraws(unittest.TestCase):
    def test_each_trap_alone_fills_the_traps(self):
        for key, (name, code, _w) in ALPHA3.items():
            with self.subTest(key=key):
                world = make_world(pack_options(trap_fill_percentage=100,
                                                trap_weights={k: int(k == key) for k in TRAP_WEIGHT_KEYS}),
                                   seed=7)
                traps = {(i.name, i.code) for i in world.multiworld.itempool
                         if i.player == world.player and i.classification == ItemClassification.trap}
                self.assertEqual(traps, {(name, code)})
                self.assertEqual(world.fill_slot_data()["trap_identities"]["items"][str(code)], key)


class TestTrapDisplay(unittest.TestCase):
    def test_default_shown_and_grouped(self):
        self.assertEqual(TrapDisplay.default, 0)
        self.assertEqual((TrapDisplay.option_shown, TrapDisplay.option_as_progression,
                          TrapDisplay.option_mixed), (0, 1, 2))
        self.assertIn(TrapDisplay, ap_ctr_option_groups["Items and Traps"])

    def test_shown_sends_no_key(self):
        co = make_world(pack_options(), seed=3).fill_slot_data()["ctr_options"]
        for key in content_plan.TRAP_DISPLAY_KEYS:
            self.assertNotIn(key, co)

    def test_as_progression_adds_one_key_and_takes_no_draw(self):
        base = make_world(pack_options(), seed=3).fill_slot_data()
        wire = make_world(pack_options(trap_display="as_progression"), seed=3).fill_slot_data()
        self.assertEqual(wire["ctr_options"].pop("trap_display"), 1)
        self.assertNotIn("trap_display_salt", wire["ctr_options"])
        self.assertEqual(json.dumps(wire, sort_keys=True), json.dumps(base, sort_keys=True))

    def test_mixed_adds_mode_and_salt_and_takes_no_draw(self):
        base = make_world(pack_options(), seed=3).fill_slot_data()
        wire = make_world(pack_options(trap_display="mixed"), seed=3).fill_slot_data()
        again = make_world(pack_options(trap_display="mixed"), seed=3).fill_slot_data()
        self.assertEqual(wire, again)
        self.assertEqual(wire["ctr_options"].pop("trap_display"), 2)
        salt = wire["ctr_options"].pop("trap_display_salt")
        self.assertTrue(0 <= salt <= content_plan.TRAP_DISPLAY_SALT_MAX)
        self.assertEqual(json.dumps(wire, sort_keys=True), json.dumps(base, sort_keys=True))

    def test_tracker_restores_mode_and_salt(self):
        for mode in ("as_progression", "mixed"):
            with self.subTest(mode=mode):
                world = make_world(pack_options(trap_display=mode), seed=11)
                wire = json.loads(json.dumps(world.fill_slot_data()))
                other = make_world({}, seed=999, passthrough=wire)
                self.assertEqual(other.options.trap_display.value, TrapDisplay.options[mode])
                self.assertEqual(other.fill_slot_data(), wire)

    def test_bad_values_refuse_on_restore(self):
        wire = json.loads(json.dumps(make_world(pack_options(trap_display="mixed"), seed=3).fill_slot_data()))
        forgeries = (("trap_display", 0), ("trap_display", 3), ("trap_display", True),
                     ("trap_display_salt", -1), ("trap_display_salt", "1"), ("trap_display_salt", 2 ** 31))
        for key, value in forgeries:
            forged = copy.deepcopy(wire)
            forged["ctr_options"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)
        forged = copy.deepcopy(wire)
        forged["ctr_options"]["trap_display"] = 1
        with self.assertRaises(OptionError):
            make_world({}, seed=999, passthrough=forged)


if __name__ == "__main__":
    unittest.main()
