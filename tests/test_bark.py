"""Bark 推送单测（MockTransport，验证 POST /push 载荷构造与多设备分发）。"""

from __future__ import annotations

import json

import httpx
import pytest

import app.core.notify.bark as bark_mod
from app.core.notify.bark import BarkNotifier
from app.core.notify.base import Message


@pytest.fixture
def install_bark_transport(monkeypatch):
    """返回 install(handler) -> captured_requests；handler 处理请求并返回响应。"""

    def install(handler):
        requests: list[httpx.Request] = []

        def wrapper(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(wrapper)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(bark_mod.httpx, "AsyncClient", patched_client)
        return requests

    return install


CONFIG = {
    "server": "https://api.day.app",
    "device_keys": "key1,key2",
    "group": "Gold",
    "sound": "minuet",
    "icon": "",
    "level": "timeSensitive",
}


def success_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"code": 200, "message": "success"})


class TestBark:
    async def test_post_payload_contains_all_params(self, install_bark_transport):
        requests = install_bark_transport(success_handler)
        result = await BarkNotifier().send(
            Message(title="金价提醒", body="上金所黄金9999 现价 900.50", url="https://example.com"),
            CONFIG,
        )
        assert result.ok is True
        assert len(requests) == 2  # 两个设备各一条

        # POST /push + JSON 体（长正文不再走 URL 路径，聚合简报不炸）
        req0 = requests[0]
        assert req0.method == "POST"
        assert str(req0.url) == "https://api.day.app/push"
        payload = json.loads(req0.content.decode("utf-8"))
        assert payload["device_key"] == "key1"
        assert payload["title"] == "金价提醒"
        assert payload["body"] == "上金所黄金9999 现价 900.50"
        assert payload["group"] == "Gold"
        assert payload["sound"] == "minuet"
        assert payload["level"] == "timeSensitive"
        assert payload["url"] == "https://example.com"
        assert json.loads(requests[1].content.decode("utf-8"))["device_key"] == "key2"

    async def test_long_multiline_body_ok(self, install_bark_transport):
        """聚合简报式长多行正文（含分隔线/换行）必须能发出去。"""
        requests = install_bark_transport(success_handler)
        body = "\n".join(
            [f"标的{i}：{100 + i}.00 元（较昨收 +0.{i}%）" for i in range(1, 11)]
            + ["─────", "简报间隔：每 1 天一次", "时间：2026-12-31 23:59:59"]
        )
        result = await BarkNotifier().send(Message(title="📊 价格简报 · 10 个标的", body=body), CONFIG)
        assert result.ok is True
        assert len(requests) == 2

    async def test_no_device_keys_fails(self, install_bark_transport):
        requests = install_bark_transport(success_handler)
        result = await BarkNotifier().send(Message(title="t", body="b"), {"device_keys": ""})
        assert result.ok is False
        assert "device_keys" in result.detail
        assert requests == []

    async def test_upstream_error_reported(self, install_bark_transport):
        def failing_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 400, "message": "bad key"})

        requests = install_bark_transport(failing_handler)
        result = await BarkNotifier().send(Message(title="t", body="b"), CONFIG)
        assert result.ok is False
        assert "bad key" in result.detail
        assert len(requests) == 2

    async def test_custom_server(self, install_bark_transport):
        requests = install_bark_transport(success_handler)
        config = dict(CONFIG, server="https://bark.selfhost.cn/")
        await BarkNotifier().send(Message(title="t", body="b"), config)
        assert str(requests[0].url) == "https://bark.selfhost.cn/push"
