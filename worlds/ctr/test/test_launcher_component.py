"""Issue #334 slice 5: the Archipelago Launcher component behind the room
page's "Connect via Game Client" link. See worlds/ctr/launcher_component.py."""
import ast
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from worlds.ctr import launcher_component as lc

GAME = "Crash Team Racing"
ROOM = "Xy3kQ9aZT_eW1b-Lr0pNqA"  # WebHost suuid shape: 22 urlsafe-base64 chars
# What a browser hands the Launcher for macros.html's link: spaces encoded.
WEBHOST_LINK = f"archipelago://Racer%20One:None@archipelago.gg:38281?game=Crash%20Team%20Racing&room={ROOM}"
EXPECTED = f"ctr-ap://connect?host=archipelago.gg&port=38281&slot=Racer%20One&room={ROOM}"

WORLD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AP_ROOT = os.path.dirname(os.path.dirname(WORLD_DIR))


def link(slot="Racer%20One", password="None", hostinfo="archipelago.gg:38281",
         query=f"game=Crash%20Team%20Racing&room={ROOM}"):
    userinfo = slot if password is None else f"{slot}:{password}"
    return f"archipelago://{userinfo}@{hostinfo}?{query}"


class Recorder:
    """Stands in for webbrowser.open and the message box."""

    def __init__(self, result=True):
        self.result = result
        self.opened = []
        self.shown = []

    def open_url(self, url):
        self.opened.append(url)
        return self.result

    def show(self, title, text, error):
        self.shown.append((title, text, error))


class TestRegistration(unittest.TestCase):
    def test_exactly_one_component_with_the_exact_identity(self):
        from worlds.LauncherComponents import Type, components
        from worlds.ctr import ctrAPWorld
        mine = [c for c in components if c.game_name == GAME]
        self.assertEqual(len(mine), 1)
        component = mine[0]
        self.assertEqual(ctrAPWorld.game, GAME)
        self.assertEqual(component.display_name, "Crash Team Racing Client")
        self.assertEqual(component.game_name, "Crash Team Racing")
        self.assertIs(component.type, Type.CLIENT)
        self.assertIs(component.supports_uri, True)
        self.assertIs(component.func, lc.launch_client)
        self.assertIsNone(component.script_name)
        self.assertIsNone(component.file_identifier)
        self.assertFalse(component.cli)

    def test_register_is_idempotent(self):
        from worlds.LauncherComponents import components
        lc.register()
        lc.register()
        self.assertEqual(len([c for c in components if c.game_name == GAME]), 1)

    def test_launcher_offers_it_for_the_room_link_and_passes_the_uri_untouched(self):
        import Launcher
        offered, text_client = Launcher.handle_uri(WEBHOST_LINK)
        self.assertEqual([c.display_name for c in offered], ["Crash Team Racing Client"])
        self.assertIsNotNone(text_client)
        with mock.patch("webbrowser.open", return_value=True) as opened:
            Launcher.run_component(offered[0], WEBHOST_LINK)
        opened.assert_called_once_with(EXPECTED)


