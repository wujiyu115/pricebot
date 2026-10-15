"""Binance 公共行情镜像源（加密货币，仅技术演示）。

接口: GET https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT
data-api.binance.vision 是 Binance 官方只读公共数据镜像，无需鉴权；
api.binance.com 主站在部分网络不可达（2026-10 实测），镜像通常可达。
返回 JSON（注意：非 GBK 行情串）。7x24 交易，schedule 用 "always"。

字段（2026-10 实测）:
  lastPrice/bidPrice/askPrice, openPrice(=24h 涨跌幅基准), highPrice/lowPrice(24h),
  volume(基础币)/quoteVolume(计价币), priceChangePercent, closeTime(ms)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, ClassVar

import httpx

from .base import Quote, SourceAdapter, SourceError, parse_float, register

_BASE_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")


@register
class BinanceSource(SourceAdapter):
    name = "binance"
    description = "Binance 公共行情镜像（加密货币 USDT 交易对，仅技术演示）"
    homepage = "https://data-api.binance.vision"
    known_symbols: ClassVar[dict[str, str]] = {
        "BTCUSDT": "比特币",
        "ETHUSDT": "以太坊",
        "SOLUSDT": "Solana",
        "BNBUSDT": "BNB",
        "XRPUSDT": "瑞波币",
        "DOGEUSDT": "狗狗币",
    }

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        symbol = symbol.strip().upper()
        if not _SYMBOL_RE.match(symbol):
            raise SourceError(f"invalid symbol: {symbol!r} (expect e.g. BTCUSDT/ETHUSDT)")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(_BASE_URL, params={"symbol": symbol})
        if resp.status_code == 400:
            # Binance 对未知交易对返回 400 + {"code":-1121,...}
            raise SourceError(f"binance invalid symbol: {symbol}")
        if resp.status_code != 200:
            raise SourceError(f"binance HTTP {resp.status_code} for {symbol}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError(f"binance bad payload for {symbol}: {exc}") from exc

        last = parse_float(data.get("lastPrice"))
        if last is None:
            raise SourceError(f"binance no usable price for {symbol}")
        # 24h 涨跌幅基准 = openPrice（priceChangePercent 与其一致）
        base_24h = parse_float(data.get("openPrice"))
        close_time = data.get("closeTime")
        time_str = (
            datetime.fromtimestamp(int(close_time) / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if close_time
            else ""
        )

        return Quote(
            symbol=symbol,
            name=f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith("USDT") else symbol,
            last=last,
            bid=parse_float(data.get("bidPrice")),
            ask=parse_float(data.get("askPrice")),
            open=base_24h,
            high=parse_float(data.get("highPrice")),
            low=parse_float(data.get("lowPrice")),
            prev_close=base_24h,  # 24h 涨跌幅基准
            volume=parse_float(data.get("volume")),
            turnover=parse_float(data.get("quoteVolume")),
            time=time_str,
            unit="USDT",
            extra={
                "change_pct": parse_float(data.get("priceChangePercent")),
                "change_24h": parse_float(data.get("priceChange")),
            },
        )


__all__ = ["BinanceSource"]
