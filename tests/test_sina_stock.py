"""新浪 A股数据源单测（GBK 行情串解析 + MockTransport 网络层）。"""

from __future__ import annotations

import httpx
import pytest

import app.core.sources.sina_stock as stock_mod
from app.core.sources.base import SourceError
from app.core.sources.sina_stock import SinaStockSource

# 2026-10-15 实测样本（茅台）
_MAOTAI = (
    "贵州茅台,1286.000,1286.000,1312.970,1317.760,1282.000,1312.310,1312.970,"
    "5767722,7537706224.000,300,1312.310,100,1312.010,500,1312.000,200,1311.990,"
    "200,1311.900,818,1312.970,300,1312.990,2600,1313.000,1500,1313.010,100,1313.020,"
    "2026-10-15,15:34:59,00"
)

# 上证指数样本（指数单位应为「点」）
_SH_INDEX = (
    "上证指数,3710.6954,3767.2271,3707.4760,3724.5611,3674.8167,0,0,"
    "510163189,774391973455,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
    "2026-10-15,15:35:27,00"
)


def _payload(symbol: str, fields: str) -> bytes:
    return f'var hq_str_{symbol}="{fields}";\n'.encode("gbk")


# 2026-10-21 实测样本（腾讯控股 rt_hk00700）
_TENCENT_HK = (
    "TENCENT,腾讯控股,412.000,410.400,413.400,393.800,393.800,-16.600,-4.045,"
    "393.600,393.800,15135231021.300,37783835,14.306,0.000,656.353,393.800,"
    "2026/10/21,16:08:20,100|0,N|Y|Y,395.000|375.400|414.600,0|||0.000|0.000|0.000, |0,Y"
)


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(stock_mod.httpx, "AsyncClient", patched_client)

    return install


class TestSinaStockParse:
    async def test_stock_fields(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "sh600519" in str(request.url)
            return httpx.Response(200, content=_payload("sh600519", _MAOTAI))

        mock_transport(handler)
        quote = await SinaStockSource().fetch("SH600519")  # 大小写归一
        assert quote.name == "贵州茅台"
        assert quote.last == 1312.970
        assert quote.prev_close == 1286.000
        assert quote.open == 1286.000
        assert quote.high == 1317.760
        assert quote.low == 1282.000
        assert quote.bid == 1312.310
        assert quote.ask == 1312.970
        assert quote.volume == 5767722  # 股
        assert quote.turnover == 7537706224.0  # 元
        assert quote.time == "2026-10-15 15:34:59"
        assert quote.unit == "元"
        # 涨跌幅：较昨收 +2.09%
        assert quote.extra["change_pct"] == pytest.approx(2.093, abs=0.01)

    async def test_index_unit_is_point(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_payload("sh000001", _SH_INDEX))

        mock_transport(handler)
        quote = await SinaStockSource().fetch("sh000001")
        assert quote.name == "上证指数"
        assert quote.last == 3707.4760
        assert quote.unit == "点"
        # 指数买一/卖一为 0 -> None
        assert quote.bid is None
        assert quote.ask is None

    async def test_hk_stock_fields(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "rt_hk00700" in str(request.url)
            return httpx.Response(200, content=_payload("rt_hk00700", _TENCENT_HK))

        mock_transport(handler)
        quote = await SinaStockSource().fetch("HK00700")  # 大小写归一
        assert quote.name == "腾讯控股"
        assert quote.last == 393.800
        assert quote.prev_close == 410.400
        assert quote.open == 412.000
        assert quote.high == 413.400
        assert quote.low == 393.800
        assert quote.bid == 393.600
        assert quote.ask == 393.800
        assert quote.volume == 37783835  # 股
        assert quote.turnover == 15135231021.3  # 港元
        assert quote.time == "2026-10-21 16:08:20"
        assert quote.unit == "港元"
        assert quote.extra["change_pct"] == pytest.approx(-4.045, abs=0.01)

    async def test_invalid_symbol_rejected(self):
        with pytest.raises(SourceError, match="invalid stock symbol"):
            await SinaStockSource().fetch("AAPL")
        with pytest.raises(SourceError, match="invalid stock symbol"):
            await SinaStockSource().fetch("sh60051")

    async def test_empty_payload_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_payload("sh600519", ""))

        mock_transport(handler)
        with pytest.raises(SourceError, match=r"empty payload|no usable price"):
            await SinaStockSource().fetch("sh600519")

    async def test_http_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        mock_transport(handler)
        with pytest.raises(SourceError, match="HTTP 403"):
            await SinaStockSource().fetch("sh600519")
