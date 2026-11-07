"""Authored item-box locations (#109).

WHAT THIS CLASS CHECKS AND WHERE THE SIGNAL COMES FROM. One check per authored
item-box position on a track. The boxes are position-keyed and mode-agnostic per
the 2026-08-06 positioning design: a box sits at a place, not at a race type, so
the same physical box is the same check whichever race mode is running on that
track. Breaking it sends the check and grants nothing locally.

WHO OWNS THE SEMANTICS. The apworld owns the names, the per-seed subset (a #179
elastic count) and the difficulty-tier logic exclusions; native owns the spawner,
the collision answer and the loader. Neither half is built here.

THE NAME COUNT IS A CEILING, NOT A PLACEMENT (ruled 2026-08-10 16:23). This block
freezes the FULL 18 tracks x 15 slots = 270-name ceiling, index-based per track,
NOT the 241 boxes currently authored. Future box work -- the pending curation
pass, lap-skip additions, curation swaps -- moves which slots a seed creates and
never needs another datapackage bump. The 241 authored placements live in
`Development/Placement Backups/2026-08-10 154700 -- AP box placements -- FINAL
241 across 18 tracks (logic survey complete).json` in the vault and are the
placement truth; this module is the name truth, and the two are deliberately
decoupled.

The 18 box tracks are the 16 adventure trophy tracks plus Slide Coliseum and
Turbo Track -- the boxes-on-all-race-types ruling (12:01) extended by the
boxes-in-relic-races ruling (13:58). That is the same 18-track set the relic
races use, and the same 18 tracks the placement file carries.

DATAPACKAGE STABILITY. This class claims the additive block 35014000, stride 15
per track in BOX_TRACKS order, and registers all 270 names UNCONDITIONALLY.
35014xxx was recorded as free by #177's own issue body; the block is clear of the
static 35011xxx-35013xxx families, the relic-perfect 35012400 block, the
lettersanity 35012500 block, the podium 35015000 / 35015100 blocks and the
itemsanity 35016xxx family.

FROZEN-NAME WARNING. These names ride the single 0.2.0 datapackage bump (#177).
After that bump they are permanent, and their ids can never move.

SEATING (#109 apworld half, 2026-08-11). `box_locations` on creates, per track,
slots 1..placed (PLACED_COUNTS) minus the slots the seed's `shortcut_knowledge`
tier removes (SK_REMOVED_AT). Slot N is defined as the Nth placement carrying
that track in PLACEMENT-FILE ORDER, COUNTED ACROSS THE ENTIRE FILE -- five
tracks are interleaved (two runs each: Crash Cove, Roo's Tubes, Hot Air Skyway,
Mystery Caves, Oxide Station), so grouping-by-track-then-numbering mis-seats 27
boxes. The table below was derived in the 2026-08-10 seating spec and
independently re-verified against the FINAL placement file (counts, positions
AND interleaving-aware slot numbers) before this build. Placement truth:
`Development/Placement Backups/2026-08-10 154700 -- AP box placements -- FINAL
241 across 18 tracks (logic survey complete).json` (vault). Native must count
slots the same way; `placement_counts` on the wire is the desync guard.
"""

from . import box_spots, destinations
from .location_class import LocationClass

# Additive block for the 270 item-box checks, stride 15 per track.
ITEM_BOX_CODE_BASE = 35014000
#: The alpha3 data package: Item Box 16 to 50 per track, stride 35, in
#: BOX_TRACKS order (35014300 to 35014929), so a track has 50 permanent box
#: numbers (ruled 2026-11-06).
SPOT_CODE_BASE = 35014300
SPOT_NUMBERS_PER_TRACK = 50
SPOT_EXTRA_PER_TRACK = SPOT_NUMBERS_PER_TRACK - 15

#: Per-track slot ceiling. The curation model's "roughly 15 candidate slots per
#: track", taken as the hard naming ceiling per the 16:23 ruling. Frozen: it is
#: the per-track stride, so changing it would renumber every track after the
#: first.
SLOTS_PER_TRACK = 15


