"""
Lightweight prefix command dispatcher.
Parses commands from DMs or designated channels.
No heavy framework — pure string splits for minimal overhead.
"""

import asyncio
import discord

from .config_manager import ConfigManager
from .logger import get_logger

log = get_logger(__name__)

# ── Command registry ────────────────────────────────────────────────────────
# Maps command name → async handler function
# This avoids repeated if/elif chains and is easily extensible


class CommandHandler:

    def __init__(self, config: ConfigManager, queue_mgr, monitor, webhook):
        self._config = config
        self._queue_mgr = queue_mgr
        self._monitor = monitor
        self._webhook = webhook
        self._commands = {
            "join":      self._cmd_join,
            "leave":     self._cmd_leave,
            "monitor":   self._cmd_monitor,
            "unmonitor": self._cmd_unmonitor,
            "addqueue":  self._cmd_addqueue,
            "delqueue":  self._cmd_delqueue,
            "setwebhook":self._cmd_setwebhook,
            "autojoin":  self._cmd_autojoin,
            "status":    self._cmd_status,
            "help":      self._cmd_help,
        }

    async def handle(self, message: discord.Message, client):
        prefix = self._config.get("prefix", "!")
        content = message.content[len(prefix):].strip()
        parts = content.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        handler = self._commands.get(cmd)
        if handler:
            try:
                await handler(message, args, client)
            except Exception as e:
                log.error("Command '%s' error: %s", cmd, e)
                await message.channel.send(f"⚠️ Error: `{e}`")
        else:
            await message.channel.send(f"❓ Unknown command. Use `{prefix}help`")

    # ─── Command Implementations ─────────────────────────────────────────────

    async def _cmd_join(self, msg, args, client):
        """!join <queue_name> <channel_id>"""
        if len(args) < 2:
            await msg.channel.send("Usage: `!join <queue_name> <channel_id>`")
            return
        qname, ch_id_str = args[0], args[1]
        try:
            ch_id = int(ch_id_str)
        except ValueError:
            await msg.channel.send("❌ Invalid channel ID (must be integer)")
            return
        await msg.channel.send(f"⏳ Joining queue **{qname}** in channel `{ch_id}`...")
        success = await self._queue_mgr.join_by_channel_id(qname, ch_id, client, trigger="manual-command")
        if success:
            await msg.channel.send(f"✅ Join command sent for **{qname}**")
        else:
            await msg.channel.send(f"❌ Failed to join **{qname}** — check logs")

    async def _cmd_leave(self, msg, args, client):
        """!leave <queue_name> <channel_id> — sends a configured leave command"""
        if len(args) < 2:
            await msg.channel.send("Usage: `!leave <queue_name> <channel_id>`")
            return
        qname, ch_id_str = args[0], args[1]
        qdata = self._config.get_queue(qname)
        if not qdata:
            await msg.channel.send(f"❌ Queue **{qname}** not configured")
            return
        leave_cmd = qdata.get("leave_command", f"!leave {qname}")
        try:
            ch_id = int(ch_id_str)
            channel = client.get_channel(ch_id) or await client.fetch_channel(ch_id)
            await channel.send(leave_cmd)
            await msg.channel.send(f"✅ Left **{qname}**")
        except Exception as e:
            await msg.channel.send(f"❌ Error: `{e}`")

    async def _cmd_monitor(self, msg, args, client):
        """!monitor <channel_id> <queue_name> — add channel to monitoring list"""
        if len(args) < 2:
            await msg.channel.send("Usage: `!monitor <channel_id> <queue_name>`")
            return
        ch_id, qname = args[0], args[1]
        qdata = self._config.get_queue(qname)
        if not qdata:
            await msg.channel.send(f"❌ Queue **{qname}** not configured. Add it first with `!addqueue`")
            return
        channels: list = qdata.get("monitored_channels", [])
        if ch_id not in channels:
            channels.append(ch_id)
            self._config.upsert_queue(qname, {"monitored_channels": channels})
            await self._config.save()
            # Rebuild channel map in the bot core
            if hasattr(client, "notify_config_changed"):
                client.notify_config_changed()
            await msg.channel.send(f"✅ Now monitoring `{ch_id}` for queue **{qname}**")
        else:
            await msg.channel.send(f"ℹ️ Channel `{ch_id}` is already monitored for **{qname}**")

    async def _cmd_unmonitor(self, msg, args, client):
        """!unmonitor <channel_id> <queue_name>"""
        if len(args) < 2:
            await msg.channel.send("Usage: `!unmonitor <channel_id> <queue_name>`")
            return
        ch_id, qname = args[0], args[1]
        qdata = self._config.get_queue(qname)
        if not qdata:
            await msg.channel.send(f"❌ Queue **{qname}** not configured")
            return
        channels: list = qdata.get("monitored_channels", [])
        if ch_id in channels:
            channels.remove(ch_id)
            self._config.upsert_queue(qname, {"monitored_channels": channels})
            await self._config.save()
            if hasattr(client, "notify_config_changed"):
                client.notify_config_changed()
            await msg.channel.send(f"✅ Removed `{ch_id}` from monitoring for **{qname}**")
        else:
            await msg.channel.send(f"ℹ️ Channel `{ch_id}` not in monitor list for **{qname}**")

    async def _cmd_addqueue(self, msg, args, client):
        """
        !addqueue <queue_name> <join_command> <keyword1,keyword2,...>
        Example: !addqueue mctiers "!join mctiers" "join mctiers,mctiers queue"
        """
        if len(args) < 3:
            await msg.channel.send(
                "Usage: `!addqueue <name> <join_command> <kw1,kw2,...>`\n"
                "Example: `!addqueue mctiers !joinmctiers mctiers,join mctiers`"
            )
            return
        qname = args[0]
        join_cmd = args[1]
        keywords = [kw.strip() for kw in " ".join(args[2:]).split(",")]

        self._config.upsert_queue(qname, {
            "join_command": join_cmd,
            "keywords": keywords,
            "monitored_channels": [],
            "open_keywords": ["queue open", f"{qname} open"],
            "close_keywords": ["queue closed", f"{qname} closed"],
            "auto_join": True,
            "webhook_url": ""
        })
        await self._config.save()
        await msg.channel.send(
            f"✅ Queue **{qname}** added\n"
            f"Join command: `{join_cmd}`\n"
            f"Keywords: `{', '.join(keywords)}`"
        )

    async def _cmd_delqueue(self, msg, args, client):
        """!delqueue <queue_name>"""
        if not args:
            await msg.channel.send("Usage: `!delqueue <queue_name>`")
            return
        qname = args[0]
        if qname in self._config.queues:
            del self._config.queues[qname]
            await self._config.save()
            if hasattr(client, "notify_config_changed"):
                client.notify_config_changed()
            await msg.channel.send(f"✅ Queue **{qname}** deleted")
        else:
            await msg.channel.send(f"❌ Queue **{qname}** not found")

    async def _cmd_setwebhook(self, msg, args, client):
        """
        !setwebhook <url> [queue_name]
        If queue_name omitted, sets the global webhook.
        """
        if not args:
            await msg.channel.send("Usage: `!setwebhook <url> [queue_name]`")
            return
        url = args[0]
        if len(args) >= 2:
            qname = args[1]
            qdata = self._config.get_queue(qname)
            if not qdata:
                await msg.channel.send(f"❌ Queue **{qname}** not configured")
                return
            self._config.upsert_queue(qname, {"webhook_url": url})
            await self._config.save()
            await msg.channel.send(f"✅ Webhook set for queue **{qname}**")
        else:
            self._config.set("global_webhook_url", url)
            await self._config.save()
            await msg.channel.send("✅ Global webhook URL updated")

    async def _cmd_autojoin(self, msg, args, client):
        """!autojoin <on|off> [queue_name]"""
        if not args:
            await msg.channel.send("Usage: `!autojoin <on|off> [queue_name]`")
            return
        state = args[0].lower() == "on"
        if len(args) >= 2:
            qname = args[1]
            self._config.upsert_queue(qname, {"auto_join": state})
            await self._config.save()
            await msg.channel.send(f"✅ Auto-join for **{qname}**: {'ON' if state else 'OFF'}")
        else:
            self._config.set("auto_join_enabled", state)
            await self._config.save()
            await msg.channel.send(f"✅ Global auto-join: {'ON' if state else 'OFF'}")

    async def _cmd_status(self, msg, args, client):
        """!status — show all configured queues and their settings"""
        queues = self._config.queues
        if not queues:
            await msg.channel.send("ℹ️ No queues configured. Use `!addqueue` to add one.")
            return
        lines = ["**Queue Status**\n"]
        for qname, qdata in queues.items():
            aj = "✅" if qdata.get("auto_join", True) else "❌"
            ch_count = len(qdata.get("monitored_channels", []))
            kw = ", ".join(qdata.get("keywords", [])[:3])
            lines.append(
                f"**{qname}** | AutoJoin: {aj} | "
                f"Monitoring: {ch_count} channels | "
                f"Keywords: `{kw}`"
            )
        global_aj = "✅" if self._config.get("auto_join_enabled") else "❌"
        lines.append(f"\nGlobal AutoJoin: {global_aj}")
        await msg.channel.send("\n".join(lines))

    async def _cmd_help(self, msg, args, client):
        """!help"""
        p = self._config.get("prefix", "!")
        help_text = f"""**Self-Bot Commands** (prefix: `{p}`)

`{p}join <queue> <channel_id>` — Manually join a queue in a channel
`{p}leave <queue> <channel_id>` — Send leave command for a queue
`{p}addqueue <name> <cmd> <kw1,kw2>` — Add/configure a queue
`{p}delqueue <name>` — Remove a queue
`{p}monitor <channel_id> <queue>` — Monitor a channel for a queue
`{p}unmonitor <channel_id> <queue>` — Stop monitoring a channel
`{p}setwebhook <url> [queue]` — Set webhook (global or per-queue)
`{p}autojoin <on|off> [queue]` — Toggle auto-join globally or per-queue
`{p}status` — Show all configured queues
`{p}help` — Show this message"""
        await msg.channel.send(help_text)
