"""慢慢买·商品历史价格源单测（解析纯函数 + MockTransport 网络层 + 实测 payload fixture）。

只覆盖免签名通道 ``getBiJiaInfo``（``apapia-history-simple`` 主机）：
- symbol → p_url 归一化（URL / 纯数字慢慢买 id）
- ``jiagequshi`` 曲线解析（Date.UTC 0-based 月份、同日去重、排序）
- 窗口内 low/high 与涨跌幅基准
- 未收录商品（spmoney=0 + 空 title）与限流（code=7700）错误路径
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

import app.core.sources.manmanbuy as mmb_mod
from app.core.sources.base import SourceError
from app.core.sources.manmanbuy import (
    ManmanbuySource,
    build_payload,
    normalize_symbol,
    parse_dotnet_date,
    parse_trend,
    prev_close_from,
    price_range,
)

# ---------------------------------------------------------------- fixtures
#: 2026-10-19 实测 getBiJiaInfo 响应节选（京东茅台 SKU，曲线压到 4 天）
_JD_MAOTAI = {
    "id": "0",
    "title": "茅台飞天 53%vol  500ml 贵州茅台酒（带杯）【需预约购买】",
    "smallpic": "https://img14.360buyimg.com/pop/jfs/t1/252613/16/18304/137207/67a5bb14F.png",
    "jiagequshi": (
        '[Date.UTC(2026,9,15),1759,""],[Date.UTC(2026,9,16),1759.00,""],'
        '[Date.UTC(2026,9,17),1699,""],[Date.UTC(2026,9,18),1699,""],[Date.UTC(2026,9,19),1759.00,""]'
    ),
    "jiagequshiyh": (
        '[Date.UTC(2026,9,15),1759,"到手价1759.00"],[Date.UTC(2026,9,16),1759.00,"到手价1759.00"],'
        '[Date.UTC(2026,9,17),1659.5,"购买1件,当前价:1699,满减：满1件，打9折"],'
        '[Date.UTC(2026,9,18),1659.5,"到手价1659.50"],[Date.UTC(2026,9,19),1759.00,"到手价1759.00"]'
    ),
    "lowerPrice": 1499.0,
    "lowerPriceyh": 1497.51,
    "currentPriceStatus": "30天最低",
    "currentPriceyhStatus": "30天最低",
    "lowerDate": "/Date(1774800751000-0000)/",
    "lowerDateyh": "/Date(1774771281000-0000)/",
    "qushi": "上涨",
    "zk_scname": "京东商城",
    "zk_scid": 1,
    "spbh": "3yuxuQot6bQUMrk3C6!!00001000111001",
    "url": "http://item.jd.com/100012043978.html",
    "spmoney": "1759",
    "changPriceRemark": "涨幅7%",
}

#: 未收录商品（jd 不存在的 SKU）实测返回：spmoney=0 + 空 title + 默认日期
_NOT_LISTED = {
    "id": "0",
    "title": "",
    "jiagequshi": "",
    "jiagequshiyh": "",
    "lowerPrice": 0,
    "lowerPriceyh": 0,
    "lowerDate": "/Date(-62135596800000-0000)/",
    "lowerDateyh": "/Date(-62135596800000-0000)/",
    "qushi": "历史最低",
    "zk_scname": "中国亚马逊",
    "zk_scid": 0,
    "spmoney": "0",
    "changPriceRemark": "",
}

_RATE_LIMITED = {
    "ok": 0,
    "msg": "访问太频繁了，请稍后重试，有问题请联系客服",
    "code": 7700,
    "data": {"restrict": True, "restrictAction": "rejectAccess"},
}


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(mmb_mod.httpx, "AsyncClient", patched_client)

    return install


# ---------------------------------------------------------------- symbol 归一化
class TestNormalizeSymbol:
    def test_plain_url_passthrough(self):
        url = "https://item.jd.com/100012043978.html"
        assert normalize_symbol(url) == url

    def test_http_url_passthrough(self):
        url = "http://item.jd.com/100012043978.html"
        assert normalize_symbol(url) == url

    def test_digits_become_manmanbuy_id(self):
        # 纯数字是慢慢买自身商品页 id 的简写（实测可解析）
        assert normalize_symbol("595744078") == "https://m.manmanbuy.com/d.aspx?id=595744078"

    def test_whitespace_stripped(self):
        assert normalize_symbol("  https://item.jd.com/1.html  ") == "https://item.jd.com/1.html"

    def test_empty_raises(self):
        with pytest.raises(SourceError, match="非空商品链接"):
            normalize_symbol("   ")

    def test_non_url_raises(self):
        with pytest.raises(SourceError, match="需为商品 URL"):
            normalize_symbol("茅台飞天")


class TestBuildPayload:
    def test_only_two_fields(self):
        # 该主机免签名：表单体只有 methodName + p_url（实测）
        payload = build_payload("https://item.jd.com/1.html")
        assert payload == {"methodName": "getBiJiaInfo", "p_url": "https://item.jd.com/1.html"}

    def test_method_override(self):
        payload = build_payload("https://item.jd.com/1.html", "getBiJiaInfo_weixin")
        assert payload["methodName"] == "getBiJiaInfo_weixin"

    def test_no_sign_or_token_fields(self):
        # 回归保护：别把 new-api 的 token/sign 混进旧 aspx 通道
        payload = build_payload("https://item.jd.com/1.html")
        assert not {"sign", "token", "u_token", "c_devid2"} & set(payload)


# ---------------------------------------------------------------- 曲线解析
class TestParseTrend:
    def test_month_is_zero_based(self):
        # Date.UTC(2026,9,19) 中 9 表示 10 月，不是 9 月
        points = parse_trend('[Date.UTC(2026,9,19),1759.00,""]')
        assert points == [(date(2026, 10, 19), 1759.0, "")]

    def test_multiple_days_sorted(self):
        points = parse_trend(_JD_MAOTAI["jiagequshi"])
        assert [p[0] for p in points] == [
            date(2026, 10, 15),
            date(2026, 10, 16),
            date(2026, 10, 17),
            date(2026, 10, 18),
            date(2026, 10, 19),
        ]
        assert points[-1][1] == 1759.0

    def test_same_day_dedup_keeps_last(self):
        # 同一天多次变价：保留最后一个（当天最终价）
        raw = '[Date.UTC(2026,9,19),100,""],[Date.UTC(2026,9,19),90,""],[Date.UTC(2026,9,19),95,""]'
        points = parse_trend(raw)
        assert len(points) == 1
        assert points[0][1] == 95.0

    def test_note_captured(self):
        points = parse_trend('[Date.UTC(2026,9,17),1659.5,"购买1件,当前价:1699"]')
        assert points[0][2] == "购买1件,当前价:1699"

    def test_empty_and_none(self):
        assert parse_trend("") == []
        assert parse_trend(None) == []
        assert parse_trend(123) == []

    def test_malformed_points_skipped(self):
        raw = '[Date.UTC(2026,9,19),1759,""],[BROKEN],not-a-point'
        assert len(parse_trend(raw)) == 1

    def test_invalid_date_skipped(self):
        # 月份越界（Date.UTC 里 20 → 21 月）不应崩
        assert parse_trend('[Date.UTC(2026,20,1),100,""]') == []


class TestParseDotnetDate:
    def test_valid_ms_timestamp(self):
        out = parse_dotnet_date("/Date(1774800751000-0000)/")
        assert out.startswith("2026-")

    def test_min_value_returns_empty(self):
        # DateTime.MinValue 占位：未收录/无历史最低时返回
        assert parse_dotnet_date("/Date(-62135596800000-0000)/") == ""

    def test_non_date_returns_empty(self):
        assert parse_dotnet_date("") == ""
        assert parse_dotnet_date(None) == ""
        assert parse_dotnet_date("2026-10-19") == ""


class TestPriceRange:
    def _points(self):
        return [
            (date(2026, 1, 1), 100.0, ""),
            (date(2026, 7, 1), 50.0, ""),
            (date(2026, 10, 1), 120.0, ""),
            (date(2026, 10, 19), 90.0, ""),
        ]

    def test_window_filters_old_points(self):
        # 以最后一天为基准往前 90 天：01-01 与 07-01 都在窗口外
        low, high = price_range(self._points(), 90)
        assert low == 90.0
        assert high == 120.0

    def test_zero_window_uses_all_history(self):
        low, high = price_range(self._points(), 0)
        assert low == 50.0
        assert high == 120.0

    def test_negative_window_uses_all_history(self):
        assert price_range(self._points(), -5) == (50.0, 120.0)

    def test_empty_points(self):
        assert price_range([], 90) == (None, None)

    def test_window_too_narrow_falls_back_to_last(self):
        # 窗口内无点时退化为最后一天，避免 low/high 全 None
        points = [(date(2020, 1, 1), 10.0, ""), (date(2026, 10, 19), 90.0, "")]
        assert price_range(points, 1) == (90.0, 90.0)


class TestPrevClose:
    def test_second_to_last_point(self):
        points = [
            (date(2026, 10, 17), 1699.0, ""),
            (date(2026, 10, 18), 1699.0, ""),
            (date(2026, 10, 19), 1759.0, ""),
        ]
        value, day = prev_close_from(points)
        assert value == 1699.0
        assert day == "2026-10-18"

    def test_single_point_has_no_basis(self):
        assert prev_close_from([(date(2026, 10, 19), 1759.0, "")]) == (None, "")

    def test_empty(self):
        assert prev_close_from([]) == (None, "")


# ---------------------------------------------------------------- fetch 主路径
class TestFetch:
    async def test_parses_quote_fields(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["method"] = request.method
            seen["body"] = request.content.decode()
            seen["ua"] = request.headers.get("User-Agent", "")
            return httpx.Response(200, json=_JD_MAOTAI)

        mock_transport(handler)
        quote = await ManmanbuySource().fetch("https://item.jd.com/100012043978.html")

        assert quote.symbol == "https://item.jd.com/100012043978.html"
        assert quote.name.startswith("茅台飞天")
        assert quote.last == 1759.0
        assert quote.unit == "元"
        assert quote.high == 1759.0
        assert quote.time == "2026-10-19"
        # 涨跌幅基准 = 前一天价格
        assert quote.prev_close == 1699.0
        assert quote.extra["prev_close_date"] == "2026-10-18"
        assert quote.extra["mall"] == "京东商城"
        assert quote.extra["status"] == "30天最低"
        assert quote.extra["hist_low"] == 1499.0
        assert quote.extra["trend_points"] == 5
        assert quote.extra["url"] == "https://item.jd.com/100012043978.html"

    async def test_request_shape(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["method"] = request.method
            seen["body"] = request.content.decode()
            seen["ua"] = request.headers.get("User-Agent", "")
            return httpx.Response(200, json=_JD_MAOTAI)

        mock_transport(handler)
        await ManmanbuySource().fetch("https://item.jd.com/100012043978.html")

        assert seen["method"] == "POST"
        assert "apapia-history-simple.manmanbuy.com" in seen["url"]
        assert "ChromeWidgetServices/WidgetServices.ashx" in seen["url"]
        assert "methodName=getBiJiaInfo" in seen["body"]
        # p_url 走表单编码，冒号斜杠需转义
        assert "p_url=https%3A%2F%2Fitem.jd.com%2F100012043978.html" in seen["body"]
        assert "Android" in seen["ua"]

    async def test_digits_symbol_resolved(self, mock_transport):
        bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content.decode())
            return httpx.Response(200, json=_JD_MAOTAI)

        mock_transport(handler)
        quote = await ManmanbuySource().fetch("595744078")
        assert "p_url=https%3A%2F%2Fm.manmanbuy.com%2Fd.aspx%3Fid%3D595744078" in bodies[0]
        assert quote.extra["url"] == "https://m.manmanbuy.com/d.aspx?id=595744078"

    async def test_final_price_field(self, mock_transport):
        # price_field=final：取到手价曲线最后一点（含满减/券后的价格）
        mock_transport(lambda r: httpx.Response(200, json=_JD_MAOTAI))
        quote = await ManmanbuySource().fetch(
            "https://item.jd.com/100012043978.html", {"price_field": "final"}
        )
        assert quote.last == 1759.0
        assert quote.extra["price_field"] == "jiagequshiyh"
        assert quote.extra["list_price"] == 1759.0
        assert quote.extra["final_note"] == "到手价1759.00"

    async def test_final_field_falls_back_when_absent(self, mock_transport):
        data = dict(_JD_MAOTAI)
        data["jiagequshiyh"] = ""
        mock_transport(lambda r: httpx.Response(200, json=data))
        quote = await ManmanbuySource().fetch("https://item.jd.com/1.html", {"price_field": "final"})
        assert quote.last == 1759.0  # 回退 spmoney
        assert quote.extra["price_field"] == "spmoney"

    async def test_window_days_configurable(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=_JD_MAOTAI))
        quote = await ManmanbuySource().fetch("https://item.jd.com/1.html", {"window_days": 0})
        # 全历史：含 1699 那天
        assert quote.low == 1699.0
        assert quote.extra["window_days"] == 0

    async def test_window_days_invalid_uses_default(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=_JD_MAOTAI))
        quote = await ManmanbuySource().fetch("https://item.jd.com/1.html", {"window_days": "abc"})
        assert quote.extra["window_days"] == 90

    async def test_method_override(self, mock_transport):
        bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content.decode())
            return httpx.Response(200, json=_JD_MAOTAI)

        mock_transport(handler)
        await ManmanbuySource().fetch(
            "https://item.jd.com/1.html", {"method": "getBiJiaInfo_weixin"}
        )
        assert "methodName=getBiJiaInfo_weixin" in bodies[0]

    async def test_name_truncated(self, mock_transport):
        data = dict(_JD_MAOTAI)
        data["title"] = "长" * 200
        mock_transport(lambda r: httpx.Response(200, json=data))
        quote = await ManmanbuySource().fetch("https://item.jd.com/1.html")
        assert len(quote.name) == 60


# ---------------------------------------------------------------- 错误路径
class TestFetchErrors:
    async def test_not_listed_product_raises(self, mock_transport):
        # 未收录：spmoney=0 + 空 title（慢慢买返回全空壳而非 4xx）
        mock_transport(lambda r: httpx.Response(200, json=_NOT_LISTED))
        with pytest.raises(SourceError, match="未收录"):
            await ManmanbuySource().fetch("https://item.jd.com/99999999999999.html")

    async def test_rate_limited_raises(self, mock_transport):
        # getHistoryTrend 同主机实测稳定返回该限流体
        mock_transport(lambda r: httpx.Response(200, json=_RATE_LIMITED))
        with pytest.raises(SourceError, match="code=7700"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")

    async def test_http_error_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(502, text="bad gateway"))
        with pytest.raises(SourceError, match="502"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")

    async def test_non_json_raises(self, mock_transport):
        # 被 WAF 302 → www.aliyun.com 时拿到的是 HTML
        mock_transport(lambda r: httpx.Response(200, text="<html>Object moved</html>"))
        with pytest.raises(SourceError, match="非 JSON"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")

    async def test_network_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        mock_transport(handler)
        with pytest.raises(SourceError, match="网络错误"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")

    async def test_non_dict_json_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=[1, 2, 3]))
        with pytest.raises(SourceError, match="结构异常"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")

    async def test_empty_symbol_raises(self):
        with pytest.raises(SourceError, match="非空商品链接"):
            await ManmanbuySource().fetch("  ")

    async def test_zero_price_raises(self, mock_transport):
        data = dict(_JD_MAOTAI)
        data["spmoney"] = "0"
        mock_transport(lambda r: httpx.Response(200, json=data))
        with pytest.raises(SourceError, match="未收录"):
            await ManmanbuySource().fetch("https://item.jd.com/1.html")


# ---------------------------------------------------------------- 注册表
class TestRegistry:
    def test_registered(self):
        from app.core.sources.base import get_source_class, list_source_names

        assert "manmanbuy" in list_source_names()
        cls = get_source_class("manmanbuy")
        assert cls.name == "manmanbuy"
        assert cls.known_symbols
