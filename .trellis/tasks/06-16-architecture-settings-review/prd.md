# System Architecture and Runtime Settings Review

## Goal

Review the current split FastAPI + React system from a whole-system architecture perspective. The review should identify whether the backend extraction flow, API boundaries, frontend interactions, and settings surface are sufficient for graceful operation, maintenance, and future extension.

## Requirements

* Review backend extraction architecture against the original `src` pipeline and the new FastAPI task API.
* Review whether FastAPI services are organized around clear boundaries: routers, services, background runners, checkpoints, database state, websocket notifications, and config/settings.
* Review frontend UX and integration for remaining fake data, dead buttons, ambiguous disabled states, wrong icons, missing API calls, and route/auth problems.
* Review settings page coverage: whether exposed settings are enough to run extraction gracefully, whether keys match backend runtime config, and whether missing operational settings are visible.
* Produce a prioritized finding list with concrete file references and suggested fixes.
* Implement only low-risk fixes that are clearly necessary during the review; defer larger architectural changes into follow-up tasks.

## Acceptance Criteria

* [ ] Findings cover backend architecture, extraction logic parity, settings/runtime config, frontend interactions, and cross-layer contracts.
* [ ] Each finding has severity, evidence, impacted files, and recommended action.
* [ ] Critical or quick low-risk defects discovered during review are fixed and verified.
* [ ] Tests/typechecks are run after any code changes.
* [ ] Larger follow-ups are explicitly listed instead of hidden.

## Definition of Done

* Review notes are persisted under this task directory.
* Any code changes made during review pass relevant checks.
* The user receives a concise architecture-level status report and prioritized next actions.

## Technical Notes

* Prior integration commits:
  * `f214ef0 feat: add task extraction integration`
  * `48be266 feat: wire auth and frontend integration`
  * `0877bf9 docs: document integration contracts`
* Relevant specs:
  * `.trellis/spec/backend/directory-structure.md`
  * `.trellis/spec/backend/quality-guidelines.md`
  * `.trellis/spec/backend/error-handling.md`
  * `.trellis/spec/guides/cross-layer-thinking-guide.md`
  * `.trellis/spec/guides/code-reuse-thinking-guide.md`
