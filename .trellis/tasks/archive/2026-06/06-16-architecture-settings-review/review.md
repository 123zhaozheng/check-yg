# Architecture and UX Review

## Scope

Reviewed `feat/web-split` against the original `src` desktop pipeline and the new FastAPI + React split. The review covered extraction parity, backend service boundaries, settings/runtime config, customer-list UX, task-to-review data flow, and verification commands.

## Fixed During Review

### P0 - Customer list creation was a dead UI path

- Evidence: `web/app/routes/customers.tsx` rendered "新建名单" and "导入名单" as disabled buttons, and `backend/app/routers/customers.py` only exposed `GET /api/customers/lists`.
- Impact: users could not create the required customer-list input for review matching. This made the review/report chain unusable from the web UI.
- Fix:
  - Added `POST /api/customers/lists` with owner scoping, empty-name validation, customer-name cleanup, and ordered de-duplication.
  - Replaced the disabled customer-list page with a working create/import dialog. Users can paste newline/comma/semicolon/tab separated names or import a `.txt/.csv` file.
  - Added API tests for creation, de-duplication, and owner scoping.

### P0 - Extraction result was not available to review/report services

- Evidence: `ExtractionTaskRunner._mark_finished()` stored records only under `Task.config.last_result`; `ReviewService.load_task_records()` reads from `Document.flow_tables`.
- Impact: a completed extraction could appear successful, but review/report/export services would load zero records unless `Document` rows were separately seeded.
- Fix:
  - Runner now mirrors normalized `flow_records` into `documents` rows grouped by `source_file`.
  - Added a regression test for the persistence helper.

## Architecture Findings

### P0 - PDF parsing parity is weaker than the original `src` flow

- Evidence:
  - Original `src/parsers/pdf_parser.py` uses MinerU markdown/table extraction and removes table blocks to build non-table context.
  - New `backend/app/parsers/pdf_parser.py` uses `pdfplumber` directly.
- Impact: heterogeneous PDF handling is likely less robust than the original flow, especially scanned/complex table PDFs. This is a functional parity risk, not just an implementation difference.
- Recommended action: port the original MinerU local/public parser behavior into the FastAPI backend, including encrypted PDF handling, markdown extraction, non-table context truncation, and raw HTML table preservation.

### P1 - LLM prompts in backend are reduced compared with `src`

- Evidence:
  - Original `src/llm/document_portrait.py` explicitly constrains `account_type`, `amount_sign_rule`, `header_attributes`, and `column_mapping`.
  - New `backend/app/llm/portrait.py`, `classifier.py`, and `normalizer.py` are much shorter and lose several detailed rules around credit-card signs, date-year inference, raw amount preservation, and column mapping.
- Impact: heterogeneous statement normalization quality may regress even when API calls succeed.
- Recommended action: move the mature prompts and fallback logic from `src/llm/*` into `backend/app/llm/*` before treating the web extractor as production-equivalent.

### P1 - Append extraction is API-shaped but semantically shallow

- Evidence: `backend/app/services/extraction/extractor.py::extract_flows_append()` delegates directly to `extract_flows()` for the new folder. Original `src/core/flow_extractor_v2.py` has checkpoint-level append semantics and previous report merging.
- Impact: append works as an additional run at the API/result merge layer, but it does not preserve all original checkpoint semantics such as document-folder lists and duplicate skipping against task metadata.
- Recommended action: port original append checkpoint semantics or document the intentionally simplified behavior.

### P1 - Settings page exposes keys the runtime only partially consumes

- Evidence:
  - Runtime consumes `llm.base_url`, `llm.model_name`, `llm.api_key`, and `llm.timeout`.
  - UI writes `mineru.mode`, `mineru.max_concurrency`, and `mineru.api_endpoint`, but current backend parser ignores them.
- Impact: users can save settings that look operational but do not affect extraction, which is a high-friction UX trap.
- Recommended action: either wire MinerU settings into `PDFParser` initialization or hide those controls until they are real.

### P1 - Completed task next actions are not yet first-class in the frontend

- Evidence: backend exposes review/report/export endpoints, but the task action menu only starts/pauses/resumes/cancels extraction.
- Impact: after extraction finishes, users still lack an obvious "run review / report / export" workflow. This makes the app feel like a demo even though backend capabilities exist.
- Recommended action: add completed-task actions for review, report, Excel export, and bundle export. The review action should prompt for a customer list when multiple lists exist.

### P2 - Several frontend routes remain placeholders

- Evidence: `web/app/routes/logs.tsx`, `prompts.tsx`, `templates.tsx`, and secondary tabs in `settings.tsx` show "后续版本" copy.
- Impact: acceptable for MVP if intentionally scoped, but the nav makes them look like live product surfaces.
- Recommended action: either implement a minimal real read-only surface or hide them from primary navigation until connected.

### P2 - Test command contract is easy to misrun

- Evidence: running `uv run --project backend pytest` from the repo root collected both root `tests/` and backend tests and failed imports. Running from `backend/` with `PYTHONPATH=.` passes.
- Impact: contributors can get false-negative test runs.
- Recommended action: add a backend test script or pyproject pytest path/pythonpath config.

## Verification

- `pnpm -C web typecheck` passed.
- `$env:PYTHONPATH='.'; uv run pytest` from `backend/` passed: 23 tests.
- Known warning: Pydantic class-based `Config` deprecation warnings remain.

