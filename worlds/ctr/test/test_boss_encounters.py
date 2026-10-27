"""Boss opponent and kit shuffle (#169 tiers 2 and 3, schema 18).

Design: the 0.3.0 #169 design with independent switches (the rulings of
2026-10-13) and the random character boss battles Wayfinder rulings. Each of
the four ordinary garages keeps its physical check, Key, door and
personal-win event; the opponent and the attack kit are drawn once at
generation and frozen on the wire.
"""
import itertools
import json
import os
import unittest

from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from .. import boss_encounters as be
from .. import boss_track_shuffle as bts

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "boss_encounters.json")
SWITCHES = ("boss_track_shuffle", "boss_opponent_shuffle", "boss_kit_shuffle")


def _build(seed=1, **options):
    options.setdefault("wumpa_check", "per_track")
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    for step in STEPS:
        call_all(mw, step)
    return mw


def _wire(mw):
    return json.loads(json.dumps(mw.worlds[PLAYER].fill_slot_data()))


def _mask(mask):
    return {name: bool(mask & (4 >> i)) for i, name in enumerate(SWITCHES)}


def _keys():
    return [k for k, _r, _c, _h in bts.GARAGES]


class TestTables(unittest.TestCase):

    def test_home_tracks_are_the_wayfinder_table(self):
        self.assertEqual(be.HOME_TRACK["Coco Bandicoot"], "Coco Park")
        self.assertEqual(be.HOME_TRACK["N. Tropy"], "Turbo Track")
        self.assertEqual(len(set(be.HOME_TRACK.values())), 16)
        for key, _r, _c, home in bts.GARAGES:
            self.assertEqual(be.HOME_TRACK[be.GARAGE_BOSS[key]], home)

    def test_oxide_is_never_an_ordinary_garage_opponent(self):
        self.assertNotIn("Nitros Oxide", be.OPPONENT_NAMES)
        self.assertEqual(len(be.OPPONENT_NAMES), 15)

    def test_signatures_are_the_retail_rows(self):
        # Rows copied from data.BossWeapon*; the shared fixture pins them for
        # native too.
        with open(FIXTURE, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual({k: [list(r) for r in rows] for k, rows in be.SIGNATURES.items()},
                         doc["signatures"])
        self.assertEqual({k: [list(r) for r in rows] for k, rows in be.FAMILY_VARIANTS.items()},
                         doc["families"])
        from ..characters import ROSTER_CHARACTER_ID
        self.assertEqual({n: [k, ROSTER_CHARACTER_ID[n]] for n, k in be.OPPONENT_KEY.items()},
                         doc["opponents"])
        self.assertEqual([list(x) for x in be.INTENSITY], doc["intensity"])

    def test_every_composed_kit_fits_every_venue(self):
        for key in _keys():
            for track in bts.VENUES:
                cps = bts.translated_schedule(key, track)
                self.assertEqual(len(cps), be.SEGMENTS)
                self.assertTrue(all(a < b for a, b in zip(cps, cps[1:])))

    def test_intensity_scales_cooldowns_only(self):
        self.assertEqual([be.scale_cooldown(0x0C, i) for i in range(4)], [18, 12, 9, 6])
        self.assertEqual(be.scale_cooldown(2, 3), be.COOLDOWN_MIN)


class TestAllEightCombinations(unittest.TestCase):

    def test_every_switch_mask_generates_and_round_trips(self):
        for mask in range(8):
            with self.subTest(mask=f"{mask:03b}"):
                mw = _build(seed=10 + mask, **_mask(mask))
                o = mw.worlds[PLAYER].options
                wire = _wire(mw)
                co = wire["ctr_options"]
                for name, on in _mask(mask).items():
                    self.assertIs(co[name], on)
                block = wire.get("boss_encounters")
                if mask == 0:
                    self.assertIsNone(block)
                    continue
                self.assertEqual(block["version"], 1 if mask == 4 else 2)
                if mask == 4:
                    continue
                tracks, opps, scheds, kit = be.parse_wire(
                    block, co["boss_opponent_shuffle"], co["boss_kit_shuffle"])
                self.assertEqual(tracks, bts.venues(o))
                self.assertEqual(opps, be.opponents(o))
                self.assertEqual(scheds, be.kits(o))
                self.assertEqual(kit is not None, co["boss_kit_shuffle"])
                for key, _r, code, _h in bts.GARAGES:
                    self.assertEqual(block["garages"][key]["location"], code)
                if not co["boss_track_shuffle"]:
                    self.assertEqual(tracks, bts.retail_venues())
                if not co["boss_opponent_shuffle"]:
                    self.assertEqual(opps, be.GARAGE_BOSS)

    def test_option_off_seed_draws_nothing_new(self):
        # Same seed, same output whether the new options are absent or set
        # to their defaults with subordinate lists filled (ignored).
        base = _wire(_build(seed=77))
        other = _wire(_build(seed=77, boss_character_blocklist=["Crash Bandicoot"],
                             boss_powerup_blocklist=["tnt"]))
        self.assertEqual(base, other)
        self.assertNotIn("boss_encounters", base)

    def test_track_only_seed_keeps_the_tier_1_block(self):
        mw = _build(seed=5, boss_track_shuffle=True)
        self.assertEqual(_wire(mw)["boss_encounters"], bts.wire_block(mw.worlds[PLAYER].options))


class TestOpponentDraw(unittest.TestCase):

    def test_opponent_only_keeps_the_garage_track(self):
        for seed in range(6):
            o = _build(seed=seed, boss_opponent_shuffle=True).worlds[PLAYER].options
            self.assertEqual(bts.venues(o), bts.retail_venues())
            self.assertEqual(len(set(be.opponents(o).values())), 4)

    def test_home_pairing_races_on_the_opponent_home_track(self):
        for seed in range(6):
            o = _build(seed=seed, boss_opponent_shuffle=True,
                       boss_track_shuffle=True).worlds[PLAYER].options
            opp = be.opponents(o)
            self.assertEqual(bts.venues(o), {k: be.HOME_TRACK[opp[k]] for k in opp})
            self.assertEqual(len(set(bts.venues(o).values())), 4)

    def test_independent_track_draws_separately(self):
        seen_unpaired = False
        for seed in range(12):
            o = _build(seed=seed, boss_opponent_shuffle=True, boss_track_shuffle=True,
                       boss_track_assignment="independent_track").worlds[PLAYER].options
            opp, v = be.opponents(o), bts.venues(o)
            seen_unpaired |= any(be.HOME_TRACK[opp[k]] != v[k] for k in v)
        self.assertTrue(seen_unpaired)

    def test_allowlist_of_exactly_four_uses_all_four(self):
        four = ["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura"]
        o = _build(seed=3, boss_opponent_shuffle=True,
                   boss_character_allowlist=four).worlds[PLAYER].options
        self.assertEqual(sorted(be.opponents(o).values()), sorted(four))

    def test_blocklist_applies_after_allowlist(self):
        with self.assertRaises(OptionError):
            _build(boss_opponent_shuffle=True,
                   boss_character_allowlist=["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura"],
                   boss_character_blocklist=["Pura"])

    def test_repeats_allowed_may_repeat(self):
        o = _build(boss_opponent_shuffle=True, boss_encounter_repeats="allow",
                   boss_character_allowlist=["Crash Bandicoot"]).worlds[PLAYER].options
        self.assertEqual(set(be.opponents(o).values()), {"Crash Bandicoot"})

    def test_home_pairing_respects_the_track_filters(self):
        # Four racers allowed, but one's home track is blocked: no matching.
        with self.assertRaises(OptionError):
            _build(boss_opponent_shuffle=True, boss_track_shuffle=True,
                   boss_character_allowlist=["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura"],
                   boss_track_blocklist=["Coco Park"])
        o = _build(boss_opponent_shuffle=True, boss_track_shuffle=True,
                   boss_character_allowlist=["Crash Bandicoot", "Coco Bandicoot", "Polar", "Pura", "N. Gin"],
                   boss_track_blocklist=["Coco Park"]).worlds[PLAYER].options
        self.assertNotIn("Coco Bandicoot", be.opponents(o).values())

    def test_deterministic_per_seed(self):
        a = be.opponents(_build(seed=9, boss_opponent_shuffle=True).worlds[PLAYER].options)
        b = be.opponents(_build(seed=9, boss_opponent_shuffle=True).worlds[PLAYER].options)
        self.assertEqual(a, b)

    def test_distinct_draw_is_uniform_and_complete(self):
        import random
        pools = [["a", "b"], ["a", "b"], ["a", "b", "c"], ["c", "d"]]
        valid = {c for c in itertools.product(*pools) if len(set(c)) == 4}
        rng = random.Random(1)
        counts = {}
        for _ in range(4000):
            pick = tuple(be._distinct_draw(rng, pools))
            counts[pick] = counts.get(pick, 0) + 1
        self.assertEqual(set(counts), valid)
        self.assertLess(max(counts.values()) / min(counts.values()), 1.3)
        self.assertIsNone(be._distinct_draw(rng, [["a"], ["a"], ["b"], ["c"]]))


class TestKitDraw(unittest.TestCase):

    def test_mixed_loadouts_use_two_to_four_families(self):
        for seed in range(8):
            o = _build(seed=seed, boss_kit_shuffle=True).worlds[PLAYER].options
            ks = be.kits(o)
            self.assertEqual(sorted(ks), sorted(_keys()))
            weapons = set()
            for key, sched in ks.items():
                fams = {be.family_of(s[2]) for s in sched}
                self.assertTrue(2 <= len(fams) <= 4, (key, sched))
                self.assertEqual(tuple(s[0] for s in sched),
                                 bts.translated_schedule(key, bts.venues(o)[key]))
                weapons.add(tuple(s[2] for s in sched))
            self.assertEqual(len(weapons), 4)

    def test_signature_profiles_are_a_permutation_of_retail(self):
        o = _build(seed=4, boss_kit_shuffle=True,
                   boss_attack_assignment="signature_profiles").worlds[PLAYER].options
        used = []
        for key, sched in be.kits(o).items():
            rows = tuple((w, t, p, c, j) for _cp, t, w, p, c, j in sched)
            match = [k for k, r in be.SIGNATURES.items() if r == rows]
            self.assertEqual(len(match), 1)
            used.append(match[0])
        self.assertEqual(sorted(used), sorted(_keys()))

    def test_powerup_blocklist(self):
        o = _build(seed=2, boss_kit_shuffle=True,
                   boss_powerup_blocklist=["tnt", "missile"]).worlds[PLAYER].options
        for sched in be.kits(o).values():
            self.assertEqual({be.family_of(s[2]) for s in sched}, {"bomb", "potion"})
        with self.assertRaises(OptionError):
            _build(boss_kit_shuffle=True, boss_powerup_blocklist=["tnt", "missile", "bomb"])
        with self.assertRaises(OptionError):
            _build(boss_kit_shuffle=True, boss_attack_assignment="signature_profiles",
                   boss_powerup_blocklist=["tnt"])
        o = _build(boss_kit_shuffle=True, boss_attack_assignment="signature_profiles",
                   boss_powerup_blocklist=["tnt"], boss_encounter_repeats="allow").worlds[PLAYER].options
        self.assertTrue(all(be.family_of(s[2]) != "tnt" for k in be.kits(o).values() for s in k))

    def test_intensity_changes_cooldowns_not_families(self):
        a = be.kits(_build(seed=6, boss_kit_shuffle=True).worlds[PLAYER].options)
        b = be.kits(_build(seed=6, boss_kit_shuffle=True,
                           boss_attack_intensity="mayhem").worlds[PLAYER].options)
        for key in a:
            self.assertEqual([s[:4] + s[5:] for s in a[key]], [s[:4] + s[5:] for s in b[key]])
            self.assertTrue(all(y[4] <= x[4] for x, y in zip(a[key], b[key])))

    def test_kit_record_on_the_wire(self):
        wire = _wire(_build(boss_kit_shuffle=True, boss_loss_easing=False,
                            boss_attack_intensity="relaxed"))
        self.assertEqual(wire["boss_encounters"]["kit"],
                         {"assignment": "mixed_loadouts", "intensity": "relaxed", "loss_easing": False})


class TestSubordinateOptions(unittest.TestCase):

    def test_ignored_without_their_switch(self):
        from .. import notices
        mw = _build(boss_character_allowlist=["Polar"], boss_track_assignment="independent_track",
                    boss_attack_intensity="mayhem", boss_loss_easing=False)
        ignored = notices._state(mw.worlds[PLAYER]).get("ignored", [])
        for label in ("Boss Character Allowlist", "Boss Track Assignment",
                      "Boss Attack Intensity", "Boss Loss Easing"):
            self.assertTrue(any(i.startswith(label) for i in ignored), label)

    def test_content_plans_refuse_the_new_switches(self):
        from .. import content_bosses
        world = type("W", (), {})()
        world.options = _build().worlds[PLAYER].options
        world.options.boss_kit_shuffle.value = 1
        with self.assertRaises(OptionError):
            content_bosses.settings(world, {"enabled": True})


class TestLogic(unittest.TestCase):

    def test_home_paired_venue_moves_the_wumpa_route_and_finish_term(self):
        mw = _build(seed=1, boss_opponent_shuffle=True, boss_track_shuffle=True)
        o = mw.worlds[PLAYER].options
        tracks = bts.garage_tracks(o)
        for _k, region, _c, _h in bts.GARAGES:
            self.assertEqual(tracks[region], be.HOME_TRACK[be.opponents(o)[_k]])

    def test_boss_checks_keep_their_codes(self):
        mw = _build(boss_opponent_shuffle=True, boss_kit_shuffle=True)
        for _k, region, code, _h in bts.GARAGES:
            loc = mw.get_location(f"{region}: Boss Race", PLAYER)
            self.assertEqual(loc.address, code)

    def test_full_accessibility_generates_with_every_switch(self):
        from Fill import distribute_items_restrictive
        from worlds.AutoWorld import call_all as _call
        mw = _build(seed=3, accessibility="full", boss_track_shuffle=True,
                    boss_opponent_shuffle=True, boss_kit_shuffle=True)
        _call(mw, "generate_basic")
        distribute_items_restrictive(mw)
        _call(mw, "post_fill")
        self.assertTrue(mw.can_beat_game(mw.state))


class TestUniversalTracker(unittest.TestCase):

    def _restore(self, wire, **yaml):
        mw = setup_multiworld(ctrAPWorld, (), seed=999, options=dict(wumpa_check="per_track", **yaml))
        world = mw.worlds[PLAYER]
        be.restore_from_wire(world, wire)
        return world.options

    def test_restores_without_redrawing(self):
        mw = _build(seed=8, boss_track_shuffle=True, boss_opponent_shuffle=True,
                    boss_kit_shuffle=True, boss_attack_intensity="intense")
        src = mw.worlds[PLAYER].options
        o = self._restore(_wire(mw), boss_character_allowlist=["Polar"])
        self.assertEqual(bts.venues(o), bts.venues(src))
        self.assertEqual(be.opponents(o), be.opponents(src))
        self.assertEqual(be.kits(o), be.kits(src))
        self.assertEqual(int(o.boss_attack_intensity.value), 2)
        self.assertEqual(o.boss_character_allowlist.value, set())

    def test_tier_1_seed_restores_with_both_new_switches_off(self):
        wire = _wire(_build(seed=8, boss_track_shuffle=True))
        del wire["ctr_options"]["boss_opponent_shuffle"]
        del wire["ctr_options"]["boss_kit_shuffle"]
        o = self._restore(wire, boss_opponent_shuffle=True, boss_kit_shuffle=True)
        self.assertFalse(o.boss_opponent_shuffle.value)
        self.assertFalse(o.boss_kit_shuffle.value)
        self.assertEqual(be.opponents(o), be.GARAGE_BOSS)

    def test_multidata_tuples_parse(self):
        wire = _wire(_build(seed=8, boss_kit_shuffle=True))
        block = wire["boss_encounters"]
        for row in block["garages"].values():
            row["packages"] = tuple(row["packages"])
            row["schedule"] = tuple(tuple(s) for s in row["schedule"])
        be.parse_wire(block, False, True)


class TestParseWire(unittest.TestCase):

    def setUp(self):
        self.wire = _wire(_build(seed=11, boss_opponent_shuffle=True, boss_kit_shuffle=True))
        self.block = self.wire["boss_encounters"]

    def _bad(self, mutate, opp=True, kit=True):
        block = json.loads(json.dumps(self.block))
        mutate(block)
        with self.assertRaises(ValueError):
            be.parse_wire(block, opp, kit)

    def test_round_trip(self):
        be.parse_wire(self.block, True, True)

    def test_refusals(self):
        g = "papu_papu"
        self._bad(lambda b: b.update(version=1))
        self._bad(lambda b: b.pop("kit"))
        self._bad(lambda b: b["garages"].pop(g))
        self._bad(lambda b: b["garages"][g].update(location=35011100))
        self._bad(lambda b: b["garages"][g].update(opponent="nitros_oxide"))
        self._bad(lambda b: b["garages"][g].update(ai_profile="mayhem"))
        self._bad(lambda b: b["garages"][g].update(attack="inherited"))
        self._bad(lambda b: b["garages"][g].update(packages=["x"]))
        self._bad(lambda b: b["garages"][g]["schedule"].pop())
        self._bad(lambda b: b["garages"][g]["schedule"][0].__setitem__(0, 1))
        self._bad(lambda b: b["garages"][g]["schedule"][1].__setitem__(2, 0x09))
        self._bad(lambda b: b["garages"][g]["schedule"][1].__setitem__(4, 0))
        self._bad(lambda b: b["kit"].update(intensity="extreme"))
        # Opponent switch off but a swapped racer on the wire.
        self._bad(lambda b: None, opp=False)
        self._bad(lambda b: None, kit=False)


if __name__ == "__main__":
    unittest.main()
