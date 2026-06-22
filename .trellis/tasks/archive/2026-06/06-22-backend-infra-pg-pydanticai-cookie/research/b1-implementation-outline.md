# Research: b1-implementation-outline (B1 实施大纲)

- **Query**: 基于现状，列 B1 五块工作要改的文件清单和顺序建议
- **Scope**: internal (基于前 4 份 research 综合)
- **Date**: 2026-06-22

## Findings

### 总原则

1. **静态挂载要先于 cookie 化**（cookie 的 `SameSite=Strict` 要求同源，否则浏览器不发 cookie）。
2. **pg 迁移要先于 Alembic**（Alembic baseline 要从 pg schema 生成）。
3. **pydantic-ai 三模块替换要逐字搬提示词**，回归 diff 以 `tests/test_llm_parity.py` 的断言为验收线。
4. **config 层不动**：`llm.base_url/model_name/api_key/timeout` 四项键名保持，只换调用层。
5. **spec 滞后**：`.trellis/spec/backend/database-guidelines.md` 和 `directory-structure.md` 仍写 "no database / PyQt5 desktop"，B1 落地后单独触发 `update-spec`，**本次不改 spec**。

### 推荐顺序（5 块工作）

```
[块1] pg 迁移 + Alembic  →  [块5] 静态挂载  →  [块2] cookie 鉴权  →  [块3] pydantic-ai 替换  →  [块4] 回归 diff
```

理由：
- 块1 是地基（DB 方言变），其他块都在 pg 上跑。
- 块5 先于块2：cookie 同源前提。
- 块3 独立于 1/2/5，可并行，但放后面避免与 cookie 改动冲突在 `dependencies.py`/`main.py`。
- 块4 是块3 的验收，必须最后。

---

### 块1 — SQLite → PostgreSQL + Alembic

**要改的文件**：

| 文件 | 改动 |
|---|---|
| `backend/pyproject.toml` | 加 `alembic>=1.13`、`asyncpg>=0.29`（或 `psycopg[binary]>=3.2`）；`aiosqlite` 保留（测试用） |
| `backend/app/config.py:12` | `DATABASE_URL` 默认改 `postgresql+asyncpg://check_yg:check_yg@localhost:5432/check_yg` |
| `backend/app/database.py:9` | `create_async_engine` 加 `pool_pre_ping=True`（pg 长连接推荐） |
| `backend/app/database.py:25-76` `init_db()` | 生产路径改 `alembic upgrade head`；保留 `create_all` 仅 `if DATABASE_URL.contains("sqlite")`（测试内存库） |
| `backend/app/database.py:79-99` `_run_lightweight_migrations` | 已有 `if not startswith("sqlite"): return`，pg 下自动跳过；Alembic 接管等价列 |
| `backend/app/models/*.py`（6 处 JSON） | `JSON` → `JSONB`：`role.py:16`(permissions), `task.py:25`(config), `document.py:25`(extracted_tables), `document.py:26`(flow_tables), `review.py:19`(match_config), `review.py:51`(record_payload)。从 `sqlalchemy.dialects.postgresql` import `JSONB`。**注意**：pg 下 `JSONB` 不支持 SQLite，测试用 SQLite 要用 `from sqlalchemy import JSON` + 方言判断，或测试也改 pg。**推荐**：用 `JSONB().with_variant(JSON(), "sqlite")` 一处搞定两边。 |
| `backend/tests/conftest.py:22-28` | 测试 engine 若仍用 sqlite 内存库，模型用 `with_variant` 即可兼容；若改 pg testcontainers，engine 换 `asyncpg` |
| **新增** `backend/alembic.ini` | 标准 alembic 配置，`sqlalchemy.url` 留空（env.py 从 settings 读） |
| **新增** `backend/migrations/env.py` | `async_engine_from_config` + `run_sync` + `target_metadata = Base.metadata` |
| **新增** `backend/migrations/script.py.mako` | alembic 模板 |
| **新增** `backend/migrations/versions/0001_baseline.py` | `alembic revision --autogenerate` 生成 13 张表 baseline |
| **新增** `docker-compose.yml`（repo 根） | `postgres:16` service + volume + env |
| **新增** `backend/.env.example` | `DATABASE_URL=postgresql+asyncpg://...` + `JWT_SECRET=...` + `LLM_*` |

