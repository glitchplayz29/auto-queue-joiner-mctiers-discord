"""
Async Discord webhook sender with rate-limit guard and connection reuse.

Key optimizations:
- Single aiohttp.ClientSession shared across all sends (connection pool reuse)
- Per-URL rate limiting (min 2s between sends to same URL)
- Queue-aware: uses per-queue webhook if set, else global fallback
- Embeds sent as JSON POST — no heavy serialization
"""

import asyncio
import time
import aiohttp

from .config_manager import ConfigManager
from .logger import get_logger

log = get_logger(__name__)


class WebhookNotifier:

    def __init__(self, config: ConfigManager):
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        # {webhook_url: last_send_epoch (monotonic)}
        self._last_sent: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-init shared session — avoids creating session before event loop starts."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=5, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    def _is_rate_limited(self, url: str) -> bool:
        cooldown = self._config.get("webhook_cooldown_seconds", 2)
        last = self._last_sent.get(url, 0)
        return (time.monotonic() - last) < cooldown

    async def send(
        self,
        url: str,
        title: str,
        description: str,
        color: int = 0x5865F2
    ) -> bool:
        """
        Send a single embed to a webhook URL.
        Silently skips if rate-limited.
        Returns True on success.
        """
        if not url:
            return False

        async with self._lock:
            if self._is_rate_limited(url):
                log.debug("Webhook rate-limited for URL ...%s", url[-20:])
                return False

            payload = {
                "embeds": [{
                    "title": title,
                    "description": description,
                    "color": color,
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat()
                }]
            }

            try:
                session = await self._get_session()
                async with session.post(url, json=payload) as resp:
                    if resp.status in (200, 204):
                        self._last_sent[url] = time.monotonic()
                        log.debug("Webhook sent: '%s'", title)
                        return True
                    elif resp.status == 429:
                        # Discord's own rate limit header
                        retry_after = float(resp.headers.get("Retry-After", 2))
                        log.warning("Webhook 429 — retry after %.1fs", retry_after)
                        await asyncio.sleep(retry_after)
                        return False
                    else:
                        body = await resp.text()
                        log.error("Webhook HTTP %d: %s", resp.status, body[:200])
                        return False
            except asyncio.TimeoutError:
                log.error("Webhook send timed out")
                return False
            except aiohttp.ClientError as e:
                log.error("Webhook client error: %s", e)
                return False

    async def send_queue_event(
        self,
        queue_name: str,
        event: str,
        description: str,
        color: int = 0x5865F2
    ):
        """
        Send a queue-specific event notification.
        Uses per-queue webhook URL if configured, else global.
        """
        qdata = self._config.get_queue(queue_name)
        url = ""
        if qdata:
            url = qdata.get("webhook_url", "")
        if not url:
            url = self._config.get("global_webhook_url", "")
        if not url:
            return  # No webhook configured

        title = f"[{queue_name.upper()}] {event.replace('_', ' ').title()}"
        await self.send(url, title, description, color)

    async def send_global(self, title: str, description: str, color: int = 0x5865F2):
        """Send to global webhook only."""
        url = self._config.get("global_webhook_url", "")
        if url:
            await self.send(url, title, description, color)

    async def close(self):
        """Release the aiohttp session cleanly on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()
            log.debug("Webhook session closed")
