"""The 0.3.0 id step: every name and code it minted, pinned family by family.

Source of every row: the 0.3.0 minting register with the answers of
2026-10-13 22:02 CEST, and the pinned registry commit for the named blocks.
The per-name pins are in fixtures/location_class_id_stability_2026_10_15_
minting_030.json and fixtures/item_id_stability_2026_10_15_minting_030.json;
this file pins the shape (first and last code, spelling, order, what is
reserved and not minted) and that nothing here creates a location or an item.
"""
import json
import pkgutil
import unittest

from test.general import setup_multiworld, gen_steps

from .. import ctrAPWorld, traps
from ..cup_checks import CUP_NAMES, GEM_CUPS
from ..crystal_checks import CRYSTAL_ARENAS
from ..item_boxes import BOX_TRACKS
from ..Locations import CTR_LOCATION_CLASSES
from ..minted_items_030 import ITEM_DATA, MINTED_TRAP_KEYS
from .. import named_tracks as nt

L = ctrAPWorld.location_name_to_id
I = ctrAPWorld.item_name_to_id
REGISTRY_COMMIT = "e01959af45848777e11508e8bf357fd143f9f68b"
REGISTRY_DIGEST = "b0ff7ced66135542d4588bcec2c44e04aba37e1034675e890920b5ec06ce5ea3"
NEW_CLASSES = ("named_track", "cup_win", "cup_sweep", "cup_leg_victory", "lap_completion",
               "crystalsanity", "custom_relic", "custom_track_race_v2", "custom_wumpa",
               "custom_item_boxes", "wumpa_shop")


class TestFixedFamilies(unittest.TestCase):
    def test_cup_checks(self):
        self.assertEqual(len(CUP_NAMES), 27)
        self.assertEqual(CUP_NAMES[0], "Patries Cup")
        self.assertEqual(CUP_NAMES[-1], "Sphere Cup")
        for i, cup in enumerate(CUP_NAMES):
            self.assertEqual(L[f"{cup}: Win"], 35027000 + i)
            self.assertEqual(L[f"{cup}: Win All Legs"], 35027200 + i)
        for i, cup in enumerate(GEM_CUPS):
            self.assertEqual(L[f"{cup}: Win All Legs"], 35028300 + i)

    def test_cup_leg_victory(self):
        self.assertEqual(L["Cortex Vortex: Cup Leg Victory"], 35027027)
        for i, track in enumerate(BOX_TRACKS):
            self.assertEqual(L[f"{track}: Cup Leg Victory"], 35016800 + i)
        for n in (1, 132):
            self.assertEqual(L[f"Custom Track {n}: Cup Leg Victory"], 35016820 + n - 1)

    def test_lap_checks(self):
        for i, track in enumerate(BOX_TRACKS):
            self.assertEqual(L[f"{track}: Complete One Lap"], 35028000 + i)
        self.assertEqual(L["Cortex Vortex: Complete One Lap"], 35026009)
        for n in (1, 132):
            self.assertEqual(L[f"Custom Track {n}: Complete One Lap"], 35028100 + n - 1)

    def test_retail_crystals(self):
        self.assertEqual(CRYSTAL_ARENAS, ("Skull Rock", "Rampage Ruins", "Rocky Road", "Nitro Court"))
        for a, arena in enumerate(CRYSTAL_ARENAS):
            self.assertEqual(L[f"{arena}: Crystal 01"], 35028400 + 20 * a)
            self.assertEqual(L[f"{arena}: Crystal 20"], 35028400 + 20 * a + 19)
            self.assertNotIn(f"{arena}: Crystal 21", L)

    def test_relic_families(self):
        self.assertEqual(L["Cortex Vortex: Relic Race Perfect"], 35026005)
        self.assertEqual(L["Custom Track 1: Relic Race Perfect"], 35024000)
        self.assertEqual(L["Custom Track 132: Relic Race Perfect"], 35024131)
        self.assertEqual(L["Custom Track 1: Sapphire Time Trial"], 35022000)
        self.assertEqual(L["Custom Track 132: Platinum Time Trial"], 35022395)

    def test_race_v2_only_above_slot_32(self):
        self.assertEqual(L["Custom Track 32: Trophy Race"], 35016331)  # live v1, unchanged
        self.assertEqual(L["Custom Track 33: Trophy Race"], 35019192)
        self.assertEqual(L["Custom Track 33: Held 1st"], 35019193)
        self.assertEqual(L["Custom Track 33: Finish (Any Position)"], 35019197)
        self.assertEqual(L["Custom Track 132: Finish (Any Position)"], 35019791)

    def test_generic_wumpa_and_boxes(self):
        self.assertEqual(L["Custom Track 1: Reach 10 Wumpa"], 35016600)
        self.assertEqual(L["Custom Track 132: Reach 10 Wumpa"], 35016731)
        self.assertEqual(L["Custom Track 1: Item Box 1"], 35017000)
        self.assertEqual(L["Custom Track 132: Item Box 15"], 35018979)
        self.assertNotIn("Custom Track 1: Item Box 16", L)

    def test_crystal_challenge_rename_kept_the_codes(self):
        """Ruled 2026-10-13 22:02 CEST: every arena completion check is
        `<Arena>: Crystal Challenge`; the four retail ids do not move."""
        for i, arena in enumerate(CRYSTAL_ARENAS):
            self.assertEqual(L[f"{arena}: Crystal Challenge"], 35013000 + i)
            self.assertNotIn(f"{arena}: Crystal Bonus Round", L)