**顺序**：装依赖 → 起 docker-compose pg → 改 config.py + database.py → 改 6 处 JSONB → `alembic init` → `alembic revision --autogenerate` → `alembic upgrade head` → 验 `init_db()` seed roles/admin → 跑现有测试。

**风险**：`JSONB().with_variant(JSON(), "sqlite")` 在 SQLAlchemy 2.x `mapped_column` 里写法是 `mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)`，要验证 SQLite 测试仍跑得通。若 with_variant 有坑，退路是测试也改 pg（testcontainers-python）。

---

### 块5 — FastAPI 挂 frontend/dist + SPA fallback

**要改的文件**：

| 文件 | 改动 |
|---|---|
| `web/react-router.config.ts:6` | `ssr: false`（前端协调，改为 SPA 模式） |
| `web/`（重新 build） | `pnpm build` 产 `web/build/client/index.html` + `assets/` |
| `backend/app/main.py:34-58` | 根路径 `/` 让位 SPA；在所有 `include_router` 之后加 `app.mount("/assets", StaticFiles(directory="web/build/client/assets"), name="assets")` + `@app.get("/{full_path:path}")` 返回 `index.html`（排除 `/api/` `/ws`） |
| `backend/app/config.py` | 可选加 `FRONTEND_DIST: str = "web/build/client"` 配置项 |
| `backend/app/main.py:24-31` CORS | 同源后可移除 CORS 或改 `allow_origins=[]` |

**顺序**：前端 `ssr:false` + rebuild → 后端 main.py 加 mount + fallback → 验 `GET /` 返 index.html、`GET /assets/*.js` 返 JS、`GET /api/auth/login` 仍返 JSON、`GET /ws` 仍握手。

**风险（最大）**：前端 SSR→SPA 是前端改动，若 web 侧不能同步，B1 第 5 块只能做到"挂 assets，index.html 手写一个空壳"——不完整。**需在实现前确认 web 侧能否改 `ssr: false`**。若不能，块5 降级为"仅挂 assets + 占位 index.html"，SPA fallback 等 web 侧配合。

---

### 块2 — cookie 鉴权

**要改的文件**：

| 文件 | 改动 |
|---|---|
| `backend/app/auth/dependencies.py:13-59` | `HTTPBearer` → 读 `Request.cookies.get("access_token")`；无 cookie → 401。**建议过渡期同时支持 header+cookie**（先 cookie 后 header）让前端渐进迁移。 |
| `backend/app/routers/auth.py:21-54` `/login` | 函数签名加 `response: Response`；返回 JSON 同时 `response.set_cookie("access_token", access_token, httponly=True, samesite="strict", path="/")` + 同样设 `refresh_token`（path 可缩到 `/api/auth/refresh` 或 `/`）。 |
| `backend/app/routers/auth.py:75-107` `/refresh` | 从 cookie 读 refresh（`request.cookies.get("refresh_token")`），过渡期 body+cookie 双支持；返回新 token 时重新 set_cookie。 |
| `backend/app/routers/auth.py` 新增 `/logout` | `@router.post("/logout")` → `response.delete_cookie("access_token")` + `response.delete_cookie("refresh_token")`。**当前无此端点，必须新增**。 |
| `backend/app/routers/auth.py:57-72` `/me` | 不动（靠 `get_current_user` 自动切 cookie）。 |
| `backend/app/schemas/auth.py` | `TokenResponse` 保留（过渡期前端仍读 JSON）；`RefreshRequest` 可标 `refresh_token: Optional[str]` 兼容 cookie 模式。 |
| `backend/app/websocket/router.py:38-61` | **建议不动**（保留 query param token）。若要改 cookie，加 `websocket.cookies.get("access_token")` 作首选，query param 兜底。 |
| `backend/tests/test_auth_api.py:77-99` | `headers={"Authorization": "Bearer ..."}` 改 `cookies={"access_token": ...}`；或过渡期 header 仍支持则不改。 |
| `backend/tests/conftest.py:54-61` | `dependency_overrides[get_current_user]` 机制不变，无需改。 |

