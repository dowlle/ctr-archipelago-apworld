# Draft Contract section: `custom_tracks`

Proposed text for a new section of `CTR Archipelago — slot_data Contract`, plus
the `schema_version` history and additive-key rows it implies. **Draft for
coordinator review — the canonical Contract note is not edited by this branch.**

Branch: `spike/baby-t-park-generation` (apworld), rung 2b of the Baby T Park
Purple Gem Cup event spike. Native counterpart: `spike/baby-t-park-rung1`,
whose `tools/CUSTOM-TRACK-SPIKE.md` describes the `config.ini` parse this block
replaces.

---

## 7j. `custom_tracks` (🔀 candidate, Baby T Park event spike)

A community custom track bound to a Gem Cup destination. When the block is
present, the named cup stops running four retail leg tracks and becomes a
single race on the custom track; winning that race awards the cup's Gem
through the cup's own gem path. Emitted ONLY when the `custom_tracks` YAML
option names a track; omitted entirely when off.

```jsonc
"custom_tracks": {
  "enabled": true,                 // always true when the block is present
  "version": 1,                    // block shape version, see below
  "tracks": [                      // exactly one entry in this build
    {
      "id": "baby-t-park",
      "lev_sha256": "96ad9f74f51a02eafcc207cd02c97052d674c950e0f24b6440a227494a705fe8",
      "vrm_sha256": "2dcaa0fe93359c7ae00fb93842a581210e0dcc2db73f4de43508375834092e83",
      "laps": 7,                   // 1..7
      "host_level_id": 6,          // 0..17, the arcade slot the bytes borrow
      "replaces_cup_level_id": 104, // Purple Gem Cup
      "boxes": true,               // AP boxes allowed on the event race
      "flags": {                   // MEASURED capabilities, all eight required
        "crates": true,
        "ctr_letters": true,
        "relic_crates": true,
        "ai_nav": true,
        "minimap": false,
        "ghosts": false,
        "spawns": 8,               // 1..8
        "checkpoints": 35          // 1..255
      }
    }
  ]
}
```

### Shape

- **A LIST of self-describing entries**, not an id-keyed object. Native's
  seed-config reader looks fields up by name and does not enumerate unknown
  keys, so it finds its track by scanning for the `replaces_cup_level_id` it
  cares about rather than by knowing an id in advance. Exactly one entry today;
  the list exists so a second bound track is a data change, not a wire
  redesign.
- **The cup travels as a LevelID** (`104`), the same currency `warp_pad_map`,
  `warp_pad_unlock` and `gem_cup_legs` already use. The YAML's human-facing
  `replaces: purple_gem_cup` never reaches the wire.
- **`version` is the block's own shape guard**, independent of the seed's
  `schema_version`. `schema_version` answers "may this native trust this seed
  at all"; `version` answers "does it understand this block's fields". Native
  must refuse a `version` it does not know rather than reading fields it cannot
  interpret. `gem_cup_legs` had no equivalent and is the reason this one exists:
  every future custom-track field would otherwise need a full schema bump.
