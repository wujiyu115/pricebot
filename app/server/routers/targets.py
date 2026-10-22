"""监控标的管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...core.sources import list_source_names
from ...core.sources.base import SourceError, get_source_class
from ...core.search import search_stocks
from ...models.schemas import TargetIn, TargetPatch, VerifyIn
from ..deps import get_services, not_found

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("")
async def list_targets(services=Depends(get_services)):
    views = services.engine.get_live_view()
    status_by_id = {v["target"]["id"]: v for v in views}
    out = []
    for target in services.target_store.list():
        view = status_by_id.get(target["id"]) or {}
        status_keys = ("last_poll", "last_error", "error_count", "quote")
        out.append({**target, "_status": {k: view.get(k) for k in status_keys}})
    return {"targets": out}


@router.get("/sources")
async def get_sources(services=Depends(get_services)):
    from ...core.sources import list_sources

    return {"sources": list_sources()}


@router.get("/search")
async def search_symbol(q: str, services=Depends(get_services)):
    """按名称/拼音/代码联想搜索股票（A股/指数/港股），返回 sina_stock 可用候选。"""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is empty")
    try:
        results = await search_stocks(query, timeout=float(services.engine.timeout))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"search failed: {exc}") from exc
    return {"results": results}


@router.post("/verify", status_code=200)
async def verify_symbol(payload: VerifyIn, services=Depends(get_services)):
    """保存前试抓一次行情，验证 source+symbol（及 generic_http 的 extra）可用。"""
    if payload.source not in list_source_names():
        raise HTTPException(status_code=422, detail=f"unknown source: {payload.source}")
    source_cls = get_source_class(payload.source)
    source = source_cls(timeout=float(services.engine.timeout))
    try:
        quote = await source.fetch(payload.symbol, payload.extra or {})
    except SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # 上游网络/解析异常统一回报
        raise HTTPException(status_code=502, detail=f"fetch failed: {exc}") from exc
    if quote.last is None:
        raise HTTPException(status_code=422, detail="代码无法获取价格（返回无有效价格字段）")
    return {"ok": True, "quote": quote.as_dict()}


@router.post("", status_code=201)
async def create_target(payload: TargetIn, services=Depends(get_services)):
    if payload.source not in list_source_names():
        raise HTTPException(status_code=422, detail=f"unknown source: {payload.source}")
    target = payload.model_dump(exclude_none=True)
    created = services.target_store.add(target)
    return {"target": created}


@router.patch("/{target_id}")
async def update_target(target_id: str, payload: TargetPatch, services=Depends(get_services)):
    if payload.source is not None and payload.source not in list_source_names():
        raise HTTPException(status_code=422, detail=f"unknown source: {payload.source}")
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated = services.target_store.update(target_id, patch)
    if updated is None:
        raise not_found("target", target_id)
    return {"target": updated}


@router.delete("/{target_id}")
async def delete_target(target_id: str, services=Depends(get_services)):
    if not services.target_store.remove(target_id):
        raise not_found("target", target_id)
    # 级联删除该标的下的规则
    removed_rules = [r for r in services.rule_store.list() if r.get("target_id") == target_id]
    for rule in removed_rules:
        services.rule_store.remove(rule["id"])
    return {"ok": True, "removed_rules": len(removed_rules)}


@router.post("/{target_id}/refresh")
async def refresh_target(target_id: str, services=Depends(get_services)):
    try:
        result = await services.run_bg(services.engine.refresh_now(target_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise not_found("target", target_id)
    quote = result.get("quote")
    return {
        "ok": quote is not None,
        "quote": quote.as_dict() if quote else None,
        "last_error": result.get("last_error"),
    }
