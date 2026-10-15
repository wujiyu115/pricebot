"""新浪国内期货行情源（主力连续合约）。

接口: GET https://hq.sinajs.cn/list=nf_SC0,nf_RB0
需要 Referer: https://finance.sina.com.cn，GBK 编码。
代码规则: 品种代码 + 0（主力连续），如 SC0/RB0/CU0/I0/AU0；
**必须带 nf_ 前缀请求**——不带前缀的旧格式返回的是历史静态数据。
品种月份合约（如 SC2501）此接口不支持。

nf_ 字段布局（2026-10-16 夜盘实测验证，见 AGENTS.md）:
  [0]名称 [1]时间HHMMSS [2]今开 [3]最高 [4]最低 [5]0 [6]买一价 [7]卖一价
  [8]最新价 [9]结算 [10]昨结(涨跌幅基准) [11]买一量 [12]卖一量
  [13]持仓量(手) [14]成交量(手) [15]市场 [16]品种 [17]日期
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

# ClassVar 保留给类属性使用；模块级映射用普通注解
import httpx

from .base import Quote, SourceAdapter, SourceError, parse_float, register

_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

_SYMBOL_RE = re.compile(r"^[A-Z]{1,2}0$")

# 品种 -> 报价单位（缺省 元/吨）；target.extra["unit"] 可覆盖
_UNITS: dict[str, str] = {
    "SC": "元/桶",
    "LU": "元/桶",
    "AU": "元/克",
    "AG": "元/千克",
    "RU": "元/吨",
    "NR": "元/吨",
}


@register
class SinaFuturesSource(SourceAdapter):
    name = "sina_futures"
    description = "新浪国内期货（上期所/大商所/郑商所/能源中心主力连续，实时价+涨跌幅）"
    homepage = "https://finance.sina.com.cn"
    known_symbols: ClassVar[dict[str, str]] = {
        "SC0": "上海原油",
        "RB0": "螺纹钢",
        "HC0": "热轧卷板",
        "CU0": "沪铜",
        "AL0": "沪铝",
        "I0": "铁矿石",
        "J0": "焦炭",
        "JM0": "焦煤",
        "M0": "豆粕",
        "TA0": "PTA",
        "MA0": "甲醇",
        "AU0": "沪金",
        "AG0": "沪银",
        "FU0": "燃料油",
        "BU0": "沥青",
        "SR0": "白糖",
        "CF0": "棉花",
        "PP0": "聚丙烯",
    }

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        symbol = symbol.strip().upper()
        if not _SYMBOL_RE.match(symbol):
            raise SourceError(
                f"invalid futures symbol: {symbol!r} (expect variety + 0, e.g. SC0/RB0/CU0)"
            )

        url = f"https://hq.sinajs.cn/list=nf_{symbol}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=_HEADERS) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise SourceError(f"sina_futures HTTP {resp.status_code} for {symbol}")
        try:
            text = resp.content.decode("gbk", errors="strict")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            raise SourceError(f"sina_futures decode error for {symbol}: {exc}") from exc

        match = re.search(r'"([^"]*)"', text)
        if not match or not match.group(1):
            raise SourceError(f"sina_futures empty payload for {symbol} (rate-limited?)")
        fields = match.group(1).split(",")
        if len(fields) < 18:
            raise SourceError(f"sina_futures bad payload for {symbol}")

        last = parse_float(fields[8])
        if last is None:
            raise SourceError(f"sina_futures no usable price for {symbol}")
        prev_settlement = parse_float(fields[10])  # 涨跌幅按昨结

        variety = symbol[:-1]
        unit = str((extra or {}).get("unit") or _UNITS.get(variety, "元/吨"))
        hhmmss = (fields[1] or "").zfill(6)
        time_str = f"{fields[17]} {hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:6]}" if len(fields) > 17 else ""

        return Quote(
            symbol=symbol,
            name=fields[0],
            last=last,
            bid=self._side(fields[6]),
            ask=self._side(fields[7]),
            open=parse_float(fields[2]),
            high=parse_float(fields[3]),
            low=parse_float(fields[4]),
            prev_close=prev_settlement,
            volume=parse_float(fields[14]),
            turnover=None,
            time=time_str,
            unit=unit,
            extra={
                "open_interest": parse_float(fields[13]),
                "market": fields[15] if len(fields) > 15 else "",
                "prev_settlement": prev_settlement,
            },
        )

    @staticmethod
    def _side(value: str | None) -> float | None:
        parsed = parse_float(value)
        return parsed if parsed and parsed > 0 else None


__all__ = ["SinaFuturesSource"]
