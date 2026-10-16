"""什么值得买·好价源单测（签名算法 + MockTransport 网络层 + 实测 payload fixture）。

覆盖两条路径：
- search（默认）：sou/list_v10 搜索接口，article_channel_type=="youhui" 过滤
- home（extra.mode="home"）：v3/home 推荐流，article_first_channel_name=="好价" 过滤
"""

from __future__ import annotations

import httpx
import pytest

import app.core.sources.smzdm as smzdm_mod
from app.core.sources.base import SourceError
from app.core.sources.smzdm import (
    SmzdmSource,
    build_cookie,
    extract_haojia,
    extract_haojia_search,
    sign_params,
)


# ---------------------------------------------------------------- fixtures
def _item(
    article_id: str,
    title: str,
    price: str,
    page_price: str = "",
    discount: str = "",
    mall: str = "京东",
    channel: str = "国内",
    region: str = "国内",
    time_sort: str = "1792100000",
    date: str = "2026-10-16 12:00:00",
) -> dict:
    return {
        "article_id": article_id,
        "article_url": f"https://www.smzdm.com/p/{article_id}",
        "article_title": title,
        "article_price": price,
        "article_page_price": page_price,
        "article_discount": discount,
        "article_mall": [{"article_title": mall}],
        "article_channel_name": channel,
        "article_first_channel_name": "好价",
        "article_region": region,
        "article_date": date,
        "time_sort": time_sort,
    }


def _home_json(items: list[dict], error_code: int = 0) -> dict:
    return {
        "error_code": error_code,
        "error_msg": "",
        "data": {
            "component": [
                {"zz_type": "banner", "zz_content": {}},
                {"zz_type": "list", "zz_content": items},
            ]
        },
    }


def _youhui_row(
    article_id: str,
    title: str,
    price: str,
    page_price: str = "",
    mall: str = "京东",
    channel: str = "国内",
    region: str = "国内",
    publish_ts: str = "1792142300",
    subtitle: str = "",
) -> dict:
    """sou/list_v10 好价行（2026-10-16 实测字段布局）。"""
    return {
        "article_channel_id": "1",
        "article_channel_type": "youhui",
        "article_channel_name": channel,
        "article_id": article_id,
        "article_url": f"https://www.smzdm.com/p/{article_id}/",
        "article_title": title,
        "article_price": price,
        "page_price": page_price,
        "article_mall": mall,
        "article_region": region,
        "article_subtitle": subtitle,
        "article_date": "17:18",
        "publish_date_lt": publish_ts,
    }


def _search_json(rows: list[dict], error_code: int = 0, total: int | None = None) -> dict:
    return {
        "error_code": error_code,
        "error_msg": "",
        "data": {
            "total_num": total if total is not None else len(rows),
            "rows": rows,
        },
    }


def _post_row(title: str) -> dict:
    """搜索结果里混排的社区文章行（非好价）。"""
    return {
        "article_channel_type": "yuanchuang",
        "article_channel_name": "文章",
        "article_title": title,
        "article_price": "#数码",
        "publish_date_lt": "1792149999",
    }


# 2026-10-16 实测样本（首页好价混排流节选）
_FEED = _home_json(
    [
        _item("183926700", "胡姬花 古法老油坊花生油 158ml", "1.9"),
        _item(
            "184023176",
            "20日20点：苹果 AirPods 5 主动降噪版 无线蓝牙耳机 白色",
            "755.57",
            page_price="¥999",
            discount="7.6折",
            time_sort="1792084437",
        ),
        _item("184078704", "美赞臣婴幼儿官方旗舰店」关注2京豆", "", channel="发现"),
        _item(
            "184060956",
            "毛戈平 遮瑕保湿养肤 气垫粉底液套装",
            "70.8",
            page_price="¥250",
            discount="2.8折",
            mall="淘宝精选",
            time_sort="1792063242",
        ),
        {
            "article_title": "非好价条目（好文）",
            "article_first_channel_name": "好文",
        },
    ]
)

