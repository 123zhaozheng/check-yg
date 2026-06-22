# Directory Structure

> How backend code is organized in this project.

---

## Overview

员工-客户金额往来审计系统（智行卫士）的 **FastAPI 后端**，位于 `backend/`。
提供 REST API + WebSocket + 多渠道流水文件的解析/清洗/标准化/AI 分析/报告能力，
由 SPA 前端（`frontend/`，Vite+React+TanStack）消费。生产同源部署：FastAPI
挂 `frontend/dist` 静态 + SPA fallback。

入口：`backend/app/main.py`（FastAPI 应用装配 + lifespan init_db + 路由注册 +
静态挂载）。运行：`uvicorn app.main:app`（从 `backend/` 启动）。

技术栈：FastAPI + SQLAlchemy 2.x async + PostgreSQL（asyncpg 运行时 /
psycopg 供 Alembic 同步迁移）+ Alembic + pydantic-ai（LLM）+ JWT cookie 鉴权。

---

## Directory Layout

```
check-yg/
├── backend/                      # FastAPI 后端
│   ├── pyproject.toml            # 依赖（uv 管理）
│   ├── alembic.ini               # Alembic 配置（连接串由 env.py 从 settings 注入）
│   ├── migrations/               # Alembic 迁移
│   │   ├── env.py                # 同步 psycopg 驱动，target_metadata=Base.metadata
│   │   ├── script.py.mako
│   │   └── versions/             # baseline + 后续迁移
│   └── app/
│       ├── main.py               # FastAPI 应用：lifespan init_db、路由注册、
│       │                         # CORS、frontend/dist 静态挂载 + SPA fallback
│       ├── config.py             # pydantic-settings Settings（DATABASE_URL、
│       │                         # JWT_*、LLM_*、MINERU_*、FRONTEND_DIST 等）
│       ├── database.py           # async engine + session + init_db
│       │                         # （pg 走 Alembic upgrade head，sqlite 测试走 create_all）
│       ├── auth/                 # 鉴权：jwt、password、dependencies、permissions
│       ├── llm/                  # LLM 集成（pydantic-ai）
│       │   ├── agent_factory.py  # 模块级单例工厂（OpenAIChatModel+OpenAIProvider）
│       │   ├── types.py          # pydantic output_type：FlowClassification/
│       │   │                     # NormalizedRow+NormalizedRows/DocumentPortrait
│       │   ├── classifier.py     # 流水表格识别（output_type=FlowClassification）
│       │   ├── normalizer.py     # 行标准化（output_type=NormalizedRows + output_validator）
│       │   └── portrait.py       # 文档画像（output_type=DocumentPortrait）
│       ├── parsers/              # 文档解析：base（FlowRecord/RawTable）、pdf（MinerU）、
│       │                         # excel、docx、html
│       ├── models/               # SQLAlchemy 模型（13 表）+ _types.py（jsonb() 辅助：
│       │                         # JSONB().with_variant(JSON(),"sqlite") 双方言）
│       ├── routers/              # FastAPI 路由：auth、users、tasks、customers、
│       │                         # settings、reviews、reports、exports
│       ├── schemas/              # pydantic 请求/响应 schema
│       ├── services/             # 业务服务（extraction 流水线、review、export 等）
│       │   └── extraction/
│       │       └── extractor.py  # FlowExtractor：parse→classify→normalize 三阶段
│       ├── websocket/            # WebSocket 通知（任务进度推送）
│       └── core/                 # 共享工具（如 matcher）
├── frontend/                     # SPA 前端（Vite+React18+TanStack Router/Query+
│                                 # Tailwind4+lightningcss(chrome108)+shadcn 风格）
├── archive/web-legacy/           # 旧 web/ 归档（react-router 7 SSR，已弃用）
├── stitch_/                      # 设计稿源文件（单色设计系统 + 7 页 code.html）
├── docs/                         # 交付规划 + pydantic-ai 规范落地参考
├── docker-compose.yml            # 本地 PostgreSQL（postgres:16）
└── .trellis/                     # Trellis 任务管理
```

---

## Module Organization

### Where new features go

| Feature type | Directory | Example |
|---|---|---|
| FastAPI 路由 | `backend/app/routers/` | `tasks.py`, `auth.py` |
| 业务服务 | `backend/app/services/` | `extraction/extractor.py` |
| 文档解析 | `backend/app/parsers/` | `excel_parser.py` |
| LLM/AI（pydantic-ai） | `backend/app/llm/` | `normalizer.py` |
| SQLAlchemy 模型 | `backend/app/models/` | `task.py`, `review.py` |
| pydantic schema | `backend/app/schemas/` | `auth.py` |
| 鉴权 | `backend/app/auth/` | `dependencies.py`, `jwt.py` |
| DB 迁移 | `backend/migrations/versions/` | `20260622_..._baseline.py` |
| 测试 | `backend/tests/` | `test_llm_parity.py` |

