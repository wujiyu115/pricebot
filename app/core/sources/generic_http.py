"""通用 HTTP 数据源（配置驱动的动态扩展）。

不写代码即可接入任意价格接口：在标的配置里声明
``source: generic_http`` 并在 ``extra`` 里给出提取规则。

extra 规则::

    {
      "url": "https://api.example.com/price?symbol=XAU",
      "method": "GET",                 # 可选，默认 GET
      "headers": {"Authorization": "Bearer x"},   # 可选
      "body": {"foo": 1},              # 可选（POST JSON）
      "json_path": "data.price",       # JSON 响应：点路径，支持数组下标 data.items[0].price
      "regex": r"price[=:]\\s*([0-9.]+)" # 文本/HTML 响应：第一个捕获组
    }

``json_path`` 与 ``regex`` 二选一；都不填时若响应体本身是纯数字也接受。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .base import Quote, SourceAdapter, SourceError, parse_float, register


def extract_json_path(data: Any, path: str) -> Any:
    """Walk a dot path with optional list indices, e.g. ``a.b[0].c``."""
    node = data
    for token in path.split("."):
        token = token.strip()
        if not token:
            continue
        match = re.fullmatch(r"([^\[\]]+)((?:\[\d+\])*)", token)
        if not match:
            raise KeyError(token)
        key, indices = match.group(1), match.group(2)
        node = node[key]
        for idx in re.findall(r"\[(\d+)\]", indices):
            node = node[int(idx)]
    return node


@register
class GenericHTTPSource(SourceAdapter):
    name = "generic_http"
    description = "通用 HTTP 数据源（JSONPath/正则提取，免代码接入任意接口）"

    def __init__(self, timeout: float = 10.0) -> None:
        super().__init__(timeout=timeout)

    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        extra = extra or {}
        url = str(extra.get("url") or "").strip()
        if not url:
            raise SourceError("generic_http requires `extra.url`")

        method = str(extra.get("method") or "GET").upper()
        headers = dict(extra.get("headers") or {})
        body = extra.get("body")

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            if body is not None and method in {"POST", "PUT", "PATCH"}:
                resp = await client.request(method, url, headers=headers, json=body)
            else:
                resp = await client.request(method, url, headers=headers)

        if resp.status_code != 200:
            raise SourceError(f"generic_http HTTP {resp.status_code} from {url}")

        raw_value = self._extract(resp, extra)
        value = parse_float(raw_value)
        if value is None:
            raise SourceError(f"generic_http extracted non-numeric value {raw_value!r} from {url}")
        return Quote(symbol=symbol, name=str(extra.get("name") or symbol), last=value)

    def _extract(self, resp: httpx.Response, extra: dict[str, Any]) -> Any:
        json_path = str(extra.get("json_path") or "").strip()
        regex = str(extra.get("regex") or "").strip()

        if json_path:
            try:
                payload = resp.json()
            except ValueError as exc:
                raise SourceError(f"generic_http non-JSON body for json_path: {exc}") from exc
            try:
                return extract_json_path(payload, json_path)
            except (KeyError, IndexError, TypeError) as exc:
                raise SourceError(f"generic_http json_path miss ({extra['json_path']}): {exc}") from exc

        if regex:
            match = re.search(regex, resp.text)
            if not match or not match.groups():
                raise SourceError(f"generic_http regex miss: {regex}")
            return match.group(1)

        text = resp.text.strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", text):
            return text
        return None


__all__ = ["GenericHTTPSource", "extract_json_path"]
