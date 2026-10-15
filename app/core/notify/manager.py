"""NotificationManager: fan-out messages to enabled channels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...utils.logger import logger
from .base import Message, SendResult, get_notifier, list_notifiers


class NotificationManager:
    """Sends a Message via every enabled channel (or an explicit subset)."""

    def __init__(self, notify_config_getter: Callable[[], dict[str, Any]]) -> None:
        # 配置必须惰性读取：settings 写入会整体重建嵌套 dict（deep_merge 生成
        # 新对象），按引用捕获的旧 dict 会与新配置脱钩
        self._get_notify_config = notify_config_getter

    async def send(self, message: Message, channels: list[str] | None = None) -> list[SendResult]:
        """Push ``message``. ``channels`` limits fan-out; None = all enabled."""
        notify_config = self._get_notify_config() or {}
        wanted = channels or [c["name"] for c in list_notifiers()]
        results: list[SendResult] = []
        for name in wanted:
            try:
                notifier_cls = get_notifier(name)
            except KeyError:
                logger.warning(f"unknown notify channel {name!r}, skipped")
                continue

            channel_config = notify_config.get(name) or {}
            if not channel_config.get("enabled"):
                if channels:
                    # explicit request for this channel -> report it's disabled
                    results.append(SendResult(name, False, "channel disabled"))
                continue

            try:
                result = await notifier_cls().send(message, channel_config)
            except Exception as exc:
                result = SendResult(name, False, f"unexpected error: {exc}")
            results.append(result)
            log = logger.info if result.ok else logger.warning
            log(f"notify[{name}] {'ok' if result.ok else 'failed'}: {result.detail}")

        return results

    async def send_test(self, channel: str) -> SendResult:
        """Send a canned message through one channel (settings page test button)."""
        message = Message(
            title="PriceBot 测试推送",
            body="如果你看到这条消息，说明该渠道配置正确 ✅",
            group="PriceBot",
            severity="info",
        )
        results = await self.send(message, channels=[channel])
        return results[0] if results else SendResult(channel, False, "no result")


__all__ = ["NotificationManager"]