### Rules

- **路由层薄**：`routers/` 只做请求解析 + 调 service + 返 schema，业务逻辑进 `services/`。
- **新模型**：在 `backend/app/models/` 加文件，`__init__.py` 导出，并在 `migrations/env.py` 的 import 列表里登记（确保 Alembic autogenerate 能发现）。
- **JSON 列**：用 `app/models/_types.py` 的 `jsonb()`（pg=JSONB / sqlite=JSON），不要直接用 `JSON` 或 `JSONB`。
- **LLM 模块**：通过 `agent_factory.get_agent()` 取模块级单例，复用 `settings.LLM_*`；提示词逐字搬进 `instructions`（硬底线：提示词保真），`output_type` 用 `app/llm/types.py` 的 pydantic 模型。
- **鉴权**：token 优先从 httpOnly cookie 读（`get_current_user`），`Authorization: Bearer` header 仅过渡兼容。

---

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python files | `snake_case.py` | `flow_extractor.py` |
| Classes | `PascalCase` | `FlowExtractor`, `ReviewMatch` |
| Dataclasses / pydantic models | `PascalCase`, noun phrase | `FlowRecord`, `NormalizedRow` |
| Config keys (env) | `UPPER_SNAKE` | `LLM_API_ENDPOINT`, `DATABASE_URL` |
| Runtime settings keys (DB) | `lower.dot` | `llm.base_url`, `mineru.mode` |
| Test files | `test_<module>.py` | `test_llm_parity.py` |
| Alembic revisions | `<date>_<rev>_<slug>.py` | `20260622_2db1..._baseline_initial_schema.py` |
| Chinese strings | Use Chinese directly in string literals | `"密码错误"`, `"精确匹配"` |

---

## Examples

- 模块级 LLM 单例：`backend/app/llm/agent_factory.py` — `get_agent(output_type, instructions, *, base_url, api_key, model, timeout, max_tokens)` 按 params 缓存，`OpenAIProvider(openai_client=AsyncOpenAI(max_retries=3, http_client=httpx.AsyncClient(trust_env=False)))`，`base_url` 强制 `/v1` 结尾。
- 双方言 JSON 列：`backend/app/models/_types.py` — `jsonb()` 返回 `JSONB().with_variant(JSON(), "sqlite")`，pg 用 JSONB / sqlite 测试用 JSON。
- cookie 鉴权：`backend/app/auth/dependencies.py` — `_extract_access_token` 先读 `request.cookies["access_token"]`，回退 `Authorization: Bearer`。

---

## Scenario: FastAPI Task Extraction Boundary

### 1. Scope / Trigger

- Trigger: the web split exposes extraction through FastAPI and React, so task/extraction behavior crosses UI, API, service, checkpoint storage, database status, and websocket notification layers.
- Use this contract when changing `backend/app/routers/tasks.py`, `backend/app/services/extraction/`, or frontend task controls.

### 2. Signatures

- `POST /api/tasks/` creates a draft extraction task.
- `GET /api/tasks/` lists paginated tasks with `page`, `page_size`, `status_filter`, and `search`.
- `GET /api/tasks/{task_id}` returns one task.
- `POST /api/tasks/{task_id}/start` starts extraction in a background job.
- `POST /api/tasks/{task_id}/append` starts append extraction for a second folder.
- `POST /api/tasks/{task_id}/pause` pauses the in-process extractor.
- `POST /api/tasks/{task_id}/resume` resumes the in-process extractor.
- `POST /api/tasks/{task_id}/cancel` requests cancellation and marks the task cancelled.

### 3. Contracts

- Create request: `title: string` required and non-empty; `description?: string`; `document_folder?: string`; `batch_size?: int`; `confidence_threshold?: int`.
- Start/append request: `document_folder?: string`; `batch_size?: int`; `confidence_threshold?: int`.
- Task response includes `id`, `title`, `description`, `status`, `owner_id`, `config`, `created_at`, `updated_at`, and `completed_at`.
- `config.document_folder` is a backend-local filesystem path. The frontend must not treat it as a browser upload path.
- Background completion writes the final extraction result into `Task.config.last_result`.
- Append completion merges new records/statistics into the existing `Task.config.last_result`; it must not overwrite prior `flow_records`.
- Websocket progress events use notification payloads with `event="task.progress"` and a `resource` object containing `task_id`, `stage`, `current`, `total`, and `percentage`.

### 4. Validation & Error Matrix

