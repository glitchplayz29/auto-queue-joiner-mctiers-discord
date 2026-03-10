"""
SelfBot core — connects to Discord Gateway, routes events.
Single asyncio event loop, zero polling.
"""

import asyncio
import time
import discord

from .config_manager import config
from .queue_manager import QueueManager
from .command_handler import CommandHandler
from .monitor import MonitorModule
from .webhook import WebhookNotifier
from .logger import get_logger

log = get_logger(__name__)


class SelfBot(discord.Client):
    """
    Inherits discord.Client which manages the WebSocket connection.
    All event handling is async and non-blocking.
    """

    def __init__(self):
        # Minimal intents — only what we need reduces gateway traffic
        super().__init__()
        self.webhook = WebhookNotifier(config)
        self.queue_mgr = QueueManager(config, self.webhook)
        self.monitor = MonitorModule(config, self.webhook)
        self.cmd_handler = CommandHandler(config, self.queue_mgr, self.monitor, self.webhook)
        self._monitor_channel_map: dict[str, list[str]] = {}
        self._rebuild_channel_map()

    def _rebuild_channel_map(self) -> None:
        """Rebuild O(1) lookup map after config changes."""
        self._monitor_channel_map = config.get_monitored_channel_map()
        log.debug("Monitor channel map rebuilt: %d channels", len(self._monitor_channel_map))

    # ─── Gateway Events ────────────────────────────────────────────

    async def on_ready(self):
        log.info("Logged in as %s (ID: %s)", self.user.name, self.user.id)
        await self.webhook.send_global(
            title="🟢 Self-Bot Online",
            description=f"Logged in as **{self.user.name}**",
            color=0x2ECC71
        )

    async def on_message(self, message: discord.Message):
        """
        Single entry point for all messages.
        Fast-path exits keep CPU usage minimal.
        """
        # Ignore own messages to prevent loops
        if message.author.id == self.user.id:
            return

        channel_id = str(message.channel.id)
        content_lower = message.content.lower()

        # ── 1. Command panel (DMs or designated channels) ──────────
        owner_id = config.get("owner_id")
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_cmd_channel = channel_id in set(str(c) for c in config.get("command_channels", []))

        if (is_dm or is_cmd_channel) and str(message.author.id) == str(owner_id):
            prefix = config.get("prefix", "!")
            if message.content.startswith(prefix):
                await self.cmd_handler.handle(message, self)
                return  # Don't process further for own commands

        # ── 2. Mention / ping detection for auto-join ───────────────
        if self.user in message.mentions and config.get("auto_join_enabled", True):
            await self._handle_mention(message, content_lower)

        # ── 3. Monitored channel queue status updates ───────────────
        if channel_id in self._monitor_channel_map:
            queue_names = self._monitor_channel_map[channel_id]
            await self.monitor.check_status(message, queue_names)

    async def _handle_mention(self, message: discord.Message, content_lower: str):
        """
        Check if the mention relates to any configured queue's keywords.
        Uses set intersection for fast multi-keyword matching.
        """
        for qname, qdata in config.queues.items():
            if not qdata.get("auto_join", True):
                continue
            keywords = [kw.lower() for kw in qdata.get("keywords", [])]
            if any(kw in content_lower for kw in keywords):
                log.info("Ping matched queue '%s' in channel %s", qname, message.channel.id)
                await self.queue_mgr.join_queue(
                    queue_name=qname,
                    channel=message.channel,
                    trigger="auto-ping",
                    triggered_by=str(message.author)
                )
                break  # Join first matching queue; adjust if multi-match needed

    def notify_config_changed(self):
        """Call this after any config mutation that affects channel mapping."""
        self._rebuild_channel_map()

    # ─── Graceful shutdown ─────────────────────────────────────────

    async def close(self):
        log.info("Shutting down...")
        await self.webhook.close()
        await super().close()
