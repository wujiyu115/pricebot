"""飞书自定义机器人推送（可选渠道，webhook + 可选签名）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, ClassVar

import httpx

from .base import Message, Notifier, SendResult, register


def _sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


@register
class FeishuNotifier(Notifier):
    name = "feishu"
    display_name = "飞书机器人"
    config_keys: ClassVar[list[str]] = ["webhook_url", "secret"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        url = str(config.get("webhook_url") or "").strip()
        if not url:
            return SendResult("feishu", False, "webhook_url not configured")

        payload: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": f"{message.title}\n{message.body}"},
        }
        secret = str(config.get("secret") or "").strip()
        if secret:
            import time

            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = _sign(secret, ts)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get("code") in (0, None):
                return SendResult("feishu", True, "sent")
            return SendResult("feishu", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            return SendResult("feishu", False, str(exc))


__all__ = ["FeishuNotifier"]