- **Both digests are required and both are the seed's authority on content.**
  The apworld never opens the files. It validates the SHAPE (64 hex digits,
  case-folded to lowercase) and forwards them; native hashes the real bytes and
  stays disarmed on any mismatch, missing file, missing digest or malformed
  digest. A disarmed loader must ALSO leave the cup vanilla — serving retail
  bytes for a race the seed thinks is the custom track is precisely the silent
  wrong-content outcome the digests exist to prevent (native spike doc, "Why
  both files must be hashed").
- **`host_level_id` is a vehicle, not a destination.** A custom track always
  takes over an existing arcade slot (`data.ArcadeDifficulty` is `[18]` and
  `data.metaDataLEV` needs a real entry), but native serves the custom bytes
  only for the redirected cup race, so the host slot's own retail race is
  unaffected in the same seed. The value is a FIXED default (6, matching the
  native loader's documented `config.ini` default) rather than an RNG draw, so
  that turning this option on cannot move any other per-seed decision.
- **`flags` are the describe-step's measured facts, and every one is
  required.** A descriptor that omits a flag is not self-describing, and a
  silently defaulted capability is the same class of plausible-but-wrong state
  the digests guard against. They are inert for generation today; they exist so
  the check rungs above the Gem (boxes, CTR letters, relic) have an honest
  input when they land, and so a native can refuse a track whose measured
  shape it cannot serve.

### Displacement, and what it does to `gem_cup_legs`

This is the load-bearing semantic, and it is a two-sided one:

- **`gem_cup_legs` keeps its complete five-cup table.** The displaced cup's row
  is still four real trophy LevelIDs. It has to be, or the block stops being
  the complete mapping every consumer relies on.
- **Generation logic treats the displaced cup as legging nothing.** The
  apworld resolves the leg map once and then splits it: `world.gem_cup_legs_table`
  is what the wire serializes, and `world.gem_cup_legs` is the same table with
  every displaced cup emptied. The logic map is what feeds the podium-region cup
  entrances (`Regions.create_regions`), the podium rung OR rule
  (`Rules.add_podium_placement_rules`) and the USF finish gate
  (`usf_finish.UsfFinishGate`).

So the displaced row on the wire is a **don't-care that native must actively
not care about**: this block tells native the cup was handed over before it
ever loads a leg, so the row is never read. **Native's solvability verifier
(`ap/ap_verify.c`) reads cup legs too and must take the same view**, or it will
verify a cup this seed does not contain.

Emptying a cup's legs is always safe for solvability: the 2026-08-07 dossier
(§3) established that a cup leg is only ever an ADDITIVE path to a track's
podium rungs — the track's own warp pad stays an independent path — so removing
legs can never orphan a rung. It is also the correct direction for the USF
finish gate: a displaced Purple cup no longer includes a USF-gated leg, so its
Gem correctly stops carrying that term, because the player really can finish
that cup without the boost chain.

### `schema_version`: proposed 8, and a deviation flagged for ruling

An old native on a `custom_tracks` seed would run the retail four-leg cup while
this seed's logic says that cup legs nothing. That is the **reachability-desync
class of the v3 cup destination keys**, exactly the case §8 says the schema
number must move for. So an option-ON seed declares **8**.

> ⚠ **Deviation from the Q28 "always bump, never conditionally" ruling, raised
> deliberately rather than taken quietly.** On this branch the bump is
> CONDITIONAL: schema is 7 with the option off and 8 with it on. Rung 2b's
> neutrality gate is a byte-level A/B against `main` for an option-off seed,
> and an unconditional bump would change every seed on the branch and make that
> proof impossible. Q28's own repair history (§7d, Opus review Blocker 1) is
> the argument against keeping it conditional at landing. **Recommendation: the
> landing makes the bump unconditional at the next release's schema number, and
> this branch's conditional form does not ship.** Coordinator's call.

### Emit / consume

| Role | Where |
|---|---|
| option | `Options.CustomTracks` (`OptionDict`, `supports_weighting = False`, default `{}`); `verify_keys` calls `custom_tracks.validate_custom_tracks` |
| validate | `custom_tracks.validate_custom_tracks`, reached from the YAML roll (`verify_keys`) AND from `generate_early` (`forced_options.raise_if_custom_tracks_descriptor_is_unusable`), so a rolled YAML and a programmatically built world fail identically — the `trap_weights` pattern |
| resolve | `Regions.create_regions` sets `world.custom_tracks` (normalized descriptor) and derives `world.gem_cup_legs` from `world.gem_cup_legs_table` via `custom_tracks.apply_displacement` |
| emit | `worlds/ctr/__init__.py` `fill_slot_data` → `custom_tracks.custom_tracks_to_wire`; `_resolve_gem_cup_legs` now serializes the COMPLETE table (`gem_cup_legs.resolved_gem_cup_legs_table`) |
| UT | `custom_tracks.reconstruct_custom_tracks_from_wire` pins the seed's descriptor in re-generation; `_ut_restore_options` restores the option value from the same reconstruction. Absent block → off, silently (any pre-custom-tracks seed). Present but unreadable → off, with a warning, because that state means the seed DID displace a cup and the tracker cannot tell which |
| native parse | **unbuilt.** `ap/ap_seedcfg.cpp` must gain this block and `CTR_CFG_SCHEMA_KNOWN` must move in lockstep. It replaces the rung-1/2a `[CustomTracks]` `config.ini` section key for key (`custom_track_lev`/`_vrm` paths stay a client-side concern; every other key comes from here) |
| native verifier | `ap/ap_verify.c` must treat a displaced cup as legging nothing (see above) |
| tracker | PopTracker pack unaffected: no new location names, no new item names, no datapackage change |

### Compatibility

- **Parsing-wise inert on an older native** (named-key reads, never enumerates).
- **Reachability-wise NOT additive**, which is what the schema number is for.
  An option-ON seed requires a native that can both parse this block and serve
  the custom track, and the player must additionally have the track's files.
- **No datapackage change.** The displaced cup keeps its region, its single
  `Purple Gem Cup: Gem` location and its `has('Purple CTR Token', 4)` pad rule.
  Nothing is created, nothing is removed, nothing is renamed.

---

## Open item the coordinator has to rule on: `boxes`

`boxes` is emitted with the ruled default `true`, matching the native loader's
`CTR_CT_BOX_ALLOW` default. **The placement data behind that permission does
not exist, and allowing boxes today is actively harmful.** From the rung-2b
mechanism analysis:

- AP-box placement is **table-driven, not instance-driven**. Positions come
  from `AP_PlacementRow { short level, x, y, z, rotY }` (`ap/ap_placement_table.h`),
  compiled in as `AP_EMBEDDED_PLACEMENTS` (241 rows across the 18 retail
  tracks) or overridden by an external `ap-box-placements.json`. Nothing walks
  the LEV's own crate instances — AP boxes are born through `AP_Spawn_AddModel`
  and are deliberately not in the LEV InstDef array. Baby T Park's own 16
  authored crates are therefore **not** usable as AP-box sites without new
  native work.
- `AP_BoxMap_ApTrack` (`ap/ap_box_map.h`) keys on **engine LevelID alone** and
  can only return one of 18 retail indices. For host slot 6 it returns Roo's
  Tubes. `AP_PlacementRow` has no field that could say "this row belongs to the
  custom track, not the retail track on the same slot".
- So with `boxes: true` the event race spawns **Roo's Tubes' authored boxes at
  Roo's Tubes coordinates on Baby T Park geometry** — cosmetically wrong,
  largely unreachable, and a **logic hazard**: those are live
  `Roo's Tubes: Item Box N` locations gated by that track's pad access, and the
  ALLOW branch deliberately bypasses the pad gate for the event race
  (`ap/ap_boxes.c`), so a player who reaches the Purple Gem Cup but not Roo's
  Tubes' physical pad can send Roo's Tubes checks out of logic.

**Recommendation: the event seed sets `boxes: false` (native
`CTR_CT_BOX_DENY`) until a custom-slot box identity exists.** The wire field is
kept, and kept defaulting to the ruled ALLOW, so the ruling is represented
honestly and flipping it is a YAML edit rather than a code change.

Unblocking it properly needs, on the native side, a track-key field on
`AP_PlacementRow`/`AP_EmbeddedPlacement` and a matching filter term in
`AP_BoxMap_BuildSet`; a custom-track arm in `AP_BoxMap_ApTrack` and in the
connect-time scout-code list; and an authoring session on the track once it
loads. On the apworld side it needs a new `LocationClass` for custom-slot boxes
registering its frozen superset unconditionally — **that one IS a datapackage
change** and has to ride a bump. Estimated 3–5 days across both sides, hard
gated on the track loading first.

---

## Rows this implies elsewhere in the Contract

**§8 `schema_version` history** — a new row:

| v | Shape | Introduced |
|---:|---|---|
| 8 | **custom tracks**: conditional top-level `custom_tracks` block (§7j) binding a community track to a Gem Cup destination and DISPLACING that cup's retail legs in logic. Bump is conditional on this branch — see the deviation note in §7j | 🔀 candidate, apworld branch `spike/baby-t-park-generation` |

**§8 additive-keys table** — no row. This is a shape/reachability change, not an
additive key.

**§10 emit/consume anchors** — the rows in the emit/consume table above fold in.
