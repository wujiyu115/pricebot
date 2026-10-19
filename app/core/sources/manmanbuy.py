"""慢慢买·商品历史价格数据源（App 内置 H5 接口逆向复现）。

symbol 语义与其他源不同：这里 symbol 是**商品页面链接**（京东 / 淘宝 / 天猫
/ 慢慢买自身的商品页），返回该商品当前价 + 历史价格曲线 + 历史最低价。

**默认走 `getBiJiaInfo`**（``POST apapia-history-simple.manmanbuy.com/
ChromeWidgetServices/WidgetServices.ashx``）：该主机**不做 token/sign 校验**，
只要 ``methodName`` + ``p_url`` 两个表单字段即返回完整 JSON（title /
spmoney 当前价 / lowerPrice 历史最低 / jiagequshi 日线曲线 / zk_scname 商城 /
currentPriceStatus 价位状态）。

逆向背景（2026-10 实测，详见 ``scripts/manmanbuy_reverse_notes.md``）：

- APK ``com.manmanbuy.bijia`` v5.2.41 的 Java 层是爱加密壳（``ijiami.dat``），
  真实业务逻辑在 React Native Hermes bundle（``assets/index.android.bundle``，
  HBC v90，56,977 个函数）——用 hermes-dec 反编译成 173MB hasm 后定位。
- 签名逻辑在 Hermes 侧的 ``makeSign`` / ``dealKeyDES``（DES-ECB + Pkcs7，
  keyDES 为固定串）与原生 ``libmmbKey.so``（``RNReactNativeMencryptSign`` 的
  ``getToken`` / ``getDeviceInfo`` / ``getFixId``）——**仅 new-api 系主机
  （``apapia-search-weblogic`` 的 ``/japi/*``、``/api/searchapi/list``）
  走这套校验**，缺 token 一律 ``{"code":10006,"msg":"token校验失败"}``。
- 但 Hermes 里 ``getBiJiaInfo`` 系列（历史价格主链路）走的是**旧 aspx 通道**，
  投递到 ``apapia-history-simple`` 这个「简单历史价」主机，该主机校验被关掉，
  因此无需复现签名即可直连。
- 已被拦截/下线的通道：``apapia.manmanbuy.com`` 与 ``apapia-history.manmanbuy.com``
  的 ``WidgetServices.ashx`` 一律 302 到 ``https://www.aliyun.com/``；
  PC 站 ``www.manmanbuy.com/history.aspx`` 与 ``m.manmanbuy.com/d.aspx`` 返回
  JS 跳转壳（``js/vm.js``，需浏览器执行）。只有 ``apapia-history-simple`` 可用。
- ``getHistoryTrend``（同主机）被单独限流，稳定返回
  ``{"ok":0,"code":7700,"msg":"访问太频繁了"}``；``getBiJiaInfo`` 连打 30 次
  无衰减（实测），故只用它。

覆盖度（2026-10 实测）：慢慢买 web 好价流里的 20 个商品逐个反查，
**20/20 命中**（京东 / 天猫 ⨯ 家电 / 手机）；未收录商品返回
``spmoney == "0"`` + 空 title。淘宝/天猫/拼多多链接需慢慢买**已收录**
（未收录返回全空壳），京东 ``item.jd.com`` / ``item.m.jd.com`` 均可。

extra 可选项::

    {
      "price_field": "price",   # price=商品标价 spmoney（默认）
                                # final=到手价（jiagequshiyh 最新值，含满减/券）
      "window_days": 90,        # low/high 统计窗口（默认 90 天；0 = 全历史）
      "method": "getBiJiaInfo", # 可切 getBiJiaInfo_weixin（字段一致，多微信分享字段）
    }

限流未实测到上限（30 次/秒级无衰减），仍建议轮询间隔 >= 30s。
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta
from typing import Any, ClassVar

import httpx

from .base import Quote, SourceAdapter, SourceError, now_str, parse_float, register

# ---- 常量（2026-10 实测） ----
_API_HOST = "https://apapia-history-simple.manmanbuy.com"
_API_PATH = "/ChromeWidgetServices/WidgetServices.ashx"
_DEFAULT_METHOD = "getBiJiaInfo"
_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 9; MI 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
_DEFAULT_WINDOW_DAYS = 90

#: ``jiagequshi`` 里的一个点：``[Date.UTC(2026,9,19),1759.00,""]``
#: 注意 ``Date.UTC`` 的月份是 **0-based**，9 表示 10 月。
_TREND_POINT_RE = re.compile(r'\[Date\.UTC\((\d+),(\d+),(\d+)\),([\d.]+),"([^"]*)"\]')
#: .NET ``/Date(1774800751000-0000)/`` 毫秒时间戳
_DOTNET_DATE_RE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def build_payload(symbol: str, method: str = _DEFAULT_METHOD) -> dict[str, str]:
    """构造表单体：``methodName`` + ``p_url``，就这两个字段（无签名）。"""
    return {"methodName": method, "p_url": normalize_symbol(symbol)}


def normalize_symbol(symbol: str) -> str:
    """symbol 归一化为 ``p_url``：纯数字当作慢慢买商品 id，其余按 URL 原样传。

    慢慢买自身的商品页 ``https://m.manmanbuy.com/d.aspx?id=594717927``
    也能作为 symbol 直接传（实测可解析），纯数字是它的简写。
    """
    text = symbol.strip()
    if not text:
        raise SourceError("manmanbuy symbol 必须是非空商品链接")
    if text.isdigit():
        return f"https://m.manmanbuy.com/d.aspx?id={text}"
    if not text.startswith(("http://", "https://")):
        raise SourceError(f"manmanbuy symbol 需为商品 URL（http/https）或纯数字 id，收到 {symbol!r}")
    return text


def parse_trend(raw: Any) -> list[tuple[date, float, str]]:
    """解析 ``jiagequshi`` / ``jiagequshiyh`` 为 ``[(日期, 价格, 备注)]``。

    同一日期可能出现多个点（当天多次变价），**按日期去重保留最后一个**
    （即当天最终价）。返回按日期升序。
    """
    if not isinstance(raw, str) or not raw:
        return []
    by_day: dict[date, tuple[float, str]] = {}
    for year, month, day, price, note in _TREND_POINT_RE.findall(raw):
        value = parse_float(price)
        if value is None:
            continue
        try:
            # Date.UTC 月份 0-based
            day_key = date(int(year), int(month) + 1, int(day))
        except ValueError:
            continue
        by_day[day_key] = (value, note)
    return [(d, v, note) for d, (v, note) in sorted(by_day.items())]


def parse_dotnet_date(raw: Any) -> str:
    """``/Date(1774800751000-0000)/`` → ``YYYY-MM-DD HH:MM:SS``（本地时区）。

    无效/默认值（``/Date(-62135596800000-0000)/`` = DateTime.MinValue）返回 ""。
    """
    if not isinstance(raw, str):
        return ""
    m = _DOTNET_DATE_RE.search(raw)
    if not m:
        return ""
    try:
        ms = int(m.group(1))
    except ValueError:
        return ""
    if ms <= 0:  # DateTime.MinValue 等占位
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))


def price_range(
    points: list[tuple[date, float, str]], window_days: int = _DEFAULT_WINDOW_DAYS
) -> tuple[float | None, float | None]:
    """窗口内 (最低, 最高)。``window_days <= 0`` 表示全历史。"""
    if not points:
        return None, None
    if window_days > 0:
        cutoff = points[-1][0] - timedelta(days=window_days)
        points = [p for p in points if p[0] >= cutoff] or points[-1:]
    prices = [p[1] for p in points]
    return min(prices), max(prices)


def prev_close_from(points: list[tuple[date, float, str]]) -> tuple[float | None, str]:
    """最近一个**早于曲线最后一天**的价格，作为涨跌幅基准。

    电商价格常年不动，多数情况下等于最新价（涨跌幅 0%），语义与股票源一致。
    """
    if len(points) < 2:
        return None, ""
    _, value, _ = points[-2]
    return value, points[-2][0].isoformat()


@register
class ManmanbuySource(SourceAdapter):
    name = "manmanbuy"
    description = "慢慢买·商品历史价格（symbol 填商品链接，返回当前价/历史最低/日线曲线）"
    homepage = "https://www.manmanbuy.com"
    known_symbols: ClassVar[dict[str, str]] = {
        "https://item.jd.com/100012043978.html": "茅台飞天 53%vol 500ml（京东）",
        "https://item.jd.com/100026667910.html": "Apple iPhone 13 A2634（京东）",
    }

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        extra = extra or {}
        method = str(extra.get("method") or _DEFAULT_METHOD).strip() or _DEFAULT_METHOD
        payload = build_payload(symbol, method)
        p_url = payload["p_url"]

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.post(
                    _API_HOST + _API_PATH,
                    data=payload,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                        "Accept": "*/*",
                        "Referer": "https://www.manmanbuy.com/",
                    },
                )
        except httpx.HTTPError as exc:
            raise SourceError(f"manmanbuy 网络错误: {exc}") from exc

        if resp.status_code != 200:
            raise SourceError(f"manmanbuy HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError("manmanbuy 响应非 JSON（可能被 WAF 拦截）") from exc
        if not isinstance(data, dict):
            raise SourceError("manmanbuy 响应结构异常")

        # 限流/业务错误：{"ok":0,"code":7700,"msg":"访问太频繁了..."}
        if data.get("ok") in (0, "0") and data.get("msg"):
            raise SourceError(f"manmanbuy 业务错误 code={data.get('code')} msg={data.get('msg')!r}")

        title = str(data.get("title") or "").strip()
        points = parse_trend(data.get("jiagequshi"))
        final_points = parse_trend(data.get("jiagequshiyh"))
        price_field = str(extra.get("price_field") or "price").strip().lower()

        last = parse_float(data.get("spmoney"))
        source_price_label = "spmoney"
        if price_field == "final" and final_points:
            last = final_points[-1][1]
            source_price_label = "jiagequshiyh"

        if not title or last is None or last <= 0:
            # 未收录：spmoney=0 + 空 title（慢慢买对未收录商品返回全空壳）
            raise SourceError(f"manmanbuy 未收录该商品（{p_url}），返回空价格")

        try:
            window_days = int(extra.get("window_days", _DEFAULT_WINDOW_DAYS))
        except (TypeError, ValueError):
            window_days = _DEFAULT_WINDOW_DAYS

        basis_points = final_points if (price_field == "final" and final_points) else points
        low, high = price_range(basis_points, window_days)
        prev_close, prev_date = prev_close_from(basis_points)
        hist_low = parse_float(data.get("lowerPrice"))
        hist_low_final = parse_float(data.get("lowerPriceyh"))
        last_day = basis_points[-1][0].isoformat() if basis_points else now_str()

        extra_out: dict[str, Any] = {
            "url": p_url,
            "mall": str(data.get("zk_scname") or ""),
            "shop_id": data.get("zk_scid"),
            "status": str(data.get("currentPriceStatus") or ""),
            "change_remark": str(data.get("changPriceRemark") or ""),
            "trend": str(data.get("qushi") or ""),
            "hist_low": hist_low,
            "hist_low_date": parse_dotnet_date(data.get("lowerDate")),
            "hist_low_final": hist_low_final,
            "hist_low_final_date": parse_dotnet_date(data.get("lowerDateyh")),
            "trend_last_day": last_day,
            "trend_points": len(basis_points),
            "prev_close_date": prev_date,
            "price_field": source_price_label,
            "window_days": window_days,
            "spbh": data.get("spbh"),
        }
        if price_field == "final" and final_points:
            note = final_points[-1][2]
            extra_out["final_note"] = note[:120]
            extra_out["list_price"] = parse_float(data.get("spmoney"))

        return Quote(
            symbol=symbol,
            name=title[:60],
            last=last,
            low=low,
            high=high,
            prev_close=prev_close,
            time=last_day,
            unit="元",
            extra=extra_out,
        )
