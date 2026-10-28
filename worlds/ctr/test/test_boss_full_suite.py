"""Boss encounters, full suite (2026-10-28 decisions 5 to 9).

N. Oxide in the opponent pool with a drawn racer in his own garage
(decision 7), the advanced weapon families (decisions 5 and 6), N. Oxide's
all_compatible profile, the Purple Gem Cup gauntlet, and the Hit Character
checks following the drawn racers (decision 9).
"""
import json
import unittest

from BaseClasses import CollectionState
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from .. import boss_encounters as be
from .. import boss_track_shuffle as bts
from .. import hit_character as hc

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1


def _build(seed=1, steps=STEPS, **options):
    options.setdefault("wumpa_check", "per_track")
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    for step in steps:
        call_all(mw, step)
    return mw


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _keys():
    return [k for k, _r, _c, _h in bts.GARAGES]


class TestOxideInPool(unittest.TestCase):

    def test_five_distinct_bosses_and_a_final_racer(self):
        seen_oxide_in_garage = False
        for seed in range(30):
            o = _build(seed=seed, boss_opponent_shuffle=True, boss_oxide_in_pool=True).worlds[PLAYER].options
            garages = be.opponents(o)
            final = be.final_opponent(o)
            self.assertNotEqual(final, be.OXIDE_NAME)
            self.assertEqual(len(set(garages.values()) | {final}), 5)
            seen_oxide_in_garage |= be.OXIDE_NAME in garages.values()
        self.assertTrue(seen_oxide_in_garage)

    def test_switch_off_keeps_oxide_out(self):
        for seed in range(10):
            o = _build(seed=seed, boss_opponent_shuffle=True).worlds[PLAYER].options
            self.assertNotIn(be.OXIDE_NAME, be.opponents(o).values())
            self.assertEqual(be.final_opponent(o), be.OXIDE_NAME)
        self.assertNotIn("final", _wire(_build(boss_opponent_shuffle=True))["boss_encounters"])

    def test_pool_too_small_refuses(self):
        four = ["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura"]
        _build(boss_opponent_shuffle=True, boss_character_allowlist=four)
        with self.assertRaises(OptionError):
            _build(boss_opponent_shuffle=True, boss_oxide_in_pool=True, boss_character_allowlist=four)
        with self.assertRaises(OptionError):
            # N. Oxide fills a garage, but the final race needs a fifth racer.
            _build(boss_opponent_shuffle=True, boss_oxide_in_pool=True,
                   boss_character_allowlist=four[:3] + ["Nitros Oxide"])

    def test_final_record_round_trips(self):
        mw = _build(seed=3, boss_opponent_shuffle=True, boss_oxide_in_pool=True)
        o = mw.worlds[PLAYER].options
        wire = _wire(mw)
        co = wire["ctr_options"]
        self.assertIs(co["boss_oxide_in_pool"], True)
        final = wire["boss_encounters"]["final"]
        self.assertEqual(final, {"locations": [35011104, 35011105],
                                 "opponent": be.OPPONENT_KEY[be.final_opponent(o)],
                                 "attack": "inherited", "schedule": []})
        parsed = be.parse_wire(wire["boss_encounters"], True, False, True, False, False)
        self.assertEqual(parsed[4], be.final_opponent(o))
        world = _build(steps=()).worlds[PLAYER]
        world._ut_restore_options(wire)
        self.assertEqual(be.final_opponent(world.options), be.final_opponent(o))
        self.assertEqual(be.opponents(world.options), be.opponents(o))


class TestAdvancedFamilies(unittest.TestCase):

    def test_garage_kits_use_the_full_suite_but_never_the_super_engine(self):
        seen = set()
        for seed in range(40):
            o = _build(seed=seed, boss_kit_shuffle=True).worlds[PLAYER].options
            for sched in be.kits(o).values():
                fams = {be.family_of(s[2]) for s in sched}
                self.assertNotIn("super_engine", fams)
                seen |= fams
        self.assertEqual(seen, set(be.GARAGE_FAMILIES))

    def test_every_advanced_row_is_certified(self):
        for fam in ("turbo", "shield", "mask", "clock", "warp_orb", "invisibility", "super_engine"):
            for w, t, p, _c, j in be.FAMILY_VARIANTS[fam]:
                self.assertIn((w, t, p, j), be.CERTIFIED_ROWS)

    def test_super_engine_in_a_garage_row_is_refused(self):
        block = _wire(_build(seed=4, boss_kit_shuffle=True))["boss_encounters"]
        block["garages"]["papu_papu"]["schedule"][0][2] = 0x0D
        block["garages"]["papu_papu"]["schedule"][0][1] = 3
        block["garages"]["papu_papu"]["schedule"][0][3] = 1
        block["garages"]["papu_papu"]["schedule"][0][5] = 0
        with self.assertRaises(ValueError):
            be.parse_wire(block, False, True)


