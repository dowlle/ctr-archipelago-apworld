"""
RAM address and bit-flag tables for Crash Team Racing NTSC-U (SCUS-94426).

Derived from:
- CTR-tools/CTR-ModSDK/include/namespace_Memcard.h (AdvProgress struct + bit layout)
- CTR-tools/CTR-ModSDK/symbols/syms1006.txt (sdata_static at 0x8008BEC4)
- icebound777/CTR-Randomizer/src/saveslot_defines.h (rewards[] array packing)
- icebound777/Archipelago-Crash-Team-Racing/worlds/ctr/data/locations.json

The player's Adventure Mode progress lives in the AdvProgress struct at
PSX virtual address 0x8008FBA4 (BizHawk MainRAM offset 0x8FBA4). The first
24 bytes are rewards[6], a bit array where each bit means "player has done X".
"""

# PSX user RAM maps 1:1 to BizHawk's "MainRAM" domain starting at offset 0.
# So PSX virt 0x8008FBA4 -> MainRAM offset 0x8FBA4.
ADVPROGRESS_BASE = 0x8FBA4
REWARDS_BYTES = 24  # rewards[6] = 6 uint32

# SaveSlot 4 is Icebound's designated multiworld item inventory. Its rewards[]
# is byte-packed counters (not bit flags), and external tools (us) write
# received items here. See [[2026-04-24 — Reconciliation — addresses.py vs
# RAMLocations.md]] section 3 for the full layout.
SAVESLOT_4_BASE = 0x993D8

# Save-safe gate. Only read/write SaveSlot data when this 4-byte int reads
# exactly 0x00000001. Other values indicate cutscenes, menu transitions, or
# save/load operations where writes can corrupt state.
SAVE_SAFE_GATE = 0x8D984

# SaveSlot 2/4 byte-packed `rewards[]` layout. Counter writes for AP
# multiworld items go here, gated on SAVE_SAFE_GATE == 1.
#
# rewards[0] (4 bytes, uint32): num trophies
# rewards[1] (4 bytes, uint32): num keys
# rewards[2] byte 0: num red CTR tokens
# rewards[2] byte 1: num green CTR tokens
# rewards[2] byte 2: num blue CTR tokens
# rewards[2] byte 3: num yellow CTR tokens
# rewards[3] byte 0: num purple CTR tokens
# rewards[4] byte 0: num sapphire relics
# rewards[4] byte 1: num gold relics
# rewards[4] byte 2: num platinum relics
# rewards[5] byte 0: num gems (0..5)
# rewards[5] & 0x100:  flag red gem
# rewards[5] & 0x200:  flag green gem
# rewards[5] & 0x400:  flag blue gem
# rewards[5] & 0x800:  flag yellow gem
# rewards[5] & 0x1000: flag purple gem

# For ROM validation, the PSX BIOS + game boot leaves a recognizable executable
# header. For MVP we accept any PSX ROM and warn in the log.
# TODO: distinguish CTR vs other PSX titles via BIOS memcard ID.

# Global save-data context (sdata_static) - per syms1006
SDATA_STATIC = 0x8BEC4


