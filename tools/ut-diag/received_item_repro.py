"""Headless Universal Tracker received-item check (issue #29).

Builds the yaml-less UT world from a seed's slot_data (default options plus
re_gen_passthrough plus a fake generation), then replays the seed's real item
placements as received items and asserts every one creates and collects. This
is the exact path the live tracker runs after connecting, so a green run here
means the received-item handling is sound on the current world code.

Usage:
    ARCHIPELAGO_ROOT=/path/to/archipelago \\
    CTR_WORLDS_SRC=/path/to/ctr-archipelago-apworld/worlds \\
    python received_item_repro.py <seed-archive.zip | multidata.archipelago>

See README.md for the environment variables.
"""
import io
import os
import sys
import glob
import zlib
import pickle
import zipfile

GAME = "Crash Team Racing"
GEN_STEPS = ("generate_early", "create_regions", "create_items",
             "set_rules", "connect_entrances", "generate_basic")


def _require_env(name):
    val = os.environ.get(name)
    if not val:
        sys.exit(f"set {name} (see README.md)")
    return val


def _load_core_and_world():
    """Put the Archipelago core on sys.path and return the CTR world class,
    force-loaded from CTR_WORLDS_SRC when that is set."""
    ap_root = _require_env("ARCHIPELAGO_ROOT")
    os.chdir(ap_root)
    sys.path.insert(0, ap_root)
    import worlds  # noqa: F401  (registers the bundled worlds)
    from worlds.AutoWorld import AutoWorldRegister

    ctr_src = os.environ.get("CTR_WORLDS_SRC")
    if ctr_src:
        # Drop any packaged apworld copy so the working-tree source wins.
        AutoWorldRegister.world_types.pop(GAME, None)
        for mod in [m for m in list(sys.modules)
                    if m == "worlds.ctr" or m.startswith("worlds.ctr.")]:
            del sys.modules[mod]
        sys.meta_path = [f for f in sys.meta_path
                         if "APWorldModuleFinder" not in type(f).__name__]
        import importlib
        worlds.__path__.insert(0, ctr_src)
        importlib.invalidate_caches()
        sys.path_importer_cache.clear()
        importlib.import_module("worlds.ctr")
    return AutoWorldRegister.world_types[GAME]


class _TolerantUnpickler(pickle.Unpickler):
    """Multidata references core AP classes; substitute anything unresolved so
    the plain slot_data / locations dicts still load."""
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


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    seed_path = sys.argv[1]
    if not os.path.exists(seed_path):
        matches = glob.glob(seed_path)
        seed_path = matches[-1] if matches else seed_path

    ctr = _load_core_and_world()
    from BaseClasses import MultiWorld, CollectionState
    from worlds.AutoWorld import call_all

    multidata = _parse_multidata(seed_path)
    wire = next(sd for sd in multidata["slot_data"].values()
                if isinstance(sd, dict) and sd.get("warp_pad_unlock"))

    options = ctr.options_dataclass(**{
        name: cls.from_any(cls.default)
        for name, cls in ctr.options_dataclass.type_hints.items()
    })
    mw = MultiWorld(1)
    mw.game[1] = GAME
    mw.player_name = {1: "Tracker"}
    mw.set_seed(1)
    mw.generation_is_fake = True
    mw.re_gen_passthrough = {GAME: wire}
    world = ctr(mw, 1)
    mw.worlds = {1: world}
    world.options = options
    for step in GEN_STEPS:
        call_all(mw, step)

    id_to_name = world.item_id_to_name
    # Replay the seed's own placements destined for this player as received items.
    placements = multidata.get("locations", {}).get(1, {})
    state = CollectionState(mw)
    failures = []
    received = 0
    for value in placements.values():
        item_id = value[0] if isinstance(value, (tuple, list)) else value
        player = value[1] if isinstance(value, (tuple, list)) and len(value) > 1 else 1
        flags = value[2] if isinstance(value, (tuple, list)) and len(value) > 2 else 1
        if player != 1 or item_id not in id_to_name:
            continue
        name = id_to_name[item_id]
        try:
            item = mw.create_item(name, 1)
            item.classification = item.classification | flags
            state.collect(item, True)
            received += 1
        except Exception as exc:  # noqa: BLE001 - report, do not abort
            failures.append((name, repr(exc)))

    print(f"replayed {received} received items; failures: "
          f"{failures if failures else 'NONE'}")
    print(f"Key={state.count('Key', 1)} Trophy={state.count('Trophy', 1)} "
          f"Sapphire Relic={state.count('Sapphire Relic', 1)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
