# Directory Structure

> How backend code is organized in this project.

---

## Overview

This is a **PyQt5 desktop application** (员工-客户金额往来审计系统), not a web service.
The "backend" layer is a Python package under `src/` providing core logic, parsers, LLM clients,
and export utilities — all consumed by the UI layer (`src/ui/`).

Entry point: `main.py` at the repo root.

---

## Directory Layout

```
check-yg/
├── main.py                    # Application entry point (PyQt5 bootstrap)
├── requirements.txt           # Dependencies
├── AGENTS.md                  # Agent instructions (Trellis managed)
├── src/                       # Main source package
│   ├── __init__.py
│   ├── config.py              # Config singleton (YAML-backed)
│   ├── core/                  # Business logic (no UI, no I/O side-effects beyond checkpoint files)
│   │   ├── checkpoint_manager.py   # Task checkpoint persistence
│   │   ├── customer.py             # Customer list management
│   │   ├── extraction_result.py    # Extraction result dataclass
│   │   ├── extractor.py            # V1 extractor (legacy wrapper)
│   │   ├── flow_extractor_v2.py    # V2 AI-powered two-stage extractor
│   │   ├── matcher.py              # Name matching (exact/desensitized/fuzzy)
│   │   ├── progress_manager.py     # Progress reporting interface
│   │   ├── review_history.py       # Review result persistence
│   │   ├── reviewer.py             # Simplified review (no LLM, pure matching)
│   │   ├── scanner.py              # Document file scanner
│   │   └── task_manager.py         # High-level task orchestration
│   ├── export_flows/               # Export and skill bundle generation
│   │   ├── skill_export.py             # Single-task skill export
│   │   ├── board_skill_export.py       # Multi-task board skill export
│   │   ├── skill_assets/scripts/       # Export script templates
│   │   └── board_skill_assets/scripts/ # Board export script templates
│   ├── llm/                  # LLM integration layer
│   │   ├── audit_agent.py          # Report generation and QA via LLM
│   │   ├── data_normalizer.py      # AI row normalization
│   │   └── flow_table_classifier.py  # AI table classification
│   ├── parsers/              # Document parsers
│   │   ├── base.py                 # BaseParser ABC + FlowRecord/RawTable dataclasses
│   │   ├── docx_parser.py          # DOCX parser
│   │   ├── excel_parser.py         # Excel parser
│   │   ├── html_parser.py          # HTML table parser
│   │   └── pdf_parser.py           # MinerU-based PDF parser
│   └── ui/                   # PyQt5 UI layer
│       ├── __init__.py
│       ├── main_window.py          # MainWindow + SettingsDialog
│       ├── styles.py               # UI style constants
│       ├── pages/                  # One file per navigation page
│       └── widgets/                # Reusable UI widgets
└── tests/                    # Unit tests
    ├── test_checkpoint_and_task_manager.py
    ├── test_extraction_result.py
    ├── test_flow_extractor_v2_and_reviewer.py
    ├── test_pdf_parser.py
    └── test_review_history.py
```

---

## Module Organization

### Where new features go

| Feature type | Directory | Example |
|---|---|---|
| Core business logic (no UI) | `src/core/` | `reviewer.py`, `matcher.py` |
| Document parsing | `src/parsers/` | `excel_parser.py` |
| LLM/AI integration | `src/llm/` | `audit_agent.py` |
| UI pages | `src/ui/pages/` | `home_page.py` |
| UI widgets (reusable) | `src/ui/widgets/` | Custom PyQt5 widgets |
| Export/bundle logic | `src/export_flows/` | `skill_export.py` |
| Tests | `tests/` | `test_review_history.py` |

### Rules

- **`src/core/` must not import from `src/ui/`**. Core is UI-independent.
- **New parsers** subclass `BaseParser` (see `src/parsers/base.py`) and set `SUPPORTED_EXTENSIONS`.
- **New UI pages** follow the pattern in `src/ui/pages/`: one file per page, each exporting a `*Page(QWidget)` class.
- **LLM modules** access config via `get_config()`, never hardcode API URLs.

