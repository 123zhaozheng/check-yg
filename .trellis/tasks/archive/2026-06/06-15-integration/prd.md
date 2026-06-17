# Frontend Backend Integration, Audit, and Finalization

## Goal

Complete the final integration task for the FastAPI + React split by auditing and fixing backend extraction flow parity, API contracts, frontend wiring, interaction behavior, and quality gates. The finished system should not depend on placeholder data for core workflows and should expose usable backend interfaces for the migrated flow-processing architecture.

## Requirements

* Backend extraction flow must be checked against the original `src/core/flow_extractor_v2.py` behavior, especially two-stage processing, checkpoints, resume/append semantics, progress reporting, cancellation/pause, document portrait extraction, table classification, and row normalization.
* Backend FastAPI code must expose appropriate task/extraction interfaces instead of leaving the extraction pipeline as unused internal code.
* Backend services should be organized for the FastAPI architecture: request validation at API boundaries, service-level orchestration, database/task metadata consistency, and websocket progress notifications where useful.
* Frontend pages must be audited for fake data, unimplemented handlers, dead buttons, wrong icons, broken navigation, and missing backend API calls.
* Frontend API client contracts must match backend routes, auth behavior, payload shapes, and error handling.
* Any fix should follow existing project patterns and avoid broad unrelated refactors.
* The task must end with lint/typecheck/test verification appropriate to touched backend and frontend code.

## Acceptance Criteria

* [ ] Extraction/task APIs exist for creating extraction tasks, starting extraction from a folder, listing tasks, viewing task detail, pausing/resuming/canceling work where supported, and appending new documents where supported.
* [ ] Backend extraction logic either reuses or faithfully ports the original `src` pipeline behavior, with documented intentional differences.
* [ ] Task status/progress shown by the frontend comes from backend APIs or websocket updates, not hardcoded mock workflow data.
* [ ] Primary frontend buttons on dashboard/tasks/customers/settings/auth flows either perform real actions, show honest disabled states, or are removed if out of scope.
* [ ] Frontend routes do not reference missing components or undefined API methods.
* [ ] Auth gating and API error handling are coherent across app routes.
* [ ] Backend tests cover the new/changed API contracts without requiring external LLM or document services.
* [ ] Frontend typecheck passes.

## Definition of Done

* Backend tests pass for changed services and routers.
* Frontend typecheck passes.
* Cross-layer API contracts are verified by code inspection and tests where practical.
* Remaining limitations, if any, are explicit and not hidden behind fake UI data.
* Trellis spec update is considered after implementation.

## Technical Approach

Use the original `src` extraction pipeline as the behavioral source of truth. The FastAPI backend should not duplicate a shallow alternate pipeline if that loses checkpoint and resume behavior; instead, it should adapt the richer logic into service and router boundaries suitable for HTTP and websocket clients. Frontend changes should prefer existing route/component patterns and connect visible workflow controls to typed API methods.

## Decision (ADR-lite)

**Context**: The web split already introduced FastAPI and React surfaces, but the final task is explicitly about checking whether the backend flow-processing logic still matches the original desktop implementation and whether the frontend is truly connected.

**Decision**: Treat this as an audit-and-fix task. First inspect current backend/frontend contracts, then repair the highest-impact mismatches and remove or mark placeholder UI behavior honestly.

**Consequences**: Some deeper extraction execution behavior may remain constrained by local filesystem and LLM configuration, but the API and frontend must expose real contracts and avoid pretending unavailable behavior is complete.

## Out of Scope

* Rebuilding the entire visual design system from scratch.
* Replacing the LLM provider or document parsing engines.
* Implementing cloud file upload/storage unless already present and needed for the existing flow.
* Changing the original desktop `src` behavior except where tests reveal a bug directly blocking the web migration.

## Technical Notes

* Active task: `.trellis/tasks/06-15-integration`.
* Original flow reference: `src/core/flow_extractor_v2.py`, `src/core/task_manager.py`, `src/core/checkpoint_manager.py`.
* Current FastAPI extraction code: `backend/app/services/extraction/extractor.py`, `backend/app/services/extraction/checkpoint.py`, `backend/app/routers/tasks.py`.
* Frontend surfaces to audit: `web/app/routes/*.tsx`, `web/app/lib/api.ts`, `web/app/hooks/use-auth.ts`, `web/app/lib/websocket.ts`.
* Backend specs loaded: `.trellis/spec/backend/*.md`, `.trellis/spec/guides/cross-layer-thinking-guide.md`, `.trellis/spec/guides/code-reuse-thinking-guide.md`.
