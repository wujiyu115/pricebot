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
from .binance import BinanceSource
from .generic_http import GenericHTTPSource
from .manmanbuy import ManmanbuySource
from .sge_daily import SGEDailySource
from .sina import SinaSource
from .sina_futures import SinaFuturesSource
from .sina_stock import SinaStockSource
from .smzdm import SmzdmSource


def load_builtin_sources() -> None:
    """Import side effects register adapters; kept explicit for clarity/tests."""
    assert SinaSource.name
    assert SGEDailySource.name
    assert GenericHTTPSource.name
    assert BinanceSource.name
    assert SinaStockSource.name
    assert SinaFuturesSource.name
    assert SmzdmSource.name
    assert ManmanbuySource.name


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