# Canonical, stable track order (module import time). 18 entries, read from
# data/locations.json through the destination table so this block's
# codes/order can never drift. The box set is the 16 trophy tracks plus the
# two trial tracks, which is exactly the set that carries Time Trial
# locations -- the same canon relic_perfect.py uses.
BOX_TRACKS = destinations.tracks_with_suffix(": Sapphire Time Trial")

#: {track region name -> native LevelID}, 18 entries, from the destination
#: table (which reads data/warp_pad_ids.json, the single LevelID source).
TRACK_LEVEL_IDS = destinations.level_ids_for(BOX_TRACKS)

#: `shortcut_knowledge` tiers (Choice values).
SK_EASY, SK_MEDIUM, SK_HARD = 0, 1, 2

# Hand-placed box spots (A3-14, ruled 2026-11-06): the per-box tables below are
# no longer literals. They are derived from the 18 built-in retail spot files
# (data/box_spots/retail, box_spots.py), which carry the same 241 boxes, numbers
# and logic; test/fixtures/retail_box_tables.json keeps the old literals and the
# conversion test rebuilds them from the files.

#: Built-in placements per track (the 2026-08-10 FINAL 241 file). A track's
#: community spots, when its file has any, are numbered from 16.
PLACED_COUNTS = dict(box_spots.RETAIL_PLACED)
destinations.check_keys(PLACED_COUNTS, BOX_TRACKS, "item_boxes.PLACED_COUNTS")
assert sum(PLACED_COUNTS.values()) == 241

#: (track, number) -> minimum `shortcut_knowledge` tier that creates the box
#: (the spot's `shortcut` field). easy removes 12 built-in boxes (both respawn
#: boxes ruled medium, 2026-08-10 15:00); medium additionally removes the 5
#: hard-tier boxes (ruled 08-10 19:53: a hard box left in a medium seed would be
#: unreachable).
SK_REQUIRED_TIER = dict(box_spots.RETAIL_TIERS)

#: Item-term rules for gated boxes, (track, number) -> (boost_min, stats).
#: `boost_min` is the spot's `needs` as a received `Progressive Boost` count
#: (0 = no boost term); `stats` = True (a hard-shortcut spot) requires one
#: received copy of EACH stat chain (the hard-tier general rule). The
#: `shortcut_knowledge` term is CREATION-side (SK_REQUIRED_TIER above), never a
#: state term. Every term is vacuous while the option that creates its items is
#: off (spec 2.2). The Tiger Temple door's itemsanity-conditional weapon set is
#: the spot's `door` field (TIGER_TEMPLE_DOOR_BOXES).
#:
#: The three UNCAPTURED Hot Air Skyway boxes (4, 6, 7) carry the ruled
#: conservative `needs: usf` default (re-arm amendment + 08-10 19:53 ruling;
#: values confirmed, ruled 2026-10-29).
BOX_RULES = dict(box_spots.RETAIL_RULES)

#: Boxes the ledger EXPLICITLY cleared as no-gate (reachable backwards from the
#: finish), the spots' `no_gate` field. Listed so nobody "fixes" them into gates
#: later; carrying no rule is their ruled state, not an omission.
EXPLICIT_NO_GATE = box_spots.RETAIL_NO_GATE

#: The boxes behind the Tiger Temple stone door (the spots' `door` field).
TIGER_TEMPLE_DOOR_BOXES = tuple(box_spots.RETAIL_DOORS.get("tiger_temple", ()))

#: The seven Tiger Temple door openers (ledger set, verbatim): thrown-forward
#: or protective weapons that can break the door. TNT is out (cannot be thrown
#: forward); Warpball, Turbo and N. Tropy Clock are not openers. The x3
#: variants count as their own names per the 08-10 family ruling.
TIGER_TEMPLE_DOOR_OPENERS = (
    "Bomb", "Bomb x3", "Missile", "Missile x3", "Beaker", "Shield Bubble",
    "Mask",
)

# Every per-box table above is keyed by a destination key from the shared table.
for _table in (SK_REQUIRED_TIER, BOX_RULES):
    destinations.require_all(track for track, _slot in _table)