**顺序**：块5 完成同源后 → 改 dependencies.py → 改 auth.py 三端点 + 加 /logout → 改测试 → 验 login Set-Cookie + me 读 cookie + logout 清 cookie 闭环。

**风险**：`SameSite=Strict` 在跨域时不发 cookie——**块5 必须先落地同源**，否则块2 无效。过渡期 header+cookie 双支持可降低此风险。

---

### 块3 — pydantic-ai 替换三模块

**要改的文件**：

| 文件 | 改动 |
|---|---|
| `backend/pyproject.toml` | 加 `pydantic-ai-slim[openai]>=1.107.0` |
| **新增** `backend/app/llm/agent_factory.py` | 模块级单例工厂：`OpenAIChatModel(model_name, provider=OpenAIProvider(base_url=..., api_key=..., http_client=httpx.AsyncClient(trust_env=False)), settings=ModelSettings(timeout=..., max_tokens=...))`。复用 `settings.LLM_*` + runtime settings。**按 conventions.md 第 34-43 行**。 |
| **新增** `backend/app/llm/types.py` | 三个 pydantic output_type：`FlowClassification(BaseModel)`（is_flow_table/confidence/reason/header_row_index/data_start_row）、`NormalizedRow(BaseModel)`（row_index/is_valid/transaction_time/counterparty_name/counterparty_account/amount/raw_amount/summary/transaction_type/source_file）、`DocumentPortrait(BaseModel)`（9 字段 + account_type/amount_sign_rule 用 `Literal`）。**不复用 `FlowRecord` dataclass**（缺 raw_amount/is_valid/row_index）。 |
| `backend/app/llm/portrait.py` | 整文件重写：`DocumentPortraitExtractor` 内部改用 `Agent(model, output_type=DocumentPortrait, instructions=SYSTEM_PROMPT_DOCUMENT_PORTRAIT逐字)`，`extract()` 调 `await agent.run(user_message)`，返回 `result.output.model_dump()`。**提示词逐字搬进 instructions**（见 llm-modules-current.md 第 3 节全文）。保留 `is_available()` 和 `api_key` 检查。 |
| `backend/app/llm/classifier.py` | 同上，`output_type=FlowClassification`，提示词逐字搬（见 llm-modules-current.md 第 1 节）。`FALLBACK_RESULT` 保留（agent.run 失败时返回 `FlowClassification` 兜底）。 |
| `backend/app/llm/normalizer.py` | 同上，`output_type=list[NormalizedRow]`，提示词逐字搬（见 llm-modules-current.md 第 2 节）。**保留 `_infer_document_context` 兜底**。加 `@agent.output_validator` 验字段完整性（conventions.md 第 82-91 行）。 |
| `backend/app/services/extraction/extractor.py:94-111` | `FlowExtractor.__init__` 三处构造改调 `agent_factory` 获取 agent 单例（或工厂按 runtime settings 构造）。**注意**：agent 是模块级单例，但 runtime settings 可能被管理员改 DB 覆盖——单例要在 settings 变更时重建，或每次 `FlowExtractor.__init__` 时按当前 runtime settings 新建 agent（conventions.md 第 68 行说 agent 无状态线程安全可复用，但 base_url/api_key 变了要重建）。 |
| `backend/app/llm/__init__.py:4-6` | 导出不变（类名不变），内部实现换。 |

