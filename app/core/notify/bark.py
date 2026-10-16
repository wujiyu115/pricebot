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

        payload: dict[str, str] = {
            "device_key": "",  # 每个设备单独填
            "title": message.title,
            "body": message.body,
            "group": group,
        }
        if sound:
            payload["sound"] = sound
        if icon:
            payload["icon"] = icon
        if level:
            payload["level"] = level
        if message.url:
            payload["url"] = message.url

        # Bark 官方 POST JSON 接口：支持任意长度正文（GET 路径式 API 会把长多行
        # 正文编进 URL，聚合简报等长消息直接 404，2026-12 实测踩坑）
        failures: list[str] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for key in keys:
                payload["device_key"] = key
                try:
                    resp = await client.post(f"{server}/push", json=payload)
                    ok = resp.status_code == 200 and resp.json().get("code") == 200
                    if not ok:
                        failures.append(f"{key[:8]}…: HTTP {resp.status_code} {resp.text[:80]}")
                except Exception as exc:
                    failures.append(f"{key[:8]}…: {exc}")

        if failures:
            return SendResult("bark", False, "; ".join(failures))
        return SendResult("bark", True, f"pushed to {len(keys)} device(s)")


__all__ = ["BarkNotifier"]
