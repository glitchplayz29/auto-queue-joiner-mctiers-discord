"""
Minimal rotating file logger.
- No console output by default (reduces I/O on VPS)
- Max 5MB per file, keeps 2 backups → max 15MB disk usage
- Thread-safe (asyncio-compatible via stdlib logging)
"""

import logging
from logging.handlers import RotatingFileHandler
import sys

_initialized = False


def setup_logging(log_file: str = "bot.log", max_bytes: int = 5_242_880, backup_count: int = 2):
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating file handler — primary output
    fh = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)

    # Minimal stderr for critical errors only (visible in systemd journal)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(logging.ERROR)
    root.addHandler(sh)

    # Silence noisy third-party loggers
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("selfcord").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