class TestConversion(unittest.TestCase):
    def test_realistic_webhost_link(self):
        self.assertEqual(lc.convert_room_link(WEBHOST_LINK), EXPECTED)

    def test_raw_spaces_as_macros_html_writes_them(self):
        raw = f"archipelago://Racer One:None@archipelago.gg:38281?game=Crash Team Racing&room={ROOM}"
        self.assertEqual(lc.convert_room_link(raw), EXPECTED)

    def test_plus_in_game_reads_as_space_like_the_launcher(self):
        self.assertEqual(lc.convert_room_link(link(query=f"game=Crash+Team+Racing&room={ROOM}")), EXPECTED)

    def test_trailing_slash_and_query_order(self):
        url = f"archipelago://Racer%20One:None@archipelago.gg:38281/?room={ROOM}&game=Crash%20Team%20Racing"
        self.assertEqual(lc.convert_room_link(url), EXPECTED)

    def test_unrelated_query_keys_are_ignored_not_forwarded(self):
        out = lc.convert_room_link(link(query=f"game=Crash%20Team%20Racing&room={ROOM}&extra=1"))
        self.assertEqual(out, EXPECTED)

    def test_hosts(self):
        cases = {
            "localhost:38281": "host=localhost&port=38281",
            "127.0.0.1:38281": "host=127.0.0.1&port=38281",
            "[::1]:38281": "host=%5B%3A%3A1%5D&port=38281",
            "Archipelago.GG:1": "host=archipelago.gg&port=1",
            "my_server-1.example.net:65535": "host=my_server-1.example.net&port=65535",
        }
        for hostinfo, fragment in cases.items():
            with self.subTest(hostinfo=hostinfo):
                self.assertIn(f"?{fragment}&", lc.convert_room_link(link(hostinfo=hostinfo)))

    def test_slot_characters_are_percent_encoded(self):
        out = lc.convert_room_link(link(slot="R%C3%A4cer%26%3D%2B%40%3F"))
        self.assertIn("&slot=R%C3%A4cer%26%3D%2B%40%3F&", out)

    def test_bounds_accepted_at_the_limit(self):
        host = "a" * 116
        slot = "é" * 31 + "x"  # 63 bytes
        room = "r" * 64
        out = lc.convert_room_link(link(slot=slot, hostinfo=f"{host}:38281",
                                        query=f"game=Crash%20Team%20Racing&room={room}"))
        self.assertIn(f"host={host}&", out)
        self.assertTrue(out.endswith(f"&room={room}"))


class TestPassword(unittest.TestCase):
    def test_sentinel_and_any_password_are_dropped(self):
        for password in ("None", "", None, "hunter2", "p%40ss:word"):
            with self.subTest(password=password):
                out = lc.convert_room_link(link(password=password))
                self.assertEqual(out, EXPECTED)
                self.assertNotIn("password", out)
                self.assertNotIn("None", out)
                self.assertNotIn("hunter2", out)

    def test_malformed_password_field_is_not_even_read(self):
        # The field is dropped undecoded, so nothing in it can fail or leak.
        self.assertEqual(lc.convert_room_link(link(password="%zz%00")), EXPECTED)


