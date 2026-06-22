# Web Split Production Parity Follow-up

## Goal

Coordinate the implementation work discovered during `architecture-settings-review` so the FastAPI + React split reaches functional parity with the original `src` pipeline instead of staying at demo-level integration.

## Background

The architecture review fixed two immediate blockers: customer-list creation and extraction-result persistence into review-readable `Document.flow_tables`. Remaining issues are larger and should be assigned as focused implementation tasks.

Reference review: `.trellis/tasks/06-16-architecture-settings-review/review.md`.

## Child Tasks

1. `06-17-web-extraction-parity-mineru` - restore original MinerU PDF behavior for heterogeneous PDF parsing.
2. `06-17-web-llm-prompt-parity` - port mature `src/llm` prompts and normalization safeguards.
3. `06-17-web-review-report-export-ux` - expose review/report/export workflows in React.
4. `06-17-web-settings-append-contract` - align settings runtime behavior and append semantics.

## Acceptance Criteria

- Each child task has a PRD with scope, references, and verification requirements.
- Child tasks can be assigned independently without hidden cross-task ambiguity.
- The parent task is complete only after all children are completed or intentionally superseded.

## Coordination Notes

- Recommended order: MinerU parity and LLM prompt parity first if extraction quality is the priority; review/export UX can proceed in parallel because backend endpoints already exist.
- Settings/append contract should consume the decisions made by MinerU parity so the UI exposes real parser settings, not placeholders.
- Avoid broad rewrites that reduce existing backend test coverage or remove current frontend task/customer flows.
