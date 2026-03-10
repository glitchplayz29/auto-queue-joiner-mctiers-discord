"""
Entry point — initializes config, logging, then runs the bot.
Single asyncio.run() call — no manual loop management.
"""

import asyncio
import sys

import discord

from bot import setup_logging, config
from bot.core import SelfBot


async def main():
    # 1. Load config (sync — must happen before async components init)
    config.load()

    # 2. Set up logging
    setup_logging(
        log_file=config.get("log_file", "bot.log"),
        max_bytes=config.get("log_max_bytes", 5_242_880)
    )

    from bot.logger import get_logger
    log = get_logger("main")

    token = config.get("token", "")
    if not token:
        log.critical("No token set in config.json — set 'token' and restart")
        print("ERROR: Set your token in config.json")
        sys.exit(1)

    bot = SelfBot()

    try:
        log.info("Starting self-bot...")
        await bot.start(token)
    except discord.LoginFailure:
        log.critical("Invalid token. Check config.json 'token' field.")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        if not bot.is_closed():
            await bot.close()
        log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
