"""
BizHawk-based Archipelago client for Crash Team Racing (PSX, 1999).

Drops into an Archipelago install as `worlds/ctr/client.py` alongside
Icebound777's in-progress apworld. Targets the vanilla NTSC-U ROM; reads
the AdvProgress struct at PSX virt 0x8008FBA4 (BizHawk MainRAM offset
0x8FBA4) to detect location checks, and sets bits in the same struct
when items are received.

Not yet tested end-to-end. Known gaps:
- No ROM fingerprint validation (accepts any PSX ROM). Users playing
  non-CTR PSX games would get false connects.
- Item-receive implementation just sets the corresponding bit in the
  vanilla AdvProgress struct. Works for Trophy, Relic, Gem, CTR Token
  grants because the game reads these bits directly. For proper
  multiworld play we'll eventually want to use Icebound's mod's slot-2
  struct instead (see CTRRandomizer_handle_item_unlocks.c).
- Goal condition check uses BeatOxide1 / BeatOxide2 bits; not yet wired
  to goals 2, 3, 4 (Everything+1, AllBosses, AllGemCups).
- Save-file detection is naive: we read AdvProgress unconditionally. If
  the player is on the title screen the struct is zeros, which is fine
  (nothing fires) but also means reconnects while on title may look
  unresponsive. Fine for MVP.

The Items and Locations here match `icebound777/Archipelago-Crash-Team-Racing`
branch `ctr-apworld` at 2026-04-18.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from NetUtils import ClientStatus
import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from .addresses import (
    ADVPROGRESS_BASE,
    REWARDS_BYTES,
    LOCATION_BITS,
    GOAL_BITS,
    SAVESLOT_4_BASE,
    SAVE_SAFE_GATE,
)
from .Locations import CTR_LOCATION_IDS

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("CTR")


# Map from AP item name → (word_index, handler_kind, arg)
# - handler_kind == "counter_u32"  : rewards[word] += arg  (where arg is 1; future-proofed for bulk)
# - handler_kind == "counter_byte" : ((rewards[word] >> (arg*8)) & 0xFF) += 1
# - handler_kind == "gem"          : set flag bit arg in rewards[5] + increment rewards[5]&0xFF
# - handler_kind == "skip"         : filler / cross-game, log but don't write
#
# Layout from SaveSlot 2/4 docstring in addresses.py. Only the word/byte
# position matters for the write — actual counter bumps are relative.
ITEM_HANDLERS: dict[str, tuple[str, int, int]] = {
    # kind,           word_idx, arg (byte_offset for counter_byte, bit_mask for gem, unused for u32/skip)
    "Trophy":          ("counter_u32",  0, 0),
    "Key":             ("counter_u32",  1, 0),
    "Red CTR Token":   ("counter_byte", 2, 0),
    "Green CTR Token": ("counter_byte", 2, 1),
    "Blue CTR Token":  ("counter_byte", 2, 2),
    "Yellow CTR Token":("counter_byte", 2, 3),
    "Purple CTR Token":("counter_byte", 3, 0),
    "Sapphire Relic":  ("counter_byte", 4, 0),
    "Gold Relic":      ("counter_byte", 4, 1),
    "Platinum Relic":  ("counter_byte", 4, 2),
    "Red Gem":         ("gem",          5, 0x100),
    "Green Gem":       ("gem",          5, 0x200),
    "Blue Gem":        ("gem",          5, 0x400),
    "Yellow Gem":      ("gem",          5, 0x800),
    "Purple Gem":      ("gem",          5, 0x1000),
    "Wumpa Fruit":     ("skip",         0, 0),
    "Archipelago Item":("skip",         0, 0),
}


class CtrClient(BizHawkClient):
    game = "Crash Team Racing"
    system = "PSX"
    # Registers the .apctr extension with Archipelago's Launcher via the
    # BizHawkClient metaclass. Double-clicking an .apctr file (or using
    # "Open Patch" in the launcher) will invoke CrashTeamRacingProcedurePatch
    # to build the randomized ROM, launch EmuHawk with the generic Lua
    # connector, and start this client.
    patch_suffix = ".apctr"

    def __init__(self) -> None:
        super().__init__()
        self.sent_locations: set[int] = set()
        self.goal_reported: bool = False
        self.last_rewards_bytes: bytes | None = None
        # Highest item index we've written to SaveSlot 4. ReceivedItems
        # messages carry (index, items) where index is the position of the
        # first item in the message within the slot's cumulative item list;
        # by only applying items whose position >= self.next_item_index we
        # avoid double-applying on reconnect / replay.
        self.next_item_index: int = 0
        # Queue of (name, handler) tuples from recent ReceivedItems that
        # haven't been written to RAM yet (because save-safe gate was down
        # or the game hadn't loaded the save). Drained in game_watcher.
        self.pending_items: list[tuple[int, str]] = []

    def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        # Intercept connection lifecycle so premature detections before a
        # server connect don't silently get latched into sent_locations and
        # never retried; also so item replay starts from index 0.
        if cmd == "Connected":
            self.sent_locations = set(args.get("checked_locations", []) or [])
            self.goal_reported = False
            self.last_rewards_bytes = None
            self.next_item_index = 0
            self.pending_items = []
        elif cmd == "ReceivedItems":
            self._queue_received_items(ctx, args)
        return self._on_package_received_items(ctx, cmd, args)

    def _queue_received_items(self, ctx: "BizHawkClientContext", args: dict) -> None:
        """Queue items from a ReceivedItems packet for application in the
        next game_watcher poll (where we can check the save-safe gate)."""
        try:
            start_index = int(args.get("index", 0))
            items = args.get("items") or []
            for offset, item in enumerate(items):
                absolute_index = start_index + offset
                if absolute_index < self.next_item_index:
                    continue  # already applied in a previous session
                item_id = getattr(item, "item", None)
                if item_id is None:
                    continue
                item_name = self._resolve_item_name(ctx, item_id)
                self.pending_items.append((absolute_index, item_name or f"id={item_id}"))
        except Exception as exc:
            logger.warning("CTR: _queue_received_items failed: %r", exc)

    @staticmethod
    def _resolve_item_name(ctx: "BizHawkClientContext", item_id: int) -> str | None:
        """Best-effort: resolve an AP item ID to its item name string.
        Different AP client versions expose the lookup differently."""
        lookup = getattr(ctx, "item_names", None)
        if lookup is None:
            return None
        # Newer AP: item_names.lookup_in_slot(item_id, slot=ctx.slot)
        for attr in ("lookup_in_slot", "lookup_in_game"):
            fn = getattr(lookup, attr, None)
            if fn is None:
                continue
            try:
                return fn(item_id, ctx.slot) if attr == "lookup_in_slot" else fn(item_id, "Crash Team Racing")
            except Exception:
                continue
        # Fallback: item_names is a dict-like mapping game -> dict
        try:
            return lookup["Crash Team Racing"][item_id]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        """Accept any running PSX ROM for now. A proper fingerprint check
        should compare a short ROM signature to a known CTR NTSC-U hash.
        This will mis-attach on non-CTR PSX games; user must know what
        they're running for MVP."""
        try:
            # Smoke test: the memory domain must be readable.
            _ = await bizhawk.read(ctx.bizhawk_ctx, [(ADVPROGRESS_BASE, 4, "MainRAM")])
        except bizhawk.RequestFailedError:
            return False

        ctx.game = self.game
        # items_handling bitfield:
        #   bit 0 = receive items from others (remote)
        #   bit 1 = receive items for your own locations (self)
        #   bit 2 = receive starting inventory
        # We deliberately OMIT bit 1 (self) because Icebound's mod already
        # delivers items placed on local locations when the player wins that
        # check in-game (via its internal DB lookup). Handling self_items
        # here would double-apply the counter bumps. We keep remote (0b001)
        # and starting inventory (0b100).
        ctx.items_handling = 0b101
        ctx.want_slot_data = True
        logger.info("CTR client attached. NOTE: no ROM fingerprint check; make sure CTR NTSC-U is running.")
        return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        try:
            raw = (await bizhawk.read(
                ctx.bizhawk_ctx,
                [(ADVPROGRESS_BASE, REWARDS_BYTES, "MainRAM")]
            ))[0]
        except bizhawk.RequestFailedError:
            return  # reconnect handled by parent

        if raw == self.last_rewards_bytes:
            return  # no change, nothing to do
        self.last_rewards_bytes = raw

        words = [int.from_bytes(raw[i*4:(i+1)*4], "little") for i in range(6)]

        # ── Detect location check flips ──
        newly_checked: list[int] = []
        for (word_idx, mask), loc_name in LOCATION_BITS.items():
            if not (words[word_idx] & mask):
                continue
            loc_id = CTR_LOCATION_IDS.get(loc_name)
            if loc_id is None:
                continue  # unknown location (bad mapping; log once?)
            if loc_id in self.sent_locations:
                continue
            if loc_id in ctx.locations_checked:
                self.sent_locations.add(loc_id)
                continue
            newly_checked.append(loc_id)
            # DO NOT add to self.sent_locations here; we only mark as sent
            # after the server actually accepts the send (see below). This
            # prevents silent data loss if we detect bits before the server
            # connection is up — the no-op send_msgs() would otherwise latch
            # locations into sent_locations and never retry them.

        if newly_checked and ctx.server is not None:
            logger.info("CTR: new location checks: %s", newly_checked)
            try:
                await ctx.send_msgs([{
                    "cmd": "LocationChecks",
                    "locations": newly_checked,
                }])
                self.sent_locations.update(newly_checked)
            except Exception as exc:
                logger.warning(
                    "CTR: send_msgs failed (%r); will retry on next poll",
                    exc,
                )

        # ── Apply any pending received items to SaveSlot 4 ──
        if self.pending_items and ctx.server is not None:
            await self._drain_pending_items(ctx)

        # ── Detect goal completion ──
        if not self.goal_reported and not ctx.finished_game:
            goal_value = 0
            slot_data_options = (ctx.slot_data or {}).get("options", {})
            if isinstance(slot_data_options, dict):
                goal_value = int(slot_data_options.get("Goal", 0))

            goal_met = False
            if goal_value == 0:
                # N. Oxide's Challenge
                w, m = GOAL_BITS["oxide_challenge"]
                goal_met = bool(words[w] & m)
            elif goal_value in (1, 2):
                # N. Oxide's Final Challenge (and Everything+1 which also requires it)
                w, m = GOAL_BITS["oxide_final_challenge"]
                goal_met = bool(words[w] & m)
            elif goal_value == 3:
                # All 16 Trophies
                trophy_masks = [v for (w, v) in LOCATION_BITS
                                if w == 0 and "Trophy Race" in LOCATION_BITS[(w, v)]]
                goal_met = all(words[0] & m for m in trophy_masks)
            elif goal_value == 4:
                # All 5 Gem Cups complete
                gem_cup_masks = [0x400, 0x800, 0x1000, 0x2000, 0x4000]
                goal_met = all(words[3] & m for m in gem_cup_masks)

            if goal_met:
                logger.info("CTR: goal condition met (mode %d)", goal_value)
                await ctx.send_msgs([{
                    "cmd": "StatusUpdate",
                    "status": ClientStatus.CLIENT_GOAL,
                }])
                self.goal_reported = True

    # ------------------------------------------------------------------
    # Item receive (placeholder)
    # ------------------------------------------------------------------

    async def _drain_pending_items(self, ctx: "BizHawkClientContext") -> None:
        """Write queued received items to SaveSlot 4, gated on the save-safe
        flag. Items that can't be applied this tick stay in the queue.
        """
        # Check the save-safe gate first. Only write when the game is in a
        # state where SaveSlot writes won't corrupt anything.
        try:
            gate_bytes = (await bizhawk.read(
                ctx.bizhawk_ctx,
                [(SAVE_SAFE_GATE, 4, "MainRAM")]
            ))[0]
        except bizhawk.RequestFailedError:
            return
        gate = int.from_bytes(gate_bytes, "little")
        if gate != 1:
            # Not safe to write; try again next poll.
            return

        # Read the current SaveSlot 4 rewards[] (24 bytes).
        try:
            ss4_bytes = (await bizhawk.read(
                ctx.bizhawk_ctx,
                [(SAVESLOT_4_BASE, REWARDS_BYTES, "MainRAM")]
            ))[0]
        except bizhawk.RequestFailedError:
            return
        rewards = bytearray(ss4_bytes)

        applied: list[tuple[int, str]] = []
        for idx, name in self.pending_items:
            handler = ITEM_HANDLERS.get(name)
            if handler is None:
                logger.info("CTR: unknown item %r (idx=%d), skipping", name, idx)
                applied.append((idx, name))
                continue
            kind, word_idx, arg = handler
            word_offset = word_idx * 4
            if kind == "skip":
                applied.append((idx, name))
                continue
            if kind == "counter_u32":
                current = int.from_bytes(rewards[word_offset:word_offset + 4], "little")
                new = (current + 1) & 0xFFFFFFFF
                rewards[word_offset:word_offset + 4] = new.to_bytes(4, "little")
                applied.append((idx, name))
                continue
            if kind == "counter_byte":
                byte_offset = word_offset + arg
                current = rewards[byte_offset]
                rewards[byte_offset] = min(current + 1, 0xFF)
                applied.append((idx, name))
                continue
            if kind == "gem":
                current = int.from_bytes(rewards[word_offset:word_offset + 4], "little")
                # Set the flag bit (arg) and bump the low-byte gem count by 1
                count = min((current & 0xFF) + 1, 0xFF)
                new = ((current & ~0xFF) | count) | arg
                rewards[word_offset:word_offset + 4] = new.to_bytes(4, "little")
                applied.append((idx, name))
                continue
            logger.warning("CTR: unhandled handler kind %r for %r", kind, name)

        if not applied:
            return

        # Write the modified rewards[] block back to SaveSlot 4.
        try:
            await bizhawk.write(
                ctx.bizhawk_ctx,
                [(SAVESLOT_4_BASE, bytes(rewards), "MainRAM")]
            )
        except bizhawk.RequestFailedError as exc:
            logger.warning("CTR: SaveSlot 4 write failed (%r); retaining queue", exc)
            return

        for idx, name in applied:
            self.next_item_index = max(self.next_item_index, idx + 1)
        applied_set = {(i, n) for (i, n) in applied}
        self.pending_items = [p for p in self.pending_items if p not in applied_set]
        logger.info(
            "CTR: applied %d items to SaveSlot 4: %s",
            len(applied), [n for _, n in applied],
        )

    def _on_package_received_items(
        self, ctx: "BizHawkClientContext", cmd: str, args: dict,
    ) -> None:
        # Keep a log line for visibility. The actual writes happen in
        # _drain_pending_items during game_watcher, where we can honor the
        # save-safe gate.
        if cmd == "ReceivedItems":
            try:
                items = args.get("items") or []
                if items:
                    item_ids = [getattr(it, "item", None) for it in items[:10]]
                    logger.info(
                        "CTR: queued %d items for SaveSlot 4 write (ids=%s)",
                        len(items), item_ids,
                    )
            except Exception as exc:
                logger.warning("CTR on_package ReceivedItems log failed: %r", exc)
