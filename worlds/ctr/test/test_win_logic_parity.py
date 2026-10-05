"""Parity: the `win_logic` slot_data block equals Archipelago's logic.

Race-loss DeathLink stakes (Contract 7m, `SCHEMA.md`). Native decides a
race's stakes by evaluating the block; the block is serialised from the term
objects the rules are compiled from (`logic_terms`). This test closes the
loop from the other side: it evaluates the emitted JSON with
`WireEvaluator`, a reference evaluator written from the wire schema with
native's inputs only (received counts by AP item id, three `ctr_options`
scalars and the bosses-won tally), and asserts

    eval(regions[entry.region]) and eval(entry.rule) == location.can_reach(state)

for every win check, on random-option seeds and random item sets. The region
half is also compared on its own against `Region.can_reach`.

The evaluator receives items the way the server sends them: start inventory
(every precollected item) as `NetworkItem(id, -2, 0)`, flags 0 whatever its
classification (MultiServer), and every other item with its own flags. Its
counts are the progression-flagged entries off location -2 plus the block's
`start` table, as SCHEMA.md "Received count" specifies.
`TestWinLogicStartInventory` covers seeds with a YAML start inventory, the
`start_inventory_from_pool` mechanism and the tight-fill backstop's
precollect.

The states need not be reachable ones: the two sides must agree everywhere.
A plain lambda ANDed onto a win check later makes the exporter raise
(`WinLogicExportError`), so the guard is the generation itself.

Seeds: `CTR_WIN_LOGIC_SEEDS` (default 150), split into chunks so xdist runs
them in parallel. `python -m worlds.ctr.test.test_win_logic_parity N` prints
the coverage tally.
"""
import collections
import copy
import json
import os
import random
import sys
import unittest
from typing import Dict

from unittest import mock

from BaseClasses import CollectionState
from Options import OptionError
from test.general import setup_multiworld
from worlds.AutoWorld import call_all

from .. import ctrAPWorld
from ..characters import ROSTER_CHARACTER_ID, unlock_item_name
from ..progressive_capability import BOOST_CHAIN, boost_item_name
from ..win_logic import win_kind, wire_size

STEPS = ("generate_early", "create_regions", "create_items", "set_rules")
PLAYER = 1
N_SEEDS = int(os.environ.get("CTR_WIN_LOGIC_SEEDS", "150"))
CHUNKS = 10
STATES_PER_SEED = 40
BOSS_FLAGS = ("Ripper Roo Boss Race Won", "Papu Papu Boss Race Won",
              "Komodo Joe Boss Race Won", "Pinstripe Boss Race Won")

#: Every logic-relevant option, drawn as `random` per seed (the research 02
#: prototype set plus the remaining rule inputs).
RANDOM_OPTS = (
    "progressive_boost", "progressive_boost_blue_fire", "progressive_stats",
    "logic_difficulty", "itemsanity", "lettersanity", "letters_per_track",
    "racer_locked_pads", "character_unlocks", "warppad_unlock_requirements",
    "shortcut_knowledge", "oxide_goal", "bosses_required_goal",
    "gems_required_goal", "oxide_final_challenge_unlock", "oxide_final_track",
    "cortex_vortex_track", "slide_coliseum_races", "turbo_track_races",
    "include_gem_cups", "randomize_gem_cup_tracks", "include_battle_arenas",
    "two_stage_density", "requirement_variety", "relic_perfect_checks",
    "warp_pad_shuffle_grouping", "box_locations", "shuffle_keys",
    "shuffle_gems", "sapphire_relic_count", "gold_relic_count",
    "platinum_relic_count", "podium_placement_checks", "hit_character",
    "oxide_1_optional", "remove_playable_oxide",
)

_TOKEN_IDS_NO_PURPLE = (35010004, 35010005, 35010006, 35010007)
# Contract section 2: (type, colour) -> the item ids a Req counts.
_TOKENS = (35010004, 35010005, 35010006, 35010007, 35010008)
_RELICS = (35010001, 35010002, 35010003)
_GEMS = (35010009, 35010010, 35010011, 35010012, 35010013)


class MalformedBlock(AssertionError):
    """The block breaks SCHEMA.md; native refuses the whole block."""


