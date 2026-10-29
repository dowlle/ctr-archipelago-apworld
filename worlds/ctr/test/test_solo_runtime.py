"""Solo runtime wrapper (#89): worlds/ctr/solo/ctr_solo.py.

Builds a client-shaped folder the way the release does (trimmed core from this
checkout, packed ctr.apworld, the solo files) and runs the wrapper as a child
process, like the native client does.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.dirname(HERE)
SOLO = os.path.join(WORLD, "solo")
REPO = os.path.dirname(os.path.dirname(WORLD))
GAME = "Crash Team Racing"

sys.path.insert(0, SOLO)
import trim_core  # noqa: E402

_CLIENT: str | None = None


def build_client() -> str:
    """One client folder per test process: <tmp>/client/{ctr.apworld, solo-runtime/}."""
    global _CLIENT
    if _CLIENT:
        return _CLIENT
    root = tempfile.mkdtemp(prefix="ctr-solo-test-")
    client = os.path.join(root, "client")
    runtime = os.path.join(client, "solo-runtime")
    os.makedirs(runtime)
    trim_core.copy(REPO, os.path.join(runtime, "archipelago"))
    for name in ("ctr_solo.py", "options-overlay.json"):
        shutil.copyfile(os.path.join(SOLO, name), os.path.join(runtime, name))
    shutil.copytree(os.path.join(SOLO, "presets"), os.path.join(runtime, "presets"))
    subprocess.run([sys.executable, os.path.join(WORLD, "tools", "build_apworld.py"),
                    os.path.join(client, "ctr.apworld")], check=True, stdout=subprocess.DEVNULL)
    _CLIENT = client
    return client


def env(home: str | None = None) -> dict:
    result = dict(os.environ)
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["CTR_SOLO_TEST_PORTS"] = "1"  # parallel test runs use their own port ranges
    result.pop("PYTHONPATH", None)
    if home:
        result["HOME"] = home
        result["XDG_DATA_HOME"] = os.path.join(home, ".local", "share")
        result["XDG_CACHE_HOME"] = os.path.join(home, ".cache")
    return result


def run(client: str, *args, solo: str | None = None, home: str | None = None, prelude: str | None = None,
        timeout: int = 180) -> tuple[list[dict], int]:
    script = os.path.join(client, "solo-runtime", "ctr_solo.py")
    base = ["--solo", solo] if solo else []
    if prelude:
        cmd = [sys.executable, "-I", "-c",
               prelude + "\nimport runpy, sys\nsys.argv = sys.argv[1:]\n"
               "sys.path.insert(0, __import__('os').path.dirname(sys.argv[0]))\n"
               "runpy.run_path(sys.argv[0], run_name='__main__')", script, *base, *args]
    else:
        cmd = [sys.executable, "-I", script, *base, *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env(home))
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return events, proc.returncode


def last(events: list[dict]) -> dict:
    assert events, "no protocol output"
    return events[-1]


def free_ports(count: int) -> int:
    """First of `count` consecutive ports that nothing listens on right now."""
    import random
    # Each xdist worker draws from its own band, so two workers never race
    # for the same range between this probe and the child's bind.
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    band = int(worker[2:]) if worker[2:].isdigit() else 0
    low = 40000 + (band % 10) * 2000
    for _ in range(200):
        base = random.randint(low, low + 1990)
        socks = []
        try:
            for port in range(base, base + count):
                sock = socket.socket()
                socks.append(sock)
                sock.bind(("127.0.0.1", port))
            return base
        except OSError:
            continue
        finally:
            for sock in socks:
                sock.close()
    raise RuntimeError("no free port range")


def write_yaml(folder: str, name: str, text: str) -> str:
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class SoloTestCase(unittest.TestCase):
    def setUp(self):
        self.client = build_client()
        self.work = tempfile.mkdtemp(prefix="solo-case-")
        self.solo = os.path.join(self.work, "solo")
        self.home = os.path.join(self.work, "home")
        os.makedirs(self.home)

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def call(self, *args, **kwargs):
        return run(self.client, *args, solo=self.solo, home=self.home, **kwargs)

    def preset(self, name: str) -> str:
        return os.path.join(self.client, "solo-runtime", "presets", name)


class TestTrimCore(unittest.TestCase):
    def test_core_has_no_other_worlds(self):
        files = trim_core.plan(REPO)
        worlds = {f.split(os.sep)[1] for f in files if f.startswith("worlds" + os.sep) and f.count(os.sep) > 1}
        self.assertEqual(worlds, {"generic"})
        for needed in ("Generate.py", "Main.py", "MultiServer.py", "Utils.py", "LICENSE",
                       os.path.join("worlds", "__init__.py")):
            self.assertIn(needed, files)
        self.assertNotIn("kvui.py", files)


class TestDescribe(SoloTestCase):
    def test_describe_matches_world_options_and_overlay(self):
        from worlds.ctr.Options import ctrAPOptions
        events, code = self.call("describe")
        self.assertEqual(code, 0, events)
        result = last(events)
        self.assertEqual(result["event"], "result")
        names = [o["name"] for o in result["options"]]
        self.assertEqual(set(names), set(ctrAPOptions.type_hints))
        overlay = result["overlay"]
        overlay_names = [n for g in overlay["groups"] for n in g["options"]]
        self.assertFalse(set(overlay_names) - set(names), "overlay names an option the world does not have")
        self.assertGreaterEqual(len(overlay_names), 12)
        for rule in overlay["rules"]:
            self.assertIn(rule["option"], names)
        self.assertEqual([p["id"] for p in result["presets"]], ["quick", "standard", "full_adventure"])
        deathlink = next(r for r in overlay["rules"] if r["option"] == "death_link")
        self.assertEqual(deathlink["forced"], "off")
        self.assertEqual(set(result["values"]), set(overlay_names))

    def test_describe_reports_preset_values(self):
        events, code = self.call("describe", "--yaml", self.preset("quick.yaml"))
        self.assertEqual(code, 0, events)
        values = last(events)["values"]
        self.assertEqual(values["warppad_unlock_requirements"], "vanilla")
        self.assertEqual(values["two_stage_density"], "off")
        self.assertEqual(values["racer_locked_pads"], 0)
        self.assertIs(values["shuffle_keys"], True)


class TestPresets(SoloTestCase):
    def test_every_preset_generates(self):
        with open(os.path.join(SOLO, "presets", "presets.json"), encoding="utf-8") as handle:
            presets = json.load(handle)["presets"]
        for preset in presets:
            with self.subTest(preset=preset["id"]):
                events, code = self.call("generate", "--yaml", self.preset(preset["file"]), "--name", "Solo",
                                         "--stamp-requires", "--preset", preset["id"])
                self.assertEqual(code, 0, events)
                result = last(events)
                self.assertEqual(result["event"], "result", result)
                phases = [e["phase"] for e in events if e["event"] == "progress"]
                self.assertEqual(phases[0], "Starting runtime")
                self.assertIn("Writing room", phases)
                room = os.path.join(self.solo, "rooms", result["room_id"])
                with open(os.path.join(room, result["room_file"]), "rb") as handle:
                    digest = hashlib.sha256(handle.read()).hexdigest()
                self.assertEqual(digest[:16], result["room_id"])
                self.assertEqual(result["slot"], "Solo")
                self.assertEqual(result["origin"], "generated")
                self.assertGreater(result["locations_total"], 0)
                self.assertTrue(os.path.isfile(os.path.join(room, "spoiler.txt")))
                import yaml
                with open(os.path.join(room, "player.yaml"), encoding="utf-8") as handle:
                    doc = yaml.safe_load(handle)
                self.assertEqual(doc["requires"]["game"][GAME], result["world_version"])
        with open(self.preset("full_adventure.yaml"), encoding="utf-8") as handle:
            self.assertIn("accessibility: full", handle.read())

    def test_a_bundled_preset_is_always_stamped(self):
        events, code = self.call("generate", "--yaml", self.preset("quick.yaml"), "--preset", "quick")
        self.assertEqual(code, 0, events)
        import yaml
        room = os.path.join(self.solo, "rooms", last(events)["room_id"])
        with open(os.path.join(room, "player.yaml"), encoding="utf-8") as handle:
            self.assertIn("requires", yaml.safe_load(handle))

    def test_overrides_and_option_error_names_the_option(self):
        events, code = self.call("validate", "--yaml", self.preset("standard.yaml"),
                                 "--set", "oxide_goal=none", "--set", "bosses_required_goal=0",
                                 "--set", "gems_required_goal=0")
        result = last(events)
        if code == 0:
            self.skipTest("the world accepts this combination now")
        self.assertEqual(result["event"], "error")
        self.assertEqual(result["kind"], "option")

    def test_unknown_option_refused(self):
        events, code = self.call("validate", "--yaml", self.preset("standard.yaml"), "--set", "no_such=1")
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "option")


class TestCustomTracks(SoloTestCase):
    """The custom-track step (decision 32): installed tracks, picked into a preset."""

    def setUp(self):
        super().setUp()
        self.assets = os.path.join(self.work, "assets")
        self.descriptors = os.path.join(self.solo, "tracks")
        os.makedirs(self.descriptors)

    def install(self, key: str, revision: str, title: str, folder: str | None = None, lev_name: str = "a.LEV",
                write_descriptor: bool = True) -> dict:
        """Made-up LEV and VRM bytes in assets/tracks/<folder>/original and a
        descriptor pinning them. Test data only: the bytes are no track."""
        original = os.path.join(self.assets, "tracks", folder or key, "original")
        os.makedirs(original, exist_ok=True)
        lev, vrm = os.urandom(3000), os.urandom(2000)
        for name, data in ((lev_name.replace("a.", f"a-{revision}."), lev), (f"b-{revision}.vrm", vrm)):
            with open(os.path.join(original, name), "wb") as handle:
                handle.write(data)
        descriptor = dict(
            id=f"package/{key}/{revision}", content_id=key,
            uuid="0f0e0d0c-0b0a-4908-8706-%012x" % int(hashlib.sha256(key.encode()).hexdigest()[:12], 16),
            revision=revision, display_name=title, author="Fixture Author", laps=3,
            capabilities=dict(time_trial=True, arcade=True, relic=True, ctr_tokens=False, wumpa=False),
            relic_targets=dict(sapphire=96000, gold=86400, platinum=76800),
            files=[dict(role="lev", sha256=hashlib.sha256(lev).hexdigest(), bytes=len(lev), format="ctr-lev",
                        format_version=1),
                   dict(role="vrm", sha256=hashlib.sha256(vrm).hexdigest(), bytes=len(vrm), format="ctr-vrm",
                        format_version=1)],
            evidence=[])
        if write_descriptor:
            with open(os.path.join(self.descriptors, f"{key}__{revision}.json"), "w", encoding="utf-8") as handle:
                json.dump(descriptor, handle)
        return descriptor

    def tracks(self) -> list:
        events, code = self.call("tracks", "--assets", self.assets)
        self.assertEqual(code, 0, events)
        return last(events)["tracks"]

    def test_lists_only_tracks_whose_files_are_installed(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        self.install("fixture-hill", "1.0", "Fixture Hill")
        # A descriptor without files, and files that do not match their pins.
        broken = self.install("fixture-gone", "1.0", "Fixture Gone")
        shutil.rmtree(os.path.join(self.assets, "tracks", "fixture-gone"))
        changed = self.install("fixture-changed", "1.0", "Fixture Changed")
        with open(os.path.join(self.assets, "tracks", "fixture-changed", "original", "b-1.0.vrm"), "r+b") as handle:
            handle.write(b"x")
        with open(os.path.join(self.descriptors, "junk.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        with open(os.path.join(self.descriptors, "foreign.json"), "w", encoding="utf-8") as handle:
            json.dump({"id": "package/x/1"}, handle)
        tracks = self.tracks()
        self.assertEqual([t["display_name"] for t in tracks], ["Fixture Hill", "Fixture Loop"])
        entry = next(t for t in tracks if t["id"] == loop["id"])
        self.assertEqual(entry["track_id"], "custom/fixture-loop/2.1")
        self.assertEqual(entry["modes"], ["trophy", "relic"])
        self.assertNotIn(broken["id"], [t["id"] for t in tracks])
        self.assertNotIn(changed["id"], [t["id"] for t in tracks])

    def test_bad_descriptor_and_room_files_are_skipped(self):
        self.install("fixture-loop", "2.1", "Fixture Loop")
        with open(os.path.join(self.descriptors, "bytes.json"), "wb") as handle:
            handle.write(b"\xff\xfe{")
        with open(os.path.join(self.descriptors, "deep.json"), "w", encoding="utf-8") as handle:
            handle.write("[" * 10000 + "]" * 10000)
        with open(os.path.join(self.descriptors, "big.json"), "w", encoding="utf-8") as handle:
            handle.write(" " * (64 * 1024 + 1) + "{}")
        rooms = os.path.join(self.solo, "rooms")
        os.makedirs(os.path.join(rooms, "0123456789abcdef"))
        with open(os.path.join(rooms, "0123456789abcdef", "room.json"), "w", encoding="utf-8") as handle:
            json.dump({"custom_tracks": {"not": "a list"}}, handle)
        outside = os.path.join(self.work, "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, "room.json"), "w", encoding="utf-8") as handle:
            json.dump({"custom_tracks": [{"id": "package/x/1"}]}, handle)
        try:
            os.symlink(outside, os.path.join(rooms, "fedcba9876543210"))
        except OSError:
            pass
        self.assertEqual([t["id"] for t in self.tracks()], ["package/fixture-loop/2.1"])

    def yaml_with_plan(self, name: str, **pool_edits) -> str:
        """An imported-style YAML with its own content plan (cups 2, crystals 1)."""
        import yaml
        section = dict(content_pool=dict(preset="mixed", tracks=dict(retail="all", modes=["trophy", "relic"]),
                                         cups=dict(count=2), crystals=dict(count=1), bosses=dict(enabled=True)),
                       pad_layout=dict(placement="shuffle", stages="single", mode_order="fixed",
                                       merge_trophy_ctr=False),
                       death_link="off", accessibility="full")
        section["content_pool"].update(pool_edits)
        return write_yaml(self.work, name, yaml.safe_dump({"name": "Imported", "game": GAME, GAME: section}))

    def room_section(self, events) -> dict:
        import yaml
        with open(os.path.join(self.solo, "rooms", last(events)["room_id"], "player.yaml"),
                  encoding="utf-8") as handle:
            return yaml.safe_load(handle)[GAME]

    def test_a_yaml_that_lists_the_same_track_keeps_one_entry(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        source = self.yaml_with_plan("same.yaml", tracks=dict(retail="all", modes=["trophy", "relic"],
                                                              custom=[loop]),
                                     required_entries=["custom/fixture-loop/2.1"])
        events, code = self.call("generate", "--yaml", source, "--assets", self.assets, "--track", loop["id"],
                                 "--guarantee", loop["id"], "--seed", "3")
        self.assertEqual(code, 0, events)
        pool = self.room_section(events)["content_pool"]
        self.assertEqual(pool["tracks"]["custom"], [loop])
        self.assertEqual(pool["required_entries"], ["custom/fixture-loop/2.1"])

    def test_a_yaml_that_lists_the_track_differently_is_refused(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        stale = json.loads(json.dumps(loop))
        stale["files"][0]["sha256"] = "a1" * 32
        stale.update(id="package/fixture-loop/2.0", revision="2.0")  # an older revision of the same track
        source = self.yaml_with_plan("stale.yaml", tracks=dict(retail="all", modes=["trophy", "relic"],
                                                               custom=[stale]),
                                     required_entries=["custom/fixture-loop/2.0"])
        events, code = self.call("validate", "--yaml", source, "--assets", self.assets, "--track", loop["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "track")
        self.assertIn("already lists Fixture Loop", last(events)["message"])
        self.assertIn("2.0", last(events)["message"])
        # The same revision with other file pins is a conflict too.
        pinned = json.loads(json.dumps(loop))
        pinned["files"][0]["sha256"] = "a1" * 32
        source = self.yaml_with_plan("pinned.yaml", tracks=dict(retail="all", modes=["trophy", "relic"],
                                                                custom=[pinned]))
        events, code = self.call("validate", "--yaml", source, "--assets", self.assets, "--track", loop["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "track")
        for pool in ({"tracks": {"custom": {}}}, [], False):
            with self.subTest(pool=pool):
                import yaml
                broken = write_yaml(self.work, "broken.yaml", yaml.safe_dump(
                    {"name": "Solo", "game": GAME, GAME: {"content_pool": pool}}))
                events, code = self.call("validate", "--yaml", broken, "--assets", self.assets, "--track", loop["id"])
                self.assertNotEqual(code, 0)
                self.assertEqual(last(events)["kind"], "option")
                self.assertEqual(last(events)["option"], "content_pool")

    def test_a_yaml_with_a_content_plan_keeps_its_counts(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        hill = self.install("fixture-hill", "1.0", "Fixture Hill")
        source = self.yaml_with_plan("plan.yaml", required_entries=["retail:3"])
        events, code = self.call("generate", "--yaml", source, "--assets", self.assets, "--track", loop["id"],
                                 "--track", hill["id"], "--guarantee", hill["id"], "--seed", "5")
        self.assertEqual(code, 0, events)
        section = self.room_section(events)
        pool = section["content_pool"]
        self.assertEqual(pool["cups"], {"count": 2})
        self.assertEqual(pool["crystals"], {"count": 1})
        self.assertEqual(pool["tracks"]["modes"], ["trophy", "relic"])
        self.assertEqual(pool["required_entries"], ["retail:3", "custom/fixture-hill/1.0"])
        self.assertEqual([d["id"] for d in pool["tracks"]["custom"]], [loop["id"], hill["id"]])
        self.assertEqual(section["pad_layout"]["stages"], "single")
        self.assertNotIn("item_pool", section)

    def test_a_yaml_without_a_content_plan_gets_the_vanilla_shape_where_it_sets_nothing(self):
        import yaml
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        source = write_yaml(self.work, "plain.yaml", yaml.safe_dump(
            {"name": "Imported", "game": GAME, GAME: dict(oxide_goal="any_percent", death_link="off",
                                                          pad_layout=dict(stages="single"))}))
        events, code = self.call("generate", "--yaml", source, "--assets", self.assets, "--track", loop["id"],
                                 "--guarantee", loop["id"], "--seed", "4")
        self.assertEqual(code, 0, events)
        section = self.room_section(events)
        with open(os.path.join(SOLO, "options-overlay.json"), encoding="utf-8") as handle:
            profile = json.load(handle)["custom_tracks"]["profile"]
        self.assertEqual(section["oxide_goal"], "any_percent")
        self.assertEqual(section["pad_layout"]["stages"], "single")  # the YAML's own value
        self.assertEqual(section["pad_layout"]["mode_order"], "fixed")  # filled in
        self.assertEqual(section["content_pool"]["cups"], {"count": 5})
        self.assertEqual(section["content_pool"]["crystals"]["count"], 4)
        self.assertEqual(section["item_pool"], profile["item_pool"])
        self.assertEqual(section["content_pool"]["required_entries"], ["custom/fixture-loop/2.1"])

    def test_a_yaml_that_does_not_fit_is_refused_with_the_world_message(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        # 30 required entries cannot fit the 27 normal pads.
        source = self.yaml_with_plan("toomany.yaml", required_entries=[f"retail:{i}" for i in range(18)] +
                                     [f"arena:{i}" for i in range(18, 25)] + [f"retail:{i}" for i in range(2)])
        events, code = self.call("validate", "--yaml", source, "--assets", self.assets, "--track", loop["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["event"], "error")
        self.assertNotEqual(last(events)["message"], "")

    def test_files_may_sit_in_the_revision_folder(self):
        # The client keeps Baby T Park 1.0.2 in tracks/baby-t-park-1.0.2.
        self.install("fixture-loop", "2.1", "Fixture Loop", folder="fixture-loop-2.1", lev_name="track.lev")
        self.assertEqual([t["id"] for t in self.tracks()], ["package/fixture-loop/2.1"])

    def test_picked_tracks_go_into_the_content_plan(self):
        import yaml
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        hill = self.install("fixture-hill", "1.0", "Fixture Hill")
        events, code = self.call("generate", "--yaml", self.preset("standard.yaml"), "--name", "Solo",
                                 "--preset", "standard", "--assets", self.assets, "--track", loop["id"],
                                 "--track", hill["id"], "--guarantee", hill["id"], "--seed", "7")
        self.assertEqual(code, 0, events)
        result = last(events)
        self.assertEqual([d["id"] for d in result["custom_tracks"]], [loop["id"], hill["id"]])
        with open(os.path.join(self.solo, "rooms", result["room_id"], "player.yaml"), encoding="utf-8") as handle:
            section = yaml.safe_load(handle)[GAME]
        pool = section["content_pool"]
        self.assertEqual(pool["tracks"]["custom"], [loop, hill])
        self.assertEqual(pool["required_entries"], ["custom/fixture-hill/1.0"])
        with open(os.path.join(SOLO, "options-overlay.json"), encoding="utf-8") as handle:
            profile = json.load(handle)["custom_tracks"]["profile"]
        self.assertEqual(section["pad_layout"], profile["pad_layout"])
        self.assertEqual(section["item_pool"], profile["item_pool"])
        self.assertEqual(pool["cups"], {"count": 5})
        self.assertEqual(pool["crystals"], {"count": 4, "pool": [21, 19, 23, 18]})
        self.assertEqual(pool["bosses"], profile["content_pool"]["bosses"])
        self.assertEqual(section["death_link"], "off")
        # The room is a content-plan room: its tracks are listed afterwards
        # even without the descriptor files.
        shutil.rmtree(self.descriptors)
        self.assertEqual(sorted(t["source"] for t in self.tracks()), ["room", "room"])

    def test_every_start_takes_one_and_two_tracks_and_a_guaranteed_pad(self):
        """Probe matrix of round 2 decision 5: the three presets and two
        imported YAMLs (with and without a content plan), seeds 1 and 2."""
        import yaml
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        hill = self.install("fixture-hill", "1.0", "Fixture Hill")
        plain = write_yaml(self.work, "plain.yaml", yaml.safe_dump(
            {"name": "Imported", "game": GAME, GAME: dict(oxide_goal="any_percent", death_link="off",
                                                          itemsanity=True, accessibility="full")}))
        planned = self.yaml_with_plan("planned.yaml")
        starts = [self.preset(n) for n in ("quick.yaml", "standard.yaml", "full_adventure.yaml")] + [plain, planned]
        picks = (([loop], []), ([loop], [loop]), ([loop, hill], [hill]), ([loop, hill], [loop, hill]))
        for source in starts:
            for picked, guaranteed in picks:
                for seed in ("1", "2"):
                    with self.subTest(start=os.path.basename(source), tracks=len(picked),
                                      guaranteed=len(guaranteed), seed=seed):
                        args = ["generate", "--yaml", source, "--assets", self.assets, "--seed", seed]
                        for d in picked:
                            args += ["--track", d["id"]]
                        for d in guaranteed:
                            args += ["--guarantee", d["id"]]
                        events, code = self.call(*args)
                        self.assertEqual(code, 0, events)

    def test_refusals(self):
        loop = self.install("fixture-loop", "2.1", "Fixture Loop")
        older = self.install("fixture-loop", "2.0", "Fixture Loop")
        events, code = self.call("validate", "--yaml", self.preset("quick.yaml"), "--assets", self.assets,
                                 "--track", loop["id"], "--track", older["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "track")
        self.assertIn("one version", last(events)["message"])
        events, code = self.call("validate", "--yaml", self.preset("quick.yaml"), "--assets", self.assets,
                                 "--track", "package/not-here/1.0")
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "track")
        events, code = self.call("validate", "--yaml", self.preset("quick.yaml"), "--assets", self.assets,
                                 "--guarantee", loop["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "track")
        legacy = write_yaml(self.work, "legacy.yaml",
                            f"name: Solo\ngame: {GAME}\n{GAME}:\n  cortex_vortex_track: true\n")
        events, code = self.call("validate", "--yaml", legacy, "--assets", self.assets, "--track", loop["id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["option"], "cortex_vortex_track")

    def test_no_track_leaves_the_preset_alone(self):
        import yaml
        events, code = self.call("generate", "--yaml", self.preset("quick.yaml"), "--name", "Solo",
                                 "--assets", self.assets)
        self.assertEqual(code, 0, events)
        with open(os.path.join(self.solo, "rooms", last(events)["room_id"], "player.yaml"),
                  encoding="utf-8") as handle:
            self.assertNotIn("content_pool", yaml.safe_load(handle)[GAME])


class TestRefusals(SoloTestCase):
    def check(self, text: str, kind: str, **expect):
        path = write_yaml(self.work, "in.yaml", text)
        events, code = self.call("validate", "--yaml", path)
        self.assertNotEqual(code, 0, events)
        result = last(events)
        self.assertEqual(result["event"], "error")
        self.assertEqual(result["kind"], kind, result)
        for key, value in expect.items():
            self.assertEqual(result.get(key), value, result)
        return result

    def test_other_game(self):
        self.check("name: A\ngame: A Link to the Past\nA Link to the Past: {}\n", "game")

    def test_two_players(self):
        self.check("name: A\ngame: Crash Team Racing\n---\nname: B\ngame: Crash Team Racing\n", "players")

    def test_an_empty_extra_document(self):
        self.check("name: A\ngame: Crash Team Racing\n---\n", "players")

    def test_weighted_game_with_zero_weight_for_another(self):
        path = write_yaml(self.work, "in.yaml",
                          "name: A\ngame:\n  Crash Team Racing: 1\n  Other Game: '0'\nCrash Team Racing: {}\n")
        events, code = self.call("validate", "--yaml", path)
        self.assertEqual(code, 0, events)

    def test_broken_syntax_has_a_line(self):
        result = self.check("name: A\ngame: Crash Team Racing\nCrash Team Racing:\n  oxide_goal: [\n", "yaml")
        self.assertIsNotNone(result.get("line"))

    def test_requires_mismatch(self):
        result = self.check("name: A\ngame: Crash Team Racing\nrequires:\n  version: 0.6.7\n  game:\n"
                            "    Crash Team Racing: 99.0.0\nCrash Team Racing: {}\n", "option")
        self.assertIn("99.0.0", result["message"])

    def test_apworld_hash_mismatch(self):
        events, code = self.call("--apworld-sha256", "0" * 64, "describe")
        self.assertNotEqual(code, 0)
        self.assertEqual(last(events)["kind"], "runtime")

    def test_import_room_rejects_non_room(self):
        path = write_yaml(self.work, "AP_fake.zip", "not a zip")
        events, code = self.call("import-room", path)
        self.assertNotEqual(code, 0)
        self.assertIn(last(events)["kind"], ("room", "internal"))


class TestIsolation(SoloTestCase):
    def snapshot(self, folder: str) -> dict:
        result = {}
        for root, _, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                result[os.path.relpath(full, folder)] = os.path.getmtime(full)
        return result

    def test_only_generic_and_ctr_load_and_nothing_outside_solo_is_written(self):
        # A global Archipelago home with another world and a stray world in ap-home.
        global_worlds = os.path.join(self.home, ".local", "share", "Archipelago", "worlds")
        os.makedirs(global_worlds)
        shutil.copyfile(os.path.join(self.client, "ctr.apworld"), os.path.join(global_worlds, "ctr.apworld"))
        with open(os.path.join(global_worlds, "broken.apworld"), "wb") as handle:
            handle.write(b"PK\x05\x06" + b"\0" * 18)
        stray = os.path.join(self.solo, "ap-home", "worlds")
        os.makedirs(stray)
        with open(os.path.join(stray, "other.apworld"), "wb") as handle:
            handle.write(b"junk")
        before_client = self.snapshot(self.client)
        before_home = self.snapshot(self.home)
        guard = ("import socket\n"
                 "_c = socket.socket.connect\n"
                 "def _guard(self, address):\n"
                 "    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):\n"
                 "        raise AssertionError('outbound connection to %r' % (address,))\n"
                 "    return _c(self, address)\n"
                 "socket.socket.connect = _guard\n"
                 "socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError('outbound'))\n")
        events, code = self.call("generate", "--yaml", self.preset("standard.yaml"), prelude=guard)
        self.assertEqual(code, 0, events)
        self.assertEqual(os.listdir(stray), ["ctr.apworld"])
        self.assertEqual(self.snapshot(self.client), before_client)
        self.assertEqual(self.snapshot(self.home), before_home)


class TestServe(SoloTestCase):
    def generate_room(self) -> dict:
        events, code = self.call("generate", "--yaml", self.preset("standard.yaml"), "--name", "Solo")
        self.assertEqual(code, 0, events)
        return last(events)

    def start(self, room_id: str, first: int, last_port: int) -> tuple[subprocess.Popen, dict]:
        script = os.path.join(self.client, "solo-runtime", "ctr_solo.py")
        proc = subprocess.Popen([sys.executable, "-I", script, "--solo", self.solo, "serve", "--room", room_id,
                                 "--game-pid", str(os.getpid()), "--port-first", str(first),
                                 "--port-last", str(last_port)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, env=env(self.home))
        line = []
        reader = threading.Thread(target=lambda: line.append(proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(60)
        if not line:
            proc.kill()
            self.fail("the server did not answer within 60 seconds")
        return proc, json.loads(line[0])

    def try_connect(self, ready: dict, password: str) -> str:
        """The first reply command to a Connect with this password."""
        import asyncio
        import websockets

        async def go():
            async with websockets.connect(f"ws://127.0.0.1:{ready['port']}") as ws:
                json.loads(await ws.recv())
                await ws.send(json.dumps([{"cmd": "Connect", "game": GAME, "name": ready["slot"],
                                           "password": password, "uuid": "test",
                                           "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                                           "items_handling": 7, "tags": [], "slot_data": False}]))
                return json.loads(await ws.recv())[0]["cmd"]

        return asyncio.run(go())

    def check_location(self, ready: dict) -> int:
        import asyncio
        import websockets

        async def go():
            async with websockets.connect(f"ws://127.0.0.1:{ready['port']}") as ws:
                info = json.loads(await ws.recv())[0]
                self.assertEqual(info["seed_name"], ready["seed_name"])
                await ws.send(json.dumps([{"cmd": "Connect", "game": GAME, "name": ready["slot"],
                                           "password": ready["password"], "uuid": "test",
                                           "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                                           "items_handling": 7, "tags": [], "slot_data": False}]))
                connected = [m for m in json.loads(await ws.recv()) if m["cmd"] == "Connected"][0]
                location = connected["missing_locations"][0]
                await ws.send(json.dumps([{"cmd": "LocationChecks", "locations": [location]}]))
                for _ in range(10):
                    msgs = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    if any(m["cmd"] == "RoomUpdate" and location in m.get("checked_locations", []) for m in msgs):
                        return location
                self.fail("check was not confirmed")

        return asyncio.run(go())

    def read_save(self, room: dict) -> dict:
        from Utils import restricted_loads
        folder = os.path.join(self.solo, "rooms", room["room_id"])
        path = os.path.join(folder, os.path.splitext(room["room_file"])[0] + ".apsave")
        with open(path, "rb") as handle:
            return restricted_loads(zlib.decompress(handle.read()))

    def test_check_survives_a_killed_server_and_occupied_port_is_skipped(self):
        room = self.generate_room()
        base = free_ports(3)
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", base))
        blocker.listen(1)
        try:
            proc, ready = self.start(room["room_id"], base, base + 2)
            try:
                self.assertEqual(ready["event"], "ready", ready)
                self.assertEqual(ready["port"], base + 1)
                lock = os.path.join(self.solo, "rooms", room["room_id"], "session.lock")
                self.assertTrue(os.path.isfile(lock))
                location = self.check_location(ready)
                # The check must already be on disk: kill without a chance to save.
                proc.kill()
                proc.wait(10)
            finally:
                if proc.poll() is None:
                    proc.kill()
        finally:
            blocker.close()
        save = self.read_save(room)
        self.assertIn(location, save["location_checks"][(0, 1)])
        # A stale lock (dead PID) does not block the next start; a live one does.
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            self.assertEqual(ready["event"], "ready", ready)
            events, code = self.call("serve", "--room", room["room_id"])
            self.assertEqual(last(events)["kind"], "running")
            listing = last(self.call("list")[0])
            self.assertEqual(listing["rooms"][0]["checks_done"], 1)
            self.assertTrue(listing["rooms"][0]["running"])
            proc.stdin.write("/save\n/exit\n")
            proc.stdin.flush()
            tail = [json.loads(line) for line in proc.stdout.read().splitlines() if line.strip()]
            self.assertEqual(tail[-1], {"event": "stopped", "reason": "exit"})
            self.assertEqual(proc.wait(10), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertTrue(os.path.isfile(os.path.join(self.solo, "rooms", room["room_id"],
                                                    os.path.splitext(room["room_file"])[0] + ".apsave.bak")))
        self.assertFalse(os.path.exists(os.path.join(self.solo, "rooms", room["room_id"], "session.lock")))

    def test_password_is_required_even_after_a_save(self):
        room = self.generate_room()
        base = free_ports(3)
        for _ in range(2):  # the second start loads the save written by the first
            proc, ready = self.start(room["room_id"], base, base + 2)
            try:
                self.assertEqual(ready["event"], "ready", ready)
                self.assertEqual(self.try_connect(ready, ""), "ConnectionRefused")
                self.assertEqual(self.try_connect(ready, "wrong"), "ConnectionRefused")
                self.assertEqual(self.try_connect(ready, ready["password"]), "Connected")
                proc.stdin.write("/exit\n")
                proc.stdin.flush()
                self.assertEqual(proc.wait(15), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()

    def test_damaged_save_is_restored_from_the_backup_or_refused(self):
        room = self.generate_room()
        base = free_ports(3)
        folder = os.path.join(self.solo, "rooms", room["room_id"])
        save = os.path.join(folder, os.path.splitext(room["room_file"])[0] + ".apsave")
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            self.check_location(ready)
            proc.stdin.write("/exit\n")
            proc.stdin.flush()
            proc.wait(15)
        finally:
            if proc.poll() is None:
                proc.kill()
        # Second start makes the .bak from the good save; then damage the save.
        proc, ready = self.start(room["room_id"], base, base + 2)
        proc.stdin.write("/exit\n")
        proc.stdin.flush()
        proc.wait(15)
        with open(save, "wb") as handle:
            handle.write(b"not a save")
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            self.assertEqual(ready["event"], "ready", ready)
            proc.stdin.write("/exit\n")
            proc.stdin.flush()
            proc.wait(15)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(len(self.read_save(room)["location_checks"][(0, 1)]), 1)
        self.assertTrue(any(n.startswith(os.path.basename(save) + ".damaged-") for n in os.listdir(folder)))
        # Both damaged: refused, nothing overwritten.
        for path in (save, save + ".bak"):
            with open(path, "wb") as handle:
                handle.write(b"broken")
        events, code = self.call("serve", "--room", room["room_id"], "--port-first", str(base),
                                 "--port-last", str(base + 2))
        self.assertEqual(last(events)["kind"], "save")

    def test_one_server_per_room_and_production_port_range(self):
        room = self.generate_room()
        base = free_ports(3)
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            self.assertEqual(ready["event"], "ready", ready)
            events, code = self.call("serve", "--room", room["room_id"], "--port-first", str(base),
                                     "--port-last", str(base + 2))
            self.assertEqual(last(events)["kind"], "running")
        finally:
            proc.kill()
            proc.wait(10)
        script = os.path.join(self.client, "solo-runtime", "ctr_solo.py")
        no_hook = env(self.home)
        no_hook.pop("CTR_SOLO_TEST_PORTS")
        out = subprocess.run([sys.executable, "-I", script, "--solo", self.solo, "serve", "--room", room["room_id"],
                              "--port-first", "39000", "--port-last", "39000"],
                             capture_output=True, text=True, timeout=120, env=no_hook)
        self.assertEqual(json.loads(out.stdout.splitlines()[-1])["kind"], "ports")

    def test_simultaneous_starts_serve_once(self):
        room = self.generate_room()
        base = free_ports(6)
        script = os.path.join(self.client, "solo-runtime", "ctr_solo.py")
        procs = [subprocess.Popen([sys.executable, "-I", script, "--solo", self.solo, "serve", "--room",
                                   room["room_id"], "--port-first", str(base), "--port-last", str(base + 5)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, env=env(self.home)) for _ in range(4)]
        try:
            firsts = [json.loads(p.stdout.readline()) for p in procs]
            kinds = sorted(e.get("kind", e["event"]) for e in firsts)
            self.assertEqual(kinds, ["ready", "running", "running", "running"], firsts)
        finally:
            for p in procs:
                p.kill()
                p.wait(10)

    def test_a_failed_save_is_retried(self):
        if os.name == "nt" or os.geteuid() == 0:
            self.skipTest("needs a POSIX folder the test can make read-only")
        room = self.generate_room()
        base = free_ports(3)
        folder = os.path.join(self.solo, "rooms", room["room_id"])
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            os.chmod(folder, 0o555)  # the check's save fails
            location = self.check_location(ready)
            os.chmod(folder, 0o755)  # storage recovers; the saver retries
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    if location in self.read_save(room)["location_checks"].get((0, 1), ()):
                        break
                except OSError:
                    pass
                time.sleep(0.5)
            proc.kill()  # no exit save: the retry alone must have written it
            proc.wait(10)
        finally:
            os.chmod(folder, 0o755)
            if proc.poll() is None:
                proc.kill()
        self.assertIn(location, self.read_save(room)["location_checks"][(0, 1)])

    def test_room_json_cannot_point_outside_the_room(self):
        room = self.generate_room()
        meta_path = os.path.join(self.solo, "rooms", room["room_id"], "room.json")
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        meta["room_file"] = "../../" + meta["room_file"]
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle)
        base = free_ports(3)
        events, code = self.call("serve", "--room", room["room_id"], "--port-first", str(base),
                                 "--port-last", str(base + 2))
        self.assertEqual(last(events)["kind"], "room")

    def test_closed_stdin_stops_the_server(self):
        room = self.generate_room()
        base = free_ports(3)
        proc, ready = self.start(room["room_id"], base, base + 2)
        try:
            self.assertEqual(ready["event"], "ready", ready)
            proc.stdin.close()
            self.assertEqual(proc.wait(15), 0)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_import_room_and_duplicate(self):
        room = self.generate_room()
        source = os.path.join(self.solo, "rooms", room["room_id"], room["room_file"])
        copy = os.path.join(self.work, room["room_file"])
        shutil.copyfile(source, copy)
        other = os.path.join(self.work, "solo2")
        events, code = run(self.client, "import-room", copy, solo=other, home=self.home)
        self.assertEqual(code, 0, events)
        self.assertEqual(last(events)["origin"], "imported")
        self.assertEqual(last(events)["room_id"], room["room_id"])
        events, code = run(self.client, "import-room", copy, solo=other, home=self.home)
        self.assertEqual(last(events)["kind"], "exists")


class TestLinks(SoloTestCase):
    def test_a_linked_solo_folder_is_refused(self):
        outside = os.path.join(self.work, "outside-solo")
        os.makedirs(outside)
        os.symlink(outside, self.solo)
        events, code = self.call("describe")
        self.assertEqual(last(events)["kind"], "runtime")
        self.assertEqual(os.listdir(outside), [])

    def test_a_linked_ap_home_gets_nothing_created(self):
        outside = os.path.join(self.work, "outside-home")
        os.makedirs(outside)
        os.makedirs(self.solo)
        os.symlink(outside, os.path.join(self.solo, "ap-home"))
        events, code = self.call("describe")
        self.assertEqual(last(events)["kind"], "runtime")
        self.assertEqual(os.listdir(outside), [])

    def test_a_linked_worlds_folder_is_refused(self):
        outside = os.path.join(self.work, "global-worlds")
        os.makedirs(outside)
        keep = os.path.join(outside, "other.apworld")
        with open(keep, "wb") as handle:
            handle.write(b"someone else's world")
        os.makedirs(os.path.join(self.solo, "ap-home"))
        os.symlink(outside, os.path.join(self.solo, "ap-home", "worlds"))
        events, code = self.call("describe")
        self.assertEqual(last(events)["kind"], "runtime")
        self.assertTrue(os.path.isfile(keep))


class TestTmp(SoloTestCase):
    def test_a_new_job_clears_a_cancelled_generation(self):
        stale = os.path.join(self.solo, "tmp", "generate-stale")
        fresh = os.path.join(self.solo, "tmp", "generate-running")
        os.makedirs(stale)
        os.makedirs(fresh)
        with open(os.path.join(stale, "AP_x.zip"), "wb") as handle:
            handle.write(b"half")
        old = time.time() - 3600
        os.utime(stale, (old, old))
        events, code = self.call("validate", "--yaml", self.preset("standard.yaml"))
        self.assertEqual(code, 0, events)
        # Abandoned work goes; work young enough to belong to a live job stays.
        self.assertEqual(os.listdir(os.path.join(self.solo, "tmp")), ["generate-running"])
        self.assertEqual(os.listdir(os.path.join(self.solo, "rooms")), [])


class TestImportYaml(SoloTestCase):
    def test_import_and_inbox_listing(self):
        os.makedirs(os.path.join(self.solo, "inbox"))
        shutil.copyfile(self.preset("quick.yaml"), os.path.join(self.solo, "inbox", "mine.yaml"))
        write_yaml(os.path.join(self.solo, "inbox"), "bad.yaml", "name: A\ngame: Other\n")
        listing = last(self.call("list")[0])
        inbox = {e["file"]: e for e in listing["inbox"]}
        self.assertEqual(inbox["mine.yaml"]["name"], "Player")
        self.assertIn("error", inbox["bad.yaml"])
        events, code = self.call("import-yaml", os.path.join(self.solo, "inbox", "mine.yaml"))
        self.assertEqual(code, 0, events)
        self.assertEqual(last(events)["file"], "mine.yaml")
        events, code = self.call("import-yaml", os.path.join(self.solo, "inbox", "mine.yaml"))
        self.assertTrue(last(events)["duplicate"])


if __name__ == "__main__":
    unittest.main()
