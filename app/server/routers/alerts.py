"""告警记录 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_services, to_thread

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    limit: int = 50,
    target_id: str | None = None,
    services=Depends(get_services),
):
    limit = max(1, min(limit, 500))
    alerts = await to_thread(services.store.list_alerts, limit, target_id)
    return {"alerts": alerts}


@router.delete("")
async def clear_alerts(services=Depends(get_services)):
    await to_thread(services.store.clear_alerts)
    return {"ok": True}