class TestRejections(unittest.TestCase):
    def assertRejected(self, url, reason=None):
        with self.assertRaises(lc.RoomLinkError) as caught:
            lc.convert_room_link(url)
        if reason is not None:
            self.assertEqual(caught.exception.reason, reason)
        return caught.exception

    def test_game_parameter(self):
        self.assertRejected(link(query=f"room={ROOM}"), "room link is not for Crash Team Racing")
        self.assertRejected(link(query=f"game=A%20Link%20to%20the%20Past&room={ROOM}"))
        self.assertRejected(link(query=f"game=crash%20team%20racing&room={ROOM}"))
        self.assertRejected(link(query=f"game=Crash%20Team%20Racing%20&room={ROOM}"))
        self.assertRejected(link(query=f"game=&room={ROOM}"))

    def test_room_parameter(self):
        self.assertRejected(link(query="game=Crash%20Team%20Racing"), "missing room id")
        self.assertRejected(link(query="game=Crash%20Team%20Racing&room="), "missing room id")
        self.assertRejected(link(query=f"game=Crash%20Team%20Racing&room={'r' * 65}"), "room id too long")
        for bad in ("a%2Fb", "a%5Cb", "a%40b"):
            with self.subTest(room=bad):
                self.assertRejected(link(query=f"game=Crash%20Team%20Racing&room={bad}"), "invalid room id")

    def test_duplicate_keys(self):
        for query in (f"game=Crash%20Team%20Racing&game=Crash%20Team%20Racing&room={ROOM}",
                      f"game=Crash%20Team%20Racing&room={ROOM}&room={ROOM}",
                      f"game=Crash%20Team%20Racing&room={ROOM}&x=1&x=2",
                      f"game=Crash%20Team%20Racing&room={ROOM}&ro%6Fm={ROOM}"):
            with self.subTest(query=query):
                self.assertRejected(link(query=query), "duplicate query key")

    def test_malformed_query(self):
        for query in ("", f"game=Crash%20Team%20Racing&&room={ROOM}", f"game=Crash%20Team%20Racing&room={ROOM}&",
                      f"game=Crash%20Team%20Racing&room", f"=x&game=Crash%20Team%20Racing&room={ROOM}"):
            with self.subTest(query=query):
                self.assertRejected(link(query=query))
        self.assertRejected(f"archipelago://Racer:None@archipelago.gg:38281", "missing query")

    def test_malformed_escapes(self):
        for url in (link(slot="Racer%2"), link(slot="Racer%zz"), link(slot="%"),
                    link(query=f"game=Crash%2 Team%20Racing&room={ROOM}"),
                    link(query=f"game=Crash%20Team%20Racing&room=abc%G1")):
            with self.subTest(url=url):
                self.assertRejected(url, "malformed percent escape")

    def test_invalid_utf8(self):
        for url in (link(slot="Racer%FF"), link(slot="%C0%AF"), link(slot="%ED%A0%80"),
                    link(query="game=Crash%20Team%20Racing&room=%E2%82")):
            with self.subTest(url=url):
                self.assertRejected(url, "invalid UTF-8")

    def test_control_characters(self):
        for url in (link(slot="Racer%00"), link(slot="Racer%0A"), link(slot="Racer%7F"), link(slot="Racer%C2%85"),
                    link(query="game=Crash%20Team%20Racing&room=ab%09cd"),
                    WEBHOST_LINK + "\n", "archipelago://Racer\t:None@archipelago.gg:38281?game=x&room=y"):
            with self.subTest(url=url):
                self.assertRejected(url, "control character not allowed")

    def test_invalid_authority(self):
        cases = [
            "archipelago://archipelago.gg:38281?game=Crash%20Team%20Racing&room=" + ROOM,  # no slot
            link(slot="", password="None"),
            link(hostinfo="archipelago.gg"),                 # no port
            link(hostinfo="archipelago.gg:"),
            link(hostinfo="archipelago.gg:0"),
            link(hostinfo="archipelago.gg:65536"),
            link(hostinfo="archipelago.gg:123456"),
            link(hostinfo="archipelago.gg:+1"),
            link(hostinfo="archipelago.gg: 1"),
            link(hostinfo="archipelago.gg:38281:1"),
            link(hostinfo=":38281"),
            link(hostinfo="archipelago..gg:38281"),
            link(hostinfo="archipelago.gg.:38281"),
            link(hostinfo="evil.com\\archipelago.gg:38281"),
            link(hostinfo="exa%6Dple.com:38281"),
            link(hostinfo="1.2.3:38281"),
            link(hostinfo="256.1.1.1:38281"),
            link(hostinfo="[::1:38281"),
            link(hostinfo="[::1]38281"),
            link(hostinfo="[fe80::1%25eth0]:38281"),
            link(hostinfo="[]:38281"),
            link(hostinfo="h%C3%A9st:38281"),
            link(hostinfo=f"{'a' * 117}:38281"),
            WEBHOST_LINK.replace("archipelago.gg:38281", "archipelago.gg:38281/evil"),
            WEBHOST_LINK + "#frag",
            "Archipelago://" + WEBHOST_LINK[len("archipelago://"):],
            "ctr-ap://connect?host=a&port=1&slot=b&room=c",
            "https://archipelago.gg/room/" + ROOM,
        ]
        for url in cases:
            with self.subTest(url=url):
                self.assertRejected(url)

    def test_last_at_ends_the_user_info(self):
        # Same split as urllib and CommonClient: nothing before the last '@'
        # can pick the host.
        url = "archipelago://Racer:None@evil.example@archipelago.gg:38281?game=Crash%20Team%20Racing&room=" + ROOM
        self.assertIn("host=archipelago.gg&", lc.convert_room_link(url))

    def test_slot_bounds(self):
        self.assertRejected(link(slot="é" * 32), "slot name too long")  # 64 bytes
        self.assertRejected(link(slot="x" * 64), "slot name too long")
        self.assertRejected(link(slot="%20Racer"), "slot name has edge whitespace")
        self.assertRejected(link(slot="Racer%20"), "slot name has edge whitespace")
        self.assertRejected(link(slot="Racer%C2%A0"), "slot name has edge whitespace")

    def test_overlong_source_and_non_string(self):
        self.assertRejected(link(query=f"game=Crash%20Team%20Racing&room={ROOM}&pad={'p' * 2100}"),
                            "room link too long")
        self.assertRejected(None, "no room link")
        self.assertRejected("", "no room link")