---

## Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Python files | `snake_case.py` | `flow_extractor_v2.py` |
| Classes | `PascalCase` | `FlowExtractorV2`, `ReviewMatch` |
| Dataclasses | `PascalCase`, noun phrase | `FlowRecord`, `RawTable`, `ReviewResult` |
| Config keys | `snake_case`, dot-separated for access | `flow_extraction.batch_size` |
| Config properties | `snake_case` with `@property` | `flow_batch_size` |
| Test files | `test_<module_name>.py` | `test_pdf_parser.py` |
| UI page files | `<name>_page.py` | `home_page.py`, `extract_page.py` |
| Chinese strings | Use Chinese directly in string literals | `"密码错误"`, `"精确匹配"` |

---

## Examples

- Well-organized core module: `src/core/reviewer.py` — single responsibility (review logic only), uses dataclasses for results, delegates matching to `NameMatcher`
- Clean parser pattern: `src/parsers/base.py` — ABC with `SUPPORTED_EXTENSIONS` class var and `extract_raw_tables()` abstract method
- Config singleton: `src/config.py` — `get_config()` function returns global instance, dot-notation access, `@property` shortcuts

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

## Scenario: FastAPI Auth Token Refresh Boundary

### 1. Scope / Trigger

- Trigger: React route guards and API retry logic depend on backend access/refresh token semantics.
- Use this contract when changing `backend/app/auth/`, `backend/app/routers/auth.py`, `web/app/lib/api.ts`, or `web/app/hooks/use-auth.ts`.

### 2. Signatures

- `POST /api/auth/login` accepts `username` and `password`.
- `POST /api/auth/refresh` accepts `refresh_token`.
- `GET /api/auth/me` requires a valid access token.

### 3. Contracts

- Login response includes `access_token`, `refresh_token`, and `token_type="bearer"`.
- Access tokens carry `type="access"` and are accepted by normal API dependencies.
- Refresh tokens carry `type="refresh"` and are accepted only by `/api/auth/refresh`.
- The frontend stores both tokens and may retry a 401 request once by calling `/api/auth/refresh`.
- `/api/auth/login` and `/api/auth/refresh` must not trigger recursive refresh attempts in the frontend API client.
- `/api/auth/me` must remain eligible for refresh retry so route guards can recover from an expired access token.

### 4. Validation & Error Matrix

- Bad username/password -> HTTP 401.
- Disabled user login -> HTTP 403.
- Refresh endpoint receives access token -> HTTP 401.
- Normal API dependency receives refresh token -> HTTP 401.
- Expired access token -> HTTP 401; frontend may refresh and retry if a refresh token exists.
- Missing refresh token in browser storage -> clear stored auth and surface the original 401.

### 5. Good/Base/Bad Cases

- Good: login stores both tokens, `/auth/me` succeeds, later expired access token is refreshed and the original request is retried.
- Base: no token in browser storage; route guard redirects to login.
- Bad: frontend skips refresh for `/auth/me`; route guard logs the user out even though the refresh token is still valid.

### 6. Tests Required

- API test asserts login returns both token types.
- API test asserts refresh rotates tokens.
- API test asserts refresh rejects access tokens.
- API test asserts `/auth/me` rejects refresh tokens.
- API test asserts expired access tokens are rejected.

### 7. Wrong vs Correct

#### Wrong

```typescript
if (response.status === 401 && !endpoint.includes("/api/auth/")) {
  await refreshAccessToken()
}
```

#### Correct

```typescript
const isRefreshEndpoint = endpoint === "/api/auth/login" || endpoint === "/api/auth/refresh"
if (response.status === 401 && !isRefreshEndpoint) {
  await refreshAccessToken()
}
```
