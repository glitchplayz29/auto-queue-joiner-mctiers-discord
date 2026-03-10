"""
Lightweight JSON config manager.
Loads once on startup, writes only on mutation.
All reads are pure dict lookups (O(1)).
"""

import json
import os
import asyncio

CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "token": "",                    # Your Discord user token
    "prefix": "!",                  # Command prefix
    "owner_id": "",                 # Your Discord user ID (string)
    "command_channels": [],          # Channel IDs where bot accepts commands
    "auto_join_enabled": True,       # Global auto-join toggle
    "join_delay_seconds": 1.5,       # Delay before sending join command
    "webhook_cooldown_seconds": 2,   # Min seconds between webhook sends
    "log_file": "bot.log",
    "log_max_bytes": 5_242_880,      # 5MB rotating log
    "queues": {
        # "mctiers": {
        #   "join_command": "!join mctiers",
        #   "keywords": ["join mctiers", "mctiers queue"],
        #   "monitored_channels": ["123456789"],
        #   "open_keywords": ["queue open", "mctiers open"],
        #   "close_keywords": ["queue closed", "mctiers closed"],
        #   "auto_join": true,
        #   "webhook_url": "https://discord.com/api/webhooks/..."
        # }
    },
    "global_webhook_url": ""        # Fallback webhook for all events
}


class ConfigManager:
    """Thread-safe (async-safe) JSON config with write-back."""

    def __init__(self):
        self._data: dict = {}
        self._lock = asyncio.Lock()

    def load(self) -> None:
        """Load config synchronously at startup."""
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge with defaults so new keys are always present
            self._data = {**DEFAULT_CONFIG, **loaded}
        else:
            self._data = DEFAULT_CONFIG.copy()
            self._save_sync()

    def _save_sync(self) -> None:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    async def save(self) -> None:
        """Async save — serializes concurrent writes via lock."""
        async with self._lock:
            await asyncio.to_thread(self._save_sync)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value

    @property
    def queues(self) -> dict:
        return self._data.get("queues", {})

    def get_queue(self, name: str) -> dict | None:
        return self._data["queues"].get(name)

    def upsert_queue(self, name: str, data: dict) -> None:
        if name not in self._data["queues"]:
            self._data["queues"][name] = {}
        self._data["queues"][name].update(data)

    def get_monitored_channel_map(self) -> dict[str, list[str]]:
        """
        Returns {channel_id: [queue_name, ...]} for O(1) event dispatch.
        Built once and cached; rebuild after config changes.
        """
        mapping: dict[str, list[str]] = {}
        for qname, qdata in self._data["queues"].items():
            for ch_id in qdata.get("monitored_channels", []):
                mapping.setdefault(ch_id, []).append(qname)
        return mapping


# Singleton instance
config = ConfigManager()
