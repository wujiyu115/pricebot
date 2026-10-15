"""新浪 A股行情源（价格、涨跌幅、五档盘口）。

接口: GET https://hq.sinajs.cn/list=sh600519,sz000001,sh000001
需要 Referer: https://finance.sina.com.cn，GBK 编码。
代码规则: sh/sz/bj + 6 位数字；sh000xxx / sz399xxx 为指数（单位: 点）。

字段布局（2026-10 实测验证，见 AGENTS.md）:
  [0]名称 [1]今开 [2]昨收 [3]最新价 [4]最高 [5]最低 [6]买一价 [7]卖一价
  [8]成交量(股) [9]成交额(元) [10-29]五档量价 [30]日期 [31]时间
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

import httpx

from .base import Quote, SourceAdapter, SourceError, parse_float, register

_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

_SYMBOL_RE = re.compile(r"^(sh|sz|bj)\d{6}$")
_INDEX_RE = re.compile(r"^(sh000|sz399)\d{3}$")


@register
class SinaStockSource(SourceAdapter):
    name = "sina_stock"
    description = "新浪 A股行情（沪深京股票/指数：最新价、涨跌幅、五档盘口）"
    homepage = "https://finance.sina.com.cn"
    known_symbols: ClassVar[dict[str, str]] = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sh600519": "贵州茅台",
        "sz000001": "平安银行",
        "sz300750": "宁德时代",
        "sh601318": "中国平安",
        "sh600036": "招商银行",
    }

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        symbol = symbol.strip().lower()
        if not _SYMBOL_RE.match(symbol):
            raise SourceError(f"invalid A-share symbol: {symbol!r} (expect sh/sz/bj + 6 digits)")

        url = f"https://hq.sinajs.cn/list={symbol}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=_HEADERS) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise SourceError(f"sina_stock HTTP {resp.status_code} for {symbol}")
        try:
            text = resp.content.decode("gbk", errors="strict")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise SourceError(f"sina_stock decode error for {symbol}: {exc}") from exc

        match = re.search(r'"([^"]*)"', text)
        if not match or not match.group(1):
            raise SourceError(f"sina_stock empty payload for {symbol} (rate-limited?)")
        fields = match.group(1).split(",")
        if len(fields) < 32 or (fields[3] in {"", "0.000"} and fields[0] == ""):
            raise SourceError(f"sina_stock no usable price for {symbol}")

        last = parse_float(fields[3])
        if last is None:
            raise SourceError(f"sina_stock no usable price for {symbol}")
        prev_close = parse_float(fields[2])
        unit = "点" if _INDEX_RE.match(symbol) else "元"

        def _side(value: str | None) -> float | None:
            # 指数无买卖盘（0 值），归一化为 None
            parsed = parse_float(value)
            return parsed if parsed and parsed > 0 else None

        return Quote(
            symbol=symbol,
            name=fields[0],
            last=last,
            bid=_side(fields[6]),
            ask=_side(fields[7]),
            open=parse_float(fields[1]),
            high=parse_float(fields[4]),
            low=parse_float(fields[5]),
            prev_close=prev_close,
            volume=parse_float(fields[8]),
            turnover=parse_float(fields[9]),
            time=f"{fields[30]} {fields[31]}" if len(fields) > 31 else "",
            unit=unit,
            extra={"change_pct": self._change_pct(last, prev_close)},
        )

    @staticmethod
    def _change_pct(last: float, prev_close: float | None) -> float | None:
        if not prev_close:
            return None
        return (last - prev_close) / prev_close * 100.0


__all__ = ["SinaStockSource"]
