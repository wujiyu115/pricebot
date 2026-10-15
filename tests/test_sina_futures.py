"""新浪国内期货数据源单测（nf_ 格式解析，2026-10-16 夜盘实测样本）。"""

from __future__ import annotations

import httpx
import pytest

import app.core.sources.sina_futures as futures_mod
from app.core.sources.base import SourceError
from app.core.sources.sina_futures import SinaFuturesSource

# 原油主力连续夜盘实时样本（01:08:24，买729.7/卖729.9/最新729.8 完美夹逼）
_SC0 = (
    "上海原油连续,010824,715.700,732.500,713.700,0.000,729.700,729.900,"
    "729.800,0.000,725.200,1,3,33206.000,65637,沪,上海原油,2026-10-16,1"
)

# 螺纹钢主力连续（日盘收盘后，23:00 夜盘结束）：昨结 3066
_RB0 = (
    "螺纹钢连续,230000,3070.000,3077.000,3061.000,0.000,3073.000,3074.000,"
    "3073.000,0.000,3066.000,132,17,1747036.000,208459,沪,螺纹钢,2026-10-15,1"
)


def _payload(symbol: str, fields: str) -> bytes:
    return f'var hq_str_nf_{symbol}="{fields}";\n'.encode("gbk")


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(futures_mod.httpx, "AsyncClient", patched_client)

    return install


class TestSinaFuturesParse:
    async def test_crude_oil_fields(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "nf_SC0" in str(request.url)  # 必须 nf_ 前缀
            return httpx.Response(200, content=_payload("SC0", _SC0))

        mock_transport(handler)
        quote = await SinaFuturesSource().fetch("sc0")  # 大小写归一
        assert quote.name == "上海原油连续"
        assert quote.last == 729.800
        assert quote.bid == 729.700
        assert quote.ask == 729.900
        assert quote.open == 715.700
        assert quote.high == 732.500
        assert quote.low == 713.700
        assert quote.prev_close == 725.200  # 昨结=涨跌幅基准
        assert quote.volume == 65637
        assert quote.time == "2026-10-16 01:08:24"
        assert quote.unit == "元/桶"  # SC 品种映射
        assert quote.extra["open_interest"] == 33206
        assert quote.extra["market"] == "沪"

    async def test_rebar_default_unit_per_ton(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_payload("RB0", _RB0))

        mock_transport(handler)
        quote = await SinaFuturesSource().fetch("RB0")
        assert quote.name == "螺纹钢连续"
        assert quote.last == 3073.000
        assert quote.unit == "元/吨"  # 缺省单位
        assert quote.time == "2026-10-15 23:00:00"

    async def test_unit_override_via_extra(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_payload("RB0", _RB0))

        mock_transport(handler)
        quote = await SinaFuturesSource().fetch("RB0", {"unit": "custom"})
        assert quote.unit == "custom"

    async def test_invalid_symbol_rejected(self):
        with pytest.raises(SourceError, match="invalid futures symbol"):
            await SinaFuturesSource().fetch("AAPL")
        with pytest.raises(SourceError, match="invalid futures symbol"):
            await SinaFuturesSource().fetch("SC2501")  # 月份合约不支持
        with pytest.raises(SourceError, match="invalid futures symbol"):
            await SinaFuturesSource().fetch("RB")

    async def test_empty_payload_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_payload("SC0", ""))

        mock_transport(handler)
        with pytest.raises(SourceError, match="empty payload"):
            await SinaFuturesSource().fetch("SC0")

    async def test_http_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        mock_transport(handler)
        with pytest.raises(SourceError, match="HTTP 403"):
            await SinaFuturesSource().fetch("SC0")
