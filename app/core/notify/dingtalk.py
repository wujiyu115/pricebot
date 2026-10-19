"""钉钉自定义机器人推送（可选渠道，加签模式）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any, ClassVar
from urllib.parse import quote_plus

import httpx

from .base import Message, Notifier, SendResult, register


@register
class DingTalkNotifier(Notifier):
    name = "dingtalk"
    display_name = "钉钉机器人"
    config_keys: ClassVar[list[str]] = ["webhook_url", "secret"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        url = str(config.get("webhook_url") or "").strip()
        if not url:
            return SendResult("dingtalk", False, "webhook_url not configured")

        secret = str(config.get("secret") or "").strip()
        if secret:
            ts = str(round(time.time() * 1000))
            string_to_sign = f"{ts}\n{secret}"
            sign = base64.b64encode(
                hmac.new(
                    secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
                ).digest()
            ).decode("utf-8")
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={quote_plus(sign)}"

        text = f"## {message.title}\n\n{message.body}"
        if message.url:
            text += f"\n\n[查看详情]({message.url})"
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": message.title, "text": text},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 200 and resp.json().get("errcode") == 0:
                return SendResult("dingtalk", True, "sent")
            return SendResult("dingtalk", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            return SendResult("dingtalk", False, str(exc))


__all__ = ["DingTalkNotifier"]
