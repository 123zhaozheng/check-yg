# Research: auth-current (鉴权现状)

- **Query**: B1 — 鉴权现状，为 cookie 化改造做底
- **Scope**: internal
- **Date**: 2026-06-22

## Findings

### 1. `backend/app/auth/` 各文件职责

`backend/app/auth/__init__.py:1-17` 导出 5 个符号：`get_current_user` / `create_access_token` / `create_refresh_token` / `verify_token` / `hash_password` / `verify_password` / `check_admin_permission` / `check_task_permission`。

#### `jwt.py`（47 行）

- `create_access_token(user_id: int, expires_delta: Optional[timedelta]=None) -> str` (jwt.py:12-25)：payload `{sub: str(user_id), exp, type:"access"}`，`jwt.encode(..., settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)`。无 `expires_delta` 时用 `settings.JWT_EXPIRE_MINUTES`（1440 分钟）。
- `create_refresh_token(user_id: int) -> str` (jwt.py:28-37)：固定 7 天，`type:"refresh"`，**不接受 expires_delta 参数**。
- `verify_token(token: str) -> Optional[dict]` (jwt.py:40-46)：`jwt.decode(..., algorithms=[settings.JWT_ALGORITHM])`，`JWTError` 返回 `None`。**不区分 access/refresh 类型**，由调用方查 `payload["type"]`。
- 依赖 `python-jose`（`from jose import JWTError, jwt`，jwt.py:7），pyproject.toml:24 `python-jose[cryptography]>=3.5.0`。

#### `dependencies.py`（60 行）

- `security = HTTPBearer()` (dependencies.py:13) — 模块级 scheme，期望 `Authorization: Bearer <token>`。
- `get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db = Depends(get_db)) -> User` (dependencies.py:16-59)：
  1. `token = credentials.credentials` (line 21)
  2. `verify_token(token)` → `None` 则 401 `WWW-Authenticate: Bearer` (line 24-29)
  3. `payload.get("type") != "access"` → 401 "Invalid token type" (line 31-35) **← 拒 refresh token**
  4. `payload.get("sub")` 无 → 401 (line 37-42)
  5. `select(User).where(User.id == int(user_id))` → 无 → 401 (line 44-51)
  6. `not user.is_active` → 403 "User account is disabled" (line 53-57)
  7. 返回 `user`

**这是 cookie 化的核心改造点**：`HTTPBearer` 只读 Authorization header。B1 要改成读 cookie（`request.cookies.get("access_token")`），或同时支持 header+cookie（过渡期）。`get_current_user` 签名要从 `Depends(security)` 改成 `request: Request` + 手动取 cookie + `verify_token`，401 时仍带 `WWW-Authenticate: Bearer`（或改成不带，因为不再是 Bearer scheme）。

#### `password.py`（15 行）

- `hash_password(password: str) -> str` (password.py:7-9)：`bcrypt.hashpw(...).decode()`。
- `verify_password(plain, hashed) -> bool` (password.py:12-14)：`bcrypt.checkpw(...)`。
- 依赖 `bcrypt`（pyproject.toml:17 `passlib[bcrypt]>=1.7.4`，但代码直接用 `bcrypt` 不是 `passlib`，**passlib 是冗余依赖**）。B1 不动这里。

#### `permissions.py`（70 行）

- `check_task_permission(db, user, task_id, required_role=None) -> bool` (permissions.py:12-62)：owner → True；admin → True（调 `check_admin_permission`）；否则查 `Collaborator` 表，按 `role_hierarchy = {"read":0, "write":1, "admin":2}` 比较。**spec/database-guidelines.md 要求 admin bypass 必须在此函数内部**（已满足）。
- `check_admin_permission(db, user) -> bool` (permissions.py:65-69)：查 `Role.name == "admin"`。
- 这两个函数与 token 传输方式无关，**B1 不动**。

### 2. `backend/app/routers/auth.py` 端点（108 行）

`router = APIRouter(prefix="/auth", tags=["auth"])` (auth.py:18)。挂载在 `/api` 前缀下（main.py:50），实际路径 `/api/auth/*`。

| 端点 | 方法 | 行 | 请求 | 响应 | token 传输 |
|---|---|---|---|---|---|
| `/login` | POST | auth.py:21-54 | `LoginRequest{username, password}` JSON body | `TokenResponse{access_token, refresh_token, token_type="bearer"}` JSON | **返回 JSON，token 在 body** |
| `/me` | GET | auth.py:57-72 | 无 body，`Authorization: Bearer <access>` header | `UserResponse{id, username, email, role, is_active}` | **读 header**（经 `get_current_user`） |
| `/refresh` | POST | auth.py:75-107 | `RefreshRequest{refresh_token}` JSON body | `TokenResponse` JSON | **refresh 在 body** |

