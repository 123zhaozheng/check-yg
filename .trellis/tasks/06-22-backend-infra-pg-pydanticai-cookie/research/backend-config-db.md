# Research: backend-config-db (配置与数据库现状)

- **Query**: B1 后端基建 — 配置/数据库现状勘察
- **Scope**: internal
- **Date**: 2026-06-22

## Findings

### 1. Settings / Config 定义

**唯一来源**：`backend/app/config.py:6-40` — `pydantic-settings.BaseSettings` 子类 `Settings`，模块底部 `settings = Settings()`（config.py:40）。env 文件 `.env`，编码 utf-8。

注意：项目 LLM 运行时实际走 `settings_service.DEFAULT_SETTINGS`（DB 中的 `llm.*` 键覆盖 env 默认），`config.py` 只是 env 级 fallback。

| 配置项 | 路径 | 默认值 | 备注 |
|---|---|---|---|
| `DATABASE_URL` | `config.py:12` | `"sqlite+aiosqlite:///./data/check_yg.db"` | 方言 aiosqlite，相对路径 |
| `JWT_SECRET` | `config.py:15` | `"change-me-in-production"` | |
| `JWT_ALGORITHM` | `config.py:16` | `"HS256"` | |
| `JWT_EXPIRE_MINUTES` | `config.py:17` | `1440` (24h) | access token 有效期 |
| `UPLOAD_DIR` | `config.py:20` | `"data/uploads"` | |
| `OUTPUT_DIR` | `config.py:21` | `"data/outputs"` | |
| `CORS_ORIGINS` | `config.py:24` | `["http://localhost:5173"]` | list[str]，dev 前端端口 |
| `LLM_API_ENDPOINT` | `config.py:27` | `"http://localhost:11434/v1"` | ollama 默认 |
| `LLM_API_KEY` | `config.py:28` | `"ollama"` | |
| `LLM_MODEL_NAME` | `config.py:29` | `"qwen2.5:7b"` | |
| `LLM_TIMEOUT` | `config.py:30` | `60` (秒) | |
| `MINERU_*` | `config.py:33-37` | mode/url/public_url/public_api_key/timeout | PDF 解析器，与 B1 无关 |

**runtime settings 层（DB 覆盖 env）**：`backend/app/services/settings_service.py:15-52` `DEFAULT_SETTINGS` 把 4 个 `llm.*` 键 + 5 个 `mineru.*` 键映射到 `settings.LLM_*` / `settings.MINERU_*` 作为初始值。`load_runtime_settings(db)` (settings_service.py:62-68) 读 `Setting` 表覆盖默认。`FlowExtractor.__init__` 用 `runtime_settings.get("llm.base_url") or settings.LLM_API_ENDPOINT` 形式回退（extractor.py:95-111）。**B1 改造只换调用层，这四项键名不变**。

### 2. DB session / engine / Base

**全部在** `backend/app/database.py`：

- `engine = create_async_engine(settings.DATABASE_URL, echo=False)` (database.py:9) — 模块级单例，无 poolclass/连接参数。
- `async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)` (database.py:11)
- `get_db()` async generator 依赖 (database.py:14-22) — `async with async_session() as session`，正常 commit，异常 rollback。
- `init_db()` (database.py:25-76) — `engine.begin()` 里 `Base.metadata.create_all`（**无 Alembic**），然后 seed 默认 roles (`admin/auditor/viewer`) 与默认 admin 用户 (`admin / admin123`)。
- `_run_lightweight_migrations(conn)` (database.py:79-99) — **仅 SQLite** 的 `ALTER TABLE review_matches ADD COLUMN ...` 手写增量迁移，给 `review_matches` 补 `counterparty_name/account/source_file/transaction_time/amount/summary/record_payload` 七列。pg 迁移后这段可由 Alembic 接管。
- `Base = DeclarativeBase` 定义在 `backend/app/models/base.py:9-12`；`TimestampMixin` (base.py:15-28) 提供 `created_at` / `updated_at`，`server_default=func.now()`，`updated_at` 带 `onupdate=func.now()`。

**测试用 engine**：`backend/tests/conftest.py:22-28` 用 `sqlite+aiosqlite:///:memory:` + `StaticPool` + `check_same_thread=False` 构造内存库；`conftest.py:54-61` 用 `app.dependency_overrides` 覆盖 `get_db` / `get_current_user`。pg 迁移后测试要换 `asyncpg` + 内存或 testcontainers。

### 3. SQLAlchemy 模型清单（`backend/app/models/*.py`）

`backend/app/models/__init__.py` 导出 12 个模型。JSON 字段（迁移 pg 后要改 JSONB）已用 **[JSON]** 标出。

