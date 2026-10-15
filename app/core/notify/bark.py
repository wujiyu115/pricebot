"""Bark 推送（iOS APNs，优先支持）。

配置（settings["notify"]["bark"]）::

    {
      "enabled": true,
      "server": "https://api.day.app",   # 自建 bark-server 可改
      "device_keys": "key1,key2",        # 多设备逗号分隔
      "group": "PriceBot",               # 消息分组
      "sound": "minuet",                 # 铃声，空=默认
      "icon": "",                        # 可选自定义图标 URL
      "level": ""                        # 可选 activePassive/active/timeSensitive/critical
    }
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote

import httpx

from .base import Message, Notifier, SendResult, register


@register
class BarkNotifier(Notifier):
    name = "bark"
    display_name = "Bark（iOS 推送）"
    config_keys: ClassVar[list[str]] = ["server", "device_keys", "group", "sound", "icon", "level"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        keys = [k.strip() for k in str(config.get("device_keys") or "").split(",") if k.strip()]
        if not keys:
            return SendResult("bark", False, "no device_keys configured")

        server = str(config.get("server") or "https://api.day.app").rstrip("/")
        group = str(config.get("group") or message.group or "PriceBot")
        params: dict[str, str] = {"group": group}
        sound = str(config.get("sound") or "").strip()
        if sound:
            params["sound"] = sound
        icon = str(config.get("icon") or "").strip()
        if icon:
            params["icon"] = icon
        level = str(config.get("level") or "").strip()
        if level:
            params["level"] = level
        if message.url:
            params["url"] = message.url

        failures: list[str] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for key in keys:
                url = (
                    f"{server}/{quote(key)}/{quote(message.title)}/{quote(message.body)}"
                    f"?{'&'.join(f'{k}={quote(v)}' for k, v in params.items())}"
                )
                try:
                    resp = await client.get(url)
                    ok = resp.status_code == 200 and resp.json().get("code") == 200
                    if not ok:
                        failures.append(f"{key[:8]}…: HTTP {resp.status_code} {resp.text[:80]}")
                except Exception as exc:
                    failures.append(f"{key[:8]}…: {exc}")

        if failures:
            return SendResult("bark", False, "; ".join(failures))
        return SendResult("bark", True, f"pushed to {len(keys)} device(s)")


__all__ = ["BarkNotifier"]
