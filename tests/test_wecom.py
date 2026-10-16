"""企业微信机器人推送单测（MockTransport，payload 契约 + errcode 判定）。"""

from __future__ import annotations

import json

import httpx
import pytest

import app.core.notify.wecom as wecom_mod
from app.core.notify.base import Message
from app.core.notify.wecom import WeComNotifier

_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=testkey123"


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def wrapper(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(wrapper)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(wecom_mod.httpx, "AsyncClient", patched_client)
        return requests

    return install


class TestWeCom:
    async def test_markdown_payload_contract(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

        requests = mock_transport(handler)
        result = await WeComNotifier().send(
            Message(title="黄金上穿阈值", body="现价 900.50 元/克"), {"webhook_url": _URL}
        )
        assert result.ok is True
        assert str(requests[0].url) == _URL

        body = json.loads(requests[0].content)
        assert body["msgtype"] == "markdown"
        assert body["markdown"]["content"].startswith("**黄金上穿阈值**")
        assert "900.50" in body["markdown"]["content"]

    async def test_errcode_nonzero_reported(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            # 无效 key 的真实响应格式（2026-10 实测）
            return httpx.Response(200, json={"errcode": 93000, "errmsg": "invalid webhook url"})

        mock_transport(handler)
        result = await WeComNotifier().send(Message(title="t", body="b"), {"webhook_url": _URL})
        assert result.ok is False
        assert "93000" in result.detail
        assert "invalid webhook url" in result.detail

    async def test_no_url_fails(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errcode": 0})

        mock_transport(handler)
        result = await WeComNotifier().send(Message(title="t", body="b"), {"webhook_url": ""})
        assert result.ok is False
        assert "webhook_url" in result.detail

    async def test_oversize_message_truncated(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

        requests = mock_transport(handler)
        long_body = "很长的价格提醒" * 200  # ~1200 chars × 3 bytes > 4000B
        result = await WeComNotifier().send(Message(title="t", body=long_body), {"webhook_url": _URL})
        assert result.ok is True
        body = json.loads(requests[0].content)
        assert len(body["markdown"]["content"].encode("utf-8")) <= 4000

    async def test_http_error_raises_detail(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, text="bad gateway")

        mock_transport(handler)
        result = await WeComNotifier().send(Message(title="t", body="b"), {"webhook_url": _URL})
        assert result.ok is False
        assert "502" in result.detail