class TestReservedNotMinted(unittest.TestCase):
    RESERVED = (
        (35019000, 35019191, "race v2 codes of slots 1..32, never used"),
        (35027100, 35027199, "later cup names, Win"),
        (35027300, 35027399, "later cup names, Win All Legs"),
        (35028503, 35028519, "arcade completion expansion"),
        (35028580, 35028599, "arcade crystal expansion"),
        (35028625, 35028639, "Wumpa Shop expansion, N. Sanity Beach"),
        (35028665, 35028679, "Wumpa Shop expansion, Gem Stone Valley"),
        (35028705, 35028719, "Wumpa Shop expansion, Lost Ruins"),
        (35028745, 35028759, "Wumpa Shop expansion, Glacier Park"),
        (35028785, 35028799, "Wumpa Shop expansion, Citadel City"),
    )

    def test_reserved_ranges_hold_no_id(self):
        codes = set(L.values()) | set(I.values())
        for first, last, label in self.RESERVED:
            with self.subTest(label):
                self.assertFalse({c for c in codes if first <= c <= last})
                self.assertTrue(any(lo <= first and last <= hi
                                    for lo, hi, _l in nt.RESERVED_ID_RANGES), label)

    def test_reserved_named_offsets_hold_no_id(self):
        for track in nt.NAMED_TRACKS:
            base = nt.NAMED_LOCATION_BASE + nt.LOCATION_BUDGET * track.block_index
            used = {code - base for _n, code in nt.track_locations(track)}
            self.assertEqual(used, set(range(0, 17)) | set(range(20, 35)))
        self.assertEqual([(lo, hi) for lo, hi, _l in nt.RESERVED_LOCATION_OFFSETS],
                         [(17, 19), (35, 119), (120, 140), (141, 199)])

    def test_arcade_names_belong_to_the_separate_259_mint(self):
        for a,arena in enumerate(("Parking Lot", "The North Bowl", "Lab Basement")):
            self.assertEqual(L[arena+": Crystal Challenge"],35028500+a)
            self.assertEqual([L[f"{arena}: Crystal {n:02d}"] for n in range(1,21)],
                             list(range(35028520+20*a,35028540+20*a)))


