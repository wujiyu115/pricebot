"""企业微信群机器人推送（备选渠道，直连 qyapi.weixin.qq.com 无需代理）。

协议（2026-10 实测验证，见 AGENTS.md）:
  POST {webhook_url}  JSON: {"msgtype": "markdown", "markdown": {"content": "..."}}
  - 成功返回 {"errcode": 0, "errmsg": "ok"}；无效 key 返回
    {"errcode": 93000, "errmsg": "invalid webhook url, ..."}（成功判定 errcode == 0）
  - 群内添加机器人即得 webhook url（含 key 参数）；markdown 消息上限 4096 字节
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from .base import Message, Notifier, SendResult, register


@register
class WeComNotifier(Notifier):
    name = "wecom"
    display_name = "企业微信机器人"
    config_keys: ClassVar[list[str]] = ["webhook_url"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        url = str(config.get("webhook_url") or "").strip()
        if not url:
            return SendResult("wecom", False, "webhook_url not configured")

        content = f"**{message.title}**\n{message.body}"
        if message.url:
            content += f"\n\n[查看详情]({message.url})"
        if len(content.encode("utf-8")) > 4000:
            content = content[:1300]  # markdown 上限 4096 字节，保守截断
        payload = {"msgtype": "markdown", "markdown": {"content": content}}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
            try:
                data = resp.json()
            except ValueError:
                return SendResult("wecom", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
            if resp.status_code == 200 and data.get("errcode") == 0:
                return SendResult("wecom", True, "sent")
            return SendResult(
                "wecom", False, f"errcode {data.get('errcode')}: {data.get('errmsg', '')[:100]}"
            )
        except Exception as exc:  # fan-out must not die on one channel
            return SendResult("wecom", False, str(exc))


__all__ = ["WeComNotifier"]
