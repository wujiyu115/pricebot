"""测试共享：fake 数据源 / fake 推送渠道（模块级收集器）。"""

from __future__ import annotations

from typing import Any, ClassVar

from app.core.notify.base import Message, Notifier, SendResult, register
from app.core.sources.base import (
    Quote,
    SourceAdapter,
    SourceError,
)
from app.core.sources.base import (
    register as register_source,
)

# 收集到的推送消息（测试断言用）
PUSHED: list[tuple[str, Message]] = []


@register_source
class FakeSource(SourceAdapter):
    """可编程 fake 数据源：quotes 按序出价，用完抛 SourceError。"""

    name = "fake_test"
    description = "fake source for tests"
    known_symbols: ClassVar[dict[str, str]] = {"FAKE_GOLD": "测试黄金"}
    # 类属性：测试里赋值后所有实例共享（engine 每次 tick 都新建实例）
    quotes: ClassVar[list[Quote]] = []

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        if not self.quotes:
            raise SourceError("fake source exhausted")
        return self.quotes.pop(0)


@register
class FakeNotifier(Notifier):
    name = "fake_push"
    display_name = "测试推送"
    config_keys: ClassVar[list[str]] = []

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        PUSHED.append((self.name, message))
        return SendResult(self.name, True, "captured")


def reset_collectors() -> None:
    PUSHED.clear()
    FakeSource.quotes = []  # type: ignore[assignment]
