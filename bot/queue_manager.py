"""
Queue join logic with per-queue cooldowns and rate limiting.
Uses asyncio.Lock per queue to prevent duplicate concurrent joins.
"""

import asyncio
import time
import discord

from .config_manager import ConfigManager
from .logger import get_logger

log = get_logger(__name__)


class QueueManager:
    """
    Manages joining queues — auto and manual.

    Cooldowns prevent spamming the same queue join command.
    Per-queue asyncio.Lock ensures no race conditions when
    multiple events trigger the same queue simultaneously.
    """

    def __init__(self, config: ConfigManager, webhook):
        self._config = config
        self._webhook = webhook
        # {queue_name: asyncio.Lock}
        self._locks: dict[str, asyncio.Lock] = {}
        # {queue_name: last_join_epoch}
        self._last_join: dict[str, float] = {}
        # Default cooldown between join attempts (seconds)
        self.JOIN_COOLDOWN = 30.0

    def _get_lock(self, queue_name: str) -> asyncio.Lock:
        if queue_name not in self._locks:
            self._locks[queue_name] = asyncio.Lock()
        return self._locks[queue_name]

    def _is_on_cooldown(self, queue_name: str) -> bool:
        last = self._last_join.get(queue_name, 0)
        return (time.monotonic() - last) < self.JOIN_COOLDOWN

    async def join_queue(
        self,
        queue_name: str,
        channel: discord.abc.Messageable,
        trigger: str = "manual",
        triggered_by: str = "owner"
    ) -> bool:
        """
        Send the join command for a named queue in the given channel.

        Returns True on success, False on cooldown or config error.
        """
        qdata = self._config.get_queue(queue_name)
        if not qdata:
            log.warning("Unknown queue '%s'", queue_name)
            return False

        lock = self._get_lock(queue_name)

        # Non-blocking lock check — skip if already joining
        if lock.locked():
            log.debug("Queue '%s' join already in progress, skipping", queue_name)
            return False

        async with lock:
            if self._is_on_cooldown(queue_name):
                remaining = self.JOIN_COOLDOWN - (time.monotonic() - self._last_join[queue_name])
                log.info("Queue '%s' on cooldown (%.1fs remaining)", queue_name, remaining)
                await self._webhook.send_queue_event(
                    queue_name=queue_name,
                    event="cooldown",
                    description=f"Join skipped — cooldown ({remaining:.0f}s remaining)",
                    color=0xF39C12
                )
                return False

            join_command = qdata.get("join_command", f"!join {queue_name}")
            delay = self._config.get("join_delay_seconds", 1.5)

            # Small async delay — avoids instant-response detection
            await asyncio.sleep(delay)

            try:
                await channel.send(join_command)
                self._last_join[queue_name] = time.monotonic()
                log.info(
                    "[JOIN] Queue='%s' | Command='%s' | Channel=%s | Trigger=%s | By=%s",
                    queue_name, join_command, channel.id, trigger, triggered_by
                )
                await self._webhook.send_queue_event(
                    queue_name=queue_name,
                    event="joined",
                    description=(
                        f"✅ Joined **{queue_name}**\n"
                        f"Channel: `{channel.id}`\n"
                        f"Trigger: `{trigger}`\n"
                        f"Command: `{join_command}`"
                    ),
                    color=0x2ECC71
                )
                return True

            except discord.Forbidden:
                log.error("No permission to send in channel %s", channel.id)
                await self._webhook.send_queue_event(
                    queue_name=queue_name,
                    event="error",
                    description=f"❌ No permission to send in channel `{channel.id}`",
                    color=0xE74C3C
                )
                return False

            except discord.HTTPException as e:
                log.error("HTTP error joining '%s': %s", queue_name, e)
                await self._webhook.send_queue_event(
                    queue_name=queue_name,
                    event="error",
                    description=f"❌ HTTP error: `{e}`",
                    color=0xE74C3C
                )
                return False

    async def join_by_channel_id(
        self,
        queue_name: str,
        channel_id: int,
        client: discord.Client,
        trigger: str = "manual"
    ) -> bool:
        """
        Resolve a channel by ID and join the queue there.
        Used by manual !join commands.
        """
        channel = client.get_channel(channel_id)
        if channel is None:
            # Fetch from API if not in cache — rare, avoid unless needed
            try:
                channel = await client.fetch_channel(channel_id)
            except discord.NotFound:
                log.error("Channel %d not found", channel_id)
                return False
        return await self.join_queue(queue_name, channel, trigger=trigger)
