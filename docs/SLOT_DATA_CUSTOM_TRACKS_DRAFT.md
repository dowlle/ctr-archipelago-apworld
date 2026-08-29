# Alpha6 contract: `custom_tracks`

This file mirrors the Alpha6 candidate implemented by the combined native and
apworld worktrees on 2026-08-29. The vault's canonical slot-data Contract is the
authority; this copy travels with the apworld for code review.

## Wire block

The block is omitted when the player's YAML does not opt into a custom track.
Every Alpha6 seed declares `schema_version: 8` regardless of block presence.

```jsonc
"custom_tracks": {
  "enabled": true,
  "version": 2,
  "tracks": [
    {
      "id": "baby-t-park",
      "package_uuid": "60d5a8a8-b69a-4f6a-a0d8-9a43d91e3f2e",
      "package_version": "1.0.0",
      "minimum_client_version": "0.2.0-alpha6",
      "minimum_apworld_version": "0.2.0-alpha6",
      "lev_sha256": "96ad9f74f51a02eafcc207cd02c97052d674c950e0f24b6440a227494a705fe8",
      "vrm_sha256": "2dcaa0fe93359c7ae00fb93842a581210e0dcc2db73f4de43508375834092e83",
      "navigation": {
        "uuid": "898a9315-693f-4ed3-b6a0-fbe50db8bc40",
        "revision": 1
      },
      "laps": 7,
      "host_level_id": 6,
      "replaces_cup_level_id": 104,
      "boxes": false,
      "flags": {
        "crates": true,
        "ctr_letters": true,
        "relic_crates": true,
        "ai_nav": true,
        "minimap": false,
        "ghosts": false,
        "spawns": 8,
        "checkpoints": 35
      }
    }
  ]
}
```

Alpha6 accepts exactly one entry and exactly the compiled Baby T Park identity.
The apworld compares package UUID, package version, minimum compatible versions,
both hashes, navigation UUID and revision, lap count, destination and measured
capabilities against its registry. Native repeats the same comparison before it
accepts local files. YAML can select approved content, but cannot mint a package
the shipped client does not recognize.

`host_level_id` defaults to 6 and remains a loading vehicle rather than a
logical destination. `boxes` defaults to false and true is rejected. Custom AP
box identities and placements do not exist in Alpha6.

## Manager and preflight

The public package contains no third-party track files. The player supplies the
two files under `assets/tracks/baby-t-park/original/`. Manager-light hashes them,
recognizes the approved identity, and creates or repairs its own local manifest.
It can copy or save the complete YAML fragment only after the package is Ready.

The AP connection is allowed to read slot data before content is Ready. If the
seed requires Baby T Park, native shows a persistent Content Required state and
blocks the displaced cup entry. Rescan or Verify can repair the manifest and arm
the same connected seed without regeneration or restart. The loader hashes both
files again at event entry and disarms on drift rather than loading retail bytes
for a seed whose logic expects the custom race.

## Displacement

Baby T Park replaces destination 104, the Purple Gem Cup, as one seven-lap race.
The wire's `gem_cup_legs` table remains the complete five-cup table for its own
contract. Generation logic empties the displaced cup's logical legs so those
retail tracks do not grant extra podium access or USF terms. Native skips retail
cup-leg loading and reward glow for the displaced cup.

Served custom bytes also have no retail podium identity. Baby T Park therefore
cannot emit Roo's Tubes position-rung checks merely because level 6 is its host
vehicle. Genuine custom-track rungs require future datapackage identities.

## Emit and consume

| Role | Owner |
|---|---|
| Validate and normalize | `worlds/ctr/custom_tracks.py` |
| Emit and UT restore | `worlds/ctr/__init__.py`, `worlds/ctr/custom_tracks.py` |
| Native parse | `ap/ap_seedcfg.cpp`, wire version 2 |
| Package preflight | `platform/native_custom_track_manager.c`, `ap/ap_hooks.c` |
| Event-entry gate | `game/232/AH_WarpPad.c`, `ap/ap_hooks.c` |
| Manager screen | `game/230/MM_ConfigMenu.c` |

There is no datapackage change. The displaced cup keeps its existing Purple Gem
location and reward. The custom race creates no new item or location names.
