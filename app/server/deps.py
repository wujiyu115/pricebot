"""FastAPI 依赖与共享助手。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from ..server.services import AppServices


def get_services(request: Request):
    services: AppServices | None = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="services not ready")
    return services


def not_found(what: str, item_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found: {item_id}")


async def to_thread(func, *args, **kwargs):
    """Blocking calls must never run on the API event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


__all__ = ["get_services", "not_found", "to_thread"]
