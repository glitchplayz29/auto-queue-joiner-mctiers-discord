"""
Monitors specified channels for queue open/close keywords.
Notifies via webhook and logs. Tracks last known state per queue
to avoid duplicate notifications (e.g., repeated "open" messages).
"""

import time
import discord

from .config_manager import ConfigManager
from .logger import get_logger

log = get_logger(__name__)

# State constants
QUEUE_UNKNOWN = "unknown"
QUEUE_OPEN    = "open"
QUEUE_CLOSED  = "closed"


class MonitorModule:
    """
    Tracks queue open/closed status per channel message scan.

    State machine per queue:
        unknown → open → closed → open → ...

    Only fires webhook/notification on state *change* to avoid spam.
    """

    def __init__(self, config: ConfigManager, webhook):
        self._config = config
        self._webhook = webhook
        # {queue_name: current_state_string}
        self._states: dict[str, str] = {}

    def _get_state(self, queue_name: str) -> str:
        return self._states.get(queue_name, QUEUE_UNKNOWN)

    def _set_state(self, queue_name: str, state: str) -> bool:
        """Returns True if state actually changed."""
        old = self._get_state(queue_name)
        if old != state:
            self._states[queue_name] = state
            return True
        return False

    async def check_status(self, message: discord.Message, queue_names: list[str]):
        """
        Called for every message in a monitored channel.
        Checks each relevant queue's open/close keywords.
        """
        content_lower = message.content.lower()

        for qname in queue_names:
            qdata = self._config.get_queue(qname)
            if not qdata:
                continue

            open_kws = [kw.lower() for kw in qdata.get("open_keywords", [])]
            close_kws = [kw.lower() for kw in qdata.get("close_keywords", [])]

            # Check close first (higher priority to avoid missing closes)
            if any(kw in content_lower for kw in close_kws):
                if self._set_state(qname, QUEUE_CLOSED):
                    log.info("[MONITOR] Queue '%s' CLOSED (channel %s)", qname, message.channel.id)
                    await self._notify_state_change(qname, QUEUE_CLOSED, message)

            elif any(kw in content_lower for kw in open_kws):
                if self._set_state(qname, QUEUE_OPEN):
                    log.info("[MONITOR] Queue '%s' OPEN (channel %s)", qname, message.channel.id)
                    await self._notify_state_change(qname, QUEUE_OPEN, message)

    async def _notify_state_change(
        self,
        queue_name: str,
        state: str,
        message: discord.Message
    ):
        is_open = state == QUEUE_OPEN
        color = 0x2ECC71 if is_open else 0xE74C3C
        emoji = "🟢" if is_open else "🔴"
        event = "queue_open" if is_open else "queue_closed"

        await self._webhook.send_queue_event(
            queue_name=queue_name,
            event=event,
            description=(
                f"{emoji} Queue **{queue_name}** is now **{state.upper()}**\n"
                f"Channel: `{message.channel.id}`\n"
                f"Server: `{getattr(message.guild, 'name', 'DM')}`\n"
                f"Message snippet: `{message.content[:80]}`"
            ),
            color=color
        )

    def get_states(self) -> dict[str, str]:
        """Return a snapshot of all current queue states."""
        return dict(self._states)