class TestSecondPassWumpaShop(unittest.TestCase):
    """The 0.3.0 second id step (2026-10-27): the 125 Wumpa Shop slots of the
    #249 design, `35028600 + 40 * hub + (n - 1)`. No item is minted."""

    HUBS = ("N. Sanity Beach", "Gem Stone Valley", "Lost Ruins", "Glacier Park", "Citadel City")

    def test_names_and_codes(self):
        for h, hub in enumerate(self.HUBS):
            with self.subTest(hub):
                self.assertEqual([L[f"{hub} Shop: Slot {n}"] for n in range(1, 26)],
                                 list(range(35028600 + 40 * h, 35028625 + 40 * h)))
                self.assertNotIn(f"{hub} Shop: Slot 26", L)
                self.assertNotIn(f"{hub} Shop: Slot 01", L)
                self.assertEqual(ctrAPWorld.location_name_to_id[f"{hub} Shop: Slot 1"],
                                 35028600 + 40 * h)

    def test_whole_shop_reservation_holds_only_shop_names(self):
        codes = {n: c for n, c in L.items() if 35028600 <= c <= 35028799}
        self.assertEqual(len(codes), 125)
        self.assertTrue(all(" Shop: Slot " in n for n in codes))
        self.assertFalse({c for c in I.values() if 35028600 <= c <= 35028799})

    def test_shop_stems_are_reserved_for_custom_titles(self):
        """Like every minted stem, `<Hub> Shop` now clashes with a custom
        title of that exact name, which gets the `(Custom)` suffix (#306)."""
        from ..custom_track_titles import reserved_stems, room_title
        for hub in self.HUBS:
            self.assertIn(f"{hub} Shop".casefold(), reserved_stems())
        self.assertEqual(room_title("Glacier Park Shop"), "Glacier Park Shop (Custom)")
        self.assertEqual(room_title("Glacier Park Shopping"), "Glacier Park Shopping")

    def test_no_event_or_item_identity(self):
        self.assertNotIn("Wumpa Income", L)
        self.assertNotIn("Wumpa Income", I)
        self.assertNotIn("Wumpa Tax", I)


class TestNamedBatch(unittest.TestCase):
    def test_pinned_registry_commit_and_mint_entries_only(self):
        doc = json.loads(pkgutil.get_data("worlds.ctr", "data/named_tracks.json").decode("utf-8"))
        self.assertEqual(doc["registry"], {"repository": "https://github.com/dowlle/ctr-track-registry",
                                           "commit": REGISTRY_COMMIT, "digest": REGISTRY_DIGEST})
        blocks = [row["block_index"] for row in doc["tracks"]]
        self.assertEqual(blocks, sorted(set(range(85)) - {14, 16, 68}))
        keys = {row["track_key"] for row in doc["tracks"]}
        # 14 and 68 are `reserved` (hubs, no race mode confirmed); 16 is
        # `builtin` (the hard-coded Cortex Vortex block).
        self.assertFalse(keys & {"christmas-hub", "st-patricks-day-hub-world", "cortex-vortex"})
        self.assertEqual(len(nt.NAMED_TRACKS), 82)

    def test_offset_layout_of_the_0_3_0_step(self):
        self.assertEqual(L["Baby T Park: Cup Leg Victory"], nt.location_code(8, "cup_leg_victory"))
        self.assertEqual(nt.location_code(8, "cup_leg_victory"), 35201615)
        self.assertEqual(L["Baby T Park: Complete One Lap"], 35201616)
        self.assertEqual(L["Baby T Park: Item Box 1"], 35201620)
        self.assertEqual(L["Baby T Park: Item Box 15"], 35201634)
        self.assertEqual(I["Letter R (Baby T Park)"], 35100042)
        self.assertEqual(L["Acid Lake: Trophy Race"], 35200000)
        self.assertEqual(L["Yoshi Circuit Legacy: Item Box 15"], 35216834)


