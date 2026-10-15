"""Bark 推送单测（MockTransport，验证 URL 构造与多设备分发）。"""

from __future__ import annotations

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
    async def test_url_contains_all_params(self, install_bark_transport):
        requests = install_bark_transport(success_handler)
        result = await BarkNotifier().send(
            Message(title="金价提醒", body="上金所黄金9999 现价 900.50", url="https://example.com"),
            CONFIG,
        )
        assert result.ok is True
        assert len(requests) == 2  # 两个设备各一条

        url = str(requests[0].url)
        assert "https://api.day.app/key1/" in url
        assert "group=Gold" in url
        assert "sound=minuet" in url
        assert "level=timeSensitive" in url
        assert "%E9%87%91%E4%BB%B7%E6%8F%90%E9%86%92" in url  # 金价提醒 URL 编码
        assert "/key2/" in str(requests[1].url)

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
        assert str(requests[0].url).startswith("https://bark.selfhost.cn/key1/")
