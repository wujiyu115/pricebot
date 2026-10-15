"""FastAPI 应用工厂（StreamCap 同款：lifespan 组装服务 + SPA 挂载）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from ..utils.logger import logger
from .routers import alerts, channels, dashboard, prices, rules, settings, targets
from .services import AppServices

PROJECT_ROOT = Path(__file__).resolve().parents[2]

__all__ = ["PROJECT_ROOT", "create_app"]


def create_app(run_path: str | None = None) -> FastAPI:
    """Build the FastAPI application hosting the SPA and all API routers."""
    if run_path is None:
        run_path = str(PROJECT_ROOT)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = AppServices(run_path)
        app.state.services = services
        services.start()
        logger.info(f"pricebot server started (run_path={run_path})")
        yield
        services.stop()
        logger.info("pricebot server stopped")

    app = FastAPI(title="PriceBot", lifespan=lifespan)

    app.include_router(targets.router)
    app.include_router(rules.router)
    app.include_router(prices.router)
    app.include_router(alerts.router)
    app.include_router(channels.router)
    app.include_router(settings.router)
    app.include_router(dashboard.router)

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    dist_dir = PROJECT_ROOT / "frontend" / "dist"
    if not dist_dir.is_dir():
        logger.info(f"Frontend dist not found at {dist_dir}, SPA routes disabled")
        return

    # 已注册的 API 路由优先匹配；此 catch-all 服务静态资源并对未知路径
    # 回退到 index.html，让 React Router 接管前端路由。
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        file = (dist_dir / full_path).resolve()
        if full_path and file.is_file() and file.is_relative_to(dist_dir):
            return FileResponse(file)
        return FileResponse(dist_dir / "index.html")

    logger.info(f"Serving frontend from {dist_dir}")
