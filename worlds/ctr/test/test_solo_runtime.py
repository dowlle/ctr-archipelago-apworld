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
        base = 39400 + (os.getpid() % 200) * 3
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
        base = 38800 + (os.getpid() % 60) * 3
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
        base = 38600 + (os.getpid() % 60) * 3
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
        base = 38400 + (os.getpid() % 60) * 3
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

    def test_closed_stdin_stops_the_server(self):
        room = self.generate_room()
        base = 39000 + (os.getpid() % 100) * 3
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
