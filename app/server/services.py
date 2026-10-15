"""应用服务容器：组装配置/存储/引擎/后台循环。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from ..core.config.settings import ConfigManager
from ..core.monitor.engine import MonitorEngine
from ..core.monitor.services import BackgroundLoop
from ..core.monitor.store import Store
from ..core.monitor.stores import RuleStore, TargetStore
from ..core.notify import load_builtin_notifiers
from ..core.notify.manager import NotificationManager
from ..core.sources import load_builtin_sources
from ..utils.logger import logger


class AppServices:
    """Owns every long-lived object; FastAPI lifespan bootstrap/teardown it."""

    def __init__(self, run_path: str) -> None:
        root = Path(run_path)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        load_builtin_sources()
        load_builtin_notifiers()

        self.config_manager = ConfigManager(root / "config")
        self.target_store = TargetStore(data_dir / "targets.json")
        self.rule_store = RuleStore(data_dir / "rules.json")
        retention = int(
            self.config_manager.user_config.get("monitor", {}).get("history_retention_days") or 90
        )
        self.store = Store(data_dir / "pricebot.db", retention_days=retention)
        self.notifier = NotificationManager(
            lambda: self.config_manager.user_config.get("notify", {})
        )
        self.engine = MonitorEngine(
            target_store=self.target_store,
            rule_store=self.rule_store,
            store=self.store,
            notifier=self.notifier,
            monitor_config_getter=lambda: self.config_manager.user_config.get("monitor", {}),
        )
        self.loop_service = BackgroundLoop()

    # ------------------------------------------------------------------ async
    async def run_bg(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Run a coroutine on the background loop; await from the API loop."""
        loop = self.loop_service.loop
        if loop is None or not loop.is_running():
            raise RuntimeError("monitor loop not running")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wrap_future(future)

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.loop_service.start(self.engine.run_forever, name="pricebot-monitor")
        logger.info("AppServices started")

    def stop(self) -> None:
        self.engine.stop()
        self.loop_service.stop()
        self.store.close()
        logger.info("AppServices stopped")


__all__ = ["AppServices"]