def _req_ids(rtype, colour):
    """SCHEMA.md `req`: types 3 and 5 name one colour 0..4; type 4 one tier
    0..2 or the legacy -1 (Sapphire). Any other colour on those types makes
    the block malformed (native refuses it)."""
    if rtype == 1:
        return (35010000,)
    if rtype == 2:
        return (35010014,)
    if rtype in (3, 5):
        if not 0 <= colour <= 4:
            raise MalformedBlock(f"req type {rtype} colour {colour}")
        return ((_TOKENS if rtype == 3 else _GEMS)[colour],)
    if rtype == 4:
        if not -1 <= colour <= 2:
            raise MalformedBlock(f"req type 4 tier {colour}")
        return (_RELICS[max(colour, 0)],)
    return {6: _TOKENS, 7: _RELICS, 8: _GEMS}[rtype]


class WireEvaluator:
    """Evaluates `win_logic` version 1 exactly as SCHEMA.md specifies, from
    native's inputs only."""

    def __init__(self, block, ctr_options, received: Dict[int, int],
                 bosses_won: int, item_ids: Dict[str, int]):
        """`received`: native's tally, `_received` of the server's entries."""
        assert block["version"] == 1
        self.block = block
        self.received = received
        self.start_table = {}
        for key, n in block["start"].items():
            if not (key.isdigit() and key[0] != "0") or type(n) is not int or n < 1:
                raise MalformedBlock(f"start {key!r}: {n!r}")
            self.start_table[int(key)] = n
        self.bosses_won = bosses_won
        self.boost_mode = int(ctr_options["boost_mode"])
        self.start = int(ctr_options["starting_character"])
        self.unlocks = bool(ctr_options["character_unlocks"])
        by_id = {cid: name for name, cid in ROSTER_CHARACTER_ID.items()}
        self.unlock_id = {cid: item_ids[unlock_item_name(n)] for cid, n in by_id.items()}
        self.boost_id = {cid: item_ids[boost_item_name(n)] for cid, n in by_id.items()}
        self.shared_boost = item_ids[BOOST_CHAIN]
        self.used = collections.Counter()

    def count(self, item_id):
        """SCHEMA.md "Received count": the tally plus the `start` table."""
        return self.received.get(item_id, 0) + self.start_table.get(item_id, 0)

    def in_logic(self, location_id: int) -> bool:
        entry = self.block["checks"][str(location_id)]
        return (self.eval(self.block["regions"][entry["region"]])
                and self.eval(entry["rule"]))

    def _driveable(self, c):
        return c == self.start or not self.unlocks or self.count(self.unlock_id[c]) >= 1

    def _boost_ok(self, c, boost):
        if boost == 0 or self.boost_mode == 0:
            return True
        n = (self.count(self.shared_boost) if self.boost_mode == 1
             else self.count(self.boost_id[c]))
        return n >= boost

    def eval(self, t) -> bool:
        if t is True or t is False:
            return t
        tag = t[0]
        self.used[tag] += 1
        if tag == "all":
            return all(self.eval(c) for c in t[1:])
        if tag == "any":
            return any(self.eval(c) for c in t[1:])
        if tag == "req":
            _, rtype, count, colour = t
            assert 1 <= rtype <= 8
            return sum(self.count(i) for i in _req_ids(rtype, colour)) >= count
        if tag == "tokens_no_purple":
            return sum(self.count(i) for i in _TOKEN_IDS_NO_PURPLE) >= t[1]
        if tag == "items":
            _, mode, count, ids = t
            assert ids and len(set(ids)) == len(ids)
            if mode == "sum":
                return sum(self.count(i) for i in ids) >= count
            assert mode == "distinct"
            return sum(1 for i in ids if self.count(i) >= 1) >= count
        if tag == "cap":
            _, boost, racer = t
            if racer >= 0:
                return self._driveable(racer) and self._boost_ok(racer, boost)
            if boost == 0 or self.boost_mode == 0:
                return True
            return any(self._driveable(c) and self._boost_ok(c, boost)
                       for c in range(16))
        if tag == "bosses":
            return self.bosses_won >= t[1]
        if tag == "families":
            held = sum(1 for fam in self.block["families"]
                       if any(self.count(i) >= 1 for i in fam))
            return held >= t[1]
        if tag == "ref":
            return self.in_logic(t[1])
        raise AssertionError(f"unknown tag {tag!r}")


