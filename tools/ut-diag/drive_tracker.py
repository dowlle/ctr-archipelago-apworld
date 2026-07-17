"""Drive the real Universal Tracker headless to surface the swallowed error.

The tracker's received-item loop wraps every item in one try/except and, on any
failure, logs only a generic "Item name X not able to be created" while
discarding the real traceback. This script extracts the installed
tracker.apworld into a temp copy, patches that except to print the traceback,
then runs the full yaml-less UT path (interpret_slot_data -> re_gen_passthrough
-> generator -> updateTracker) against a seed's slot_data and feeds synthetic
received items. Any real exception in create/collect is printed verbatim.

Usage:
    ARCHIPELAGO_ROOT=/path/to/archipelago \\
    python drive_tracker.py <seed-archive.zip | multidata.archipelago>

Optional: TRACKER_APWORLD to point at a specific tracker.apworld
(default <ARCHIPELAGO_ROOT>/custom_worlds/tracker.apworld). See README.md.
"""
import io
import os
import sys
import glob
import zlib
import shutil
import pickle
import logging
import zipfile
import tempfile
import traceback
from collections import namedtuple

GAME = "Crash Team Racing"

# The tracker's received-item except, and the same block with a traceback print.
_ORIG_EXCEPT = (
    '            except Exception:\n'
    '                error_label: str = "Item name " + str(item_name) + '
    '" not able to be created"\n'
)
_PATCHED_EXCEPT = (
    '            except Exception:\n'
    '                import traceback as _tb; print("UT DIAG create/collect '
    'failed for", item_name); _tb.print_exc()\n'
    '                error_label: str = "Item name " + str(item_name) + '
    '" not able to be created"\n'
)


def _require_env(name):
    val = os.environ.get(name)
    if not val:
        sys.exit(f"set {name} (see README.md)")
    return val


class _TolerantUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except Exception:
            return type(name, (), {})


def _parse_multidata(path):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            inner = next(n for n in archive.namelist()
                         if n.endswith(".archipelago"))
            raw = archive.read(inner)
    else:
        with open(path, "rb") as handle:
            raw = handle.read()
    return _TolerantUnpickler(io.BytesIO(zlib.decompress(raw[1:]))).load()


def _extract_patched_tracker(ap_root, workdir):
    src = os.environ.get(
        "TRACKER_APWORLD",
        os.path.join(ap_root, "custom_worlds", "tracker.apworld"))
    if not os.path.exists(src):
        sys.exit(f"tracker.apworld not found at {src}; set TRACKER_APWORLD")
    with zipfile.ZipFile(src) as archive:
        archive.extractall(workdir)
    core = os.path.join(workdir, "tracker", "TrackerCore.py")
    text = open(core, encoding="utf-8").read()
    if _ORIG_EXCEPT not in text:
        print("WARNING: received-item except not found verbatim; tracker "
              "version may differ. Running unpatched.")
    else:
        open(core, "w", encoding="utf-8").write(
            text.replace(_ORIG_EXCEPT, _PATCHED_EXCEPT))
    return workdir


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    seed_path = sys.argv[1]
    if not os.path.exists(seed_path):
        matches = glob.glob(seed_path)
        seed_path = matches[-1] if matches else seed_path

    ap_root = _require_env("ARCHIPELAGO_ROOT")
    os.chdir(ap_root)
    sys.path.insert(0, ap_root)

    workdir = tempfile.mkdtemp(prefix="ut-diag-tracker-")
    try:
        sys.path.insert(0, _extract_patched_tracker(ap_root, workdir))
        import worlds  # noqa: F401
        from worlds.AutoWorld import AutoWorldRegister
        ctr = AutoWorldRegister.world_types[GAME]

        wire = next(sd for sd in _parse_multidata(seed_path)["slot_data"].values()
                    if isinstance(sd, dict) and sd.get("warp_pad_unlock"))

        import tracker.TrackerCore as tc_mod
        core = tc_mod.TrackerCore(logging.getLogger("ut-diag"), False, False)
        core.game = GAME
        core.slot = 1
        core.slot_name = "Tracker"
        core.team = 0
        core.hints = {}
        core.hide_excluded = False
        core.missing_locations = set()
        core.ignored_locations = set()
        core.enable_glitched_logic = False
        core.sorting_priorities = {
            g.value: 0 for g in tc_mod.TrackerLogLineGroup}
        core.sorting_priorities["error"] = -1

        core.initalize_tracker_core(ctr, wire)
        if core.multiworld is None:
            print("generation failed - the tracker could not build the world")
            return

        world = core.multiworld.worlds[core.player_id]
        name_to_id = {v: k for k, v in world.item_id_to_name.items()}
        received_item = namedtuple("received_item", "item flags location player")
        core.tracker_items_received = [
            received_item(name_to_id[n], 1, -1, -1)
            for n in ("Key", "Trophy", "Wumpa Fruit", "Sapphire Relic",
                      "Red CTR Token")
            if n in name_to_id
        ]
        try:
            result = core.updateTracker()
            counts = dict(result.all_items) if hasattr(result, "all_items") else result
            print("updateTracker completed; collected item counts:", counts)
        except Exception:  # noqa: BLE001
            print("updateTracker raised after the item loop "
                  "(the item traceback above, if any, is the real signal):")
            traceback.print_exc()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
