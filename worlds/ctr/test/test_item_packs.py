"""Pool-only packs and the content-plan envelope (#133 PR 4a).

Progressive Starting Wumpa, Turbo Grant and Tizi Helper add no location and no
rule. In a content plan they take item ledger rows, sized by the optional plan
record `item_packs`, and use slots that would otherwise be filler, as on the
legacy path. An explicit DeathLink send list and the two warp-pad display
settings ride optional `ctr_options` keys; the `trap_identities` block rides
every content-plan room, as it does every schema-18 room. The paired native
parser applies the same rules (native tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest

from Options import OptionError

from .. import content_plan, traps
from .test_content_plan import make_world, profile_options
from .test_track_checks import check_options

PSW, TURBO, TIZI = 35010122, 35010189, 35010188


def pack_options(psw=3, turbo=True, tizi=True, **extra):
    options = check_options(rungs=False)
    options.update(progressive_starting_wumpa=psw, turbo_grant=turbo, tizi_helper=tizi, **extra)
    return options


def rows_of(plan):
    return {row["item"]: row for row in plan["items"]["rows"]}


def pool_names(world):
    return [item.name for item in world.multiworld.itempool if item.player == world.player]


class TestOffKeepsTheWire(unittest.TestCase):
    def test_no_pack_means_no_record_no_feature_no_row(self):
        world = make_world(pack_options(psw=0, turbo=False, tizi=False), seed=4)
        plan = world.ctr_content_plan
        self.assertNotIn("item_packs", plan)
        self.assertNotIn(content_plan.PACK_FEATURE, plan["required_features"])
        self.assertFalse({PSW, TURBO, TIZI} & set(rows_of(plan)))

    def test_default_envelope_has_no_optional_key(self):
        wire = make_world(profile_options(), seed=4).fill_slot_data()
        self.assertFalse(set(content_plan.ENVELOPE_OPTIONAL) & set(wire["ctr_options"]))

    def test_packs_take_no_draw(self):
        # The plan apart from the ledger and the record is the same seed.
        off = make_world(pack_options(psw=0, turbo=False, tizi=False), seed=9).ctr_content_plan
        on = make_world(pack_options(), seed=9).ctr_content_plan
        for key in ("tracks", "entries", "pads", "checks", "requirements"):
            self.assertEqual(on[key], off[key], key)


class TestPacks(unittest.TestCase):
    def test_record_rows_and_pool(self):
        off = make_world(pack_options(psw=0, turbo=False, tizi=False), seed=5)
        world = make_world(pack_options(psw=4), seed=5)
        plan = world.ctr_content_plan
        self.assertEqual(plan["item_packs"], dict(progressive_starting_wumpa=4, turbo_grant=True, tizi_helper=True))
        self.assertIn(content_plan.PACK_FEATURE, plan["required_features"])
        rows = rows_of(plan)
        for code, count in ((PSW, 4), (TURBO, 1), (TIZI, 1)):
            self.assertEqual((rows[code]["base"], rows[code]["extra"], rows[code]["remaining"]), (count, 0, count))
        names = pool_names(world)
        self.assertEqual((names.count("Progressive Starting Wumpa"), names.count("Turbo Grant"),
                          names.count("Tizi Helper")), (4, 1, 1))
        # Six filler slots became the six pack items; no location was added.
        self.assertEqual(plan["items"]["filler_count"], off.ctr_content_plan["items"]["filler_count"] - 6)
        self.assertEqual(len(world.multiworld.get_locations(1)), len(off.multiworld.get_locations(1)))
        self.assertTrue(content_plan.validate(plan))

    def test_each_pack_alone(self):
        for psw, turbo, tizi, record in ((10, False, False, dict(progressive_starting_wumpa=10)),
                                         (0, True, False, dict(turbo_grant=True)),
                                         (0, False, True, dict(tizi_helper=True))):
            with self.subTest(record=record):
                plan = make_world(pack_options(psw=psw, turbo=turbo, tizi=tizi), seed=6).ctr_content_plan
                self.assertEqual(plan["item_packs"], record)

    def test_pack_items_can_start_from_the_pool(self):
        world = make_world(pack_options(start_inventory_from_pool={"Turbo Grant": 1}), seed=7)
        row = rows_of(world.ctr_content_plan)[TURBO]
        self.assertEqual((row["start_from_pool"], row["remaining"]), (1, 0))
        self.assertNotIn("Turbo Grant", pool_names(world))

    def test_a_full_pool_refuses_instead_of_dropping_a_pack(self):
        options = profile_options()
        options.update(progressive_starting_wumpa=10, turbo_grant=True)
        with self.assertRaisesRegex(OptionError, "Short by"):
            make_world(options)

    def test_forged_records_and_rows_refuse(self):
        wire = make_world(pack_options(psw=2), seed=8).fill_slot_data()

        def row(p, code):
            return next(r for r in p["items"]["rows"] if r["item"] == code)

        def more_wumpa(p):
            row(p, PSW).update(base=3, remaining=3, receipt_cap=3, requirement_ceiling=3)
            p["items"]["filler_count"] -= 1

        def drop_turbo_row(p):
            p["items"]["rows"].remove(row(p, TURBO))
            p["items"]["filler_count"] += 1

        def drop_record(p):
            p.pop("item_packs")
            p["required_features"].remove(content_plan.PACK_FEATURE)

        mutations = {
            "count disagrees with row": lambda p: p["item_packs"].__setitem__("progressive_starting_wumpa", 3),
            "row disagrees with count": more_wumpa,
            "count as Boolean": lambda p: p["item_packs"].__setitem__("progressive_starting_wumpa", True),
            "count above ten": lambda p: p["item_packs"].__setitem__("progressive_starting_wumpa", 11),
            "count zero": lambda p: p["item_packs"].__setitem__("progressive_starting_wumpa", 0),
            "grant false": lambda p: p["item_packs"].__setitem__("turbo_grant", False),
            "grant as integer": lambda p: p["item_packs"].__setitem__("tizi_helper", 1),
            "unknown pack": lambda p: p["item_packs"].__setitem__("itemsanity", True),
            "empty record": lambda p: p.__setitem__("item_packs", {}),
            "row without record": drop_record,
            "record without row": drop_turbo_row,
            "feature dropped": lambda p: p["required_features"].remove(content_plan.PACK_FEATURE),
            "extra copy": lambda p: row(p, TIZI).update(extra=1, remaining=2, receipt_cap=2),
        }
        for name, mutate in mutations.items():
            forged = copy.deepcopy(wire)
            mutate(forged["content_plan"])
            with self.subTest(mutation=name), self.assertRaises(OptionError):
                content_plan.validate(forged["content_plan"])


class TestEnvelope(unittest.TestCase):
    def test_explicit_send_list_and_display_keys(self):
        options = pack_options(psw=0, turbo=False, tizi=False, death_link="race_loss",
                               death_link_send=["weapon_hit", "race_loss"],
                               warp_pad_item_display="by_reward_type", ap_item_type_colors=False)
        co = make_world(options, seed=3).fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link_send"], co["warp_pad_item_display"], co["ap_item_type_colors"]), (6, 1, False))

    def test_empty_send_list_is_receive_only(self):
        co = make_world(pack_options(death_link="mask_reset", death_link_send=[]), seed=3).fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co["death_link_send"]), (1, 0))

    def test_no_one_way_deathlink(self):
        # Ruling 2026-09-30, as on a normal seed: sending implies receiving.
        co = make_world(pack_options(death_link="off", death_link_send=["mask_grab"]), seed=3).fill_slot_data()["ctr_options"]
        self.assertEqual((co["death_link"], co["death_link_send"]), (1, 1))

    def test_weapon_hit_rides_the_envelope(self):
        # #483: death_link 4 on a content-plan room, coupled to mask grabs, and
        # the tracker restores the room from it.
        world = make_world(pack_options(death_link="weapon_hit"), seed=3)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        self.assertEqual((wire["ctr_options"]["death_link"], wire["ctr_options"].get("death_link_send")), (4, None))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.fill_slot_data(), wire)

    def test_tracker_yaml_cannot_change_an_omitted_send_mask(self):
        # Finding 4 of the 0.3.0 review: a seed that omitted death_link_send
        # follows death_link; the tracking player's own YAML must not leak in.
        world = make_world(pack_options(death_link="mask_reset"), seed=3)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        self.assertNotIn("death_link_send", wire["ctr_options"])
        for yaml_value in ([], ["weapon_hit", "race_loss"]):
            with self.subTest(tracker_yaml=yaml_value):
                other = make_world({"death_link_send": yaml_value}, seed=999, passthrough=wire)
                self.assertEqual(other.options.death_link_send.value, {"follow_death_link"})
                self.assertEqual(other.fill_slot_data(), wire)

    def test_trap_identities_on_every_room(self):
        world = make_world(profile_options(), seed=3)
        self.assertEqual(world.fill_slot_data()["trap_identities"], traps.trap_identities_block(world.item_name_to_id))

    def test_bad_envelope_values_refuse_on_restore(self):
        wire = json.loads(json.dumps(make_world(pack_options(), seed=3).fill_slot_data()))
        for key, value in (("death_link", 5), ("death_link", True), ("death_link_send", 8), ("death_link_send", True), ("death_link_send", -1),
                           ("warp_pad_item_display", 2), ("warp_pad_item_display", False),
                           ("ap_item_type_colors", 1)):
            forged = copy.deepcopy(wire)
            forged["ctr_options"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(OptionError):
                make_world({}, seed=999, passthrough=forged)


class TestTrackerAndFill(unittest.TestCase):
    def test_tracker_restores_packs_and_envelope(self):
        options = pack_options(psw=5, death_link="any_hit", death_link_send=["race_loss"],
                               warp_pad_item_display="by_reward_type", ap_item_type_colors=False)
        world = make_world(options, seed=11)
        wire = json.loads(json.dumps(world.fill_slot_data()))
        other = make_world({}, seed=999, passthrough=wire)
        self.assertEqual(other.ctr_content_plan, world.ctr_content_plan)
        self.assertEqual(other.fill_slot_data(), wire)
        # The ledger items; filler and traps are drawn again by the tracker.
        self.assertEqual(other.ctr_content_items.selected_names(), world.ctr_content_items.selected_names())
        self.assertEqual((other.options.progressive_starting_wumpa.value, other.options.turbo_grant.value,
                          other.options.tizi_helper.value), (5, 1, 1))

    def test_seeds_fill_and_beat(self):
        from Fill import distribute_items_restrictive
        for seed in range(8):
            options = pack_options(psw=seed % 11, turbo=bool(seed % 2), tizi=seed % 3 != 0,
                                   wumpa_check=("off", "global", "per_track")[seed % 3])
            world = make_world(options, seed=seed)
            with self.subTest(seed=seed):
                distribute_items_restrictive(world.multiworld)
                self.assertTrue(world.multiworld.can_beat_game())
                self.assertEqual(len(world.multiworld.precollected_items[1]), 0)


if __name__ == "__main__":
    unittest.main()