- Empty title -> HTTP 422.
- Missing `document_folder` on start/append when no saved folder exists -> HTTP 422.
- Nonexistent or non-directory `document_folder` -> HTTP 422.
- Starting/append while `Task.status == "running"` or runner has a live job -> HTTP 409.
- Pause/resume/cancel without an in-process extractor -> HTTP 409 when the action cannot be honored.
- Task owned by another user -> HTTP 403.
- Unknown task id -> HTTP 404.

### 5. Good/Base/Bad Cases

- Good: create with a valid folder, start, stream websocket progress, finish with `completed` and `config.last_result.total_records`.
- Base: create without a folder; task remains `draft`, and frontend disables start until a folder is supplied.
- Bad: append with a missing folder; API returns 422 and must not create a background job.

### 6. Tests Required

- API test asserts task creation persists `draft` status and config.
- API test asserts start rejects nonexistent folders.
- API test monkeypatches the runner and asserts start marks `running` and passes `task_id`, folder, batch size, and confidence threshold.
- API test asserts pause/resume/cancel delegate to runner and update visible task status.
- Unit test asserts append result merging preserves previous records and combines totals/errors/statistics.

### 7. Wrong vs Correct

#### Wrong

```python
# Starts a long extraction inside the request handler and returns only after LLM calls finish.
result = await FlowExtractor().extract_flows(folder)
task.status = "completed"
```

#### Correct

```python
# Commit the task as running, dispatch a background runner, and let the runner write completion state.
task.status = "running"
await runner.start(task_id=task.id, owner_id=current_user.id, document_folder=folder)
```

---

## Scenario: FastAPI Auth Cookie Boundary

### 1. Scope / Trigger

- Trigger: SPA 路由守卫与 API 重试依赖后端 access/refresh token 语义。
- Use this contract when changing `backend/app/auth/`, `backend/app/routers/auth.py`,
  `backend/app/schemas/auth.py`, or `frontend/src/lib/api.ts`.

### 2. Signatures

- `POST /api/auth/login` accepts `username` and `password`; sets `access_token` + `refresh_token` httpOnly cookies.
- `POST /api/auth/refresh` reads `refresh_token` from cookie first, falls back to body; rotates both cookies.
- `POST /api/auth/logout` clears both cookies.
- `GET /api/auth/me` requires a valid access token (cookie or `Authorization: Bearer` header).

### 3. Contracts

- Cookies: `HttpOnly`, `SameSite=Strict`, `Path=/`（同源前提由 FastAPI 挂 `frontend/dist` 保证）。
- Login/refresh response 仍含 `access_token`/`refresh_token`/`token_type="bearer"`（过渡期前端可读 JSON，但权威来源是 cookie）。
- Access tokens carry `type="access"` and are accepted by `get_current_user` (cookie 优先，header 兼容).
- Refresh tokens carry `type="refresh"` and are accepted only by `/api/auth/refresh`.
- `get_current_user` 优先读 `request.cookies["access_token"]`，回退 `Authorization: Bearer`（API 测试与过渡兼容）。
- 前端 `apiFetch` 发 `credentials: "include"`；401 跳 `/login?redirect=...`（login/refresh 端点自身不重试）。

### 4. Validation & Error Matrix

- Bad username/password -> HTTP 401.
- Disabled user login -> HTTP 403.
- Refresh endpoint receives access token -> HTTP 401.
- Normal API dependency receives refresh token -> HTTP 401.
- Expired access token -> HTTP 401; frontend 跳 /login（cookie 模式下不再做客户端 refresh 重试，由用户重新登录；如需静默续期可在前端调 /refresh）。
- Missing refresh token (cookie + body 都无) on /refresh -> HTTP 401.

### 5. Good/Base/Bad Cases

- Good: login Set-Cookie，`/auth/me` 读 cookie 成功，refresh 读 cookie 轮转，logout 清 cookie，后续 /me 401。
- Base: 无 cookie；路由守卫跳 /login。
- Bad: 前端 fetch 不带 `credentials: "include"`；浏览器不发 cookie，/me 永远 401。

### 6. Tests Required

- API test asserts login returns both token types AND sets both httpOnly+SameSite=Strict cookies.
- API test asserts refresh rotates tokens (body + cookie 两种路径).
- API test asserts refresh rejects access tokens.
- API test asserts `/auth/me` rejects refresh tokens.
- API test asserts expired access tokens are rejected.
- API test asserts /me reads access_token from cookie; /refresh reads refresh_token from cookie; /logout clears cookies; /me after logout 401.

---

## Scenario: MinerU PDF Parser and Settings Wiring