**顺序**：装依赖 → 建 agent_factory + types → 替换 portrait（最简单，单输出）→ 替换 classifier → 替换 normalizer（最复杂，list 输出 + validator）→ extractor.py 接线 → 跑 test_llm_parity.py（此时会全红，因为 mock 方式变了）→ 进块4 重写测试。

**风险**：
- `trust_env=False` 在 `OpenAIProvider` 里要显式传 `http_client=httpx.AsyncClient(trust_env=False)`，否则 ollama/内网环境可能走代理。
- `max_tokens` 三模块不同（1500/1500/4000），agent_factory 要支持 per-agent 配置或三个工厂函数。
- `temperature=0.1` 保留（conventions.md 示例 0.0，改 0.0 会让回归 diff 不过）。
- agent 单例 vs runtime settings 动态覆盖的矛盾——建议 `agent_factory.get_agent(base_url, api_key, model, timeout, max_tokens)` 按 params 缓存，settings 变了重建。

---

### 块4 — 回归 diff

**要改的文件**：

| 文件 | 改动 |
|---|---|
| `backend/tests/test_llm_parity.py` | **整文件重写 mock 方式**：从 patch `httpx.AsyncClient` 改成 patch `openai.AsyncOpenAI` 或用 `respx`/`pytest-vcr`。**断言逐字保留**（portrait 9 字段、classifier 5 字段、normalizer 的 raw_amount/amount/transaction_type 三连）。 |
| **新增** `backend/tests/fixtures/llm/portrait_input.json` | 固定 portrait 输入（document_name + non_table_context + content_preview） |
| **新增** `backend/tests/fixtures/llm/normalizer_input.json` | 固定 normalizer 输入（rows + portrait + source_file） |
| **新增** `backend/tests/fixtures/llm/normalizer_expected.json` | 旧 httpx 实现的 golden output（换框架前录一次） |
| **新增** `backend/tests/test_llm_diff.py` | 跑新 pydantic-ai agent，逐字段 diff `normalizer_expected.json`，验"记录 1:1 + 字段无丢"（task.json 验收线） |

**顺序**：块3 完成前先用旧 httpx 实现跑固定输入录 golden → 块3 完成后跑新 agent diff → 验全字段一致。

**风险**：LLM 输出非确定性，即使 temperature=0.1 固定，换框架后 OpenAI SDK vs httpx 直连的请求体细微差异（如默认 headers、system message 位置）可能导致模型输出不同。**若 diff 不过**，排查：
1. system prompt 是否逐字一致（conventions.md 说 instructions 带 history 时会丢历史的 system，单轮无影响）。
2. `max_tokens`/`temperature` 是否一致。
3. `response_format=json_object` 是否等价于 pydantic-ai 的 Tool Output 模式（conventions.md 第 73 行说默认 Tool Output，不是 JSON mode）——**这是最大差异**，pydantic-ai 把 output_type 注册成工具调用，不是 `response_format=json_object`。可能需要 `output_type=NormalizedRow` + 显式 `model_settings=ModelSettings(...)` 或用 `output_type` 的 JSON schema 模式。

## 关键依赖与风险汇总

1. **块5 前端 SSR→SPA 是最大跨层风险**：web 侧不改 `ssr:false`，静态挂载拿不到 index.html。**实现前必须与前端协调**。
2. **JSONB + SQLite with_variant** 要验证 SQLAlchemy 2.x 写法，否则测试库要换 pg。
3. **pydantic-ai Tool Output vs 现有 `response_format=json_object`** 是块3 最大语义差异，可能让回归 diff 不过。备选：用 pydantic-ai 的 `output_type` + `ModelSettings` 强制 JSON 模式，或接受工具调用模式但调 prompt 让输出兼容。
4. **agent 单例 vs runtime settings 动态覆盖** 要设计缓存/重建策略。
5. **spec 滞后**：`database-guidelines.md`/`directory-structure.md` 仍写 "no database / PyQt5"，B1 落地后触发 `update-spec`，不在本次 research 范围。
