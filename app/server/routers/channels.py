"""推送渠道配置与测试 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...core.notify import get_notifier, list_notifiers
from ...models.schemas import ChannelConfigIn
from ..deps import get_services

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("")
async def list_channels(services=Depends(get_services)):
    notify_config = services.config_manager.user_config.get("notify", {})
    channels = []
    for meta in list_notifiers():
        config = dict(notify_config.get(meta["name"]) or {})
        channels.append({**meta, "config": config})
    return {"channels": channels}


@router.put("/{name}")
async def update_channel(name: str, payload: ChannelConfigIn, services=Depends(get_services)):
    try:
        get_notifier(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown channel: {name}") from None

    patch: dict = {"notify": {name: dict(payload.values)}}
    if payload.enabled is not None:
        patch["notify"][name]["enabled"] = payload.enabled
    services.config_manager.apply_user_patch(patch)
    return {"ok": True, "version": services.config_manager.version}


@router.post("/{name}/test")
async def test_channel(name: str, services=Depends(get_services)):
    try:
        get_notifier(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown channel: {name}") from None

    try:
        result = await services.run_bg(services.notifier.send_test(name))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": result.ok, "channel": result.channel, "detail": result.detail}
