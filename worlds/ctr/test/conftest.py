"""Tests of the original generator, which no YAML reaches since one generator row 7.
row12_tests.txt lists them. They are skipped here, and row 12 deletes them with the
code they test."""
import pathlib

import pytest

LISTED = set(pathlib.Path(__file__).with_name("row12_tests.txt").read_text(encoding="utf-8").split())


def pytest_collection_modifyitems(items):
    skip = pytest.mark.skip(reason="tests the original generator, which row 12 deletes")
    for item in items:
        if item.nodeid.rpartition("/")[2] in LISTED:
            item.add_marker(skip)
