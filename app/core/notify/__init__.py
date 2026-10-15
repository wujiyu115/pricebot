"""Notify package -- importing registers all built-in channels."""

from __future__ import annotations

from .bark import BarkNotifier
from .base import Message, Notifier, SendResult, get_notifier, list_notifiers, register
from .dingtalk import DingTalkNotifier
from .feishu import FeishuNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier


def load_builtin_notifiers() -> None:
    assert BarkNotifier.name
    assert TelegramNotifier.name
    assert FeishuNotifier.name
    assert DingTalkNotifier.name
    assert WebhookNotifier.name


__all__ = [
    "Message",
    "Notifier",
    "SendResult",
    "get_notifier",
    "list_notifiers",
    "load_builtin_notifiers",
    "register",
]

