"""股票名称/拼音搜索（腾讯财经 smartbox 联想接口）。

接口: GET https://smartbox.gtimg.cn/s3/?v=2&q=<关键词>&t=all
响应为 GBK 时代遗留的 JS 变量格式，但 2026-10 实测名称部分已改为
纯 ASCII + ``\\uXXXX`` 字面转义（hexdump 验证），按 unicode_escape 解码。

响应格式（``^`` 分隔记录，``~`` 分隔字段）::

    v_hint="sh~600519~\u8d35\u5dde\u8305\u53f0~gzmt~GP-A^hk~00700~...~GP"

字段: market~code~name~pinyin~type；常见 type: GP-A(A股) GP(港股/美股)
ZS(指数) QZ(权证) jj/KJ(基金)。空结果返回 ``v_hint="N"``。

只保留 sina_stock 源可消费的候选: 沪深京 A股/指数 + 港股正股 + 美股正股。
美股 code 带交易所后缀（aapl.oq / brk.b.n），去掉后缀即 gb_ 请求的纯 ticker；
名称含 "etf"（不区分大小写）的美股条目过滤（smartbox 会返回大量杠杆/期权 ETF）。
"""

from __future__ import annotations

import re

import httpx

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}
_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_MAX_RESULTS = 15
# smartbox 美股代码的交易所后缀（brk.b.n -> brk.b）
_US_EXCH_SUFFIX = (".oq", ".n", ".am", ".ps", ".ob", ".pk")


def _decode_escapes(text: str) -> str:
    """解码 smartbox 名称里的 ``\\uXXXX`` 字面转义。"""
    return _ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def parse_smartbox(text: str) -> list[dict]:
    """解析 smartbox 响应，返回 sina_stock 可用的候选列表。

    元素: {source, symbol, name, market, kind}，去重、上限 _MAX_RESULTS。
    """
    match = re.search(r'v_hint="([^"]*)"', text)
    if not match or match.group(1) in {"", "N"}:
        return []

    seen: set[str] = set()
    results: list[dict] = []
    for record in match.group(1).split("^"):
        parts = record.split("~")
        if len(parts) < 5:
            continue
        market, code, name, _pinyin, kind_raw = parts[:5]
        name = _decode_escapes(name).strip()
        if not name:
            continue

        if market in {"sh", "sz", "bj"}:
            kind = "index" if kind_raw == "ZS" else "stock"
            if kind_raw != "ZS" and not kind_raw.startswith("GP-A"):
                continue  # 排除沪深基金/权证等
        elif market == "hk":
            kind = "stock"
            if kind_raw != "GP" or not code.isdigit() or len(code) != 5:
                continue  # 港股只要 5 位数字正股（排除权证 QZ/指数等）
        elif market == "us":
            kind = "stock"
            if kind_raw != "GP" or "etf" in name.lower():
                continue  # 美股只要正股，过滤杠杆/期权 ETF（smartbox 无类型区分）
            for suffix in _US_EXCH_SUFFIX:
                if code.endswith(suffix):
                    code = code[: -len(suffix)]
                    break
            if not code:
                continue
        else:
            continue  # 其余市场暂无源支持

        symbol = f"{market}{code}"
        if symbol in seen:
            continue
        seen.add(symbol)
        results.append(
            {"source": "sina_stock", "symbol": symbol, "name": name, "market": market, "kind": kind}
        )
        if len(results) >= _MAX_RESULTS:
            break
    return results


async def search_stocks(query: str, timeout: float = 5.0) -> list[dict]:
    """按名称/拼音/代码联想搜索，返回候选列表（网络异常向上抛）。"""
    url = "https://smartbox.gtimg.cn/s3/"
    params = {"v": "2", "q": query, "t": "all"}
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as client:
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    return parse_smartbox(resp.text)


__all__ = ["parse_smartbox", "search_stocks"]
