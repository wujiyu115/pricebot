"""Ntfy 推送单测（MockTransport，含 priority 整数契约）。"""

from __future__ import annotations

import httpx
import pytest

import app.core.notify.ntfy as ntfy_mod
from app.core.notify.base import Message
from app.core.notify.ntfy import NtfyNotifier


@pytest.fixture
def capture(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        import json

        body = json.loads(request.content)
        if not body.get("topic"):
            return httpx.Response(400, json={"code": 40024, "error": "invalid request"})
        return httpx.Response(200, json={"id": "x", "event": "message", "topic": body["topic"]})

    real_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ntfy_mod.httpx, "AsyncClient", patched_client)
    return requests


CONFIG = {
    "server": "https://ntfy.sh",
    "topic": "my-pricebot-x7k2",
    "priority": "high",
    "tags": "chart_with_upwards_trend",
}


class TestNtfy:
    async def test_publish_payload_contract(self, capture):
        result = await NtfyNotifier().send(
            Message(title="🟢 黄金上穿阈值", body="现价 900.50 元/克"), CONFIG
        )
        assert result.ok is True
        assert len(capture) == 1

        import json

        body = json.loads(capture[0].content)
        assert str(capture[0].url) == "https://ntfy.sh/"
        assert body["topic"] == "my-pricebot-x7k2"
        assert body["title"] == "🟢 黄金上穿阈值"
        # 关键契约: JSON 体里 priority 必须是整数（字符串会得到误导性 400 invalid JSON）
        assert body["priority"] == 4
        assert body["tags"] == ["chart_with_upwards_trend"]
        assert "click" not in body  # 无 url 时不下发 click

    async def test_click_url_when_message_has_url(self, capture):
        result = await NtfyNotifier().send(
            Message(
                title="🟢 好价提醒",
                body="action6 2293.30 元",
                url="https://post.smzdm.com/p/abc/",
            ),
            CONFIG,
        )
        assert result.ok is True
        import json

        body = json.loads(capture[0].content)
        # message.url → ntfy 官方 click 字段：点击通知直接跳转
        assert body["click"] == "https://post.smzdm.com/p/abc/"

    async def test_priority_aliases_and_int(self, capture):
        notifier = NtfyNotifier()
        for alias, expected in [("urgent", 5), ("min", 1), ("2", 2), ("", 4)]:
            config = dict(CONFIG, priority=alias, topic="t-ok")
            result = await notifier.send(Message(title="t", body="b"), config)
            assert result.ok is True
            import json

            body = json.loads(capture[-1].content)
            assert body["priority"] == expected, f"priority {alias!r} 应映射为 {expected}"

    async def test_no_topic_fails(self, capture):
        result = await NtfyNotifier().send(Message(title="t", body="b"), {"topic": ""})
        assert result.ok is False
        assert "topic" in result.detail
        assert capture == []

    async def test_invalid_topic_rejected(self, capture):
        result = await NtfyNotifier().send(
            Message(title="t", body="b"), dict(CONFIG, topic="not/allowed")
        )
        assert result.ok is False
        assert "invalid topic" in result.detail

    async def test_upstream_400_reported(self, capture):
        result = await NtfyNotifier().send(
            Message(title="t", body="b"), dict(CONFIG, topic="")
        )
        assert result.ok is False

    async def test_custom_server(self, capture):
        result = await NtfyNotifier().send(
            Message(title="t", body="b"),
            dict(CONFIG, server="http://nas.local:8090/"),
        )
        assert result.ok is True
        assert str(capture[0].url) == "http://nas.local:8090/"