**`/login` 流程**（auth.py:22-54）：
1. `select(User).where(User.username == request.username)` → 无 → 401 "Incorrect username or password" + `WWW-Authenticate: Bearer` (line 25-35)
2. `verify_password(request.password, user.hashed_password)` 失败 → 同上
3. `not user.is_active` → 403 "User account is disabled" (line 37-41)
4. `access_token = create_access_token(user.id, expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES))` (line 44-47)
5. `refresh_token = create_refresh_token(user.id)` (line 48)
6. `return TokenResponse(access_token=..., refresh_token=..., token_type="bearer")` (line 50-54)

**`/refresh` 流程**（auth.py:76-107）：
1. `verify_token(request.refresh_token)` → `None` 或 `type != "refresh"` → 401 "Invalid refresh token" (line 78-84) **← 拒 access token**
2. `select(User).where(User.id == int(payload["sub"]))` → 无/disabled → 401 (line 86-95)
3. 重新签 access + refresh（**轮转**，line 97-101）
4. 返回新 `TokenResponse` (line 103-107)

**`/me` 流程**（auth.py:58-72）：
1. `Depends(get_current_user)` 拿 user（header Bearer access token）
2. `select(Role).where(Role.id == current_user.role_id)` 取 role name
3. 返回 `UserResponse(id, username, email, role=role.name or "unknown", is_active)`

**用到的 pydantic schema**（`backend/app/schemas/auth.py`）：
- `LoginRequest{username: str, password: str}` (auth.py:6-9)
- `TokenResponse{access_token: str, refresh_token: str, token_type: str = "bearer"}` (auth.py:13-18)
- `RefreshRequest{refresh_token: str}` (auth.py:21-23)
- `UserResponse{id, username, email, role, is_active}` + `Config.from_attributes = True` (auth.py:27-37)
- `TokenPayload{sub, type, exp}` (auth.py:40-45) — **未在 router 里用，可能旧代码遗留**

**B1 cookie 化落点**：
- `/login` 和 `/refresh`：除了返回 JSON，**还要 `response.set_cookie(...)`** 两个 cookie：`access_token`（HttpOnly, SameSite=Strict, Path=/）+ `refresh_token`（HttpOnly, SameSite=Strict, Path=/api/auth/refresh 或 Path=/）。task.json 要求 `HttpOnly, SameSite=Strict, Path=/`。需要改函数签名加 `response: Response` 参数（FastAPI 注入），或直接返回 `JSONResponse` 并设 cookie。
- `/refresh`：从 cookie 读 refresh（不再从 body），但**过渡期建议同时支持 body+cookie**以免前端没同步改就崩。
- `/me`：`get_current_user` 改成读 cookie 后，`/me` 自动跟随，router 代码不动。
- **新增 `/logout`**：task.json 要求 `/logout 清 cookie`。当前 router 无 logout 端点（auth.py 只有 3 个），B1 要加 `@router.post("/logout")` 返回 `response.delete_cookie("access_token")` + `response.delete_cookie("refresh_token")`。

### 3. 其他路由怎么取当前用户

**统一模式**：`current_user: User = Depends(get_current_user)`。`get_current_user` 是唯一入口，所有受保护路由都走它。

**调用分布**（grep `get_current_user` in `backend/app/routers/`）：
- `auth.py:59` — `/me`
- `users.py:51,116,149,184,248` — 5 个端点（create/list/update/delete/...）
- `tasks.py:153,181,216,280,332,349,402,452,470,487,...` — 10+ 个端点（list/create/start/pause/resume/cancel/upload/append-upload/...）
- `customers.py:62,99` — 2 个
- `reviews.py:28,60,80` — 3 个
- `reports.py:26,57,74` — 3 个
- `exports.py:26,49,71` — 3 个
- `settings.py:45,93,116,152` — 4 个

**全部通过 `Depends(get_current_user)`**，无任何路由自己解 token。**好处**：B1 只要改 `dependencies.py` 一个文件，所有路由自动从 header 切到 cookie。

**`backend/tests/conftest.py:54-61`**：测试用 `app.dependency_overrides[get_current_user] = override_get_current_user` 直接返回固定 user，绕过 token 解析。B1 改 cookie 后，测试 override 机制不变（dependency_overrides 与传参方式无关）。但 `test_auth_api.py:77-99` 的 `test_me_rejects_refresh_token` / `test_expired_access_token_is_rejected` 用 `headers={"Authorization": "Bearer ..."}` 直接打 `client.get("/api/auth/me", headers=...)` —— **这两个测试要改成 `cookies={"access_token": ...}`**，或 B1 决定 header+cookie 双支持（过渡期）。