def _pick(rng, cls):
    """A concrete random value for one option class, drawn from `rng` so a
    failing draw is reproducible (the "random" option string resolves through
    the unseeded global RNG)."""
    from Options import Choice, Range, Toggle
    if issubclass(cls, Toggle):
        return rng.random() < 0.5
    if issubclass(cls, Choice):
        return rng.choice(sorted(cls.name_lookup.values()))
    if issubclass(cls, Range):
        return rng.randint(cls.range_start, cls.range_end)
    return cls.default


def _random_options(rng):
    from ..Options import ctrAPOptions
    hints = ctrAPOptions.type_hints
    opts = {k: _pick(rng, hints[k]) for k in RANDOM_OPTS}
    opts["accessibility"] = "minimal"  # rules do not read it; raises the valid rate
    if rng.random() < 0.25:
        from ..custom_tracks import BABY_T_PARK_CURRENT
        entry = copy.deepcopy(BABY_T_PARK_CURRENT)
        entry["modes"] = {"ctr_challenge": rng.random() < 0.7}
        opts["custom_tracks"] = {"baby-t-park": entry}
    return opts


START_LOCATION = -2  # MultiServer: start inventory is NetworkItem(id, -2, 0)


def _player_items(mw):
    """Every item this slot can receive during play: the pool and the items
    locked onto locations (vanilla-pinned Purple tokens, Gems, ...), whatever
    their classification, as (item, server location). Pool items are not
    placed yet; any found location is positive, so 1 stands in for it. The
    start inventory is not here: the server always sends it (`_start_entries`)
    and every `CollectionState` already holds it."""
    items = [(it, 1) for it in mw.itempool if it.player == PLAYER]
    items += [(loc.item, int(loc.address)) for loc in mw.get_locations()
              if loc.item is not None and loc.item.player == PLAYER
              and loc.address is not None]
    return items


def _start_entries(mw):
    """The start inventory exactly as MultiServer sends it: every precollected
    item with a code, as (id, -2, flags 0), whatever its classification."""
    return [(int(it.code), START_LOCATION, 0)
            for it in mw.precollected_items[PLAYER] if it.code is not None]


def _received(entries):
    """Native's tally from ReceivedItems entries (id, location, flags): only
    progression-flagged copies off location -2 (SCHEMA.md "Received count").
    The block's `start` table supplies the start inventory."""
    out = collections.Counter()
    for item_id, location, flags in entries:
        if location != START_LOCATION and flags & 0b001:
            out[item_id] += 1
    return out


def _states(mw, rng, n):
    """(Archipelago state, native's tally) pairs. The state is a fresh
    `CollectionState`, which holds the precollected items, plus the chosen
    advancement copies, as collection does. Native's entries are the start
    inventory as the server sends it plus the chosen copies with their own
    flags."""
    items = _player_items(mw)
    start = _start_entries(mw)
    events = [loc.item.name for loc in mw.get_locations(PLAYER)
              if loc.item is not None and loc.address is None]

    def build(chosen, chosen_events):
        state = CollectionState(mw)
        for it, _ in chosen:
            if it.advancement:
                state.add_item(it.name, PLAYER)
        for name in chosen_events:
            state.add_item(name, PLAYER)
        entries = start + [(int(it.code), loc, it.flags)
                           for it, loc in chosen if it.code is not None]
        return state, _received(entries)

    yield build([], [])
    yield build(items, events)
    for _ in range(n):
        p = rng.choice((0.15, 0.35, 0.6, 0.85))
        yield build([it for it in items if rng.random() < p],
                    [name for name in events if rng.random() < 0.5])


