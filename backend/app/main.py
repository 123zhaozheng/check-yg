"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await init_db()
    yield


app = FastAPI(
    title="Check-YG API",
    lifespan=lifespan,
)

# CORS middleware（开发分离代理时仍需要；生产同源后可置空 CORS_ORIGINS）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routers
from app.routers import auth_router, users_router
from app.routers.dashboard import router as dashboard_router
from app.routers.tasks import router as tasks_router, findings_router as findings_router
from app.routers.customers import router as customers_router
from app.routers.settings import router as settings_router
from app.routers.reviews import router as reviews_router
from app.routers.reports import router as reports_router
from app.routers.exports import router as exports_router
from app.websocket.router import router as websocket_router

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(findings_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(websocket_router)


# ---------------------------------------------------------------------------
# 生产同源：FastAPI 挂 frontend/dist 静态 + SPA fallback
# 开发模式下 dist 可能不存在（前端单独 `pnpm dev` 走 Vite proxy），此时跳过挂载。
# ---------------------------------------------------------------------------


def _frontend_dist() -> Path | None:
    """返回存在的 frontend/dist 目录，不存在返回 None。"""
    dist = Path(settings.FRONTEND_DIST)
    if not dist.is_absolute():
        # backend 从 backend/ 启动，相对路径相对 backend/ 解析。
        dist = Path(__file__).resolve().parent.parent / dist
    index_html = dist / "index.html"
    if index_html.exists():
        return dist
    return None


_DIST = _frontend_dist()

if _DIST is not None:
    _ASSETS = _DIST / "assets"
    if _ASSETS.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_ASSETS)),
            name="frontend-assets",
        )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request):
        """SPA fallback：非 /api、非 /ws、非 /assets 的路径都返 index.html，
        让前端路由接管。已存在的静态文件（favicon 等）直接返回。
        """
        # /api 与 /ws 由各自的 router/handler 处理，不应走到这里；但
        # FastAPI 路由匹配顺序下，已注册的 /api/* 优先匹配，这里兜底其余。
        if full_path.startswith(("api/", "ws")):
            raise HTTPException(status_code=404)

        # 根目录下的静态文件（如 favicon.ico、vite.svg）直接返回。
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))

        index = _DIST / "index.html"
        return FileResponse(str(index))
else:
    @app.get("/")
    async def root():
        """Health check（开发模式，无 frontend/dist 时）。"""
        return {"status": "ok"}

