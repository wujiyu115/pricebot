"""股票名称搜索解析单测（腾讯 smartbox 联想接口，样本为 2026-10-21 实测）。"""

from __future__ import annotations

from app.core.search import parse_smartbox


def test_parse_mixed_results():
    """中文名/拼音/港股/指数混合结果，unicode 转义解码 + 类型过滤。"""
    # 2026-10-21 实测: 搜「腾讯」
    raw = (
        'v_hint="sh~000847~\\u817e\\u8baf\\u6d4e\\u5b89~txja~ZS^hk~00700~'
        '\\u817e\\u8baf\\u63a7\\u80a1~txkg~GP^hk~80700~\\u817e\\u8baf\\u63a7\\u80a1r~txkgr~GP'
        '^us~tcehy.ps~\\u817e\\u8baf\\u63a7\\u80a1(adr)~txkgadr~GP^hk~13005~'
        '\\u817e\\u8baf\\u6cd5\\u5174\\u4e03\\u4e09\\u8d2dA~txfxqsga~QZ"'
    )
    results = parse_smartbox(raw)
    # sh000847 指数 + hk00700 正股 + hk80700（人民币柜台，同为 GP 正股）；us ADR、QZ 权证不返回
    assert [r["symbol"] for r in results] == ["sh000847", "hk00700", "hk80700"]
    assert results[0]["name"] == "腾讯济安"
    assert results[0]["kind"] == "index"
    assert results[1]["name"] == "腾讯控股"
    assert results[1]["kind"] == "stock"
    assert results[1]["source"] == "sina_stock"


def test_parse_a_share_and_pinyin():
    # 2026-10-21 实测: 搜「茅台」
    raw = 'v_hint="sh~600519~\\u8d35\\u5dde\\u8305\\u53f0~gzmt~GP-A"'
    results = parse_smartbox(raw)
    assert len(results) == 1
    assert results[0] == {
        "source": "sina_stock",
        "symbol": "sh600519",
        "name": "贵州茅台",
        "market": "sh",
        "kind": "stock",
    }


def test_parse_fund_filtered():
    """沪深基金（KJ/jj 类型）应被过滤，不进入候选。"""
    # 2026-10-21 实测: 搜「00700」（截取含基金部分）
    raw = (
        'v_hint="hk~00700~\\u817e\\u8baf\\u63a7\\u80a1~txkg~GP^jj~007005~'
        '\\u4e2d\\u91d1\\u65b0\\u533b\\u836f\\u80a1\\u7968C~zjxyygpc~KJ"'
    )
    results = parse_smartbox(raw)
    assert [r["symbol"] for r in results] == ["hk00700"]


def test_parse_empty_and_no_match():
    assert parse_smartbox('v_hint="N"') == []
    assert parse_smartbox("") == []
    assert parse_smartbox("garbage without quotes") == []


def test_parse_dedup():
    raw = (
        'v_hint="sh~600519~\\u8d35\\u5dde\\u8305\\u53f0~gzmt~GP-A^'
        'sh~600519~\\u8d35\\u5dde\\u8305\\u53f0~gzmt~GP-A"'
    )
    results = parse_smartbox(raw)
    assert len(results) == 1
