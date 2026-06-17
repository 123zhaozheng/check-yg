# Align Settings and Append Runtime Contracts

## Goal

Make the web settings surface and append extraction behavior honest and operational: settings exposed in the UI must affect backend runtime, and append extraction should match the original checkpoint/dedup/merge semantics closely enough for production use.

## Problem

The settings UI writes MinerU keys that current runtime code does not consume, while append extraction delegates to a plain extraction run and relies mostly on result merging. This creates confusing UX and weaker operational semantics than the original `src` flow.

## Scope

- Audit every setting shown in `web/app/routes/settings.tsx` against `backend/app/services/settings_service.py` and runtime consumers.
- Wire real runtime consumers for relevant settings or hide/de-emphasize controls that are not implemented.
- Add missing operational settings needed by extraction, such as LLM timeout and flow thresholds, only if they are consumed by runtime code.
- Align append extraction with original behavior:
  - Store all task document folders, not just last folder.
  - Deduplicate new documents against existing paths.
  - Preserve previous records and per-document stats.
  - Preserve checkpoint/resume behavior where possible.
- Update specs if the web runtime contract intentionally differs from desktop `src`.

## Reference Files

- `web/app/routes/settings.tsx`
- `backend/app/services/settings_service.py`
- `backend/app/routers/settings.py`
- `backend/app/services/extraction/extractor.py`
- `backend/app/services/extraction/runner.py`
- `src/core/checkpoint_manager.py`
- `src/core/flow_extractor_v2.py`
- `.trellis/spec/backend/database-guidelines.md`

## Acceptance Criteria

- No settings page field is purely decorative.
- Runtime settings are loaded once per task run and passed into the components that need them.
- Append extraction skips duplicate documents and merges records without losing prior results.
- Tests cover setting load/override behavior and append merge/dedup behavior.
- Existing backend tests and frontend typecheck pass.

## Out of Scope

- Full settings redesign.
- Implementing user/role administration UI unless required by settings permissions.
