"""#306 B+ and named blocks as Universal Tracker and the room see them.

B+ (generic slot ids, any track): the room title travels in slot_data
(`custom_track_titles`, schema 18, or the content plan's `room_title`). UT's
regeneration renames the aliased locations to that title, CTR rules keep
working because they hold Location objects, and the room datapackage copy
renames the custom letter items too.

C (named block): a track whose key has a block uses its ids and frozen name.
The fixture rows are TEST DATA ONLY.
"""
import copy
import unittest
from unittest.mock import patch

from BaseClasses import CollectionState
from Fill import distribute_items_restrictive
from test.general import gen_steps, setup_multiworld
from worlds.AutoWorld import call_all

from .. import content_plan, ctrAPWorld, destinations
from ..custom_check_namespace import custom_check_code
from ..custom_track_datapackage import embed_track_names
from ..custom_tracks import BABY_T_PARK_CURRENT
from ..named_tracks import location_code
from .test_content_plan import make_world, profile_options
from .test_named_tracks import fixture_tracks

GAME = ctrAPWorld.game
#: Legacy-path room title of the compiled Baby T Park package on the generic
#: slot path (B+): the tests below take the legacy path off its named block
#: while the block's names stay registered, so the clash rule adds the track
#: key as author (a generic slot never shows a named track's own name).
LEGACY_TITLE = "Baby T Park (Custom, baby-t-park)"
#: Registry block of baby-t-park in data/named_tracks.json.
BABY_T_PARK_BLOCK = 8
STEPS = ("generate_early", "create_regions", "create_items", "set_rules")


def legacy_options(**descriptor_extra):
    entry = copy.deepcopy(BABY_T_PARK_CURRENT)
    entry["modes"] = {"ctr_challenge": True}
    entry.update(descriptor_extra)
    return {"accessibility": "full", "lettersanity": "locations_and_items",
            "custom_tracks": {"baby-t-park": entry}}


def tracker_for(wire, seed):
    tracker = setup_multiworld(ctrAPWorld, steps=(), seed=seed, options={})
    tracker.re_gen_passthrough = {GAME: wire}
    tracker.generation_is_fake = True
    for step in STEPS + ("generate_basic",):
        call_all(tracker, step)
    return tracker


def reachable(multiworld, names):
    state = CollectionState(multiworld)
    for name in names:
        state.collect(multiworld.worlds[1].create_item(name), True)
    return {loc.address for loc in multiworld.get_locations(1)
            if loc.address is not None and loc.can_reach(state)}


