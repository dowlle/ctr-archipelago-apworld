"""Regression guard for the multiworld-aware two-stage fill probe (issue #75).

`pre_fill` keeps CTR's genuine two-stage warp-pad gating unless THIS seed would
make AP's `fill_restrictive` dead-end, in which case it collapses every stage-2
gate for the seed. The predictor for "would this seed dead-end" is
`_probe_two_stage_fillable`, a dry run of the fill on a parallel multiworld.

Until 0.2.0 that dry run was `_MW(1)` unconditionally, so in a real multiworld it
answered a question about a room that does not exist. CTR's FillError tail is a
property of the ROOM (a ~97% progression pool has nothing to route around a gated
region with, and a partner world's locations are what supply the relief), so the
solo-shaped predictor was wrong in both directions: it missed seeds that really do
fail, and it collapsed stage 2 on seeds that fill fine with other players present.

Measured on the 0.1.5 apworld, 2-player against a 0-location companion, 10,000
seeds per arm: `podium_placement_checks: false` went 90 FillErrors -> 0, and the
tightest measured content config went 241 -> 0. Those are measurements, not
guarantees; these tests lock in the MECHANISM, not a zero-failure claim.

Guarded here:
- the probe mirrors the real room's player count, games, names and seed;
- each mirrored slot carries the real slot's own option object;
- solo is unchanged: one player still means a one-player dry run;
- a predicted FillError returns False (collapse), any other error returns None
  (fail open, keep two-stage) -- the probe must never make a fillable seed worse;
- a room whose slot ids are not 1..N fails open rather than predicting for the
  wrong numbering.
"""

import types
import unittest
from unittest import mock

import BaseClasses
import Fill
from worlds import AutoWorld

from .. import ctrAPWorld


class _FakeOptions:
    """Stands in for a slot's options dataclass. Identity is what the tests check,
    so it deliberately carries no behaviour."""

    def __init__(self, tag):
        self.tag = tag


class _FakeWorld:
    """A non-CTR companion world type, cheap to construct."""

    game = "FakeCompanion"

    def __init__(self, multiworld, player):
        self.multiworld = multiworld
        self.player = player
        self.options = None


def _fake_real_multiworld(games):
    """A stand-in for the REAL multiworld the probe is asked to mirror.

    games: {player: game_name}. Each player gets its own tagged options object so
    the test can prove the probe carried the right one to the right slot.
    """
    mw = types.SimpleNamespace()
    mw.player_ids = tuple(sorted(games))
    mw.game = dict(games)
    mw.player_name = {p: f"Player{p}" for p in games}
    mw.seed = 123456789
    mw.worlds = {}
    for p in games:
        w = types.SimpleNamespace()
        w.options = _FakeOptions(f"opts-for-{p}")
        mw.worlds[p] = w
    return mw


class ProbeMirrorsTheRoom(unittest.TestCase):
    """What the probe BUILDS. The dry run itself is stubbed out; these tests are
    about the shape of the room it constructs, which is the whole fix."""

    def _probe(self, games, dist=None):
        """Run _probe_two_stage_fillable against a fake real room, with call_all
        and the fill stubbed. Returns (verdict, captured_probe_multiworld)."""
        real = _fake_real_multiworld(games)
        world = ctrAPWorld.__new__(ctrAPWorld)
        world.multiworld = real
        world.player = 1
        world.options = real.worlds[1].options

        captured = {}

        def fake_dist(pmw, *a, **kw):
            captured["pmw"] = pmw
            if dist is not None:
                dist(pmw)

        world_types = dict(AutoWorld.AutoWorldRegister.world_types)
        world_types["FakeCompanion"] = _FakeWorld

        with mock.patch.object(AutoWorld, "call_all", lambda *a, **kw: None), \
                mock.patch.object(Fill, "distribute_items_restrictive", fake_dist), \
                mock.patch.dict(AutoWorld.AutoWorldRegister.world_types,
                                world_types, clear=True):
            verdict = world._probe_two_stage_fillable()
        return verdict, captured.get("pmw")

    def test_mirrors_player_count_and_games(self):
        """The dry run has one slot per real slot, running the same games. This is
        the bug: it used to be _MW(1) with only CTR, no matter the real room."""
        verdict, pmw = self._probe({1: "Crash Team Racing", 2: "FakeCompanion",
                                    3: "FakeCompanion"})
        self.assertIs(verdict, True)
        self.assertEqual(pmw.players, 3)
        self.assertEqual(dict(pmw.game), {1: "Crash Team Racing",
                                          2: "FakeCompanion", 3: "FakeCompanion"})
        self.assertEqual(sorted(pmw.worlds), [1, 2, 3])
        self.assertIsInstance(pmw.worlds[1], ctrAPWorld)
        self.assertIsInstance(pmw.worlds[2], _FakeWorld)
        self.assertIsInstance(pmw.worlds[3], _FakeWorld)

    def test_each_slot_carries_its_own_option_object(self):
        """Identical option OBJECTS, per slot -- the same construction style the
        shipped solo probe used for CTR (`pw.options = self.options`). Same object
        means the mirrored slot rolls identically to the slot it mirrors."""
        real_games = {1: "Crash Team Racing", 2: "FakeCompanion"}
        real = _fake_real_multiworld(real_games)
        world = ctrAPWorld.__new__(ctrAPWorld)
        world.multiworld = real
        world.player = 1
        world.options = real.worlds[1].options

        captured = {}
        world_types = dict(AutoWorld.AutoWorldRegister.world_types)
        world_types["FakeCompanion"] = _FakeWorld
        with mock.patch.object(AutoWorld, "call_all", lambda *a, **kw: None), \
                mock.patch.object(Fill, "distribute_items_restrictive",
                                  lambda pmw, *a, **kw: captured.update(pmw=pmw)), \
                mock.patch.dict(AutoWorld.AutoWorldRegister.world_types,
                                world_types, clear=True):
            world._probe_two_stage_fillable()

        pmw = captured["pmw"]
        for p in real_games:
            self.assertIs(pmw.worlds[p].options, real.worlds[p].options,
                          f"slot {p} must carry the real slot's own option object")

    def test_mirrors_names_and_seed(self):
        """Same seed -> same random stream -> the dry run makes the same fill
        decisions as the real fill it is predicting."""
        _, pmw = self._probe({1: "Crash Team Racing", 2: "FakeCompanion"})
        self.assertEqual(pmw.seed, 123456789)
        self.assertEqual(dict(pmw.player_name), {1: "Player1", 2: "Player2"})

    def test_solo_is_still_a_one_player_dry_run(self):
        """SOLO BEHAVIOUR IS PRESERVED. With one player the mirror is _MW(1)
        carrying this world's own options, i.e. exactly the shipped probe. The
        0.2.0 change must not move solo generation at all."""
        verdict, pmw = self._probe({1: "Crash Team Racing"})
        self.assertIs(verdict, True)
        self.assertEqual(pmw.players, 1)
        self.assertEqual(dict(pmw.game), {1: "Crash Team Racing"})
        self.assertEqual(sorted(pmw.worlds), [1])
        self.assertIsInstance(pmw.worlds[1], ctrAPWorld)


