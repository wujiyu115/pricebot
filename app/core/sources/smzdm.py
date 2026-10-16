"""什么值得买·好价数据源（App 签名接口逆向复现）。

symbol 语义与其他源不同：这里 symbol 是**商品关键词**（如 ``action6``、
``iPhone``），返回含该关键词的最新一条好价（成交价 + 原价基准）。

**默认走 App 搜索接口**（``s-api.smzdm.com/sou/list_v10``，好价 tab）：
任意关键词精确匹配、结果确定（与设备无关）、带原价/商城/发布时间。
``extra.mode="home"`` 可切回旧路径——首页好价推荐流
（``homepage-api.smzdm.com/v3/home``）：推荐流按 device_id 个性化且逐次
轮换，冷门关键词基本不会出现，仅适合浏览热门品类。

逆向背景（2026-10 实测，详见 ``scripts/smzdm_reverse_notes.md``）：
App v11.1.95 的 OkHttp 拦截器 ``mf/C6052a`` 对全部请求参数（含公共参数）
按 key ASCII 排序拼接 ``k=v&...&key=<KEY>``、去空格、MD5 大写作为 ``sign``；
s-api 主机额外注入 ``sid``（会话标识：毫秒时间戳+4 位随机数，``Ng.f.o()``）；
公共设备参数经 ``mf/C6053b`` 走 Cookie 头注入（device_id 必须是 32 位 hex）。

.. note::
    此处 MD5 是 SMZDM 协议规定的签名原语（反编译自
    ``C4717r0.a()`` 的 ``MessageDigest.getInstance("MD5")``），
    属互操作性要求而非安全选型，不可替换为更强哈希。

extra 可选项::

    {
      "mode": "search",         # search=搜索接口（默认，精确匹配任意关键词）
                                # home=首页推荐流（个性化轮换，仅热门品类）
      "channel": "国内",        # 过滤 article_channel_name（国内/发现/海淘）
      "region": "国内",         # 过滤 article_region
      "limit": "20",            # 拉取条数（默认 20）
      "offset": "0",            # 翻页偏移（默认 0）
      "order": "",              # search 模式排序（默认相关度，服务端定义）
      "attempts": 3,            # home 模式无匹配时重抽次数（默认 3，换 device_seed）
      "device_seed": "xxx",     # home 模式设备种子（默认固定值）
    }

搜索接口结果与设备无关，无匹配即真无该关键词好价（不重试）；
home 推荐流单抽命中率 ~50%，重抽 3 次综合 >85%。

上游限流未实测，建议轮询间隔 >= 30s。
"""

from __future__ import annotations

import hashlib
import random
import time
from typing import Any, ClassVar

import httpx

from .base import Quote, SourceAdapter, SourceError, now_str, parse_float, register

# ---- 常量（v11.1.95 实测） ----
_APP_VERSION = "11.1.95"
_APP_VERSION_CODE = "1110950"
# liblib_zdm_key.so 导出符号 getDefaultNativeKey 返回的明文
_SIGN_KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
# App 搜索接口（好价 tab），T1.java 反编译
_SEARCH_URL = "https://s-api.smzdm.com/sou/list_v10"
# 首页好价推荐流（旧路径）
_HOME_URL = "https://homepage-api.smzdm.com/v3/home"
_USER_AGENT = f"smzdm_android_V{_APP_VERSION} rv:{_APP_VERSION_CODE} (Xiaomi;Android9;zh-CN)smzdmapp"
_DEFAULT_DEVICE_SEED = "pricebot-smzdm-source"


# ---- 签名原语（协议规定，勿改动） ----
# SMZDM 协议用 MD5 作为签名哈希（反编译自 C4717r0.a()：
# MessageDigest.getInstance("MD5")），是互操作性要求而非安全选型。
# 以下两处 hashlib.md5 均为实现该协议，不可替换为 SHA-256。


def sign_params(params: dict[str, str]) -> str:
    """SMZDM App 签名：排序拼接 ``k=v&...&key=KEY``，去空格，MD5 大写。

    空值参数（None/""）不参与拼接。MD5 为协议规定，见模块 docstring。
    """
    raw = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    raw += "&key=" + _SIGN_KEY
    return hashlib.md5(raw.replace(" ", "").encode("utf-8")).hexdigest().upper()