def check_seed(mw, rng, states_per_seed=STATES_PER_SEED, tally=None):
    """Compare the block with can_reach on one generated multiworld. Returns
    a list of disagreement descriptions (empty = parity)."""
    world = mw.worlds[PLAYER]
    slot_data = world.fill_slot_data()
    block = slot_data["win_logic"]
    assert json.loads(json.dumps(block)) == block
    assert wire_size(block) < 32 * 1024, wire_size(block)
    wins = {int(loc.address): loc for loc in mw.get_locations(PLAYER)
            if loc.address is not None and win_kind(loc.name)}
    assert set(map(int, block["checks"])) == set(wins), "entry set != win checks"
    item_ids = world.item_name_to_id
    bad = []
    for state, received in _states(mw, rng, states_per_seed):
        bosses = sum(1 for f in BOSS_FLAGS if state.has(f, PLAYER))
        ev = WireEvaluator(block, slot_data["ctr_options"], received, bosses, item_ids)
        for loc_id, loc in wins.items():
            entry = block["checks"][str(loc_id)]
            region_want = loc.parent_region.can_reach(state)
            region_got = ev.eval(block["regions"][entry["region"]])
            want = loc.can_reach(state)
            got = ev.in_logic(loc_id)
            if tally is not None:
                tally["evaluations"] += 1
                tally["kind:" + entry["kind"]] += 1
            if want != got or region_want != region_got:
                bad.append({"loc": loc.name, "can_reach": want, "wire": got,
                            "region_can_reach": region_want, "region_wire": region_got,
                            "rule": entry["rule"],
                            "region": block["regions"][entry["region"]]})
        if tally is not None:
            tally.update({"op:" + k: v for k, v in ev.used.items()})
    return bad


def run(n_seeds, rng_seed, tally=None, sizes=None):
    """Generate `n_seeds` valid random-option seeds and check each one."""
    rng = random.Random(rng_seed)
    done = attempts = 0
    failures = []
    while done < n_seeds:
        attempts += 1
        assert attempts <= n_seeds * 10, f"only {done} valid seeds in {attempts} attempts"
        seed = rng.randrange(1 << 30)
        options = _random_options(rng)
        try:
            mw = setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)
        except OptionError:
            continue
        done += 1
        bad = check_seed(mw, rng, tally=tally)
        for b in bad[:1]:
            b["seed"], b["options"] = seed, {k: str(v) for k, v in options.items()}
        if sizes is not None:
            sizes.append(wire_size(mw.worlds[PLAYER].fill_slot_data()["win_logic"]))
        if tally is not None:
            tally["seeds"] += 1
            o = mw.worlds[PLAYER].options
            for name in ("progressive_boost", "warppad_unlock_requirements",
                         "include_battle_arenas", "itemsanity", "logic_difficulty",
                         "lettersanity", "oxide_goal", "shortcut_knowledge",
                         "cortex_vortex_track", "character_unlocks"):
                tally[f"opt:{name}={int(getattr(o, name).value)}"] += 1
            tally["opt:racer_locks_drawn"] += bool(getattr(mw.worlds[PLAYER], "ctr_racer_locks", None))
            tally["opt:custom_track"] += "custom_tracks" in options
            tally["checks"] += len([1 for loc in mw.get_locations(PLAYER)
                                    if loc.address is not None and win_kind(loc.name)])
        if bad:
            failures.append((seed, bad[:3], len(bad)))
    if tally is not None:
        tally["attempts"] += attempts
    return failures


class TestWinLogicParity(unittest.TestCase):
    """`CHUNKS` methods, each `N_SEEDS / CHUNKS` seeds, so xdist parallelises."""