destinations.require_all(track for track, _slot in EXPLICIT_NO_GATE)
del _table


class ItemBoxLocationClass(LocationClass):
    """The 270 authored item-box checks as a `LocationClass` (#176)."""

    key = "item_boxes"
    display_name = "Item Box Checks"
    code_blocks = (ITEM_BOX_CODE_BASE, SPOT_CODE_BASE)

    def all_locations(self):
        return ([(self.location_name(track, slot + 1),
                  ITEM_BOX_CODE_BASE + ti * SLOTS_PER_TRACK + slot,
                  track)
                 for ti, track in enumerate(BOX_TRACKS)
                 for slot in range(SLOTS_PER_TRACK)]
                + [(self.location_name(track, n), self.slot_code(track, n), track)
                   for track in BOX_TRACKS
                   for n in range(SLOTS_PER_TRACK + 1, SPOT_NUMBERS_PER_TRACK + 1)])

    def location_name(self, track: str, slot: int) -> str:
        """AP location name for a track's box slot, e.g.
        'Crash Cove: Item Box 1'. `slot` is 1-based because the name is
        player-visible in hints and trackers and a 0-based first box would read
        as a bug; the CODE is 0-based off the block, as everywhere else."""
        return f"{track}: Item Box {slot}"

    def created_location_names(self, options):
        """The active slots for this seed: per track, slots 1..placed, minus
        the slots the seed's `shortcut_knowledge` tier removes (removal, not
        exclusion -- a removed slot is never created, the #28/#171 shape).
        229 at easy (default), 236 at medium, 241 at hard."""
        toggle = getattr(options, "box_locations", None)
        if toggle is None or not bool(toggle.value):
            return []
        tier = int(getattr(options, "shortcut_knowledge").value)
        from .cortex_vortex import dropped_track
        # A destination the Cortex Vortex track dropped takes its boxes with
        # it (Cortex Vortex itself has none).
        dropped = dropped_track(options)
        out = []
        for track in BOX_TRACKS:
            if track == dropped:
                continue
            for slot in range(1, PLACED_COUNTS[track] + 1):
                if SK_REQUIRED_TIER.get((track, slot), SK_EASY) > tier:
                    continue
                out.append(self.location_name(track, slot))
        return out

    def slot_code(self, track: str, slot: int) -> int:
        """AP location code for a track's 1-based slot (box number 1 to 50)."""
        index = BOX_TRACKS.index(track)
        if slot > SLOTS_PER_TRACK:
            return SPOT_CODE_BASE + index * SPOT_EXTRA_PER_TRACK + (slot - SLOTS_PER_TRACK - 1)
        return ITEM_BOX_CODE_BASE + index * SLOTS_PER_TRACK + (slot - 1)

    def wire_block(self, options):
        """The `item_box_checks` slot_data block (call only when the toggle is
        on). All 18 tracks always present, keyed by native LevelID as a decimal
        string; each value a fixed 15-entry array of AP location codes with -1
        for a slot not live this seed (beyond the placed count OR removed by
        the knowledge tier -- native's behaviour is identical for both, so the
        two causes are deliberately collapsed). `placement_counts` carries the
        authored per-track counts so native can detect a placement-file desync
        in one comparison at parse time instead of silently mis-seating every
        rule after an off-by-one."""
        created = set(self.created_location_names(options))
        locations = {}
        for track in BOX_TRACKS:
            row = []
            for slot in range(1, SLOTS_PER_TRACK + 1):
                live = self.location_name(track, slot) in created
                row.append(self.slot_code(track, slot) if live else -1)
            locations[str(TRACK_LEVEL_IDS[track])] = row
        return {
            "enabled": True,
            "placement_counts": {str(TRACK_LEVEL_IDS[t]): PLACED_COUNTS[t]
                                 for t in BOX_TRACKS},
            "locations": locations,
        }


#: The registered item-box class. `Locations.py` registers this instance.
ITEM_BOX_CLASS = ItemBoxLocationClass()
