# Web Split Parity Review Fixes

## Goal

Close the gaps surfaced by the review of the 06-17 web split parity work so
the FastAPI + React split reaches the acceptance criteria each child task
claimed, rather than leaving half-wired flows and identity bugs.

## Background

A review of the completed parity umbrella found five issues ranging from a
missing frontend entry point (P1) to a document-identity bug that can drop or
reuse records across same-named files (P1). The fixes are scoped to the
already-merged work; no new features.

## Findings to Fix

### P1-a Append extraction has no frontend entry
`backend/app/routers/tasks.py` exposes `POST /api/tasks/{task_id}/append`, but
`web/app/routes/tasks.tsx` only offers start/pause/resume/cancel and the
completed-task review/export workflow. Users cannot append documents from the
web UI, so the append contract is not closed.

The web app must not require a backend-local directory path (that is the
desktop `src` semantics). Instead, both task creation and append must use
browser file selection / drag-and-drop upload, so a user picks or drops files
directly in the browser.

### P1-b Document identity uses filename, not full path
`backend/app/services/extraction/checkpoint.py` keys checkpoints by
`document_name` only, and `extractor.py` loads/saves checkpoints and builds
`source_file` from `doc_path.name`. The runner then dedups append merges by
`source_file`. Two files named `流水.pdf` in different folders collide: a new
file can be skipped, an old checkpoint reused, or records dropped. The
original `src` pipeline hashes `name|path` (path normalized to posix) and
dedups append documents by full path.

### P2-a Single PDF calls MinerU twice
`extract_raw_tables()` calls `_get_markdown()`, then stage 1 calls
`extract_non_table_context()` which calls `_get_markdown()` again. For the
public MinerU agent this uploads/polls/downloads the same PDF twice. PRD
requires reusing the same markdown to avoid redundant API calls.

### P2-b Review button state contradicts its message
When no customer list exists, the workflow dialog shows "审查将使用系统默认
名单" but `handleRunReview()` errors out when `selectedListId` is empty, and
the button stays enabled. PRD requires disabled states to explain the missing
prerequisite rather than present an inert, contradictory control.

### P3 Placeholder AI/Security settings tabs
`web/app/routes/settings.tsx` renders AI and Security tabs whose content is
only "后续版本中提供". This is decorative config surface, inconsistent with
the "no decorative settings" direction.

## Scope

- P1-a: replace the backend-local directory input with browser file upload
  for both task creation and append:
  - backend: add a multipart upload endpoint that saves uploaded files under
    a per-task folder (under `UPLOAD_DIR`) and starts extraction (or append)
    against that folder; keep the parser/extraction pipeline unchanged
    (it still reads from a filesystem folder).
  - frontend `tasks.tsx`: create-task dialog and a new append dialog both use
    a file picker (multi-select) + drag-and-drop dropzone + a removable
    selected-files list; submitting uploads the files then triggers start /
    append.
  - remove the `document_folder` text input from the create dialog.
- P1-b: make document identity path-aware across the backend extraction layer:
  - `checkpoint.py`: add `document_path` to load/save/clear signatures and
    key checkpoint files by `name|path` hash (posix-normalized), mirroring
    `src/core/checkpoint_manager.py`.
  - `extractor.py`: pass `document_path=str(doc_path)` at every checkpoint
    call; keep `source_file` as the filename for display but use full path
    for identity/dedup where it matters.
  - `extract_flows_append`: scan the new folder and skip documents whose full
    path already appears in the task's prior `last_result.processed_document_paths`,
    so a same-named file in a new folder is still processed and a same-path
    file is skipped.
  - `runner._merge_results`: dedup by full document path, not `source_file`.
- P2-a: have `PDFParser` parse markdown once per file within a single stage-1
  pass and feed it to both table extraction and non-table context; avoid the
  second MinerU call.
- P2-b: when no customer list exists, disable the review button and show a
  message that explains the prerequisite (create a list first), removing the
  "default list" wording.
- P3: remove the AI and Security placeholder tabs from `settings.tsx`.

## Reference Files

- `backend/app/services/extraction/checkpoint.py`
- `backend/app/services/extraction/extractor.py`
- `backend/app/services/extraction/runner.py`
- `backend/app/parsers/pdf_parser.py`
- `backend/app/routers/tasks.py`
- `web/app/routes/tasks.tsx`
- `web/app/routes/settings.tsx`
- `src/core/checkpoint_manager.py` (reference for path-aware hash + dedup)
- `src/core/flow_extractor_v2.py` (reference for append dedup by full path)

## Acceptance Criteria

- Task creation and append both upload files via the browser (multi-select
  picker + drag-and-drop + removable selected-files list); no backend-local
  directory path is typed by the user. The uploaded files are extracted.
- A completed task in the web UI has an append action that uploads new files
  and the task returns to running.
- Two files with the same name in different folders (e.g. uploaded in two
  separate append runs) are treated as distinct documents: both are processed,
  neither's checkpoint is reused by the other, and append does not drop the
  new one.
- A single PDF is parsed by MinerU at most once per stage-1 pass (table +
  non-table context share one markdown fetch); a test asserts `_get_markdown`
  is called once.
- With no customer list, the review button is disabled and its helper text
  says to create a list first; no "default list" promise.
- Settings page has no placeholder AI/Security tabs.
- Backend tests pass (existing + new tests for upload, path-aware
  checkpoint/dedup, and single-MinerU-call); frontend typecheck + build pass.

## Out of Scope

- Re-architecting the extraction pipeline beyond the identity/dedup fix.
- New settings categories or redesigning the settings layout beyond removing
  placeholder tabs.
- Changing backend append/report/export algorithms outside the dedup identity.
