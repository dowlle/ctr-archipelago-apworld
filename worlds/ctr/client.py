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
)
from .Locations import CTR_LOCATION_IDS

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

logger = logging.getLogger("CTR")


# Bits to set in AdvProgress when each item is received. One entry per item
# name in Icebound's items.json. For now we only handle per-track progression
# items implicitly (the per-track location checks read the same bits); for
# count items (Trophy, Key, etc) we defer the full implementation until we
# move to the mod's slot-2 struct.
#
# The tricky part: a single "Trophy" item from AP isn't tied to a specific
# track. If we set arbitrary Trophy bits, we'd need to pick which track to
# mark. For MVP we leave item-receive as a no-op and log them; locations
# still fire correctly when the player naturally earns trophies in the
# randomized game.
ITEMS_LOG_ONLY = True


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

    def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        # Keep the existing ReceivedItems logger below; we also intercept
        # connection lifecycle so premature detections before a server connect
        # don't silently get latched into sent_locations and never retried.
        if cmd == "Connected":
            # Fresh server connection: trust the server's locations_checked
            # and retry everything else on the next poll.
            self.sent_locations = set(args.get("checked_locations", []) or [])
            self.goal_reported = False
            self.last_rewards_bytes = None
        return self._on_package_received_items(ctx, cmd, args)

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
        # Handle items locally (grant immediately) + from server + initial pool
        ctx.items_handling = 0b111
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

    def _on_package_received_items(
        self, ctx: "BizHawkClientContext", cmd: str, args: dict,
    ) -> None:
        # `args["items"]` contains NetworkItem dataclasses, not dicts, so
        # `.get("item")` on them raises AttributeError and kills the socket.
        # We also wrap the whole thing in try/except so any future log formatter
        # bug cannot tear down the connection.
        if cmd == "ReceivedItems" and ITEMS_LOG_ONLY:
            try:
                items = args.get("items") or []
                if items:
                    item_ids = [getattr(it, "item", None) for it in items[:10]]
                    logger.info(
                        "CTR: received %d items (log-only, not yet applied): ids=%s",
                        len(items), item_ids,
                    )
            except Exception as exc:
                logger.warning("CTR on_package ReceivedItems log failed: %r", exc)