### 1. Scope / Trigger
- Trigger: web extraction must parse heterogeneous PDFs (scanned, multi-column, encrypted) with the same production semantics as the desktop `src` pipeline, driven by runtime settings rather than hardcoded values.
- Use this contract when changing `backend/app/parsers/pdf_parser.py`, `backend/app/services/settings_service.py`, `backend/app/services/extraction/extractor.py`, or `frontend/src/routes/__authenticated/settings.tsx`.

### 2. Signatures
- `PDFParser(mineru_mode, mineru_url, mineru_public_url, mineru_public_api_key, timeout)` — chooses `MinerUClient` (local) or `PublicMinerUClient` (public agent) from `mineru_mode`.
- `PDFParser.extract_raw_tables(path) -> List[RawTable]` and `PDFParser.extract_non_table_context(path, max_chars) -> str` parse MinerU markdown via `HTMLTableParser`.
- `PDFParser.extract_tables_and_context(path, max_chars) -> (List[RawTable], str)` fetches MinerU markdown **once** and returns both tables and non-table context — the extractor must use this for PDFs to avoid a second MinerU API call (costly on the public agent).
- `FlowExtractor(runtime_settings)` constructs `PDFParser` from runtime MinerU settings with config env defaults as fallback.
- `POST /api/tasks/upload` (multipart) and `POST /api/tasks/{task_id}/append-upload` (multipart) save uploaded files under `UPLOAD_DIR/tasks/{task_id}/run-{n}/` and start/append extraction — the web UI never asks the user for a backend-local directory path.
- `CheckpointManager.load/save/clear_checkpoint(task_id, document_name, document_path=...)` keys checkpoint files by `name|posix_path` md5 hash, so same-named files in different folders get distinct checkpoints.

### 3. Contracts
- MinerU runtime settings keys (all category `mineru`, in `DEFAULT_SETTINGS` and `config.py` env defaults): `mineru.mode` (`local`|`public`), `mineru.url`, `mineru.public_url`, `mineru.public_api_key`, `mineru.timeout`.
- The settings UI must only expose keys the runtime consumes — no `fast`/`precise` mode (no such runtime concept), no `max_concurrency`, no `mineru.api_endpoint` (wrong key; runtime reads `mineru.url`). No placeholder AI/Security tabs.
- Document identity is the full path (posix-normalized), not the filename: checkpoints, append dedup, and `processed_document_paths` all use `name|path`. `source_file` stays as the filename for display only.
- Each create/append upload gets its own `run-{n}/` subfolder so same-named files across runs stay distinct documents (path-aware identity).
- Encrypted PDFs: auto-extract password from the last parenthesized filename segment; fall back to an optional password callback; surface a clear error when no callback is set.
- The normalizer prompt guarantees `amount` is always positive and `raw_amount` preserves the source sign; the extractor post-processes `transaction_type` from `raw_amount` + `amount_sign_rule` (credit cards defer to the LLM).

### 4. Validation & Error Matrix
| Condition | Behavior |
|----------|----------|
| `mineru.mode=public` but no `public_api_key` | Public client sends no Authorization header; MinerU API rejects |
| MinerU service unreachable | `extract_raw_tables` returns `[]`, `extract_non_table_context` returns `""` (log + continue) |
| Encrypted PDF with no filename password and no callback | `extract_raw_tables` returns `[]`; error logged |
| Upload with no supported files | `POST /tasks/upload` and `/append-upload` return 422 before creating/changing any task |
| `flow.batch_size` / `flow.confidence_threshold` in settings | NOT consumed — start/append reads request > task.config > hardcoded 20/70; do not add these to `DEFAULT_SETTINGS` |

### 5. Tests Required
- Client selection (local vs public), markdown→table, non-table context stripping, encrypted-PDF fallback, single-Mineru-fetch (`extract_tables_and_context` calls `_get_markdown` once), and runtime-settings wiring into `PDFParser` (see `tests/test_pdf_parser.py`, `tests/test_review_fixes.py`).
- Upload endpoints create+start and append, distinct run dirs, 422 on unsupported files.
- Path-aware checkpoint identity (same name + different path → distinct checkpoints) and append skips already-processed paths.
- `DEFAULT_SETTINGS` contains the mineru.* keys and excludes decorative `flow.*` keys.

### 6. Wrong vs Correct
#### Wrong
```python
# Hardcoded MinerU URL; ignores runtime settings.
self.pdf_parser = PDFParser()
```
#### Correct
```python
# Wire DB/runtime MinerU settings into the parser with env defaults as fallback.
self.pdf_parser = PDFParser(
    mineru_mode=runtime_settings.get("mineru.mode") or settings.MINERU_MODE,
    mineru_url=runtime_settings.get("mineru.url") or settings.MINERU_URL,
    timeout=mineru_timeout,
)
```