# (word_index, bit_mask) -> location name (matching icebound's locations.json)
# word_index is the index into rewards[], bit_mask is the PSX uint32 bit.
# After reading 24 bytes at ADVPROGRESS_BASE, we interpret them as 6 little-endian
# uint32s and then for each entry below, check whether word[word_index] & bit_mask != 0.
LOCATION_BITS: dict[tuple[int, int], str] = {
    # ──── rewards[0] at 0x8008FBA4 ─────────────────────────────────────────
    # Adventure Mode trophies (16 tracks)
    (0, 0x00000040): "Dingo Canyon: Trophy Race",
    (0, 0x00000080): "Dragon Mines: Trophy Race",
    (0, 0x00000100): "Blizzard Bluff: Trophy Race",
    (0, 0x00000200): "Crash Cove: Trophy Race",
    (0, 0x00000400): "Tiger Temple: Trophy Race",
    (0, 0x00000800): "Papu's Pyramid: Trophy Race",
    (0, 0x00001000): "Roo's Tubes: Trophy Race",
    (0, 0x00002000): "Hot Air Skyway: Trophy Race",
    (0, 0x00004000): "Sewer Speedway: Trophy Race",
    (0, 0x00008000): "Mystery Caves: Trophy Race",
    (0, 0x00010000): "Cortex Castle: Trophy Race",
    (0, 0x00020000): "N. Gin Labs: Trophy Race",
    (0, 0x00040000): "Polar Pass: Trophy Race",
    (0, 0x00080000): "Oxide Station: Trophy Race",
    (0, 0x00100000): "Coco Park: Trophy Race",
    (0, 0x00200000): "Tiny Arena: Trophy Race",
    # Sapphire Relics (first 10 of 18, continued in word 1)
    (0, 0x00400000): "Dingo Canyon: Sapphire Time Trial",
    (0, 0x00800000): "Dragon Mines: Sapphire Time Trial",
    (0, 0x01000000): "Blizzard Bluff: Sapphire Time Trial",
    (0, 0x02000000): "Crash Cove: Sapphire Time Trial",
    (0, 0x04000000): "Tiger Temple: Sapphire Time Trial",
    (0, 0x08000000): "Papu's Pyramid: Sapphire Time Trial",
    (0, 0x10000000): "Roo's Tubes: Sapphire Time Trial",
    (0, 0x20000000): "Hot Air Skyway: Sapphire Time Trial",
    (0, 0x40000000): "Sewer Speedway: Sapphire Time Trial",
    (0, 0x80000000): "Mystery Caves: Sapphire Time Trial",

    # ──── rewards[1] at 0x8008FBA8 ─────────────────────────────────────────
    # Remaining Sapphire Relics (8)
    (1, 0x00000001): "Cortex Castle: Sapphire Time Trial",
    (1, 0x00000002): "N. Gin Labs: Sapphire Time Trial",
    (1, 0x00000004): "Polar Pass: Sapphire Time Trial",
    (1, 0x00000008): "Oxide Station: Sapphire Time Trial",
    (1, 0x00000010): "Coco Park: Sapphire Time Trial",
    (1, 0x00000020): "Tiny Arena: Sapphire Time Trial",
    (1, 0x00000040): "Slide Coliseum: Sapphire Time Trial",
    (1, 0x00000080): "Turbo Track: Sapphire Time Trial",
    # Gold Relics (18)
    (1, 0x00000100): "Dingo Canyon: Gold Time Trial",
    (1, 0x00000200): "Dragon Mines: Gold Time Trial",
    (1, 0x00000400): "Blizzard Bluff: Gold Time Trial",
    (1, 0x00000800): "Crash Cove: Gold Time Trial",
    (1, 0x00001000): "Tiger Temple: Gold Time Trial",
    (1, 0x00002000): "Papu's Pyramid: Gold Time Trial",
    (1, 0x00004000): "Roo's Tubes: Gold Time Trial",
    (1, 0x00008000): "Hot Air Skyway: Gold Time Trial",
    (1, 0x00010000): "Sewer Speedway: Gold Time Trial",
    (1, 0x00020000): "Mystery Caves: Gold Time Trial",
    (1, 0x00040000): "Cortex Castle: Gold Time Trial",
    (1, 0x00080000): "N. Gin Labs: Gold Time Trial",
    (1, 0x00100000): "Polar Pass: Gold Time Trial",
    (1, 0x00200000): "Oxide Station: Gold Time Trial",
    (1, 0x00400000): "Coco Park: Gold Time Trial",
    (1, 0x00800000): "Tiny Arena: Gold Time Trial",
    (1, 0x01000000): "Slide Coliseum: Gold Time Trial",
    (1, 0x02000000): "Turbo Track: Gold Time Trial",
    # Platinum Relics (first 6, continued in word 2)
    (1, 0x04000000): "Dingo Canyon: Platinum Time Trial",
    (1, 0x08000000): "Dragon Mines: Platinum Time Trial",
    (1, 0x10000000): "Blizzard Bluff: Platinum Time Trial",
    (1, 0x20000000): "Crash Cove: Platinum Time Trial",
    (1, 0x40000000): "Tiger Temple: Platinum Time Trial",
    (1, 0x80000000): "Papu's Pyramid: Platinum Time Trial",

    # ──── rewards[2] at 0x8008FBAC ─────────────────────────────────────────
    # Remaining Platinum Relics (12)
    (2, 0x00000001): "Roo's Tubes: Platinum Time Trial",
    (2, 0x00000002): "Hot Air Skyway: Platinum Time Trial",
    (2, 0x00000004): "Sewer Speedway: Platinum Time Trial",
    (2, 0x00000008): "Mystery Caves: Platinum Time Trial",
    (2, 0x00000010): "Cortex Castle: Platinum Time Trial",
    (2, 0x00000020): "N. Gin Labs: Platinum Time Trial",
    (2, 0x00000040): "Polar Pass: Platinum Time Trial",
    (2, 0x00000080): "Oxide Station: Platinum Time Trial",
    (2, 0x00000100): "Coco Park: Platinum Time Trial",
    (2, 0x00000200): "Tiny Arena: Platinum Time Trial",
    (2, 0x00000400): "Slide Coliseum: Platinum Time Trial",
    (2, 0x00000800): "Turbo Track: Platinum Time Trial",
    # CTR Token Challenges (16 tracks, token color per track is fixed in vanilla)
    (2, 0x00001000): "Dingo Canyon: CTR Token Challenge",
    (2, 0x00002000): "Dragon Mines: CTR Token Challenge",
    (2, 0x00004000): "Blizzard Bluff: CTR Token Challenge",
    (2, 0x00008000): "Crash Cove: CTR Token Challenge",
    (2, 0x00010000): "Tiger Temple: CTR Token Challenge",
    (2, 0x00020000): "Papu's Pyramid: CTR Token Challenge",
    (2, 0x00040000): "Roo's Tubes: CTR Token Challenge",
    (2, 0x00080000): "Hot Air Skyway: CTR Token Challenge",
    (2, 0x00100000): "Sewer Speedway: CTR Token Challenge",
    (2, 0x00200000): "Mystery Caves: CTR Token Challenge",
    (2, 0x00400000): "Cortex Castle: CTR Token Challenge",
    (2, 0x00800000): "N. Gin Labs: CTR Token Challenge",
    (2, 0x01000000): "Polar Pass: CTR Token Challenge",
    (2, 0x02000000): "Oxide Station: CTR Token Challenge",
    (2, 0x04000000): "Coco Park: CTR Token Challenge",
    (2, 0x08000000): "Tiny Arena: CTR Token Challenge",
    # Boss-defeat bits (each "boss key" bit is set when you beat the corresponding boss)
    (2, 0x40000000): "Ripper Roo Garage: Boss Race",
    (2, 0x80000000): "Papu Papu Garage: Boss Race",

    # ──── rewards[3] at 0x8008FBB0 ─────────────────────────────────────────
    (3, 0x00000001): "Komodo Joe Garage: Boss Race",
    (3, 0x00000002): "Pinstripe Garage: Boss Race",
    # 0x4, 0x8 are BeatOxide1/2 which are goal conditions, handled separately
    # 0x10-0x200 are door-state flags, not locations
    # Gem Cup completions (5)
    (3, 0x00000400): "Red Gem Cup: Gem",
    (3, 0x00000800): "Green Gem Cup: Gem",
    (3, 0x00001000): "Blue Gem Cup: Gem",
    (3, 0x00002000): "Yellow Gem Cup: Gem",
    (3, 0x00004000): "Purple Gem Cup: Gem",
    # Battle arena Crystal Bonus Rounds (one per hub's arena)
    (3, 0x00008000): "Skull Rock: Crystal Bonus Round",
    (3, 0x00010000): "Rampage Ruins: Crystal Bonus Round",
    (3, 0x00020000): "Rocky Road: Crystal Bonus Round",
    (3, 0x00040000): "Nitro Court: Crystal Bonus Round",
    # 0x80000 and beyond are hint flags / "already seen" markers, not locations
}


