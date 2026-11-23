"""Merged mode builds: the optional `relic_files` pin pair on custom packages.

Some tracks ship their modes in two Saphi builds: one carries the crates,
letters and Arcade, a sibling carries the Relic Race lap graph. `relic_files`
pins the second build. Native serves it only for a Relic Race; the apworld adds
no rule and no id, so identity, crates, spots and sanity stay those of the main
pair. The descriptor rules are shared with native (tools/test-content-plan-parity.py).
"""
import copy
import json
import unittest
from pathlib import Path

from .. import content_plan, custom_packages
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN, options_with
from .test_track_modes import mode_pool
from .test_toasty_terrace import PACKAGE as TOASTY_130, TRACK, toasty_options

RELIC_PAIR = [dict(role="lev", sha256="db74f5ae84d1b57cef68fde1af498b799e8c0bc04262a7fefdfe47c4f5ea181e",
                   bytes=1085668, format="ctr-lev", format_version=1),
              dict(role="vrm", sha256="5d71c8083bef9cdf16312c879da4431fa61129fe83bb26622ed60d1dd991f673",
                   bytes=458808, format="ctr-vrm", format_version=1)]
TARGETS = dict(sapphire=86400, gold=67200, platinum=48000)  # 1:30.00, 1:10.00, 0:50.00


def merged(base=None, **changes):
    """UNKNOWN (relic true, targets set) with a relic pair; changes replace top-level fields."""
    d = copy.deepcopy(base if base is not None else UNKNOWN)
    d["relic_files"] = copy.deepcopy(RELIC_PAIR)
    d["relic_revision"] = "1.3.1"
    d.update(copy.deepcopy(changes))
    return {k: v for k, v in d.items() if v is not None}


def toasty_merged(**changes):
    d = copy.deepcopy(TOASTY_130)
    d["capabilities"]["relic"] = True
    d["relic_targets"] = dict(TARGETS)
    d["relic_files"] = copy.deepcopy(RELIC_PAIR)
    d["relic_revision"] = "1.3.1"
    d.update(copy.deepcopy(changes))
    return d


