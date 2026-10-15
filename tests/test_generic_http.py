"""通用 HTTP 源提取逻辑单测（httpx.MockTransport，不打真网）。"""

from __future__ import annotations

import httpx
import pytest

import app.core.sources.generic_http as generic_mod
from app.core.sources.base import SourceError
from app.core.sources.generic_http import GenericHTTPSource, extract_json_path


class TestJsonPath:
    def test_nested(self):
        assert extract_json_path({"a": {"b": {"c": 1}}}, "a.b.c") == 1

    def test_list_index(self):
        assert extract_json_path({"items": [{"p": 1}, {"p": 2}]}, "items[1].p") == 2

    def test_missing_raises(self):
        with pytest.raises((KeyError, TypeError, IndexError)):
            extract_json_path({"a": 1}, "a.b")


@pytest.fixture
def mock_transport(monkeypatch):
    """把 generic_http 模块里的 AsyncClient 换成带 MockTransport 的版本。"""

    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(generic_mod.httpx, "AsyncClient", patched_client)

    return install


class TestGenericFetch:
    async def test_json_path_extract(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "api.test"
            return httpx.Response(200, json={"data": {"price": "895.5"}})

        mock_transport(handler)
        src = GenericHTTPSource()
        quote = await src.fetch("X", {"url": "https://api.test/p", "json_path": "data.price"})
        assert quote.last == 895.5
        assert quote.symbol == "X"

    async def test_regex_extract(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='<span id="p">金价: 892.30 元/克</span>')

        mock_transport(handler)
        quote = await GenericHTTPSource().fetch(
            "X",
            {"url": "https://api.test/p", "regex": r"金价:\s*([0-9.]+)"},
        )
        assert quote.last == 892.30

    async def test_pure_number_body(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="123.45")

        mock_transport(handler)
        quote = await GenericHTTPSource().fetch("X", {"url": "https://api.test/p"})
        assert quote.last == 123.45

    async def test_missing_url_raises(self):
        with pytest.raises(SourceError):
            await GenericHTTPSource().fetch("X", {})

    async def test_http_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        mock_transport(handler)
        with pytest.raises(SourceError):
            await GenericHTTPSource().fetch("X", {"url": "https://api.test/p"})

    async def test_non_numeric_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"price": "abc"}})

        mock_transport(handler)
        with pytest.raises(SourceError):
            await GenericHTTPSource().fetch(
                "X", {"url": "https://api.test/p", "json_path": "data.price"}
            )

    async def test_json_path_miss_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"other": 1})

        mock_transport(handler)
        with pytest.raises(SourceError):
            await GenericHTTPSource().fetch(
                "X", {"url": "https://api.test/p", "json_path": "data.price"}
            )

    async def test_regex_miss_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="nothing here")

        mock_transport(handler)
        with pytest.raises(SourceError):
            await GenericHTTPSource().fetch(
                "X", {"url": "https://api.test/p", "regex": r"(missing)"}
            )