# Goal condition bits (checked against victory items, not sent as locations)
GOAL_BITS = {
    "oxide_challenge": (3, 0x00000004),       # BeatOxide1 = Oxide's Challenge (goal 0)
    "oxide_final_challenge": (3, 0x00000008), # BeatOxide2 = Oxide's Final Challenge (goals 1, 2)
}


def parse_rewards(raw: bytes) -> list[int]:
    """Parse 24 raw bytes into the 6-uint32 rewards array (little-endian)."""
    if len(raw) != REWARDS_BYTES:
        raise ValueError(f"Expected {REWARDS_BYTES} bytes, got {len(raw)}")
    return [int.from_bytes(raw[i*4:(i+1)*4], "little") for i in range(6)]


def detect_set_locations(raw: bytes) -> list[str]:
    """Given raw AdvProgress.rewards bytes, return the list of location names
    whose bits are currently set."""
    words = parse_rewards(raw)
    out: list[str] = []
    for (word_idx, mask), name in LOCATION_BITS.items():
        if words[word_idx] & mask:
            out.append(name)
    return out


def detect_goals(raw: bytes) -> dict[str, bool]:
    """Return {goal_name: True/False} for each goal condition."""
    words = parse_rewards(raw)
    return {name: bool(words[w] & m) for name, (w, m) in GOAL_BITS.items()}
