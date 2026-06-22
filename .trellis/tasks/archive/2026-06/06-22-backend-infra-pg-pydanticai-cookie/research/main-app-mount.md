# Research: main-app-mount (FastAPI 应用装配现状)

- **Query**: B1 — main.py 应用装配、路由/中间件/静态挂载现状
- **Scope**: internal
- **Date**: 2026-06-22

## Findings

### 1. 入口与 app 工厂

**`backend/app/main.py`（59 行，无 app 工厂）**：

模块级直接 `app = FastAPI(title="Check-YG API", lifespan=lifespan)` (main.py:19-22)，**不是工厂函数**。`uvicorn` 直接 `app:app` 启动（pyproject.toml 无 `[tool.uv]` script，`uvicorn app.main:app` 手动启）。

`lifespan` (main.py:12-16) 是 `@asynccontextmanager`，startup 调 `init_db()`（create_all + seed），shutdown 无操作。**B1 加 Alembic 后**，`init_db()` 要么改成调 `alembic upgrade head`，要么保留 `create_all` 仅用于测试，生产走 alembic。若 pg 起步空库，`lifespan` 里可能要 `await engine.dispose()` 在 shutdown。

### 2. 路由注册（main.py:40-58）

```python
from app.routers import auth_router, users_router
from app.routers.tasks import router as tasks_router
from app.routers.customers import router as customers_router
from app.routers.settings import router as settings_router
from app.routers.reviews import router as reviews_router
from app.routers.reports import router as reports_router
from app.routers.exports import router as exports_router
from app.websocket.router import router as websocket_router

app.include_router(auth_router, prefix="/api")        # /api/auth/*
app.include_router(users_router, prefix="/api")       # /api/users/*
app.include_router(tasks_router, prefix="/api")       # /api/tasks/*
app.include_router(customers_router, prefix="/api")   # /api/customers/*
app.include_router(settings_router, prefix="/api")    # /api/settings/*
app.include_router(reviews_router, prefix="/api")     # /api/tasks/{id}/review, /api/reviews/*
app.include_router(reports_router, prefix="/api")     # /api/tasks/{id}/report, /api/reports/*
app.include_router(exports_router, prefix="/api")     # /api/tasks/{id}/export/*, /api/exports/*
app.include_router(websocket_router)                  # /ws（无 /api 前缀）
```

**注意**：
- `routers/__init__.py:1-7` 只导出 `auth_router` 和 `users_router`，其余 6 个 router 在 main.py 里逐个 `from app.routers.xxx import router`。
- `reviews`/`reports`/`exports` 的 router 自身**没有 prefix**（`router = APIRouter(tags=["reviews"])` reviews.py:20），端点路径里带 `/tasks/{task_id}/...` 和 `/reviews/{review_id}/...`，靠 main.py 的 `/api` 前缀拼成 `/api/tasks/{id}/review` 等。
- `tasks` router 自带 `prefix="/tasks"` (tasks.py:20)，加 `/api` → `/api/tasks/*`。
- `websocket_router` 自带 `/ws` 路径（websocket/router.py:19），**无 `/api` 前缀**，挂载时也不加 prefix（main.py:58）。

**健康检查**：`@app.get("/")` (main.py:34-37) 返回 `{"status":"ok"}`，**这是唯一的根路径端点**。B1 静态挂载 frontend/dist 后，`/` 要让给 SPA index.html，健康检查改路径（如 `/api/health`）或保留但放在静态挂载之前（FastAPI 路由按注册顺序匹配，先注册的赢）。

### 3. 中间件（main.py:24-31）

**只有 CORSMiddleware**：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

无 GZip、无 SessionMiddleware、无 TrustedHost、无自定义 middleware。**B1 cookie 化不需要 SessionMiddleware**（JWT 无状态，cookie 只是载体）。静态挂载后若前后端同源，CORS 可移除或改 `allow_origins=[]`。

### 4. WebSocket 装配

**`backend/app/websocket/router.py`（62 行）**：`@router.websocket("/ws")` (router.py:19) 是唯一 WS 端点。鉴权读 `websocket.query_params.get("token")` (router.py:39)，用 `verify_token` 校验 `type=="access"`，再查 User。连接由 `ConnectionManager` (manager.py:13-55) 按 `user_id` 维护 `dict[int, set[WebSocket]]`。

**挂载点**：main.py:58 `app.include_router(websocket_router)`（无 prefix，路径 `/ws`）。

**通知**：`backend/app/websocket/notifications.py:13-32` `notify_user(user_id, event, title, message, resource)` 广播 `{"type":"notification","payload":{event,title,message,resource,timestamp}}`。被 `services/extraction/runner.py`、`routers/reviews.py`、`routers/reports.py`、`routers/exports.py` 调用。

