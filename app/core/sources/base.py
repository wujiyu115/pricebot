"""Data-source adapter base classes and registry.

A *source adapter* knows how to fetch a quote for one symbol from one upstream
provider. New sources are added by dropping a module into ``app/core/sources/``
that subclasses :class:`SourceAdapter` and calls :class:`register` -- the
engine discovers everything through the registry, so adding a source never
requires touching engine or API code.

For config-driven extension without writing code, use the ``generic_http``
source (see ``generic_http.py``): it extracts a number from any HTTP response
via JSON dot-paths or a regex.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, TypeVar


@dataclass
class Quote:
    """One successful fetch of a symbol."""

    symbol: str
    name: str = ""
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    turnover: float | None = None
    time: str = ""
    unit: str = ""  # 元/克（贵金属）、元（股票）、点（指数）
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """API 序列化。含 ``extra``（源附加信息：smzdm 的商城/到手价、
        manmanbuy 的历史最低/价位状态/日线点数等）。

        ``extra`` 是各源自定的扁平小 dict（实测最大 ~0.5KB），随 ``/api/dashboard``
        一起下发，供前端展示与推送文案引用。
        """
        return {
            "symbol": self.symbol,
            "name": self.name,
            "last": self.last,
            "bid": self.bid,
            "ask": self.ask,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "prev_close": self.prev_close,
            "volume": self.volume,
            "turnover": self.turnover,
            "time": self.time,
            "unit": self.unit,
            "extra": dict(self.extra or {}),
        }


class SourceError(Exception):
    """Raised when a source cannot produce a usable quote."""


class SourceAdapter(ABC):
    """Base class for all price sources."""

    #: registry name, referenced by targets ("source": "<name>")
    name: ClassVar[str] = ""
    #: human description shown in the UI
    description: ClassVar[str] = ""
    #: optional URL template / docs shown in the UI
    homepage: ClassVar[str] = ""
    #: known symbols offered as quick-pick in the UI: {symbol: display}
    known_symbols: ClassVar[dict[str, str]] = {}

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    @abstractmethod
    async def fetch(self, symbol: str, extra: dict[str, Any] | None = None) -> Quote:
        """Fetch one quote for ``symbol``. Raise :class:`SourceError` on failure."""


_REGISTRY: dict[str, type[SourceAdapter]] = {}

_SourceT = TypeVar("_SourceT", bound=SourceAdapter)


def register(cls: type[_SourceT]) -> type[_SourceT]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a non-empty `name`")
    if cls.name in _REGISTRY and _REGISTRY[cls.name] is not cls:
        raise ValueError(f"duplicate source name: {cls.name}")
    _REGISTRY[cls.name] = cls
    return cls


def get_source_class(name: str) -> type[SourceAdapter]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown source: {name!r} (available: {list_source_names()})")
    return _REGISTRY[name]


def list_sources() -> list[dict[str, Any]]:
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "homepage": cls.homepage,
            "known_symbols": cls.known_symbols,
        }
        for cls in _REGISTRY.values()
    ]


def list_source_names() -> list[str]:
    return sorted(_REGISTRY)


# --------------------------------------------------------------------- shared
def parse_float(value: Any) -> float | None:
    """Parse a numeric-ish string, returning None for '--'/''/None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


__all__ = [
    "Quote",
    "SourceAdapter",
    "SourceError",
    "get_source_class",
    "list_source_names",
    "list_sources",
    "now_str",
    "parse_float",
    "re",
    "register",
]