class TestMintedItems(unittest.TestCase):
    def test_codes_and_classes(self):
        self.assertEqual([(r["name"], r["code"], r["classification"].name) for r in ITEM_DATA], [
            ("Reserve Top-Up", 35010203, "filler"),
            ("Warp Pad Preview", 35010204, "useful"),
            ("AP Box Colours", 35010205, "useful"),
            ("Clocked Out", 35010206, "trap"),
            ("Reverse Camera", 35010207, "trap"),
        ])
        for row in ITEM_DATA:
            self.assertEqual(I[row["name"]], row["code"])
            self.assertEqual(row["count"], 0)

    def test_only_implemented_minted_traps_are_registered(self):
        """No registry row until the feature PR: the trap_identities block and
        the trap draw stay as they are."""
        registered = {e.name for e in traps.TRAP_REGISTRY}
        self.assertEqual(registered & set(MINTED_TRAP_KEYS), {"Clocked Out", "Reverse Camera"})
        self.assertEqual({e.key for e in traps.TRAP_REGISTRY} & set(MINTED_TRAP_KEYS.values()), {"clocked_out", "reverse_camera"})
        self.assertLessEqual(set(MINTED_TRAP_KEYS), set(ctrAPWorld.item_name_groups["Traps"]))


class TestInert(unittest.TestCase):
    def test_new_classes_create_nothing_in_a_default_seed(self):
        mw = setup_multiworld(ctrAPWorld, gen_steps, seed=1503)
        created = {loc.name for loc in mw.get_locations(1)}
        for location_class in CTR_LOCATION_CLASSES:
            if location_class.key in NEW_CLASSES:
                with self.subTest(location_class.key):
                    self.assertFalse(created & set(location_class.names()))
        minted = {row["name"] for row in ITEM_DATA} - {"Clocked Out", "Reverse Camera", "Reserve Top-Up"}
        self.assertFalse({item.name for item in mw.itempool} & minted)


class TestBuildScript(unittest.TestCase):
    """tools/build_named_tracks.py against a throwaway registry repository."""

    def _repo(self, tamper=False):
        import hashlib, os, subprocess, tempfile
        from ..tools import build_named_tracks as b
        root = tempfile.mkdtemp(prefix="ctr-registry-test-")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        os.makedirs(os.path.join(root, "tracks"))
        rows = [("alpha-track", 0, "Alpha Track", "mint"), ("hub-world", 1, "Hub World", "reserved"),
                ("cortex-vortex", 2, "Cortex Vortex", "builtin")]
        registry = {"schema_version": 1, "tracks": [
            {"track_key": k, "block_index": i, "ap_name": n, "mint_status": s, "shipped_in": None,
             "maps_to": "Cortex Vortex" if s == "builtin" else None,
             "revisions": [{"content_id": hashlib.sha256(k.encode()).hexdigest()}]}
            for k, i, n, s in rows]}
        files = {"registry.json": json.dumps(registry).encode()}
        for k, *_ in rows:
            files[f"tracks/{k}.json"] = json.dumps({"track_key": k}).encode()
        digest = b.digest_of(files)
        named = {"format": 1, "registry": {"digest": "0" * 64 if tamper else digest},
                 "tracks": b.mint_rows(registry)}
        files["named_tracks.json"] = json.dumps(named).encode()
        files["DIGEST.json"] = json.dumps({"digest": digest}).encode()
        for rel, data in files.items():
            with open(os.path.join(root, rel), "wb") as f:
                f.write(data)
        git = ["git", "-C", root, "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "seed"], check=True)
        commit = subprocess.run(git[:3] + ["rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True).stdout.strip()
        return b, __import__("pathlib").Path(root), commit, digest

    def test_only_mint_entries_with_provenance(self):
        b, root, commit, digest = self._repo()
        doc = b.build(root, commit)
        self.assertEqual(doc["registry"]["commit"], commit)
        self.assertEqual(doc["registry"]["digest"], digest)
        self.assertEqual([r["track_key"] for r in doc["tracks"]], ["alpha-track"])

    def test_digest_mismatch_is_refused(self):
        b, root, commit, _digest = self._repo(tamper=True)
        with self.assertRaises(SystemExit):
            b.build(root, commit)

    def test_dropping_a_shipped_block_is_refused(self):
        b, root, commit, _digest = self._repo()
        doc = b.build(root, commit)
        previous = {"tracks": [{"track_key": "gone", "block_index": 5, "ap_name": "Gone"}]}
        self.assertTrue(b.append_only_problems(previous, doc))
        self.assertFalse(b.append_only_problems(doc, doc))