class TestRelicFilesAdmission(unittest.TestCase):
    def refused(self, descriptor, field):
        with self.assertRaises(custom_packages.PackageError) as caught:
            custom_packages.admit(descriptor)
        self.assertIn(field, str(caught.exception))

    def test_canonical_admission(self):
        self.assertEqual(custom_packages.admit(merged()), merged())
        no_revision = merged()
        del no_revision["relic_revision"]
        self.assertEqual(custom_packages.admit(copy.deepcopy(no_revision)), no_revision)
        same_revision = merged(relic_revision=UNKNOWN["revision"])  # Sunken Sprint: both builds are 1.0.0
        self.assertEqual(custom_packages.admit(copy.deepcopy(same_revision)), same_revision)
        # One shared file is fine: only the whole pair must differ.
        shared_vrm = merged()
        shared_vrm["relic_files"][1] = copy.deepcopy(UNKNOWN["files"][1])
        self.assertEqual(custom_packages.admit(copy.deepcopy(shared_vrm)), shared_vrm)
        self.assertEqual(custom_packages.admit(toasty_merged()), toasty_merged())

    def test_refusals(self):
        same = merged(relic_files=copy.deepcopy(UNKNOWN["files"]))
        self.refused(same, "relic_files")
        one = merged()
        one["relic_files"] = one["relic_files"][:1]
        self.refused(one, "relic_files")
        three = merged()
        three["relic_files"].append(copy.deepcopy(three["relic_files"][0]))
        self.refused(three, "relic_files")
        swapped = merged()
        swapped["relic_files"].reverse()
        self.refused(swapped, "relic_files[0].role")
        self.refused(merged(relic_files="x"), "relic_files")
        for index, field, value, name in (
                (0, "role", "vrm", "role"), (0, "format", "ctr-vrm", "format"),
                (1, "format", "ctr-lev", "format"), (0, "format_version", 2, "format_version"),
                (0, "format_version", True, "format_version"),
                (0, "sha256", "DB" * 32, "sha256"), (0, "sha256", "db" * 31, "sha256"),
                (1, "sha256", "zz" * 32, "sha256"), (0, "bytes", 0, "bytes"),
                (0, "bytes", custom_packages.LEV_MAX_BYTES + 1, "bytes"),
                (1, "bytes", custom_packages.VRM_MAX_BYTES + 1, "bytes"), (1, "bytes", "9", "bytes")):
            d = merged()
            d["relic_files"][index][field] = value
            with self.subTest(index=index, field=field, value=value):
                self.refused(d, f"relic_files[{index}].{name}")
        extra = merged()
        extra["relic_files"][0]["extra"] = 1
        self.refused(extra, "unknown field extra")
        missing = merged()
        del missing["relic_files"][1]["bytes"]
        self.refused(missing, "missing bytes")
        # Within the limits: the largest allowed pair is accepted.
        largest = merged()
        largest["relic_files"][0]["bytes"] = custom_packages.LEV_MAX_BYTES
        largest["relic_files"][1]["bytes"] = custom_packages.VRM_MAX_BYTES
        self.assertTrue(custom_packages.admit(largest))

    def test_requires_the_relic_capability_and_targets(self):
        no_relic = merged()
        no_relic["capabilities"]["relic"] = False
        del no_relic["relic_targets"]
        self.refused(no_relic, "relic_files")
        self.assertIn("capabilities.relic", self._message(no_relic))
        keep_targets = merged()
        keep_targets["capabilities"]["relic"] = False
        self.refused(keep_targets, "relic_targets")  # the standing rule still fires
        no_targets = merged()
        del no_targets["relic_targets"]
        self.refused(no_targets, "relic_targets")

    def _message(self, descriptor):
        with self.assertRaises(custom_packages.PackageError) as caught:
            custom_packages.admit(descriptor)
        return str(caught.exception)

    def test_relic_revision_rules(self):
        for bad in ("", " 1.3.1", "1 3", "é", "x" * 65, 1, ["1"]):
            with self.subTest(bad=bad):
                self.refused(merged(relic_revision=bad), "relic_revision")
        null = merged()
        null["relic_revision"] = None
        self.refused(null, "relic_revision")
        self.assertTrue(custom_packages.admit(merged(relic_revision="x" * 64)))
        alone = copy.deepcopy(UNKNOWN)
        alone["relic_revision"] = "1.3.1"
        self.refused(alone, "relic_revision")

    def test_evidence_may_name_either_pair(self):
        def row(*hashes):
            return dict(capability="relic", file_hashes=list(hashes), verifier="fixture", revision=1,
                        level="structural")
        main_lev, main_vrm = (p["sha256"] for p in UNKNOWN["files"])
        relic_lev, relic_vrm = (p["sha256"] for p in RELIC_PAIR)
        d = merged(evidence=[row(relic_lev), row(relic_vrm), row(main_lev, relic_lev), row(relic_lev, relic_vrm),
                             row(main_lev, main_vrm)])
        self.assertEqual(custom_packages.admit(copy.deepcopy(d)), d)
        self.refused(merged(evidence=[row("ee" * 32)]), "evidence[0].file_hashes")
        # Without relic_files the relic hashes are not pins of the package.
        plain = copy.deepcopy(UNKNOWN)
        plain["evidence"] = [row(relic_lev)]
        self.refused(plain, "evidence[0].file_hashes")

    def test_repeated_pairs_across_packages_are_refused(self):
        other = copy.deepcopy(UNKNOWN)
        other.update(id="package/other-loop/1.0", content_id="other-loop", revision="1.0",
                     uuid="11111111-2222-4333-8444-555555555555", display_name="Other Loop")
        other["files"][0]["sha256"] = "c1" * 32
        other["files"][1]["sha256"] = "d1" * 32
        first = merged()
        for relic_pair in (RELIC_PAIR, UNKNOWN["files"]):
            twin = merged(base=other)
            twin["relic_files"] = copy.deepcopy(relic_pair if relic_pair is RELIC_PAIR else first["files"])
            with self.subTest(pair=relic_pair[0]["sha256"][:4]), self.assertRaises(custom_packages.PackageError) as caught:
                custom_packages.admit_all([first, twin])
            self.assertIn("repeats the LEV and VRM pair", str(caught.exception))
        # A relic pair that equals another package's files pair is the same ambiguity.
        reuse = copy.deepcopy(other)
        reuse["relic_files"] = copy.deepcopy(UNKNOWN["files"])
        reuse["relic_targets"] = dict(TARGETS)
        with self.assertRaises(custom_packages.PackageError):
            custom_packages.admit_all([copy.deepcopy(UNKNOWN), reuse])
        # Distinct pairs are fine, merged or not.
        distinct = merged(base=other)
        distinct["relic_files"][0]["sha256"] = "e1" * 32
        self.assertEqual(len(custom_packages.admit_all([first, distinct])), 2)
        self.assertEqual(len(custom_packages.admit_all([first, copy.deepcopy(other)])), 2)

    def test_schema_declares_the_fields(self):
        schema = json.loads((Path(custom_packages.__file__).parent / "data/content-plan-v1.schema.json").read_text())
        props = schema["$defs"]["Package"]["properties"]
        self.assertEqual(props["relic_files"]["minItems"], 2)
        self.assertEqual(props["relic_files"]["maxItems"], 2)
        self.assertEqual(props["relic_files"]["items"], {"$ref": "#/$defs/FilePin"})
        self.assertEqual(props["relic_revision"]["pattern"], props["revision"]["pattern"])
        self.assertEqual(props["relic_revision"]["maxLength"], 64)
        self.assertNotIn("relic_files", schema["$defs"]["Package"]["required"])