# 2026-10-16 实测样本（sou/list_v10 搜索 "action6" 节选）
_SEARCH_FEED = _search_json(
    [
        _post_row("上班路上用Action6记录通勤日常"),
        _youhui_row(
            "184100820",
            "国家补贴：大疆 Osmo Action 6 全能级运动相机 可变光圈Vlog旅行",
            "2293.3",
            page_price="¥2998",
            subtitle="2293.3元（需用券）",
            publish_ts="1792142300",
        ),
        _post_row("大疆Action 6差价900元：京东上到底该买哪一档"),
        _youhui_row(
            "184099001",
            "大疆 Osmo Action 6 可变光圈 运动相机",
            "2299",
            mall="天猫精选",
            publish_ts="1792120186",
        ),
        _youhui_row(
            "184090002",
            "大疆 Osmo Action 6 运动相机（无价格活动条目）",
            "",
            publish_ts="1792130000",
        ),
    ]
)


@pytest.fixture
def mock_transport(monkeypatch):
    def install(handler) -> None:
        real_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(smzdm_mod.httpx, "AsyncClient", patched_client)

    return install


# ---------------------------------------------------------------- 签名
class TestSign:
    def test_sorted_concat_and_md5_upper(self):
        # 与 App C6052a 一致：排序拼接 + &key= + 去空格 + MD5 大写
        params = {"v": "11.1.95", "f": "android", "weixin": "0", "time": "1792080105000", "limit": "10"}
        expected_raw = (
            "f=android&limit=10&time=1792080105000&v=11.1.95&weixin=0&key=apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
        )
        assert sign_params(params) == __import__("hashlib").md5(expected_raw.encode()).hexdigest().upper()

    def test_empty_values_excluded(self):
        assert sign_params({"a": "", "b": "1"}) == sign_params({"b": "1"})

    def test_spaces_stripped(self):
        # 值里带空格需整体去空格后再哈希
        assert sign_params({"k": "a b"}) == sign_params({"k": "ab"})

    def test_deterministic(self):
        p = {"f": "android", "v": "11.1.95", "time": "1792080105000"}
        assert sign_params(p) == sign_params(dict(p))


class TestCookie:
    def test_device_id_is_hex32(self):
        cookie = build_cookie()
        did = dict(kv.split("=", 1) for kv in cookie.split("; "))["device_id"]
        assert len(did) == 32 and int(did, 16) >= 0

    def test_seed_changes_device_id(self):
        assert build_cookie("a") != build_cookie("b")


# ---------------------------------------------------------------- 提取
class TestExtractHome:
    def test_only_haojia_returned(self):
        items = extract_haojia(_FEED)
        assert len(items) == 4
        assert all(it["article_first_channel_name"] == "好价" for it in items)

    def test_no_list_component(self):
        assert extract_haojia({"data": {"component": []}}) == []
        assert extract_haojia({}) == []


class TestExtractSearch:
    def test_only_youhui_returned(self):
        rows = extract_haojia_search(_SEARCH_FEED)
        assert len(rows) == 3
        assert all(r["article_channel_type"] == "youhui" for r in rows)

    def test_empty_rows(self):
        assert extract_haojia_search({"data": {"rows": []}}) == []
        assert extract_haojia_search({}) == []