def build_cookie(device_seed: str = _DEFAULT_DEVICE_SEED) -> str:
    """构造 App 公共参数 Cookie（device_id 须为 32 位 hex，内容任意）。"""
    # device_id 的 32 位 hex 是 SMZDM 服务器侧的格式要求（真实 App 对设备串
    # 做 MD5，见 S0.h()），非安全用途，不可替换为更强哈希。
    device_id = hashlib.md5(device_seed.encode()).hexdigest()
    parts = [
        f"device_id={device_id}",
        f"new_device_id={device_id}",
        "smzdm_id=0",
        "f=android",
        f"v={_APP_VERSION}",
        f"device_s={device_id}",
        "device_smzdm=android",
        "device_system_version=9",
        f"device_smzdm_version_code={_APP_VERSION_CODE}",
        "basic_v=0",
        "user_type=0",
        "new_user_type=0",
    ]
    return "; ".join(parts)


def _common_params() -> dict[str, str]:
    """拦截器注入的公共参数（全部参与签名）。time 用本地毫秒，服务端±5min 容忍。"""
    return {
        "f": "android",
        "v": _APP_VERSION,
        "weixin": "0",
        "time": str(int(time.time() * 1000)),
        "basic_v": "0",
        "zhuanzai_ab": "",
    }


def _build_sid() -> str:
    """s-api 主机会话标识（Ng.f）：毫秒时间戳 + 4 位随机数。"""
    return f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"