**B1 影响**：cookie 化后 WS 鉴权可从 `websocket.cookies.get("access_token")` 读，但建议保留 query param 兼容（浏览器 WS API 不能设 Authorization header，cookie 在同源下自动带但跨域 WS 不一定）。task.json 未明确要求 WS 改 cookie，**建议不改**。

### 5. 静态文件挂载 / SPA fallback 现状

**完全没有**。grep `StaticFiles|mount|FileResponse` in `backend/app/` 结果：
- `routers/reports.py:86` `FileResponse(path, filename=path.name, media_type="text/markdown; charset=utf-8")` — 下载报告文件
- `routers/exports.py:88` `FileResponse(path, ...)` — 下载导出文件
- 无 `from fastapi.staticfiles import StaticFiles`
- 无 `app.mount(...)`

**前端 build 产物现状**：`web/build/client/` 下有 `assets/`（JS/CSS 带哈希）+ `favicon.ico`，**没有 index.html**（React Router 7 SSR 模式 build 产物在 `web/build/server/index.js` + `web/build/client/`，index.html 由 server 渲染）。`web/react-router.config.ts:6` `ssr: true` — **当前是 SSR 不是 SPA**。

**B1 第 5 块"SPA fallback + 静态挂载"的矛盾**：
- task.json 写 "FastAPI 挂 frontend/dist 静态+SPA fallback"，但当前前端是 SSR 模式，build 出来的是 `server/index.js`（Node server）+ `client/assets/`，**不是纯静态 SPA**。
- 要做纯静态挂载，前端要改成 SPA 模式：`web/react-router.config.ts` 设 `ssr: false`，重新 `pnpm build`，产物变成 `build/client/index.html` + `assets/`，可由 FastAPI `StaticFiles` 直接服务。
- 或者保留 SSR，但 FastAPI 不跑 Node，无法直接服务 SSR（要起 Node 进程或用 `@react-router/serve`）。这超出 B1 后端基建范围。

**建议方案**：
1. 把 `web/react-router.config.ts` 改 `ssr: false`（前端改动，需协调）。
2. `pnpm build` 产 `web/build/client/index.html` + `web/build/client/assets/*`。
3. `backend/app/main.py` 加：
   ```python
   from fastapi.staticfiles import StaticFiles
   from fastapi.responses import FileResponse
   # 路由注册之后、最后挂载
   app.mount("/assets", StaticFiles(directory="web/build/client/assets"), name="assets")
   @app.get("/{full_path:path}")
   async def spa_fallback(full_path: str):
       return FileResponse("web/build/client/index.html")
   ```
4. `/{full_path:path}` 通配要放在所有 API 路由之后注册（FastAPI 按顺序匹配），且要排除 `/api/*` 和 `/ws`（用更具体的 path 或检查 `full_path.startswith("api/")` 返回 404）。

**CORS 与同源**：静态挂载后前后端同源（都走 8000 端口），`CORS_ORIGINS` 可改空或移除，`SameSite=Strict` cookie 才能工作（呼应 auth-current.md 的结论）。

**`web/build/client/assets/` 已有内容**（Bash ls 结果）：`entry.client-*.js`（183KB）、`analytics-*.js`（344KB）、`dist-*.js`（32KB）、`customers/dashboard/dialog/...` 等路由 chunk。但没有 index.html，**说明当前 build 是 SSR，不能直接挂**。

## 6. pyproject.toml 与启动方式

`backend/pyproject.toml`（无 `[project.scripts]`，无 `[tool.uv]`）：

- Python `>=3.13`
- 依赖 33 行（见 backend-config-db.md），**无 `alembic`/`asyncpg`/`psycopg`/`pydantic-ai`**。
- 测试：`pytest>=9.1.0` + `pytest-asyncio>=1.4.0` 已在依赖里。
- 无 `uvicorn[standard]` 之外的 ASGI server。

**启动**：`uvicorn app.main:app --reload`（README 或惯例，未在 pyproject 里固化为 script）。B1 不改启动方式。

## Caveats / Not Found

- 无 `.env` / `.env.example`（glob 无匹配），settings 全靠代码默认 + DB Setting 表。B1 要加 `.env.example` 至少含 `DATABASE_URL=postgresql+asyncpg://check_yg:check_yg@localhost:5432/check_yg`。
- 无 `docker-compose.yml`（glob 无匹配）。B1 要新增，起 pg +（可选）后端。
- `web/Dockerfile` 存在但 `backend/Dockerfile` 不存在。B1 若要容器化后端要新增，但 task.json 只说 "docker-compose 起本地 pg"，后端可本地跑。
- 前端 SSR vs SPA 的决策不在 backend 研究范围，但**直接影响 B1 第 5 块能否落地**——需在实现阶段与前端协调把 `ssr: false`，否则静态挂载拿不到 index.html。这是 B1 最大的跨层风险点。