# ---------------------------------------------------------------- search 路径（默认）
class TestFetchSearch:
    async def test_default_mode_is_search(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_SEARCH_FEED)

        mock_transport(handler)
        quote = await SmzdmSource().fetch("Action 6")
        assert "sou/list_v10" in seen["url"]
        assert quote.last == 2293.3
        assert quote.prev_close == 2998.0  # ¥2998 去符号
        assert quote.extra["mall"] == "京东"
        assert quote.extra["subtitle"] == "2293.3元（需用券）"
        assert quote.extra["region"] == "国内"
        assert quote.time == "2026-10-16 17:18"  # publish_date_lt 格式化

    async def test_newest_youhui_picked(self, mock_transport):
        # 两条带价格好价，取 publish_date_lt 更新的
        feed = _search_json(
            [
                _youhui_row("old", "牛奶 全脂 1L", "12.9", publish_ts="1792000000"),
                _youhui_row("new", "牛奶 脱脂 950ml", "15.9", publish_ts="1792100000"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("牛奶")
        assert quote.last == 15.9
        assert quote.extra["article_id"] == "new"

    async def test_skips_priceless_youhui(self, mock_transport):
        feed = _search_json(
            [
                _youhui_row("act", "牛奶 互动赢京豆", "", publish_ts="9999999999"),
                _youhui_row("ok", "牛奶 纯牛奶 250ml", "9.9", publish_ts="1"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("牛奶")
        assert quote.last == 9.9

    async def test_channel_filter(self, mock_transport):
        feed = _search_json(
            [
                _youhui_row("a", "牛奶 1L", "9.9", channel="国内"),
                _youhui_row("b", "牛奶 2L", "19.9", channel="海淘"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("牛奶", {"channel": "海淘"})
        assert quote.last == 19.9

    async def test_region_filter(self, mock_transport):
        feed = _search_json(
            [
                _youhui_row("a", "牛奶 1L", "9.9", region="国内"),
                _youhui_row("b", "牛奶 2L", "19.9", region="海外直邮"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("牛奶", {"region": "海外直邮"})
        assert quote.last == 19.9

    async def test_no_youhui_raises_without_retry(self, mock_transport):
        # 搜索结果确定，无匹配不重试（区别于 home 模式）
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_search_json([_post_row("牛奶 文章")]))

        mock_transport(handler)
        with pytest.raises(SourceError, match="暂无带价格的好价"):
            await SmzdmSource().fetch("牛奶")
        assert len(calls) == 1

    async def test_request_params_signed(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_SEARCH_FEED)

        mock_transport(handler)
        await SmzdmSource().fetch("Action 6")
        from urllib.parse import parse_qs, urlparse

        q = {k: v[0] for k, v in parse_qs(urlparse(seen["url"]).query).items()}
        assert q["keyword"] == "Action 6"
        assert q["search_tab"] == "good_price"
        assert q["sid"]  # s-api 会话标识
        assert q["limit"] == "20"
        sent_sign = q.pop("sign")
        assert sent_sign == sign_params(q)

    async def test_business_error_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=_search_json([], error_code=1)))
        with pytest.raises(SourceError, match="error_code=1"):
            await SmzdmSource().fetch("牛奶")

    async def test_http_error_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(403, text="forbidden"))
        with pytest.raises(SourceError, match="403"):
            await SmzdmSource().fetch("牛奶")

    async def test_network_error_raises(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        mock_transport(handler)
        with pytest.raises(SourceError, match="网络错误"):
            await SmzdmSource().fetch("牛奶")


# ---------------------------------------------------------------- home 路径（extra.mode="home"）
class TestFetchHome:
    async def test_keyword_match_newest_with_price(self, mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            assert "v3/home" in str(request.url)
            return httpx.Response(200, json=_FEED)

        mock_transport(handler)
        quote = await SmzdmSource().fetch("AirPods", {"mode": "home"})
        assert quote.symbol == "AirPods"
        assert "AirPods 5" in quote.name
        assert quote.last == 755.57
        assert quote.prev_close == 999.0  # ¥999 去符号
        assert quote.unit == "元"
        assert quote.extra["mall"] == "京东"
        assert quote.extra["discount"] == "7.6折"
        assert quote.extra["url"].endswith("/184023176")
        assert quote.time == "2026-10-16 12:00:00"

    async def test_skips_priceless_activity_items(self, mock_transport):
        # 「关注2京豆」无价格但 time_sort 更新，应被跳过而非报错
        feed = _home_json(
            [
                _item("new", "美赞臣 关注2京豆", "", time_sort="9999999999"),
                _item("old", "美赞臣 奶粉 800g", "89", time_sort="1"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("美赞臣", {"mode": "home"})
        assert quote.last == 89.0

    async def test_channel_filter(self, mock_transport):
        # 同关键词两条带价格好价，channel 过滤应只选发现频道那条
        feed = _home_json(
            [
                _item("a", "特价 牛奶 250ml", "9.9", channel="国内", time_sort="2"),
                _item("b", "海蕿 牛奶 1L", "15.9", channel="海蕿", time_sort="3"),
            ]
        )
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("牛奶", {"mode": "home", "channel": "海蕿"})
        assert quote.last == 15.9
        assert quote.extra["channel"] == "海蕿"
        # 过滤到不存在的频道 → 无匹配
        with pytest.raises(SourceError, match="无匹配"):
            await SmzdmSource().fetch("牛奶", {"mode": "home", "channel": "发现"})

    async def test_no_match_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=_FEED))
        with pytest.raises(SourceError, match="无匹配"):
            await SmzdmSource().fetch("不存在的关键词xyz", {"mode": "home"})

    async def test_retry_until_hit(self, mock_transport):
        # 推荐流轮换：首次无匹配重抽，第 2 抽命中则成功
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if len(calls) == 1:
                return httpx.Response(200, json=_home_json([]))  # 空流
            return httpx.Response(200, json=_FEED)

        mock_transport(handler)
        quote = await SmzdmSource().fetch("AirPods", {"mode": "home"})
        assert quote.last == 755.57
        assert len(calls) == 2

    async def test_no_match_retries_then_raises(self, mock_transport):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_home_json([]))

        mock_transport(handler)
        with pytest.raises(SourceError, match="无匹配"):
            await SmzdmSource().fetch("牛奶", {"mode": "home"})
        assert len(calls) == 3  # 默认 3 抽

    async def test_retry_seed_rotates(self, mock_transport):
        cookies = []

        def handler(request: httpx.Request) -> httpx.Response:
            cookies.append(request.headers.get("Cookie", ""))
            return httpx.Response(200, json=_home_json([]))

        mock_transport(handler)
        with pytest.raises(SourceError):
            await SmzdmSource().fetch("牛奶", {"mode": "home"})
        dids = {dict(kv.split("=", 1) for kv in c.split("; "))["device_id"] for c in cookies}
        assert len(dids) == 3  # 每抽换 device_id → 不同个性化流

    async def test_attempts_configurable(self, mock_transport):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_home_json([]))

        mock_transport(handler)
        with pytest.raises(SourceError):
            await SmzdmSource().fetch("牛奶", {"mode": "home", "attempts": 1})
        assert len(calls) == 1

    async def test_business_error_raises(self, mock_transport):
        mock_transport(lambda r: httpx.Response(200, json=_home_json([], error_code=1)))
        with pytest.raises(SourceError, match="error_code=1"):
            await SmzdmSource().fetch("牛奶", {"mode": "home"})

    async def test_request_has_sign_and_cookie(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["cookie"] = request.headers.get("Cookie", "")
            seen["ua"] = request.headers.get("User-Agent", "")
            return httpx.Response(200, json=_FEED)

        mock_transport(handler)
        await SmzdmSource().fetch("AirPods", {"mode": "home"})
        assert "sign=" in seen["url"]
        assert "f=android" in seen["url"] and "v=11.1.95" in seen["url"]
        assert "device_id=" in seen["cookie"]
        assert "smzdmapp" in seen["ua"]
        # sign 可独立复算验证（用请求里实际发出的参数，去掉 sign 自身）
        from urllib.parse import parse_qs, urlparse

        q = {k: v[0] for k, v in parse_qs(urlparse(seen["url"]).query).items()}
        sent_sign = q.pop("sign")
        assert sent_sign == sign_params(q)


# ---------------------------------------------------------------- 通用
class TestFetchCommon:
    async def test_empty_symbol_raises(self):
        with pytest.raises(SourceError, match="非空关键词"):
            await SmzdmSource().fetch("  ")

    async def test_mode_case_insensitive(self, mock_transport):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json=_FEED)

        mock_transport(handler)
        quote = await SmzdmSource().fetch("AirPods", {"mode": "HOME"})
        assert "v3/home" in seen["url"]
        assert quote.last == 755.57


class TestNormMatch:
    async def test_search_case_and_space_insensitive(self, mock_transport):
        # 「action6」应命中标题「Action 6」（大小写 + 空格归一化）
        mock_transport(lambda r: httpx.Response(200, json=_SEARCH_FEED))
        quote = await SmzdmSource().fetch("action6")
        assert quote.last == 2293.3

    async def test_home_case_and_space_insensitive(self, mock_transport):
        feed = _home_json([_item("a", "AIRPODS 5 耳机", "755.57")])
        mock_transport(lambda r: httpx.Response(200, json=feed))
        quote = await SmzdmSource().fetch("airpods", {"mode": "home"})
        assert quote.last == 755.57
