"""新浪财经行情源（上金所实时价）。

接口: GET https://hq.sinajs.cn/list=SGE_AU9999,SGE_AUTD
需要 Referer: https://finance.sina.com.cn，GBK 编码。

字段布局（2026-10 实测验证，见 AGENTS.md）:
  [0]代码 [1]名称 [2]合约 [3]今开 [4]昨结 [5]昨收 [6]? [7]最高
  [8]最低 [9]买一 [10]卖一 [11]最新价 [14]持仓量 [15]成交额 [16]时间 [17]涨跌幅%
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


@register
class SinaSource(SourceAdapter):
    name = "sina"
    description = "新浪财经行情（上金所现货/延期实时报价，含买卖盘）"
    homepage = "https://finance.sina.com.cn"
    known_symbols: ClassVar[dict[str, str]] = {
        "SGE_AU9999": "上金所 黄金9999 (Au99.99)",
        "SGE_AU9995": "上金所 黄金9995 (Au99.95)",
        "SGE_AU100G": "上金所 黄金100g",
        "SGE_AUTD": "上金所 黄金T+D (Au(T+D))",
        "SGE_MAUTD": "上金所 迷你黄金T+D (mAu(T+D))",
        "SGE_AGTD": "上金所 白银T+D (Ag(T+D))",
        "SGE_PTA": "上金所 铂金9995 (Pt99.95)",
    }

    def __init__(self, timeout: float = 10.0) -> None:
        super().__init__(timeout=timeout)

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        symbol = symbol.strip().upper()
        url = f"https://hq.sinajs.cn/list={symbol}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=_HEADERS) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise SourceError(f"sina HTTP {resp.status_code} for {symbol}")
        try:
            text = resp.content.decode("gbk", errors="strict")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise SourceError(f"sina decode error for {symbol}: {exc}") from exc

        match = re.search(r'"([^"]*)"', text)
        if not match:
            raise SourceError(f"sina empty payload for {symbol} (rate-limited?)")
        fields = match.group(1).split(",")
        if len(fields) < 12 or fields[11] in {"", "--"}:
            raise SourceError(f"sina no usable price for {symbol}")

        return Quote(
            symbol=symbol,
            name=fields[1].strip() if len(fields) > 1 else "",
            last=parse_float(fields[11]),
            bid=parse_float(fields[9]) if len(fields) > 9 else None,
            ask=parse_float(fields[10]) if len(fields) > 10 else None,
            open=parse_float(fields[3]) if len(fields) > 3 else None,
            high=parse_float(fields[7]) if len(fields) > 7 else None,
            low=parse_float(fields[8]) if len(fields) > 8 else None,
            prev_close=parse_float(fields[5]) if len(fields) > 5 else None,
            volume=parse_float(fields[14]) if len(fields) > 14 else None,
            turnover=parse_float(fields[15]) if len(fields) > 15 else None,
            time=fields[16] if len(fields) > 16 else "",
            unit="元/克",
        )


__all__ = ["SinaSource"]