class TestLaunchClient(unittest.TestCase):
    def test_opens_once_after_validation(self):
        rec = Recorder()
        self.assertTrue(lc.launch_client(WEBHOST_LINK, open_url=rec.open_url, show=rec.show))
        self.assertEqual(rec.opened, [EXPECTED])
        self.assertEqual(rec.shown, [])

    def test_default_opener_is_webbrowser_open_called_once(self):
        with mock.patch("webbrowser.open", return_value=True) as opened:
            self.assertTrue(lc.launch_client(WEBHOST_LINK, show=Recorder().show))
        opened.assert_called_once_with(EXPECTED)

    def test_never_opens_on_rejection(self):
        rec = Recorder()
        for bad in (link(query=f"room={ROOM}"), link(hostinfo="archipelago.gg:0"), "not a link"):
            self.assertFalse(lc.launch_client(bad, open_url=rec.open_url, show=rec.show))
        self.assertEqual(rec.opened, [])
        self.assertEqual(len(rec.shown), 3)
        self.assertTrue(all(error for _, _, error in rec.shown))

    def test_manual_card_click_shows_setup_guidance_and_opens_nothing(self):
        rec = Recorder()
        with mock.patch("webbrowser.open") as opened:
            self.assertFalse(lc.launch_client(show=rec.show))
        opened.assert_not_called()
        self.assertEqual(rec.opened, [])
        self.assertEqual(len(rec.shown), 1)
        title, text, error = rec.shown[0]
        self.assertFalse(error)
        self.assertIn("room page", text)

    def test_extra_arguments_are_rejected(self):
        rec = Recorder()
        self.assertFalse(lc.launch_client(WEBHOST_LINK, "--extra", open_url=rec.open_url, show=rec.show))
        self.assertEqual(rec.opened, [])

    def test_open_failure_is_reported(self):
        for opener in (Recorder(result=False).open_url, mock.Mock(side_effect=OSError("no handler"))):
            rec = Recorder()
            self.assertFalse(lc.launch_client(WEBHOST_LINK, open_url=opener, show=rec.show))
            self.assertEqual(len(rec.shown), 1)
            self.assertTrue(rec.shown[0][2])

    def test_messages_never_echo_the_link_or_credentials(self):
        secret_slot = "SecretSlot"
        secret_pass = "hunter2"
        bad_links = [
            f"archipelago://{secret_slot}:{secret_pass}@archipelago.gg:0?game=Crash%20Team%20Racing&room={ROOM}",
            f"archipelago://{secret_slot}:{secret_pass}@archipelago.gg:38281?game=Other&room={ROOM}",
            f"archipelago://{secret_slot}%zz:{secret_pass}@archipelago.gg:38281?game=Crash%20Team%20Racing&room={ROOM}",
            f"archipelago://{secret_slot}:{secret_pass}@archipelago.gg:38281?game=Crash%20Team%20Racing&room=a/b",
        ]
        forbidden = (secret_slot, secret_pass, "archipelago.gg", ROOM, "archipelago://", "38281")
        for bad in bad_links:
            rec = Recorder()
            with self.assertLogs(level=logging.DEBUG) as logs:
                lc.launch_client(bad, open_url=rec.open_url, show=rec.show)
            output = "\n".join(logs.output) + "\n".join(f"{t}\n{m}" for t, m, _ in rec.shown)
            for value in forbidden:
                self.assertNotIn(value, output)
        # A successful hand-off logs no values either.
        rec = Recorder()
        good = f"archipelago://{secret_slot}:{secret_pass}@archipelago.gg:38281?game=Crash%20Team%20Racing&room={ROOM}"
        with self.assertLogs(level=logging.DEBUG) as logs:
            lc.launch_client(good, open_url=rec.open_url, show=rec.show)
        for value in forbidden:
            self.assertNotIn(value, "\n".join(logs.output))
        self.assertNotIn(secret_pass, rec.opened[0])