class TestRelicFilesPlan(unittest.TestCase):
    def test_round_trips_and_validates(self):
        plan = make_world(options_with([merged()])).ctr_content_plan
        self.assertEqual(plan["packages"], [merged()])
        self.assertTrue(content_plan.validate(plan))
        self.assertTrue(content_plan.validate(copy.deepcopy(plan), restoring=True))
        wire = json.loads(json.dumps(plan))
        self.assertEqual(wire["packages"], [merged()])
        self.assertTrue(content_plan.validate(wire, restoring=True))

    def test_shape_and_canonical_checks_refuse_forgeries(self):
        plan = make_world(options_with([merged()])).ctr_content_plan
        for restoring in (False, True):
            for mutate in (lambda p: p.update(relic_files=p["relic_files"][:1]),
                           lambda p: p.update(relic_files=copy.deepcopy(p["files"])),
                           lambda p: p["capabilities"].update(relic=False),
                           lambda p: p.pop("relic_targets"),
                           lambda p: p.update(relic_revision="")):
                forged = copy.deepcopy(plan)
                mutate(forged["packages"][0])
                with self.subTest(restoring=restoring), self.assertRaises(Exception):
                    content_plan.validate(forged, restoring=restoring)

    def test_a_merged_package_changes_nothing_but_the_wire_field(self):
        """Same package without relic_files: identical plan apart from that field and revision text."""
        plain = make_world(options_with([copy.deepcopy(UNKNOWN)])).ctr_content_plan
        both = make_world(options_with([merged()])).ctr_content_plan
        stripped = copy.deepcopy(both)
        for field in ("relic_files", "relic_revision"):
            del stripped["packages"][0][field]
        self.assertEqual(stripped, plain)
        self.assertEqual([c["location"] for c in both["checks"]], [c["location"] for c in plain["checks"]])

    def test_old_rooms_without_the_field_are_unchanged(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/older-room.json").read_text())
        plan = fixture["content_plan"]
        self.assertTrue(all("relic_files" not in p and "relic_revision" not in p for p in plan["packages"]))
        self.assertTrue(content_plan.validate(copy.deepcopy(plan), restoring=True))

    def test_toasty_like_package_keeps_main_pair_counts_and_adds_relic_checks(self):
        def build(package):
            options = toasty_options()
            options["content_pool"]["tracks"]["modes"] = ["trophy", "ctr", "relic"]
            options["item_pool"] = mode_pool()
            options["content_pool"]["tracks"]["custom"] = [package]
            options["content_pool"]["required_entries"] = [TRACK]
            return make_world(options, seed=3, stop_before="pre_fill")

        base = build(copy.deepcopy(TOASTY_130))
        # The same package with relic on and no relic pair: the reference for counts.
        relic_only = toasty_merged()
        del relic_only["relic_files"], relic_only["relic_revision"]
        reference = build(relic_only)
        both = build(toasty_merged())
        p_base, p_ref, p_both = (w.ctr_content_plan for w in (base, reference, both))
        self.assertTrue(content_plan.validate(p_both))
        wire = json.loads(json.dumps(both.fill_slot_data()))
        restored = make_world({}, passthrough=wire, stop_before="pre_fill")
        self.assertEqual(restored.ctr_content_plan, wire["content_plan"])
        self.assertEqual(p_both["packages"][0]["relic_files"], RELIC_PAIR)

        def checks_of(plan, kind=None):
            return [c for c in plan["checks"] if c["owner"] == TRACK and (kind is None or c["kind"] == kind)]
        relic_names = {c["display_name"] for c in checks_of(p_both, "relic")}
        self.assertEqual(relic_names, {"Toasty Terrace: Gold Time Trial", "Toasty Terrace: Platinum Time Trial"})
        self.assertEqual(checks_of(p_base, "relic"), [])
        # Crates, spots and sanity stay those of the main pair.
        row = lambda plan: next(r for r in plan["sanity"]["tracks"] if r["track_id"] == TRACK)
        self.assertEqual(row(p_both), row(p_base))
        self.assertEqual(row(p_both)["counts"], [20, 4, 0])
        self.assertEqual(len(checks_of(p_both, "box")), len(checks_of(p_base, "box")))
        for kind in ("box", "weapon_crate", "wumpa_crate", "lap", "trophy", "ctr", "relic"):
            self.assertEqual(len(checks_of(p_both, kind)), len(checks_of(p_ref, kind)), kind)
        self.assertEqual([c["display_name"] for c in checks_of(p_both)],
                         [c["display_name"] for c in checks_of(p_ref)])
        self.assertEqual(p_both["tracks"], p_ref["tracks"])
        self.assertEqual(p_both["item_boxes"], p_ref["item_boxes"])
        self.assertEqual(p_both["sanity"], p_ref["sanity"])
        self.assertEqual(p_both["checks"], p_ref["checks"])
