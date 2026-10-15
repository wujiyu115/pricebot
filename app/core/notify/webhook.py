"""通用 webhook 推送（可选渠道，POST JSON）。"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .base import Message, Notifier, SendResult, register


@register
class WebhookNotifier(Notifier):
    name = "webhook"
    display_name = "通用 Webhook"
    config_keys: ClassVar[list[str]] = ["url", "method", "headers"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        url = str(config.get("url") or "").strip()
        if not url:
            return SendResult("webhook", False, "url not configured")
        method = str(config.get("method") or "POST").upper()
        headers = dict(config.get("headers") or {})
        payload = {
            "title": message.title,
            "body": message.body,
            "group": message.group,
            "url": message.url,
            "severity": message.severity,
            **message.extra,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.request(method, url, headers=headers, json=payload)
            if 200 <= resp.status_code < 300:
                return SendResult("webhook", True, f"HTTP {resp.status_code}")
            return SendResult("webhook", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            return SendResult("webhook", False, str(exc))


__all__ = ["WebhookNotifier"]

