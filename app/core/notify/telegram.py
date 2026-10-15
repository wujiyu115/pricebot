"""Telegram Bot 推送（可选渠道）。"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .base import Message, Notifier, SendResult, register


@register
class TelegramNotifier(Notifier):
    name = "telegram"
    display_name = "Telegram Bot"
    config_keys: ClassVar[list[str]] = ["bot_token", "chat_id"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        token = str(config.get("bot_token") or "").strip()
        chat_id = str(config.get("chat_id") or "").strip()
        if not token or not chat_id:
            return SendResult("telegram", False, "bot_token/chat_id not configured")

        text = f"*{message.title}*\n{message.body}"
        if message.url:
            text += f"\n{message.url}"
        api = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    api,
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                )
            if resp.status_code == 200 and resp.json().get("ok"):
                return SendResult("telegram", True, "sent")
            return SendResult("telegram", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            return SendResult("telegram", False, str(exc))


__all__ = ["TelegramNotifier"]

