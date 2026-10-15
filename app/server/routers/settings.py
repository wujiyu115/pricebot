"""系统设置 API（两层配置 + 乐观锁）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...models.schemas import SettingsPatchIn
from ..deps import get_services

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(services=Depends(get_services)):
    cm = services.config_manager
    return {
        "default_settings": cm.default_config,
        "user_overrides": cm.user_overrides,
        "user_settings": cm.user_config,
        "version": cm.version,
    }


@router.put("")
async def update_settings(payload: SettingsPatchIn, services=Depends(get_services)):
    cm = services.config_manager
    if payload.version != cm.version:
        raise HTTPException(status_code=409, detail="err.settingsVersionMismatch")
    cm.apply_user_patch(payload.patch)
    return {"ok": True, "version": cm.version}


@router.delete("/keys/{path:path}")
async def unset_setting(path: str, services=Depends(get_services)):
    cm = services.config_manager
    if not cm.unset_user_key(path):
        raise HTTPException(status_code=404, detail=f"key not in user layer: {path}")
    return {"ok": True, "version": cm.version}
