"""Check the packed Acid Lake room emitted by each determinism fuzz case."""

from pathlib import Path
from zipfile import ZipFile
import zlib

from fuzz import GenOutcome
from hooks.determinism import Hook as DeterminismHook
from Utils import restricted_loads
from worlds.ctr import track_fill


class Hook(DeterminismHook):
    def __init__(self):
        super().__init__()
        self.fill_error = None

    def before_generate(self, args):
        super().before_generate(args)
        self.fill_error = None

    def after_generate(self, mw, output_dir):
        super().after_generate(mw, output_dir)
        if mw is None:
            return
        try:
            archive_path = Path(output_dir) / f"AP_{mw.seed_name}.zip"
            with ZipFile(archive_path) as archive:
                name, = (name for name in archive.namelist() if name.endswith(".archipelago"))
                room = restricted_loads(zlib.decompress(archive.read(name)[1:]))
            slot, = room["slot_data"].values()
            plan = slot["content_plan"]
            if (slot["schema_version"] != track_fill.SCHEMA
                    or slot["ctr_options"]["schema_version"] != track_fill.SCHEMA
                    or track_fill.FEATURE not in plan["required_features"]):
                raise ValueError("The generated Acid Lake room must require schema 19 and track_fill_v1.")
            package, = (p for p in plan["packages"] if p["content_id"] == "acid-lake")
            frozen = package["fill"]
            bundled = track_fill.bundled("acid-lake", package["files"][0]["sha256"], package["laps"])
            if (not bundled or frozen["counts"]["time_crates"] != 29
                    or track_fill.canonical_bytes(frozen) != track_fill.canonical_bytes(bundled)):
                raise ValueError("The generated room must freeze all 29 pinned Acid Lake crates and targets.")
        except Exception as exc:
            self.fill_error = exc

    def reclassify_outcome(self, outcome, exc):
        if self.fill_error is not None:
            return GenOutcome.Failure, self.fill_error
        return super().reclassify_outcome(outcome, exc)