class TestOxideProfile(unittest.TestCase):

    def test_all_compatible_composes_thirteen_segments(self):
        seen = set()
        for seed in range(25):
            o = _build(seed=seed, oxide_attack_profile="all_compatible").worlds[PLAYER].options
            sched = be.final_schedule(o)
            self.assertEqual(tuple(s[0] for s in sched), be.OXIDE_CHECKPOINTS)
            self.assertGreaterEqual(len({be.family_of(s[2]) for s in sched}), 2)
            seen |= {be.family_of(s[2]) for s in sched}
        self.assertIn("super_engine", seen)

    def test_profile_alone_emits_a_version_2_block(self):
        mw = _build(seed=5, oxide_attack_profile="all_compatible")
        wire = _wire(mw)
        self.assertEqual(wire["ctr_options"]["oxide_attack_profile"], "all_compatible")
        block = wire["boss_encounters"]
        self.assertEqual(block["version"], 2)
        self.assertEqual(block["final"]["opponent"], "nitros_oxide")
        self.assertEqual(block["final"]["attack"], "composed")
        for key, row in block["garages"].items():
            self.assertEqual(row["attack"], "inherited")
            self.assertEqual(row["opponent"], key)
        world = _build(steps=()).worlds[PLAYER]
        world._ut_restore_options(wire)
        self.assertEqual(be.final_schedule(world.options), be.final_schedule(mw.worlds[PLAYER].options))

    def test_oxide_blocklist_is_separate(self):
        o = _build(seed=6, oxide_attack_profile="all_compatible",
                   oxide_powerup_blocklist=["super_engine", "clock"],
                   boss_kit_shuffle=True, boss_powerup_blocklist=["bomb"]).worlds[PLAYER].options
        fams = {be.family_of(s[2]) for s in be.final_schedule(o)}
        self.assertFalse(fams & {"super_engine", "clock"})
        with self.assertRaises(OptionError):
            _build(oxide_attack_profile="all_compatible", oxide_powerup_blocklist=list(be.FAMILIES))

    def test_retail_profile_has_no_final_record(self):
        self.assertIsNone(_wire(_build()).get("boss_encounters"))
        self.assertEqual(_wire(_build())["ctr_options"]["oxide_attack_profile"], "retail")


class TestGauntlet(unittest.TestCase):

    def test_needs_the_kit_switch(self):
        with self.assertRaises(OptionError):
            _build(purple_cup_boss_gauntlet=True)

    def test_legs_carry_the_garage_kits(self):
        mw = _build(seed=7, boss_kit_shuffle=True, boss_opponent_shuffle=True, purple_cup_boss_gauntlet=True)
        o = mw.worlds[PLAYER].options
        wire = _wire(mw)
        self.assertIs(wire["ctr_options"]["purple_cup_boss_gauntlet"], True)
        legs = wire["boss_encounters"]["gauntlet"]["legs"]
        self.assertEqual(len(legs), 4)
        from ..gem_cup_legs import resolved_gem_cup_legs
        cup = resolved_gem_cup_legs(mw.worlds[PLAYER])["Purple Gem Cup"]
        for i, key in enumerate(_keys()):
            leg = legs[i]
            self.assertEqual(leg["attacker"], be.OPPONENT_KEY[be.opponents(o)[key]])
            self.assertEqual(leg["track"], bts.VENUE_LEVEL_IDS[cup[i]])
            self.assertEqual([s[0] for s in leg["schedule"]], list(bts.translated_schedule(key, cup[i])))
            self.assertEqual([s[1:] for s in leg["schedule"]], [list(s[1:]) for s in be.kits(o)[key]])
        be.parse_wire(wire["boss_encounters"], True, True, False, True, False)
        bad = json.loads(json.dumps(wire["boss_encounters"]))
        bad["gauntlet"]["legs"][0]["attacker"] = bad["gauntlet"]["legs"][1]["attacker"]
        with self.assertRaises(ValueError):
            be.parse_wire(bad, True, True, False, True, False)

    def test_a_cortex_vortex_leg_carries_no_attack(self):
        found = False
        for seed in range(40):
            mw = _build(seed=seed, boss_kit_shuffle=True, purple_cup_boss_gauntlet=True,
                        randomize_gem_cup_tracks=True, cortex_vortex_track=True)
            from ..gem_cup_legs import resolved_gem_cup_legs
            cup = resolved_gem_cup_legs(mw.worlds[PLAYER])["Purple Gem Cup"]
            legs = _wire(mw)["boss_encounters"]["gauntlet"]["legs"]
            for i, track in enumerate(cup):
                if track not in bts.VENUES:
                    found = True
                    self.assertEqual((legs[i]["track"], legs[i]["schedule"]), (-1, []))
            if found:
                break
        self.assertTrue(found)