class TestNoSideEffectSurface(unittest.TestCase):
    """The AP-Pie audit flags process launching in apworlds. The component
    reaches the OS only through webbrowser.open."""

    def test_module_imports_and_calls(self):
        with open(lc.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported - {"__future__", "logging", "re", "unicodedata", "typing", "urllib",
                                     "webbrowser", "Utils", "worlds"}, set())
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for banned in ("startfile", "Popen", "system", "spawn", "run", "call", "check_output",
                       "open_new", "open_new_tab", "urlopen", "settings", "get_settings"):
            self.assertNotIn(banned, attrs | names)

    def test_webbrowser_open_is_the_only_os_hand_off(self):
        with open(lc.__file__, encoding="utf-8") as f:
            source = f.read()
        opens = [node for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Attribute) and node.attr == "open"
                 and isinstance(node.value, ast.Name) and node.value.id == "webbrowser"]
        self.assertEqual(len(opens), 1)
        for banned in ("subprocess", "os.startfile", "Popen", "shortcuts.vdf", "host.yaml", "winreg"):
            self.assertNotIn(banned, source)


# ctr-native-ap's launch-request parser, compiled from its own source, is the
# authority on what the component's output must look like. Point
# CTR_NATIVE_AP_SOURCE at a ctr-native-ap checkout (with include/ and platform/)
# to run it; without that the test skips.
NATIVE_DRIVER = r"""
#include <stdio.h>
#include <string.h>
#include "platform/native_launch_request.h"
int main(void) {
    char line[4096];
    while (fgets(line, sizeof line, stdin)) {
        NativeLaunchRequest r;
        NativeLaunchRequestStatus s;
        line[strcspn(line, "\n")] = 0;
        s = NativeLaunchRequest_Parse(line, &r);
        if (s == NATIVE_LAUNCH_REQUEST_OK)
            printf("0\t%s\t%u\t%s\t%s\n", r.host, r.port, r.slot, r.room);
        else
            printf("%d\n", (int)s);
    }
    return 0;
}
"""


