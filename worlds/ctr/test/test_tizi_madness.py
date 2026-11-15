"""Tizi Madness: hard shortcut knowledge only, and the Mask with Itemsanity (A4-96).

Ruling of 2026-11-14, 23:03 to 23:06 CET (tizi_madness.py). The track is
Coco Team Racing track 3 as the client imports it; it is recognised by its LEV
and VRM pins, never by its title.
"""
import copy
import json
import unittest

from BaseClasses import CollectionState

from .. import content_cups, content_plan, custom_packages, tizi_madness
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN, options_with

TIZI_ID = "custom/cocoteamracing-track-3/1.0.0"
SK = {"easy": 0, "medium": 1, "hard": 2}


def tizi_descriptor(**changes):
    """The descriptor Play Solo writes for the imported track (pins from the
    A4-39 import, title and credit from A4-95)."""
    d = dict(id="package/cocoteamracing-track-3/1.0.0", content_id="cocoteamracing-track-3",
             uuid="3c0c0a00-0000-4000-8000-000000000003", revision="1.0.0",
             display_name="Tizi Madness", author="FrostedWombat", laps=3,
             capabilities=dict(time_trial=True, arcade=True, relic=False, ctr_tokens=True, wumpa=False),
             files=[dict(role="lev", sha256=tizi_madness.LEV_SHA256, bytes=888368, format="ctr-lev",
                         format_version=1),
                    dict(role="vrm", sha256=tizi_madness.VRM_SHA256, bytes=458808, format="ctr-vrm",
                         format_version=1)],
             evidence=[],
             locator=dict(kind="xdelta", patch_sha256=tizi_madness.PATCH_SHA256,
                          bigfile_index=tizi_madness.BIGFILE_INDEX, patch_name="CocoTeamRacing.xdelta"))
    d.update(changes)
    return d


def renamed_copy():
    """The same bytes under another title, key and uuid: a player's rename."""
    return tizi_descriptor(id="package/my-mask-track/2.0", content_id="my-mask-track", revision="2.0",
                           uuid="11111111-2222-4333-8444-555555555555", display_name="My Mask Track",
                           author="Someone")


def impostor():
    """Another track that happens to be titled Tizi Madness."""
    d = copy.deepcopy(UNKNOWN)
    d.update(id="package/tizi-madness/1.0", content_id="tizi-madness", revision="1.0",
             uuid="99999999-2222-4333-8444-555555555555", display_name="Tizi Madness")
    return d


def world_with(descriptor, sk, itemsanity=False, required=True, seed=7, **extra):
    custom = [descriptor]
    tid = f"custom/{descriptor['content_id']}/{descriptor['revision']}"
    options = options_with(custom, required=[tid] if required else [])
    options.update(shortcut_knowledge=SK[sk], itemsanity=itemsanity, **extra)
    return make_world(options, seed=seed)


def plan_has(plan, descriptor):
    tid = f"custom/{descriptor['content_id']}/{descriptor['revision']}"
    return tid in {t["id"] for t in plan["tracks"]} or descriptor["id"] in {p["id"] for p in plan["packages"]}


class TestIdentity(unittest.TestCase):
    def test_the_pins_are_the_imported_track(self):
        package = custom_packages.admit(tizi_descriptor())
        self.assertTrue(tizi_madness.is_tizi_madness(package))
        self.assertTrue(tizi_madness.is_tizi_madness(custom_packages.admit(renamed_copy())))

    def test_a_title_is_never_an_identity(self):
        self.assertFalse(tizi_madness.is_tizi_madness(custom_packages.admit(impostor())))

    def test_one_pin_is_not_enough(self):
        for i in (0, 1):
            d = tizi_descriptor()
            d["files"][i]["sha256"] = "ab" * 32
            with self.subTest(changed=d["files"][i]["role"]):
                self.assertFalse(tizi_madness.is_tizi_madness(custom_packages.admit(d)))
        self.assertFalse(tizi_madness.is_tizi_madness(None))

    def test_native_holds_the_same_pair(self):
        # include/platform/native_tizi_madness.h and native_track_sources.inc
        # (BIGFILE 47 of the Coco patch); the native harness pins its side.
        self.assertEqual(tizi_madness.LEV_SHA256,
                         "3e80b47339d243db00acc33d6b7eb9efb15eaf946aa830b1766d56f5b1c15e42")
        self.assertEqual(tizi_madness.VRM_SHA256,
                         "74c00036dd24a34134c76236ae89dba1f3caa4b67bb30ca5717988b8987bf6ce")


