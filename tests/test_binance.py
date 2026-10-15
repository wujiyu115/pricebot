"""Binance 公共行情镜像源单测（2026-10 实测 payload fixture）。"""

from __future__ import annotations

import httpx
import pytest

import app.core.sources.binance as binance_mod
from app.core.sources.base import SourceError
from app.core.sources.binance import BinanceSource

# 2026-10-16 实测样本（节选关键字段）
_BTC = {
    "symbol": "BTCUSDT",
    "priceChange": "555.15000000",
    "priceChangePercent": "0.677",
    "lastPrice": "82538.40000000",
    "bidPrice": "82537.63000000",
    "askPrice": "82537.64000000",
    "openPrice": "81983.25000000",
    "highPrice": "82634.30000000",
    "lowPrice": "79800.00000000",
    "volume": "22634.83580000",
    "quoteVolume": "1840194271.77753510",
    "closeTime": 1792084672011,
}


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(binance_mod.httpx, "AsyncClient", patched_client)

    return install


class TestBinanceParse:
    async def test_btc_fields(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "symbol=BTCUSDT" in str(request.url)
            return httpx.Response(200, json=_BTC)

        mock_transport(handler)
        quote = await BinanceSource().fetch("btcusdt")  # 大小写归一
        assert quote.symbol == "BTCUSDT"
        assert quote.name == "BTC/USDT"
        assert quote.last == 82538.4
        assert quote.bid == 82537.63
        assert quote.ask == 82537.64
        assert quote.open == 81983.25
        assert quote.high == 82634.3
        assert quote.low == 79800.0
        assert quote.prev_close == 81983.25  # 24h 涨跌幅基准 = openPrice
        assert quote.volume == 22634.8358
        assert quote.turnover == pytest.approx(1840194271.7775, abs=0.01)
        assert quote.unit == "USDT"
        assert quote.extra["change_pct"] == 0.677
        assert quote.extra["change_24h"] == 555.15
        assert quote.time.startswith("2026-10-")

    async def test_eth_naming(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={**_BTC, "symbol": "ETHUSDT"})

        mock_transport(handler)
        quote = await BinanceSource().fetch("ETHUSDT")
        assert quote.name == "ETH/USDT"

    async def test_invalid_symbol_rejected(self):
        with pytest.raises(SourceError, match="invalid symbol"):
            await BinanceSource().fetch("BTC")

    async def test_unknown_pair_400(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

        mock_transport(handler)
        with pytest.raises(SourceError, match="invalid symbol"):
            await BinanceSource().fetch("XXXXUSDT")

    async def test_http_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502)

        mock_transport(handler)
        with pytest.raises(SourceError, match="HTTP 502"):
            await BinanceSource().fetch("BTCUSDT")

    async def test_bad_payload_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not json")

        mock_transport(handler)
        with pytest.raises(SourceError, match="bad payload"):
            await BinanceSource().fetch("BTCUSDT")

    async def test_no_price_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"symbol": "BTCUSDT"})

        mock_transport(handler)
        with pytest.raises(SourceError, match="no usable price"):
            await BinanceSource().fetch("BTCUSDT")