class ProbeVerdicts(unittest.TestCase):
    """What the probe RETURNS, which is what pre_fill acts on."""

    def _probe_raising(self, exc, games=None):
        games = games or {1: "Crash Team Racing", 2: "FakeCompanion"}
        real = _fake_real_multiworld(games)
        world = ctrAPWorld.__new__(ctrAPWorld)
        world.multiworld = real
        world.player = 1
        world.options = real.worlds[1].options

        def boom(pmw, *a, **kw):
            raise exc

        world_types = dict(AutoWorld.AutoWorldRegister.world_types)
        world_types["FakeCompanion"] = _FakeWorld
        with mock.patch.object(AutoWorld, "call_all", lambda *a, **kw: None), \
                mock.patch.object(Fill, "distribute_items_restrictive", boom), \
                mock.patch.dict(AutoWorld.AutoWorldRegister.world_types,
                                world_types, clear=True):
            return world._probe_two_stage_fillable()

    def test_predicted_fill_error_returns_false(self):
        """False is the only verdict that collapses stage 2."""
        self.assertIs(self._probe_raising(Fill.FillError("no more spots")), False)

    def test_any_other_error_fails_open(self):
        """FAIL-OPEN. A probe that cannot run must keep two-stage: the probe is
        allowed to be unavailable, it is not allowed to make a fillable seed
        worse. Companion worlds are arbitrary third-party code, so 'the probe
        blew up on someone else's world' is a real case, not a hypothetical."""
        for exc in (RuntimeError("companion exploded"),
                    KeyError("missing option"),
                    ValueError("bad data")):
            with self.subTest(exc=type(exc).__name__):
                self.assertIsNone(self._probe_raising(exc))

    def test_non_contiguous_player_ids_fail_open(self):
        """_MW(n) builds slots 1..n. If a real room ever numbers its slots any
        other way, mirroring it by count would silently predict for the wrong
        slots, so the probe declines instead."""
        real = _fake_real_multiworld({1: "Crash Team Racing", 3: "FakeCompanion"})
        world = ctrAPWorld.__new__(ctrAPWorld)
        world.multiworld = real
        world.player = 1
        world.options = real.worlds[1].options
        called = []
        with mock.patch.object(Fill, "distribute_items_restrictive",
                               lambda *a, **kw: called.append(1)):
            self.assertIsNone(world._probe_two_stage_fillable())
        self.assertEqual(called, [], "must not run a dry run it cannot trust")


class ProbeRunsOnARealMultiworld(unittest.TestCase):
    """End-to-end: the probe survives a genuine 2-player generation. The unit
    tests above stub call_all, so this is the one that proves the constructed room
    is actually generatable."""

    def test_probe_returns_a_real_verdict_in_a_two_player_room(self):
        from BaseClasses import MultiWorld, CollectionState
        from argparse import Namespace

        games = {1: "Crash Team Racing", 2: "Archipelago"}
        mw = MultiWorld(len(games))
        mw.game = dict(games)
        mw.player_name = {1: "CTR", 2: "Partner"}
        mw.set_seed(4242)
        args = Namespace()
        per = {}
        for player, game in games.items():
            wt = AutoWorld.AutoWorldRegister.world_types[game]
            for name, option in wt.options_dataclass.type_hints.items():
                per.setdefault(name, {})[player] = option.from_any(option.default)
        for name, mapping in per.items():
            setattr(args, name, mapping)
        mw.set_options(args)
        mw.state = CollectionState(mw)
        for step in ("generate_early", "create_regions", "create_items",
                     "set_rules", "connect_entrances", "generate_basic"):
            AutoWorld.call_all(mw, step)

        verdict = mw.worlds[1]._probe_two_stage_fillable()
        # True or False are both legitimate seed-dependent answers; None would mean
        # the probe could not construct/generate the mirrored room at all, which is
        # the failure this test exists to catch.
        self.assertIn(verdict, (True, False),
                      "probe failed open on a plain 2-player room")


if __name__ == "__main__":
    unittest.main()
