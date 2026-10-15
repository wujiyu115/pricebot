"""上金所官网日K源（备用/历史数据）。

接口: POST https://www.sge.com.cn/graph/Dailyhq  (form: instid=Au99.99)
返回 {"time": [[日期, 开盘, 收盘, 最低, 最高], ...]}，按日期升序。

用作「最新价」时取最后一根日K的收盘（收盘后为定值，盘中为最近快照），
并可用 ``days`` 参数拉取历史序列供前端画走势图。
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .base import Quote, SourceAdapter, SourceError, parse_float, register

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.sge.com.cn/sjzx/mrhq",
    "Origin": "https://www.sge.com.cn",
}


@register
class SGEDailySource(SourceAdapter):
    name = "sge_daily"
    description = "上金所官网每日行情（日K收盘价，适合收盘监控与历史走势）"
    homepage = "https://www.sge.com.cn/sjzx/mrhq"
    known_symbols: ClassVar[dict[str, str]] = {
        "Au99.99": "上金所 黄金9999",
        "Au99.95": "上金所 黄金9995",
        "Au100g": "上金所 黄金100g",
        "Au(T+D)": "上金所 黄金T+D",
        "mAu(T+D)": "上金所 迷你黄金T+D",
        "Ag(T+D)": "上金所 白银T+D",
        "Pt99.95": "上金所 铂金9995",
    }

    def __init__(self, timeout: float = 15.0) -> None:
        super().__init__(timeout=timeout)

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        rows = await self.fetch_daily(symbol, days=2)
        if not rows:
            raise SourceError(f"sge_daily empty history for {symbol}")
        date, open_, close, low, high = rows[-1]
        return Quote(
            symbol=symbol,
            name=self.known_symbols.get(symbol, symbol),
            last=close,
            open=open_,
            high=high,
            low=low,
            time=f"{date} 00:00:00",
            extra={"daily": True},
        )

    async def fetch_daily(self, symbol: str, days: int = 120) -> list[list[Any]]:
        """Return daily K rows ``[date, open, close, low, high]`` ascending."""
        async with httpx.AsyncClient(timeout=self.timeout, headers=_HEADERS) as client:
            resp = await client.post(
                "https://www.sge.com.cn/graph/Dailyhq",
                data={"instid": symbol},
            )
        if resp.status_code != 200:
            raise SourceError(f"sge_daily HTTP {resp.status_code} for {symbol}")
        try:
            payload = resp.json()
            rows = payload.get("time") or []
        except (ValueError, AttributeError) as exc:
            raise SourceError(f"sge_daily bad payload for {symbol}: {exc}") from exc

        parsed: list[list[Any]] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 5:
                continue
            parsed.append(
                [
                    str(row[0]),
                    parse_float(row[1]),
                    parse_float(row[2]),
                    parse_float(row[3]),
                    parse_float(row[4]),
                ]
            )
        if days > 0:
            parsed = parsed[-days:]
        return parsed


__all__ = ["SGEDailySource"]