class TestHardOnly(unittest.TestCase):
    def test_easy_and_medium_leave_the_track_out(self):
        for sk in ("easy", "medium"):
            for descriptor in (tizi_descriptor(), renamed_copy()):
                with self.subTest(sk=sk, title=descriptor["display_name"]):
                    world = world_with(descriptor, sk)
                    plan = world.ctr_content_plan
                    self.assertFalse(plan_has(plan, descriptor))
                    self.assertNotIn(tizi_madness.LEV_SHA256, json.dumps(plan))
                    self.assertEqual(world.ctr_tizi_madness_left_out, [descriptor["id"]])
                    self.assertEqual(world.options.required_entries.value, [])

    def test_hard_keeps_it(self):
        world = world_with(tizi_descriptor(), "hard")
        self.assertTrue(plan_has(world.ctr_content_plan, tizi_descriptor()))
        self.assertFalse(hasattr(world, "ctr_tizi_madness_left_out"))

    def test_an_impostor_title_stays_in_easy(self):
        world = world_with(impostor(), "easy")
        self.assertTrue(plan_has(world.ctr_content_plan, impostor()))

    def test_names_other_options_give_it_go_with_it(self):
        # track_modes and required_entries by title or key, as a player writes them.
        for name in ("Tizi Madness", "cocoteamracing-track-3"):
            with self.subTest(name=name):
                options = options_with([tizi_descriptor(), copy.deepcopy(content_plan.PACKAGES[1])],
                                       required=[name, "custom/baby-t-park/1.0.2"])
                options.update(shortcut_knowledge=0, track_modes={name: ["trophy"]})
                world = make_world(options, seed=3)
                self.assertFalse(plan_has(world.ctr_content_plan, tizi_descriptor()))
                self.assertEqual(len(world.options.required_entries.value), 1)
                self.assertFalse({"Tizi Madness", "cocoteamracing-track-3"} & set(world.options.required_entries.value))
                self.assertNotIn(name, world.options.track_modes.value)

    def test_the_rest_of_the_seed_is_unchanged(self):
        # Easy with Tizi Madness listed draws exactly the seed without it.
        base = copy.deepcopy(content_plan.PACKAGES[1])
        with_it = options_with([tizi_descriptor(), base], required=["custom/baby-t-park/1.0.2"])
        with_it.update(shortcut_knowledge=0)
        without = options_with([copy.deepcopy(base)], required=["custom/baby-t-park/1.0.2"])
        without.update(shortcut_knowledge=0)
        for seed in (1, 2):
            with self.subTest(seed=seed):
                a = make_world(with_it, seed=seed).ctr_content_plan
                b = make_world(without, seed=seed).ctr_content_plan
                self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_a_malformed_descriptor_still_gets_its_own_error(self):
        from Options import OptionError
        bad = tizi_descriptor(laps=99)
        options = options_with([bad], required=[])
        options.update(shortcut_knowledge=0)
        with self.assertRaises((OptionError, custom_packages.PackageError)) as caught:
            make_world(options, seed=1)
        self.assertIn("laps", str(caught.exception))


def items_but(world, *left_out):
    """Ten copies of every item this world knows, except `left_out`: more than
    any gate asks for, so only the left-out item can close one."""
    state = CollectionState(world.multiworld)
    for name in world.item_name_to_id:
        if name not in left_out:
            for _ in range(10):
                state.collect(world.create_item(name), True)
    return state


def names_in(term):
    """Item names the Has terms of an installed term ask for."""
    from .. import logic_terms
    out = set()
    if isinstance(term, logic_terms.Has):
        out.add(term.item)
    for value in vars(term).values():
        for child in (value if isinstance(value, (list, tuple)) else (value,)):
            if isinstance(child, logic_terms.Term):
                out |= names_in(child)
    return out


class TestMaskLogic(unittest.TestCase):
    def tizi_pad(self, world):
        plan = world.ctr_content_plan
        entry = next(e for e in plan["entries"] if e.get("track_id") == TIZI_ID)
        return next(p for p in plan["pads"] if p["entry_id"] == entry["id"]), entry

    def test_itemsanity_gates_every_check_on_the_track_on_the_mask(self):
        world = world_with(tizi_descriptor(), "hard", itemsanity=True)
        mw, player = world.multiworld, world.player
        pad, entry = self.tizi_pad(world)
        self.assertEqual(tizi_madness.mask_gated_entries(world.ctr_content_plan), {entry["id"]})
        entrance = mw.get_entrance(pad["id"], player)
        self.assertFalse(entrance.access_rule(items_but(world, "Mask")))
        self.assertTrue(entrance.access_rule(items_but(world)))
        checks = [c for c in world.ctr_content_plan["checks"] if c["owner"] == TIZI_ID]
        self.assertTrue(checks)
        without, with_all = items_but(world, "Mask"), items_but(world)
        for check in checks:
            location = mw.get_location(content_plan.LOCATION_BY_CODE[check["location"]], player)
            with self.subTest(location=location.name):
                self.assertFalse(location.can_reach(without))
                self.assertTrue(location.can_reach(with_all))

    def test_other_pads_do_not_need_the_mask(self):
        world = world_with(tizi_descriptor(), "hard", itemsanity=True)
        mw, player = world.multiworld, world.player
        tizi, _entry = self.tizi_pad(world)
        state = items_but(world, "Mask")
        others = [p for p in world.ctr_content_plan["pads"] if p["entry_id"] is not None and p["id"] != tizi["id"]]
        self.assertTrue(others)
        self.assertTrue(all(mw.get_entrance(p["id"], player).access_rule(state) for p in others))

    def test_without_itemsanity_no_item_is_needed(self):
        world = world_with(tizi_descriptor(), "hard", itemsanity=False)
        self.assertEqual(tizi_madness.mask_gated_entries(world.ctr_content_plan), frozenset())
        pad, _entry = self.tizi_pad(world)
        self.assertTrue(world.multiworld.get_entrance(pad["id"], world.player).access_rule(items_but(world)))

    def test_the_gate_is_in_the_exported_win_logic(self):
        # Native's DeathLink stakes read the exported terms (Contract 7m): the
        # entrance term names the Mask, so the game and the logic agree.
        from .. import logic_terms
        world = world_with(tizi_descriptor(), "hard", itemsanity=True)
        pad, _entry = self.tizi_pad(world)
        self.assertIn("Mask", names_in(logic_terms.term_of(world.multiworld.get_entrance(pad["id"], world.player))))
        plain = world_with(tizi_descriptor(), "hard", itemsanity=False)
        pad, _entry = self.tizi_pad(plain)
        self.assertNotIn("Mask", names_in(logic_terms.term_of(plain.multiworld.get_entrance(pad["id"], plain.player))))


