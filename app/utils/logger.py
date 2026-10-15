"""Loguru-based logging shared by the whole app."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logger(log_dir: str | Path = "logs") -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", format=_FORMAT)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.add(
        Path(log_dir) / "pricebot_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        level="INFO",
        format=_FORMAT,
        encoding="utf-8",
        enqueue=True,
    )


__all__ = ["logger", "setup_logger"]