class TestLegacyPathTitles(unittest.TestCase):
    """B+ on the legacy path: a track without a named block keeps its generic
    slot ids and gets its room title. Baby T Park has block 8 in this build, so
    these tests hide the block from the legacy path (test only) while its
    names stay registered; the named path is TestLegacyPathNamedBlock below."""
    seed = 20261013

    def setUp(self):
        rest = {k: t for k, t in destinations.NAMED_BY_KEY.items() if k != "baby-t-park"}
        self._patch = patch.object(destinations, "NAMED_BY_KEY", rest)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def source(self, **extra):
        mw = setup_multiworld(ctrAPWorld, STEPS, seed=self.seed, options=legacy_options(**extra))
        return mw, mw.worlds[1].fill_slot_data()

    def test_title_block_on_the_schema_18_wire(self):
        _mw, wire = self.source()
        self.assertEqual(wire["schema_version"], 18)
        self.assertEqual(wire["custom_track_titles"],
                         {"version": 1, "tracks": [{"slot": 1, "title": LEGACY_TITLE}]})
        _mw, wire = self.source(title="Crash  Cove", author="Ana")
        self.assertEqual(wire["custom_track_titles"]["tracks"][0]["title"], "Crash Cove (Custom)")
        self.assertNotIn("title", wire["custom_tracks"]["tracks"][0])

    def test_no_custom_track_means_no_block(self):
        mw = setup_multiworld(ctrAPWorld, STEPS, seed=self.seed, options={})
        self.assertNotIn("custom_track_titles", mw.worlds[1].fill_slot_data())

    def test_tracker_renames_and_logic_is_unchanged(self):
        source, wire = self.source()
        tracker = tracker_for(wire, self.seed)
        world = tracker.worlds[1]
        by_address = {loc.address: loc.name for loc in tracker.get_locations(1)}
        self.assertEqual(by_address[35016300], f"{LEGACY_TITLE}: Trophy Race")
        self.assertEqual(by_address[35016400], f"{LEGACY_TITLE}: Held 1st")
        self.assertEqual(by_address[custom_check_code("ctr_location", 1)],
                         f"{LEGACY_TITLE}: CTR Token Challenge")
        self.assertEqual(world.location_id_to_alias, {})
        self.assertNotIn("Custom Track 1: Trophy Race", tracker.regions.location_cache[1])
        self.assertEqual(set(by_address), {loc.address for loc in source.get_locations(1)})
        # Every rule evaluates by object after the rename, with the same answer
        # the server's world gives for the same items.
        pool = sorted(item.name for item in source.itempool if item.player == 1)
        for cut in (0, len(pool) // 3, 2 * len(pool) // 3, len(pool)):
            with self.subTest(items=cut):
                self.assertEqual(reachable(tracker, pool[:cut]), reachable(source, pool[:cut]))

    def test_tracker_without_title_block_uses_compiled_titles(self):
        _source, wire = self.source(title="Neon Rush")
        old = {k: v for k, v in wire.items() if k != "custom_track_titles"}
        names = {loc.address: loc.name for loc in tracker_for(old, self.seed).get_locations(1)}
        self.assertEqual(names[35016300], f"{LEGACY_TITLE}: Trophy Race")
        names = {loc.address: loc.name for loc in tracker_for(wire, self.seed).get_locations(1)}
        self.assertEqual(names[35016300], "Neon Rush: Trophy Race")

    def test_real_generation_never_renames(self):
        mw = setup_multiworld(ctrAPWorld, gen_steps, seed=self.seed, options=legacy_options())
        self.assertIn("Custom Track 1: Trophy Race", mw.regions.location_cache[1])
        self.assertIn(35016300, mw.worlds[1].location_id_to_alias)

    def test_room_datapackage_renames_letter_items(self):
        mw = setup_multiworld(ctrAPWorld, gen_steps, seed=self.seed, options=legacy_options())
        distribute_items_restrictive(mw)
        package = ctrAPWorld.get_data_package_data()
        multidata = {"datapackage": {GAME: copy.deepcopy(package)}}
        embed_track_names(mw, multidata, GAME)
        room = multidata["datapackage"][GAME]
        letters = [custom_check_code("letter_item", 1, i) for i in range(3)]
        placed = {loc.item.code for loc in mw.get_locations() if loc.item}
        self.assertTrue(placed & set(letters), "the seed pools a custom letter item")
        for code, letter in zip(letters, "CTR"):
            if code in placed:
                self.assertEqual(room["item_name_to_id"][f"Letter {letter} ({LEGACY_TITLE})"], code)
                self.assertNotIn(f"Letter {letter} (Custom Track 1)", room["item_name_to_id"])
        self.assertEqual(room["location_name_to_id"][f"{LEGACY_TITLE}: Trophy Race"], 35016300)
        self.assertEqual(set(room["item_name_to_id"].values()), set(package["item_name_to_id"].values()))
        self.assertNotEqual(room["checksum"], package["checksum"])
        self.assertEqual(package, ctrAPWorld.get_data_package_data(), "registered package mutated")


class TestLegacyPathNamedBlock(unittest.TestCase):
    """#133: a legacy entry whose track has a named block uses the block for
    every check and item, so the room and Universal Tracker show the real name
    with no alias, no rename and no checksum change."""
    seed = 20261013
    base = 35200000 + 200 * BABY_T_PARK_BLOCK

    def source(self, steps=STEPS, **extra):
        mw = setup_multiworld(ctrAPWorld, steps, seed=self.seed, options=legacy_options(**extra))
        return mw, mw.worlds[1].fill_slot_data()

    def test_wire_names_the_block_and_carries_its_codes(self):
        _mw, wire = self.source()
        entry = wire["custom_tracks"]["tracks"][0]
        self.assertEqual(entry["named_block"], BABY_T_PARK_BLOCK)
        self.assertEqual(entry["locations"]["trophy"], self.base)
        self.assertEqual(entry["locations"]["ctr"], self.base + 9)
        self.assertTrue(all(c == -1 or self.base + 1 <= c <= self.base + 5
                            for c in entry["locations"]["podium"]))
        letters = wire["custom_lettersanity_checks"]["tracks"][0]
        self.assertTrue(all(c == -1 or self.base + 11 <= c <= self.base + 13 for c in letters["locations"]))
        item_base = 35100000 + 5 * BABY_T_PARK_BLOCK
        self.assertTrue(all(c == -1 or item_base <= c <= item_base + 2 for c in letters["items"]))
        # The title block names the slot by the block's frozen stem; a YAML
        # title cannot rename a named track.
        self.assertEqual(wire["custom_track_titles"],
                         {"version": 1, "tracks": [{"slot": 1, "title": "Baby T Park"}]})
        _mw, wire = self.source(title="Neon Rush")
        self.assertEqual(wire["custom_track_titles"]["tracks"][0]["title"], "Baby T Park")

    def test_names_are_real_and_no_generic_check_is_created(self):
        mw, _wire = self.source()
        names = {loc.address: loc.name for loc in mw.get_locations(1) if loc.address is not None}
        self.assertEqual(names[self.base], "Baby T Park: Trophy Race")
        self.assertEqual(names[self.base + 9], "Baby T Park: CTR Token Challenge")
        self.assertFalse([n for n in names.values() if n.startswith("Custom Track ")])
        self.assertFalse([a for a in names if 35016300 <= a <= 35016559 or 35020000 <= a <= 35023131])
        self.assertEqual(mw.worlds[1].location_id_to_alias, {})
        pooled = {item.name for item in mw.itempool if item.player == 1}
        self.assertFalse({n for n in pooled if n.endswith("(Custom Track 1)")})
        self.assertTrue({n for n in pooled if n.endswith("(Baby T Park)")})

    def test_tracker_restores_the_same_names_and_logic(self):
        source, wire = self.source()
        tracker = tracker_for(wire, self.seed)
        self.assertEqual({loc.address: loc.name for loc in tracker.get_locations(1)},
                         {loc.address: loc.name for loc in source.get_locations(1)})
        pool = sorted(item.name for item in source.itempool if item.player == 1)
        for cut in (0, len(pool) // 3, 2 * len(pool) // 3, len(pool)):
            with self.subTest(items=cut):
                self.assertEqual(reachable(tracker, pool[:cut]), reachable(source, pool[:cut]))

    def test_tracker_refuses_a_forged_block(self):
        from ..custom_tracks import reconstruct_custom_tracks_from_wire
        _source, wire = self.source()
        self.assertTrue(reconstruct_custom_tracks_from_wire(wire))
        for forged in (0, None, True, 8.0):
            bad = copy.deepcopy(wire)
            if forged is None:
                del bad["custom_tracks"]["tracks"][0]["named_block"]
            else:
                bad["custom_tracks"]["tracks"][0]["named_block"] = forged
            with self.subTest(block=forged):
                self.assertEqual(reconstruct_custom_tracks_from_wire(bad), {})

    def test_room_datapackage_is_untouched(self):
        mw, _wire = self.source(steps=gen_steps)
        distribute_items_restrictive(mw)
        package = ctrAPWorld.get_data_package_data()
        multidata = {"datapackage": {GAME: copy.deepcopy(package)}}
        embed_track_names(mw, multidata, GAME)
        self.assertEqual(multidata["datapackage"][GAME], package)


class TestSharedItemOwners(unittest.TestCase):
    """Two CTR players share one generic letter item code (#306 review)."""

    CODE = custom_check_code("letter_item", 1, 0)

    def room(self, titles_p2):
        from types import SimpleNamespace as NS
        canonical_name = "Letter C (Custom Track 1)"
        package = {"location_name_to_id": {}, "location_name_groups": {},
                   "item_name_to_id": {canonical_name: self.CODE}, "item_name_groups": {}}
        item = lambda player: NS(player=player, code=self.CODE)
        locations = [NS(address=None, item=item(1), player=1), NS(address=None, item=item(2), player=2)]
        worlds = {1: NS(game=GAME, custom_track_titles={1: "Baby T Park"}),
                  2: NS(game=GAME, custom_track_titles=titles_p2)}
        mw = NS(player_ids=[1, 2], worlds=worlds, player_name={1: "Ana", 2: "Bo"},
                precollected_items={}, get_locations=lambda player=None: [
                    l for l in locations if player is None or l.player == player])
        multidata = {"datapackage": {GAME: package}}
        with patch("worlds.ctr.custom_track_datapackage.location_aliases", return_value={}), \
                patch("worlds.ctr.custom_track_datapackage.data_package_checksum", return_value="x"):
            embed_track_names(mw, multidata, GAME)
        return multidata["datapackage"][GAME]["item_name_to_id"]

    def test_player_without_title_keeps_canonical_name_visible(self):
        names = self.room({})
        self.assertEqual(sorted(names.values()), [self.CODE])
        (label,) = names
        self.assertIn("Letter C (Baby T Park) (Ana, P1)", label)
        self.assertIn("Letter C (Custom Track 1) (Bo, P2)", label)

    def test_both_titled_players_are_named(self):
        (label,) = self.room({1: "Neon Rush"})
        self.assertIn("Baby T Park", label)
        self.assertIn("Neon Rush", label)


class FixtureRegistry:
    """Load the fixture rows as if a build had minted them (test data only)."""

    def __enter__(self):
        tracks = fixture_tracks()
        from ..named_tracks import track_locations
        codes = {code: name for t in tracks for name, code in track_locations(t)}
        self.patches = [
            patch.object(destinations, "NAMED_TRACKS", tracks),
            patch.dict(destinations.NAMED_BY_KEY, {t.track_key: t for t in tracks}),
            patch.dict(content_plan.LOCATION_BY_CODE, codes),
        ]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


class WithoutNamedBlock:
    """A build without baby-t-park's block, to exercise the generic content-plan
    addressing (B+) with the only package the content plan admits. Test only."""

    def __enter__(self):
        rest = tuple(t for t in destinations.NAMED_TRACKS if t.track_key != "baby-t-park")
        self.patches = [patch.object(destinations, "NAMED_TRACKS", rest),
                        patch.object(destinations, "NAMED_BY_KEY", {t.track_key: t for t in rest})]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


class TestContentPlanAddressing(unittest.TestCase):
    def test_shipped_package_uses_its_named_block(self):
        world = make_world(profile_options())
        track = next(t for t in world.ctr_content_plan["tracks"] if t["origin"] == "custom")
        self.assertEqual((track["named_block"], track["room_title"]), (BABY_T_PARK_BLOCK, "Baby T Park"))
        code = location_code(BABY_T_PARK_BLOCK, "trophy")
        check = next(c for c in world.ctr_content_plan["checks"] if c["owner"] == track["id"])
        self.assertEqual((check["location"], check["display_name"]), (code, "Baby T Park: Trophy Race"))
        self.assertNotIn(code, world.location_id_to_alias)
        tracker = make_world(profile_options(), passthrough=world.fill_slot_data())
        tracker.generate_basic()
        names = {loc.address: loc.name for loc in tracker.multiworld.get_locations(1)}
        self.assertEqual(names[code], "Baby T Park: Trophy Race")

    def test_generic_package_carries_its_room_title(self):
        with WithoutNamedBlock():
            world = make_world(profile_options())
            track = next(t for t in world.ctr_content_plan["tracks"] if t["origin"] == "custom")
            self.assertEqual(track["room_title"], "Baby T Park")
            self.assertNotIn("named_block", track)
            check = next(c for c in world.ctr_content_plan["checks"] if c["owner"] == track["id"])
            self.assertEqual((check["location"], check["display_name"]), (35016300, "Baby T Park: Trophy Race"))
            tracker = make_world(profile_options(), passthrough=world.fill_slot_data())
            tracker.generate_basic()
            names = {loc.address: loc.name for loc in tracker.multiworld.get_locations(1)}
            self.assertEqual(names[35016300], "Baby T Park: Trophy Race")

    def test_fixture_named_block_is_used_and_needs_no_alias(self):
        with FixtureRegistry():
            world = make_world(profile_options())
            plan = world.ctr_content_plan
            track = next(t for t in plan["tracks"] if t["origin"] == "custom")
            self.assertEqual((track["named_block"], track["room_title"]), (0, "Fixture Speedway"))
            check = next(c for c in plan["checks"] if c["owner"] == track["id"])
            self.assertEqual(check["location"], location_code(0, "trophy"))
            self.assertEqual(check["display_name"], "Fixture Speedway: Trophy Race")
            names = {loc.address: loc.name for loc in world.multiworld.get_locations(1)}
            self.assertEqual(names[35200000], "Fixture Speedway: Trophy Race")
            self.assertNotIn(35200000, world.location_id_to_alias)
            self.assertTrue(content_plan.validate(plan))
            tracker = make_world(profile_options(), passthrough=world.fill_slot_data())
            tracker.generate_basic()
            names = {loc.address: loc.name for loc in tracker.multiworld.get_locations(1)}
            self.assertEqual(names[35200000], "Fixture Speedway: Trophy Race")
            wire = world.fill_slot_data()
        # Without the block in this build, the same plan is refused.
        with self.assertRaises(Exception):
            content_plan.validate(wire["content_plan"])

    def test_plan_validation_refuses_forged_addressing(self):
        world = make_world(profile_options())
        plan = world.ctr_content_plan
        index = next(i for i, t in enumerate(plan["tracks"]) if t["origin"] == "custom")
        for change in (lambda t: t.update(named_block=0), lambda t: t.update(room_title="[x]")):
            forged = copy.deepcopy(plan)
            change(forged["tracks"][index])
            with self.subTest(change=change), self.assertRaises(Exception):
                content_plan.validate(forged)
