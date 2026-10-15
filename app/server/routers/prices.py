"""行情查询 API：实时快照、tick 历史、上金所日K。"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from ...core.sources.sge_daily import SGEDailySource
from ..deps import get_services, to_thread

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("/live")
async def live(services=Depends(get_services)):
    return {"targets": services.engine.get_live_view()}


@router.get("/history")
async def history(
    target_id: str,
    hours: float = 24.0,
    limit: int = 5000,
    services=Depends(get_services),
):
    if services.target_store.get(target_id) is None:
        raise HTTPException(status_code=404, detail=f"target not found: {target_id}")
    hours = max(0.1, min(hours, 24 * 30))
    limit = max(1, min(limit, 20000))
    since = time.time() - hours * 3600
    ticks = await to_thread(services.store.get_ticks, target_id, since, limit)
    return {"target_id": target_id, "ticks": ticks}


@router.get("/daily")
async def daily(symbol: str = "Au99.99", days: int = 120, services=Depends(get_services)):
    days = max(1, min(days, 1000))
    source = SGEDailySource(timeout=float(services.engine.timeout))
    try:
        rows = await services.run_bg(source.fetch_daily(symbol, days=days))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"sge_daily failed: {exc}") from exc
    return {"symbol": symbol, "rows": rows}