def extract_haojia(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从 v3/home 响应提取好价条目（混排流里过滤 article_first_channel_name）。"""
    for comp in payload.get("data", {}).get("component", []):
        if comp.get("zz_type") == "list":
            return [
                it
                for it in comp.get("zz_content", [])
                if isinstance(it, dict) and it.get("article_first_channel_name") == "好价"
            ]
    return []


def extract_haojia_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从 sou/list_v10 响应提取好价条目（混排结果里过滤 article_channel_type）。

    搜索结果混有社区文章（yuanchuang/zhiyoushuo 等），好价行的
    ``article_channel_type == "youhui"``（T1.java 的 SearchResultBean 布局）。
    """
    rows = payload.get("data", {}).get("rows", [])
    return [it for it in rows if isinstance(it, dict) and it.get("article_channel_type") == "youhui"]


def _norm_text(s: str) -> str:
    """匹配归一化：去空格 + 小写（"Action 6" ≡ "action6"）。"""
    return s.replace(" ", "").lower()


@register
class SmzdmSource(SourceAdapter):
    name = "smzdm"
    description = "什么值得买·好价搜索（symbol 填商品关键词，返回最新匹配好价）"
    homepage = "https://www.smzdm.com"
    known_symbols: ClassVar[dict[str, str]] = {
        "iPhone": "苹果 iPhone",
        "茅台": "茅台",
        "牛奶": "牛奶",
        "洗衣液": "洗衣液",
        "空气炸锅": "空气炸锅",
    }

    def __init__(self, timeout: float = 15.0) -> None:
        super().__init__(timeout=timeout)
        # home 推荐流按 device_id 个性化且逐次轮换，单抽命中率不稳定；
        # 每次换 device_seed 重抽可显著提高关键词命中（实测~50%/抽 → 3抽>85%）
        self._default_attempts = 3

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        extra = extra or {}
        keyword = symbol.strip()
        if not keyword:
            raise SourceError("smzdm symbol 必须是非空关键词")

        mode = str(extra.get("mode") or "search").strip().lower()
        if mode == "home":
            return await self._fetch_home(keyword, extra)
        return await self._fetch_search(keyword, extra)

    # ------------------------------------------------------------------ search
    async def _fetch_search(self, keyword: str, extra: dict[str, Any]) -> Quote:
        """搜索接口（默认路径）：精确匹配任意关键词，结果确定无需重试。"""
        params = {
            "keyword": keyword,
            "limit": str(extra.get("limit") or "20"),
            "offset": str(extra.get("offset") or "0"),
            "order": str(extra.get("order") or ""),
            "page": "1",
            "search_source": "1",
            "search_tab": "good_price",
            "sid": _build_sid(),
            **_common_params(),
        }
        params["sign"] = sign_params(params)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    _SEARCH_URL,
                    params=params,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Cookie": build_cookie(str(extra.get("device_seed") or _DEFAULT_DEVICE_SEED)),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise SourceError(f"smzdm 网络错误: {exc}") from exc

        if resp.status_code != 200:
            raise SourceError(f"smzdm HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise SourceError("smzdm 响应非 JSON") from exc
        if payload.get("error_code") not in (0, "0"):
            raise SourceError(
                f"smzdm 业务错误 error_code={payload.get('error_code')} "
                f"error_msg={payload.get('error_msg')!r}"
            )

        items = extract_haojia_search(payload)
        channel = str(extra.get("channel") or "").strip()
        region = str(extra.get("region") or "").strip()
        matches: list[tuple[float, dict[str, Any]]] = []
        kw = _norm_text(keyword)
        for it in items:
            title = it.get("article_title") or ""
            if kw not in _norm_text(title):
                continue
            if channel and it.get("article_channel_name") != channel:
                continue
            if region and it.get("article_region") != region:
                continue
            price = parse_float(it.get("article_price"))
            if price is None:
                continue  # 活动类条目无价格，跳过
            matches.append((float(it.get("publish_date_lt") or 0), it))

        if not matches:
            raise SourceError(f"smzdm 搜索「{keyword}」暂无带价格的好价条目")

        _, item = max(matches, key=lambda m: m[0])
        mall = str(item.get("article_mall") or "")
        page_price = item.get("page_price")
        if isinstance(page_price, str):
            page_price = page_price.removeprefix("¥").strip()
        ts = item.get("publish_date_lt")
        if ts:
            item_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
        else:
            item_time = str(item.get("article_date") or now_str())
        return Quote(
            symbol=keyword,
            name=str(item.get("article_title") or keyword)[:60],
            last=parse_float(item.get("article_price")),
            prev_close=parse_float(page_price),  # 原价作为涨跌幅基准
            time=item_time,
            unit="元",
            extra={
                "article_id": item.get("article_id"),
                "mall": mall,
                "subtitle": item.get("article_subtitle"),
                "channel": item.get("article_channel_name"),
                "region": item.get("article_region"),
                "url": item.get("article_url"),
            },
        )

    # ------------------------------------------------------------------ home
    async def _fetch_home(self, keyword: str, extra: dict[str, Any]) -> Quote:
        """首页推荐流（旧路径）：按 device_id 个性化轮换，无匹配时重抽换流。"""
        base_seed = str(extra.get("device_seed") or _DEFAULT_DEVICE_SEED)
        attempts = int(extra.get("attempts") or self._default_attempts)
        last_error: SourceError | None = None
        for i in range(max(1, attempts)):
            seed = base_seed if i == 0 else f"{base_seed}-{i}"
            try:
                return await self._fetch_home_once(keyword, extra, seed)
            except SourceError as exc:
                # 无匹配才重抽；网络/业务错误直接抛（重抽无意义）
                if "无匹配" not in str(exc):
                    raise
                last_error = exc
        raise last_error  # type: ignore[misc]

    async def _fetch_home_once(self, keyword: str, extra: dict[str, Any], seed: str) -> Quote:
        params = {
            "limit": str(extra.get("limit") or "20"),
            "offset": str(extra.get("offset") or "0"),
            "with_filter": "1",
            "first_startup": "0",
            "reflow_page": "1",
            "reflow_position": "1",
            **_common_params(),
        }
        params["sign"] = sign_params(params)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    _HOME_URL,
                    params=params,
                    headers={
                        "User-Agent": _USER_AGENT,
                        "Cookie": build_cookie(seed),
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise SourceError(f"smzdm 网络错误: {exc}") from exc

        if resp.status_code != 200:
            raise SourceError(f"smzdm HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise SourceError("smzdm 响应非 JSON") from exc
        if payload.get("error_code") not in (0, "0"):
            raise SourceError(
                f"smzdm 业务错误 error_code={payload.get('error_code')} "
                f"error_msg={payload.get('error_msg')!r}"
            )

        items = extract_haojia(payload)
        channel = str(extra.get("channel") or "").strip()
        region = str(extra.get("region") or "").strip()
        matches: list[tuple[float, dict[str, Any]]] = []
        kw = _norm_text(keyword)
        for it in items:
            title = it.get("article_title") or ""
            if kw not in _norm_text(title):
                continue
            if channel and it.get("article_channel_name") != channel:
                continue
            if region and it.get("article_region") != region:
                continue
            price = parse_float(it.get("article_price"))
            if price is None:
                continue  # 活动类条目无价格，跳过
            matches.append((float(it.get("time_sort") or 0), it))

        if not matches:
            raise SourceError(f"smzdm 好价流中无匹配「{keyword}」且带价格的条目")

        _, item = max(matches, key=lambda m: m[0])
        malls = item.get("article_mall")
        mall = (
            malls[0].get("article_title", "")
            if isinstance(malls, list) and malls and isinstance(malls[0], dict)
            else ""
        )
        page_price = item.get("article_page_price")
        if isinstance(page_price, str):
            page_price = page_price.removeprefix("¥").strip()
        return Quote(
            symbol=keyword,
            name=str(item.get("article_title") or keyword)[:60],
            last=parse_float(item.get("article_price")),
            prev_close=parse_float(page_price),  # 原价作为涨跌幅基准
            time=str(item.get("article_date") or now_str()),
            unit="元",
            extra={
                "article_id": item.get("article_id"),
                "mall": mall,
                "discount": item.get("article_discount"),
                "channel": item.get("article_channel_name"),
                "url": item.get("article_url"),
            },
        )