class TestBossAndCupRoutes(unittest.TestCase):
    """A boss race or Gem Cup on Tizi Madness waits for the Mask too."""

    def test_boss_and_cup_entries_on_the_track_need_the_mask(self):
        from .test_content_bosses import boss_options
        seen = set()
        for seed in range(40):
            options = boss_options(boss_track_shuffle=True, itemsanity=True, shortcut_knowledge=SK["hard"])
            options["item_pool"]["base"]["trophies"] = 12
            options["content_pool"]["cups"] = dict(count=dict(min=2, max=3))
            descriptor = tizi_descriptor()
            descriptor["capabilities"].update(checkpoints=35, ai_nav=True)
            options["content_pool"]["tracks"]["custom"] = [descriptor]
            options["content_pool"]["required_entries"] = []
            world = make_world(options, seed=seed)
            plan, mw, player = world.ctr_content_plan, world.multiworld, world.player
            gated = tizi_madness.mask_gated_entries(plan)
            without, with_all = items_but(world, "Mask"), items_but(world)
            for enc in plan["encounters"]:
                if enc["entry_id"] in gated:
                    seen.add("boss")
                    entrance = mw.get_entrance(enc["id"], player)
                    self.assertFalse(entrance.access_rule(without), enc["id"])
                    self.assertTrue(entrance.access_rule(with_all), enc["id"])
            for pad in plan["pads"]:
                entry = next((e for e in plan["entries"] if e["id"] == pad["entry_id"]), None)
                if entry is not None and entry["kind"] == content_cups.KIND and entry["id"] in gated:
                    seen.add("cup")
                    self.assertFalse(mw.get_entrance(pad["id"], player).access_rule(without), pad["id"])
            if seen == {"boss", "cup"}:
                break
        self.assertEqual(seen, {"boss", "cup"})


class TestGatedEntries(unittest.TestCase):
    """mask_gated_entries on hand-made plans: cups and boss races."""

    @staticmethod
    def plan(entries, itemsanity=True):
        packages = [custom_packages.admit(tizi_descriptor()), custom_packages.admit(impostor())]
        tracks = [dict(id=TIZI_ID, package_id=packages[0]["id"]),
                  dict(id="custom/tizi-madness/1.0", package_id=packages[1]["id"]),
                  dict(id="retail:0")]
        return dict(packages=packages, tracks=tracks, entries=entries,
                    global_checks=dict(itemsanity=itemsanity))

    def test_track_cup_and_boss_entries(self):
        entries = [dict(id="e/track", kind="track", track_id=TIZI_ID),
                   dict(id="e/impostor", kind="track", track_id="custom/tizi-madness/1.0"),
                   dict(id="e/retail", kind="track", track_id="retail:0"),
                   dict(id="e/cup", kind=content_cups.KIND,
                        legs=[dict(id="e/cup/leg:0", track_id="retail:0"), dict(id="e/cup/leg:1", track_id=TIZI_ID)]),
                   dict(id="e/cup2", kind=content_cups.KIND, legs=[dict(id="e/cup2/leg:0", track_id="retail:0")]),
                   dict(id="e/boss", kind="boss_race", track_id=TIZI_ID),
                   dict(id="e/arena", kind="crystal", arena_id=1)]
        self.assertEqual(tizi_madness.mask_gated_entries(self.plan(entries)), {"e/track", "e/cup", "e/boss"})
        self.assertEqual(tizi_madness.mask_gated_entries(self.plan(entries, itemsanity=False)), frozenset())


if __name__ == "__main__":
    unittest.main()
