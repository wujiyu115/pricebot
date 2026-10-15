"""Background asyncio loop service (StreamCap 同款模式).

监控引擎跑在独立后台线程的事件循环里，API（uvicorn loop）需要操作引擎时
用 :func:`run_coro` 把协程投递过去，再 ``asyncio.wrap_future`` 等结果——
避免跨 event loop await 原语的坑（见 AGENTS.md「跨 event loop」）。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

from ...utils.logger import logger


class BackgroundLoop:
    """Runs an asyncio loop in a daemon thread; exposes submit helpers."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._main_task: asyncio.Task[None] | None = None
        self._ready = threading.Event()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def start(self, main_coro_factory, name: str = "background") -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()

        async def _main() -> None:
            self._loop = asyncio.get_running_loop()
            self._main_task = asyncio.current_task()
            self._ready.set()
            try:
                await main_coro_factory()
            except asyncio.CancelledError:
                logger.info("background loop cancelled")

        def _run() -> None:
            asyncio.run(_main())

        self._thread = threading.Thread(target=_run, name=name, daemon=True)
        self._thread.start()
        # 等 loop 就绪，保证 run_coro 提交时 loop 一定存在
        if not self._ready.wait(timeout=10):
            raise RuntimeError("background loop failed to start")
        logger.info(f"background loop thread started: {name}")

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():

            def _cancel_main() -> None:
                if self._main_task and not self._main_task.done():
                    self._main_task.cancel()

            loop.call_soon_threadsafe(_cancel_main)
        if self._thread:
            self._thread.join(timeout=10)
        self._loop = None
        self._thread = None
        self._main_task = None
        logger.info("background loop stopped")


def run_coro(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, Any]) -> Future:
    """Submit a coroutine to the background loop from another thread."""
    return asyncio.run_coroutine_threadsafe(coro, loop)


async def resolve_on_loop(future: Future) -> Any:
    """Await a ``run_coroutine_threadsafe`` future from a foreign loop."""
    return await asyncio.wrap_future(future)


__all__ = ["BackgroundLoop", "resolve_on_loop", "run_coro"]
