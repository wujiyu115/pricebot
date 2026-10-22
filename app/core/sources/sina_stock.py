"""新浪 沪深京 A股 + 港股行情源（价格、涨跌幅、五档盘口）。

接口: GET https://hq.sinajs.cn/list=sh600519,sz000001,sh000001 / rt_hk00700
需要 Referer: https://finance.sina.com.cn，GBK 编码。
代码规则: A股 sh/sz/bj + 6 位数字（sh000xxx / sz399xxx 为指数，单位: 点）；
港股 hk + 5 位数字（如 hk00700 腾讯，走 rt_hk 前缀，单位: 港元）。

A股字段布局（2026-10 实测验证，见 AGENTS.md）:
  [0]名称 [1]今开 [2]昨收 [3]最新价 [4]最高 [5]最低 [6]买一价 [7]卖一价
  [8]成交量(股) [9]成交额(元) [10-29]五档量价 [30]日期 [31]时间

港股 rt_hk 字段布局（2026-10 实测验证，样本 00700/00005/01810）:
  [0]英文名 [1]中文名 [2]今开 [3]昨收 [4]最高 [5]最低 [6]最新价
  [7]跌额 [8]涨跌幅% [9]买一价 [10]卖一价 [11]成交额(港元) [12]成交量(股)
  [13]市盈率 [15]52周最高 [16]52周最低 [17]日期(YYYY/MM/DD) [18]时间
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
_HK_RE = re.compile(r"^hk\d{5}$")


@register
class SinaStockSource(SourceAdapter):
    name = "sina_stock"
    description = "新浪 股票行情（沪深京 A股/指数 + 港股：最新价、涨跌幅、盘口）"
    homepage = "https://finance.sina.com.cn"
    known_symbols: ClassVar[dict[str, str]] = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sh600519": "贵州茅台",
        "sz000001": "平安银行",
        "sz300750": "宁德时代",
        "sh601318": "中国平安",
        "sh600036": "招商银行",
        "hk00700": "腾讯控股",
        "hk01810": "小米集团",
    }

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        symbol = symbol.strip().lower()
        if _HK_RE.match(symbol):
            return await self._fetch_hk(symbol)
        if not _SYMBOL_RE.match(symbol):
            raise SourceError(
                f"invalid stock symbol: {symbol!r} (A股: sh/sz/bj + 6 digits; 港股: hk + 5 digits)"
            )
        return await self._fetch_a(symbol)

    async def _fetch_raw(self, list_param: str, symbol: str) -> list[str]:
        """请求 hq.sinajs.cn 并拆出逗号分隔字段列表。"""
        url = f"https://hq.sinajs.cn/list={list_param}"
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
        return match.group(1).split(",")

    async def _fetch_a(self, symbol: str) -> Quote:
        fields = await self._fetch_raw(symbol, symbol)
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

    async def _fetch_hk(self, symbol: str) -> Quote:
        """港股（rt_hk 前缀），字段布局见模块 docstring。"""
        fields = await self._fetch_raw(f"rt_hk{symbol[2:]}", symbol)
        if len(fields) < 19:
            raise SourceError(f"sina_stock no usable price for {symbol}")

        last = parse_float(fields[6])
        if last is None:
            raise SourceError(f"sina_stock no usable price for {symbol}")
        prev_close = parse_float(fields[3])

        def _side(value: str) -> float | None:
            parsed = parse_float(value)
            return parsed if parsed and parsed > 0 else None

        raw_date = fields[17].replace("/", "-")
        return Quote(
            symbol=symbol,
            name=fields[1],
            last=last,
            bid=_side(fields[9]),
            ask=_side(fields[10]),
            open=parse_float(fields[2]),
            high=parse_float(fields[4]),
            low=parse_float(fields[5]),
            prev_close=prev_close,
            volume=parse_float(fields[12]),
            turnover=parse_float(fields[11]),
            time=f"{raw_date} {fields[18]}" if fields[18] else raw_date,
            unit="港元",
            extra={"change_pct": self._change_pct(last, prev_close)},
        )

    @staticmethod
    def _change_pct(last: float, prev_close: float | None) -> float | None:
        if not prev_close:
            return None
        return (last - prev_close) / prev_close * 100.0


__all__ = ["SinaStockSource"]