| 模型 | 文件:行 | 核心字段 | JSON 字段 |
|---|---|---|---|
| `Base` / `TimestampMixin` | `base.py:9,15` | — | — |
| `User` | `user.py:11` | id, username(unique), email(unique), hashed_password, role_id FK, is_active, +timestamps | — |
| `Role` | `role.py:9` | id, name(unique), description | **permissions [JSON]** (role.py:16) |
| `Task` | `task.py:11` | id, title, description(Text), owner_id FK, status(`draft/running/paused/completed/failed/cancelled`), completed_at, +timestamps | **config [JSON]** (task.py:25) — 存 `last_result`/`document_folder` 等 |
| `TaskLog` | `task_log.py:11` | id, task_id FK, level(`info/warning/error`), message(Text), created_at | — |
| `Document` | `document.py:11` | id, task_id FK, filename, original_path, status(`pending/processing/completed/failed`), error_log(Text), created_at | **extracted_tables [JSON]** (document.py:25), **flow_tables [JSON]** (document.py:26) — runner 写 `{"records": [...]}` |
| `CustomerList` | `customer_list.py:11` | id, name, owner_id FK, row_count, created_at | — |
| `CustomerListItem` | `customer_list.py:32` | id, list_id FK, name, notes(Text) | — |
| `Review` | `review.py:11` | id, task_id FK, customer_list_id FK, status, created_at | **match_config [JSON]** (review.py:19) |
| `ReviewMatch` | `review.py:34` | id, review_id FK, record_id, customer_name, match_type(`exact/masked/fuzzy`), score(Float), counterparty_name/account, source_file, transaction_time, amount, summary(Text) | **record_payload [JSON]** (review.py:51) — 整条标准化记录 |
| `Report` | `report.py:11` | id, task_id FK, review_id FK(nullable), format, content_path, created_at | — |
| `ExportFile` | `export.py:11` | id, task_id FK, review_id FK(nullable), format, file_path, created_at | — |
| `Collaborator` | `collaborator.py:11` | id, task_id FK, user_id FK, role(`read/write/admin`), invited_by FK, created_at | — |
| `Setting` | `setting.py:11` | key(PK str), value(Text), category, updated_at, updated_by FK | — |

**JSON → JSONB 迁移清单（pg 方言）**：`Role.permissions`、`Task.config`、`Document.extracted_tables`、`Document.flow_tables`、`Review.match_config`、`ReviewMatch.record_payload`。共 6 处，全部 `Mapped[dict | None] = mapped_column(JSON, nullable=True)`。pg 下把 `JSON` 换成 `sqlalchemy.dialects.postgresql.JSONB`（或 `JSONB(astext_type=Text())` 便于查询）。SQLAlchemy 2.x `mapped_column(JSONB(...))` 写法与现有 `Mapped[dict | None]` 注解兼容。

### 4. Alembic 现状

**未安装 Alembic**：

- `backend/**/alembic*` glob → 无匹配。
- `backend/**/migrations/**` glob → 无匹配。
- `backend/pyproject.toml:7-33` 依赖里无 `alembic`、无 `asyncpg`、无 `psycopg`。只有 `aiosqlite>=0.22.1`。
- `backend/uv.lock` 同样只锁了 `aiosqlite`。
- 现有"迁移"是 `init_db()` 的 `create_all` + `_run_lightweight_migrations` 的 SQLite ALTER，**不是 Alembic**。

**B1 落点**：新增 `alembic.ini`（backend 根）+ `backend/migrations/`（env.py 用 `async_engine_from_config` + `run_sync`），baseline migration 用 `--autogenerate` 从现有 13 张表生成；`init_db()` 里 `create_all` 改成 `alembic upgrade head` 或保留 `create_all` 仅用于测试内存库。`pyproject.toml` 加 `alembic>=1.13`、`asyncpg>=0.29`（或 `psycopg[binary]>=3.2`）。

### 5. 现有 DB 文件位置

`backend/data/check_yg.db`（sqlite，已 gitignored? status 显示 M）。`backend/data/uploads/tasks/*/run-*/*.pdf`、`backend/data/outputs/exports/*`、`backend/data/checkpoints/*` 都是运行时产物。**B1 pg 迁移空库起步，这些文件不迁移**，只重建 schema + reseed roles/admin。

## Caveats / Not Found

- 没有任何 `.env` / `.env.example` 文件提交到仓库（glob 无匹配），settings 全靠代码默认值 + 运行时 `Setting` 表覆盖。B1 要新增 `docker-compose.yml`（pg）和 `.env.example`（DATABASE_URL=postgresql+asyncpg://...）。
- `init_db()` 的 `_run_lightweight_migrations` 里有 `if not settings.DATABASE_URL.startswith("sqlite"): return` (database.py:81-82) — pg 下这段自动跳过，不会冲突，但仍需 Alembic 提供等价列。
- `.trellis/spec/backend/database-guidelines.md` 和 `directory-structure.md` 仍把项目描述成 "PyQt5 desktop app, no database, YAML/JSON persistence"（spec 已严重滞后于 backend/ 现实）。B1 落地后应触发 `update-spec` 更新这两份 spec，但**本次 research 不改 spec**。
