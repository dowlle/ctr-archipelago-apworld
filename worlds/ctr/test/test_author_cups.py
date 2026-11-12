"""Track author cups (A4-71, ruled 2026-11-12 19:40 CET): a drawn cup named after
a track author races that author's tracks first, without retries, extra
passes or a change to any other cup or option meaning."""
import copy
import json
import pkgutil
import random
import unittest

from .. import content_cups, content_plan, cup_checks, track_credits
from .test_content_plan import make_world, profile_options


class _World:
    def __init__(self, seed):
        self.random = random.Random(seed)


def _retail(n):
    return dict(id=f"retail:{n}", origin="retail", retail_id=n, laps=3)


def _custom(slot, key):
    return dict(id=f"custom/{key}/1.0", origin="custom", package_id=f"package/{key}/1.0", custom_slot=slot, laps=3)


def _spec(cap=4, within=False, across=True):
    return dict(custom_legs=(0, cap), repeats=dict(within_cup=within, across_cups=across))


class TestAuthors(unittest.TestCase):
    def test_registry_credits_and_package_labels(self):
        self.assertEqual(track_credits.authors_of(dict(origin="cortex_vortex")), {"lockheart"})
        shared = track_credits.authors_of(_custom(1, "sids-house"), dict(content_id="sids-house", author="Unknown"))
        self.assertTrue({"lolothesamurai", "panchopew"} <= shared)
        label = track_credits.authors_of(_custom(2, "no-such-key"), dict(content_id="no-such-key",
                                                                          author="Boxic & PanchoPew"))
        self.assertEqual(label, {"boxic", "panchopew"})
        self.assertEqual(track_credits.authors_of(_retail(3)), frozenset())

    def test_credits_share_the_named_tracks_pin(self):
        """Both files come from one registry commit (tools/build_named_tracks.py)."""
        credits = json.loads(pkgutil.get_data("worlds.ctr", "data/track_credits.json"))
        named = json.loads(pkgutil.get_data("worlds.ctr", "data/named_tracks.json"))
        self.assertEqual(credits["registry"], named["registry"])
        self.assertEqual(credits["format"], 1)

    def test_every_author_cup_is_drawable_and_has_registry_tracks(self):
        drawable = {cup_checks.CUP_NAMES[i] for i in cup_checks.CUP_DRAW_INDICES}
        credited = {name.lower() for names in track_credits.REGISTRY_CREDITS.values() for name in names}
        for cup, author in cup_checks.CUP_TRACK_AUTHORS.items():
            self.assertIn(cup, drawable)
            self.assertIn(author.lower(), credited)
        self.assertEqual(cup_checks.CUP_NAMES[41:], ("Boxic Cup", "Lolothesamurai Cup", "PanchoPew Cup"))


