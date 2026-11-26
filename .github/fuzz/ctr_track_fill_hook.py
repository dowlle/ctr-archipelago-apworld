"""Check the packed Acid Lake and Arabian Heights Day room of each determinism fuzz case."""

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
            day, = (p for p in plan["packages"] if p["content_id"] == "arabian-heights-day")
            weapons = track_fill.package_weapons(day)
            if (len(weapons) != 27 or day["capabilities"]["weapon_crates"] != 0
                    or track_fill.canonical_bytes(day["fill"]) != track_fill.canonical_bytes(
                        track_fill.bundled("arabian-heights-day", day["files"][0]["sha256"], day["laps"]))):
                raise ValueError("The generated room must freeze Arabian Heights Day's 27 pinned weapon crates.")
            track = next(t["id"] for t in plan["tracks"] if t.get("package_id") == day["id"])
            spots = next((s for s in (plan.get("item_boxes") or {}).get("spot_sets", ()) if s["track_id"] == track), None)
            picked = set(spots["picked"]) if spots else set()
            row = next((r for r in (plan.get("sanity") or {}).get("tracks", ()) if r["track_id"] == track), None)
            if len(picked) > 15 or (row and (row["counts"][0] != 27 or picked & set(row["weapon_crate"]))):
                raise ValueError("Day seats at most 15 boxes and no seated crate is a sanity check.")
        except Exception as exc:
            self.fill_error = exc

    def reclassify_outcome(self, outcome, exc):
        if self.fill_error is not None:
            return GenOutcome.Failure, self.fill_error
        return super().reclassify_outcome(outcome, exc)
