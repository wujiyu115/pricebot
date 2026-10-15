"""Source adapter package -- importing this module registers all built-in sources."""

from __future__ import annotations

from .base import (
    Quote,
    SourceAdapter,
    SourceError,
    get_source_class,
    list_source_names,
    list_sources,
    register,
)
from .generic_http import GenericHTTPSource
from .sge_daily import SGEDailySource
from .sina import SinaSource
from .sina_stock import SinaStockSource


def load_builtin_sources() -> None:
    """Import side effects register adapters; kept explicit for clarity/tests."""
    assert SinaSource.name
    assert SGEDailySource.name
    assert GenericHTTPSource.name
    assert SinaStockSource.name


__all__ = [
    "Quote",
    "SourceAdapter",
    "SourceError",
    "get_source_class",
    "list_source_names",
    "list_sources",
    "load_builtin_sources",
    "register",
]