class TestHitFollowsTheDrawnRacer(unittest.TestCase):
    """Decision 9: a Hit check's boss-race route follows the racer actually
    drawn for that garage, and beating a garage unlocks that racer as an
    opponent in other races."""

    def _mw(self, seed, **extra):
        return _build(seed=seed, hit_character=True, boss_opponent_shuffle=True, **extra)

    def test_block_names_the_drawn_racers(self):
        for seed in range(8):
            mw = self._mw(seed, boss_oxide_in_pool=bool(seed % 2))
            o = mw.worlds[PLAYER].options
            block = _wire(mw)["hit_character_encounters"]
            identity = be.boss_identity(o)
            self.assertEqual({int(c): v for c, v in block["bosses"].items()}, identity)
            triggers = hc.unlock_triggers_for(identity)
            for guest in hc.GUEST_RACER_IDS:
                self.assertEqual((tuple(block["unlock_triggers"][str(guest)]["any_of"]),
                                  block["unlock_triggers"][str(guest)]["kind"]), triggers[guest])
                if not triggers[guest][0]:
                    self.assertEqual(block["unlock_triggers"][str(guest)]["fallback_keys"],
                                     hc.CONTENT_PLAN_FALLBACK_KEYS[guest])

    def test_retail_identity_keeps_the_retail_triggers(self):
        self.assertEqual(hc.unlock_triggers_for(hc.BOSS_WIN_OPPONENTS), hc.UNLOCK_TRIGGERS)
        self.assertFalse(hc.identity_shuffled(hc.BOSS_WIN_OPPONENTS))

    def test_drawn_garage_win_unlocks_the_drawn_racer(self):
        identity = dict(hc.BOSS_WIN_OPPONENTS)
        identity[35011100] = 13       # Penta Penguin races Ripper Roo's garage
        identity[35011101] = 0        # Crash races Papu Papu's garage
        t = hc.unlock_triggers_for(identity)
        self.assertEqual(t[13], ((35011008, 35011010, 35011100), "boss"))
        self.assertEqual(t[10], ((), "boss"))    # Ripper Roo is raced nowhere
        self.assertEqual(t[9], ((), "boss"))
        self.assertEqual(t[8], ((35011103,), "boss"))
        self.assertTrue(hc.identity_shuffled(identity))

    def test_boss_route_moves_with_the_racer(self):
        for seed in range(12):
            mw = self._mw(seed)
            world = mw.worlds[PLAYER]
            o = world.options
            opp = be.opponents(o)
            raced = {be.OPPONENT_ENGINE_ID[n] for n in opp.values()}
            block = world.ctr_hit_character_encounters
            for target in range(16):
                routes = hc._build_boss_routes(world, PLAYER, target, block)
                codes = {c for c, cid in be.boss_identity(o).items() if cid == target}
                created = {c for c in codes if mw.regions.location_cache[PLAYER].get(
                    hc._location_name_by_code(world)[c]) is not None}
                self.assertEqual(len(routes), len(created), (seed, target))
                if target in (8, 9, 10, 11) and target not in raced:
                    self.assertEqual(routes, [])

    def test_ut_restores_the_shuffled_block(self):
        mw = self._mw(4, boss_oxide_in_pool=True)
        wire = _wire(mw)
        world = _build(steps=()).worlds[PLAYER]
        world._ut_restore_options(wire)
        self.assertEqual(world.ctr_hit_character_encounters["bosses"],
                         wire["hit_character_encounters"]["bosses"])

    def test_full_accessibility_generates(self):
        from worlds.AutoWorld import call_all as _call_all
        from Fill import distribute_items_restrictive
        for seed in (11, 12, 13):
            mw = _build(seed=seed, hit_character=True, boss_opponent_shuffle=True, boss_oxide_in_pool=True,
                        boss_track_shuffle=True, boss_kit_shuffle=True, accessibility="full")
            _call_all(mw, "generate_basic")
            distribute_items_restrictive(mw)
            _call_all(mw, "post_fill")
            self.assertTrue(mw.can_beat_game(CollectionState(mw)))
            state = mw.get_all_state(False)
            for cid in range(16):
                loc = mw.get_location(hc.HIT_CHARACTER_CLASS.location_name(cid), PLAYER)
                self.assertTrue(loc.can_reach(state), (seed, cid))


if __name__ == "__main__":
    unittest.main()