class TestPrefer(unittest.TestCase):
    BOXIC = cup_checks.CUP_NAMES.index("Boxic Cup")
    TESTER = cup_checks.CUP_NAMES.index("Patries Cup")

    def setUp(self):
        self.custom = [_custom(1, "a"), _custom(2, "b"), _custom(3, "c"), _custom(4, "d"), _custom(5, "e")]
        self.authors = {t["id"]: frozenset({"boxic"} if t["id"].split("/")[1] in "bce" else {"other"})
                        for t in self.custom}

    def cup(self, index, legs):
        return dict(cup_index=index, id=f"cup:{index}", legs=list(legs), shortened=True)

    def test_author_tracks_first_then_today(self):
        cups = [self.cup(self.BOXIC, [_retail(0), self.custom[0], _retail(1), _retail(2)])]
        content_cups.prefer_author_tracks(_World(1), cups, self.custom, _spec(), self.authors)
        legs = cups[0]["legs"]
        self.assertEqual({t["id"] for t in legs if t["origin"] == "custom"},
                         {self.custom[i]["id"] for i in (1, 2, 4)})
        self.assertEqual(len({t["id"] for t in legs}), 4)
        # The other author's custom leg is replaced first, then original legs.
        self.assertEqual(sum(t["origin"] == "retail" for t in legs), 1)

    def test_cup_custom_legs_caps_the_preference(self):
        for cap in range(5):
            legs = [_retail(0), _retail(1), _retail(2), _retail(3)]
            cups = [self.cup(self.BOXIC, legs)]
            content_cups.prefer_author_tracks(_World(cap), cups, self.custom, _spec(cap), self.authors)
            self.assertEqual(sum(t["origin"] == "custom" for t in cups[0]["legs"]), min(cap, 3))

    def test_held_legs_stay_and_nothing_is_drawn_when_enough(self):
        legs = [self.custom[1], self.custom[2], self.custom[4], _retail(5)]
        cups = [self.cup(self.BOXIC, legs)]
        world = _World(7)
        state = world.random.getstate()
        content_cups.prefer_author_tracks(world, cups, self.custom, _spec(), self.authors)
        self.assertEqual(cups[0]["legs"], legs)
        self.assertEqual(world.random.getstate(), state)

    def test_no_author_tracks_draws_nothing(self):
        authors = {t["id"]: frozenset({"other"}) for t in self.custom}
        legs = [_retail(0), self.custom[0], _retail(1), _retail(2)]
        cups = [self.cup(self.BOXIC, legs), self.cup(self.TESTER, legs),
                dict(gem_cup=0, cup_index=None, id="gem_cup:0", legs=list(legs), shortened=True)]
        world = _World(3)
        state = world.random.getstate()
        content_cups.prefer_author_tracks(world, cups, self.custom, _spec(), authors)
        self.assertEqual([c["legs"] for c in cups], [legs, legs, legs])
        self.assertEqual(world.random.getstate(), state)

    def test_tester_and_gem_cups_are_unchanged(self):
        legs = [_retail(0), self.custom[0], _retail(1), _retail(2)]
        cups = [self.cup(self.TESTER, legs), dict(gem_cup=1, cup_index=None, id="gem_cup:1", legs=list(legs))]
        content_cups.prefer_author_tracks(_World(4), cups, self.custom, _spec(), self.authors)
        self.assertEqual([c["legs"] for c in cups], [legs, legs])

    def test_no_repeat_across_cups_is_left_alone(self):
        legs = [_retail(0), _retail(1), _retail(2), _retail(3)]
        cups = [self.cup(self.BOXIC, legs)]
        content_cups.prefer_author_tracks(_World(5), cups, self.custom, _spec(across=False), self.authors)
        self.assertEqual(cups[0]["legs"], legs)

    def test_deterministic(self):
        def run(seed):
            cups = [self.cup(self.BOXIC, [_retail(0), self.custom[0], _retail(1), _retail(2)])]
            content_cups.prefer_author_tracks(_World(seed), cups, self.custom, _spec(), self.authors)
            return [t["id"] for t in cups[0]["legs"]]
        self.assertEqual(run(11), run(11))


def _lockheart_options():
    """Baby T Park (Lockheart's package) and the bundled Cortex Vortex in the
    pool, 27 cups, so Lockheart Cup is drawn on some seeds."""
    options = profile_options()
    pool = options["content_pool"]
    pool["tracks"]["custom"] = [copy.deepcopy(content_plan.PACKAGES[1])]
    pool["tracks"]["cortex_vortex"] = True
    pool["required_entries"] = []
    pool["cups"] = dict(count=dict(min=27, max=27))
    return options


class TestLockheartCupOnAPlan(unittest.TestCase):
    def test_lockheart_cup_races_his_tracks(self):
        lockheart = content_cups.entry_id(cup_checks.CUP_NAMES.index("Lockheart Cup"))
        seen = 0
        for seed in range(12):
            plan = make_world(_lockheart_options(), seed=seed).ctr_content_plan
            entries = {e["id"]: e for e in plan["entries"] if e.get("kind") == content_cups.KIND}
            if lockheart not in entries:
                continue
            seen += 1
            tracks = {leg["track_id"] for leg in entries[lockheart]["legs"]}
            self.assertTrue(any(t.startswith("custom/baby-t-park/") for t in tracks), (seed, tracks))
            self.assertTrue(any("cortex" in t for t in tracks), (seed, tracks))
        self.assertGreater(seen, 0, "no seed drew Lockheart Cup; widen the seed range")

    def test_same_seed_same_plan(self):
        a = make_world(_lockheart_options(), seed=5).ctr_content_plan
        b = make_world(_lockheart_options(), seed=5).ctr_content_plan
        self.assertEqual(content_plan.canonical(a), content_plan.canonical(b))


if __name__ == "__main__":
    unittest.main()