def _make_chunk(index):
    def test(self):
        per = max(1, N_SEEDS // CHUNKS)
        failures = run(per, 20261002 + index)
        self.assertEqual(failures, [], json.dumps(failures, default=str)[:4000])
    test.__name__ = f"test_parity_chunk_{index}"
    return test


for _i in range(CHUNKS):
    setattr(TestWinLogicParity, f"test_parity_chunk_{_i}", _make_chunk(_i))


class TestWinLogicFixedSeeds(unittest.TestCase):
    """Named option corners the random draw reaches rarely."""

    CASES = (
        {},
        {"warppad_unlock_requirements": "vanilla"},
        {"progressive_boost": "per_character", "character_unlocks": True,
         "racer_locked_pads": 6, "itemsanity": True, "box_locations": True,
         "include_battle_arenas": False, "lettersanity": "locations_and_items",
         "logic_difficulty": "easy"},
        {"progressive_boost": "shared_global", "progressive_boost_blue_fire": True,
         "oxide_goal": "101_percent", "bosses_required_goal": 4,
         "gems_required_goal": 5, "oxide_final_challenge_unlock": "any_relic_type",
         "cortex_vortex_track": True, "lettersanity": "items_only",
         "box_locations": True},
        {"progressive_boost": "shared_global", "oxide_goal": "any_percent",
         "bosses_required_goal": 2, "gems_required_goal": 3,
         "shortcut_knowledge": "hard", "itemsanity": True, "box_locations": True,
         "slide_coliseum_races": "trophy_and_ctr_challenge",
         "turbo_track_races": "trophy_race"},
        {"oxide_goal": "disabled", "bosses_required_goal": 4},
    )

    def test_corners(self):
        rng = random.Random(7)
        for case in self.CASES:
            with self.subTest(options=case):
                mw = setup_multiworld(ctrAPWorld, STEPS, seed=11, options=case)
                self.assertEqual(check_seed(mw, rng, states_per_seed=60), [])


def generate_with_start(options, seed, steps=STEPS, from_pool=None):
    """`setup_multiworld` in Main.py's order around the start inventory: the
    YAML `start_inventory` (and `from_pool`, Main's
    `start_inventory_from_pool` handling) is precollected right after
    `generate_early` with `create_item`, and the `from_pool` copies are then
    removed from the item pool and topped up with filler after
    `generate_basic` (or at the end), before `pre_fill`."""
    mw = setup_multiworld(ctrAPWorld, (), seed=seed, options=options)
    world = mw.worlds[PLAYER]
    pending = dict(from_pool or {})

    def deplete():
        for name, n in pending.items():
            for _ in range(n):
                index = next(i for i, it in enumerate(mw.itempool)
                             if it.player == PLAYER and it.name == name)
                del mw.itempool[index]
                mw.itempool.append(world.create_filler())
        pending.clear()

    for step in steps:
        if step == "pre_fill":
            deplete()
        call_all(mw, step)
        if step == "generate_early":
            for name, n in world.options.start_inventory.value.items():
                for _ in range(n):
                    mw.push_precollected(mw.create_item(name, PLAYER))
            for name, n in pending.items():
                for _ in range(n):
                    mw.push_precollected(mw.create_item(name, PLAYER))
        if step == "generate_basic":
            deplete()
    deplete()
    return mw


class TestWinLogicStartInventory(unittest.TestCase):
    """Review B1: the server sends start inventory with flags 0, but
    Archipelago's logic and Universal Tracker count its progression copies.
    The block's `start` table carries them; every source of precollected
    items must keep parity."""

    def _check(self, mw, states=40):
        precollected = [it for it in mw.precollected_items[PLAYER] if it.code is not None]
        self.assertTrue(precollected, "the seed has no start inventory")
        block = mw.worlds[PLAYER].fill_slot_data()["win_logic"]
        want = collections.Counter(str(int(it.code)) for it in precollected if it.advancement)
        self.assertEqual(block["start"], dict(want))
        self.assertEqual(check_seed(mw, random.Random(5), states_per_seed=states), [])
        return block

    def test_yaml_start_inventory(self):
        coco_unlock = unlock_item_name("Coco Bandicoot")
        cases = (
            {"start_inventory": {"Key": 4, "Trophy": 16}},
            {"progressive_boost": "shared_global",
             "start_inventory": {"Progressive Boost": 3}},
            {"start_inventory": {"Sapphire Relic": 5, "Red CTR Token": 4,
                                 "Green CTR Token": 4, "Blue CTR Token": 4,
                                 "Yellow CTR Token": 4, "Wumpa Fruit": 2}},
            {"progressive_boost": "per_character", "character_unlocks": True,
             "starting_character": "crash_bandicoot",
             "start_inventory": {coco_unlock: 1,
                                 boost_item_name("Coco Bandicoot"): 2,
                                 "Key": 1}},
            {"warppad_unlock_requirements": "vanilla", "accessibility": "minimal",
             "start_inventory": {"Gold Relic": 3, "Platinum Relic": 2,
                                 "Red Gem": 1, "Purple CTR Token": 2}},
            {"oxide_goal": "101_percent", "bosses_required_goal": 4,
             "gems_required_goal": 5, "include_battle_arenas": False,
             "start_inventory": {"Purple Gem": 1, "Yellow CTR Token": 3,
                                 "Trophy": 8}},
        )
        for case in cases:
            with self.subTest(options=case):
                try:
                    mw = generate_with_start(case, seed=13)
                except OptionError as exc:
                    self.fail(f"fixture refused: {exc}")
                self._check(mw)

    def test_random_options_with_start_inventory(self):
        """Random option draws, each with a random start inventory drawn from
        the slot's own progression items."""
        rng = random.Random(4242)
        done = attempts = 0
        while done < 12:
            attempts += 1
            self.assertLess(attempts, 150)
            seed = rng.randrange(1 << 30)
            options = _random_options(rng)
            try:
                probe = setup_multiworld(ctrAPWorld, STEPS, seed=seed, options=options)
            except OptionError:
                continue
            names = sorted({it.name for it in probe.itempool
                            if it.player == PLAYER and it.advancement})
            pick = rng.sample(names, min(len(names), rng.randint(1, 6)))
            options = dict(options, start_inventory={n: rng.randint(1, 4) for n in pick})
            mw = generate_with_start(options, seed)
            with self.subTest(seed=seed, start=options["start_inventory"]):
                self._check(mw, states=20)
            done += 1

    def test_start_inventory_from_pool(self):
        """CTR declares no `start_inventory_from_pool` option today; this pins
        Main.py's mechanism for it (create_item copies precollected, the pool
        copies removed) in case one is added."""
        from_pool = {"Key": 2, "Sapphire Relic": 3, "Red CTR Token": 2}
        mw = generate_with_start({}, seed=17, from_pool=from_pool)
        pool = collections.Counter(it.name for it in mw.itempool if it.player == PLAYER)
        ref = generate_with_start({}, seed=17)
        ref_pool = collections.Counter(it.name for it in ref.itempool if it.player == PLAYER)
        for name, n in from_pool.items():
            self.assertEqual(pool[name], ref_pool[name] - n, name)
        self._check(mw)

    def test_backstop_precollect(self):
        """The tight-fill backstop (`_rollback_precollect_backstop`) moves
        stranded pool items into the start inventory. Natural firings are
        about 0.1 to 0.2 percent of solo seeds, so the simulation is forced to
        dead-end once and to name two progression items; the precollect
        itself is the backstop's own code."""
        world_cls = ctrAPWorld
        calls = {"n": 0}

        def simulate(self, panic):
            calls["n"] += 1
            return calls["n"] > 1

        def stranded(self):
            names = [it.name for it in self.multiworld.itempool
                     if it.player == self.player and it.advancement
                     and it.name in ("Key", "Trophy", "Sapphire Relic")]
            return sorted(set(names))[:2]

        steps = STEPS + ("connect_entrances", "generate_basic", "pre_fill")
        with mock.patch.object(world_cls, "_rollback_simulate_fill", simulate), \
                mock.patch.object(world_cls, "_rollback_enumerate_stranded", stranded):
            mw = generate_with_start({}, seed=19, steps=steps)
        world = mw.worlds[PLAYER]
        self.assertTrue(getattr(world, "_ctr_backstop_fired", False))
        self.assertEqual(len(world._ctr_backstop_items), 2)
        block = self._check(mw)
        self.assertTrue(block["start"])


if __name__ == "__main__":
    # Evidence run: python -m worlds.ctr.test.test_win_logic_parity N [rng_seed]
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_SEEDS
    tally = collections.Counter()
    sizes = []
    fails = run(n, int(sys.argv[2]) if len(sys.argv) > 2 else 1, tally, sizes)
    sizes.sort()
    print(json.dumps({"failures": len(fails), "tally": dict(sorted(tally.items())),
                      "size_min_median_max": [sizes[0], sizes[len(sizes) // 2], sizes[-1]],
                      "failure_samples": fails[:3]}, indent=1, default=str))
