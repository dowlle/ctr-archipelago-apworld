# Universal Tracker diagnostics (issue #29)

Harness for verifying and debugging the world's Universal Tracker support
(`interpret_slot_data` + `ut_can_gen_without_yaml`). These scripts reconstruct
the UT re-generation path in-process so a future session can confirm the
tracker's logic view matches a generating seed, and can capture the real
exception behind the tracker's swallowed "Item name X not able to be created"
warning.

## Setup

All paths are read from environment variables so nothing machine-specific is
committed. Point them at your own checkout:

- `ARCHIPELAGO_ROOT` (required): path to an Archipelago core source tree
  (the folder containing `BaseClasses.py`, `Generate.py`, `worlds/`). Run the
  scripts with a Python that has Archipelago's `requirements.txt` installed.
- `CTR_WORLDS_SRC` (optional): path to this repo's `worlds/` directory. When
  set, the world is force-loaded from source instead of any packaged
  `custom_worlds/ctr.apworld`, so you test working-tree code. Leave unset to
  use whatever the core registers.
- `TRACKER_APWORLD` (optional, `drive_tracker.py` only): path to the installed
  `tracker.apworld`. Defaults to `<ARCHIPELAGO_ROOT>/custom_worlds/tracker.apworld`.

Each script takes the seed's exported multiworld archive (the generator's
output `.zip`, or a raw `.archipelago`) as its first argument and parses the CTR
slot's `slot_data` from it.

## Scripts

- `received_item_repro.py <seed.zip>` - builds the yaml-less UT world from the
  seed's `slot_data` (default options + `re_gen_passthrough` + a fake
  generation), then replays the seed's real item placements as received items
  and asserts every one creates and collects. This exercises the exact path the
  live tracker runs after connecting. Use it to prove (or disprove) a
  received-item regression headlessly.

- `drive_tracker.py <seed.zip>` - drives the real `TrackerCore` from the
  installed `tracker.apworld` end to end (interpret_slot_data -> re_gen_passthrough
  -> generator -> updateTracker) against the seed's `slot_data`, then feeds
  synthetic received items. It patches the tracker's received-item `except`
  in a temporary extracted copy so the otherwise-swallowed traceback is printed.
  Use it to see the true exception when the tracker reports items "not able to
  be created".

## Notes

- The tracker swallows the real error at the received-item loop's `except`
  (it only logs a generic label). `drive_tracker.py`'s patch, or the standalone
  diagnostic tracker build, is the way to surface it.
- A build/version skew between the seed's generating apworld and the tracker's
  loaded apworld produces a different, earlier error ("datapackage is
  incorrect"), not "not able to be created" - worth ruling out first by
  hash-comparing the two `ctr.apworld` files.
