"""Imported-track patch locator on custom package descriptors (xdelta importer, 0.3.0).

A track imported from an xdelta patch keeps the B+ path (or its named block)
exactly as any other package. The optional `locator` only tells the client
which patch and BIGFILE slot to import, so a room can say "Needs <track> from
<patch>". It is informational: no logic, ids or admission depend on it.
"""
import copy
import unittest

from .. import content_plan, custom_packages
from .test_content_plan import make_world
from .test_custom_packages import UNKNOWN, options_with

LOCATOR = dict(kind="xdelta", patch_sha256="5e" * 32, bigfile_index=1, patch_name="Fixture Pack.xdelta",
               source_url="https://example.invalid/pack")


def located(**changes):
    d = copy.deepcopy(UNKNOWN)
    d["locator"] = dict(LOCATOR, **changes)
    return d


class TestLocator(unittest.TestCase):
    def test_locator_admits_canonically(self):
        self.assertEqual(custom_packages.admit(located()), located())
        minimal = located()
        del minimal["locator"]["patch_name"], minimal["locator"]["source_url"]
        self.assertEqual(custom_packages.admit(copy.deepcopy(minimal)), minimal)
        longest = located(source_url="https://" + "x" * 120)  # 128 bytes, the wire string budget
        self.assertEqual(custom_packages.admit(copy.deepcopy(longest)), longest)

    def refused(self, descriptor, field):
        with self.assertRaises(custom_packages.PackageError) as caught:
            custom_packages.admit(descriptor)
        self.assertIn(field, str(caught.exception))

    def test_locator_fields_are_closed_and_bounded(self):
        self.refused(located(kind="saphi"), "locator.kind")
        self.refused(located(patch_sha256="5E" * 32), "locator.patch_sha256")
        self.refused(located(patch_sha256="5e" * 31), "locator.patch_sha256")
        self.refused(located(bigfile_index=4096), "locator.bigfile_index")
        self.refused(located(bigfile_index=-1), "locator.bigfile_index")
        self.refused(located(bigfile_index=True), "locator.bigfile_index")
        self.refused(located(patch_name="x" * 65), "locator.patch_name")
        self.refused(located(patch_name="café.xdelta"), "locator.patch_name")
        self.refused(located(source_url="http://example.invalid/pack"), "locator.source_url")
        self.refused(located(source_url="https://example.invalid/a b"), "locator.source_url")
        self.refused(located(source_url="https://" + "x" * 121), "locator.source_url")  # 129 bytes
        self.refused(located(extra=1), "unknown field extra")
        d = located()
        del d["locator"]["bigfile_index"]
        self.refused(d, "missing bigfile_index")

    def test_locator_reaches_the_wire_and_changes_nothing_else(self):
        plain = make_world(options_with([UNKNOWN])).ctr_content_plan
        with_locator = make_world(options_with([located()])).ctr_content_plan
        self.assertEqual(with_locator["packages"], [located()])
        self.assertTrue(content_plan.validate(with_locator))
        longest = make_world(options_with([located(source_url="https://" + "x" * 120)])).ctr_content_plan
        self.assertTrue(content_plan.validate(longest))
        stripped = copy.deepcopy(with_locator)
        del stripped["packages"][0]["locator"]
        self.assertEqual(stripped, plain, "the locator must not change tracks, checks or ids")
