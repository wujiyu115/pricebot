#!/usr/bin/env python3
"""SMZDM App API 签名 PoC（逆向成果固化，仅依赖 stdlib）。

逆向来源：com.smzdm.client.android v11.1.95 静态分析（jadx + capstone）。
算法与参数详见同目录 smzdm_reverse_notes.md。

用法：
    python3 scripts/smzdm_sign_poc.py                 # 拉首页好价流并打印
    python3 scripts/smzdm_sign_poc.py --keyword 牛奶   # 标题关键词过滤
    python3 scripts/smzdm_sign_poc.py --raw out.json   # 原始 JSON 落盘
    python3 scripts/smzdm_sign_poc.py --sign-demo      # 只打印签名过程不联网

若服务器返回 error_code!=0 或 sign 相关错误，说明新版 App 已更换密钥/算法，
按 smzdm_reverse_notes.md「密钥失效重新提取」一节重走逆向流程。
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# liblib_zdm_key.so 导出符号 getDefaultNativeKey 返回的明文（v11.1.95）
KEY = "apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
VER = "11.1.95"
VER_CODE = "1110950"
HOME_URL = "https://homepage-api.smzdm.com/v3/home"
TIME_URL = "https://app-api.smzdm.com/get_server_time"
UA = f"smzdm_android_V{VER} rv:{VER_CODE} (Xiaomi;Android9;zh-CN)smzdmapp"


# ---- 签名原语（协议规定，勿改动） ----
# SMZDM 协议用 MD5 作为签名哈希（反编译自 C4717r0.a()：
# MessageDigest.getInstance("MD5")），此处 MD5 是互操作性要求而非
# 安全选型——签名仅做请求防伪，不承载密码学安全。
# 以下两处 hashlib.md5 调用均为实现该协议，不可替换为 SHA-256。


def sign_params(params: dict) -> str:
    """按 mf/C6052a.java 还原的签名算法。

    排序键拼接 k=v&...，尾部接 &key=<KEY>，整体去空格后 MD5 大写 hex。
    空值参数（None/""）不参与拼接。
    """
    s = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] not in (None, ""))
    s += "&key=" + KEY
    return hashlib.md5(s.replace(" ", "").encode("utf-8")).hexdigest().upper()


def build_cookie(device_raw: str = "pricebot-poc-device") -> str:
    """按 mf/C6053b.java + S0.n() 还原的 Cookie。

    device_id 必须是 32 位 hex（服务器校验存在性，内容任意），
    缺失会得到 error_code=1 "device_id 没有赋值"。
    """
    # 同上：device_id 的 32 位 hex 是 SMZDM 服务器侧的格式要求
    # （真实 App 为对原始设备串做 MD5，见 H.f()），非安全用途。
    d = hashlib.md5(device_raw.encode()).hexdigest()
    parts = [
        f"device_id={d}",
        f"new_device_id={d}",
        "smzdm_id=0",
        "f=android",
        f"v={VER}",
        f"device_s={d}",
        "device_smzdm=android",
        "device_system_version=9",
        f"device_smzdm_version_code={VER_CODE}",
        "basic_v=0",
        f"session_id={uuid.uuid4().hex}",
        "user_type=0",
        "new_user_type=0",
    ]
    return "; ".join(parts)


def server_time_ms() -> int:
    """服务端毫秒时间（App 用 HttpURLConnection.getDate()，±5min 容忍）。

    接口对无签名请求返回 404，但 404 响应也带 Date 头，直接取之。
    """
    try:
        req = urllib.request.Request(TIME_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        date = r.headers.get("Date")
    except urllib.error.HTTPError as e:
        date = e.headers.get("Date")
    except Exception:
        date = None
    if date:
        import email.utils

        pt = email.utils.parsedate_tz(date)
        if pt:
            return int(time.mktime(pt[:9]) - (pt[9] or 0) + time.timezone) * 1000
    return int(time.time() * 1000)


def build_common_params() -> dict:
    """C6052a 注入的公共参数（全部参与签名）。"""
    return {
        "f": "android",
        "v": VER,
        "weixin": "0",
        "time": str(server_time_ms()),
        "basic_v": "0",
        "zhuanzai_ab": "",
    }


def fetch_home(biz_params: dict | None = None) -> dict:
    """签名调用 v3/home，返回解析后的 JSON。"""
    p = {**(biz_params or {}), **build_common_params()}
    p["sign"] = sign_params(p)
    url = f"{HOME_URL}?{urllib.parse.urlencode(p, safe='')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Cookie": build_cookie(),
            "Accept": "application/json",
        },
    )
    print(f">>> GET {url[:160]}...", file=sys.stderr)
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8", "replace")
    print(f"<<< HTTP {r.status}  {len(body)} bytes", file=sys.stderr)
    j = json.loads(body)
    if j.get("error_code") not in (0, "0"):
        raise RuntimeError(f"业务错误 error_code={j.get('error_code')} error_msg={j.get('error_msg')!r}")
    return j


def extract_haojia(home_json: dict) -> list:
    """从 v3/home 响应提取好价条目（混排流里过滤 article_first_channel_name）。"""
    comp = home_json.get("data", {}).get("component", [])
    for c in comp:
        if c.get("zz_type") == "list":
            items = c.get("zz_content", [])
            return [
                it for it in items if isinstance(it, dict) and it.get("article_first_channel_name") == "好价"
            ]
    return []


def print_haojia(items: list, keyword: str | None) -> None:
    shown = 0
    for it in items:
        title = it.get("article_title") or ""
        if keyword and keyword not in title:
            continue
        malls = it.get("article_mall")
        mall = malls[0].get("article_title", "") if isinstance(malls, list) and malls else ""
        price = it.get("article_price") or "-"
        orig = it.get("article_page_price") or "-"
        disc = it.get("article_discount") or "-"
        print(f"[{it.get('article_channel_name')}/{it.get('article_region')}] {title[:60]}")
        print(
            f"    {price} (原价{orig} 折扣{disc})  @{mall}  {it.get('article_date')}  {it.get('article_url')}"
        )
        shown += 1
    if not shown:
        print("(无匹配好价条目)")


def sign_demo() -> None:
    demo = {**build_common_params(), "limit": "10", "offset": "0"}
    print("签名明文构造：")
    s = "&".join(f"{k}={demo[k]}" for k in sorted(demo) if demo[k] not in (None, "")) + "&key=" + KEY
    print(f"  去空格前: {s}")
    print(f"  sign = {sign_params(demo)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="SMZDM App API 签名 PoC")
    ap.add_argument("--keyword", help="标题关键词过滤")
    ap.add_argument("--raw", metavar="FILE", help="原始 JSON 写入文件")
    ap.add_argument("--limit", default="20", help="limit 参数（默认 20）")
    ap.add_argument("--offset", default="0", help="offset 参数")
    ap.add_argument("--sign-demo", action="store_true", help="仅演示签名，不请求")
    args = ap.parse_args()

    if args.sign_demo:
        sign_demo()
        return 0

    j = fetch_home(
        {
            "limit": args.limit,
            "offset": args.offset,
            "with_filter": "1",
            "first_startup": "0",
            "reflow_page": "1",
            "reflow_position": "1",
        }
    )
    if args.raw:
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(j, f, ensure_ascii=False, indent=2)
        print(f"原始 JSON 已写入 {args.raw}", file=sys.stderr)
    items = extract_haojia(j)
    print(f"\n好价条目 {len(items)} 条：")
    print_haojia(items, args.keyword)
    return 0


if __name__ == "__main__":
    sys.exit(main())