class TestNativeParserAgreement(unittest.TestCase):
    ACCEPTED = [
        (WEBHOST_LINK, ("archipelago.gg", 38281, "Racer One", ROOM)),
        (link(hostinfo="[::1]:1"), ("[::1]", 1, "Racer One", ROOM)),
        (link(hostinfo="127.0.0.1:65535"), ("127.0.0.1", 65535, "Racer One", ROOM)),
        (link(slot="R%C3%A4cer%26%3D%2B%40%3F", password="hunter2"), ("archipelago.gg", 38281, "Räcer&=+@?", ROOM)),
        (link(slot="é" * 31 + "x", hostinfo=f"{'a' * 116}:38281",
              query=f"game=Crash%20Team%20Racing&room={'r' * 64}"), ("a" * 116, 38281, "é" * 31 + "x", "r" * 64)),
        (link(query="game=Crash%20Team%20Racing&room=a+b%20c"), ("archipelago.gg", 38281, "Racer One", "a b c")),
    ]

    def test_native_parser_accepts_every_output(self):
        source = os.environ.get("CTR_NATIVE_AP_SOURCE")
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not source or not compiler:
            self.skipTest("set CTR_NATIVE_AP_SOURCE to a ctr-native-ap checkout and provide a C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            driver = os.path.join(tmp, "driver.c")
            exe = os.path.join(tmp, "driver")
            with open(driver, "w", encoding="utf-8") as f:
                f.write(NATIVE_DRIVER)
            subprocess.run([compiler, "-std=c99", "-Wall", "-Werror", "-I", os.path.join(source, "include"),
                            "-I", source, driver, os.path.join(source, "platform", "native_launch_request.c"),
                            "-o", exe], check=True)
            outputs = [lc.convert_room_link(url) for url, _ in self.ACCEPTED]
            result = subprocess.run([exe], input="\n".join(outputs) + "\n", capture_output=True,
                                    check=True, encoding="utf-8")
        rows = result.stdout.splitlines()
        self.assertEqual(len(rows), len(outputs))
        for row, (_, expected) in zip(rows, self.ACCEPTED):
            status, host, port, slot, room = row.split("\t")
            self.assertEqual(status, "0")
            self.assertEqual((host, int(port), slot, room), expected)


# The world as players install it: packed by the same tool CI uses and loaded
# by Archipelago's own apworld loader from custom_worlds, with the loose
# worlds/ctr folder absent.
PACKED_PROBE = r"""
import json, sys
from unittest import mock
import worlds
from worlds.AutoWorld import AutoWorldRegister
from worlds.LauncherComponents import components, Type
world = AutoWorldRegister.world_types["Crash Team Racing"]
module = sys.modules[world.__module__]
mine = [c for c in components if c.game_name == "Crash Team Racing"]
with mock.patch("webbrowser.open", return_value=True) as opened:
    mine[0].func(sys.argv[1])
print(json.dumps({
    "module_file": module.__file__,
    "failed": list(worlds.failed_world_loads),
    "components": [[c.display_name, c.game_name, c.type is Type.CLIENT, c.supports_uri] for c in mine],
    "opened": [call.args[0] for call in opened.call_args_list],
}))
"""


class TestPackedWorld(unittest.TestCase):
    def test_packed_apworld_imports_and_registers_the_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "ap")
            os.makedirs(os.path.join(root, "worlds"))
            os.makedirs(os.path.join(root, "custom_worlds"))
            for entry in os.listdir(AP_ROOT):
                if entry in ("worlds", "custom_worlds") or entry.startswith("."):
                    continue
                os.symlink(os.path.join(AP_ROOT, entry), os.path.join(root, entry))
            for entry in os.listdir(os.path.join(AP_ROOT, "worlds")):
                if entry in ("ctr", "__pycache__"):
                    continue
                os.symlink(os.path.join(AP_ROOT, "worlds", entry), os.path.join(root, "worlds", entry))
            packed = os.path.join(root, "custom_worlds", "ctr.apworld")
            subprocess.run([sys.executable, os.path.join(WORLD_DIR, "tools", "build_apworld.py"), packed],
                           check=True, capture_output=True)
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", SKIP_REQUIREMENTS_UPDATE="1")
            env.pop("PYTHONPATH", None)
            result = subprocess.run([sys.executable, "-c", PACKED_PROBE, WEBHOST_LINK], cwd=root, env=env,
                                    capture_output=True, encoding="utf-8", timeout=600)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(report["module_file"].startswith(packed + os.sep), report["module_file"])
        self.assertNotIn("ctr", report["failed"])
        self.assertNotIn("Crash Team Racing", report["failed"])
        self.assertEqual(report["components"], [["Crash Team Racing Client", "Crash Team Racing", True, True]])
        self.assertEqual(report["opened"], [EXPECTED])


if __name__ == "__main__":
    unittest.main()