**WebSocket 鉴权**（`backend/app/websocket/router.py:38-61`）：`_authenticate_websocket` 从 `websocket.query_params.get("token")` 读 token（不是 header，因为浏览器 WebSocket 不能设 Authorization header）。B1 cookie 化后，WebSocket 可以从 `websocket.cookies.get("access_token")` 读，**但要同时保留 query param 兼容**（部分客户端不支持 cookie）。task.json 没明确要求 WebSocket 改 cookie，建议保留 query param。

### 4. CORS 配置

**在 `backend/app/main.py:25-31`**：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # ["http://localhost:5173"]
    allow_credentials=True,               # ← 已开，cookie 跨域必需
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**`allow_credentials=True` 已经开**，但 `allow_origins=["http://localhost:5173"]` 是**精确列表**（不是 `["*"]`）。Starlette 的 `CORSMiddleware` 在 `allow_credentials=True` 时禁止 `allow_origins=["*"]`，必须显式列表——**现状已合规**。

**B1 cookie 化的关键点**：
- 前端 `web/app/lib/api.ts:5` `API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"`，**跨域**（5173 → 8000）。cookie 跨域要 `SameSite=Lax` 或 `None` + Secure，但 task.json 要求 `SameSite=Strict`。
- **矛盾**：`SameSite=Strict` + 跨域 → 浏览器不发 cookie。要么前端走同源（B1 第 5 块"静态挂载"就是为此——前端 build 后由后端 8000 端口同源服务），要么 cookie 用 `SameSite=Lax`（跨站 GET 仍带，但 POST 不带，不适合 login）。
- **结论**：B1 的"cookie 鉴权"和"静态挂载"是**绑定的**——必须先做静态挂载让前后端同源，`SameSite=Strict` 才能工作。顺序上静态挂载要先于或同时于 cookie 化。
- 若静态挂载后 `CORS_ORIGINS` 可改成 `["http://localhost:8000"]` 或干脆移除 CORS 中间件（同源不需要）。

### 5. 前端 token 存储现状（B1 要改的下游）

`web/app/lib/api.ts:18-39`：`getToken/setToken/getRefreshToken/setRefreshToken/clearToken` 全走 `localStorage`。`apiFetch` (api.ts:70-135) 每次请求加 `Authorization: Bearer ${token}` header，401 时调 `refreshAccessToken()` (api.ts:47-68) 用 body 传 refresh_token，刷新后重试。

`web/app/hooks/use-auth.ts:28-39` `login` 调 `/api/auth/login` 拿 token 存 localStorage，再调 `/api/auth/me`。`logout` (use-auth.ts:41-44) 只 `clearToken()` + 清 state，**不调后端**（因为后端没 /logout）。

**B1 cookie 化后前端要改**：
- `api.ts` 删掉 `Authorization` header 注入（浏览器自动带 cookie），删 `refreshAccessToken` 的 body 传 token（改 POST `/api/auth/refresh` 无 body，靠 cookie），删 `getToken/setToken/...` localStorage 逻辑（或保留作 fallback）。
- `use-auth.ts` `login` 不再存 token（后端 Set-Cookie 即可），`logout` 要调 `POST /api/auth/logout` 让后端清 cookie。
- `downloadFile`/`uploadForm` (api.ts:169-282) 也要删 Authorization header，加 `credentials: "include"`（fetch 默认同源带 cookie，跨域要显式）。
- **但这是 web 侧改动，B1 任务范围是 backend**。task.json 第 5 块"FastAPI 挂 frontend/dist 静态+SPA fallback"就是为了**同源**让 cookie 自动带，前端 api.ts 改动可以最小化（甚至 `API_BASE` 改成 `""` 同源即可）。spec `directory-structure.md` 的 "FastAPI Auth Token Refresh Boundary" 场景（line 188-250）描述了现有 header+refresh 契约，B1 落地后要 `update-spec` 更新成 cookie 契约。

## Caveats / Not Found

- `python-jose` 项目已半废弃（维护缓慢），B1 若想顺带换 `pyjwt` 可做，但 task.json 没要求，**建议不动**以缩小 diff。
- `passlib[bcrypt]` 在 pyproject.toml:17 但代码用 `bcrypt` 直接，passlib 是冗余。B1 不清理（不在任务范围）。
- `TokenPayload` schema (schemas/auth.py:40-45) 定义了但 router 没用，疑似遗留。B1 不动。
- `create_refresh_token` 不接受 `expires_delta`，固定 7 天。若 B1 要让 refresh cookie 寿命与 access 一致或更长，要改签名。task.json 没明确，建议保持 7 天。
- `JWT_EXPIRE_MINUTES=1440`（24h）对 access token 偏长，cookie 化后 HttpOnly cookie 无法被 JS 读，刷新逻辑要靠 refresh token 或 cookie 续期。task.json 没要求改寿命，保留。
