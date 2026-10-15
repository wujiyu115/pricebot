"""Notifier base classes and registry.

Each push channel is an adapter registered by name. ``NotificationManager``
fans a message out to all enabled channels (or an explicit subset chosen by a
rule). Adding a channel = new module + ``@register`` -- nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar


@dataclass
class Message:
    """A rendered notification ready to be pushed."""

    title: str
    body: str
    group: str = "PriceBot"
    url: str = ""
    severity: str = "info"  # info | warn | alert
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    channel: str
    ok: bool
    detail: str = ""


class Notifier(ABC):
    """Base class for push channels."""

    name: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    #: config keys this channel reads from settings["notify"][name]
    config_keys: ClassVar[list[str]] = []

    @abstractmethod
    async def send(self, message: Message, config: dict[str, Any]) -> SendResult:
        """Push ``message`` using channel config ``config`` (effective dict)."""


_REGISTRY: dict[str, type[Notifier]] = {}

_NotifierT = TypeVar("_NotifierT", bound=Notifier)


def register(cls: type[_NotifierT]) -> type[_NotifierT]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a non-empty `name`")
    _REGISTRY[cls.name] = cls
    return cls


def get_notifier(name: str) -> type[Notifier]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown notifier: {name!r}")
    return _REGISTRY[name]


def list_notifiers() -> list[dict[str, Any]]:
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "config_keys": cls.config_keys,
        }
        for cls in _REGISTRY.values()
    ]


__all__ = ["Message", "Notifier", "SendResult", "get_notifier", "list_notifiers", "register"]
