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
import json
import pkgutil

from .location_class import LocationClass

# Additive block for the 270 item-box checks, stride 15 per track.
ITEM_BOX_CODE_BASE = 35014000

#: Per-track slot ceiling. The curation model's "roughly 15 candidate slots per
#: track", taken as the hard naming ceiling per the 16:23 ruling. Frozen: it is
#: the per-track stride, so changing it would renumber every track after the
#: first.
SLOTS_PER_TRACK = 15


def _box_tracks():
    """The 18 box tracks in canonical (Sapphire-trial code) order, read from
    data/locations.json so this block's codes/order can never drift. The box set
    is the 16 trophy tracks plus the two trial tracks, which is exactly the set
    that carries Time Trial locations -- the same canon relic_perfect.py uses."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/locations.json").decode("utf-8")
    )
    tt = [(loc["code"], loc["region"]) for loc in data
          if loc["name"].endswith(": Sapphire Time Trial") and loc["code"] is not None]
    return [region for _code, region in sorted(tt)]


# Canonical, stable track order (module import time). 18 entries.
BOX_TRACKS = _box_tracks()


def _track_level_ids():
    """{track region name -> native LevelID} for the 18 box tracks, read from
    data/warp_pad_ids.json (the single LevelID source) so the wire keys can
    never drift from the pad canon."""
    data = json.loads(
        pkgutil.get_data(__package__, "data/warp_pad_ids.json").decode("utf-8")
    )
    return {pad_name[: -len(" Warp Pad")]: meta["level_id"]
            for pad_name, meta in data["pads"].items()
            if pad_name[: -len(" Warp Pad")] in set(BOX_TRACKS)}


#: {track region name -> native LevelID}, 18 entries.
TRACK_LEVEL_IDS = _track_level_ids()

#: Authored placements per track (FINAL 241 file; re-verified 2026-08-11).
#: Slots placed+1..15 stay inert this curation generation.
PLACED_COUNTS = {
    "Dingo Canyon": 15, "Dragon Mines": 13, "Blizzard Bluff": 14,
    "Crash Cove": 10, "Tiger Temple": 10, "Papu's Pyramid": 12,
    "Roo's Tubes": 11, "Hot Air Skyway": 15, "Sewer Speedway": 15,
    "Mystery Caves": 13, "Cortex Castle": 14, "N. Gin Labs": 15,
    "Polar Pass": 15, "Oxide Station": 14, "Coco Park": 10,
    "Tiny Arena": 15, "Slide Coliseum": 15, "Turbo Track": 15,
}
assert sum(PLACED_COUNTS.values()) == 241

#: `shortcut_knowledge` tiers (Choice values).
SK_EASY, SK_MEDIUM, SK_HARD = 0, 1, 2

#: Slots REMOVED below a knowledge tier, keyed (track, slot) -> minimum tier
#: that creates the slot. easy removes all 12 (both respawn boxes ruled medium,
#: 2026-08-10 15:00); medium additionally removes the 5 hard-tier slots (ruled
#: 08-10 19:53: a hard slot left in a medium seed would be unreachable).
SK_REQUIRED_TIER = {
    ("Tiger Temple", 5): SK_MEDIUM,
    ("Coco Park", 7): SK_MEDIUM,        # respawn box, ruled medium
    ("Dragon Mines", 2): SK_MEDIUM,     # respawn box, ruled medium
    ("Sewer Speedway", 2): SK_MEDIUM,
    ("Sewer Speedway", 3): SK_MEDIUM,
    ("Papu's Pyramid", 6): SK_MEDIUM,
    ("Papu's Pyramid", 12): SK_MEDIUM,
    ("Papu's Pyramid", 7): SK_HARD,
    ("Papu's Pyramid", 10): SK_HARD,
    ("Polar Pass", 9): SK_HARD,         # ruled hard TIER (ruled 08-10 15:07)
    ("Hot Air Skyway", 8): SK_HARD,
    ("Oxide Station", 6): SK_HARD,
}

#: Item-term rules for gated slots, keyed (track, slot) -> (boost_min, stats).
#: `boost_min` is the required received `Progressive Boost` count (0 = no boost
#: term); `stats` = True requires one received copy of EACH stat chain (the
#: hard-tier general rule). The `shortcut_knowledge` term is CREATION-side
#: (SK_REQUIRED_TIER above), never a state term: a slot that exists in the seed
#: already satisfies its knowledge tier. Every term is vacuous while the option
#: that creates its items is off (spec 2.2) -- see Rules.add_item_box_rules.
#: The Tiger Temple door's itemsanity-conditional weapon set is special-cased
#: there, not here.
#:
#: ⚠ The three UNCAPTURED Hot Air Skyway slots (4, 6, 7) carry the ruled
#: conservative `Progressive Boost >= 2` DEFAULT (re-arm amendment + 08-10
#: 19:53 ruling), pending an in-game marking pass with exact evidence --
#: over-restriction cannot create an unbeatable seed, free-reach could.
BOX_RULES = {
    ("Crash Cove", 4): (1, False),
    ("Crash Cove", 9): (1, False),
    ("Crash Cove", 10): (1, False),
    ("Sewer Speedway", 2): (1, False),
    ("Sewer Speedway", 3): (1, False),
    ("Papu's Pyramid", 6): (1, False),
    ("Papu's Pyramid", 12): (1, False),
    ("Papu's Pyramid", 7): (1, True),
    ("Papu's Pyramid", 10): (1, True),
    ("Dragon Mines", 2): (0, False),    # respawn: SK creation term only
    ("Coco Park", 7): (0, False),       # respawn: SK creation term only
    ("Polar Pass", 14): (1, False),
    ("Polar Pass", 15): (1, False),
    ("Polar Pass", 9): (1, True),
    ("Cortex Castle", 10): (1, False),
    ("Cortex Castle", 11): (2, False),
    ("N. Gin Labs", 4): (2, False),
    ("N. Gin Labs", 5): (2, False),
    ("N. Gin Labs", 6): (2, False),
    ("N. Gin Labs", 7): (2, False),
    ("N. Gin Labs", 8): (2, False),
    ("N. Gin Labs", 9): (2, False),
    ("N. Gin Labs", 14): (2, False),
    ("N. Gin Labs", 15): (2, False),
    ("Oxide Station", 6): (0, True),    # NO boost term: pads are ladder-exempt
    ("Oxide Station", 13): (2, False),
    ("Hot Air Skyway", 1): (2, False),
    ("Hot Air Skyway", 2): (2, False),
    ("Hot Air Skyway", 3): (2, False),
    ("Hot Air Skyway", 4): (2, False),  # UNCAPTURED, ruled conservative default
    ("Hot Air Skyway", 5): (2, False),
    ("Hot Air Skyway", 6): (2, False),  # UNCAPTURED, ruled conservative default
    ("Hot Air Skyway", 7): (2, False),  # UNCAPTURED, ruled conservative default
    ("Hot Air Skyway", 8): (2, True),
    ("Hot Air Skyway", 9): (2, False),
    ("Hot Air Skyway", 13): (2, False),
    ("Hot Air Skyway", 14): (2, False),
    ("Hot Air Skyway", 15): (2, False),
    # Slot 1 = level_id 15, pos (-7846, 390, -6907): unbreakable without boost,
    # found in logic and stuck in the 2026-08-12 live session (ruled
    # 21:39). Boost, not USF -- the report says "boost".
    ("Tiny Arena", 1): (1, False),
    ("Tiger Temple", 5): (0, False),    # itemsanity-conditional door, Rules.py
}

#: Slots the ledger EXPLICITLY cleared as no-gate (reachable backwards from the
#: finish). Listed so nobody "fixes" them into gates later; carrying no rule is
#: their ruled state, not an omission.
EXPLICIT_NO_GATE = frozenset({
    ("Cortex Castle", 12), ("Cortex Castle", 13),
    ("Oxide Station", 4), ("Oxide Station", 7), ("Oxide Station", 14),
    ("Hot Air Skyway", 10), ("Hot Air Skyway", 11), ("Hot Air Skyway", 12),
})

#: The seven Tiger Temple door openers (ledger set, verbatim): thrown-forward
#: or protective weapons that can break the door. TNT is out (cannot be thrown
#: forward); Warpball, Turbo and N. Tropy Clock are not openers. The x3
#: variants count as their own names per the 08-10 family ruling.
TIGER_TEMPLE_DOOR_OPENERS = (
    "Bomb", "Bomb x3", "Missile", "Missile x3", "Beaker", "Shield Bubble",
    "Mask",
)


class ItemBoxLocationClass(LocationClass):
    """The 270 authored item-box checks as a `LocationClass` (#176)."""

    key = "item_boxes"
    display_name = "Item Box Checks"
    code_blocks = (ITEM_BOX_CODE_BASE,)

    def all_locations(self):
        return [(self.location_name(track, slot + 1),
                 ITEM_BOX_CODE_BASE + ti * SLOTS_PER_TRACK + slot,
                 track)
                for ti, track in enumerate(BOX_TRACKS)
                for slot in range(SLOTS_PER_TRACK)]

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
        out = []
        for track in BOX_TRACKS:
            for slot in range(1, PLACED_COUNTS[track] + 1):
                if SK_REQUIRED_TIER.get((track, slot), SK_EASY) > tier:
                    continue
                out.append(self.location_name(track, slot))
        return out

    def slot_code(self, track: str, slot: int) -> int:
        """AP location code for a track's 1-based slot."""
        return (ITEM_BOX_CODE_BASE
                + BOX_TRACKS.index(track) * SLOTS_PER_TRACK + (slot - 1))

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
