"""告警规则管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...core.monitor.rules import RULE_TYPES
from ...core.notify import list_notifiers
from ...models.schemas import RuleIn, RulePatch
from ..deps import get_services, not_found

router = APIRouter(prefix="/api/rules", tags=["rules"])

_VALID_TYPES = {item["value"] for item in RULE_TYPES}


@router.get("")
async def list_rules(services=Depends(get_services)):
    target_names = {t["id"]: t["name"] for t in services.target_store.list()}
    rules = []
    for item in services.rule_store.list():
        rules.append({**item, "target_name": target_names.get(item.get("target_id"), "?")})
    return {"rules": rules}


@router.get("/meta")
async def rules_meta(services=Depends(get_services)):
    return {
        "rule_types": RULE_TYPES,
        "channels": [{"name": c["name"], "display_name": c["display_name"]} for c in list_notifiers()],
    }


@router.post("", status_code=201)
async def create_rule(payload: RuleIn, services=Depends(get_services)):
    if payload.type not in _VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid rule type: {payload.type}")
    if services.target_store.get(payload.target_id) is None:
        raise not_found("target", payload.target_id)
    created = services.rule_store.add(payload.model_dump())
    return {"rule": created}


@router.patch("/{rule_id}")
async def update_rule(rule_id: str, payload: RulePatch, services=Depends(get_services)):
    if payload.type is not None and payload.type not in _VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid rule type: {payload.type}")
    if payload.target_id is not None and services.target_store.get(payload.target_id) is None:
        raise not_found("target", payload.target_id)
    patch = payload.model_dump(exclude_unset=True)
    updated = services.rule_store.update(rule_id, patch)
    if updated is None:
        raise not_found("rule", rule_id)
    return {"rule": updated}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, services=Depends(get_services)):
    if not services.rule_store.remove(rule_id):
        raise not_found("rule", rule_id)
    return {"ok": True}
