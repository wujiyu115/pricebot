"""Ntfy 推送（开源，Android/iOS APP 弹窗，HTTP 发布，自托管友好）。

协议（2026-10 实测验证，见 AGENTS.md）:
  POST {server}/  JSON: {"topic", "title", "message", "priority": <int 1-5>, "tags": [...]}
  - **priority 在 JSON 体里必须是整数**（min=1/low=2/default=3/high=4/urgent=5）；
    字符串别名（"high" 等）只支持 HTTP 头/CLI，JSON 里传字符串会得到**误导性的
    400 "request body must be valid JSON"**（实测踩坑）
  - 中文标题/正文正常；tags 用官方 shortcode（如 chart_with_upwards_trend）
  - 手机端装 ntfy App 订阅同一 topic 即收弹窗；topic 名即"密码"，建议加随机后缀

配置（settings["notify"]["ntfy"]）::
    {"enabled": true, "server": "https://ntfy.sh", "topic": "my-pricebot-xx9z",
     "priority": "high", "tags": "chart_with_upwards_trend"}
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

import httpx

from .base import Message, Notifier, SendResult, register

_PRIORITY_MAP = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}
_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@register
class NtfyNotifier(Notifier):
    name = "ntfy"
    display_name = "Ntfy（开源 APP 弹窗）"
    config_keys: ClassVar[list[str]] = ["server", "topic", "priority", "tags"]

    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        topic = str(config.get("topic") or "").strip()
        if not topic:
            return SendResult("ntfy", False, "topic not configured")
        if not _TOPIC_RE.match(topic):
            return SendResult("ntfy", False, f"invalid topic: {topic!r}")

        server = str(config.get("server") or "https://ntfy.sh").rstrip("/")
        priority_raw = str(config.get("priority") or "high").strip().lower()
        # JSON 体要求整数优先级；接受 1-5 或别名
        if priority_raw.isdigit() and priority_raw in {"1", "2", "3", "4", "5"}:
            priority = int(priority_raw)
        else:
            priority = _PRIORITY_MAP.get(priority_raw, 4)

        payload: dict[str, Any] = {
            "topic": topic,
            "title": message.title,
            "message": message.body,
            "priority": priority,
        }
        tags = [t.strip() for t in str(config.get("tags") or "").split(",") if t.strip()]
        if tags:
            payload["tags"] = tags
        if message.url:
            payload["click"] = message.url  # 点击通知跳转（JSON 发布的官方字段）

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{server}/", json=payload)
            if resp.status_code == 200 and resp.json().get("event") == "message":
                return SendResult("ntfy", True, f"published to topic {topic!r}")
            try:
                detail = resp.json().get("error", resp.text[:120])
            except ValueError:
                detail = resp.text[:120]
            return SendResult("ntfy", False, f"HTTP {resp.status_code}: {detail}")
        except Exception as exc:  # fan-out must not die on one channel
            return SendResult("ntfy", False, str(exc))


__all__ = ["NtfyNotifier"]
