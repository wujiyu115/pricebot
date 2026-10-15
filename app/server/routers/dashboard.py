"""仪表盘聚合 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...core.sources import list_source_names
from ..deps import get_services, to_thread

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(services=Depends(get_services)):
    targets = services.target_store.list()
    rules = services.rule_store.list()
    live = {v["target"]["id"]: v for v in services.engine.get_live_view()}
    recent_alerts = await to_thread(services.store.list_alerts, 10)
    return {
        "engine": {
            "running": services.loop_service.loop is not None
            and services.loop_service.loop.is_running(),
            "interval_seconds": services.engine.interval,
        },
        "counts": {
            "targets": len(targets),
            "targets_enabled": sum(1 for t in targets if t.get("enabled", True)),
            "rules": len(rules),
            "rules_enabled": sum(1 for r in rules if r.get("enabled", True)),
        },
        "quotes": [
            {
                "target_id": t["id"],
                "name": t["name"],
                "symbol": t["symbol"],
                "source": t["source"],
                "enabled": t.get("enabled", True),
                "quote": (live.get(t["id"]) or {}).get("quote"),
                "last_error": (live.get(t["id"]) or {}).get("last_error"),
            }
            for t in targets
        ],
        "recent_alerts": recent_alerts,
        "sources": list_source_names(),
    }
